"""theScore Bet (Penn) sportsbook client: anonymous GraphQL access, competition/event listing, same-game-parlay (Parlay+)
pricing through the anonymous betslip, implication rules for redundant-leg pairs, and devig helpers.

Boards: the web app talks to https://sportsbook.<region>.thescore.bet/graphql. `ca-default` is the Ontario board; it answers
market queries from anywhere but withholds Parlay+ prices unless the caller's IP is in a valid region (regionalMetadata.validRegion).
A US-hosted caller is redirected to its state board (for example `US-OH`), which prices Parlay+ for anonymous betslips.
Set THESCORE_REGION to choose the board; the screen records the board it priced on.

Only read-only market queries and anonymous draft-betslip mutations are used. Nothing logs in or places a bet.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REGION = os.environ.get("THESCORE_REGION", "US-OH")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CLIENT_HEADERS = {"x-client": "tsb", "x-platform": "web", "x-app": "tsb", "x-app-version": "26.19.1", "x-device": "DESKTOP", "x-dma": "",
                  "apollographql-client-name": "tsb-tsb-web", "apollographql-client-version": "26.19.1"}
# sha256 of the web client's persisted documents (captured from the site on 2026-10-08); free-form documents are also accepted.
PERSISTED = {"Startup": "8c52170d05417bcc2642d4fb132694a00b4825facf4f23fa47bb78f2b8b59d83",
             "SportsMenu": "27e68b7528beaec518b78b90f3fc1f232618e0045890629272616a5be6d3bb16",
             "Marketplace": "c587e757f8e71fcbe6ea01e6b8a8da697bd7a9e9213c157a687bb79a6f5b828d",
             "BetslipAddMarketSelection": "2498f2b6a9a13dece42e3fc9acf539cceb3609882b1f7486ef96eebdaee0ee52"}
MARKETPLACE_VARS = {"includeSectionDefaultField": True, "isAdhocCarouselEnabled": False, "isCfpRankingEnabled": False, "includeStandardizedBoxscore": False,
                    "isBrandingImageEnabled": False, "isNewFeaturedBetParticipantLogoEnabled": False, "isSubscription": False,
                    "isFeaturedMarketCardRedesignEnabled": False, "isCombatSportsRedesignEnabled": False, "isParlayLoungeHeaderRedesignEnabled": False,
                    "isFeaturedBetCarouselHeaderRedesignEnabled": False, "isDsModelRecommendedPropsEnabled": False, "isLivePageEventCounterOnTabsEnabled": False,
                    "isBlueprintUiFieldEnabled": False, "canonicalUrl": "/home", "filterInput": None, "oddsFormat": "AMERICAN", "pageType": "PAGE",
                    "includeRecommendedProps": True, "includeRichEvent": True}
EVENT_FIELDS = "fallbackEvent { id name startTime status deepLink { webUrl } competition { slug name } sport { slug name } ... on StandardEvent { homeParticipant { abbreviation mediumName fullName } awayParticipant { abbreviation mediumName fullName } } }"
MARKET_FIELDS = "{ id name status type selections { id rawId type status name { fullName cleanName minimalName } participant { abbreviation mediumName fullName } points { decimalPoints } odds { denominatorLong numeratorLong formattedOdds(oddsFormat: AMERICAN) } } }"
CARD_TYPES = ["GridMarketCard", "SimpleGridMarketCard", "SoccerGridMarketCard", "TennisGridMarketCard", "CombatGridMarketCard", "CricketGridMarketCard"]
BETSLIP_Q = ("query { betslip { id numberOfSelections errors { message code } parlay { errors { message code } draftBets { id isParlayPlusEligible betToWinRatio "
             "totalOdds { formattedOdds(oddsFormat: AMERICAN) } errors { message code } draftLegs { marketName errors { message code } marketSelection { id } } } } } }")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decimal_odds(sel):
    """theScore odds carry decimal odds as numerator/denominator (13/11 = 1.1818 for -550)."""
    o = sel.get("odds") or {}
    try:
        return float(o["numeratorLong"]) / float(o["denominatorLong"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def find_typename(obj, typename, acc=None):
    acc = [] if acc is None else acc
    if isinstance(obj, dict):
        if obj.get("__typename") == typename:
            acc.append(obj)
        for v in obj.values():
            find_typename(v, typename, acc)
    elif isinstance(obj, list):
        for x in obj:
            find_typename(x, typename, acc)
    return acc


class TheScore:
    """One anonymous session (its own draft betslip) against one regional board."""

    def __init__(self, region=None, token=None, timeout=60, sleep=0.0):
        self.region = region or REGION
        self.gql = f"https://sportsbook.{self.region}.thescore.bet/graphql"
        site = "https://sportsbook.ca.thescore.bet" if self.region.lower().startswith("ca") else "https://sportsbook.thescore.bet"
        install_id = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(22))  # fresh anonymous identity per client
        self.base_headers = dict(CLIENT_HEADERS, **{"accept": "application/json", "content-type": "application/json", "origin": site, "referer": site + "/",
                                                    "user-agent": UA, "x-install-id": install_id})
        self.timeout = timeout
        self.sleep = sleep
        self.requests = 0
        self.startup = None
        self.token = token
        if not self.token:
            connect = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(30))  # anonymous betslips are keyed by this
            self.startup = self.persisted("Startup", {"connectToken": connect}, auth=False)["data"]["startup"]
            self.token = self.startup["anonymousToken"]
        self.headers = dict(self.base_headers, **{"x-anonymous-authorization": "Bearer " + self.token})

    def _request(self, url, body=None, auth=True):
        headers = self.headers if auth else self.base_headers
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=dict(headers, **{"Accept-Encoding": "identity"}), method="POST" if data else "GET")
        self.requests += 1
        if self.sleep:
            time.sleep(self.sleep)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                return json.loads(text)
            except ValueError:
                return {"errors": [{"message": f"HTTP {e.code}: {text[:300]}"}]}

    def persisted(self, op, variables, auth=True, post=False):
        ext = {"persistedQuery": {"version": 1, "sha256Hash": PERSISTED[op]}}
        url = f"{self.gql}/persisted_queries/{PERSISTED[op]}"
        if post:
            return self._request(url, {"operationName": op, "variables": variables, "extensions": ext}, auth)
        q = urllib.parse.urlencode({"operationName": op, "variables": json.dumps(variables, separators=(",", ":")), "extensions": json.dumps(ext, separators=(",", ":"))})
        return self._request(f"{url}?{q}", None, auth)

    def query(self, document, variables=None):
        return self._request(self.gql, {"query": document, "variables": variables or {}})

    # ----- board navigation -----
    def regional_metadata(self):
        r = self.query("query { startup { regionalMetadata { currentCountryCode currentRegionCode ipAddressRegionCode validRegion } } }")
        return ((r.get("data") or {}).get("startup") or {}).get("regionalMetadata"), r.get("errors")

    def competitions(self):
        """Every competition page in the sports menu: [{path: [...labels], url}]."""
        menu = self.persisted("SportsMenu", {})["data"]["sportsMenu"]["menuItems"]
        out, seen = [], set()

        def walk(items, path):
            for it in items:
                label = it.get("label")
                url = (it.get("deepLink") or {}).get("webUrl")
                if it.get("type") == "LEAF" and url and "/competition/" in url and "/event/" not in url and url not in seen:
                    seen.add(url)
                    out.append({"path": path + [label], "url": url, "sport": url.split("/")[2]})
                walk(it.get("sportsMenuItemChildren") or [], path + [label])
        walk(menu, [])
        return out

    def competition_events(self, url):
        """Events with their main-line markets from the competition 'Lines' section."""
        r = self.query('query($u: String!) { page(canonicalUrl: $u) { id pageChildren { ... on Section { id label slug archetype hasContent default } } } }', {"u": url})
        page = (r.get("data") or {}).get("page")
        if not page:
            return None, r.get("errors") or "no page"
        secs = page.get("pageChildren") or []
        lines = [s for s in secs if s.get("archetype") == "COMPETITION_LINES"] or [s for s in secs if s.get("default")] or secs[:1]
        if not lines:
            return [], None
        frag = "{ __typename " + " ".join(f"... on {c} {{ id {EVENT_FIELDS} pagedMarkets: markets(pageType: PAGE) {MARKET_FIELDS} }}" for c in CARD_TYPES) + \
               f" ... on ThreeWayMoneylineMarketCard {{ id {EVENT_FIELDS} markets(pageType: PAGE) {MARKET_FIELDS} }} }}"
        r = self.query('query($id: ID!) { node(id: $id) { ... on Section { id sectionChildren { __typename ... on MarketplaceShelf { id marketplaceShelfChildren %s } } } } }' % frag, {"id": lines[0]["id"]})
        if r.get("errors") and not (r.get("data") or {}).get("node"):
            return None, r["errors"]
        out = []
        for ch in (((r.get("data") or {}).get("node") or {}).get("sectionChildren") or []):
            for card in ch.get("marketplaceShelfChildren") or []:
                ev = card.get("fallbackEvent")
                if ev:
                    out.append({"event": ev, "markets": card.get("pagedMarkets") or card.get("markets") or []})
        return out, None

    def event_markets(self, web_url):
        """All markets on an event page (Popular section plus every drawer), via the persisted Marketplace document."""
        r = self.persisted("Marketplace", dict(MARKETPLACE_VARS, canonicalUrl=web_url))
        page = (r.get("data") or {}).get("page")
        if not page:
            return None, r.get("errors")
        seen, out = set(), []
        for m in find_typename(page, "Market"):
            if m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            out.append(m)
        header = (page.get("pageHeaders") or [{}])[0].get("fallbackEvent") if page.get("pageHeaders") else None
        return {"markets": out, "event": header}, None

    # ----- anonymous betslip (Parlay+ pricing) -----
    def clear(self):
        return self.query("mutation { betslipClear { id numberOfSelections } }")

    def add(self, sel):
        sid = sel["id"] if str(sel["id"]).startswith("MarketSelection:") else "MarketSelection:" + sel["id"]
        v = {"isSubscription": False, "input": {"selectionId": sid, "odds": {"denominatorLong": sel["odds"]["denominatorLong"], "numeratorLong": sel["odds"]["numeratorLong"]},
                                                "selectionOrigin": None}, "oddsFormat": "AMERICAN", "includeOddsTrend": False, "includeSurcharge": False}
        r = self.persisted("BetslipAddMarketSelection", v, post=True)
        return ((r.get("data") or {}).get("betslipAddMarketSelection")), r.get("errors")

    def betslip(self):
        r = self.query(BETSLIP_Q)
        return ((r.get("data") or {}).get("betslip")), r.get("errors")

    def price_parlay(self, selections, max_wait=6.0, poll=0.3):
        """Clear the slip, add each selection, wait for the parlay draft bet to be priced.
        -> dict(decimal, legs, waited, error, errors) ; decimal is None when the book refuses or does not price the combination."""
        self.clear()
        for s in selections:
            b, err = self.add(s)
            if err or not b:
                return {"decimal": None, "error": "add_failed", "errors": err}
            if b.get("errors"):
                return {"decimal": None, "error": "betslip_error", "errors": b["errors"]}
        t0 = time.time()
        last = None
        while time.time() - t0 <= max_wait:
            b, err = self.betslip()
            if b:
                last = b
                drafts = (b.get("parlay") or {}).get("draftBets") or []
                wanted = {str(s["id"]).replace("MarketSelection:", "") for s in selections}
                if b.get("numberOfSelections") != len(selections):
                    return {"decimal": None, "error": "slip_count_mismatch", "errors": None, "waited": round(time.time() - t0, 2), "n": b.get("numberOfSelections")}
                if drafts:
                    d = drafts[0]
                    legs = {str((leg.get("marketSelection") or {}).get("id") or "").replace("BetslipMarketSelection:", "") for leg in d.get("draftLegs") or []}
                    if legs and legs != wanted:
                        return {"decimal": None, "error": "slip_legs_mismatch", "errors": None, "waited": round(time.time() - t0, 2), "n": b.get("numberOfSelections")}
                    if d.get("betToWinRatio") is not None:
                        return {"decimal": 1.0 + float(d["betToWinRatio"]), "formatted": (d.get("totalOdds") or {}).get("formattedOdds"), "eligible": d.get("isParlayPlusEligible"),
                                "waited": round(time.time() - t0, 2), "error": None, "errors": None, "n": b.get("numberOfSelections")}
                    errs = list(d.get("errors") or []) + [e for leg in d.get("draftLegs") or [] for e in (leg.get("errors") or [])]
                else:
                    errs = list((b.get("parlay") or {}).get("errors") or []) + list(b.get("errors") or [])
                if errs:
                    return {"decimal": None, "error": (errs[0].get("code") or errs[0].get("message")), "errors": errs, "waited": round(time.time() - t0, 2), "n": b.get("numberOfSelections")}
            time.sleep(poll)
        return {"decimal": None, "error": "timeout", "errors": None, "waited": round(time.time() - t0, 2), "n": (last or {}).get("numberOfSelections")}


# ---------------------------------------------------------------------------------------------------------------------
# Implication rules: pairs (A, B) where winning A guarantees winning B, so a fair same-game price for A+B equals A's price.
# ---------------------------------------------------------------------------------------------------------------------
PLUS_RE = re.compile(r"^(\d+(?:\.\d+)?)\+$")
SCORE_RE = re.compile(r"(\d+)\s*-\s*(\d+)$")
ROUND_RE = re.compile(r"\bRound (\d+)\b", re.I)
TEAM_TOTAL_RE = re.compile(r"^(.*?) Total (Goals|Points|Runs|Games|Sets)$")
PLAYER_STAT_RE = re.compile(r"^(?P<player>.+?) (?P<stat>Total .+?|Touchdowns Scored)$")
WIN_TYPE_MARKETS = ("Method Of Victory", "Method Of Victory (Double Chance)", "Round Betting", "Method & Round Combo", "Winning Margin", "Win To Nil",
                    "Correct Score", "Correct Score - Best Of 3 Sets", "Correct Score - Best Of 5 Sets", "Half Time/Full Time", "Half-Time/Full-Time", "To Win Both Halves",
                    "Winning Method", "Set Betting", "Correct Set Score", "To Win From Behind", "Win Both Halves", "Margin Of Victory")
GAME_TOTAL_NAMES = ("Total Goals", "Total Points", "Total Runs", "Total Games", "Total Rounds")
# stat implications inside one player's ladders: winning `src N+` guarantees `dst M+` for every M <= N*factor
STAT_IMPLIES = {
    "Total Rushing Yards": [("Total Rushing + Receiving Yards", 1.0)],
    "Total Receiving Yards": [("Total Rushing + Receiving Yards", 1.0)],
    "Total Goals": [("Total Points", 1.0)],
    "Total Assists": [("Total Points", 1.0), ("Total Points + Assists", 1.0), ("Total Rebounds + Assists", 1.0), ("Total Points + Rebounds + Assists", 1.0)],
    "Total Points": [("Total Points + Assists", 1.0), ("Total Points + Rebounds", 1.0), ("Total Points + Rebounds + Assists", 1.0)],
    "Total Rebounds": [("Total Points + Rebounds", 1.0), ("Total Rebounds + Assists", 1.0), ("Total Points + Rebounds + Assists", 1.0)],
    "Total 3-Pointers Made": [("Total Points", 3.0)],
    "Total Three Pointers Made": [("Total Points", 3.0)],
    "Total Home Runs": [("Total Hits", 1.0), ("Total RBIs", 1.0), ("Total Runs", 1.0), ("Total Bases", 4.0), ("Total Runs Scored", 1.0)],
    "Total Hits": [("Total Bases", 1.0)],
}


def open_selections(market):
    return [s for s in market.get("selections") or [] if s.get("status") == "OPEN" and s.get("odds") and decimal_odds(s)]


def threshold(sel):
    """'275+' -> 275.0; Over/Under lines come from points."""
    nm = ((sel.get("name") or {}).get("fullName") or "").strip()
    m = PLUS_RE.match(nm)
    if m:
        return float(m.group(1))
    return None


def name_variants(participant):
    out = set()
    if not participant:
        return out
    for k in ("fullName", "mediumName", "abbreviation"):
        v = (participant.get(k) or "").strip()
        if v:
            out.add(v)
    full = (participant.get("fullName") or "").strip()
    if full:
        parts = full.split()
        if len(parts) >= 2:
            out.add(parts[-1])
            out.add(f"{parts[0][0]}. {parts[-1]}")
            out.add(" ".join(parts[1:]))
            out.add(" ".join(parts[:2]))
            if len(parts[0]) >= 4 and parts[0].lower() not in ("real", "club", "sporting", "athletic", "atletico", "inter", "west", "east", "north", "south", "new", "san", "los", "las", "saint", "united", "city", "state"):
                out.add(parts[0])
    return {v for v in out if len(v) >= 3}


def mentions(text, variants):
    t = (text or "").lower()
    for v in sorted(variants, key=len, reverse=True):
        vl = v.lower()
        i = t.find(vl)
        while i >= 0:
            before = t[i - 1] if i > 0 else " "
            after = t[i + len(vl)] if i + len(vl) < len(t) else " "
            if not before.isalnum() and not after.isalnum():
                return True
            i = t.find(vl, i + 1)
    return False


def event_sides(event):
    """-> {'home': {...variants}, 'away': {...}}"""
    sides = {}
    for side in ("home", "away"):
        sides[side] = name_variants(event.get(f"{side}Participant") or {})
    name = event.get("name") or ""
    for sep, order in ((" @ ", ("away", "home")), (" vs ", ("home", "away")), (" v ", ("home", "away"))):
        if sep in name and not (sides["home"] and sides["away"]):
            a, b = [x.strip() for x in name.split(sep, 1)]
            sides[order[0]] |= name_variants({"fullName": a})
            sides[order[1]] |= name_variants({"fullName": b})
    sides["HOME"], sides["AWAY"] = sides["home"], sides["away"]
    return sides


def by_name(markets):
    fam = {}
    for m in markets:
        if m.get("status") != "OPEN":
            continue
        fam.setdefault((m.get("name") or "", m.get("type") or ""), []).extend(open_selections(m))
    return fam


def leg_record(market_name, market_type, sel):
    return {"market": market_name, "market_type": market_type, "selection": (sel.get("name") or {}).get("fullName"), "selection_type": sel.get("type"),
            "points": (sel.get("points") or {}).get("decimalPoints"), "price": sel.get("odds", {}).get("formattedOdds"), "decimal": decimal_odds(sel), "id": sel.get("id")}


def implied_pairs(event, markets, max_per_rule=2):
    """Candidate (A implies B) pairs for one event. Returns [{rule, a, b, a_sel, b_sel}]."""
    fam = by_name(markets)
    sides = event_sides(event)
    out = []

    def add(rule, an, at, a, bn, bt, b):
        if a.get("id") == b.get("id") or an == bn and at == bt:
            return
        out.append({"rule": rule, "a": leg_record(an, at, a), "b": leg_record(bn, bt, b), "a_sel": a, "b_sel": b})

    def take(rule, items):
        for k, (an, at, a, bn, bt, b) in enumerate(items[:max_per_rule]):
            add(rule, an, at, a, bn, bt, b)

    ml_key = next((k for k in fam if k[1] in ("MONEYLINE", "THREE_WAY_MONEYLINE") and k[0] in ("Moneyline", "Match Winner", "Match Result", "Fight Winner", "Money Line")), None)
    ml = {s["type"]: s for s in fam.get(ml_key, [])} if ml_key else {}
    spread_key = next((k for k in fam if k[1] == "SPREAD" and k[0] in ("Game Spread", "Run Line", "Puck Line", "Spread", "Match Spread", "Game Handicap", "2-Way Handicap")), None)
    spreads = fam.get(spread_key, []) if spread_key else []
    game_total_key = next((k for k in fam if k[1] == "TOTAL" and k[0] in GAME_TOTAL_NAMES), None)
    game_totals = fam.get(game_total_key, []) if game_total_key else []

    # R1 moneyline <-> spread, same side
    items = []
    for side in ("HOME", "AWAY"):
        m = ml.get(f"{side}_MONEYLINE")
        if not m:
            continue
        pos = sorted([s for s in spreads if s["type"] == f"{side}_SPREAD" and (s.get("points") or {}).get("decimalPoints", 0) > 0 and (s["points"]["decimalPoints"] % 1)], key=lambda s: -s["points"]["decimalPoints"])
        neg = sorted([s for s in spreads if s["type"] == f"{side}_SPREAD" and (s.get("points") or {}).get("decimalPoints", 0) < 0 and (s["points"]["decimalPoints"] % 1)], key=lambda s: s["points"]["decimalPoints"])
        if pos:
            items.append((ml_key[0], ml_key[1], m, spread_key[0], spread_key[1], pos[0]))
        if neg:
            items.append((spread_key[0], spread_key[1], neg[0], ml_key[0], ml_key[1], m))
    take("ml_spread", items)

    # R2 'N+' ladder (LIST) vs Over line (TOTAL) of the same market name
    items = []
    for (n, t), sels in fam.items():
        if t != "LIST" or (n, "TOTAL") not in fam:
            continue
        overs = [s for s in fam[(n, "TOTAL")] if s["type"] == "OVER" and s.get("points")]
        ladder = [(threshold(s), s) for s in sels if threshold(s) is not None]
        for o in overs[:1]:
            line = o["points"]["decimalPoints"]
            above = [s for th, s in sorted(ladder) if th > line]
            if above:
                items.append((n, "LIST", above[0], n, "TOTAL", o))
    take("ladder_over_twin", items)

    # R3 first scorer -> anytime / 1+ / Over 0.5 for the same player
    items = []
    for (n, t), sels in fam.items():
        if t != "LIST" or not n.startswith("First") or "Scorer" not in n:
            continue
        for s in sels[:6]:
            p = (s.get("name") or {}).get("fullName") or ""
            tgt = None
            for (n2, t2), sels2 in fam.items():
                if n2 == f"{p} Touchdowns Scored" and t2 == "LIST":
                    tgt = next((x for x in sels2 if (x.get("name") or {}).get("fullName") == "1+"), None)
                elif n2 == f"{p} Total Goals" and t2 == "TOTAL":
                    tgt = next((x for x in sels2 if x["type"] == "OVER" and (x.get("points") or {}).get("decimalPoints") == 0.5), None)
                elif n2 in ("Anytime Goalscorer", "Anytime Goal Scorer", "Anytime Touchdown Scorer") and t2 == "LIST":
                    tgt = next((x for x in sels2 if (x.get("name") or {}).get("fullName") == p), None)
                if tgt:
                    items.append((n, t, s, n2, t2, tgt))
                    break
    take("first_scorer_anytime", items)

    # R4 win-type market selection (method, round, correct score, margin, HT/FT, win to nil) -> that participant's moneyline
    items = []
    for (n, t), sels in fam.items():
        if t != "LIST" or n not in WIN_TYPE_MARKETS or not ml:
            continue
        for side in ("HOME", "AWAY"):
            m = ml.get(f"{side}_MONEYLINE")
            if not m or not sides[side]:
                continue
            for s in sels:
                nm = (s.get("name") or {}).get("fullName") or ""
                if "Draw" in nm and n not in ("Correct Score",):
                    continue
                if n in ("Half Time/Full Time", "Half-Time/Full-Time") and nm.count("/") == 1:
                    ht, ft = [x.strip() for x in nm.split("/")]
                    if not mentions(ft, sides[side]):
                        continue
                elif n == "Correct Score":
                    sc = SCORE_RE.search(nm)
                    if not sc or not mentions(nm, sides[side]):
                        continue
                    if int(sc.group(1)) <= int(sc.group(2)):  # the named team's goals come first
                        continue
                elif not mentions(nm, sides[side]):
                    continue
                items.append((n, t, s, ml_key[0], ml_key[1], m))
                break
    take("win_type_moneyline", items)

    # R5 MMA/boxing: 'X In Round N' -> Under L rounds (L > N); 'By Points/Decision' -> Over L rounds
    items, items2 = [], []
    rounds_key = next((k for k in fam if k[1] == "TOTAL" and k[0] == "Total Rounds"), None)
    if rounds_key:
        unders = sorted([s for s in fam[rounds_key] if s["type"] == "UNDER" and s.get("points")], key=lambda s: s["points"]["decimalPoints"])
        overs = sorted([s for s in fam[rounds_key] if s["type"] == "OVER" and s.get("points")], key=lambda s: -s["points"]["decimalPoints"])
        for (n, t), sels in fam.items():
            if t != "LIST" or n not in ("Round Betting", "Method & Round Combo"):
                continue
            for s in sels:
                nm = (s.get("name") or {}).get("fullName") or ""
                r = ROUND_RE.search(nm)
                if r:
                    u = next((x for x in unders if x["points"]["decimalPoints"] > int(r.group(1))), None)
                    if u:
                        items.append((n, t, s, rounds_key[0], rounds_key[1], u))
                        break
        for (n, t), sels in fam.items():
            if t != "LIST" or n not in ("Method Of Victory", "Round Betting"):
                continue
            for s in sels:
                nm = (s.get("name") or {}).get("fullName") or ""
                if ("Points" in nm or "Decision" in nm) and overs:
                    items2.append((n, t, s, rounds_key[0], rounds_key[1], overs[0]))
                    break
    take("round_under_rounds", items)
    take("decision_over_rounds", items2)

    # R6 tennis correct set score 'X 2-0' -> X wins set 1 (and set 2); 'X 2-1' -> X wins the match (R4 covers the match winner)
    items = []
    for (n, t), sels in fam.items():
        if t != "LIST" or not n.startswith("Correct Score - Best Of"):
            continue
        for s in sels:
            nm = (s.get("name") or {}).get("fullName") or ""
            sc = SCORE_RE.search(nm)
            if not sc or int(sc.group(2)) != 0:
                continue
            for side in ("HOME", "AWAY"):
                if not mentions(nm, sides[side]):
                    continue
                for set_name in ("1st Set Winner", "2nd Set Winner"):
                    w = next((x for x in fam.get((set_name, "MONEYLINE"), []) if x["type"] == f"{side}_MONEYLINE"), None)
                    if w:
                        items.append((n, t, s, set_name, "MONEYLINE", w))
            if len(items) >= max_per_rule:
                break
    take("set_score_set_winner", items)

    # R7 soccer correct score 'H-A' -> game Over/Under lines, BTTS, team totals, double chance
    items = []
    cs = fam.get(("Correct Score", "LIST"), [])
    if cs and sides["home"]:
        for s in cs:
            nm = (s.get("name") or {}).get("fullName") or ""
            sc = SCORE_RE.search(nm)
            if not sc:
                continue
            h, a = int(sc.group(1)), int(sc.group(2))
            if not (mentions(nm, sides["home"]) or mentions(nm, sides["away"]) or "Draw" in nm):
                continue
            # the first number belongs to the named team; map to home/away
            hg, ag = (h, a) if (mentions(nm, sides["home"]) or "Draw" in nm) else (a, h)
            tot = hg + ag
            o = next((x for x in sorted(game_totals, key=lambda x: -(x.get("points") or {}).get("decimalPoints", 0)) if x["type"] == "OVER" and x["points"]["decimalPoints"] < tot), None)
            if o:
                items.append(("Correct Score", "LIST", s, game_total_key[0], "TOTAL", o))
            u = next((x for x in sorted(game_totals, key=lambda x: (x.get("points") or {}).get("decimalPoints", 0)) if x["type"] == "UNDER" and x["points"]["decimalPoints"] > tot), None)
            if u:
                items.append(("Correct Score", "LIST", s, game_total_key[0], "TOTAL", u))
            btts = fam.get(("Both Teams To Score", "MONEYLINE"), [])
            want = "Yes" if (hg > 0 and ag > 0) else "No"
            b = next((x for x in btts if (x.get("name") or {}).get("fullName") == want), None)
            if b:
                items.append(("Correct Score", "LIST", s, "Both Teams To Score", "MONEYLINE", b))
            if len(items) >= max_per_rule * 2:
                break
    for it in items[: max_per_rule * 2]:
        add("correct_score_totals", *it)

    # R8 team total Over L -> game total Over L' (L' <= L); game Under L' -> team Under L (L >= L')
    items = []
    if game_totals:
        for (n, t), sels in fam.items():
            if t != "TOTAL":
                continue
            m = TEAM_TOTAL_RE.match(n)
            if not m or n in GAME_TOTAL_NAMES or (n, t) == game_total_key:
                continue
            if not (mentions(m.group(1), sides["home"]) or mentions(m.group(1), sides["away"])):
                continue
            for s in sorted([x for x in sels if x["type"] == "OVER" and x.get("points")], key=lambda x: -x["points"]["decimalPoints"])[:1]:
                g = next((x for x in sorted(game_totals, key=lambda x: -(x.get("points") or {}).get("decimalPoints", 0)) if x["type"] == "OVER" and x["points"]["decimalPoints"] <= s["points"]["decimalPoints"]), None)
                if g:
                    items.append((n, t, s, game_total_key[0], "TOTAL", g))
            for g in sorted([x for x in game_totals if x["type"] == "UNDER" and x.get("points")], key=lambda x: x["points"]["decimalPoints"])[:1]:
                s = next((x for x in sorted(sels, key=lambda x: (x.get("points") or {}).get("decimalPoints", 0)) if x["type"] == "UNDER" and x.get("points") and x["points"]["decimalPoints"] >= g["points"]["decimalPoints"]), None)
                if s:
                    items.append((game_total_key[0], "TOTAL", g, n, t, s))
    take("team_total_game_total", items)

    # R9 moneyline -> double chance / draw no bet containing the same team
    items = []
    for side in ("HOME", "AWAY"):
        m = ml.get(f"{side}_MONEYLINE")
        if not m:
            continue
        for (n, t), sels in fam.items():
            if n == "Double Chance":
                dc = next((x for x in sels if mentions((x.get("name") or {}).get("fullName"), sides[side]) and "Draw" in ((x.get("name") or {}).get("fullName") or "")), None)
                if dc:
                    items.append((ml_key[0], ml_key[1], m, n, t, dc))
            if n in ("Draw No Bet", "Tie No Bet"):
                d = next((x for x in sels if x["type"] == f"{side}_MONEYLINE" or mentions((x.get("name") or {}).get("fullName"), sides[side])), None)
                if d:
                    items.append((ml_key[0], ml_key[1], m, n, t, d))
    take("moneyline_double_chance", items)

    # R10 cross-stat player ladders: 'P src N+' -> 'P dst M+' (M <= N*factor), both LIST or TOTAL
    items = []
    for (n, t), sels in fam.items():
        pm = PLAYER_STAT_RE.match(n)
        if not pm:
            continue
        player, stat = pm.group("player"), pm.group("stat")
        for dst, factor in STAT_IMPLIES.get(stat, []):
            for (n2, t2), sels2 in fam.items():
                if n2 != f"{player} {dst}":
                    continue
                src = [(threshold(s) if t == "LIST" else ((s.get("points") or {}).get("decimalPoints", -1) + 0.5 if s["type"] == "OVER" else None), s) for s in sels]
                src = sorted([(th, s) for th, s in src if th is not None], key=lambda z: -z[0])
                dsts = [(threshold(s) if t2 == "LIST" else ((s.get("points") or {}).get("decimalPoints", -1) + 0.5 if s["type"] == "OVER" else None), s) for s in sels2]
                dsts = sorted([(th, s) for th, s in dsts if th is not None], key=lambda z: -z[0])
                for th, s in src[:1]:
                    d = next((x for th2, x in dsts if th2 <= th * factor), None)
                    if d:
                        items.append((n, t, s, n2, t2, d))
    take("cross_stat_ladder", items)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# devig helpers
# ---------------------------------------------------------------------------------------------------------------------
def devig_multiplicative(decimals):
    q = [1.0 / d for d in decimals]
    s = sum(q)
    return [x / s for x in q], s


def devig_power(decimals, tol=1e-10):
    """Find k with sum((1/d)^k) = 1 (power / 'logarithmic' method); harsher on long shots than multiplicative."""
    q = [1.0 / d for d in decimals]
    lo, hi = 0.5, 10.0
    for _ in range(200):
        k = (lo + hi) / 2
        s = sum(x ** k for x in q)
        if abs(s - 1) < tol:
            break
        if s > 1:
            lo = k
        else:
            hi = k
    return [x ** k for x in q], k


def ev(decimal_price, fair_prob):
    return decimal_price * fair_prob - 1.0
