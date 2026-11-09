#!/usr/bin/env python3
"""theScore Bet reader: anonymous session and raw GraphQL calls against the API the public web app uses before login.

Status (November 9, 2026): Cloudflare accepts the client, but the API is location-gated. From a US cloud address
ca-on redirects to ca-default, which returns no anonymous token, and page queries without a token are refused.
Run it from an Ontario connection with TSB_API=https://sportsbook.ca-on.thescore.bet/graphql.

Read-only with respect to money: it never logs in and has no place-bet call.

TSB_API=https://sportsbook.ca-on.thescore.bet/graphql python3 tools/collect_thescore_sgp.py startup
python3 tools/collect_thescore_sgp.py gql --file q.graphql --vars '{"canonicalUrl": "/sport/football/organization/united-states/competition/nfl"}'
"""
# %% imports
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live/thescore"
# ca-on answers only Ontario addresses and redirects everyone else to ca-default, the out-of-province Canadian board
API = os.environ.get("TSB_API", "https://sportsbook.ca-default.thescore.bet/graphql")
APP = "thescore_bet"
APP_VERSION = "26.21.0"
UA = "BeatingAnything-research/1.0 (price reader; no login)"  # states what it is; no browser impersonation
MIN_GAP_S = 0.5  # pause between requests
_last = [0.0]


# %% session
def session():
    p = STATE / "session.json"
    if p.exists():
        return json.loads(p.read_text())
    s = dict(install_id=str(uuid.uuid4()), token=None)
    STATE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s))
    return s


def save_session(s):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "session.json").write_text(json.dumps(s))


def gql(query, variables=None, operation=None, sess=None, api=API, app=APP):
    sess = sess or session()
    headers = {"Content-Type": "application/json", "Accept": "application/json", "x-platform": "web", "x-app-version": APP_VERSION, "x-app": app,
               "x-client": app, "x-install-id": sess["install_id"], "User-Agent": UA}
    if sess.get("token"):
        headers["x-anonymous-authorization"] = f"Bearer {sess['token']}"
    body = dict(query=query, variables=variables or {})
    if operation:
        body["operationName"] = operation
    wait = MIN_GAP_S - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(api, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        out = dict(http_status=e.code, body=e.read().decode("utf8", "replace")[:2000])
    _last[0] = time.time()
    return out


STARTUP = "query Startup { startup { anonymousToken } }"


def startup(api=API, app=APP):
    s = session()
    s["token"] = None
    out = gql(STARTUP, operation="Startup", sess=s, api=api, app=app)
    tok = ((out.get("data") or {}).get("startup") or {}).get("anonymousToken")
    if tok:
        s["token"] = tok
        save_session(s)
    return out, bool(tok)


# %% main
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("startup")
    st.add_argument("--api", default=API)
    st.add_argument("--app", default=APP)
    g = sub.add_parser("gql")
    g.add_argument("--file", required=True)
    g.add_argument("--vars", default="{}")
    g.add_argument("--max-chars", type=int, default=6000)
    g.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "startup":
        out, ok = startup(a.api, a.app)
        txt = json.dumps(out)
        print("token cached" if ok else "no token", txt[:1500] if not ok else "")
    elif a.cmd == "gql":
        out = gql(Path(a.file).read_text(), json.loads(a.vars))
        txt = json.dumps(out, indent=1)
        if a.out:
            Path(a.out).write_text(txt)
        print(txt[:a.max_chars])


if __name__ == "__main__":
    sys.exit(main())
