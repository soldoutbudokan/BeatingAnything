from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import pandas as pd

from beating.cricket import teams as T

VENUES = pd.DataFrame([
    dict(venue_id=v, country=c, cricket_country=cc, utc_offset_hours=off, dst_region=dst)
    for v, c, cc, off, dst in [
        ("chepauk", "India", "India", 5.5, "none"), ("wankhede", "India", "India", 5.5, "none"),
        ("eden", "India", "India", 5.5, "none"), ("chinnaswamy", "India", "India", 5.5, "none"),
        ("guwahati", "India", "India", 5.5, "none"), ("motera", "India", "India", 5.5, "none"),
        ("dubai", "United Arab Emirates", "United Arab Emirates", 4.0, "none"),
        ("kensington", "Barbados", "West Indies", -4.0, "none"), ("cardiff", "Wales", "England", 0.0, "eu"),
        ("scg", "Australia", "Australia", 10.0, "au_south"), ("perth", "Australia", "Australia", 8.0, "none"),
        ("adelaide", "Australia", "Australia", 9.5, "au_south"), ("lords", "England", "England", 0.0, "eu"),
    ]])


def info(day, t1, t2, venue, event="Indian Premier League", match_type="T20", gender="male", team_type="club",
         season=None, number=None, stage=None, winner=None):
    ev = {"name": event}
    if number is not None:
        ev["match_number"] = number
    if stage:
        ev["stage"] = stage
    out = {"winner": winner, "by": {"runs": 1}} if winner else {"result": "no result"}
    return {"dates": [day], "teams": [t1, t2], "venue": venue, "city": None, "event": ev,
            "match_type": match_type, "gender": gender, "team_type": team_type, "season": season or day[:4],
            "outcome": out, "toss": {"winner": t1, "decision": "field"}}


def frame(infos) -> pd.DataFrame:
    m = pd.DataFrame([T.match_row(str(i), x) for i, x in enumerate(infos)])
    m["match_number"] = m.match_number.astype("Int64")
    m["venue_id"] = m.venue_raw
    return T.add_ids(m)


def round_robin(year: str, homes: dict, start_month="04", event="Indian Premier League", hub=None, n_rounds=2):
    """Every team hosts every other team n_rounds/2 times at its home venue (or at `hub`)."""
    teams, out, day = list(homes), [], 1
    for r in range(n_rounds):
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                h, g = (a, b) if r % 2 == 0 else (b, a)
                out.append(info(f"{year}-{start_month}-{day:02d}", h, g, hub or homes[h], event=event,
                                number=day, winner=h))
                day += 1
    return out


class LineageTests(unittest.TestCase):
    def test_renames_share_an_id(self):
        self.assertEqual(T.team_id_for("Kings XI Punjab", "male"), T.team_id_for("Punjab Kings", "male"))
        self.assertEqual(T.canonical_name("Delhi Daredevils", "male"), "Delhi Capitals")
        self.assertEqual(T.canonical_name("Royal Challengers Bangalore", "female"), "Royal Challengers Bengaluru")
        self.assertEqual(T.team_id_for("Rising Pune Supergiants", "male"), "rising_pune_supergiant_m")
        self.assertEqual(T.team_id_for("St Lucia Zouks", "male"), T.team_id_for("St Lucia Stars", "male"))
        self.assertEqual(T.team_id_for("Trinidad & Tobago Red Steel", "male"), "trinbago_knight_riders_m")
        self.assertEqual(T.team_id_for("Birmingham Bears", "male"), "warwickshire_m")
        self.assertEqual(T.team_id_for("Auckland Aces", "male"), T.team_id_for("Auckland", "male"))
        self.assertEqual(T.team_id_for("Swaziland", "male", "international"), "eswatini_m")

    def test_distinct_teams_stay_distinct(self):
        self.assertNotEqual(T.team_id_for("Deccan Chargers", "male"), T.team_id_for("Sunrisers Hyderabad", "male"))
        self.assertEqual(T.lineage_id("sunrisers_hyderabad_m"), "deccan_chargers_m")
        self.assertNotEqual(T.team_id_for("Trent Rockets", "male"), T.team_id_for("Trent Rockets", "female"))
        self.assertEqual(T.team_id_for("Warriors", "male"), "warriors_m")      # CSA franchise
        self.assertEqual(T.team_id_for("Warriors", "female"), "warriors_fairbreak_w")
        self.assertEqual(T.team_id_for("Oval Invincibles", "female"), "mi_london_w")

    def test_lineage_chain_and_countries(self):
        self.assertEqual(T.lineage_id("dhaka_capitals_m"), "dhaka_gladiators_m")
        self.assertEqual(T.lineage_id("chattogram_royals_m"), "chittagong_kings_m")
        self.assertEqual(T.intl_country("ICC World XI"), "")
        self.assertEqual(T.team_id_for("United States of America", "female", "international"),
                         "united_states_of_america_w")
        self.assertEqual(T.comp_country("ipl"), "India")
        self.assertEqual(T.comp_country("cpl"), "West Indies")

    def test_full_members(self):
        self.assertFalse(T.is_full_member("Ireland", "2017-06-21"))
        self.assertTrue(T.is_full_member("Afghanistan", "2017-06-22"))
        self.assertTrue(T.is_full_member("Bangladesh", "2000-06-26"))
        self.assertFalse(T.is_full_member("Bangladesh", "2000-06-25"))
        self.assertTrue(T.is_full_member("Zimbabwe", "2003-01-01"))
        self.assertFalse(T.is_full_member("Scotland", "2024-01-01"))
        self.assertEqual(T.full_member_from("World XI"), "")

    def test_team_table(self):
        m = frame([info("2019-04-01", "Kings XI Punjab", "Delhi Daredevils", "chepauk"),
                   info("2021-04-01", "Punjab Kings", "Delhi Capitals", "chepauk"),
                   info("2021-05-01", "India", "Ireland", "eden", event="Ireland tour of India",
                        team_type="international")])
        t = T.team_table(m)
        self.assertEqual(list(t.columns), T.TEAM_COLUMNS)
        self.assertEqual(t[t.team_id.eq("punjab_kings_m")].team_raw.tolist(), ["Kings XI Punjab", "Punjab Kings"])
        ire = t[t.team_raw.eq("Ireland")].iloc[0]
        self.assertEqual((ire.country, ire.full_member_from, ire.competition_id),
                         ("Ireland", "2017-06-22", "intl_t20_m"))
        self.assertEqual(t.loc[t.team_raw.eq("Kings XI Punjab"), "country"].iloc[0], "India")


class InternationalHomeTests(unittest.TestCase):
    def test_country_rule(self):
        at = T.venue_countries(VENUES)
        self.assertEqual(T.intl_status("West Indies", "India", at["kensington"]), "home")
        self.assertEqual(T.intl_status("India", "West Indies", at["kensington"]), "away")
        self.assertEqual(T.intl_status("Barbados", "England", at["kensington"]), "home")
        self.assertEqual(T.intl_status("England", "Pakistan", at["cardiff"]), "home")
        self.assertEqual(T.intl_status("Pakistan", "Australia", at["dubai"]), "neutral")
        self.assertEqual(T.intl_status("", "India", at["dubai"]), "neutral")

    def test_table_and_function(self):
        m = frame([info("2020-01-01", "Pakistan", "Australia", "dubai", event="Australia tour of UAE",
                        match_type="Test", team_type="international"),
                   info("2020-02-01", "Australia", "India", "scg", event="India tour of Australia",
                        match_type="ODI", team_type="international")])
        st, _ = T.home_status_table(m, VENUES)
        self.assertEqual(st.home_status1.tolist(), ["neutral", "home"])
        self.assertEqual(st.home_status2.tolist(), ["neutral", "away"])
        self.assertEqual(T.home_status("india_m", "australia_m", "international", "scg", venues=VENUES,
                                       team_countries=("India", "Australia")), "away")


class ClubHomeTests(unittest.TestCase):
    HOMES = {"Chennai Super Kings": "chepauk", "Mumbai Indians": "wankhede", "Kolkata Knight Riders": "eden",
             "Royal Challengers Bangalore": "chinnaswamy"}

    def statuses(self, infos):
        m = frame(infos)
        st, homes = T.home_status_table(m, VENUES)
        return m.merge(st, on="match_id"), homes

    def test_home_away_from_full_season(self):
        m, homes = self.statuses(round_robin("2019", self.HOMES))
        self.assertTrue((m.home_status1_full == "home").all() and (m.home_status2_full == "away").all())
        tab = homes.table()
        self.assertEqual(sorted(tab.venue_id), sorted(self.HOMES.values()))
        self.assertTrue((tab.rule == "share").all())
        # the first matches of the first season have no history: neutral as of the day
        self.assertEqual(m.home_status1.iloc[0], "neutral")
        self.assertEqual(m.home_source1.iloc[0], "none")
        self.assertEqual(m.home_status1.iloc[-1], "home")

    def test_abroad_host_share_and_hub_seasons_are_neutral(self):
        m, homes = self.statuses(round_robin("2020", self.HOMES, hub="dubai"))   # IPL 2020 in the UAE
        self.assertTrue((m.home_status1_full == "neutral").all())
        self.assertEqual(set(homes.neutral_venues().reason), {"abroad"})
        m, homes = self.statuses(round_robin("2022", self.HOMES, hub="wankhede"))  # one Indian hub ground
        self.assertTrue((m.home_status1_full == "neutral").all())
        self.assertEqual(set(homes.neutral_venues().reason), {"host_share"})
        csk, mi, kkr, rcb = self.HOMES
        hub = round_robin("2021", self.HOMES) + [   # a hub ground where no side plays in over half the games
            info(f"2021-05-0{k}", a, b, "guwahati", number=20 + k)
            for k, (a, b) in enumerate([(csk, mi), (kkr, rcb), (csk, kkr), (mi, rcb)], 1)]
        m, homes = self.statuses(hub)
        nv = homes.neutral_venues().set_index("venue_id").reason
        self.assertEqual((nv["guwahati"], nv["chepauk"]), ("no_dominant_team", ""))
        self.assertTrue((m.home_status1_full[m.venue_id.eq("guwahati")] == "neutral").all())

    def test_secondary_ground_and_knockouts(self):
        season = round_robin("2023", self.HOMES, n_rounds=4)
        season[0]["venue"] = season[1]["venue"] = "guwahati"   # two of CSK's six home games moved to Guwahati
        season += [info("2023-05-28", "Mumbai Indians", "Kolkata Knight Riders", "motera", stage="Final",
                        winner="Mumbai Indians"),
                   info("2023-05-26", "Mumbai Indians", "Kolkata Knight Riders", "motera", stage="Qualifier 2")]
        m, homes = self.statuses(season)
        tab = homes.table().set_index(["team_id", "venue_id"]).rule
        self.assertEqual(tab[("chennai_super_kings_m", "guwahati")], "secondary")
        self.assertNotIn("motera", homes.table().venue_id.tolist())   # knockouts do not define homes
        self.assertEqual(m.loc[m.stage.eq("Final"), "home_status1_full"].iloc[0], "neutral")

    def test_asof_uses_only_earlier_matches(self):
        first = round_robin("2018", self.HOMES)
        second = round_robin("2019", {**self.HOMES, "Chennai Super Kings": "guwahati"}, n_rounds=4)
        a, _ = self.statuses(first + second[:3])
        b, _ = self.statuses(first + second)
        cols = ["home_status1", "home_status2", "home_source1", "home_source2"]
        pd.testing.assert_frame_equal(a[cols].reset_index(drop=True), b[cols].iloc[:len(a)].reset_index(drop=True))
        # early 2019: CSK's 2018 home stands in; once enough 2019 matches exist the new ground counts
        csk = b[b.season.eq("2019") & b.team1_raw.eq("Chennai Super Kings")]
        self.assertTrue(csk.home_source1.iloc[0].startswith("prev:"))
        self.assertEqual(csk.home_status1.iloc[-1], "home")
        self.assertEqual(csk.home_status1_full.tolist(), ["home"] * len(csk))

    def test_forecast_uses_previous_season(self):
        m = frame(round_robin("2024", self.HOMES))
        hv = T.home_venues_at(m, "2025-03-01", VENUES)
        mi, csk = "mumbai_indians_m", "chennai_super_kings_m"
        args = dict(team_type="club", competition_id="ipl", season="2025", day="2025-03-22", homes=hv, venues=VENUES)
        self.assertEqual(T.home_status(mi, csk, venue_id="wankhede", **args), "home")
        self.assertEqual(T.home_status(csk, mi, venue_id="wankhede", **args), "away")
        self.assertEqual(T.home_status(csk, mi, venue_id="motera", **args), "neutral")
        early = T.home_venues_at(m, "2024-04-03", VENUES)   # cutoff before most of the season
        self.assertEqual(early.seasons["ipl"]["2024"].n, 2)


class StartSlotTests(unittest.TestCase):
    def slots(self, infos):
        m = frame(infos)
        return T.start_slots(m, VENUES).set_index("match_id")

    def test_league_double_headers(self):
        bbl = dict(event="Big Bash League")
        s = self.slots([info("2023-04-01", "Mumbai Indians", "Kolkata Knight Riders", "wankhede", number=2),
                        info("2023-04-01", "Chennai Super Kings", "Delhi Capitals", "chepauk", number=1),
                        info("2023-04-02", "Mumbai Indians", "Chennai Super Kings", "wankhede", number=3),
                        info("2023-12-31", "Sydney Sixers", "Perth Scorchers", "scg", number=1, **bbl),
                        info("2023-12-31", "Perth Scorchers", "Hobart Hurricanes", "perth", number=2, **bbl),
                        info("2024-01-01", "Sydney Sixers", "Hobart Hurricanes", "scg", number=3, **bbl),
                        info("2024-01-01", "Adelaide Strikers", "Perth Scorchers", "adelaide", number=4, **bbl),
                        info("2023-06-01", "Surrey", "Kent", "lords", event="Vitality Blast")])
        want = ["night", "day", "night", "unknown", "night", "day", "night", "unknown"]
        self.assertEqual(s.start_slot.tolist(), want)
        self.assertEqual(s.source[3], "bbl_double_header_ambiguous")
        self.assertEqual(s.source[7], "no_rule")

    def test_women_before_men_and_tests(self):
        def intl(day, a, b, venue, match_type):
            return info(day, a, b, venue, event=f"{b} tour of India", match_type=match_type, team_type="international")
        s = self.slots([info("2024-07-23", "Welsh Fire", "Trent Rockets", "cardiff", gender="female",
                             event="The Hundred Women's Competition"),
                        info("2024-07-23", "Welsh Fire", "Trent Rockets", "cardiff", event="The Hundred Men's Competition"),
                        intl("2019-11-22", "India", "Bangladesh", "eden", "Test"),
                        intl("2019-11-14", "India", "Bangladesh", "chepauk", "Test"),
                        intl("2019-12-15", "India", "West Indies", "chepauk", "ODI"),
                        intl("2019-12-16", "Scotland", "Oman", "chepauk", "ODI")])
        self.assertEqual(s.start_slot.tolist(), ["day", "day_night", "day_night", "day", "day_night", "unknown"])
        self.assertEqual(s.source[2], "pink_ball_list")

    def test_slot_lookup_defaults_to_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dn.csv"
            pd.DataFrame([dict(match_id="1", start_date="2020-01-01", competition_id="ipl", venue_id="x",
                               start_slot="night", source="s", confidence="high", note="")]).to_csv(p, index=False)
            self.assertEqual((T.start_slot_for(1, p), T.start_slot_for("2", p)), ("night", "unknown"))


class ScanTests(unittest.TestCase):
    def test_scan_zip_reads_info_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "all.zip"
            with zipfile.ZipFile(z, "w") as f:
                for k, x in enumerate([info("2021-04-09", "Mumbai Indians", "Royal Challengers Bangalore",
                                            "chepauk", number=1, winner="Royal Challengers Bangalore"),
                                       info("2021-04-10", "Chennai Super Kings", "Delhi Capitals", "wankhede",
                                            number=2)]):
                    f.writestr(f"{1254058 + k}.json", json.dumps({"meta": {"data_version": "1.2.0"}, "info": x,
                                                                   "innings": []}, indent=1))
                f.writestr("wi_201706.json", json.dumps({"info": info("2017-06-01", "A", "B", "x")}))
                f.writestr("README.txt", "x")
            m = T.scan_matches(z)
        self.assertEqual(m.match_id.tolist(), [1254058, 1254059, 90201706])
        self.assertEqual(m.file_stem.iloc[-1], "wi_201706")
        self.assertEqual(m.match_id.iloc[-1], 90201706)
        m = m.iloc[:2]
        self.assertEqual(m.competition_id.tolist(), ["ipl", "ipl"])
        m["venue_id"] = m.venue_raw
        m = T.add_ids(m)
        self.assertEqual(m.winner_id.iloc[0], "royal_challengers_bengaluru_m")
        self.assertEqual(m.team2.iloc[0], "Royal Challengers Bengaluru")
        self.assertEqual(m.result.tolist(), ["win", "no result"])


if __name__ == "__main__":
    unittest.main()
