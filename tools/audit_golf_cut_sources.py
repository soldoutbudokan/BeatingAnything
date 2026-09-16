#!/usr/bin/env python3
"""Bounded 2025 ordinary-event official cut source acquisition; no weather reads.

Only the 25 configured ordinary-rule events. One worker, cache, 1-second spacing,
25 index + 25 R2-note + 10 explicitly selected follow-up fetches at most.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import gzip
import html
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/golf-cut-audit"
HOST = "https://pgatourmedia.pgatourhq.com"
CAPS = {"index": 25, "r2": 25, "followup": 10}
# Freeze URLs before examining any outcomes. Failed or absent routes stay unknown.
SLUGS = {
    "R2025006": "sonyopeninhawaii", "R2025003": "wmphoenixopen",
    "R2025540": "mexicoopenatvidantaworld",
    "R2025010": "cognizantclassicinthepalmbeaches",
    "R2025483": "puertoricoopen", "R2025011": "theplayerschampionship",
    "R2025475": "valsparchampionship", "R2025020": "texaschildrenshoustonopen",
    "R2025041": "valerotexasopen", "R2025522": "coralespuntacanachampionship",
    "R2025019": "thecjcupbyronnelson", "R2025553": "oneflightmyrtlebeachclassic",
    "R2025021": "charlesschwabchallenge", "R2025032": "rbccanadianopen",
    "R2025524": "rocketclassic", "R2025030": "johndeereclassic",
    "R2025541": "genesisscottishopen", "R2025518": "iscochampionship",
    "R2025525": "3mopen", "R2025013": "wyndhamchampionship",
    "R2025464": "procorechampionship", "R2025054": "sandersonfarmschampionship",
    "R2025554": "bankofutahchampionship",
    "R2025457": "worldwidetechnologychampionship",
    "R2025528": "butterfieldbermudachampionship",
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def metadata() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(RAW.glob("*.meta.json"))]


def fetch(event_id: str, kind: str, url: str, suffix: str) -> Path:
    if kind not in CAPS:
        raise ValueError(kind)
    path = RAW / f"{event_id}-{suffix}"
    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        m = json.loads(meta_path.read_text())
        if m["url"] != url:
            raise ValueError("Refuse cache URL replacement")
        return path
    records = metadata()
    if any(m["kind"] == "reallocated_r2_slot_final_metadata" for m in records):
        raise RuntimeError("Final one-time check completed; no further acquisition authorized")
    if any(m.get("status") in (401, 403, 429) for m in records):
        raise RuntimeError("A source denial already stopped this acquisition")
    counts = Counter(m["kind"] for m in records)
    if counts[kind] >= CAPS[kind] or sum(counts.values()) >= 60:
        raise RuntimeError("Source file budget exhausted")
    if urlsplit(url).hostname != "pgatourmedia.pgatourhq.com":
        raise ValueError("Only linked official media sources allowed")
    m = {"url": url, "pga_id": event_id, "kind": kind,
         "request_started_utc": utc(), "file": str(path.relative_to(ROOT))}
    chunks: list[bytes] = []
    try:
        with urlopen(url, timeout=30) as response:
            m.update(status=response.status, headers={k: v for k, v in response.headers.items()
                     if k.lower() in ("date", "content-type", "etag", "last-modified")})
            started = time.monotonic()
            while chunk := response.read(16_384):
                chunks.append(chunk)
                if sum(map(len, chunks)) > 8_000_000 or time.monotonic() - started > 60:
                    raise RuntimeError("Per-file size/time budget exceeded")
    except HTTPError as exc:
        chunks = [exc.read(100_000)]
        m.update(status=exc.code, error=str(exc))
    except Exception as exc:
        m.update(error=f"{type(exc).__name__}: {exc}")
    body = b"".join(chunks)
    path.write_bytes(body)
    m.update(received_utc=utc(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
             complete=m.get("status") == 200 and "error" not in m)
    meta_path.write_text(json.dumps(m, indent=2) + "\n")
    print(event_id, kind, m.get("status"), len(body), m.get("error", ""), flush=True)
    time.sleep(1)
    if m.get("status") in (401, 403, 429):
        raise RuntimeError("Source denial: no retry or bypass")
    return path


def note_links(path: Path) -> dict[str, str]:
    content = path.read_text(errors="replace")
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", content, flags=re.S | re.I):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if not cells or re.sub(r"<[^>]+>", "", cells[0]).strip() != "Notes":
            continue
        links = {}
        for rnd, cell in enumerate(cells[1:5], 1):
            found = re.findall(r"href=[\"']([^\"']+)[\"']", cell)
            if len(found) == 1:
                parts = urlsplit(urljoin(HOST, html.unescape(found[0])))
                links[str(rnd)] = urlunsplit((parts.scheme, parts.netloc,
                                             quote(parts.path, safe="/%"), parts.query, parts.fragment))
        return links
    return {}


def acquire(followup: list[str]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config/golf-cut-rules-2025.json").read_text())
    events = [e for e in config["events"] if e["ordinary_rule_candidate"]]
    assert len(events) == 25 and {e["pga_id"] for e in events} == set(SLUGS)
    if followup:
        for spec in followup:
            event_id, rnd = spec.split(":")
            assert event_id in SLUGS and rnd in ("3", "4")
            links = note_links(RAW / f"{event_id}-index.html")
            if rnd not in links:
                print(event_id, "missing follow-up link", rnd, flush=True)
                continue
            fetch(event_id, "followup", links[rnd], f"r{rnd}.pdf")
        return
    for event in events:
        event_id = event["pga_id"]
        path = fetch(event_id, "index", f"{HOST}/tours/2025/pgatour/{SLUGS[event_id]}", "index.html")
        links = note_links(path)
        (RAW / f"{event_id}-links.json").write_text(json.dumps(links, indent=2) + "\n")
        if "2" in links:
            fetch(event_id, "r2", links["2"], "r2.pdf")
        else:
            print(event_id, "missing R2 Notes link; no alternative request", flush=True)


def reconcile() -> None:
    """Audit complete cached scorecards against already frozen official statements."""
    from explore_golf_sport import statuses
    from explore_golf_sunday import complete_score

    def canon(value):
        return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if c.isalnum())

    source_path = RAW / "official-cut-statements.json"
    statements = json.loads(source_path.read_text())
    scores_path = ROOT / "data/raw/golf-sport/scoreboard-2025.json"
    events = {e["id"]: e for e in json.loads(scores_path.read_text())["events"] if e.get("id")}
    rows = []
    for statement in statements["events"]:
        row = {"pga_id": statement["pga_id"], "name": statement["name"]}
        if statement["cut"] is None:
            row["status"] = "not_reconciled_no_official_threshold"
            rows.append(row)
            continue
        event = events[statement["espn_id"]]
        final = statuses(event)
        tee_path = ROOT / f"data/raw/golf-weather-groups/{statement['pga_id']}-teetimes.json"
        tee = json.loads(tee_path.read_text())["data"]["teeTimesCompressedV2"]["payload"]
        tee = json.loads(gzip.decompress(base64.b64decode(tee))) if isinstance(tee, str) else tee
        amateurs = {}
        r3_names = set()
        r3_ids = {}
        for rnd in tee["rounds"]:
            for group in rnd["groups"]:
                for player in group["players"]:
                    name = canon(player["displayName"])
                    if rnd["roundInt"] in (1, 2):
                        if name in amateurs and amateurs[name] != player["amateur"]:
                            raise ValueError("Official amateur flag disagreement")
                        amateurs[name] = player["amateur"]
                    elif rnd["roundInt"] == 3:
                        r3_names.add(name)
                        r3_ids[player["id"]] = player["amateur"]
        players = []
        for player in event["competitions"][0]["competitors"]:
            pid = str(player["id"])
            rnds = {r["period"]: r for r in player.get("linescores", []) if r.get("period") in (1, 2, 3, 4)}
            if len(rnds) != len([r for r in player.get("linescores", []) if r.get("period") in (1, 2, 3, 4)]):
                raise ValueError("Duplicate player-round")
            complete = {r: complete_score(raw) for r, raw in rnds.items()}
            score36 = sum(complete[r] for r in (1, 2)) if all(complete.get(r) is not None for r in (1, 2)) else None
            name = player["athlete"]["displayName"]
            norm = canon(name)
            detail = final.get(pid, {}).get("detail")
            positive_holes = {r: sum(isinstance(h.get("value"), (float, int)) and h["value"] > 0
                                     for h in raw.get("linescores", [])) for r, raw in rnds.items()}
            players.append({"espn_player_id": pid, "name": name, "score36": score36,
                            "detail": detail, "html_status_present": pid in final,
                            "amateur": amateurs.get(norm), "r3_tee_present": norm in r3_names,
                            "positive_holes_by_round": positive_holes,
                            "complete_rounds": [r for r, score in complete.items() if score is not None]})
        cutoff = statement["cut"]["score_strokes"]
        valid = [p for p in players if p["score36"] is not None]
        qualifying = [p for p in valid if p["score36"] <= cutoff]
        ranked = sorted(p["score36"] for p in valid)
        # This is a diagnostic conditional on all complete totals being eligible.
        # Do not use it to infer, repair or replace the official cut rule or threshold.
        conditional_65th = ranked[64] if len(ranked) >= 65 else None
        flagged = [p for p in players if p["detail"] in ("WD", "W/D", "DQ")]
        known_names = {canon(p["name"]) for p in players}
        unmatched_official_amateurs = [name for name, amateur in amateurs.items()
                                       if amateur and name not in known_names]
        row.update(status="reconciled_source_audit", official_cut=statement["cut"],
                   api_player_records=len(players), complete36_records=len(valid),
                   incomplete36_records=len(players) - len(valid),
                   cached_count_at_or_below_official_cut=len(qualifying),
                   cached_amateurs_at_or_below_official_cut=sum(p["amateur"] is True for p in qualifying),
                   qualifying_unknown_amateur_flag=[p["name"] for p in qualifying if p["amateur"] is None],
                   unmatched_official_amateur_names=unmatched_official_amateurs,
                   count_matches=(len(qualifying) == statement["cut"]["qualifiers"]
                                  if statement["cut"]["qualifiers"] is not None else None),
                   amateurs_match=((not unmatched_official_amateurs
                                   and sum(p["amateur"] is True for p in qualifying) == statement["cut"]["amateurs"])
                                   if statement["cut"]["amateurs"] is not None else None),
                   conditional_65th_complete_score=conditional_65th,
                   conditional_65th_matches=conditional_65th == cutoff,
                   official_r3_tee_player_count=len(r3_ids),
                   official_r3_tee_amateurs=sum(r3_ids.values()),
                   official_r3_tee_amateurs_match=(sum(r3_ids.values()) == statement["cut"]["amateurs"]
                                                  if statement["cut"]["amateurs"] is not None else None),
                   official_r3_tee_count_matches_cached_qualifiers=len(r3_ids) == len(qualifying),
                   qualifiers_absent_official_r3_tee=[p["name"] for p in qualifying if not p["r3_tee_present"]],
                   missing_final_status=[p["name"] for p in players if not p["html_status_present"]],
                   wd_dq=flagged,
                   qualifier_cut_status_conflicts=[p for p in qualifying if p["detail"] == "CUT"],
                   above_cut_noncut_status_conflicts=[p for p in valid if p["score36"] > cutoff
                                                     and p["detail"] not in ("CUT", "WD", "W/D", "DQ")],
                   sources=[{"file": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in [tee_path, ROOT / f"data/raw/golf-sport/leaderboard-{statement['espn_id']}.html"]])
        rows.append(row)
    result = {"scope": "Official-threshold source reconciliation only; no weather or effect estimate.",
              "created_utc": utc(),
              "sources": [{"file": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in [source_path, scores_path]], "events": rows}
    (RAW / "reconciliation.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row["pga_id"], row["status"], {k: row.get(k) for k in
              ("count_matches", "amateurs_match", "conditional_65th_matches", "qualifiers_absent_official_r3_tee")}, flush=True)
        if row.get("wd_dq"):
            print("  WD/DQ", [(p["name"], p["score36"], p["positive_holes_by_round"]) for p in row["wd_dq"]], flush=True)


def bermuda_final_metadata_once() -> None:
    """One expressly reallocated unused R2 slot; no further acquisition afterward."""
    from beating.golf_collect import PUBLIC_PGA_KEY, QUERIES, decode_payloads, http_request

    path = RAW / "R2025528-final-leaderboard.json"
    meta_path = path.with_suffix(".meta.json")
    if not meta_path.exists():
        counts = Counter(m["kind"] for m in metadata())
        if counts != Counter({"index": 25, "r2": 23, "followup": 10}):
            raise RuntimeError("Unexpected acquisition budget before one-time reallocation")
        request = {"query": QUERIES["LeaderboardCompressedV3"],
                   "operationName": "LeaderboardCompressedV3",
                   "variables": {"leaderboardCompressedV3Id": "R2025528"}}
        started = utc()
        status, headers, body = http_request("POST", "https://orchestrator.pgatour.com/graphql",
            json.dumps(request).encode(), {"Content-Type": "application/json", "x-api-key": PUBLIC_PGA_KEY}, 30)
        path.write_bytes(body)
        meta = {"url": "https://orchestrator.pgatour.com/graphql", "request": request,
                "pga_id": "R2025528", "kind": "reallocated_r2_slot_final_metadata",
                "request_started_utc": started, "received_utc": utc(), "status": status,
                "file": str(path.relative_to(ROOT)), "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "complete": status == 200,
                "headers": {k: v for k, v in headers.items() if k.lower() in ("date", "content-type", "etag")},
                "budget_reallocation": "Parent expressly reassigned exactly one unused R2-note slot to an explicit official final leaderboard cut-metadata check, total request 59 of 60; no further acquisition authorized."}
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
        print("Bermuda final metadata HTTP", status, "bytes", len(body), flush=True)
        if status != 200:
            return
    raw = json.loads(path.read_text())
    if raw.get("errors"):
        print("GraphQL errors; no further request", raw["errors"])
        return
    board = decode_payloads(raw)["data"]["leaderboardCompressedV3"]
    if board["id"] != "R2025528":
        raise ValueError("Bermuda final source identity mismatch")
    payload = board["payload"]
    # Inspect metadata only. Never inspect or derive a cutoff from player scores.
    selected = {k: v for k, v in payload.items() if "cut" in k.casefold()}
    information_rows = [{k: row[k] for k in ("__typename", "id", "displayText", "mobileDisplayText") if k in row}
                        for row in payload.get("players", [])
                        if row.get("__typename") == "InformationRow"
                        and "cut" in str(row.get("id", "")).casefold()]
    evidence = {"id": board["id"], "top_level_keys": list(payload), "explicit_cut_metadata": selected,
                "explicit_cut_information_rows": information_rows,
                "source": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "inspected_utc": utc(), "scope": "Top-level metadata and labelled InformationRow cut metadata only; no player outcome inspection."}
    (RAW / "R2025528-explicit-cut-metadata.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--followup", action="append", default=[], metavar="PGA_ID:ROUND")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--bermuda-final-metadata", action="store_true")
    args = parser.parse_args()
    if args.bermuda_final_metadata:
        if args.reconcile or args.followup:
            parser.error("One-time metadata acquisition must run separately")
        bermuda_final_metadata_once()
    elif args.reconcile:
        if args.followup:
            parser.error("Keep acquisition and reconciliation separate")
        reconcile()
    else:
        acquire(args.followup)
