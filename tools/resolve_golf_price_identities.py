#!/usr/bin/env python3
"""Resolve the price audit's unmatched names using retained public DG profiles.

This source-only follow-up changes no sport screen, prices, clocks or eligibility.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_golf_historical_prices import audit, classify, digest, name_key, verified
from explore_golf_rotation import EDITIONS


class ProfileHeader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.titles, self.urls = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            if attrs.get("property") == "og:title":
                self.titles.append(attrs.get("content", ""))
            if attrs.get("property") == "og:url":
                self.urls.append(attrs.get("content", ""))


def profile_name(raw, dg_id):
    page = ProfileHeader()
    page.feed(raw.decode("utf-8"))
    if len(page.urls) != 1 or len(page.titles) != 1:
        raise ValueError("Missing or ambiguous profile header")
    url = urlsplit(page.urls[0])
    if (url.scheme != "https" or url.netloc != "datagolf.com"
            or url.path not in ("/player_profiles", "/player-profiles")
            or parse_qs(url.query) != {"dg_id": [str(dg_id)]}):
        raise ValueError("Profile does not identify the requested Data Golf ID")
    suffix = " Stats | Data Golf"
    if not page.titles[0].endswith(suffix):
        raise ValueError("Unexpected profile title")
    name = page.titles[0][:-len(suffix)].strip()
    if not name:
        raise ValueError("Empty profile name")
    return name


def profile_key(name):
    # Explicit Danish transliteration; retain all other original normalizations.
    return name_key(name).replace("ø", "o")


def resolve(row, names, profiles, pair):
    augmented = dict(names)
    used = []
    fields = [("player_name", "dg_id"), ("opponent_name", "opponent_dg_id")]
    if row["market"] == "3-balls":
        fields.append(("opponent2_name", "opponent2_dg_id"))
    for field, id_field in fields:
        key = name_key(row[field], surname_first=True)
        # Never override an existing match or ambiguous original name.
        if augmented.get(key):
            continue
        ident = row[id_field]
        if ident not in profiles:
            continue
        current_name = profiles[ident]
        matches = [p for group in names.values() for p in group
                   if profile_key(p["name"]) == profile_key(current_name)]
        augmented[key] = matches
        used.append({"dg_id": ident, "export_name": row[field],
                     "profile_name": current_name,
                     "pga_player_ids": [p["pga_player_id"] for p in matches]})
    return {**classify(row, augmented, pair), "profile_matches": used}


def main():
    raw_dir = ROOT / "data/raw/golf-historical-price-search-2026-09-19"
    identity_dir = ROOT / "data/raw/golf-historical-player-identities-2026-09-19"
    baseline, rows = audit(raw_dir, ROOT / "data/raw/golf-rotation")
    required = set()
    for row in rows:
        missing = {p["name"] for p in row["unmatched"]}
        for field, id_field in (("player_name", "dg_id"),
                               ("opponent_name", "opponent_dg_id"),
                               ("opponent2_name", "opponent2_dg_id")):
            if row[field] in missing:
                required.add(row[id_field])
    identities, sources = {}, []
    for ident in sorted(required):
        path = identity_dir / f"{ident}.html"
        raw, source = verified(path)
        if source["status"] != 200:
            raise ValueError("Failed profile capture")
        identities[path.stem] = profile_name(raw, path.stem)
        sources.append(source)
    # Use the audit's hash-verified, exact official assignments. All target-field
    # players may not occur in an already matched price, so decode tee sources.
    import base64
    import gzip
    contexts = {}
    for ident, _, hard, easy in EDITIONS:
        raw, _ = verified(ROOT / f"data/raw/golf-rotation/{ident}-tee.json", ".capture.json")
        wire = json.loads(raw)["data"]["teeTimesCompressedV2"]
        tee = json.loads(gzip.decompress(base64.b64decode(wire["payload"], validate=True)))
        names = defaultdict(list)
        for round_ in tee["rounds"]:
            if round_["roundInt"] != 1:
                continue
            for group in round_["groups"]:
                for p in group["players"]:
                    names[name_key(p["displayName"])].append({
                        "pga_player_id": p["id"], "name": p["displayName"],
                        "course_id": group.get("courseId"),
                        "group_number": group.get("groupNumber"),
                        "tee_time_epoch_ms": group.get("teeTime")})
        contexts[ident] = (names, (hard, easy))
    resolved = []
    for row in rows:
        names, pair = contexts[row["pga_tournament_id"]]
        context = resolve(row, names, identities, pair)
        resolved.append({**row, "original_classification": row["classification"], **context})
    data = (json.dumps(resolved, indent=2) + "\n").encode()
    inventory = identity_dir / "g11-price-assignment-inventory.json"
    inventory.write_bytes(data)
    report = {
        "scope": "Public profile identity follow-up only; no backtest or sport-screen changes",
        "price_source_commit": baseline["commit"],
        "price_and_tee_sources": baseline["sources"], "profile_sources": sources,
        "identity_names": identities,
        "initial_classifications": baseline["target_classifications"],
        "resolved_classifications": dict(Counter(r["classification"] for r in resolved)),
        "editions": {ident: dict(Counter(r["classification"] for r in resolved
                       if r["pga_tournament_id"] == ident)) for ident in contexts},
        "resolved_identity_rows": [{"tournament": r["pga_tournament_id"],
             "market": r["market"], "matches": r["profile_matches"],
             "classification": r["classification"]} for r in resolved if r["profile_matches"]],
        "derived_inventory": {"path": str(inventory.relative_to(ROOT)), "sha256": digest(data)},
        "eligible_g11_bets": 0,
        "limitations": baseline["limitations"][:5] + [
            "Profiles were retrieved retrospectively and establish current ID/name identity only.",
            "Name joins remain unique within edition; Danish ø is explicitly transliterated to o.",
            "Headshot filename numbers are not used as PGA player IDs.",
            "Selected export cannot establish the full universe of offered markets."]}
    output = ROOT / "reports/golf-price-identity-followup-2026-09-19.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("initial_classifications", "resolved_classifications", "editions")}))


if __name__ == "__main__":
    main()
