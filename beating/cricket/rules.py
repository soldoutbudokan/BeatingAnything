"""Playing-conditions timeline: what the rules were for a given match.

Method. ``config/cricket-rules.json`` holds an ordered list of layers. A layer
matches on format, gender, team type, competition, tier, event, official status,
associate flag, the teams involved and whether the match is a knockout, and on a
half-open date range; matching layers are applied in file order, later ones
overriding earlier ones field by field (plan section 5). :func:`rules_for` then
resolves per-match facts: scheduled days (four-day Tests change overs per day and
the follow-on lead), knockout-only DRS and super overs, and a ``drs_scope`` of
``none`` clearing the review count. Every returned dict carries all section-5
fields plus the ids of the layers that set them.

Validation. :func:`validate` streams the Cricsheet zip once and checks every
data-testable field against what the timeline says for each match: DRS
observed share, the most unsuccessful non-umpire's-call reviews by one team in an
innings, recorded powerplay windows, scheduled overs and balls per over, bowler
quotas, follow-on enforcements and leads, impact-player replacements, protected
dismissals on free-hit balls, who faces after a mid-over catch, one- versus two-run
no-balls, super overs in ties, minimum overs in D/L results and Test days and overs
per day.

Limits. Where Cricsheet cannot see a rule (two new balls, stop clock, fielders
outside the circle beyond powerplays) the value is from memory and marked so.
Whether a match had DRS is series-specific; ``drs_available`` is the competition
default and ``drs_scope='selected'`` marks partial coverage, so models fitted on
history should use each match's observed reviews. Umpire's-call flags are only
recorded from late 2017, so earlier counts treat every failed review as lost.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import zipfile

from beating.cricket.competitions import competition_for, competition_meta

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "cricket-rules.json"
FIELDS = (
    "overs_per_innings", "balls_per_over", "balls_per_innings", "bowler_quota_overs", "bowler_quota_balls",
    "powerplay_overs", "fielders_outside", "free_hit", "noball_extra_runs", "drs_available", "drs_scope",
    "reviews_per_innings", "umpires_call_retains_review", "review_topup_after_80", "test_overs_per_day",
    "test_days", "follow_on_lead", "new_ball_after_overs", "balls_in_use", "impact_player", "tactical_sub",
    "super_over", "min_overs_for_result", "max_consecutive_balls_per_end", "slow_over_rate_fielding_penalty",
    "stop_clock", "concussion_substitutes", "caught_crossing_counts",
)
WHEN_KEYS = {"fmt", "gender", "team_type", "competition_id", "tier", "event_id", "official", "assoc_match",
             "teams_any", "teams_all", "knockout", "stage_regex"}
KNOCKOUT_RE = re.compile(r"final|semi|quarter|qualifier \d|qualifier$|eliminator|play-?off|knock-?out|challenger",
                         re.IGNORECASE)
PROTECTED = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
CAUGHT = {"caught", "caught and bowled"}
NOT_OUT = {"retired hurt", "retired not out"}


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> dict:
    cfg = json.loads(Path(path or CONFIG_PATH).read_text())
    for layer in cfg["layers"]:
        bad = set(layer.get("when", {})) - WHEN_KEYS
        unknown = set(layer["set"]) - set(FIELDS)
        if bad or unknown:
            raise ValueError(f"layer {layer['id']}: bad when keys {bad} or fields {unknown}")
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
    so = out["super_over"]
    if so == "knockout_only":
        so = ("repeat" if date >= "2019-10-14" else "single") if knockout else "none"
    out["super_over_this_match"] = so
    mo = out["min_overs_for_result"]
    out["min_balls_for_result"] = None if mo is None else mo * out["balls_per_over"]
    return tuple(sorted(out.items())), tuple(sorted(source.items()))


def rules_for(competition_id: str, fmt: str, gender: str, date, *, event_id: str | None = None,
              teams=None, official: bool = True, assoc_match: bool = False, knockout: bool | None = None,
              stage: str | None = None, scheduled_days: int | None = None, match_id=None,
              config_path: str | None = None) -> dict:
    """Every section-5 field for one match; ``_layers`` gives the layer that set each field.

    ``knockout`` defaults to :func:`is_knockout` of ``stage``; ``match_id`` picks up
    ``match_overrides`` (scheduled days) from the config. ``drs_allowed`` (plan section 5)
    is true when the rules permit DRS in this match, including ``drs_scope='selected'``
    series; ``drs_available`` is only the competition default."""
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


# ---------------------------------------------------------------- data scan

def _over_no(x: float) -> int:
    return int(math.floor(x)) + 1


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
    for inn in d["innings"]:
        pps = [(p.get("type"), _over_no(p["from"]), _over_no(p["to"])) for p in inn.get("powerplays", [])]
        r = dict(team=inn["team"], super_over=bool(inn.get("super_over")), declared=bool(inn.get("declared")),
                 forfeited=bool(inn.get("forfeited")), target=inn.get("target"), powerplays=pps)
        legal = runs = wkts = prot_wkts = 0
        max_over, nb, bowler_balls, bowler_overs, reviews, repl = -1, Counter(), Counter(), defaultdict(set), [], []
        fh_pending, fh_n, fh_viol, sets, catches, crossed = False, 0, 0, [], 0, 0
        for o in inn.get("overs", []):
            max_over = max(max_over, o["over"])
            first = None
            dels = o["deliveries"]
            for j, dl in enumerate(dels):
                ex = dl.get("extras", {})
                is_legal = "wides" not in ex and "noballs" not in ex
                kinds = [w["kind"] for w in dl.get("wickets", [])]
                if j + 1 < len(dels) and any(w["kind"] in CAUGHT and w.get("player_out") == dl["batter"]
                                             for w in dl.get("wickets", [])):
                    catches += 1
                    crossed += dels[j + 1]["batter"] == dl["non_striker"]
                runs += dl["runs"]["total"]
                wkts += sum(k not in NOT_OUT for k in kinds)
                prot_wkts += sum(k in PROTECTED for k in kinds)
                if fh_pending:
                    fh_n += 1
                    fh_viol += any(k in PROTECTED for k in kinds)
                    fh_pending = not is_legal
                if "noballs" in ex:
                    nb[ex["noballs"]] += 1
                    fh_pending = True
                if "review" in dl:
                    rv = dl["review"]
                    reviews.append((o["over"], rv.get("by"), rv.get("decision"), rv.get("umpires_call")))
                for kind, lst in dl.get("replacements", {}).items():
                    repl.extend((kind, x.get("reason")) for x in lst)
                first = first or dl["bowler"]
                if is_legal:
                    legal += 1
                    bowler_balls[dl["bowler"]] += 1
                    bowler_overs[dl["bowler"]].add(o["over"])
            sets.append(first)
        run = best = 0
        for a, b in zip([None] + sets, sets):
            run = run + 1 if a == b else 1
            best = max(best, run)
        r.update(legal=legal, runs=runs, wkts=wkts, prot_wkts=prot_wkts, max_over=max_over, nb=dict(nb),
                 bowler_max_balls=max(bowler_balls.values(), default=0),
                 bowler_max_overs=max(map(len, bowler_overs.values()), default=0), fh_n=fh_n, fh_viol=fh_viol,
                 reviews=reviews, repl=repl, max_consecutive_overs=best, catches_mid_over=catches,
                 catches_crossed=crossed)
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
    for s in summaries:
        s["comp"] = competition_for(s).as_dict()
        s["rules"] = rules_for_match(s, match_id=s["match_id"], config_path=config_path)
        s["date"] = str(s["dates"][0])
        s["year"] = int(s["date"][:4])
        s["result"] = (s["outcome"] or {}).get("result", "win")
        s["method"] = (s["outcome"] or {}).get("method")
        s["main_innings"] = [i for i in s["innings"] if not i["super_over"]]
    return summaries


def _key(s: dict) -> str:
    return s["comp"]["competition_id"]


def _family(s: dict) -> str:
    c = s["comp"]
    return c["competition_id"] if c["team_type"] == "international" else f"club_{c['fmt'].lower()}_{c['gender'][0]}"


def check_drs(summaries: list[dict]) -> list[dict]:
    """(a) Share of matches with any recorded review vs the rules' drs_available, per competition season."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        seg = ("assoc" if s["comp"]["assoc_match"] else "full") if s["comp"]["team_type"] == "international" else "club"
        period = str(s["year"]) if s["comp"]["team_type"] == "international" else s["season"]
        g = groups[(_key(s), period, seg)]
        g["n"] += 1
        if s["reviews_missing"]:
            g["missing"] += 1
            continue
        obs = any(i["reviews"] for i in s["main_innings"])
        exp = s["rules"]["drs_available"]
        g["exp_true"] += exp
        g["obs_true"] += obs and exp
        g["obs_false"] += obs and not exp
        g["selected"] += s["rules"]["drs_scope"] in ("selected", "knockouts") and not exp
    rows = []
    for (cid, period, seg), g in sorted(groups.items()):
        n_false = g["n"] - g["missing"] - g["exp_true"]
        sh_t = g["obs_true"] / g["exp_true"] if g["exp_true"] else None
        sh_f = g["obs_false"] / n_false if n_false else None
        status = "ok"
        if g["exp_true"] >= 5 and sh_t < 0.4:
            status = "conflict_rules_on_data_off"
        elif n_false >= 5 and sh_f > 0.2:
            status = "partial_selected" if g["selected"] == n_false else "conflict_rules_off_data_on"
        if (sh_t or 0) + (sh_f or 0) > 0 or g["exp_true"]:
            rows.append(dict(competition_id=cid, period=period, segment=seg, n=g["n"], reviews_missing=g["missing"],
                             n_rules_on=g["exp_true"], share_obs_when_on=None if sh_t is None else round(sh_t, 3),
                             n_rules_off=n_false, share_obs_when_off=None if sh_f is None else round(sh_f, 3),
                             status=status))
    return rows


def _team_innings_reviews(s: dict):
    for inn in s["main_innings"]:
        by = defaultdict(lambda: [0, 0, 0])
        for over, team, decision, ucall in inn["reviews"]:
            if decision != "struck down":
                continue
            c = by[team]
            c[0] += 1
            c[1] += ucall is not True
            c[2] += over < 80
        for team, (fail, fail_nuc, fail_pre80) in by.items():
            yield inn, team, fail, fail_nuc, fail_pre80


def check_review_limits(summaries: list[dict]) -> dict:
    """(b) Most unsuccessful reviews by one team in one innings vs reviews_per_innings.

    A failed review counts against the allowance unless it was umpire's call and the
    rules retain such reviews; during the 2013-2017 Test top-up the allowance applies
    to the first 80 overs and again after them. A failed review in a match whose rules
    have no DRS at all (``reviews_per_innings`` null) is counted separately."""
    rows = {"pooled": defaultdict(Counter), "by_competition": defaultdict(Counter)}
    extra = defaultdict(lambda: dict(counts=Counter(), limits=set(), examples=[]))
    for s in summaries:
        r = s["rules"]
        lim, retain = r["reviews_per_innings"], r["umpires_call_retains_review"]
        for inn, team, fail, nuc, pre80 in _team_innings_reviews(s):
            counted = nuc if retain else fail
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
        pp = s["rules"]["powerplay_overs"]
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
            q = r["bowler_quota_overs"]
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
    """(e) Follow-ons (the side batting third batted second) and their first-innings leads."""
    groups = defaultdict(lambda: dict(n=0, fo=0, leads=[], below=[], opp=0, opp_fo=0))
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
        thr = s["rules"]["follow_on_lead"]
        if thr is not None and lead >= thr and len(inns) >= 3:
            g["opp"] += 1
            g["opp_fo"] += fo
        if fo:
            g["fo"] += 1
            g["leads"].append(lead)
            if thr is not None and lead < thr:
                g["below"].append(dict(match_id=s["match_id"], date=s["date"], lead=lead, rule=thr,
                                       dates=len(s["dates"])))
    rows = []
    for cid, g in sorted(groups.items()):
        L = sorted(g["leads"])
        rows.append(dict(competition_id=cid, matches=g["n"], follow_ons=g["fo"], min_lead=L[0] if L else None,
                         median_lead=L[len(L) // 2] if L else None, enforced_below_rule=g["below"],
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
        g["rule_tactical"] += s["rules"]["tactical_sub"] in ("supersub", "x_factor")
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
                         rules_supersub_or_x_factor=g["rule_tactical"] > 0, status=status))
    return rows


def _poisson_cdf(k: int, mu: float) -> float:
    return sum(math.exp(-mu) * mu**i / math.factorial(i) for i in range(k + 1))


def check_free_hit(summaries: list[dict]) -> list[dict]:
    """(g) Bowled/caught/lbw/stumped dismissals on free-hit-eligible balls vs the base rate.

    ``ratio`` is observed over expected-without-free-hits (the innings' protected-dismissal
    rate per legal ball). 'none' conflicts when significantly below half the base rate,
    'front_foot' when significantly above 0.6 of it (or zero with 15+ expected), and
    'all_noballs' when more than one in 500 free-hit balls ends in a protected dismissal."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        if s["comp"]["fmt"] == "TEST":
            continue
        g = groups[(_key(s), s["rules"]["free_hit"])]
        g["y0"] = min(g["y0"] or 9999, s["year"])
        g["y1"] = max(g["y1"], s["year"])
        for inn in s["main_innings"]:
            g["fh"] += inn["fh_n"]
            g["viol"] += inn["fh_viol"]
            g["prot"] += inn["prot_wkts"]
            g["legal"] += inn["legal"]
    rows = []
    for (cid, fh), g in sorted(groups.items()):
        if not g["fh"]:
            continue
        base = g["prot"] / max(g["legal"], 1)
        mu = g["fh"] * base
        ratio = g["viol"] / mu if mu else None
        if fh == "all_noballs":
            status = "ok" if g["viol"] <= max(1, g["fh"] // 500) else "conflict"
        elif fh == "none":
            status = "conflict" if mu >= 3 and _poisson_cdf(g["viol"], 0.5 * mu) < 0.05 else "ok"
        else:
            status = "conflict" if (mu >= 3 and 1 - _poisson_cdf(g["viol"] - 1, 0.6 * mu) < 0.05) or (
                g["viol"] == 0 and mu * 0.2 >= 3) else "ok"
        rows.append(dict(competition_id=cid, rule=fh, years=[g["y0"], g["y1"]], free_hit_balls=g["fh"],
                         protected_dismissals=g["viol"], base_rate=round(base, 4), expected_if_no_free_hit=round(mu, 2),
                         ratio=None if ratio is None else round(ratio, 3), status=status))
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
    """No-ball penalty: share of no-balls carrying 1 vs 2 extras vs noball_extra_runs."""
    groups = defaultdict(lambda: Counter())
    for s in summaries:
        g = groups[(_key(s), s["year"])]
        g["rule_" + str(s["rules"]["noball_extra_runs"])] += 1
        for inn in s["main_innings"]:
            for v, c in inn["nb"].items():
                if int(v) in (1, 2):
                    g[f"nb{int(v)}"] += c
    rows = []
    for (cid, year), g in sorted(groups.items()):
        n = g["nb1"] + g["nb2"]
        if not n:
            continue
        rule = 2 if g["rule_2"] > g["rule_1"] else 1
        share = g[f"nb{rule}"] / n
        rows.append(dict(competition_id=cid, year=year, one_run=g["nb1"], two_run=g["nb2"], rule=rule,
                         share_matching=round(share, 3), status="ok" if share >= 0.9 or n < 10 else "conflict"))
    return rows


def check_super_overs(summaries: list[dict]) -> list[dict]:
    """Ties: decided by super over / bowl-out vs the rules' super_over (resolved per match)."""
    groups = defaultdict(lambda: dict(ties=0, so=0, bowl_out=0, dl_ties=0, examples=[]))
    for s in summaries:
        if s["result"] != "tie":
            continue
        rule = s["rules"]["super_over_this_match"]
        g = groups[(_key(s), rule)]
        so = any(i["super_over"] for i in s["innings"])
        g["ties"] += 1
        g["so"] += so
        g["bowl_out"] += "bowl_out" in (s["outcome"] or {})
        g["dl_ties"] += s["method"] is not None
        ok = (rule == "none" and not so) or (rule in ("single", "repeat") and (so or s["method"] is not None)) or (
            rule == "bowl_out" and "bowl_out" in (s["outcome"] or {}))
        if not ok and len(g["examples"]) < 5:
            g["examples"].append(f"{s['match_id']}:{s['date']}")
        g["bad"] = g.get("bad", 0) + (not ok)
    return [dict(competition_id=cid, rule=rule, ties=g["ties"], super_over_ties=g["so"], bowl_outs=g["bowl_out"],
                 dl_ties=g["dl_ties"], mismatches=g.get("bad", 0), examples=g["examples"],
                 status="ok" if g.get("bad", 0) <= max(1, g["ties"] // 4) else "conflict")
            for (cid, rule), g in sorted(groups.items())]


def check_min_overs(summaries: list[dict]) -> list[dict]:
    """Shortest D/L chase that produced a result vs min_overs_for_result."""
    groups = defaultdict(lambda: dict(n=0, min=None, rule=set(), ex=None))
    for s in summaries:
        if s["method"] != "D/L" or s["result"] != "win" or len(s["main_innings"]) < 2:
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
        g["rule_days"][r["test_days"]] += 1
        g["rule_opd"][r["test_overs_per_day"]] += 1
        sched = r["test_days"] or n_days
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
        free_hit=check_free_hit(summaries), caught_crossing=check_caught_crossing(summaries),
        noball_runs=check_noball_runs(summaries),
        super_overs=check_super_overs(summaries), min_overs_for_result=check_min_overs(summaries),
        test_days=check_test_days(summaries))
    explain_anomalies(sections, load_config(config_path).get("data_anomalies", []))
    status = {}
    for name, rows in sections.items():
        flat = rows["pooled"] + rows["by_competition"] if isinstance(rows, dict) else rows
        status[name] = dict(Counter(r["status"] for r in flat))
    report = dict(generated_by="beating.cricket.rules.validate", config_version=load_config(config_path)["version"],
                  competitions=comps, status_counts=status, **sections)
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
