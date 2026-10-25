"""Playing-conditions timeline: what the rules were for a given match.

Method. ``config/cricket-rules.json`` holds an ordered list of layers. A layer
matches on format, gender, team type, competition, tier, event, official status,
associate flag, the teams involved and whether the match is a knockout, and on a
half-open date range; matching layers are applied in file order, later ones
overriding earlier ones field by field (plan section 5). :func:`rules_for` then
resolves per-match facts: scheduled days (four-day Tests change overs per day and
the follow-on lead), knockout-only DRS and tie-breaks, ``drs_scope='none'``
clearing the review count, the follow-on lead by days remaining (Law 14.1), the
free-hit probability after a no-ball, and the reduced-innings tables: bowler
quotas and powerplay windows for every innings length N (``bowler_quota_reduced``
and ``pp_windows_reduced``, keyed by ``str(N)``). The engine applies those with the
N known at the time: an innings cut after its powerplay keeps the powerplay it
had, and a bowler already past a new quota bowls no more. Field names follow plan
section 5 (:data:`PLAN_FIELDS`, all returned); the earlier names are returned too as
deprecated aliases (:data:`LEGACY_ALIASES`; ``super_over``/``super_over_this_match`` keep
the old values ``single``/``repeat`` for ``so_boundary_count``/``so_repeat``). Every
returned dict carries ``_layers``, the layer or table that set each field.

Validation. :func:`validate` streams the Cricsheet zip once and checks every
data-testable field against what the timeline says for each match: DRS observed
share by event and by series (:func:`match_drs_available` and the series key), the
most unsuccessful non-umpire's-call reviews by one team in an innings, recorded
powerplay windows (full and reduced innings), scheduled overs and balls per over,
bowler quotas (full and reduced), follow-on enforcements and leads, impact-player
replacements, protected dismissals on free-hit balls (which also estimates
``p_free_hit_given_nb``), who faces after a mid-over catch, one- versus two-run
no-balls, tie-breaks, minimum overs in rain-rule results, Test days and overs per
day, and the umpire's-call share by zone era.

Limits. Where Cricsheet cannot see a rule (two new balls, stop clock, fielders
outside the circle beyond powerplays, the umpire's-call zone) the value is from
memory and marked so. Whether a match had DRS is series-specific;
``drs_available`` is the competition default and ``drs_scope='selected'`` marks
partial coverage (set by team, since the venue is not an input), so models fitted on
history should use :func:`match_drs_available` or
:func:`beating.cricket.competitions.drs_available_for_matches`.
Umpire's-call flags are only recorded from late 2017, so earlier counts treat every
failed review as lost. Reduced tables are keyed by whole overs and cover only the
first (and, for men's ODIs, all three) mandatory powerplays.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import zipfile

from beating.cricket.competitions import assign_series_keys, competition_for, competition_meta

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "cricket-rules.json"
FIELDS = (
    "overs_per_innings", "balls_per_over", "balls_per_innings", "bowler_quota", "bowler_quota_balls",
    "reduced_quota_rule", "pp_windows", "pp_reduced_rule", "field_restr", "free_hit", "noball_penalty_runs",
    "drs_available", "drs_scope", "reviews_per_innings", "umpires_call_retains_review", "review_topup_after_80",
    "ucall_zone_era", "test_overs_per_day", "scheduled_days", "new_ball_after_overs", "two_new_balls",
    "two_new_balls_until_over", "impact_player", "tactical_sub", "tie_break", "min_overs_for_result",
    "max_consecutive_balls_per_end", "slow_over_rate_fielding_penalty", "stop_clock", "concussion_substitutes",
    "caught_crossing_counts",
)
DERIVED = ("drs_allowed", "tie_break_rule", "min_balls_for_result", "p_free_hit_given_nb", "follow_on_lead",
           "follow_on_lead_by_days", "bowler_quota_reduced", "pp_windows_reduced")
LEGACY_ALIASES = {"noball_extra_runs": "noball_penalty_runs", "test_days": "scheduled_days",
                  "powerplay_overs": "pp_windows", "fielders_outside": "field_restr",
                  "bowler_quota_overs": "bowler_quota", "balls_in_use": "two_new_balls",
                  "super_over": "tie_break_rule", "super_over_this_match": "tie_break"}
PLAN_FIELDS = ("overs_per_innings", "balls_per_over", "bowler_quota", "pp_windows", "field_restr", "free_hit",
               "p_free_hit_given_nb", "noball_penalty_runs", "caught_crossing_counts", "drs_allowed",
               "reviews_per_innings", "umpires_call_retains_review", "review_topup_after_80", "ucall_zone_era",
               "test_overs_per_day", "scheduled_days", "follow_on_lead", "new_ball_after_overs", "two_new_balls",
               "impact_player", "tie_break", "min_overs_for_result")  # plan section 5, in its order
TIE_BREAKS = ("none", "bowl_out", "so_boundary_count", "so_repeat")
LEGACY_TIE_BREAK = {"so_boundary_count": "single", "so_repeat": "repeat"}
QUOTA_RULES = ("fifth_min2", "hundred_balls")
WHEN_KEYS = {"fmt", "gender", "team_type", "competition_id", "tier", "event_id", "official", "assoc_match",
             "teams_any", "teams_all", "knockout", "stage_regex"}
KNOCKOUT_RE = re.compile(r"(?<!race to the )final|semi|quarter|qualifier \d|qualifier$|eliminator|play-?off|"
                         r"knock-?out|challenger", re.IGNORECASE)
RAIN_METHODS = {"D/L", "DLS", "VJD"}
PROTECTED = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
CAUGHT = {"caught", "caught and bowled"}
NOT_OUT = {"retired hurt", "retired not out"}


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> dict:
    cfg = json.loads(Path(path or CONFIG_PATH).read_text())
    tables = set(cfg.get("reduced_tables", {}))
    for layer in cfg["layers"]:
        bad = set(layer.get("when", {})) - WHEN_KEYS
        unknown = set(layer["set"]) - set(FIELDS)
        st = layer["set"]
        if bad or unknown:
            raise ValueError(f"layer {layer['id']}: bad when keys {bad} or fields {unknown}")
        if st.get("pp_reduced_rule") not in tables | {None} or st.get("reduced_quota_rule") not in (*QUOTA_RULES, None):
            raise ValueError(f"layer {layer['id']}: unknown reduced rule")
        if "tie_break" in st and st["tie_break"] not in (*TIE_BREAKS, "knockout_only"):
            raise ValueError(f"layer {layer['id']}: unknown tie_break {st['tie_break']!r}")
    return cfg


def is_knockout(stage: str | None) -> bool:
    return bool(stage) and bool(KNOCKOUT_RE.search(stage))


def _matches(when: dict, ctx: dict) -> bool:
    for key, want in when.items():
        if key == "teams_any":
            if not ctx["teams"] or not any(t in want for t in ctx["teams"]):
                return False
        elif key == "teams_all":
            if not ctx["teams"] or not all(t in want for t in ctx["teams"]):
                return False
        elif key == "stage_regex":
            if not ctx["stage"] or not re.search(want, ctx["stage"], re.IGNORECASE):
                return False
        elif isinstance(want, list):
            if ctx.get(key) not in want:
                return False
        elif bool(ctx.get(key)) != bool(want):
            return False
    return True


def reduced_quota(rule: str, n: int, bpo: int = 6) -> list[int]:
    """[max overs per bowler, bowlers allowed one more, max balls] for an innings of ``n`` overs.

    ``fifth_min2``: floor(n/5) overs, n mod 5 bowlers one more; below 10 overs every
    bowler may bowl 2. ``hundred_balls``: n/5 of the balls rounded up to whole sets, at
    least 10 balls, with no extra-bowler allowance."""
    if rule == "hundred_balls":
        balls = max(10, bpo * ((n * bpo + 5 * bpo - 1) // (5 * bpo)))
        return [balls // bpo, 0, balls]
    q, extra = (min(2, n), 0) if n < 10 else (n // 5, n % 5)
    return [q, extra, q * bpo]


def reduced_powerplay(rule: str, n: int, bpo: int, field_restr: list) -> dict:
    """Mandatory powerplay windows and fielding limits for an innings of ``n`` overs, in legal balls.

    Integer formulas (round half up) so the JavaScript engine can mirror them exactly;
    the limit after the last window is the full-length table's last value."""
    balls, tail = n * bpo, field_restr[-1][2]
    if rule == "odi_p123_men":
        p2 = (6 * n + 5) // 10
        p1 = (n - p2 + 1) // 2
        cuts = [p1 * bpo, (p1 + p2) * bpo]
        lims = [field_restr[0][2], field_restr[1][2] if len(field_restr) > 2 else tail, tail]
        bounds = [0] + [min(c, balls) for c in cuts] + [balls]
        wins = [[a + 1, b] for a, b in zip(bounds, bounds[1:]) if b > a]
        return {"mandatory": wins, "field_restr": [w + [lim] for w, lim in zip(wins, lims) if w[1] >= w[0]]}
    p1 = {"t20_overs": bpo * ((3 * n + 5) // 10), "t20_balls": (3 * balls + 5) // 10,
          "t20_surge": bpo * max(2, (n + 4) // 5), "odi_p1_round": bpo * ((2 * n + 5) // 10),
          "hundred_quarter": (balls + 2) // 4}[rule]
    p1 = max(1, min(p1, balls))
    restr = [[1, p1, field_restr[0][2]]] + ([[p1 + 1, balls, tail]] if p1 < balls else [])
    return {"mandatory": [[1, p1]], "field_restr": restr}


def follow_on_threshold(rules: dict, days_remaining: int) -> int | None:
    """Law 14.1 follow-on lead for the days remaining when play first starts (Law 14.1.3)."""
    table = rules.get("follow_on_lead_by_days")
    return None if not table else table[str(max(1, min(5, int(days_remaining))))]


@lru_cache(maxsize=65536)
def _resolve(competition_id: str, fmt: str, gender: str, date: str, event_id: str | None, teams: tuple,
             official: bool, assoc_match: bool, knockout: bool, stage: str | None, scheduled_days: int | None,
             config_path: str | None) -> tuple:
    cfg = load_config(config_path)
    meta = competition_meta(competition_id)
    ctx = dict(fmt=fmt, gender=gender, team_type=meta["team_type"], competition_id=competition_id,
               tier=meta["tier"], event_id=event_id or competition_id, official=official,
               assoc_match=assoc_match, teams=teams, knockout=knockout, stage=stage)
    out, source = {}, {}
    for layer in cfg["layers"]:
        if layer.get("from") and date < layer["from"]:
            continue
        if layer.get("until") and date >= layer["until"]:
            continue
        if _matches(layer.get("when", {}), ctx):
            for k, v in layer["set"].items():
                out[k], source[k] = v, layer["id"]
    if scheduled_days is not None:
        extra = cfg.get("scheduled_days_rules", {}).get(fmt, {}).get(str(scheduled_days))
        for k, v in (extra or {}).items():
            out[k], source[k] = v, f"scheduled_days_{scheduled_days}"
    if out["drs_scope"] == "knockouts":
        out["drs_available"] = knockout
    if out["drs_scope"] == "none":
        out["drs_available"], out["reviews_per_innings"] = False, None
    out["drs_allowed"] = out["drs_available"] or out["drs_scope"] == "selected"
    source["drs_allowed"] = source["drs_scope"]
    rule = out["tie_break"]
    if rule == "knockout_only":
        out["tie_break"] = ("so_repeat" if date >= "2019-10-14" else "so_boundary_count") if knockout else "none"
    out["tie_break_rule"], source["tie_break_rule"] = rule, source["tie_break"]
    mo, bpo, n_sched = out["min_overs_for_result"], out["balls_per_over"], out["overs_per_innings"]
    out["min_balls_for_result"] = None if mo is None else mo * bpo
    source["min_balls_for_result"] = source["min_overs_for_result"]
    fh = out["free_hit"]
    table = cfg.get("p_free_hit_given_nb", {})
    out["p_free_hit_given_nb"] = {"none": 0.0, "all_noballs": 1.0}.get(
        fh, table.get("by_competition", {}).get(competition_id, table.get("default")))
    source["p_free_hit_given_nb"] = source["free_hit"] if fh != "front_foot" else "p_free_hit_given_nb"
    days = out["scheduled_days"]
    by_days = cfg["follow_on_lead_by_days"]["table"] if days else None
    out["follow_on_lead_by_days"] = by_days
    out["follow_on_lead"] = by_days[str(min(5, days))] if days else None
    source["follow_on_lead"] = source["follow_on_lead_by_days"] = "follow_on_lead_by_days"
    qr, pr = out["reduced_quota_rule"], out["pp_reduced_rule"]
    ns = range(1, (n_sched or 0) + 1)
    out["bowler_quota_reduced"] = {str(n): reduced_quota(qr, n, bpo) for n in ns} if qr else None
    out["pp_windows_reduced"] = ({str(n): reduced_powerplay(pr, n, bpo, out["field_restr"]) for n in ns}
                                 if pr and out["field_restr"] else None)
    source["bowler_quota_reduced"], source["pp_windows_reduced"] = source["reduced_quota_rule"], source["pp_reduced_rule"]
    two, until = out["two_new_balls"], out["two_new_balls_until_over"]
    legacy = dict(out, balls_in_use="two_balls_until_34" if two and until else "two_new_balls" if two else "one",
                  tie_break_rule=LEGACY_TIE_BREAK.get(rule, rule), tie_break=LEGACY_TIE_BREAK.get(out["tie_break"],
                                                                                                 out["tie_break"]))
    for old, new in LEGACY_ALIASES.items():
        out[old] = legacy.get(old, legacy[new])
        source[old] = source[new]
    return tuple(sorted(out.items())), tuple(sorted(source.items()))


def rules_for(competition_id: str, fmt: str, gender: str, date, *, event_id: str | None = None,
              teams=None, official: bool = True, assoc_match: bool = False, knockout: bool | None = None,
              stage: str | None = None, scheduled_days: int | None = None, match_id=None,
              config_path: str | None = None) -> dict:
    """Every section-5 field for one match; ``_layers`` gives the layer that set each field.

    ``knockout`` defaults to :func:`is_knockout` of ``stage``; ``match_id`` picks up
    ``match_overrides`` (scheduled days) from the config. ``drs_allowed`` (plan section 5)
    is true when the rules permit DRS in this match, including ``drs_scope='selected'``
    series; ``drs_available`` is only the competition default. ``tie_break`` is resolved
    for this match (stage and date); ``tie_break_rule`` is the configured value."""
    date = str(date)[:10]
    if knockout is None:
        knockout = is_knockout(stage)
    if match_id is not None and scheduled_days is None:
        override = load_config(config_path).get("match_overrides", {}).get(str(match_id), {})
        scheduled_days = override.get("scheduled_days")
    items, source = _resolve(competition_id, fmt, gender, date, event_id, tuple(teams or ()), bool(official),
                             bool(assoc_match), bool(knockout), stage, scheduled_days, config_path)
    out = json.loads(json.dumps(dict(items)))
    out["_layers"] = dict(source)
    return out


def rules_for_match(info: dict, match_id=None, config_path: str | None = None) -> dict:
    """Rules for a Cricsheet ``info`` dict (competition, teams, stage and date taken from it)."""
    comp = competition_for(info)
    stage = (info.get("event") or {}).get("stage")
    return rules_for(comp.competition_id, comp.fmt, comp.gender, info["dates"][0], event_id=comp.event_id,
                     teams=info.get("teams"), official=comp.official or comp.team_type != "international",
                     assoc_match=comp.assoc_match, stage=stage, match_id=match_id, config_path=config_path)


def match_drs_available(matches: "pd.DataFrame") -> "pd.DataFrame":
    """Plan 4.2 ``drs_available`` and ``drs_source`` per match.

    Needs ``series_key``, ``drs_allowed`` (from :func:`rules_for`), ``has_review`` (any
    review recorded in the match) and ``reviews_missing`` ('reviews' in ``info.missing``).
    The value is drs_allowed AND (a review in the match OR in another match of the same
    series whose reviews are not missing) AND reviews are not missing: ``unknown``
    (null) when missing, ``rules`` when the rules forbid DRS, ``match`` when the match
    has a review, otherwise ``series`` (true when the series has a review)."""
    import pandas as pd

    seen = matches["has_review"].astype(bool) & ~matches["reviews_missing"].astype(bool)
    series_seen = seen.groupby(matches["series_key"]).transform("any")
    allowed = matches["drs_allowed"].astype(bool)
    missing = matches["reviews_missing"].astype(bool)
    source = pd.Series("series", index=matches.index)
    source[seen] = "match"
    source[~allowed] = "rules"
    source[missing] = "unknown"
    value = (allowed & series_seen).astype(object)
    value[missing] = None
    return pd.DataFrame({"drs_available": value, "drs_source": source})


# ---------------------------------------------------------------- data scan

def _over_no(x: float) -> int:
    return int(math.floor(x)) + 1


def _ball_pos(x: float) -> tuple[int, int]:
    """Cricsheet ``over.delivery`` (0-based over, 1-based delivery incl. extras) as a tuple."""
    o = int(math.floor(x))
    return o, int(round((x - o) * 10))


def scan_match(d: dict, match_id: str) -> dict:
    """Compact per-match summary used by :func:`validate`."""
    info = d["info"]
    ev = info.get("event") or {}
    keep = ("match_type", "gender", "team_type", "dates", "teams", "season", "overs", "balls_per_over", "outcome")
    rec = {k: info.get(k) for k in keep}
    rec.update(match_id=str(match_id), event={k: ev[k] for k in ("name", "stage") if k in ev},
               reviews_missing="reviews" in [m for m in info.get("missing", []) if isinstance(m, str)],
               innings=[])
    rec["season"] = str(rec["season"])
    by_over = info.get("match_type") not in ("Test", "MDM")
    for inn in d["innings"]:
        raw_pp = inn.get("powerplays", [])
        pps = [(p.get("type"), _over_no(p["from"]), _over_no(p["to"])) for p in raw_pp]
        r = dict(team=inn["team"], super_over=bool(inn.get("super_over")), declared=bool(inn.get("declared")),
                 forfeited=bool(inn.get("forfeited")), target=inn.get("target"), powerplays=pps,
                 pp_raw=[(p.get("type"), p["from"], p["to"]) for p in raw_pp])
        legal = runs = wkts = prot_wkts = 0
        max_over, nb, bowler_balls, bowler_overs, reviews, repl = -1, Counter(), Counter(), defaultdict(set), [], []
        fh_pending, fh_n, fh_viol, sets, catches, crossed = False, 0, 0, [], 0, 0
        legal_by_over, prot_by_over, fh_by_over, cum = Counter(), Counter(), Counter(), {}
        for o in inn.get("overs", []):
            max_over = max(max_over, o["over"])
            first = None
            dels = o["deliveries"]
            for j, dl in enumerate(dels):
                ex = dl.get("extras", {})
                is_legal = "wides" not in ex and "noballs" not in ex
                cum[(o["over"], j + 1)] = (legal, legal + is_legal)
                kinds = [w["kind"] for w in dl.get("wickets", [])]
                if j + 1 < len(dels) and any(w["kind"] in CAUGHT and w.get("player_out") == dl["batter"]
                                             for w in dl.get("wickets", [])):
                    catches += 1
                    crossed += dels[j + 1]["batter"] == dl["non_striker"]
                runs += dl["runs"]["total"]
                wkts += sum(k not in NOT_OUT for k in kinds)
                prot = any(k in PROTECTED for k in kinds)
                prot_wkts += sum(k in PROTECTED for k in kinds)
                if fh_pending:
                    fh_n += 1
                    fh_viol += prot
                    if by_over:
                        fh_by_over[(o["over"], prot)] += 1
                    fh_pending = not is_legal
                if "noballs" in ex:
                    nb[ex["noballs"]] += 1
                    fh_pending = True
                if "review" in dl:
                    rv = dl["review"]
                    reviews.append((o["over"], rv.get("by"), rv.get("decision"), rv.get("umpires_call"),
                                    kinds[0] if kinds else None, rv.get("by") == inn["team"]))
                for kind, lst in dl.get("replacements", {}).items():
                    repl.extend((kind, x.get("reason")) for x in lst)
                first = first or dl["bowler"]
                if is_legal:
                    legal += 1
                    bowler_balls[dl["bowler"]] += 1
                    bowler_overs[dl["bowler"]].add(o["over"])
                    if by_over:
                        legal_by_over[o["over"]] += 1
                        prot_by_over[o["over"]] += prot
            sets.append(first)
        run = best = 0
        for a, b in zip([None] + sets, sets):
            run = run + 1 if a == b else 1
            best = max(best, run)
        r.update(legal=legal, runs=runs, wkts=wkts, prot_wkts=prot_wkts, max_over=max_over, nb=dict(nb),
                 bowler_max_balls=max(bowler_balls.values(), default=0),
                 bowler_max_overs=max(map(len, bowler_overs.values()), default=0), fh_n=fh_n, fh_viol=fh_viol,
                 bowler_overs=sorted(map(len, bowler_overs.values()), reverse=True),
                 reviews=reviews, repl=repl, max_consecutive_overs=best, catches_mid_over=catches,
                 catches_crossed=crossed, legal_by_over=dict(legal_by_over), prot_by_over=dict(prot_by_over),
                 fh_by_over=[(o, p, c) for (o, p), c in fh_by_over.items()],
                 pp_legal=[(t, cum.get(_ball_pos(a), (None,))[0], cum.get(_ball_pos(b), (None, None))[1])
                           for t, a, b in r["pp_raw"]])
        rec["innings"].append(r)
    return rec


_ZIP = {}


def _scan_name(args):
    path, name = args
    z = _ZIP.get(path) or _ZIP.setdefault(path, zipfile.ZipFile(path))
    return scan_match(json.loads(z.read(name)), name[:-5])


def scan_zip(path, workers: int = 2, limit: int | None = None) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith(".json")][:limit]
    jobs = [(str(path), n) for n in names]
    if workers <= 1:
        return [_scan_name(j) for j in jobs]
    import multiprocessing as mp
    with mp.get_context("fork").Pool(workers) as pool:
        return pool.map(_scan_name, jobs, chunksize=64)


# ---------------------------------------------------------------- validation

def _annotate(summaries: list[dict], config_path: str | None = None) -> list[dict]:
    overrides = load_config(config_path).get("match_overrides", {})
    for s in summaries:
        s["comp"] = competition_for(s).as_dict()
        s["rules"] = rules_for_match(s, match_id=s["match_id"], config_path=config_path)
        s["date"] = str(s["dates"][0])
        s["year"] = int(s["date"][:4])
        s["result"] = (s["outcome"] or {}).get("result", "win")
        s["method"] = (s["outcome"] or {}).get("method")
        s["main_innings"] = [i for i in s["innings"] if not i["super_over"]]
        s["has_review"] = any(i["reviews"] for i in s["main_innings"])
        s["days_lost_at_start"] = overrides.get(s["match_id"], {}).get("days_lost_at_start", 0)
    keys = assign_series_keys(dict(competition_id=s["comp"]["competition_id"], event_id=s["comp"]["event_id"],
                                   event_name=s["comp"]["event_name"], season=s["season"], date=s["date"],
                                   teams=s["teams"] or ()) for s in summaries)
    for s, k in zip(summaries, keys):
        s["series_key"] = k
    return summaries


def _key(s: dict) -> str:
    return s["comp"]["competition_id"]


def _family(s: dict) -> str:
    c = s["comp"]
    return c["competition_id"] if c["team_type"] == "international" else f"club_{c['fmt'].lower()}_{c['gender'][0]}"


def check_drs(summaries: list[dict]) -> list[dict]:
    """(a) Share of matches with any recorded review vs the rules' drs_available.

    Club matches group by competition season; internationals by competition, event id,
    year and associate/full, so a series-level difference is not hidden by pooling. Reviews
    where the default is off are 'partial_selected' when they all fall in matches whose
    rules allow DRS in some series (``drs_scope`` selected or knockouts), a conflict when
    two or more fall in matches with ``drs_scope='none'``."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        intl = s["comp"]["team_type"] == "international"
        seg = ("assoc" if s["comp"]["assoc_match"] else "full") if intl else "club"
        period = str(s["year"]) if intl else s["season"]
        g = groups[(_key(s), s["comp"]["event_id"] if intl else _key(s), period, seg)]
        g["n"] += 1
        if s["reviews_missing"]:
            g["missing"] += 1
            continue
        obs = s["has_review"]
        exp = s["rules"]["drs_available"]
        g["exp_true"] += exp
        g["obs_true"] += obs and exp
        g["obs_false"] += obs and not exp
        g["obs_false_none"] += obs and not exp and s["rules"]["drs_scope"] == "none"
    rows = []
    for (cid, event_id, period, seg), g in sorted(groups.items()):
        n_false = g["n"] - g["missing"] - g["exp_true"]
        sh_t = g["obs_true"] / g["exp_true"] if g["exp_true"] else None
        sh_f = g["obs_false"] / n_false if n_false else None
        status = "ok"
        if g["exp_true"] >= 5 and sh_t < 0.4:
            status = "conflict_rules_on_data_off"
        elif n_false >= 5 and sh_f > 0.2:
            status = "partial_selected" if g["obs_false_none"] <= 1 else "conflict_rules_off_data_on"
        if (sh_t or 0) + (sh_f or 0) > 0 or g["exp_true"]:
            rows.append(dict(competition_id=cid, event_id=event_id, period=period, segment=seg, n=g["n"],
                             reviews_missing=g["missing"],
                             n_rules_on=g["exp_true"], share_obs_when_on=None if sh_t is None else round(sh_t, 3),
                             n_rules_off=n_false, share_obs_when_off=None if sh_f is None else round(sh_f, 3),
                             reviews_where_scope_none=g["obs_false_none"], status=status))
    return rows


def _team_innings_reviews(s: dict):
    """(innings, team, [(over, umpires_call), ...]) for each team's unsuccessful reviews."""
    for inn in s["main_innings"]:
        by = defaultdict(list)
        for over, team, decision, ucall, *_ in inn["reviews"]:
            if decision == "struck down":
                by[team].append((over, ucall is True))
        for team, fails in by.items():
            yield inn, team, fails


def check_review_limits(summaries: list[dict]) -> dict:
    """(b) Most unsuccessful reviews by one team in one innings vs reviews_per_innings.

    A failed review counts against the allowance unless it was umpire's call and the
    rules retain such reviews; while a Test top-up applies (men 2013-2017, women from
    2021) the allowance covers the first 80 overs and again the rest of the innings. A failed review in a match whose rules
    have no DRS at all (``reviews_per_innings`` null) is counted separately."""
    rows = {"pooled": defaultdict(Counter), "by_competition": defaultdict(Counter)}
    extra = defaultdict(lambda: dict(counts=Counter(), limits=set(), examples=[]))
    for s in summaries:
        r = s["rules"]
        lim, retain = r["reviews_per_innings"], r["umpires_call_retains_review"]
        for inn, team, fails in _team_innings_reviews(s):
            fail, nuc = len(fails), sum(not u for _, u in fails)
            counted_overs = [o for o, u in fails if not (retain and u)]
            counted, pre80 = len(counted_overs), sum(o < 80 for o in counted_overs)
            for part, key in (("pooled", (_family(s), s["year"])), ("by_competition", (_key(s), s["year"]))):
                g, x = rows[part][key], extra[(part, key)]
                g["n"] += 1
                g["max_fail"] = max(g["max_fail"], fail)
                g["max_nuc"] = max(g["max_nuc"], nuc)
                x["counts"][counted] += 1
                x["limits"].add(lim)
                if lim is None:
                    g["no_allowance"] += 1
                    if len(x["examples"]) < 5:
                        x["examples"].append(f"{s['match_id']}:{team}:{counted}:no_drs_in_rules")
                    continue
                bad = (pre80 > lim or counted > 2 * lim) if r["review_topup_after_80"] else counted > lim
                g["at_limit"] += counted == lim
                g["viol"] += bad
                if bad and len(x["examples"]) < 5:
                    x["examples"].append(f"{s['match_id']}:{team}:{counted}")
    out = {}
    for part, groups in rows.items():
        out[part] = []
        for key, g in sorted(groups.items()):
            x = extra[(part, key)]
            robust = max([k for k, c in x["counts"].items() if c >= 2] or [max(x["counts"])])
            lims = sorted(v for v in x["limits"] if v is not None)
            status = ("conflict" if g["viol"] > 1 or g["no_allowance"] > 1 else
                      "ok" if not lims or robust >= max(lims) or g["n"] < 30 else "limit_not_reached")
            out[part].append(dict(key=key[0], year=key[1], team_innings=g["n"], max_failed=g["max_fail"],
                                  max_failed_non_ucall=g["max_nuc"], robust_max_counted=robust,
                                  rules_reviews=lims or None, n_at_limit=g["at_limit"], n_violations=g["viol"],
                                  n_failed_without_drs_in_rules=g["no_allowance"], examples=x["examples"],
                                  status=status))
    return out


def _full_length(s: dict, inn: dict) -> bool:
    overs = s["rules"]["overs_per_innings"]
    tgt = (inn.get("target") or {}).get("overs")
    return overs is not None and inn["max_over"] + 1 == overs and (tgt is None or tgt == overs) and s["method"] is None


def check_powerplays(summaries: list[dict]) -> list[dict]:
    """(c) Recorded mandatory windows (full-length innings) and optional blocks vs powerplay_overs."""
    groups = defaultdict(lambda: dict(n=0, match=0, sig=Counter(), opt_in=0, opt_n=0, rule=Counter()))
    for s in summaries:
        pp = s["rules"]["pp_windows"]
        if not pp or s["comp"]["fmt"] == "TEST":
            continue
        want = [list(w) for w in pp["mandatory"]]
        for inn in s["main_innings"]:
            if not inn["powerplays"] or not _full_length(s, inn):
                continue
            g = groups[(_key(s), s["season"])]
            got = [[a, b] for t, a, b in inn["powerplays"] if t == "mandatory"]
            g["n"] += 1
            g["match"] += got == want
            g["sig"][json.dumps(got)] += 1
            g["rule"][json.dumps(want)] += 1
            for t, a, b in inn["powerplays"]:
                if t in ("batting", "fielding"):
                    g["opt_n"] += 1
                    blk = pp.get(t)
                    g["opt_in"] += bool(blk) and blk["window"][0] <= a and b <= blk["window"][1]
    rows = []
    for (cid, season), g in sorted(groups.items()):
        share = g["match"] / g["n"]
        in_window = g["opt_in"] / g["opt_n"] if g["opt_n"] else None
        rows.append(dict(competition_id=cid, season=season, full_innings=g["n"],
                         rules_mandatory=json.loads(g["rule"].most_common(1)[0][0]),
                         modal_recorded=json.loads(g["sig"].most_common(1)[0][0]), share_matching=round(share, 3),
                         optional_blocks=g["opt_n"], share_blocks_in_rules_window=in_window and round(in_window, 3),
                         status="ok" if share >= 0.8 and (in_window is None or in_window >= 0.8) else "conflict"))
    return rows


def check_overs_balls(summaries: list[dict]) -> list[dict]:
    """(d) Scheduled overs, balls per over, bowler quotas and consecutive sets per competition."""
    groups = defaultdict(lambda: dict(n=0, overs=Counter(), bpo=Counter(), over_mis=[], bpo_mis=0, quota_viol=[],
                                      max_bowler=0, max_bowler_overs=0, max_consec=0, inn=0))
    for s in summaries:
        r, g = s["rules"], groups[_key(s)]
        g["n"] += 1
        g["overs"][str(s["overs"])] += 1
        g["bpo"][str(s["balls_per_over"])] += 1
        if r["overs_per_innings"] is not None and s["overs"] not in (None, r["overs_per_innings"]):
            g["over_mis"].append(s["match_id"])
        g["bpo_mis"] += s["balls_per_over"] != r["balls_per_over"]
        for inn in s["main_innings"]:
            g["inn"] += 1
            g["max_bowler"] = max(g["max_bowler"], inn["bowler_max_balls"])
            g["max_bowler_overs"] = max(g["max_bowler_overs"], inn["bowler_max_overs"])
            g["max_consec"] = max(g["max_consec"], inn["max_consecutive_overs"])
            q = r["bowler_quota"]
            if q is not None and inn["bowler_max_overs"] > q:
                g["quota_viol"].append(s["match_id"])
    rows = []
    for cid, g in sorted(groups.items()):
        ok = g["bpo_mis"] == 0 and len(g["quota_viol"]) <= max(2, g["inn"] // 1000)
        rows.append(dict(competition_id=cid, matches=g["n"], info_overs=dict(g["overs"]), balls_per_over=dict(g["bpo"]),
                         overs_mismatches=len(g["over_mis"]), overs_mismatch_examples=g["over_mis"][:5],
                         bpo_mismatches=g["bpo_mis"], max_legal_balls_one_bowler=g["max_bowler"],
                         max_overs_one_bowler=g["max_bowler_overs"], quota_violations=len(g["quota_viol"]),
                         quota_violation_examples=g["quota_viol"][:5], max_consecutive_overs_one_bowler=g["max_consec"],
                         status="ok" if ok else "conflict"))
    return rows


def check_follow_on(summaries: list[dict]) -> list[dict]:
    """(e) Follow-ons (the side batting third batted second) and their first-innings leads.

    The threshold is Law 14.1 for the days remaining when play started: the scheduled
    days less any whole days lost at the start (``days_lost_at_start`` match overrides)."""
    groups = defaultdict(lambda: dict(n=0, fo=0, leads=[], below=[], opp=0, opp_fo=0, thr=Counter()))
    for s in summaries:
        inns = s["main_innings"]
        if s["comp"]["fmt"] != "TEST" or len(inns) < 2:
            continue
        g = groups[_key(s)]
        g["n"] += 1
        if any(i["forfeited"] for i in inns[:2]):
            continue
        lead = inns[0]["runs"] - inns[1]["runs"]
        fo = len(inns) >= 3 and inns[2]["team"] == inns[1]["team"]
        days = s["rules"]["scheduled_days"]
        thr = follow_on_threshold(s["rules"], days - s["days_lost_at_start"]) if days else None
        g["thr"][thr] += 1
        if thr is not None and lead >= thr and len(inns) >= 3:
            g["opp"] += 1
            g["opp_fo"] += fo
        if fo:
            g["fo"] += 1
            g["leads"].append(lead)
            if thr is not None and lead < thr:
                g["below"].append(dict(match_id=s["match_id"], date=s["date"], lead=lead, rule=thr,
                                       dates=len(s["dates"])))
            elif s["days_lost_at_start"]:
                g.setdefault("lost_day", []).append(dict(match_id=s["match_id"], lead=lead, rule=thr))
    rows = []
    for cid, g in sorted(groups.items()):
        L = sorted(g["leads"])
        rows.append(dict(competition_id=cid, matches=g["n"], follow_ons=g["fo"], min_lead=L[0] if L else None,
                         median_lead=L[len(L) // 2] if L else None,
                         rule_leads={str(k): v for k, v in sorted(g["thr"].items(), key=str)},
                         enforced_below_rule=g["below"], enforced_after_lost_day=g.get("lost_day", []),
                         opportunities=g["opp"],
                         enforcement_rate=round(g["opp_fo"] / g["opp"], 3) if g["opp"] else None,
                         status="ok" if not g["below"] else "conflict"))
    return rows


def check_replacements(summaries: list[dict]) -> list[dict]:
    """(f) Seasons with impact-player (and supersub / X-factor) replacements vs the rules."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        reasons = {reason for inn in s["innings"] for kind, reason in inn["repl"] if kind == "match"}
        g = groups[(_key(s), s["season"])]
        g["n"] += 1
        g["impact"] += "impact_player" in reasons
        g["supersub"] += "supersub" in reasons
        g["rule_impact"] += s["rules"]["impact_player"]
        g["rule_tactical"] += s["rules"]["tactical_sub"] == "supersub"
    rows = []
    for (cid, season), g in sorted(groups.items()):
        if not (g["impact"] or g["supersub"] or g["rule_impact"] or g["rule_tactical"]):
            continue
        rule_on = g["rule_impact"] > g["n"] / 2
        share = g["impact"] / g["n"]
        status = "ok" if (rule_on and share >= 0.5) or (not rule_on and g["impact"] == 0) else "conflict"
        if g["supersub"] and not g["rule_tactical"]:
            status = "conflict"
        rows.append(dict(competition_id=cid, season=season, matches=g["n"], impact_player_matches=g["impact"],
                         supersub_matches=g["supersub"], rules_impact_player=rule_on,
                         rules_supersub=g["rule_tactical"] > 0, status=status))
    return rows


def _poisson_cdf(k: int, mu: float) -> float:
    return sum(math.exp(-mu) * mu**i / math.factorial(i) for i in range(k + 1))


FREE_HIT_PRIOR, FREE_HIT_MIN_EXPECTED = 10.0, 20.0


def check_free_hit(summaries: list[dict], config_path: str | None = None) -> list[dict]:
    """(g) Bowled/caught/lbw/stumped dismissals on free-hit-eligible balls vs the base rate.

    ``ratio`` is observed over expected-without-free-hits at the cell's protected-dismissal
    rate per legal ball; ``ratio_by_over`` uses that rate over by over (no-balls cluster
    in high-wicket overs). 'none' conflicts when significantly below half the base rate,
    'front_foot' when significantly above 0.6 of it (or zero with 15+ expected), and
    'all_noballs' when more than one in 500 free-hit balls ends in a protected dismissal.
    For front_foot cells, ``p_estimate`` = 1 - ratio_by_over shrunk to the pooled
    front-foot ratio with a Gamma prior worth :data:`FREE_HIT_PRIOR` expected dismissals.
    Cells with at least :data:`FREE_HIT_MIN_EXPECTED` expected dismissals get their own
    value and conflict when the config's ``p_free_hit_given_nb`` is more than 0.05 away;
    smaller cells use the pooled default and conflict only when their count is outside
    the central 98% of a Poisson at the pooled ratio."""
    cfg = load_config(config_path).get("p_free_hit_given_nb", {})
    groups = defaultdict(lambda: dict(c=Counter(), leg=Counter(), prot=Counter(), fh=Counter(), viol=Counter()))
    for s in summaries:
        if s["comp"]["fmt"] == "TEST":
            continue
        g = groups[(_key(s), s["rules"]["free_hit"])]
        c = g["c"]
        c["y0"] = min(c["y0"] or 9999, s["year"])
        c["y1"] = max(c["y1"], s["year"])
        for inn in s["main_innings"]:
            c["fh"] += inn["fh_n"]
            c["viol"] += inn["fh_viol"]
            c["prot"] += inn["prot_wkts"]
            c["legal"] += inn["legal"]
            for o, n in inn["legal_by_over"].items():
                g["leg"][int(o)] += n
            for o, n in inn["prot_by_over"].items():
                g["prot"][int(o)] += n
            for o, p, n in inn["fh_by_over"]:
                g["fh"][int(o)] += n
                g["viol"][int(o)] += n * p
    rows = []
    for (cid, fh), g in sorted(groups.items()):
        c = g["c"]
        if not c["fh"]:
            continue
        base = c["prot"] / max(c["legal"], 1)
        mu = c["fh"] * base
        mu_adj = sum(n * g["prot"][o] / g["leg"][o] for o, n in g["fh"].items() if g["leg"][o])
        ratio = c["viol"] / mu if mu else None
        if fh == "all_noballs":
            status = "ok" if c["viol"] <= max(1, c["fh"] // 500) else "conflict"
        elif fh == "none":
            status = "conflict" if mu >= 3 and _poisson_cdf(c["viol"], 0.5 * mu) < 0.05 else "ok"
        else:
            status = "conflict" if (mu >= 3 and 1 - _poisson_cdf(c["viol"] - 1, 0.6 * mu) < 0.05) or (
                c["viol"] == 0 and mu * 0.2 >= 3) else "ok"
        rows.append(dict(competition_id=cid, rule=fh, years=[c["y0"], c["y1"]], free_hit_balls=c["fh"],
                         protected_dismissals=c["viol"], base_rate=round(base, 4), expected_if_no_free_hit=round(mu, 2),
                         ratio=None if ratio is None else round(ratio, 3), expected_by_over=round(mu_adj, 2),
                         ratio_by_over=round(c["viol"] / mu_adj, 3) if mu_adj else None, status=status))
    ff = [r for r in rows if r["rule"] == "front_foot"]
    pooled = sum(r["protected_dismissals"] for r in ff) / max(sum(r["expected_by_over"] for r in ff), 1e-9)
    for r in ff:
        shrunk = (r["protected_dismissals"] + FREE_HIT_PRIOR * pooled) / (r["expected_by_over"] + FREE_HIT_PRIOR)
        r["p_estimate"] = round(min(1.0, max(0.0, 1 - shrunk)), 2)
        r["p_config"] = cfg.get("by_competition", {}).get(r["competition_id"], cfg.get("default"))
        r["own_estimate"] = r["expected_by_over"] >= FREE_HIT_MIN_EXPECTED
        if r["own_estimate"]:
            bad = r["p_config"] is None or abs(r["p_config"] - r["p_estimate"]) > 0.05
        else:
            mu0, k = pooled * r["expected_by_over"], r["protected_dismissals"]
            bad = (r["competition_id"] in cfg.get("by_competition", {}) or _poisson_cdf(k, mu0) < 0.01
                   or (k > 0 and 1 - _poisson_cdf(k - 1, mu0) < 0.01))
        if bad:
            r["status"] = "conflict"
    if ff:
        rows.append(dict(competition_id="_pooled_front_foot", rule="front_foot", ratio_by_over=round(pooled, 3),
                         p_estimate=round(1 - pooled, 2), p_config=cfg.get("default"),
                         status="ok" if cfg.get("default") is not None and abs(cfg["default"] - (1 - pooled)) <= 0.05
                         else "conflict"))
    return rows


def check_caught_crossing(summaries: list[dict]) -> list[dict]:
    """Mid-over catches: share where the old non-striker faces the next ball vs caught_crossing_counts.

    With crossing counted, batters who crossed leave the new batter at the non-striker's
    end (about half of T20 catches, a few percent in first-class cricket). Without it the
    share must be about zero: 'false' conflicts above max(2, 2%) of catches, 'true' when
    100+ catches show no crossing at all."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        g = groups[(_key(s), s["rules"]["caught_crossing_counts"])]
        g["y0"] = min(g["y0"] or 9999, s["year"])
        g["y1"] = max(g["y1"], s["year"])
        for inn in s["main_innings"]:
            g["n"] += inn["catches_mid_over"]
            g["x"] += inn["catches_crossed"]
    rows = []
    for (cid, rule), g in sorted(groups.items()):
        if not g["n"]:
            continue
        bad = g["x"] > max(2, 0.02 * g["n"]) if not rule else g["n"] >= 100 and g["x"] == 0
        rows.append(dict(competition_id=cid, rule=rule, years=[g["y0"], g["y1"]], catches_mid_over=g["n"],
                         old_non_striker_on_strike=g["x"], share=round(g["x"] / g["n"], 3),
                         status="conflict" if bad else "ok"))
    return rows


def check_noball_runs(summaries: list[dict]) -> list[dict]:
    """No-ball penalty: share of no-balls carrying 1 vs 2 extras vs noball_penalty_runs.

    ``other`` counts no-balls with 3+ extras: Cricsheet folds byes and leg-byes run off a
    no-ball into ``extras.noballs``, so ingest must take the penalty from the rules and
    treat the rest as byes."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        g = groups[(_key(s), s["year"])]
        g["rule_" + str(s["rules"]["noball_penalty_runs"])] += 1
        for inn in s["main_innings"]:
            for v, c in inn["nb"].items():
                g[f"nb{int(v)}" if int(v) in (1, 2) else "other"] += c
    rows = []
    for (cid, year), g in sorted(groups.items()):
        n = g["nb1"] + g["nb2"]
        if not n:
            continue
        rule = 2 if g["rule_2"] > g["rule_1"] else 1
        share = g[f"nb{rule}"] / n
        rows.append(dict(competition_id=cid, year=year, one_run=g["nb1"], two_run=g["nb2"], other=g["other"], rule=rule,
                         share_matching=round(share, 3), status="ok" if share >= 0.9 or n < 10 else "conflict"))
    return rows


def check_super_overs(summaries: list[dict]) -> list[dict]:
    """Ties: decided by super over / bowl-out vs the rules' tie_break (resolved per match).

    Under so_repeat a match whose last super over was also tied is a mismatch; under
    so_boundary_count a tied super over is settled by the boundary count (eliminator)."""
    groups = defaultdict(lambda: dict(ties=0, so=0, bowl_out=0, dl_ties=0, so_tied=0, examples=[]))
    for s in summaries:
        if s["result"] != "tie":
            continue
        rule = s["rules"]["tie_break"]
        g = groups[(_key(s), rule)]
        sos = [i["runs"] for i in s["innings"] if i["super_over"]]
        so = bool(sos)
        last_tied = len(sos) >= 2 and sos[-1] == sos[-2]
        g["ties"] += 1
        g["so"] += so
        g["so_tied"] += any(sos[k] == sos[k + 1] for k in range(0, len(sos) - 1, 2))
        g["bowl_out"] += "bowl_out" in (s["outcome"] or {})
        g["dl_ties"] += s["method"] is not None
        ok = (rule == "none" and not so) or (
            rule in ("so_boundary_count", "so_repeat") and (so or s["method"] is not None)) or (
            rule == "bowl_out" and "bowl_out" in (s["outcome"] or {}))
        ok = ok and not (rule == "so_repeat" and last_tied)
        if not ok and len(g["examples"]) < 5:
            g["examples"].append(f"{s['match_id']}:{s['date']}")
        g["bad"] = g.get("bad", 0) + (not ok)
    return [dict(competition_id=cid, rule=rule, ties=g["ties"], super_over_ties=g["so"],
                 tied_super_overs=g["so_tied"], bowl_outs=g["bowl_out"],
                 dl_ties=g["dl_ties"], mismatches=g.get("bad", 0), examples=g["examples"],
                 status="ok" if g.get("bad", 0) <= max(1, g["ties"] // 4) else "conflict")
            for (cid, rule), g in sorted(groups.items())]


def check_min_overs(summaries: list[dict]) -> list[dict]:
    """Shortest rain-rule chase (D/L, DLS or VJD) that produced a result vs min_overs_for_result."""
    groups = defaultdict(lambda: dict(n=0, min=None, rule=set(), ex=None))
    for s in summaries:
        if s["method"] not in RAIN_METHODS or s["result"] != "win" or len(s["main_innings"]) < 2:
            continue
        t = (s["main_innings"][1].get("target") or {}).get("overs")
        if t is None:
            continue
        g = groups[_key(s)]
        g["n"] += 1
        g["rule"].add(s["rules"]["min_overs_for_result"])
        if g["min"] is None or t < g["min"]:
            g["min"], g["ex"] = t, s["match_id"]
    rows = []
    for cid, g in sorted(groups.items()):
        rule = min(x for x in g["rule"] if x is not None) if any(x is not None for x in g["rule"]) else None
        rows.append(dict(competition_id=cid, dl_results=g["n"], min_target_overs=g["min"], example=g["ex"],
                         rules_min_overs=rule, status="ok" if rule is None or g["min"] >= rule else "conflict"))
    return rows


def check_test_days(summaries: list[dict]) -> list[dict]:
    """Drawn multi-day matches: dates used vs test_days and overs per scheduled day vs test_overs_per_day."""
    groups = defaultdict(lambda: dict(n=0, dates=Counter(), opd=[], rule_days=Counter(), rule_opd=Counter(), over=[]))
    for s in summaries:
        if s["comp"]["fmt"] != "TEST" or s["result"] != "draw":
            continue
        r = s["rules"]
        g = groups[_key(s)]
        n_days = len(s["dates"])
        g["n"] += 1
        g["dates"][n_days] += 1
        g["rule_days"][r["scheduled_days"]] += 1
        g["rule_opd"][r["test_overs_per_day"]] += 1
        sched = r["scheduled_days"] or n_days
        opd = sum(i["legal"] for i in s["main_innings"]) / 6 / sched
        g["opd"].append(opd)
        if r["test_overs_per_day"] and opd > r["test_overs_per_day"] + 4:
            g["over"].append(f"{s['match_id']}:{opd:.1f}")
    rows = []
    for cid, g in sorted(groups.items()):
        o = sorted(g["opd"])
        days = g["rule_days"].most_common(1)[0][0]
        share = g["dates"][days] / g["n"]
        rows.append(dict(competition_id=cid, draws=g["n"], dates_used=dict(g["dates"]), rules_days=days,
                         share_draws_using_rule_days=round(share, 3),
                         rules_overs_per_day=g["rule_opd"].most_common(1)[0][0],
                         overs_per_day_p90=round(o[int(0.9 * (len(o) - 1))], 1), overs_per_day_max=round(o[-1], 1),
                         draws_above_rule_plus_4=g["over"][:5],
                         status="ok" if share >= 0.8 and len(g["over"]) <= max(1, g["n"] // 50) else "conflict"))
    return rows


def _reduced_innings(s: dict):
    """(innings number, N, innings, timing) for limited-overs innings cut to a whole N overs.

    N is the second innings' revised target overs; the first innings counts when it ran
    exactly N overs. ``timing`` comes from the recorded first powerplay: ``pre`` when it
    ends where the reduced table says (the cut came before it ended), ``mid`` when it
    has its full length (the cut came later), ``both`` when the two coincide, ``during``
    when it ends strictly between the two (the cut came during the powerplay, or a
    later second cut), ``other`` when it fits no cut timing, ``unknown`` when none is
    recorded or the record cannot be scored (the innings ended inside the powerplay, or
    the recorded end is past the full-length powerplay)."""
    r, inns = s["rules"], s["main_innings"]
    sched, bpo = r["overs_per_innings"], r["balls_per_over"]
    if not sched or s["comp"]["fmt"] == "TEST" or len(inns) < 2 or not r["pp_windows"]:
        return
    t = (inns[1].get("target") or {}).get("overs")
    if t is None or t >= sched or t != int(t) or t < 1:
        return
    n = int(t)
    table = (r["pp_windows_reduced"] or {}).get(str(n))
    full = r["pp_windows"]["mandatory"][0][1] * bpo
    for k, inn in enumerate(inns[:2]):
        if k == 0 and inn["max_over"] + 1 != n:
            continue
        rec = [b for t_, a, b in inn["pp_legal"] if t_ == "mandatory"]
        want = table["mandatory"][0][1] if table else None
        if not rec or rec[0] is None or rec[0] >= inn["legal"] or rec[0] > full:
            timing = "unknown"
        elif rec[0] == want:
            timing = "both" if want == full else "pre"
        elif rec[0] == full:
            timing = "mid"
        else:
            timing = "during" if want is not None and min(want, full) < rec[0] < max(want, full) else "other"
        yield k + 1, n, inn, timing, rec, table


def check_reduced_powerplays(summaries: list[dict]) -> list[dict]:
    """Reduced innings: recorded first powerplay (in legal balls) vs pp_windows_reduced.

    Innings whose powerplay kept its full length (cut after it) or ended between the
    table and full length (cut during it) are consistent with the table applied with
    the N known at the time, and are reported but not scored. A season conflicts when
    fewer than 75% of the scored innings match (5+ innings), a rule's pooled row
    (``competition_id`` '_all') when fewer than 85% do. For the men's three-powerplay
    table the end of P2 is compared too."""
    groups = defaultdict(lambda: dict(c=Counter(), rule=Counter(), p2=Counter(), ex=[]))
    for s in summaries:
        for k, n, inn, timing, rec, table in _reduced_innings(s):
            rule = s["rules"]["pp_reduced_rule"]
            for key in ((_key(s), s["season"]), ("_all", rule)):
                g = groups[key]
                g["c"][timing] += 1
                g["rule"][rule] += 1
                if timing in ("pre", "both") and table and len(table["mandatory"]) > 1:
                    g["p2"]["n"] += 1
                    g["p2"]["match"] += len(rec) > 1 and rec[1] == table["mandatory"][1][1]
                if timing == "other" and len(g["ex"]) < 5:
                    tab = table and table["mandatory"][0][1]
                    g["ex"].append(f"{s['match_id']}:{k}:N={n}:recorded={rec[0]}:table={tab}")
    rows = []
    for (cid, season), g in sorted(groups.items(), key=lambda kv: (kv[0][0] == "_all", kv[0])):
        c = g["c"]
        scored = c["pre"] + c["both"] + c["other"]
        share = (c["pre"] + c["both"]) / scored if scored else None
        floor = 0.85 if cid == "_all" else 0.75
        rows.append(dict(competition_id=cid, season=None if cid == "_all" else season,
                         rule=g["rule"].most_common(1)[0][0], innings=sum(c.values()),
                         matching=c["pre"] + c["both"], cut_after_powerplay=c["mid"], cut_during_powerplay=c["during"],
                         other=c["other"], no_powerplay_recorded=c["unknown"],
                         share_matching=None if share is None else round(share, 3),
                         p2_end_matching=f"{g['p2']['match']}/{g['p2']['n']}" if g["p2"]["n"] else None,
                         examples=g["ex"], status="ok" if scored < 5 or share >= floor else "conflict"))
    return rows


def check_reduced_quotas(summaries: list[dict]) -> list[dict]:
    """Reduced innings: overs per bowler vs bowler_quota_reduced, by when the cut came.

    An innings complies when no bowler exceeds the quota plus one and at most the
    allowed number of bowlers bowl the extra over (the Hundred: legal balls). Innings
    cut before their powerplay ended (``pre``) must comply; those cut later (``mid``)
    may not, since a bowler keeps overs bowled before the cut."""
    groups = defaultdict(lambda: dict(c=Counter(), ex=defaultdict(list)))
    for s in summaries:
        for k, n, inn, timing, rec, table in _reduced_innings(s):
            q = (s["rules"]["bowler_quota_reduced"] or {}).get(str(n))
            if not q:
                continue
            quota, extra, balls = q
            if s["comp"]["fmt"] == "HUNDRED":
                ok = inn["bowler_max_balls"] <= balls
            else:
                bo = inn["bowler_overs"]
                ok = all(x <= quota + (1 if extra else 0) for x in bo) and sum(x > quota for x in bo) <= extra
            t = "pre" if timing in ("pre", "both") else timing
            g = groups[(s["comp"]["fmt"], _key(s))]
            g["c"][t] += 1
            g["c"][t + "_ok"] += ok
            if not ok and len(g["ex"][t]) < 3:
                g["ex"][t].append(f"{s['match_id']}:{k}:N={n}:{inn['bowler_overs']}")
    rows = []
    for (fmt, cid), g in sorted(groups.items()):
        c = g["c"]
        row = dict(fmt=fmt, competition_id=cid)
        for t in ("pre", "during", "mid", "other", "unknown"):
            row[t] = f"{c[t + '_ok']}/{c[t]}"
        row["examples"] = dict(g["ex"])
        row["status"] = "conflict" if c["pre"] >= 10 and c["pre_ok"] / c["pre"] < 0.9 else "ok"
        rows.append(row)
    tot = Counter()
    for (fmt, _), g in groups.items():
        for t in ("pre", "during", "mid", "other", "unknown"):
            tot[(fmt, t)] += g["c"][t]
            tot[(fmt, t + "_ok")] += g["c"][t + "_ok"]
    for fmt in sorted({f for f, _ in groups}):
        row = dict(fmt=fmt, competition_id="_all")
        for t in ("pre", "during", "mid", "other", "unknown"):
            row[t] = f"{tot[(fmt, t + '_ok')]}/{tot[(fmt, t)]}"
        row["status"] = "conflict" if tot[(fmt, "pre")] >= 10 and tot[(fmt, "pre_ok")] / tot[(fmt, "pre")] < 0.95 else "ok"
        rows.append(row)
    return rows


def check_drs_series(summaries: list[dict]) -> list[dict]:
    """Per-match DRS from the plan formula (:func:`match_drs_available`) by competition.

    Conflicts: a review recorded in a match whose rules forbid DRS. Also listed: series
    of 3+ matches with reviews recorded where the competition default is DRS in every
    match (``drs_scope`` all) but no match has a review (series played without DRS)."""
    import pandas as pd

    df = pd.DataFrame(dict(series_key=[s["series_key"] for s in summaries], competition_id=[_key(s) for s in summaries],
                           drs_allowed=[s["rules"]["drs_allowed"] for s in summaries],
                           default_on=[s["rules"]["drs_available"] and s["rules"]["drs_scope"] == "all" for s in summaries],
                           has_review=[s["has_review"] for s in summaries],
                           reviews_missing=[s["reviews_missing"] for s in summaries],
                           match_id=[s["match_id"] for s in summaries]))
    df = df.join(match_drs_available(df))
    for s, (v, src) in zip(summaries, zip(df.drs_available, df.drs_source)):
        s["drs_available_match"], s["drs_source"] = v, src
    ok_rows = ~df.reviews_missing
    ser = df[ok_rows].groupby(["competition_id", "series_key"]).agg(n=("match_id", "size"), rev=("has_review", "sum"),
                                                                  on=("default_on", "all"))
    dark = ser[(ser.n >= 3) & (ser.rev == 0) & ser.on].reset_index()
    rows = []
    for cid, d in df.groupby("competition_id"):
        bad = d[d.has_review & ~d.drs_allowed & ~d.reviews_missing]
        dk = dark[dark.competition_id == cid]
        src = d.drs_source.value_counts().to_dict()
        if not (d.has_review.any() or d.drs_allowed.any()):
            continue
        rows.append(dict(competition_id=cid, matches=len(d), series=int(d.series_key.nunique()),
                         drs_true=int((d.drs_available == True).sum()), drs_false=int((d.drs_available == False).sum()),  # noqa: E712
                         drs_null=int(d.drs_available.isna().sum()), source=src,
                         series_true_without_own_review=int(((d.drs_source == "series") & (d.drs_available == True)).sum()),  # noqa: E712
                         reviews_where_rules_forbid=len(bad), examples=bad.match_id.head(5).tolist(),
                         default_on_series_without_reviews=len(dk), matches_in_those_series=int(dk.n.sum()),
                         dark_series_examples=dk.series_key.head(3).tolist(),
                         status="conflict" if len(bad) else "ok"))
    return rows


def check_ucall_zone(summaries: list[dict]) -> list[dict]:
    """Umpire's-call share of failed reviews by family and ucall_zone_era (anchor only, status 'info').

    Batting reviews count when the on-field out stood on an lbw; fielding reviews when
    the not-out stood. Only matches dated on or after the first recorded flag."""
    first = {"TEST": "2017-08-25", "ODI": "2017-10-16", "T20": "2017-12-24", "HUNDRED": "2021-07-30"}
    groups = defaultdict(Counter)
    for s in summaries:
        fam = s["comp"]["fmt"]
        if s["date"] < first[fam]:
            continue
        g = groups[(fam, s["rules"]["ucall_zone_era"])]
        for inn in s["main_innings"]:
            for over, by, dec, uc, kind, by_bat in inn["reviews"]:
                if dec != "struck down":
                    continue
                side = "bat" if by_bat and kind == "lbw" else "field" if not by_bat and kind is None else None
                if side:
                    g[side] += 1
                    g[side + "_uc"] += uc is True
    return [dict(fam=fam, ucall_zone_era=era, failed_bat_lbw=g["bat"],
                 bat_ucall_share=round(g["bat_uc"] / g["bat"], 3) if g["bat"] else None, failed_field=g["field"],
                 field_ucall_share=round(g["field_uc"] / g["field"], 3) if g["field"] else None, status="info")
            for (fam, era), g in sorted(groups.items())]


def competition_summary(summaries: list[dict]) -> tuple[dict, list[dict]]:
    """Counts by competition and tier, generic (fallback) mappings, and one row per distinct event."""
    by_id, tiers, generic, events = Counter(), Counter(), Counter(), {}
    for s in summaries:
        c = s["comp"]
        by_id[c["competition_id"]] += 1
        tiers[c["tier"]] += 1
        if c["generic"]:
            generic[c["event_id"]] += 1
        key = (c["event_name"] or "(none)", s["match_type"], s["gender"], s["team_type"], c["competition_id"],
               c["event_id"], c["tier"], c["generic"])
        e = events.setdefault(key, [0, s["date"], s["date"]])
        e[0], e[1], e[2] = e[0] + 1, min(e[1], s["date"]), max(e[2], s["date"])
    rows = [dict(zip(("event_name", "match_type", "gender", "team_type", "competition_id", "event_id", "tier",
                      "generic"), k), n_matches=n, first=a, last=b) for k, (n, a, b) in events.items()]
    rows.sort(key=lambda r: (-r["n_matches"], r["event_name"]))
    return dict(matches=len(summaries), distinct_event_rows=len(rows), distinct_event_names=len({k[0] for k in events}),
                n_competitions=len(by_id), by_competition=dict(by_id.most_common()), by_tier=dict(tiers),
                generic=dict(generic), generic_matches=sum(generic.values())), rows


def explain_anomalies(sections: dict, anomalies: list[dict]) -> None:
    """Mark non-ok rows covered by a documented ``data_anomalies`` entry as 'explained'."""
    for a in anomalies:
        rows = sections[a["section"]]
        flat = rows["pooled"] + rows["by_competition"] if isinstance(rows, dict) else rows
        for row in flat:
            if all(row.get(k) == v for k, v in a["where"].items()):
                row["explanation"] = a["explanation"]
                if row["status"] != "ok":
                    row["status"] = "explained"


def validate(summaries: list[dict], config_path: str | None = None) -> dict:
    """Run every check; ``summaries`` come from :func:`scan_zip` (or :func:`scan_match`)."""
    _annotate(summaries, config_path)
    comps, events = competition_summary(summaries)
    sections = dict(
        drs_observed=check_drs(summaries), review_limits=check_review_limits(summaries),
        powerplays=check_powerplays(summaries), overs_balls=check_overs_balls(summaries),
        follow_on=check_follow_on(summaries), replacements=check_replacements(summaries),
        free_hit=check_free_hit(summaries, config_path), caught_crossing=check_caught_crossing(summaries),
        noball_runs=check_noball_runs(summaries),
        super_overs=check_super_overs(summaries), min_overs_for_result=check_min_overs(summaries),
        test_days=check_test_days(summaries), reduced_powerplays=check_reduced_powerplays(summaries),
        reduced_quotas=check_reduced_quotas(summaries), drs_series=check_drs_series(summaries),
        ucall_zone=check_ucall_zone(summaries))
    explain_anomalies(sections, load_config(config_path).get("data_anomalies", []))
    status = {}
    for name, rows in sections.items():
        flat = rows["pooled"] + rows["by_competition"] if isinstance(rows, dict) else rows
        status[name] = dict(Counter(r["status"] for r in flat))
    ff = [r for r in sections["free_hit"] if r["rule"] == "front_foot" and "p_estimate" in r]
    estimate = dict(default=next((r["p_estimate"] for r in ff if r["competition_id"] == "_pooled_front_foot"), None),
                    by_competition={r["competition_id"]: r["p_estimate"] for r in ff if r.get("own_estimate")})
    src = Counter(s["drs_source"] for s in summaries)
    report = dict(generated_by="beating.cricket.rules.validate", config_version=load_config(config_path)["version"],
                  competitions=comps, status_counts=status, p_free_hit_given_nb_estimate=estimate,
                  drs_available_by_source=dict(src), **sections)
    report["_events"] = events
    return report


def main(argv=None) -> None:
    import argparse
    import csv

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", default=str(ROOT / "data/raw/cricsheet/all_json.zip"))
    ap.add_argument("--report", default=str(ROOT / "reports/cricket-rules-validation.json"))
    ap.add_argument("--events-csv", default=str(ROOT / "data/derived/cricket/competition-events.csv"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    report = validate(scan_zip(a.zip, a.workers, a.limit))
    events = report.pop("_events")
    Path(a.events_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(a.events_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(events[0]))
        w.writeheader()
        w.writerows(events)
    Path(a.report).write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps(report["status_counts"], indent=1))
    print("matches", report["competitions"]["matches"], "generic", report["competitions"]["generic"])


if __name__ == "__main__":
    main()
