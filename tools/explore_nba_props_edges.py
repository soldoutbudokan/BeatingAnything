#!/usr/bin/env python3
"""NBA player-points props ~12h before tip: star-absence teammate Overs and a consensus/under-bias model.

python tools/explore_nba_props_edges.py
Needs git and network on first run: clones the pinned public prop archive (11 US books, main and
alternate points lines, box scores) and fetches only the official injury-report PDFs issued just
before each price snapshot. Writes reports/nba-props-edges-2026-09-22.json. No wagers.
"""
# %% setup
import glob
import json
import re
import subprocess
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nba-props-edges"
ARCHIVE = RAW / "nba-props-threshold-app"
ARCHIVE_COMMIT = "233dbbc86b9c6e13df04d4e8b063581b3aa15abb"
INJ_REPO, INJ_COMMIT = "akng8/nba-injury-scraper", "02cfe44f7453182eb4a29283285a7af64f5e3c9a"
PDFS = RAW / "injury-pdfs"
OUT = ROOT / "reports/nba-props-edges-2026-09-22.json"
US_BOOKS = ["fanduel", "draftkings", "betmgm", "williamhill_us", "betrivers", "fanatics"]
ALIAS = {"nicolasclaxton": "nicclaxton", "carltoncarrington": "bubcarrington", "herbjones": "herbertjones",
         "ronholland": "ronaldholland", "vincentwilliams": "vincewilliams"}


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    s = re.sub("[^a-z]", "", s)
    return ALIAS.get(s, s)


def season_of(t):
    return np.where(t < pd.Timestamp("2024-08-01", tz="UTC"), "2023-24",
                    np.where(t < pd.Timestamp("2025-08-01", tz="UTC"), "2024-25", "2025-26"))


RAW.mkdir(parents=True, exist_ok=True)
if not ARCHIVE.exists():
    subprocess.run(["git", "clone", "https://github.com/devlincorrigan/nba-props-threshold-app.git", str(ARCHIVE)], check=True)
    subprocess.run(["git", "-C", str(ARCHIVE), "checkout", ARCHIVE_COMMIT], check=True)
head = subprocess.run(["git", "-C", str(ARCHIVE), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert head == ARCHIVE_COMMIT, f"archive at {head}, expected {ARCHIVE_COMMIT}"

# %% flatten main-line prices (one Over/Under pair per book-player, the most balanced if several)
rows = []
for f in sorted(glob.glob(str(ARCHIVE / "data/historical_points/*.json"))):
    d = json.load(open(f))
    e = d["data"]
    for b in e["bookmakers"]:
        for m in b["markets"]:
            if m["key"] != "player_points":
                continue
            for o in m["outcomes"]:
                rows.append((e["id"], d["timestamp"], e["commence_time"], b["key"], o.get("description"), o["name"], o.get("point"), o["price"]))
P = pd.DataFrame(rows, columns=["event_id", "snap", "commence", "book", "player", "side", "point", "price"])
P["snap"], P["commence"] = pd.to_datetime(P.snap), pd.to_datetime(P.commence)
M = P.pivot_table(index=["event_id", "snap", "commence", "book", "player", "point"], columns="side", values="price", aggfunc="first").reset_index().dropna(subset=["Over", "Under"])
M["imbalance"] = (1 / M.Over - 1 / M.Under).abs()
M = M.sort_values("imbalance").drop_duplicates(["event_id", "book", "player"]).drop(columns="imbalance")

# %% outcomes from the archive's box scores; props on players who did not play are void and dropped
box = pd.read_csv(ARCHIVE / "data/box_scores/player_stats.csv")
box["gameDate"] = pd.to_datetime(box.gameDate)
box["key"] = (box.firstName.fillna("") + " " + box.familyName.fillna("")).map(norm_name)
box["played"] = box.minutesFloat.fillna(0) > 0
mp = pd.read_csv(ARCHIVE / "data/game_event_bijection.csv")
M = M.merge(mp, on="event_id")
M["key"] = M.player.map(norm_name)
b1 = box[["gameId", "key", "personId", "teamTricode", "points", "played"]].drop_duplicates(["gameId", "key"])
M = M.merge(b1, left_on=["game_id", "key"], right_on=["gameId", "key"])
M = M[M.played & (M.points != M.point)].copy()
M["season"] = season_of(M.commence)
M["over_win"] = (M.points > M.point).astype(int)
M["nv_over"] = (1 / M.Over) / (1 / M.Over + 1 / M.Under)
M["ret_over"] = np.where(M.over_win == 1, M.Over - 1, -1.0)
M["ret_under"] = np.where(M.over_win == 0, M.Under - 1, -1.0)
print("settled book-player rows", len(M), "player-games", M[["event_id", "player"]].drop_duplicates().shape[0])

# %% star table: season-to-date average from prior games only; absence and previous-game status
tg = box[["season", "gameId", "gameDate", "teamTricode"]].drop_duplicates().sort_values(["teamTricode", "gameDate"])
tg["tseq"] = tg.groupby(["season", "teamTricode"]).cumcount()
s = box.merge(tg[["gameId", "teamTricode", "tseq"]], on=["gameId", "teamTricode"]).sort_values(["personId", "season", "tseq"])
s["pts_played"], s["n_played"] = np.where(s.played, s.points, 0), s.played.astype(int)
grp = s.groupby(["season", "personId"])
s["n_before"] = grp.n_played.cumsum() - s.n_played
s["avg_before"] = (grp.pts_played.cumsum() - s.pts_played) / s.n_before.replace(0, np.nan)
s["prev_played"] = grp.played.shift(1)
s.loc[grp.tseq.shift(1) != s.tseq - 1, "prev_played"] = np.nan
stars = s[(s.avg_before >= 20) & (s.n_before >= 8)].copy()
stars["fresh"] = stars.prev_played == True  # noqa: E712 (NaN means not on the previous roster)


def summary(x):
    pg = x.drop_duplicates(["event_id", "player"])
    tgames = x[["game_id", "teamTricode"]].drop_duplicates().shape[0]
    # Team-game clustered SE: teammates' Overs move together.
    c = x.groupby(["game_id", "teamTricode"]).ret_over.agg(["sum", "size"])
    se_cl = np.sqrt(((c["sum"] - c["size"] * x.ret_over.mean()) ** 2).sum()) / len(x) if len(c) > 1 else np.nan
    return {"book_rows": len(x), "player_games": len(pg), "team_games": tgames, "no_vig_over": round(x.nv_over.mean(), 4),
            "over_hit": round(x.over_win.mean(), 4), "roi_over": round(x.ret_over.mean(), 4), "se_clustered": round(se_cl, 4),
            "roi_under": round(x.ret_under.mean(), 4)}


# %% (1) ex-post: teammates of a star who sat (known only after the fact; not a tradable trigger by itself)
st = stars.assign(cls=np.select([~stars.played & stars.fresh, ~stars.played & (stars.prev_played == False), stars.played & (stars.prev_played == False)],  # noqa: E712
                                ["star out, first game", "star out, continuing", "star returns"], "none"))
rank = {"star out, first game": 0, "star out, continuing": 1, "star returns": 2, "none": 3}
team_cls = st.assign(r=st.cls.map(rank)).groupby(["gameId", "teamTricode"]).r.min().map({v: k for k, v in rank.items()})
M["expost"] = pd.MultiIndex.from_frame(M[["game_id", "teamTricode"]]).map(team_cls.to_dict()).fillna("no 20-ppg star")
expost = {c: summary(x) for c, x in M.groupby("expost")}
expost_by_season = {f"{c} | {se}": summary(x) for (c, se), x in M[M.expost.str.startswith("star")].groupby(["expost", "season"])}
print(pd.DataFrame(expost).T.to_string())

# %% (2) ex-ante: official injury report issued >=1h before the price snapshot (filename hour, ET)
tree = RAW / "injury-files.txt"
if not tree.exists():  # file names only; a blobless clone avoids downloading every PDF
    clone = RAW / "inj-tree"
    subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", f"https://github.com/{INJ_REPO}.git", str(clone)], check=True)
    tree.write_text(subprocess.run(["git", "-C", str(clone), "ls-tree", "-r", "--name-only", INJ_COMMIT], capture_output=True, text=True, check=True).stdout)
rep = []
for line in tree.read_text().split():
    m = re.search(r"Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})(AM|PM)\.pdf", line)
    if m:
        rep.append((line, pd.Timestamp(m[1]) + pd.Timedelta(hours=int(m[2]) % 12 + (12 if m[3] == "PM" else 0))))
R = pd.DataFrame(rep, columns=["path", "t_et"]).sort_values("t_et").reset_index(drop=True)
ev = M.drop_duplicates("event_id")[["event_id", "snap", "game_id"]].copy()
ev["snap_et"] = ev.snap.dt.tz_convert("America/New_York").dt.tz_localize(None)
i = np.searchsorted(R.t_et.values, (ev.snap_et - pd.Timedelta(hours=1)).values, side="right") - 1
ev["path"], ev["t_et"] = R.path.values[np.clip(i, 0, None)], R.t_et.values[np.clip(i, 0, None)]
ev = ev[(i >= 0) & ((ev.snap_et - ev.t_et) <= pd.Timedelta(hours=6))]
PDFS.mkdir(parents=True, exist_ok=True)


def fetch(path):
    dest = PDFS / Path(path).name
    if not dest.exists():
        dest.write_bytes(urlopen(f"https://raw.githubusercontent.com/{INJ_REPO}/{INJ_COMMIT}/{path}", timeout=60).read())


with ThreadPoolExecutor(8) as ex:
    list(ex.map(fetch, sorted(set(ev.path))))

# %% parse reports: player status per (game date, team); teams marked NOT YET SUBMITTED are unknown, not healthy
import pdfplumber  # noqa: E402

TEAMS = {(c + n).replace(" ", ""): t for c, n, t in box[["teamCity", "teamName", "teamTricode"]].drop_duplicates().itertuples(index=False)}
STATUS = {"Out", "Doubtful", "Questionable", "Probable", "Available"}


def parse(pdf_path):
    out, nys, cur, team = [], [], None, None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").split("\n"):
                tok = line.split()
                for j, t in enumerate(tok):
                    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", t):
                        cur = t
                    elif t in TEAMS:
                        team = TEAMS[t]
                    elif t.upper().startswith("NOTYETSUBMITTED"):
                        nys.append((cur, team))
                    elif "," in t and j + 1 < len(tok) and tok[j + 1] in STATUS:
                        last, first = t.split(",", 1)
                        out.append((cur, team, norm_name(first + re.sub(r"(Jr\.?|Sr\.?|III|II|IV)$", "", last)), tok[j + 1]))
    return Path(pdf_path).name, out, nys


parsed = [parse(p) for p in sorted(PDFS.glob("*.pdf"))]
D = pd.DataFrame([(f, *r) for f, o, _ in parsed for r in o], columns=["file", "gd", "team", "key", "status"]).drop_duplicates(["file", "gd", "key"])
N = pd.DataFrame([(f, *r) for f, _, n in parsed for r in n], columns=["file", "gd", "team"]).drop_duplicates()
for x in (D, N):
    x["gd"] = pd.to_datetime(x.gd, format="%m/%d/%Y")
ev["file"] = ev.path.str.split("/").str[-1]
S = stars.merge(ev[["game_id", "file"]], left_on="gameId", right_on="game_id")
S = S.merge(D[["file", "gd", "key", "status"]], left_on=["file", "gameDate", "key"], right_on=["file", "gd", "key"], how="left")
S = S.merge(N.assign(nys=True)[["file", "gd", "team", "nys"]], left_on=["file", "gameDate", "teamTricode"], right_on=["file", "gd", "team"], how="left")
S["status"] = np.where(S.status.notna(), S.status, np.where(S.nys == True, "team not submitted", "not listed"))  # noqa: E712
star_status_vs_played = pd.crosstab(S.status, S.played).to_dict()
exante_rank = {"Out": 0, "Doubtful": 1, "Questionable": 1}
S["r"] = S.status.map(exante_rank).fillna(2)
tc = S.groupby(["gameId", "teamTricode"]).r.min().map({0: "star listed OUT", 1: "star DOUBTFUL/QUESTIONABLE", 2: "star not listed/other"})
Mx = M[M.game_id.isin(S.gameId)].copy()
Mx["exante"] = pd.MultiIndex.from_frame(Mx[["game_id", "teamTricode"]]).map(tc.to_dict()).fillna("no 20-ppg star")
exante = {c: summary(x) for c, x in Mx.groupby("exante")}
exante_by_season = {f"{c} | {se}": summary(x) for (c, se), x in Mx[Mx.exante == "star listed OUT"].groupby(["exante", "season"])}
exante_fanduel = {c: summary(x) for c, x in Mx[Mx.book == "fanduel"].groupby("exante")}
print(pd.DataFrame(exante).T.to_string())
print(pd.DataFrame(exante_by_season).T.to_string())

# %% (3) consensus model: leave-one-out median across books, calibrated shift fitted on earlier seasons only
sd_coef = np.polyfit(M.point, np.abs(M.points - M.point) * np.sqrt(np.pi / 2), 1)
sd = lambda line: np.polyval(sd_coef, line)  # noqa: E731
M["mu"] = M.point + sd(M.point) * norm.ppf(M.nv_over)
g = M.groupby(["event_id", "player"])
M["n_other"] = g.book.transform("size") - 1
M["cons_mu"] = (g.mu.transform("sum") - M.mu) / M.n_other.replace(0, np.nan)  # leave-one-out mean of implied medians
M = M[M.n_other >= 3]


def nll(th, d):
    p = np.clip(1 - norm.cdf((d.point - d.cons_mu + th[0]) / (th[1] * sd(d.point))), 1e-6, 1 - 1e-6)
    return -(d.over_win * np.log(p) + (1 - d.over_win) * np.log(1 - p)).sum()


consensus = {}
tests = []
for test, train in [("2024-25", ["2023-24"]), ("2025-26", ["2023-24", "2024-25"])]:
    th = minimize(nll, [0, 1], args=(M[M.season.isin(train)],), method="Nelder-Mead").x
    te = M[(M.season == test) & M.book.isin(US_BOOKS)].copy()
    te["pf"] = 1 - norm.cdf((te.point - te.cons_mu + th[0]) / (th[1] * sd(te.point)))
    consensus[f"fit_for_{test}"] = {"over_shift_points": round(th[0], 3), "scale": round(th[1], 3)}
    tests.append(te)
T = pd.concat(tests)
bets = pd.concat([T.assign(side="O", ev=T.pf * T.Over - 1, ret=T.ret_over), T.assign(side="U", ev=(1 - T.pf) * T.Under - 1, ret=T.ret_under)])
best = bets.sort_values("ev", ascending=False).drop_duplicates(["event_id", "player"])  # one bet per player-game at the best US book
for thr in (0.02, 0.04, 0.06, 0.08):
    b = best[best.ev > thr]
    consensus[f"ev>{thr}"] = {"bets": len(b), "pred_ev": round(b.ev.mean(), 4), "roi": round(b.ret.mean(), 4),
                              "se": round(b.ret.std() / np.sqrt(len(b)), 4), "under_share": round((b.side == "U").mean(), 3),
                              "by_season_roi": b.groupby("season").ret.mean().round(4).to_dict()}
print(json.dumps(consensus, indent=1))

# %% save
OUT.write_text(json.dumps({
    "archive": {"repo": "devlincorrigan/nba-props-threshold-app", "commit": ARCHIVE_COMMIT, "snapshot_lead": "~12h before tip"},
    "injury_reports": {"repo": INJ_REPO, "commit": INJ_COMMIT, "rule": "latest report with filename hour <= snapshot - 1h, within 6h",
                       "events_covered": int(ev.shape[0]), "star_status_vs_played": star_status_vs_played},
    "expost_star_absence": expost, "expost_by_season": expost_by_season,
    "exante_star_status": exante, "exante_star_out_by_season": exante_by_season, "exante_fanduel_only": exante_fanduel,
    "consensus_model": consensus}, indent=2, default=float) + "\n")
print("wrote", OUT.relative_to(ROOT))
