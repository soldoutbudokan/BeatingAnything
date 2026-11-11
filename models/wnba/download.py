# %% Download wehoop parquet files and ESPN rosters (cached)
from __future__ import annotations

import json
import subprocess
import sys

from models.wnba.common import ESPN, RAW, SEASONS, WEHOOP

KINDS = {
    "play_by_play": "pbp/parquet/play_by_play",
    "player_box": "player_box/parquet/player_box",
    "team_box": "team_box/parquet/team_box",
    "wnba_schedule": "schedules/parquet/wnba_schedule",
}


def fetch(url: str, dest, refresh: bool = False):
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return False
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(["curl", "-sSfL", "--retry", "3", "-o", str(tmp), url], check=True)
    tmp.rename(dest)
    return True


# %% wehoop
def download_wehoop(refresh_current: bool = False):
    n = 0
    for y in SEASONS:
        for name, path in KINDS.items():
            dest = RAW / f"{name}_{y}.parquet"
            n += fetch(f"{WEHOOP}/{path}_{y}.parquet", dest, refresh=refresh_current and y == SEASONS[-1])
    return n


# %% ESPN rosters (current only: the site API ignores ?season= for past rosters)
def download_rosters(refresh: bool = False):
    teams_path = RAW / "espn_teams.json"
    fetch(f"{ESPN}/teams", teams_path, refresh)
    teams = json.loads(teams_path.read_text())["sports"][0]["leagues"][0]["teams"]
    out = []
    for t in teams:
        tid = t["team"]["id"]
        dest = RAW / f"espn_roster_{tid}.json"
        fetch(f"{ESPN}/teams/{tid}/roster", dest, refresh)
        out.append(dest)
    return out


def main(refresh: bool = False):
    n = download_wehoop(refresh_current=refresh)
    r = download_rosters(refresh)
    print(f"download: {n} new wehoop files, {len(r)} ESPN rosters")


# %%
if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
