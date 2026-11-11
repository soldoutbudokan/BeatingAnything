"""Build models/ipl/static/player_styles.csv (batting hand + bowling type per cricsheet id).

Sources, in priority order (later = lower priority, used to fill gaps):
  1. curated overrides   models/ipl/static/player_styles_curated.csv
  2. cricketdata::player_meta  (github.com/robjhyndman/cricketdata data/player_meta.rda,
     Cricinfo-derived, keyed by cricsheet id)  -> converted to CSV in data/raw/cricket_styles/gh/
  3. small GitHub-mirrored Cricinfo scrapes keyed by cricinfo id (joined via people.csv key_cricinfo)

Inputs live under data/raw/cricket_styles/ (gitignored). Run:
  python models/ipl/static/build_player_styles.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "cricket_styles"
GH = RAW / "gh"
STATIC = Path(__file__).resolve().parent
OUT = STATIC / "player_styles.csv"
CURATED = STATIC / "player_styles_curated.csv"

COLS = ["cricsheet_id", "name", "bat_hand", "bowl_type", "bowl_group", "source", "confidence"]
PACE = {"RF", "RFM", "RM", "LF", "LFM", "LM"}
SPIN = {"OB", "LB", "SLA", "SLW"}
VOCAB = PACE | SPIN | {"none"}


def group(bt: str) -> str:
    if bt in PACE:
        return "pace"
    if bt in SPIN:
        return "spin"
    if bt == "none":
        return "none"
    return ""


def norm_bat(s) -> str:
    if not s or str(s).strip().upper() in {"NA", "NAN", "NONE"}:
        return ""
    s = str(s).lower()
    if s.startswith("left") or s in {"lhb", "l"}:
        return "L"
    if s.startswith("right") or s in {"rhb", "r"}:
        return "R"
    return ""


def norm_one(s: str) -> str:
    """Map one Cricinfo-style bowling description to vocab ('' if unknown/ambiguous)."""
    s = s.lower().replace("-", " ").replace("_", " ").strip()
    s = re.sub(r"\s+", " ", s)
    if not s or s in {"na", "nan", "none"}:
        return ""
    if "wrist" in s or "chinaman" in s or "left arm unorthodox" in s:
        return "SLW"
    if "orthodox" in s or s in {"left arm slow", "slow left arm", "left arm spin"}:
        return "SLA"
    if "leg" in s or "googly" in s:
        return "LB"
    if "off" in s:
        return "OB"
    left = s.startswith("left")
    right = s.startswith("right")
    if not (left or right):
        return ""
    if "fast medium" in s or "medium fast" in s:
        return "LFM" if left else "RFM"
    if "fast" in s:
        return "LF" if left else "RF"
    if "medium" in s or "slow medium" in s:
        return "LM" if left else "RM"
    # "right arm slow", "right arm bowler" etc. -> ambiguous
    return ""


def norm_bowl(s):
    """Return (bowl_type, ambiguous_flag). Multiple styles: first listed wins, flagged."""
    if s is None:
        return "", False
    s = str(s)
    parts = [p for p in re.split(r"[,/;]", s) if p.strip()]
    types = [t for t in (norm_one(p) for p in parts) if t]
    if not types:
        return "", False
    uniq = list(dict.fromkeys(types))
    return uniq[0], len(uniq) > 1


def load_people():
    people = {}
    by_cricinfo = {}
    with open(RAW / "dl" / "people.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            people[r["identifier"]] = r
            for k in ("key_cricinfo", "key_cricinfo_2", "key_cricinfo_3"):
                if r.get(k):
                    by_cricinfo[r[k].strip()] = r["identifier"]
    return people, by_cricinfo


def load_balls():
    balls = {}
    p = RAW / "players_balls.csv"
    if p.exists():
        with open(p, newline="") as fh:
            for r in csv.DictReader(fh):
                balls[r["id"]] = r
    return balls


def secondary(by_cricinfo):
    """cricinfo-id keyed scrapes mirrored on GitHub. Returns {cid: [(bat, bowl_raw, src)]}."""
    out: dict[str, list] = {}

    def add(cinfo, bat, bowl, src):
        cid = by_cricinfo.get(str(cinfo).strip())
        if cid:
            out.setdefault(cid, []).append((norm_bat(bat), bowl, src))

    specs = [
        ("ritesh2024.csv", "ritesh-ojha/IPL-DATASET", None, "longBattingStyles", "longBowlingStyles"),
        ("nishant_meta.csv", "nishantsingh98/cricket_analysis", "cricinfo_id", "batting_style", "bowling_style"),
        ("suyog.csv", "SuyogKhanal/CricRec", "id", "bating_style", "bowling_style"),
        ("cyber.csv", "cyberkrishna/dbms-project", "id", "bating_style", "bowling_style"),
        ("arnav.csv", "arnavbonigala/ipl-engine", "player_id", "bat_style", "bowl_style"),
    ]
    for fn, src, idcol, batcol, bowlcol in specs:
        p = GH / fn
        if not p.exists():
            continue
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if idcol is None:
                    m = re.search(r"-(\d+)$", r.get("espn_url", "").strip())
                    if not m:
                        continue
                    cinfo = m.group(1)
                else:
                    cinfo = r[idcol]
                add(cinfo, r.get(batcol), r.get(bowlcol), "github:" + src)
    return out


def main():
    people, by_cricinfo = load_people()
    balls = load_balls()
    rows: dict[str, dict] = {}

    # --- primary dataset
    pm_path = GH / "cricketdata_player_meta.csv"
    pm = {}
    if pm_path.exists():
        with open(pm_path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cid = r["cricsheet_id"]
                if cid not in people or cid in pm:
                    continue
                p = people[cid]
                keys = {p["key_cricinfo"], p["key_cricinfo_2"], p["key_cricinfo_3"]} - {""}
                if keys and r["cricinfo_id"] not in keys:
                    continue  # id bridge disagrees with cricsheet register -> distrust row
                pm[cid] = r
    sec = secondary(by_cricinfo)

    ids = set(pm) | set(sec) | {i for i in balls if i in people}
    for cid in ids:
        bat, bt, src, conf = "", "", [], "high"
        if cid in pm:
            r = pm[cid]
            bat = norm_bat(r["batting_style"])
            bt, amb = norm_bowl(r["bowling_style"])
            src.append("cricketdata_player_meta")
            if amb:
                conf = "medium"
            raw = (r["bowling_style"] or "").lower()
            if bt == "" and raw and raw not in {"na"}:
                conf = "low"  # e.g. "Right arm Bowler" / "Right arm Slow"
        for b2, bowl2, s2 in sec.get(cid, []):
            bt2, _ = norm_bowl(bowl2)
            used = False
            if not bat and b2:
                bat, used = b2, True
            if not bt and bt2:
                bt, used = bt2, True
            if used:
                src.append(s2)
        rows[cid] = {"cricsheet_id": cid, "name": people[cid]["name"], "bat_hand": bat,
                     "bowl_type": bt, "source": "+".join(dict.fromkeys(src)), "confidence": conf}

    # --- "none" for players with no recorded style who essentially never bowl
    for cid, r in rows.items():
        b = balls.get(cid)
        if not r["bowl_type"] and b is not None and int(b["bowled"]) + int(b["ipl_bowled"]) <= 6:
            if True:  # no parseable style and (almost) never bowled in the data
                r["bowl_type"] = "none"
                r["source"] = "+".join(x for x in (r["source"], "cricsheet_no_bowling") if x)
                if cid not in pm:
                    r["confidence"] = "medium"

    # --- curated overrides (highest priority)
    if CURATED.exists():
        with open(CURATED, newline="", encoding="utf-8") as fh:
            for c in csv.DictReader(fh):
                cid = c["cricsheet_id"].strip()
                if cid not in people:
                    print("WARN curated id not in people.csv:", cid, c.get("name"))
                    continue
                r = rows.setdefault(cid, {"cricsheet_id": cid, "name": people[cid]["name"],
                                          "bat_hand": "", "bowl_type": "", "source": "", "confidence": ""})
                changed = False
                if c.get("bat_hand"):
                    changed |= r["bat_hand"] != c["bat_hand"]
                    r["bat_hand"] = c["bat_hand"]
                if c.get("bowl_type"):
                    changed |= r["bowl_type"] != c["bowl_type"]
                    r["bowl_type"] = c["bowl_type"]
                if changed or not r["source"]:
                    r["source"] = "curated" if not r["source"] else "curated(override:" + r["source"] + ")"
                    r["confidence"] = c.get("confidence") or "medium"
                elif "curated" not in r["source"]:
                    r["source"] += "+curated_verified"

    out = []
    for r in rows.values():
        if not r["bat_hand"] and not r["bowl_type"]:
            continue
        assert r["bat_hand"] in {"", "R", "L"}, r
        assert r["bowl_type"] in VOCAB | {""}, r
        r["bowl_group"] = group(r["bowl_type"])
        out.append(r)
    out.sort(key=lambda r: r["cricsheet_id"])

    fd, tmp = tempfile.mkstemp(dir=STATIC, prefix=".player_styles.", suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in out:
            w.writerow({k: r[k] for k in COLS})
    os.replace(tmp, OUT)
    print(f"wrote {len(out)} rows -> {OUT}")


if __name__ == "__main__":
    main()
