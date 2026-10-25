"""Declarative delivery-model features shared by the fits and both engines (plan 6.2-6.5, 8).

Method. `config/cricket-feature-spec.json` defines canonical per-ball *fields*, integer *factors* on them
(clip, half-open buckets, integer-ratio buckets, categorical maps and a few named builtins: the chase
resource ratio on the frozen resource table, Test runs per expected over left, batting depth), *groups*
that are mixed-radix products of factors (first factor most significant) with an applicability
condition, an optional per-row weight (or two indices weighted p and 1 - p for the bowler's-end umpire),
a class basis and a prior, plus standardized dense weather columns and class masks, for each delivery
model (dtype, outcome, wk) and fitting family (T20 with the Hundred's own context levels, ODI, TEST).
The spec is evaluated two ways that must agree exactly: vectorized over `balls_enriched` for a (fitting
family, gender) slice (`load_slice`, `group_levels`, `build_design`), and for one pre-ball engine view
plus bundle lookups (`levels_from_view`, the path `provider.py` and `provider.js` follow).
`views_from_rows` turns enriched rows into views with per-match lookups so that `parity` can compare the
two paths on real balls.

Designs keep rows of matches whose last played date is before the cutoff, weighted
0.5 ** (age_days / (365.25 * half_life_years)) from the match start, rows under 0.02 dropped, awarded
matches dropped. Labels follow the on-field reconstruction (plan 6.5): `onfield_class` / `onfield_wk`
where `drs_available` is true, the recorded class and kind otherwise; wides leave the outcome and wk fits.
Data-driven factors (players, venues, umpires, competitions, seasons, eras, matches) index label lists
built from the design rows and kept in `design.meta` for export; random-walk groups get `rw_prev`
(previous season of the competition; latest earlier listed year of the family); nested groups are
additive under their parent. Experience and role position come from the ingest as of each match date;
depth is computed here from the batting XI, arrivals and as-of role positions.

Limits. Depth uses the realized order of later batters for the fallback position of players without a
role history, and drops replaced-out players who had not batted from the recorded replacement innings
on. A view without `season_key` takes the competition's latest season started by the date (differs from
the recorded season in 144 of 23,132 matches). Dense columns and two-index weights are float32 in the
design; the scalar path is float64 throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from beating.cricket import glm, ingest as IG

ROOT = IG.ROOT
SPEC_PATH = ROOT / "config" / "cricket-feature-spec.json"
RESOURCE_PATH = ROOT / "data" / "derived" / "cricket" / "resource_table.json"
BALLS_PATH = IG.OUT_DIR / "balls_enriched.parquet"
MATCHES_PATH = IG.OUT_DIR / "matches_enriched.parquet"
REPORT_PATH = ROOT / "reports" / "cricket-features-summary.json"

DTYPES = ("legal", "wide", "noball")
WK_ALL = ("caught", "bowled", "lbw", "stumped", "other", "run_out")
TIMINGS = ("original", "pre_inn2", "unknown")
DNB = 99                      # arrival of a batter who has not batted
RECOGNIZED = 7                # depth counts batters with role position <= 7
MAX_ARR = 12
LIMITED = ("T20", "HUNDRED", "ODI")

# ball column -> field name; categorical fields are recoded to the spec's field levels on load
RENAME = {"inn_wkts": "wkts", "max_balls_known_before": "max_balls", "bat_home_status": "bat_home",
          "bowl_home_status": "bowl_home", "bowler_class": "bowl_class", "bowler_type": "bowl_type",
          "striker_hand": "bat_hand", "elevation_m": "elevation", "drs_available": "drs", "wx_temp_c": "temp",
          "wx_rh": "rh", "wx_cloud_oktas": "cloud", "wx_wet_day": "precip", "wx_dew_dep_evening": "dew_dep"}
FEATURE_COLS = ["match_id", "innings", "batter_id", "bowler_id", "dtype", "outcome_class", "onfield_class", "wk",
                "onfield_wk", "inn_wkts", "striker_balls", "striker_arrival", "nonstriker_arrival", "runs_required",
                "target_known", "target_timing", "max_balls_known_before", "balls_remaining", "field_restr",
                "bat_home_status", "bowl_home_status", "start_slot", "bowler_class", "bowler_type", "striker_hand",
                "striker_overseas", "bowler_overseas", "region", "ball_brand", "elevation_m", "ball_age_overs",
                "second_new_ball", "est_day", "est_overs_into_day", "exp_overs_left", "lead", "striker_exp",
                "bowler_exp", "striker_role_pos", "free_hit", "free_hit_p", "drs_available", "bowl_end_umpire_p",
                "fam", "competition_id", "season_key", "wx_temp_c", "wx_rh", "wx_cloud_oktas", "wx_wet_day",
                "wx_dew_dep_evening"]
VIEW_COLS = ["ball_seq", "over", "ball_in_over", "legal_ball_index", "non_striker_id", "inn_runs", "inn_unavailable",
             "striker_runs", "nonstriker_runs", "nonstriker_balls", "partnership_runs", "partnership_balls",
             "bowler_balls_inn", "bowler_spell_overs", "match_legal_balls", "target_runs", "pp_window",
             "bat_reviews_left", "bowl_reviews_left", "bat_fail_reviews", "bowl_fail_reviews"]
MATCH_COLS = ["match_id", "start_date", "dates_played", "fam", "fit_fam", "gender", "team_type", "venue_id",
              "venue_country", "region", "elevation_m", "ball_brand", "competition_id", "season_key", "umpire1_id",
              "umpire2_id", "awarded", "scheduled_days", "scheduled_balls", "xi_start_team1", "xi_start_team2",
              "subs", "team1", "team2", "team1_raw", "team2_raw", "start_slot", "home_status1", "home_status2"]
EXTRA_LEVELS = {"dtype": DTYPES, "target_timing": TIMINGS, "wk": WK_ALL, "onfield_wk": WK_ALL,
                "pp_window": IG.PP_LEVELS}


def load_spec(path=SPEC_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def load_resource(path=RESOURCE_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------- slices

@dataclass
class Slice:
    """Enriched balls of one (fitting family, gender), field-ready: categorical codes in the spec's field
    levels (-1 null), numbers with nulls as float32 NaN, ids as int32 person ids."""
    fit_fam: str
    gender: str
    b: dict
    m: pd.DataFrame          # slice matches sorted by match_id; b["mi"] indexes rows of it
    ident: np.ndarray        # person_id -> registry identifier
    cands: dict | None = None

    @property
    def n(self) -> int:
        return len(self.b["match_id"])


def _cat_levels(spec: dict) -> dict:
    out = {k: tuple(v["levels"]) for k, v in spec["fields"].items() if v["kind"] == "cat"}
    out.update(EXTRA_LEVELS)
    return out


def _arrow_to_numpy(col, levels=None):
    """(array, labels): dictionary columns as int16 codes (recoded to `levels` when given, else with their
    own label list), booleans / nullable ints / floats as float32 with NaN, other ints native."""
    if pa.types.is_dictionary(col.type):
        own = col.dictionary.to_pylist()
        codes = col.indices.fill_null(-1).to_numpy(zero_copy_only=False).astype(np.int16)
        if levels is None:
            return codes, own
        lut = np.array([levels.index(v) if v in levels else -1 for v in own] + [-1], dtype=np.int16)
        return lut[codes], list(levels)
    if pa.types.is_boolean(col.type) or pa.types.is_floating(col.type) or col.null_count:
        return col.cast(pa.float32()).fill_null(float("nan")).to_numpy(zero_copy_only=False), None
    return col.to_numpy(zero_copy_only=False), None


def load_slice(fit_fam: str, gender: str, match_ids=None, *, full: bool = False, spec: dict | None = None,
               candidates: bool | None = None) -> Slice:
    """Read the slice's balls (only the row groups holding `match_ids` when given) and its matches, and
    compute depth. `full` adds the columns `views_from_rows` needs and keeps per-innings batting orders."""
    spec = spec or load_spec()
    fams = spec["fit_families"][fit_fam]
    m = IG.read_table(MATCHES_PATH, columns=MATCH_COLS)
    m = m[(m.fit_fam == fit_fam) & (m.gender == gender)]
    if match_ids is not None:
        m = m[m.match_id.isin(np.asarray(match_ids))]
    m = m.sort_values("match_id").reset_index(drop=True)
    ids = m.match_id.to_numpy(np.int64)
    pf = pq.ParquetFile(BALLS_PATH)
    groups = list(range(pf.metadata.num_row_groups))
    if match_ids is not None:
        def hit(g):
            s = pf.metadata.row_group(g).column(0).statistics
            return s is None or bool(((ids >= s.min) & (ids <= s.max)).any())
        groups = [g for g in groups if hit(g)]
    cols = FEATURE_COLS + (VIEW_COLS if full else [])
    parts = []
    for g in groups:
        t = pf.read_row_group(g, columns=cols)
        keep = np.isin(t.column("match_id").to_numpy(), ids)
        if keep.any():
            parts.append(t.filter(pa.array(keep)))
        del t
    t = pa.concat_tables(parts).unify_dictionaries() if parts else pf.schema_arrow.empty_table().select(cols)
    del parts
    levels = _cat_levels(spec)
    b = {}
    for c in cols:
        name = RENAME.get(c, c)
        col = t.column(c).combine_chunks()
        arr, lab = _arrow_to_numpy(col, levels.get(name) if c not in ("competition_id", "season_key") else None)
        b[name] = arr
        if lab is not None and c in ("competition_id", "season_key"):
            b[name + "_labels"] = lab
        t = t.drop_columns([c])
    b["mi"] = np.searchsorted(ids, b["match_id"]).astype(np.int32)
    if not set(np.unique(b["fam"])) <= {spec["fields"]["fam"]["levels"].index(f) for f in fams}:
        raise ValueError("slice holds rows outside its fitting family")
    people = IG.read_table("people_index", columns=["person_id", "identifier"])
    ident = np.empty(int(people.person_id.max()) + 1, dtype=object)
    ident[people.person_id.to_numpy()] = people.identifier.to_numpy()
    sl = Slice(fit_fam, gender, b, m, ident)
    _attach_depth(sl, keep_orders=full if candidates is None else candidates)
    return sl


def _json_list(s):
    return json.loads(s) if isinstance(s, str) and s else []


def _innings_orders(sl: Slice) -> dict:
    """(match_id, innings) -> (person ids in batting order, arrivals, as-of role positions or NaN):
    batters of the innings by arrival, then XI players who did not bat in XI order, minus players
    replaced out (recorded replacement innings <= this innings) who had not batted."""
    m = sl.m
    mids = m.match_id.to_numpy()
    inn = pd.read_parquet(IG.OUT_DIR / "innings.parquet", columns=["match_id", "innings", "team_idx"])
    inn = inn[inn.match_id.isin(mids)]
    pi = IG.read_table("player_innings", columns=["match_id", "innings", "team_idx", "player_id", "arrival",
                                                   "balls_faced", "balls_bowled"])
    meta = IG.read_table(MATCHES_PATH, columns=["match_id", "start_date", "fit_fam", "gender"])
    meta = meta[(meta.fit_fam == sl.fit_fam) & (meta.gender == sl.gender)]
    pi = pi[pi.match_id.isin(meta.match_id)]
    here = pi[pi.match_id.isin(mids)]
    xi_players = set()
    for c in ("xi_start_team1", "xi_start_team2"):
        for s in m[c]:
            xi_players.update(_json_list(s))
    players = set(here.player_id.tolist()) | xi_players
    ctx = IG.player_context(pi[pi.player_id.isin(players)], meta)
    role = dict(zip(zip(ctx.match_id.to_numpy(), ctx.player_id.to_numpy()), ctx.striker_role_pos.to_numpy()))
    bats = here[here.arrival > 0].sort_values(["match_id", "innings", "arrival"])
    batted = {k: (g.player_id.tolist(), g.arrival.tolist()) for k, g in bats.groupby(["match_id", "innings"])}
    row = {mid: i for i, mid in enumerate(mids)}
    out = {}
    for mid, k, t in zip(inn.match_id.to_numpy(), inn.innings.to_numpy(), inn.team_idx.to_numpy()):
        r = m.iloc[row[mid]]
        names = {r[f"team{t}"], r[f"team{t}_raw"]}
        gone = {s["out"] for s in _json_list(r.subs) if s.get("team") in names and s.get("out") is not None
                and (s.get("innings") or 0) <= k}
        ids, arr = batted.get((mid, k), ([], []))
        seen = set(ids)
        dnb = [p for p in _json_list(r[f"xi_start_team{t}"]) if p not in seen and p not in gone]
        order = list(ids) + dnb
        out[(int(mid), int(k))] = (order, list(arr) + [DNB] * len(dnb),
                                   [float(role.get((mid, p), np.nan)) for p in order])
    return out


def _attach_depth(sl: Slice, keep_orders: bool = False) -> None:
    """depth per ball (spec builtin 'depth'): batters still to come with role position <= 7, the role
    position of a player without history being his expected arrival rank m + 1 + i."""
    orders = _innings_orders(sl)
    keys = sorted(orders)
    kidx = {k: i for i, k in enumerate(keys)}
    width = max([len(orders[k][0]) for k in keys] + [1]) + 1
    n_inn = len(keys)
    c_tab = np.zeros((n_inn, MAX_ARR + 1), dtype=np.int16)     # entries with arrival <= m
    s_known = np.zeros((n_inn, width), dtype=np.int16)         # prefix counts of known role <= 7
    s_nan = np.zeros((n_inn, width), dtype=np.int16)           # prefix counts of unknown role
    k_len = np.zeros(n_inn, dtype=np.int16)
    for i, k in enumerate(keys):
        order, arr, rp = orders[k]
        a = np.asarray(arr, dtype=np.int64)
        c_tab[i] = np.searchsorted(a, np.arange(MAX_ARR + 1), side="right")
        r = np.asarray(rp, dtype=np.float64)
        s_known[i, 1:len(r) + 1] = np.cumsum(~np.isnan(r) & (r <= RECOGNIZED))
        s_known[i, len(r) + 1:] = s_known[i, len(r)]
        s_nan[i, 1:len(r) + 1] = np.cumsum(np.isnan(r))
        s_nan[i, len(r) + 1:] = s_nan[i, len(r)]
        k_len[i] = len(r)
    b = sl.b
    key = list(zip(b["match_id"].tolist(), b["innings"].tolist()))
    ii = np.array([kidx.get(k, -1) for k in key], dtype=np.int64)
    mm = np.clip(np.maximum(b["striker_arrival"], b["nonstriker_arrival"]).astype(np.int64), 0, MAX_ARR)
    ok = ii >= 0
    i0 = np.where(ok, ii, 0)
    c = c_tab[i0, mm].astype(np.int64)
    kl = k_len[i0].astype(np.int64)
    hi = np.clip(RECOGNIZED - mm + c, c, kl)
    d = (s_known[i0, kl] - s_known[i0, c]) + (s_nan[i0, hi] - s_nan[i0, c])
    b["depth"] = np.where(ok, d, np.nan).astype(np.float32)
    sl.cands = orders if keep_orders else None


# ---------------------------------------------------------------- vectorized fields

class VecFields:
    """Canonical fields of the slice rows `rows` (all rows when None), computed on demand."""

    def __init__(self, sl: Slice, spec: dict, rows=None):
        self.sl, self.spec, self.rows, self.cache = sl, spec, rows, {}
        self.levels = _cat_levels(spec)

    def raw(self, name):
        a = self.sl.b[name]
        return a if self.rows is None else a[self.rows]

    def code(self, name, value) -> int:
        lv = self.levels[name]
        return lv.index(value) if value in lv else -2

    def __getitem__(self, name):
        if name in self.cache:
            return self.cache[name]
        sl, f = self.sl, None
        if name == "elapsed":
            f = self.num("max_balls") - self.num("balls_remaining")
        elif name == "super_over":
            f = np.zeros(self.n, np.float32)
        elif name == "runs_required":
            f = np.where(self.raw("target_known") == 1, self.raw("runs_required"), np.nan)
        elif name == "chase_ok":
            f = ((self.raw("fam") != self.code("fam", "TEST")) & (self.raw("innings") == 2)
                 & (self.raw("target_known") == 1) & np.isin(self.raw("target_timing"), [0, 1])
                 & ~np.isnan(self.raw("runs_required"))).astype(np.float32)
        elif name == "overs_into_day":
            f = np.floor(self.raw("est_overs_into_day"))
        elif name == "scheduled_days":
            f = sl.m.scheduled_days.to_numpy(np.float32, na_value=np.nan)[self.raw("mi")]
        elif name == "year":
            f = sl.m.start_date.str[:4].astype(int).to_numpy(np.float32)[self.raw("mi")]
        elif name == "is_noball":
            f = (self.raw("dtype") == 2).astype(np.float32)
        else:
            f = self.raw(name)
        self.cache[name] = f
        return f

    def num(self, name) -> np.ndarray:
        return np.asarray(self[name], dtype=np.float64)

    @property
    def n(self) -> int:
        return len(self.raw("match_id"))


# ---------------------------------------------------------------- ids (data-driven factors)

def _season_first_dates(m: pd.DataFrame) -> dict:
    return m.groupby("season_key").start_date.min().to_dict()


def build_ids(F: VecFields) -> dict:
    """Label lists of the data-driven factors over the rows of F, with per-row codes."""
    sl, out = F.sl, {}
    mi = F.raw("mi")
    m = sl.m

    def make(name, labels, per_row, order=None):
        labels = sorted(set(labels) - {None}, key=order) if order else sorted(set(labels) - {None})
        idx = {s: i for i, s in enumerate(labels)}
        out[name] = {"labels": labels, "index": idx, "codes": per_row(idx)}

    for name, col in (("batter", "batter_id"), ("bowler", "bowler_id")):
        pid = F.raw(col)
        u = np.unique(pid[pid >= 0])
        labs = [sl.ident[p] for p in u]

        def per_row(idx, pid=pid, u=u, labs=labs):
            lut = np.full(len(sl.ident) + 1, -1, dtype=np.int32)
            lut[u] = [idx[s] for s in labs]
            return lut[np.where(pid >= 0, pid, len(sl.ident))]
        make(name, labs, per_row)
    used = np.unique(mi)
    mu = m.iloc[used]

    def per_match(values):
        values = np.asarray(values, dtype=object)

        def f(idx):
            lut = np.array([idx.get(v, -1) if v is not None and v == v else -1 for v in values] + [-1], np.int32)
            return lut[mi]
        return f
    make("venue", mu.venue_id.dropna().tolist(), per_match(m.venue_id.to_numpy(object)))
    make("competition", mu.competition_id.tolist(), per_match(m.competition_id.to_numpy(object)))
    first = _season_first_dates(m)
    make("season", mu.season_key.tolist(), per_match(m.season_key.to_numpy(object)),
         order=lambda s: (s.rsplit(":", 1)[0], first[s], s))
    # era label: the row's own fam (Hundred rows keep HUNDRED) and the match year
    fam_lv = F.levels["fam"]
    ekey = F.raw("fam").astype(np.int64) * 10000 + F["year"].astype(np.int64)
    ek, inv = np.unique(ekey, return_inverse=True)
    elabels = [f"{fam_lv[k // 10000]}|{k % 10000}" for k in ek]
    labels = sorted(elabels, key=lambda s: (s.split("|")[0], int(s.split("|")[1])))
    index = {s: i for i, s in enumerate(labels)}
    out["era"] = {"labels": labels, "index": index,
                  "codes": np.array([index[s] for s in elabels], np.int32)[inv]}
    ump = sorted({sl.ident[int(u)] for c in ("umpire1_id", "umpire2_id") for u in mu[c].dropna().tolist()})
    uidx = {s: i for i, s in enumerate(ump)}

    def ump_codes(c):
        vals = [uidx.get(sl.ident[int(u)], -1) if u == u and u is not None else -1
                for u in m[c].to_numpy(object, na_value=np.nan)]
        return np.array(vals + [-1], np.int32)[mi]
    out["umpire"] = {"labels": ump, "index": uidx, "codes": ump_codes("umpire1_id"), "codes2": ump_codes("umpire2_id")}
    mid = F.raw("match_id")
    um, inv = np.unique(mid, return_inverse=True)
    out["match"] = {"labels": [str(x) for x in um], "codes": inv.astype(np.int32)}
    out["match"]["index"] = {s: i for i, s in enumerate(out["match"]["labels"])}
    key = mid.astype(np.int64) * 8 + F.raw("innings").astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    out["match_innings"] = {"labels": [f"{k // 8}:{k % 8}" for k in uk], "codes": inv.astype(np.int32)}
    out["match_innings"]["index"] = {s: i for i, s in enumerate(out["match_innings"]["labels"])}
    out["season"]["first"] = {s: first[s] for s in out["season"]["labels"]}
    return out


def _rw_prev_of_id(name: str, ids: dict) -> np.ndarray:
    labels = ids[name]["labels"]
    prev = np.full(len(labels), -1, dtype=np.int64)
    sep = ":" if name == "season" else "|"
    for i in range(1, len(labels)):
        if labels[i].rsplit(sep, 1)[0] == labels[i - 1].rsplit(sep, 1)[0]:
            prev[i] = i - 1
    return prev


# ---------------------------------------------------------------- factors, groups, weights (vectorized)

_RES_CACHE: dict = {}


def _resource_args(fam: str, gender: str, res: dict):
    """(P as an int array, N, G100) of the frozen resource table for a limited-overs fam, else None."""
    t = {"T20": "T20", "HUNDRED": "T20", "ODI": "ODI"}.get(fam)
    if t is None:
        return None
    key = (id(res), t, gender)
    if key not in _RES_CACHE:
        tab = res["tables"][t][gender]
        _RES_CACHE[key] = (res, np.asarray(tab["P"], dtype=np.int64), tab["N"], int(math.floor(100 * tab["G"] + 0.5)))
    return _RES_CACHE[key][1:]


def factor_size(spec: dict, name: str, fit_fam: str, ids: dict | None = None) -> int:
    f = spec["factors"][name]
    t = f["type"]
    if t == "id":
        return len(ids[f["id"]]["labels"])
    if t == "categorical":
        return len(f["levels_by_fit_family"][fit_fam]) if "levels_by_fit_family" in f else f["n"]
    if t == "clip":
        return f["hi"] - f["lo"] + 1
    if t == "buckets":
        return len(f["cuts"]) + 1
    if t == "bool":
        return 2
    if t == "ratio_buckets":
        cuts = f.get("cuts") or next(iter(f["cuts_by_fam"].values()))
        return len(cuts) + 1
    return f["n"]


def factor_vec(spec: dict, name: str, F: VecFields, ids: dict | None = None, res: dict | None = None) -> np.ndarray:
    """int32 levels of factor `name` for every row of F (-1 = not applicable)."""
    f = spec["factors"][name]
    t, fit_fam = f["type"], F.sl.fit_fam
    if t == "id":
        return ids[f["id"]]["codes"]
    if t == "categorical":
        own = F.levels[f["field"]]
        if "levels_by_fit_family" in f:
            tg = f["levels_by_fit_family"][fit_fam]
            lut = [tg.index(v) if v in tg else -1 for v in own] + [-1]
        else:
            null = f.get("null_level", -1)
            lut = [f["map"].get(v, null) for v in own] + [null]
        return np.asarray(lut, dtype=np.int32)[F[f["field"]]]
    if t == "clip":
        x = F.num(f["field"])
        return np.where(np.isnan(x), -1, np.clip(np.nan_to_num(x), f["lo"], f["hi"]) - f["lo"]).astype(np.int32)
    if t == "buckets":
        x = F.num(f["field"])
        lev = np.searchsorted(np.asarray(f["cuts"], np.float64), x,
                              side="left" if f.get("side") == "right" else "right").astype(np.int32)
        lev[np.isnan(x)] = -1
        return lev
    if t == "bool":
        x = F.num(f["field"])
        return np.where(np.isnan(x), -1, x).astype(np.int32)
    if t == "ratio_buckets":
        num, den = F.num(f["num"]), F.num(f["den"])
        lev = np.zeros(F.n, dtype=np.int32)
        fam = F.raw("fam")
        for code, fname in enumerate(F.levels["fam"]):
            cuts = f["cuts"] if "cuts" in f else f["cuts_by_fam"].get(fname, [])
            sel = fam == code
            if not sel.any():
                continue
            for a, b in cuts:
                lev[sel] += (b * num[sel] >= a * den[sel])
        lev[np.isnan(num)] = -1
        lev[np.isnan(den)] = f["den_null_level"]
        lev[F.num("super_over") > 0] = f["super_over_level"]
        return lev
    if t == "builtin" and f["name"] == "resource_ratio":
        res = res or load_resource()
        lev = np.full(F.n, -1, dtype=np.int32)
        rr, u, w = F.num("runs_required"), F.num("balls_remaining"), F.num("wkts")
        fam = F.raw("fam")
        for code, fname in enumerate(F.levels["fam"]):
            args = _resource_args(fname, F.sl.gender, res)
            sel = (fam == code) & ~np.isnan(rr) & ~np.isnan(u) & ~np.isnan(w)
            if args is None or not sel.any():
                continue
            P, N, g100 = args
            p = P[np.clip(u[sel], 0, N).astype(np.int64), np.clip(w[sel], 0, 10).astype(np.int64)].astype(np.float64)
            lhs = 1e7 * rr[sel]
            lev[sel] = sum((lhs >= c * p * g100).astype(np.int32) for c in f["cuts100"])
        return lev
    if t == "builtin" and f["name"] == "runs_per_over_left":
        rr, eol = F.num("runs_required"), F.num("exp_overs_left")
        lev = sum((rr >= c * eol).astype(np.int32) for c in f["cuts"])
        lev[np.isnan(rr) | np.isnan(eol)] = -1
        return lev
    raise ValueError(f"unknown factor {name!r}")


def _cond_vec(F: VecFields, clauses: list) -> np.ndarray:
    ok = np.ones(F.n, dtype=bool)
    for c in clauses:
        name, op, val = c["field"], c["op"], c.get("value")
        if name in F.levels:
            x = F[name]
            if op == "eq":
                ok &= x == F.code(name, val)
            elif op == "ne":
                ok &= (x >= 0) & (x != F.code(name, val))
            elif op == "in":
                ok &= np.isin(x, [F.code(name, v) for v in val])
            elif op == "notnull":
                ok &= x >= 0
            else:
                raise ValueError(op)
            continue
        x = F.num(name)
        v = float(val) if isinstance(val, (bool, int, float)) else val
        if op == "eq":
            ok &= x == v
        elif op == "ne":
            ok &= ~np.isnan(x) & (x != v)
        elif op == "in":
            ok &= np.isin(x, [float(t) for t in val])
        elif op == "notnull":
            ok &= ~np.isnan(x)
        elif op == "ge":
            ok &= x >= v
        elif op == "le":
            ok &= x <= v
        else:
            raise ValueError(op)
    return ok


def weight_vec(spec: dict, name: str, F: VecFields) -> np.ndarray:
    key = ("_w", name)
    if key in F.cache:
        return F.cache[key]
    bc = F["bowl_class"]
    test = F.raw("fam") == F.code("fam", "TEST")
    if name == "is_spin":
        w = (bc == F.code("bowl_class", "spin")).astype(np.float64)
    elif name == "is_pace":
        w = (bc == F.code("bowl_class", "pace")).astype(np.float64)
    elif name == "spin_sign":
        w = (bc == F.code("bowl_class", "spin")).astype(np.float64) - (bc == F.code("bowl_class", "pace"))
    elif name == "is_death":
        w = ((factor_vec(spec, "phase3", F) == 2) & ~test).astype(np.float64)
    elif name == "newball":
        ph = factor_vec(spec, "phase3", F)
        w = np.where(test, F.num("ball_age_overs") <= 15, ph == 0).astype(np.float64)
    elif name == "first10":
        w = (F.num("striker_balls") < 10).astype(np.float64)
    elif name == "wear":
        s, d = F.num("scheduled_days"), F.num("est_day")
        ok = test & (s > 1) & ~np.isnan(d)
        with np.errstate(invalid="ignore", divide="ignore"):
            w = np.where(ok, (np.minimum(d, s) - 1) / (s - 1), 0.0)
    elif name == "free_hit_p":
        w = np.nan_to_num(F.num("free_hit_p"))
    else:
        raise ValueError(f"unknown weight {name!r}")
    F.cache[key] = w
    return w


def model_groups(spec: dict, model: str, fit_fam: str) -> list[dict]:
    return [g for g in spec["models"][model]["groups"] if fit_fam in g.get("fit_families", spec["fit_families"])]


def group_levels(spec: dict, g: dict, F: VecFields, ids: dict, res: dict | None = None) -> dict:
    """{'index', 'n', 'weight', 'index2', 'weight2'} of group g for every row of F; index -1 where the group
    does not apply or its weight is 0; weight None means 1."""
    if g.get("two_index"):
        ids_u = ids["umpire"]
        p = F.num("bowl_end_umpire_p")
        w, w2 = np.nan_to_num(p, nan=0.5), 1.0 - np.nan_to_num(p, nan=0.5)
        i1, i2 = ids_u["codes"].copy(), ids_u["codes2"].copy()
        ok = _cond_vec(F, g.get("when", []))
        i1[~ok | (w == 0)] = -1
        i2[~ok | (w2 == 0)] = -1
        return {"index": i1, "n": len(ids_u["labels"]), "weight": w, "index2": i2, "weight2": w2}
    lev = np.zeros(F.n, dtype=np.int64)
    n = 1
    for name in g["factors"]:
        x = factor_vec(spec, name, F, ids, res)
        k = factor_size(spec, name, F.sl.fit_fam, ids)
        lev = np.where((lev < 0) | (x < 0), -1, lev * k + x)
        n *= k
    if g.get("when"):
        lev[~_cond_vec(F, g["when"])] = -1
    w = None
    if g.get("weight"):
        w = weight_vec(spec, g["weight"], F)
        lev[w == 0] = -1
    return {"index": lev, "n": n, "weight": w, "index2": None, "weight2": None}


def _small_int(a: np.ndarray, n: int) -> np.ndarray:
    return a.astype(np.int8 if n < 127 else np.int16 if n < 32767 else np.int32)


def basis_matrix(spec: dict, model: str, basis) -> np.ndarray | None:
    k1 = len(spec["classes"][spec["models"][model]["classes"]]) - 1
    if basis in (None, "all"):
        return None
    if "direction" in basis:
        return np.asarray(spec["directions"][basis["direction"]][1:], dtype=np.float64)[None, :]
    cls = basis["classes"] if "classes" in basis else [c for c in range(1, k1 + 1) if c not in basis["exclude"]]
    out = np.zeros((len(cls), k1))
    out[np.arange(len(cls)), np.asarray(cls) - 1] = 1.0
    return out


def factor_labels(spec: dict, name: str, fit_fam: str, ids: dict | None) -> list[str]:
    f = spec["factors"][name]
    t = f["type"]
    if t == "id":
        return list(ids[f["id"]]["labels"])
    if t == "categorical":
        if "levels_by_fit_family" in f:
            return list(f["levels_by_fit_family"][fit_fam])
        names = [[] for _ in range(f["n"])]
        for k, v in f["map"].items():
            names[v].append(k)
        return ["/".join(x) if x else "null" for x in names]
    if t == "clip":
        return [str(v) for v in range(f["lo"], f["hi"] + 1)]
    if t == "buckets":
        c = f["cuts"]
        if f.get("side") == "right":
            return [f"<={c[0]}"] + [f"({a},{b}]" for a, b in zip(c, c[1:])] + [f">{c[-1]}"]
        return [f"<{c[0]}"] + [f"[{a},{b})" for a, b in zip(c, c[1:])] + [f">={c[-1]}"]
    if t == "bool":
        return ["false", "true"]
    return [str(i) for i in range(factor_size(spec, name, fit_fam, ids))]


def group_labels(spec: dict, g: dict, fit_fam: str, ids: dict) -> list[str]:
    if g.get("two_index"):
        return list(ids["umpire"]["labels"])
    out = [""]
    for name in g["factors"]:
        lab = factor_labels(spec, name, fit_fam, ids)
        out = [f"{a}|{b}" if a else b for a in out for b in lab]
    return out


def group_rw_prev(spec: dict, g: dict, fit_fam: str, ids: dict) -> np.ndarray | None:
    prior = g.get("prior") or {}
    if prior.get("type") != "rw":
        return None
    over = {"season": "season", "year": "era"}[prior["over"]]
    names = g["factors"]
    dims = [factor_size(spec, x, fit_fam, ids) for x in names]
    pos = [i for i, x in enumerate(names) if spec["factors"][x].get("id") == over][0]
    comp = list(np.unravel_index(np.arange(int(np.prod(dims))), dims))
    p = _rw_prev_of_id(over, ids)[comp[pos]]
    comp[pos] = np.maximum(p, 0)
    return np.where(p >= 0, np.ravel_multi_index(comp, dims), -1)


# ---------------------------------------------------------------- dense columns and masks

def dense_stats(spec: dict, model: str, F: VecFields) -> dict:
    out = {}
    for d in spec["models"][model]["dense"]:
        if d["field"] in out:
            continue
        x = F.num(d["field"])
        x = x[~np.isnan(x)]
        mu = float(x.mean()) if len(x) else 0.0
        sd = float(x.std()) if len(x) else 1.0
        out[d["field"]] = [mu, sd if sd >= 1e-9 else 1.0]
    return out


def dense_columns(spec: dict, model: str, fit_fam: str) -> list[dict]:
    return [d for d in spec["models"][model]["dense"] if fit_fam in d.get("fit_families", spec["fit_families"])]


def dense_vec(spec: dict, model: str, F: VecFields, stats: dict) -> np.ndarray:
    cols = dense_columns(spec, model, F.sl.fit_fam)
    out = np.zeros((F.n, len(cols)), dtype=np.float64)
    for j, d in enumerate(cols):
        mu, sd = stats[d["field"]]
        x = F.num(d["field"])
        z = (x - mu) / sd
        z[np.isnan(z)] = 0.0
        z = z * float(d.get("sign", 1))
        if d.get("times"):
            z = z * weight_vec(spec, d["times"], F)
        if d.get("when"):
            z[~_cond_vec(F, d["when"])] = 0.0
        out[:, j] = z
    return out


def mask_vec(spec: dict, model: str, F: VecFields) -> list[tuple[np.ndarray, int]]:
    out = []
    for mk in spec["models"][model]["masks"]:
        hit = np.zeros(F.n, dtype=bool)
        for c in mk["any"]:
            hit |= _cond_vec(F, [c])
        out.append((hit, mk["class"]))
    return out


# ---------------------------------------------------------------- designs

def design_rows(sl: Slice, model: str, cutoff: str, half_life: float, spec: dict | None = None,
                min_weight: float | None = None):
    """(rows, weights, labels) of the model's design at the cutoff: strictly pre-cutoff matches (last
    played date before it), time-decay weights from the match start, rows under min_weight dropped."""
    spec = spec or load_spec()
    b, m = sl.b, sl.m
    min_weight = spec["design"]["min_weight"] if min_weight is None else min_weight
    last = m.dates_played.map(lambda s: max(_json_list(s)) if _json_list(s) else None).fillna(m.start_date)
    ok_m = (last.to_numpy(str) < cutoff) & ~m.awarded.fillna(False).to_numpy(bool)
    age = (np.datetime64(cutoff) - m.start_date.to_numpy("datetime64[D]")).astype(np.float64)
    wm = 0.5 ** (age / (365.25 * half_life))
    mi = b["mi"]
    keep = ok_m[mi] & (wm[mi] >= min_weight)
    dt = spec["models"][model]["rows"]["dtype_in"]
    keep &= np.isin(b["dtype"], [DTYPES.index(x) for x in dt])
    drs = b["drs"] == 1
    if model == "dtype":
        y = b["dtype"].astype(np.int16)
    else:
        cls = np.where(drs, b["onfield_class"], b["outcome_class"])
        if model == "outcome":
            y = np.nan_to_num(cls, nan=-1).astype(np.int16)
        else:
            kind = np.where(drs, b["onfield_wk"], b["wk"]).astype(np.int16)
            y = np.where((cls == 6) & (kind >= 0) & (kind < 5), kind, -1).astype(np.int16)
    keep &= y >= 0
    rows = np.flatnonzero(keep)
    return rows, wm[mi[rows]], y[rows].astype(np.int8)


def build_design(sl: Slice, model: str, cutoff: str, half_life: float, spec: dict | None = None,
                 res: dict | None = None) -> glm.Design:
    """glm.Design of `model` for the slice at `cutoff` with time decay `half_life` (years). design.meta keeps
    the label lists, group descriptions, dense standardization and row counts needed for export."""
    spec = spec or load_spec()
    res = res or load_resource()
    t0 = time.time()
    rows, w, y = design_rows(sl, model, cutoff, half_life, spec)
    F = VecFields(sl, spec, rows)
    ids = build_ids(F)
    k = len(spec["classes"][spec["models"][model]["classes"]])
    groups, gmeta = [], {}
    for g in model_groups(spec, model, sl.fit_fam):
        lv = group_levels(spec, g, F, ids, res)
        prior = g.get("prior") or spec["design"]["default_prior"]
        grp = glm.Group(name=g["name"], index=_small_int(lv["index"], lv["n"]), n_levels=lv["n"],
                        sigma=float(prior.get("sd", g.get("sd", 0.1))),
                        weight=None if lv["weight"] is None else lv["weight"].astype(np.float32),
                        index2=None if lv["index2"] is None else _small_int(lv["index2"], lv["n"]),
                        weight2=None if lv["weight2"] is None else lv["weight2"].astype(np.float32),
                        basis=basis_matrix(spec, model, g.get("basis")),
                        labels=group_labels(spec, g, sl.fit_fam, ids),
                        rw_prev=group_rw_prev(spec, g, sl.fit_fam, ids),
                        sigma_root=float(prior.get("sd_root", 1.0)))
        groups.append(grp)
        hit = lv["index"][lv["index"] >= 0]
        used = np.unique(hit).size
        gmeta[g["name"]] = {"factors": g["factors"], "n_levels": lv["n"], "n_used": int(used),
                            "level_rows": np.bincount(hit, minlength=lv["n"]).tolist() if lv["n"] <= 64 else None,
                            "rows": int((lv["index"] >= 0).sum()), "parent": g.get("parent"),
                            "prior": prior.get("type", "iid"), "component": g.get("component"),
                            "export": g.get("export"), "latent": g.get("latent"), "weight": g.get("weight"),
                            "two_index": g.get("two_index")}
        del lv
    stats = dense_stats(spec, model, F)
    cols = dense_columns(spec, model, sl.fit_fam)
    dense = dense_vec(spec, model, F, stats).astype(np.float32) if cols else None
    masks = mask_vec(spec, model, F)
    d = glm.Design(y=y, n_classes=k, groups=groups, weights=w, dense=dense,
                   dense_names=[c["name"] for c in cols], masks=masks)
    d.meta = {"fit_fam": sl.fit_fam, "gender": sl.gender, "model": model, "cutoff": cutoff, "half_life": half_life,
              "spec_version": spec["version"], "rows": int(len(rows)), "weight_sum": float(w.sum()),
              "row_index": rows, "groups": gmeta, "standardize": stats,
              "ids": {kx: v["labels"] for kx, v in ids.items()},
              "season_first": ids["season"]["first"], "seconds": round(time.time() - t0, 2)}
    return d


def design_nbytes(d: glm.Design) -> int:
    n = d.y.nbytes + (0 if d.weights is None else d.weights.nbytes) + (0 if d.dense is None else d.dense.nbytes)
    n += sum(m.nbytes for m, _ in d.masks)
    for g in d.groups:
        for a in (g.index, g.weight, g.index2, g.weight2):
            n += 0 if a is None else a.nbytes
    return n


def model_lookups(design_meta: dict) -> dict:
    """The per-model part of the scalar lookups: label -> index maps and dense standardization."""
    ids = {k: {s: i for i, s in enumerate(v)} for k, v in design_meta["ids"].items()}
    return {"ids": ids, "standardize": design_meta["standardize"]}


# ---------------------------------------------------------------- scalar path (one view)

def season_from_view(view: dict, lookups: dict):
    if view.get("season_key"):
        return view["season_key"]
    seasons = (lookups.get("seasons") or {}).get(view.get("competition_id")) or []
    date = str(view.get("date") or "")[:10]
    out = None
    for first, key in seasons:
        if first <= date:
            out = key
    return out


def view_fields(v: dict, lookups: dict) -> dict:
    """Canonical fields of one pre-ball view (spec 'fields', view derivations)."""
    players, ctx = lookups.get("players") or {}, lookups.get("player_ctx") or {}
    venue = (lookups.get("venues") or {}).get(v.get("venue_id")) or {}
    fam, so = v["fam"], v.get("super_over") or 0
    st, ns, bw = v.get("striker"), v.get("nonstriker"), v.get("bowler")
    ps, pb = players.get(st) or {}, (players.get(bw) or {}) if bw is not None else {}
    cs, cb = ctx.get(st) or {}, (ctx.get(bw) or {}) if bw is not None else {}
    mb, br, rr = v.get("max_balls"), v.get("balls_remaining"), v.get("runs_required")
    club = ((lookups.get("competitions") or {}).get(v.get("competition_id")) or {}).get("club")
    vc = venue.get("country")

    def overseas(p):
        c = p.get("country")
        return (c != vc) if club and c and vc else None
    role = cs.get("role_pos")
    m = max(v.get("striker_arrival") or 0, v.get("nonstriker_arrival") or 0)
    depth = None
    if v.get("to_come") is not None:
        depth = 0
        for i, p in enumerate(v["to_come"]):
            r = (ctx.get(p) or {}).get("role_pos")
            depth += (r if r is not None else m + 1 + i) <= RECOGNIZED
    fh = v.get("free_hit")
    wx = v.get("weather")
    if wx is None:
        month = str(v.get("date") or "")[5:7]
        wx = ((lookups.get("climatology") or {}).get(v.get("venue_id")) or {}).get(month)
    wx = dict(wx or {})
    days = wx.get("days")
    if fam == "TEST" and days and v.get("est_day") and v["est_day"] <= len(days) and days[v["est_day"] - 1]:
        wx.update({k: x for k, x in days[v["est_day"] - 1].items() if x is not None})
    return {
        "fam": fam, "innings": v.get("so_innings") if so else v.get("innings"), "super_over": so,
        "max_balls": mb, "balls_remaining": br, "elapsed": None if mb is None or br is None else mb - br,
        "wkts": v.get("wkts"), "runs_required": rr,
        "chase_ok": fam != "TEST" and rr is not None and v.get("target_timing") in ("original", "pre_inn2", "revised"),
        "striker_balls": v.get("striker_balls"), "field_restr": v.get("field_restr"),
        "bat_home": v.get("bat_home_status"), "bowl_home": v.get("bowl_home_status"), "start_slot": v.get("start_slot"),
        "bowl_class": pb.get("bowl_class") or "unknown", "bowl_type": pb.get("bowl_type"),
        "bat_hand": ps.get("bat_hand") or "U",
        "striker_overseas": overseas(ps), "bowler_overseas": overseas(pb) if bw is not None else None,
        "region": venue.get("region"), "ball_brand": venue.get("ball_brand") if fam == "TEST" else None,
        "elevation": venue.get("elevation_m"), "ball_age_overs": v.get("ball_age_overs"),
        "second_new_ball": v.get("second_new_ball"), "est_day": v.get("est_day"),
        "scheduled_days": v.get("scheduled_days"), "overs_into_day": v.get("overs_into_day"),
        "exp_overs_left": v.get("exp_overs_left"), "lead": v.get("lead"),
        "striker_exp": cs.get("exp_bat") or 0, "bowler_exp": (cb.get("exp_bowl") or 0) if bw is not None else None,
        "striker_role_pos": role if role is not None else v.get("striker_arrival"), "depth": depth,
        "free_hit": fh, "free_hit_p": 1.0 if fh is True else 0.0 if fh is False else float(v.get("free_hit_p") or 0.0),
        "is_noball": v.get("dtype") == "noball", "drs": v.get("drs_enabled"),
        "year": int(str(v["date"])[:4]) if v.get("date") else None,
        "temp": wx.get("temp_c"), "rh": wx.get("rh"), "cloud": wx.get("cloud_oktas"),
        "precip": wx.get("wet_day", wx.get("rain_risk")), "dew_dep": wx.get("dew_depression_evening"),
        "_st": st, "_ns": ns, "_bw": bw, "_venue": v.get("venue_id"), "_competition": v.get("competition_id"),
        "_season": season_from_view(v, lookups), "_gender": v.get("gender"), "_ub": v.get("bowl_end_umpire"),
        "_ums": v.get("umpires"), "_ump_p": v.get("bowl_end_umpire_p"),
    }


def _bool(x):
    return None if x is None else bool(x)


def factor_scalar(spec: dict, name: str, f: dict, fit_fam: str, gender: str, lk: dict, res: dict | None) -> int:
    d = spec["factors"][name]
    t = d["type"]
    if t == "id":
        return _id_scalar(d["id"], f, lk)
    if t == "categorical":
        x = f[d["field"]]
        if "levels_by_fit_family" in d:
            tg = d["levels_by_fit_family"][fit_fam]
            return tg.index(x) if x in tg else -1
        return d["map"].get(x, d.get("null_level", -1)) if x is not None else d.get("null_level", -1)
    if t == "clip":
        x = f[d["field"]]
        return -1 if x is None else min(max(int(x), d["lo"]), d["hi"]) - d["lo"]
    if t == "buckets":
        x = f[d["field"]]
        if x is None:
            return -1
        return sum(1 for c in d["cuts"] if (c < x if d.get("side") == "right" else c <= x))
    if t == "bool":
        x = _bool(f[d["field"]])
        return -1 if x is None else int(x)
    if t == "ratio_buckets":
        if f["super_over"]:
            return d["super_over_level"]
        den, num = f[d["den"]], f[d["num"]]
        if den is None:
            return d["den_null_level"]
        if num is None:
            return -1
        cuts = d["cuts"] if "cuts" in d else d["cuts_by_fam"].get(f["fam"], [])
        return sum(1 for a, b in cuts if b * num >= a * den)
    if t == "builtin" and d["name"] == "resource_ratio":
        rr, u, w = f["runs_required"], f["balls_remaining"], f["wkts"]
        args = _resource_args(f["fam"], gender, res or load_resource())
        if args is None or rr is None or u is None or w is None:
            return -1
        P, N, g100 = args
        p = int(P[min(max(int(u), 0), N), min(max(int(w), 0), 10)])
        return sum(1 for c in d["cuts100"] if 10**7 * int(rr) >= c * p * g100)
    if t == "builtin" and d["name"] == "runs_per_over_left":
        rr, eol = f["runs_required"], f["exp_overs_left"]
        if rr is None or eol is None:
            return -1
        return sum(1 for c in d["cuts"] if float(rr) >= c * float(eol))
    raise ValueError(f"unknown factor {name!r}")


def _id_scalar(kind: str, f: dict, lk: dict) -> int:
    idx = (lk.get("ids") or {}).get(kind) or {}
    if kind in ("match", "match_innings"):
        return 0
    if kind == "batter":
        lab = f["_st"]
    elif kind == "bowler":
        lab = f["_bw"]
    elif kind == "venue":
        lab = f["_venue"]
    elif kind == "competition":
        lab = f["_competition"]
    elif kind == "season":
        lab = f["_season"]
    elif kind == "era":
        lab = f"{f['fam']}|{f['year']}"
        if lab not in idx and f["year"] is not None:
            years = [int(s.split("|")[1]) for s in idx if s.split("|")[0] == f["fam"] and int(s.split("|")[1]) < f["year"]]
            lab = f"{f['fam']}|{max(years)}" if years else None
    else:
        raise ValueError(kind)
    return idx.get(lab, -1) if lab is not None else -1


def _cond_scalar(f: dict, clauses: list) -> bool:
    for c in clauses:
        x, op, val = f[c["field"]], c["op"], c.get("value")
        if isinstance(val, bool) or isinstance(x, (bool, np.bool_)):
            x = _bool(x)
        if op == "notnull":
            ok = x is not None
        elif x is None:
            ok = False
        elif op == "eq":
            ok = x == val
        elif op == "ne":
            ok = x != val
        elif op == "in":
            ok = x in val
        elif op == "ge":
            ok = x >= val
        elif op == "le":
            ok = x <= val
        else:
            raise ValueError(op)
        if not ok:
            return False
    return True


def weight_scalar(spec: dict, name: str, f: dict, fit_fam: str) -> float:
    bc, test = f["bowl_class"], f["fam"] == "TEST"
    if name == "is_spin":
        return 1.0 if bc == "spin" else 0.0
    if name == "is_pace":
        return 1.0 if bc == "pace" else 0.0
    if name == "spin_sign":
        return 1.0 if bc == "spin" else -1.0 if bc == "pace" else 0.0
    if name == "is_death":
        return 1.0 if not test and factor_scalar(spec, "phase3", f, fit_fam, "", {}, None) == 2 else 0.0
    if name == "newball":
        if test:
            a = f["ball_age_overs"]
            return 1.0 if a is not None and a <= 15 else 0.0
        return 1.0 if factor_scalar(spec, "phase3", f, fit_fam, "", {}, None) == 0 else 0.0
    if name == "first10":
        x = f["striker_balls"]
        return 1.0 if x is not None and x < 10 else 0.0
    if name == "wear":
        s, d = f["scheduled_days"], f["est_day"]
        if not test or s is None or d is None or s <= 1:
            return 0.0
        return (min(float(d), float(s)) - 1) / (float(s) - 1)
    if name == "free_hit_p":
        return float(f["free_hit_p"])
    raise ValueError(f"unknown weight {name!r}")


def fit_family_of(spec: dict, fam: str) -> str:
    return next(k for k, v in spec["fit_families"].items() if fam in v)


def levels_from_view(view: dict, spec: dict, lookups: dict, model: str | None = None, res: dict | None = None) -> dict:
    """Group levels, weights, dense values and masked classes of `model` for one pre-ball view:
    {'groups': {name: (level, weight, level2, weight2)}, 'dense': [...], 'mask': [classes]}; without
    `model`, {model: that} for every model (lookups may then hold per-model parts under 'models').

    lookups: players {id: bat_hand, bowl_type, bowl_class, country}, player_ctx {id: exp_bat, exp_bowl,
    role_pos} (bundle exp_balls_bat / exp_balls_bowl / role_pos), venues {id: region, country, elevation_m,
    ball_brand}, competitions {id: club}, seasons {competition: [[first_date, season_key], ...]},
    optional climatology {venue: {month: weather}}, and the model's ids {factor: {label: index}} and
    standardize {field: [mean, sd]} (`model_lookups`). Latent groups (match, innings) return level 0 when
    they apply; their values come from view['latent']."""
    f = view_fields(view, lookups)
    if model is not None:
        return levels_from_fields(f, spec, lookups, model, res)
    per = lookups.get("models") or {}
    return {m: levels_from_fields(f, spec, {**lookups, **(per.get(m) or {})}, m, res) for m in spec["models"]}


def levels_from_fields(f: dict, spec: dict, lookups: dict, model: str, res: dict | None = None) -> dict:
    """levels_from_view on canonical fields (view_fields output)."""
    fit_fam = fit_family_of(spec, f["fam"])
    gender = f.get("_gender") or "male"
    ids = lookups.get("ids") or {}
    out = {}
    for g in model_groups(spec, model, fit_fam):
        if g.get("two_index"):
            uidx = ids.get("umpire") or {}
            ok = _cond_scalar(f, g.get("when", []))
            ub, ums = f.get("_ub"), f.get("_ums")
            if ub is not None:
                i1, w1, i2, w2 = uidx.get(ub, -1), 1.0, -1, 0.0
            elif ums:
                p = f.get("_ump_p")
                p = 0.5 if p is None else float(p)
                i1, w1, i2, w2 = uidx.get(ums[0], -1), p, uidx.get(ums[1], -1), 1.0 - p
            else:
                i1, w1, i2, w2 = -1, 0.0, -1, 0.0
            out[g["name"]] = (i1 if ok and w1 != 0 else -1, w1, i2 if ok and w2 != 0 else -1, w2)
            continue
        lev = 0
        for name in g["factors"]:
            x = factor_scalar(spec, name, f, fit_fam, gender, lookups, res)
            k = 1 if g.get("latent") else factor_size_scalar(spec, name, fit_fam, ids)
            lev = -1 if lev < 0 or x < 0 else lev * k + x
        if g.get("when") and not _cond_scalar(f, g["when"]):
            lev = -1
        w = 1.0
        if g.get("weight"):
            w = weight_scalar(spec, g["weight"], f, fit_fam)
            if w == 0:
                lev = -1
        out[g["name"]] = (lev, w, -1, 0.0)
    dense = []
    st = lookups.get("standardize") or {}
    for d in dense_columns(spec, model, fit_fam):
        x = f[d["field"]]
        mu, sd = st.get(d["field"], (0.0, 1.0))
        z = 0.0 if x is None else (float(x) - mu) / sd
        if z != z:
            z = 0.0
        z = z * float(d.get("sign", 1))
        if d.get("times"):
            z = z * weight_scalar(spec, d["times"], f, fit_fam)
        if d.get("when") and not _cond_scalar(f, d["when"]):
            z = 0.0
        dense.append(z)
    masks = [mk["class"] for mk in spec["models"][model]["masks"] if any(_cond_scalar(f, [c]) for c in mk["any"])]
    return {"groups": out, "dense": dense, "mask": masks}


def eta_from_levels(lv: dict, params: dict, spec: dict, model: str, latent: dict | None = None) -> list[float]:
    """Full eta (class 0 = 0) of one row from levels_from_view output and glm-style parameters
    {'intercept': (K-1,), group name: (n_levels, d), 'dense': (p, K-1)}; a latent group uses latent[name]
    (length d) in place of a level row; masked classes get glm.MASK_OFFSET. Float64, class by class."""
    k1 = len(spec["classes"][spec["models"][model]["classes"]]) - 1
    eta = [float(x) for x in params["intercept"]]
    latent = latent or {}
    for g in spec["models"][model]["groups"]:
        name = g["name"]
        if name not in lv["groups"]:
            continue
        i1, w1, i2, w2 = lv["groups"][name]
        basis = basis_matrix(spec, model, g.get("basis"))
        for idx, w in ((i1, w1), (i2, w2)):
            if idx < 0:
                continue
            row = latent.get(name) if g.get("latent") else params[name][idx]
            if row is None:
                continue
            row = [float(x) for x in row]
            if basis is None:
                for k in range(k1):
                    eta[k] += w * row[k]
            else:
                for k in range(k1):
                    eta[k] += w * sum(row[j] * float(basis[j][k]) for j in range(len(row)))
    if lv["dense"]:
        C = params["dense"]
        for k in range(k1):
            eta[k] += sum(float(x) * float(C[j][k]) for j, x in enumerate(lv["dense"]))
    for c in lv["mask"]:
        eta[c - 1] += glm.MASK_OFFSET
    return [0.0] + eta


def factor_size_scalar(spec: dict, name: str, fit_fam: str, ids: dict) -> int:
    d = spec["factors"][name]
    if d["type"] == "id":
        return len(ids.get(d["id"]) or {})
    return factor_size(spec, name, fit_fam)


# ---------------------------------------------------------------- enriched rows -> views

def static_lookups(spec: dict | None = None) -> dict:
    """Player, venue, competition and season lookups from the processed tables (labels: registry ids)."""
    pl = IG.read_table(IG.OUT_DIR / "players.parquet", columns=["player_id", "bat_hand", "bowl_type", "bowl_class",
                                                                 "country"])
    players = {r.player_id: {"bat_hand": r.bat_hand, "bowl_type": r.bowl_type, "bowl_class": r.bowl_class,
                             "country": r.country if isinstance(r.country, str) else None}
               for r in pl.itertuples(index=False)}
    m = IG.read_table(MATCHES_PATH, columns=["match_id", "start_date", "venue_id", "region", "venue_country",
                                             "elevation_m", "ball_brand", "fit_fam", "competition_id",
                                             "season_key", "team_type"])
    venues = {}
    for r in m.itertuples(index=False):
        v = venues.setdefault(r.venue_id, {"region": r.region, "country": r.venue_country,
                                           "elevation_m": None if pd.isna(r.elevation_m) else float(r.elevation_m),
                                           "ball_brand": None})
        if r.fit_fam == "TEST" and isinstance(r.ball_brand, str):
            v["ball_brand"] = r.ball_brand
    comps = {c: {"club": bool((g.team_type == "club").all())} for c, g in m.groupby("competition_id")}
    first = m.groupby(["competition_id", "season_key"]).start_date.min().reset_index().sort_values(
        ["competition_id", "start_date", "season_key"])
    seasons = {c: [[d, s] for d, s in zip(g.start_date, g.season_key)] for c, g in first.groupby("competition_id")}
    return {"players": players, "venues": venues, "competitions": comps, "seasons": seasons}


def _num(x):
    if x is None:
        return None
    x = float(x)
    if x != x:
        return None
    return int(x) if x.is_integer() else x


def _int(x):
    x = _num(x)
    return None if x is None else int(x)


def views_from_rows(sl: Slice, rows, base: dict | None = None, spec: dict | None = None) -> list[tuple[dict, dict]]:
    """(view, lookups) per enriched row: views with the provider.VIEW_KEYS the table supports (training
    extras season_key, bowl_end_umpire_p, free_hit_p) and per-match lookups (base static lookups plus the
    match's player context: exp as of the match, as-of role positions, venue and competition)."""
    if sl.cands is None:
        raise ValueError("load the slice with full=True")
    spec = spec or load_spec()
    base = base or static_lookups(spec)
    b, m, ident = sl.b, sl.m, sl.ident
    lv = _cat_levels(spec)

    def cat(name, i):
        c = int(b[name][i])
        return lv[name][c] if c >= 0 else None
    per_match, out = {}, []
    rows = np.asarray(rows)
    by_match = {}
    for (km, _), (order, _, rp) in sl.cands.items():
        by_match.setdefault(km, []).append((order, rp))
    for i in rows:
        mi = int(b["mi"][i])
        r = m.iloc[mi]
        mid = int(r.match_id)
        if mid not in per_match:
            sel = np.flatnonzero(b["mi"] == mi)
            ctx = {}
            for j in sel:
                ctx.setdefault(ident[b["batter_id"][j]], {})["exp_bat"] = int(b["striker_exp"][j])
                ctx.setdefault(ident[b["bowler_id"][j]], {})["exp_bowl"] = int(b["bowler_exp"][j])
            for order, rp in by_match.get(mid, []):
                for p, x in zip(order, rp):
                    ctx.setdefault(ident[p], {})["role_pos"] = None if x != x else float(x)
            for c in ctx.values():
                c.setdefault("role_pos", None)
            lk = dict(base)
            lk["player_ctx"] = ctx
            lk["venues"] = {r.venue_id: {"region": r.region, "country": r.venue_country,
                                         "elevation_m": None if pd.isna(r.elevation_m) else float(r.elevation_m),
                                         "ball_brand": r.ball_brand if isinstance(r.ball_brand, str) else None}}
            lk["competitions"] = {r.competition_id: {"club": r.team_type == "club"}}
            per_match[mid] = lk
        lk = per_match[mid]
        inn = int(b["innings"][i])
        cand = sl.cands.get((mid, inn))
        mm = max(int(b["striker_arrival"][i]), int(b["nonstriker_arrival"][i]))
        to_come = None
        if cand is not None:
            c = int(np.searchsorted(np.asarray(cand[1], np.int64), min(mm, MAX_ARR), side="right"))
            to_come = tuple(ident[p] for p in cand[0][c:])
        tk = b["target_known"][i] == 1
        fh = _bool(_num(b["free_hit"][i]))
        fam = cat("fam", i)
        u1, u2 = r.umpire1_id, r.umpire2_id
        ums = [None if pd.isna(u) else ident[int(u)] for u in (u1, u2)]
        ums = None if ums == [None, None] else ums
        hs = (r.home_status1, r.home_status2)
        v = {
            "fam": fam, "gender": sl.gender, "competition_id": r.competition_id, "date": r.start_date,
            "venue_id": r.venue_id, "neutral": r.home_status1 == "neutral", "start_slot": cat("start_slot", i),
            "weather": {"temp_c": _num(b["temp"][i]), "rh": _num(b["rh"][i]), "cloud_oktas": _num(b["cloud"][i]),
                        "dew_depression_evening": _num(b["dew_dep"][i]), "wet_day": _num(b["precip"][i])},
            "umpires": ums, "rules": None, "drs_enabled": _bool(_num(b["drs"][i])),
            "sched_balls": _int(r.scheduled_balls) if fam != "TEST" else None,
            "scheduled_days": _int(r.scheduled_days), "teams": (r.team1, r.team2),
            "home": (hs[0] == "home", hs[1] == "home"), "prep": None, "toss_winner": None,
            "innings": inn, "super_over": 0, "so_innings": 0, "bat_team": None, "bowl_team": None,
            "bat_home_status": cat("bat_home", i), "bowl_home_status": cat("bowl_home", i),
            "target_timing": cat("target_timing", i) if tk else None, "followed_on": None, "prev_innings": None,
            "umpire_offset": None, "latent": None,
            "legal_balls": _int(b["legal_ball_index"][i]), "ball_in_over": _int(b["ball_in_over"][i]),
            "over": _int(b["over"][i]), "max_balls": _int(b["max_balls"][i]),
            "balls_remaining": _int(b["balls_remaining"][i]), "runs": _int(b["inn_runs"][i]),
            "wkts": _int(b["wkts"][i]), "unavailable": _int(b["inn_unavailable"][i]),
            "target": _int(b["target_runs"][i]) if tk else None,
            "runs_required": _int(b["runs_required"][i]) if tk else None,
            "striker": ident[b["batter_id"][i]], "nonstriker": ident[b["non_striker_id"][i]],
            "bowler": ident[b["bowler_id"][i]],
            "striker_runs": _int(b["striker_runs"][i]), "striker_balls": _int(b["striker_balls"][i]),
            "nonstriker_runs": _int(b["nonstriker_runs"][i]), "nonstriker_balls": _int(b["nonstriker_balls"][i]),
            "striker_arrival": _int(b["striker_arrival"][i]), "nonstriker_arrival": _int(b["nonstriker_arrival"][i]),
            "striker_pos": None, "nonstriker_pos": None,
            "bowler_balls": _int(b["bowler_balls_inn"][i]), "bowler_runs": None, "bowler_wkts": None,
            "bowler_overs": None, "bowler_spell": _int(b["bowler_spell_overs"][i]), "bowler_part_timer": False,
            "partnership_runs": _int(b["partnership_runs"][i]), "partnership_balls": _int(b["partnership_balls"][i]),
            "free_hit": fh, "pp_window": cat("pp_window", i), "field_restr": _int(b["field_restr"][i]),
            "reviews_bat": _int(b["bat_reviews_left"][i]), "reviews_bowl": _int(b["bowl_reviews_left"][i]),
            "bat_fail_reviews": _int(b["bat_fail_reviews"][i]), "bowl_fail_reviews": _int(b["bowl_fail_reviews"][i]),
            "ball_age_overs": _int(b["ball_age_overs"][i]), "second_new_ball": _bool(_num(b["second_new_ball"][i])),
            "innings_overs": _int(b["over"][i]), "match_legal_balls": _int(b["match_legal_balls"][i]),
            "clock_used": None, "est_day": _int(b["est_day"][i]),
            "overs_into_day": None if np.isnan(b["est_overs_into_day"][i]) else int(math.floor(b["est_overs_into_day"][i])),
            "exp_overs_left": _num(b["exp_overs_left"][i]) if not np.isnan(b["exp_overs_left"][i]) else None,
            "lead": _int(b["lead"][i]), "striker_form": None, "nonstriker_form": None, "bowler_form": None,
            "bowl_end_umpire": None, "to_come": to_come,
            "last_over_runs": None, "last_over_wkt": None, "dtype": cat("dtype", i),
            # training extras (required view additions, see the spec)
            "season_key": r.season_key, "bowl_end_umpire_p": _float(b["bowl_end_umpire_p"][i]),
            "free_hit_p": _float(b["free_hit_p"][i]),
        }
        if v["exp_overs_left"] is not None:
            v["exp_overs_left"] = float(b["exp_overs_left"][i])
        out.append((v, lk))
    return out


def _float(x):
    x = float(x)
    return None if x != x else x


# ---------------------------------------------------------------- parity of the two paths

def parity(sl: Slice, rows, spec: dict | None = None, models=("dtype", "outcome", "wk"), base: dict | None = None,
           res: dict | None = None) -> dict:
    """Compare vectorized group levels / weights / dense / masks with levels_from_view on `rows` of a full
    slice, for every model's groups (all rows, regardless of the model's row filter). Returns counts and
    the first mismatches."""
    spec = spec or load_spec()
    res = res or load_resource()
    rows = np.asarray(rows)
    F = VecFields(sl, spec, rows)
    ids = build_ids(F)
    views = views_from_rows(sl, rows, base, spec)
    rep = {"rows": int(len(rows)), "checks": 0, "mismatches": 0, "examples": [], "by_group": {}}
    for model in models:
        stats = dense_stats(spec, model, F)
        lk_model = {"ids": {k: dict(v["index"]) for k, v in ids.items()}, "standardize": stats}
        vec = {g["name"]: (g, group_levels(spec, g, F, ids, res)) for g in model_groups(spec, model, sl.fit_fam)}
        dv = dense_vec(spec, model, F, stats) if dense_columns(spec, model, sl.fit_fam) else None
        mv = mask_vec(spec, model, F)
        for j, (view, lk) in enumerate(views):
            s = levels_from_view(view, spec, {**lk, **lk_model}, model, res)
            for name, (g, lv) in vec.items():
                i1 = int(lv["index"][j])
                w1 = 1.0 if lv["weight"] is None else float(lv["weight"][j])
                i2 = -1 if lv["index2"] is None else int(lv["index2"][j])
                w2 = 0.0 if lv["weight2"] is None else float(lv["weight2"][j])
                if g.get("latent"):
                    i1 = 0 if i1 >= 0 else -1
                got = s["groups"][name]
                ok = (got[0] == i1) and (i1 < 0 or got[1] == w1) and (got[2] == i2) and (i2 < 0 or got[3] == w2)
                rep["checks"] += 1
                bg = rep["by_group"].setdefault(f"{model}.{name}", [0, 0])
                bg[0] += 1
                if not ok:
                    bg[1] += 1
                    rep["mismatches"] += 1
                    if len(rep["examples"]) < 20:
                        rep["examples"].append({"model": model, "group": name, "row": int(rows[j]),
                                                "vec": [i1, w1, i2, w2], "scalar": list(got)})
            if dv is not None:
                rep["checks"] += 1
                if not np.array_equal(np.asarray(s["dense"]), dv[j]):
                    rep["mismatches"] += 1
                    if len(rep["examples"]) < 20:
                        rep["examples"].append({"model": model, "group": "dense", "row": int(rows[j]),
                                                "vec": dv[j].tolist(), "scalar": s["dense"]})
            rep["checks"] += 1
            want = [k for hit, k in mv if hit[j]]
            if want != s["mask"]:
                rep["mismatches"] += 1
                if len(rep["examples"]) < 20:
                    rep["examples"].append({"model": model, "group": "mask", "row": int(rows[j]),
                                            "vec": want, "scalar": s["mask"]})
    rep["by_group"] = {k: v for k, v in rep["by_group"].items() if v[1]} or "all agree"
    return rep


# ---------------------------------------------------------------- summary report

REPORT_NOTES = {
    "half_life": "build_design takes the half-life in years; age in days from the match start, w = 0.5 ** (age / (365.25 * hl))",
    "cutoff_rule": "a match enters only when its last played date is before the cutoff (stricter than its start date)",
    "labels": "players and umpires are labelled by Cricsheet registry identifier (people_index.identifier); engines pass those ids",
    "outcome_label": "onfield_class where drs_available is true, else the recorded outcome_class; wides leave the outcome and wk fits",
    "masks": "class 6 masked on no-balls and certain free hits; 6,969 uncertain free hits (front-foot era) are unmasked and "
             "carry o_free_hit with weight free_hit_p; no recorded class-6 out falls on a masked row",
    "retirements": "the ball table has no retirement-only rows (retirements are events), so that exclusion is empty",
    "phase": "phase6/phase3 use elapsed = max_balls - balls_remaining (the ingest's over-position count); equal to legal balls "
             "in the engines; Tests have one phase level, so set x phase3 is set alone there",
    "ball_age": "training ball_age_overs / second_new_ball are the ingest's over % 80 / over >= 80; engines use the simulated take-up",
    "newball": "bat_newball / bowl_newball weight: limited overs phase3 == 0 (first powerplay span), Tests ball age <= 15 overs",
    "depth": "realized later batting order gives the fallback rank of players without a role history; replaced-out "
             "non-batters dropped from the replacement innings on",
    "season": "views without season_key use the competition's latest season started by the date (144 of 23,132 matches differ)",
    "nested": "nested groups are additive under their parent (glm has no parent link); parents are kept in design.meta",
    "dtype_umpire": "the bowler's-end umpire on dtype applies to both wide and no-ball classes",
    "wk_free_hit": "the plan's 'free-hit/no-ball, masked to none' wk term is not a group: class-6 outs never occur on those rows",
}


def _rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024
    return float("nan")


def summary(cutoff: str = "2023-01-01", half_life: float = 3.0, parity_n: int = 6000, seed: int = 7) -> dict:
    """Rows per (family, gender, model) after decay, level counts per group, the men's T20 design
    memory and build time with glm preparation, and a real-ball parity check across families."""
    import gc
    spec, res = load_spec(), load_resource()
    fam_names = spec["fields"]["fam"]["levels"]
    rep = {"spec_version": spec["version"], "cutoff": cutoff, "half_life_years": half_life,
           "min_weight": spec["design"]["min_weight"], "slices": {}, "parity": {}}
    base = static_lookups(spec)
    for fit_fam in spec["fit_families"]:
        for gender in ("male", "female"):
            t0 = time.time()
            sl = load_slice(fit_fam, gender, spec=spec, candidates=False)
            out = {"balls": sl.n, "matches": int(len(sl.m)), "load_seconds": round(time.time() - t0, 1),
                   "depth_null": int(np.isnan(sl.b["depth"]).sum()), "models": {}}
            for model in spec["models"]:
                rss0 = _rss_mb()
                t1 = time.time()
                d = build_design(sl, model, cutoff, half_life, spec, res)
                mo = {"rows": d.meta["rows"], "weight_sum": round(d.meta["weight_sum"], 1),
                      "class_counts": np.bincount(d.y, minlength=d.n_classes).tolist(),
                      "build_seconds": round(time.time() - t1, 1), "design_mb": round(design_nbytes(d) / 2**20, 1),
                      "rss_growth_mb": round(_rss_mb() - rss0, 1),
                      "rows_by_fam": {f: int(c) for f, c in zip(fam_names, np.bincount(sl.b["fam"][d.meta["row_index"]],
                                                                                   minlength=4)) if c},
                      "masked_rows": {str(k): int(r.sum()) for r, k in d.masks},
                      "standardize": d.meta["standardize"],
                      "groups": {k: {x: v[x] for x in ("n_levels", "n_used", "rows", "level_rows") if v[x] is not None}
                                 for k, v in d.meta["groups"].items()}}
                if fit_fam == "T20" and gender == "male" and model == "outcome":
                    t2 = time.time()
                    prep = glm._Prepared(d)
                    nnz = sum((c.full.nnz if c.full is not None else 0) + sum(m.nnz for m, _ in c.basis)
                              for c in prep.chunks)
                    pb = sum((c.full.data.nbytes + c.full.indices.nbytes + c.full.indptr.nbytes if c.full is not None else 0)
                             + sum(m.data.nbytes + m.indices.nbytes + m.indptr.nbytes for m, _ in c.basis)
                             for c in prep.chunks)
                    mo["glm_prepare"] = {"seconds": round(time.time() - t2, 1), "nnz": int(nnz),
                                         "matrices_mb": round(pb / 2**20, 1), "n_params": int(prep.layout.size),
                                         "rss_after_mb": round(_rss_mb(), 1),
                                         "design_plus_prepared_mb": round((design_nbytes(d) + pb) / 2**20, 1)}
                    del prep
                out["models"][model] = mo
                del d
                gc.collect()
            rng = np.random.default_rng(seed)
            mids = sl.m.match_id.to_numpy()
            pick = rng.choice(mids, size=min(len(mids), 40), replace=False)
            del sl
            gc.collect()
            sub = load_slice(fit_fam, gender, pick, full=True, spec=spec)
            n = min(sub.n, max(1, parity_n // 6))
            rows = np.sort(rng.choice(sub.n, size=n, replace=False))
            p = parity(sub, rows, spec, base=base, res=res)
            rep["parity"][f"{fit_fam}-{gender}"] = {k: p[k] for k in ("rows", "checks", "mismatches", "by_group", "examples")}
            out["total_seconds"] = round(time.time() - t0, 1)
            rep["slices"][f"{fit_fam}-{gender}"] = out
            del sub
            gc.collect()
            print(fit_fam, gender, json.dumps({k: v["rows"] for k, v in out["models"].items()}), flush=True)
    import resource
    rep["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    rep["required_view_additions"] = spec["required_view_additions"]
    rep["notes"] = REPORT_NOTES
    rep["parity_total"] = {"rows": sum(v["rows"] for v in rep["parity"].values()),
                           "checks": sum(v["checks"] for v in rep["parity"].values()),
                           "mismatches": sum(v["mismatches"] for v in rep["parity"].values())}
    return rep


def main():
    rep = summary()
    REPORT_PATH.write_text(json.dumps(rep, indent=1, default=str) + "\n")
    print(json.dumps(rep["parity_total"]))


if __name__ == "__main__":
    main()
