"""Conjunction constructions for theScore Bet Parlay+: legs implied by two (or three) other legs together.

Every market selection is turned into an *atom*: a predicate over a small integer outcome space (a player's rushing and
receiving yards; a team game's home and away score; a hitter's hits, home runs and bases ...). A base is two or three atoms
from different markets of the same space. The feasible outcomes of the base are enumerated exactly; any other atom that
holds on every feasible outcome is implied by the base. Stacking an implied atom on the base cannot change the winning
event, so a fair Parlay+ price for base + implied legs equals the base price. PR 4 showed theScore's engine multiplies such
legs in when a twin (ladder rung plus Over line of the same stat) is stacked; this module finds every such construction.
"""
from __future__ import annotations

import itertools
import math
import re

from beating.thescore import decimal_odds, open_selections, event_sides, mentions

PLUS_RE = re.compile(r"^(\d+(?:\.\d+)?)\+$")
SCORE_RE = re.compile(r"(\d+)\s*-\s*(\d+)$")

# ----------------------------------------------------------------------------------------------------------------------
# outcome spaces
# ----------------------------------------------------------------------------------------------------------------------
PLAYER_SPACES = {
    # space name -> (base variables with ranges, derived variables, extra constraints on base variables)
    "football_yards": dict(vars={"R": (-10, 260), "C": (-10, 260)}, derived={"S": lambda v: v["R"] + v["C"]}, constraints=[]),
    "basketball": dict(vars={"P": (0, 60), "RB": (0, 30), "AS": (0, 25)}, derived={"PRB": lambda v: v["P"] + v["RB"], "PAS": lambda v: v["P"] + v["AS"], "ASRB": lambda v: v["AS"] + v["RB"], "PRA": lambda v: v["P"] + v["RB"] + v["AS"]}, constraints=[]),
    "basketball_threes": dict(vars={"P": (0, 60), "TPM": (0, 15)}, derived={}, constraints=[lambda v: v["P"] >= 3 * v["TPM"]]),
    "baseball_bat": dict(vars={"H": (0, 6), "HR": (0, 4), "TB": (0, 24), "RBI": (0, 10)}, derived={}, constraints=[lambda v: v["HR"] <= v["H"], lambda v: v["TB"] >= v["H"] + 3 * v["HR"], lambda v: v["TB"] <= 4 * v["H"], lambda v: v["RBI"] >= v["HR"]]),
    "hockey_skater": dict(vars={"G": (0, 5), "PTS": (0, 8), "SOG": (0, 15)}, derived={}, constraints=[lambda v: v["PTS"] >= v["G"], lambda v: v["SOG"] >= v["G"]]),
}
PLAYER_STATS = {  # market suffix -> (space, variable)
    "Total Rushing Yards": ("football_yards", "R"), "Total Receiving Yards": ("football_yards", "C"), "Total Rushing + Receiving Yards": ("football_yards", "S"),
    "Total Points": ("basketball", "P"), "Total Rebounds": ("basketball", "RB"), "Total Assists": ("basketball", "AS"),
    "Total Points And Rebounds": ("basketball", "PRB"), "Total Points And Assists": ("basketball", "PAS"), "Total Assists And Rebounds": ("basketball", "ASRB"),
    "Total Points, Rebounds And Assists": ("basketball", "PRA"), "Total 3-Pointers Made": ("basketball_threes", "TPM"),
    "Total Hits": ("baseball_bat", "H"), "Total Home Runs": ("baseball_bat", "HR"), "Total Bases": ("baseball_bat", "TB"), "Total RBIs": ("baseball_bat", "RBI"),
    "Total Goals": ("hockey_skater", "G"), "Total Shots On Goal": ("hockey_skater", "SOG"),
}
# hockey 'Total Points' clashes with basketball 'Total Points'; resolved by sport below
SPORT_SPACES = {"football": {"football_yards"}, "basketball": {"basketball", "basketball_threes"}, "baseball": {"baseball_bat"}, "hockey": {"hockey_skater"}}
TEAM_RANGE = {"football": (0, 75), "basketball": (40, 160), "hockey": (0, 12), "baseball": (0, 20), "soccer": (0, 9), "rugby-league": (0, 70), "rugby-union": (0, 70), "handball": (10, 50), "australian-rules": (20, 160)}
GAME_TOTAL_NAMES = ("Total Goals", "Total Points", "Total Runs")
SPREAD_NAMES = ("Game Spread", "Run Line", "Puck Line", "2-Way Handicap")
ML_NAMES = ("Moneyline", "Match Result")


def line_bounds(sel):
    """-> (op, threshold) for an Over/Under selection on a half or whole line; whole-line pushes are excluded."""
    pts = (sel.get("points") or {}).get("decimalPoints")
    if pts is None or float(pts) == int(pts):
        return None
    if sel["type"] == "OVER":
        return (">=", math.ceil(pts))
    if sel["type"] == "UNDER":
        return ("<=", math.floor(pts))
    return None


def ladder_bound(sel):
    m = PLUS_RE.match(((sel.get("name") or {}).get("fullName") or "").strip())
    return (">=", float(m.group(1))) if m else None


class Atom:
    __slots__ = ("key", "market", "mtype", "sel", "space", "pred", "label", "decimal", "var", "op", "thr", "player")

    def __init__(self, market, sel, space, pred, label, var=None, op=None, thr=None, player=None):
        self.key = sel["id"]
        self.market = market["name"]
        self.mtype = market["type"]
        self.sel = sel
        self.space = space
        self.pred = pred
        self.label = label
        self.decimal = decimal_odds(sel)
        self.var, self.op, self.thr, self.player = var, op, thr, player

    def record(self):
        return {"market": self.market, "market_type": self.mtype, "selection": (self.sel.get("name") or {}).get("fullName"), "selection_type": self.sel.get("type"),
                "points": (self.sel.get("points") or {}).get("decimalPoints"), "price": self.sel["odds"]["formattedOdds"], "decimal": self.decimal, "id": self.sel["id"],
                "var": self.var, "op": self.op, "threshold": self.thr, "player": self.player}


def player_atoms(markets, sport):
    """Atoms keyed by (player, space)."""
    out = {}
    for m in markets:
        if m.get("status") != "OPEN":
            continue
        pm = re.match(r"^(?P<player>.+?) (?P<stat>Total .+)$", m.get("name") or "")
        if not pm or pm.group("player").startswith("Total"):
            continue
        stat = pm.group("stat")
        if sport == "hockey" and stat == "Total Points":
            space, var = "hockey_skater", "PTS"
        elif stat in PLAYER_STATS:
            space, var = PLAYER_STATS[stat]
        else:
            continue
        if space not in SPORT_SPACES.get(sport, set()):
            continue
        player = pm.group("player")
        for s in open_selections(m):
            b = ladder_bound(s) if m["type"] == "LIST" else line_bounds(s)
            if not b:
                continue
            op, thr = b
            pred = (lambda v, var=var, thr=thr: v[var] >= thr) if op == ">=" else (lambda v, var=var, thr=thr: v[var] <= thr)
            out.setdefault((player, space), []).append(Atom(m, s, space, pred, f"{player} {stat} {s['name']['fullName']}", var, op, thr, player))
    return out


def team_atoms(markets, event, sport):
    """Atoms over (H, A) for one game: spreads, totals, team totals, moneylines, soccer extras."""
    sides = event_sides(event)
    out = []

    def side_of(text, stype=None):
        if stype and stype.startswith("HOME"):
            return "H"
        if stype and stype.startswith("AWAY"):
            return "A"
        if mentions(text, sides["home"]):
            return "H"
        if mentions(text, sides["away"]):
            return "A"
        return None

    for m in markets:
        if m.get("status") != "OPEN":
            continue
        name, mtype = m.get("name") or "", m.get("type") or ""
        for s in open_selections(m):
            nm = (s.get("name") or {}).get("fullName") or ""
            pts = (s.get("points") or {}).get("decimalPoints")
            if name in SPREAD_NAMES and mtype == "SPREAD" and pts is not None and float(pts) != int(pts):
                side = side_of(nm, s["type"])
                if not side:
                    continue
                # team covers: own margin + pts > 0  ->  margin >= ceil(-pts) ... with half lines: margin > -pts
                thr = math.floor(-pts) + 1  # margin >= thr
                pred = (lambda v, thr=thr: v["H"] - v["A"] >= thr) if side == "H" else (lambda v, thr=thr: v["A"] - v["H"] >= thr)
                out.append(Atom(m, s, "team", pred, f"{name} {nm}", "margin_" + side, ">=", thr))
            elif name in GAME_TOTAL_NAMES and mtype == "TOTAL":
                b = line_bounds(s)
                if b:
                    op, thr = b
                    pred = (lambda v, thr=thr: v["H"] + v["A"] >= thr) if op == ">=" else (lambda v, thr=thr: v["H"] + v["A"] <= thr)
                    out.append(Atom(m, s, "team", pred, f"{name} {nm}", "total", op, thr))
            elif mtype == "TOTAL" and re.match(r"^(.*?) Total (Goals|Points|Runs)$", name) and name not in GAME_TOTAL_NAMES:
                side = side_of(name.rsplit(" Total", 1)[0])
                b = line_bounds(s)
                if side and b:
                    op, thr = b
                    pred = (lambda v, side=side, thr=thr: v[side] >= thr) if op == ">=" else (lambda v, side=side, thr=thr: v[side] <= thr)
                    out.append(Atom(m, s, "team", pred, f"{name} {nm}", "team_" + side, op, thr))
            elif name in ML_NAMES and mtype in ("MONEYLINE", "THREE_WAY_MONEYLINE"):
                if s["type"] == "DRAW":
                    out.append(Atom(m, s, "team", lambda v: v["H"] == v["A"], f"{name} Draw", "result", "==", 0))
                    continue
                side = side_of(nm, s["type"])
                if side == "H":
                    out.append(Atom(m, s, "team", lambda v: v["H"] > v["A"], f"{name} {nm}", "result", ">", 0))
                elif side == "A":
                    out.append(Atom(m, s, "team", lambda v: v["A"] > v["H"], f"{name} {nm}", "result", "<", 0))
            elif name == "Both Teams To Score":
                yes = nm.lower() == "yes"
                out.append(Atom(m, s, "team", (lambda v: v["H"] > 0 and v["A"] > 0) if yes else (lambda v: v["H"] == 0 or v["A"] == 0), f"BTTS {nm}", "btts", "==", 1 if yes else 0))
            elif name == "Double Chance":
                side = side_of(nm)
                if side and "Draw" in nm:
                    out.append(Atom(m, s, "team", (lambda v: v["H"] >= v["A"]) if side == "H" else (lambda v: v["A"] >= v["H"]), f"Double Chance {nm}", "dc_" + side, ">=", 0))
            elif name in ("Draw No Bet", "Tie No Bet"):
                side = side_of(nm, s["type"])
                if side:
                    out.append(Atom(m, s, "team", (lambda v: v["H"] > v["A"]) if side == "H" else (lambda v: v["A"] > v["H"]), f"DNB {nm}", "dnb_" + side, ">", 0))
            elif name == "Correct Score":
                sc = SCORE_RE.search(nm)
                side = side_of(nm)
                if sc and (side or "Draw" in nm):
                    g1, g2 = int(sc.group(1)), int(sc.group(2))
                    h, a = (g1, g2) if side in ("H", None) else (g2, g1)
                    out.append(Atom(m, s, "team", lambda v, h=h, a=a: v["H"] == h and v["A"] == a, f"Correct Score {nm}", "score", "==", f"{h}-{a}"))
    return out


# ----------------------------------------------------------------------------------------------------------------------
# feasibility
# ----------------------------------------------------------------------------------------------------------------------
def feasible_points(space, base, sport=None):
    """Enumerate the integer outcomes consistent with every base atom. -> list of dict (empty when the base is impossible)."""
    if space == "team":
        lo, hi = TEAM_RANGE.get(sport, (0, 100))
        pts = []
        for h in range(lo, hi + 1):
            for a in range(lo, hi + 1):
                v = {"H": h, "A": a}
                if all(atom.pred(v) for atom in base):
                    pts.append(v)
        return pts
    spec = PLAYER_SPACES[space]
    names = list(spec["vars"])
    ranges = [range(spec["vars"][n][0], spec["vars"][n][1] + 1) for n in names]
    pts = []
    for combo in itertools.product(*ranges):
        v = dict(zip(names, combo))
        if any(not c(v) for c in spec["constraints"]):
            continue
        for d, f in spec["derived"].items():
            v[d] = f(v)
        if all(atom.pred(v) for atom in base):
            pts.append(v)
    return pts


def implied_atoms(points, candidates, base, singles=None):
    """Atoms that hold on every feasible outcome of the base but on neither base atom alone (a true conjunction implication).
    `singles` maps each base atom key to that atom's own feasible outcomes."""
    base_keys = {a.key for a in base}
    base_markets = {a.market for a in base}
    out = []
    for atom in candidates:
        if atom.key in base_keys or atom.market in base_markets:
            continue
        if not all(atom.pred(v) for v in points):
            continue
        if singles and any(all(atom.pred(v) for v in pts) for pts in singles.values()):
            continue  # already implied by one leg alone: that is the two-leg case, not a conjunction
        out.append(atom)
    return out


def pick_stack(implied):
    """One implied atom per market name family (LIST rung and TOTAL line are different markets): the highest threshold of each,
    which is the most 'expensive' implied leg and so the largest multiplier if the engine treats it as independent."""
    best = {}
    for a in implied:
        key = (a.market, a.mtype)
        cur = best.get(key)
        if cur is None or (isinstance(a.thr, (int, float)) and isinstance(cur.thr, (int, float)) and ((a.op in (">=", ">") and a.thr > cur.thr) or (a.op in ("<=", "<") and a.thr < cur.thr))):
            best[key] = a
    return list(best.values())


# ----------------------------------------------------------------------------------------------------------------------
# construction enumeration
# ----------------------------------------------------------------------------------------------------------------------
def base_pairs_player(atoms, max_per_player=40):
    """Pairs of atoms on different variables of one player (different markets), favouring main lines plus ladder rungs."""
    by_var = {}
    for a in atoms:
        by_var.setdefault((a.var, a.op), []).append(a)
    pairs = []
    keys = list(by_var)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            (v1, o1), (v2, o2) = keys[i], keys[j]
            if v1 == v2:
                continue
            for a in by_var[keys[i]]:
                for b in by_var[keys[j]]:
                    if a.market == b.market:
                        continue
                    pairs.append((a, b))
    # keep the pairs with the most lines first (ladder x main), capped
    pairs.sort(key=lambda p: (p[0].mtype == p[1].mtype, -(p[0].decimal or 0) - (p[1].decimal or 0)))
    return pairs[:max_per_player]


def base_pairs_team(atoms, max_pairs=60):
    groups = {}
    for a in atoms:
        groups.setdefault(a.var.split("_")[0] if a.var else "x", []).append(a)
    pairs = []
    fam = list(groups)
    for i in range(len(fam)):
        for j in range(i + 1, len(fam)):
            for a in groups[fam[i]]:
                for b in groups[fam[j]]:
                    if a.market == b.market:
                        continue
                    pairs.append((a, b))
    pairs.sort(key=lambda p: -(p[0].decimal or 0) * (p[1].decimal or 0))
    return pairs[:max_pairs]


def constructions(event, markets, sport, max_per_player=40, max_team_pairs=60, max_points_check=400000):
    """-> list of dict(space, player, base=[atoms], implied=[atoms], stack=[atoms])."""
    out = []
    patoms = player_atoms(markets, sport)
    for (player, space), atoms in patoms.items():
        single_cache = {}
        for a, b in base_pairs_player(atoms, max_per_player):
            pts = feasible_points(space, [a, b], sport)
            if not pts:
                continue
            for atom in (a, b):
                if atom.key not in single_cache:
                    single_cache[atom.key] = feasible_points(space, [atom], sport)
            imp = implied_atoms(pts, atoms, [a, b], {a.key: single_cache[a.key], b.key: single_cache[b.key]})
            if imp:
                out.append({"space": space, "player": player, "base": [a, b], "implied": imp, "stack": pick_stack(imp), "feasible": len(pts)})
    tatoms = team_atoms(markets, event, sport)
    if tatoms and sport in TEAM_RANGE:
        single_cache = {}
        for a, b in base_pairs_team(tatoms, max_team_pairs):
            pts = feasible_points("team", [a, b], sport)
            if not pts:
                continue
            for atom in (a, b):
                if atom.key not in single_cache:
                    single_cache[atom.key] = feasible_points("team", [atom], sport)
            imp = implied_atoms(pts, tatoms, [a, b], {a.key: single_cache[a.key], b.key: single_cache[b.key]})
            if imp:
                out.append({"space": "team", "player": None, "base": [a, b], "implied": imp, "stack": pick_stack(imp), "feasible": len(pts)})
    return out
