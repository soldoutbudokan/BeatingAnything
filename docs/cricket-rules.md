# Cricket playing conditions and competitions

Written October 24, 2026, for the ball-by-ball model in `CRICKET-MODEL-PLAN.md` (sections 4.5 and 5).

| File | Role |
| --- | --- |
| `beating/cricket/competitions.py` | Cricsheet event -> `competition_id`, tier, `event_id`, `assoc_match`; `season_key` |
| `beating/cricket/rules.py` | `rules_for` / `rules_for_match`, the data scan and `validate` |
| `config/cricket-rules.json` | the playing-conditions timeline (ordered layers, match overrides, documented data anomalies) |
| `reports/cricket-rules-validation.json` | every data check, row by row, with a status |
| `data/derived/cricket/competition-events.csv` | all 1,445 distinct (event name, match type, gender, team type) rows with their mapping, counts and first/last dates |
| `tests/test_cricket_rules.py` | 23 unit tests on small hand-built fixtures, no network and no zip |
| `tests/test_cricket_rules_verify.py` | 6 regression tests for the fixes from the independent verification (`drs_allowed`, associate DRS, caught crossing, Hundred detection) |

Rebuild the report and event list (about 1 CPU-minute, 2 workers):

```
flock .../cricket-heavy.lock env PYTHONPATH=. .venv/bin/python -m beating.cricket.rules --workers 2
```

## Using it

```python
from beating.cricket.competitions import competition_for, season_key
from beating.cricket.rules import rules_for, rules_for_match

comp = competition_for(info)          # Competition(competition_id='ipl', tier='franchise_major', fmt='T20', event_id='ipl', ...)
season_key(info)                      # 'ipl:2023'
rules_for_match(info, match_id=match_id)    # competition, teams, stage and date come from info
rules_for("intl_test_m", "TEST", "male", "2021-02-05", teams=["India", "England"])
rules_for("blast", "T20", "male", "2023-07-15", stage="Final")
```

`rules_for(competition_id, fmt, gender, date, *, event_id, teams, official, assoc_match, knockout, stage, scheduled_days, match_id)` returns the section-5 fields listed under Deviations plus `_layers` (which layer set each field). The derived fields are `super_over_this_match` (`knockout_only` turned into `none`, `single` or `repeat` for this match), `min_balls_for_result` and `drs_allowed`. `drs_allowed` is the plan's "rules allow DRS": true when `drs_available` is true or `drs_scope` is `selected`. Use it, not `drs_available` (the competition default), in the plan's per-match `drs_available` formula; otherwise the 172 `selected`-scope matches with recorded reviews would be dropped from DRS fits. `str(comp)` is the `competition_id`, so the returned object can stand in for the id string.

## Competitions

**Method.** A match with `team_type == 'international'` always maps to `intl_<t20|odi|test>_<m|w>` from the Cricsheet match type (Test/MDM -> test, ODI/ODM -> odi, T20/IT20 -> t20). The event name only sets `event_id`: `icc_cwc`, `icc_t20wc`, `icc_ct`, `icc_wtc_final`, `icc_qualifier` (any "qualifier", "region" or "play-off" event), `icc_league` (World Cricket League, CWC League 2, Challenge League), `icc_intercontinental`, `icc_womens_championship`, `asia_cup`, `multisport`, `bilateral` ("X tour of Y", "X in Y ... Series", "X v Y", named trophies such as The Ashes and Border-Gavaskar), `multi_nation` (tri-series, quadrangulars and other cups), `intl_unnamed` (no event name). `assoc_match` is true when either side was not an ICC full member on the match date. Zimbabwe counts from 1992-07-06, Bangladesh from 2000-06-26, and Ireland and Afghanistan from 2017-06-22. The World, Asia and Africa XIs count as full members. `official` is false for IT20, ODM and MDM internationals. Tier is `intl_full` for official matches between two full members and `intl_assoc` otherwise.

A club match maps by its normalised event name through an ordered alias table. That table absorbs sponsor and format renames: Indian Premier League; (KFC) Big Bash League; NatWest T20 Blast, Vitality Blast, Vitality Blast Men, Friends Provident/Friends Life t20 and Twenty20 Cup -> `blast`; Vitality Blast Women -> `blast_w`; LV=, Specsavers and Rothesay County Championship, and the Bob Willis Trophy -> `county_championship`; Royal London, Metro Bank, Clydesdale Bank 40 and Yorkshire Bank 40 One-Day Cup -> `eng_one_day_cup`; Rachael Heyhoe Flint Trophy and ECB Women's One-Day Cup -> `eng_women_one_day`; (Marsh) Sheffield Shield; The Marsh Cup, Marsh One-Day Cup, Ryobi, Matador and JLT One-Day Cup, and One-Day Cup (Australia) -> `aus_one_day_cup`; HRV Cup, HRV Twenty20, Georgie Pie, Burger King and Dream11 Super Smash -> `super_smash`; CSA T20 Challenge, Ram Slam, MiWAY and CSA Pro20 -> `csa_t20`; The Hundred Men's and Women's Competition -> `hundred_m` and `hundred_w` (`fmt = HUNDRED`). The table also maps Ranji Trophy, Vijay Hazare, Quaid-e-Azam, Ford Trophy and others that are not in this Cricsheet build. A club event that matches nothing falls back to `other_<fmt>_<m|w>` with `generic=True` and tier `domestic_minor`.

Tiers: `franchise_major` covers IPL, BBL, PSL, CPL, SA20, ILT20, MLC, BPL, LPL, Mzansi Super League, both Hundreds, WPL, WBBL, WCPL and the Women's Cricket Super League. `domestic_major` covers the national first-class, one-day and T20 championships of full members, including the Blast. `domestic_minor` covers the Irish Inter-Provincials, Women's T20 Challenge, FairBreak, Nepal Premier League, European T20 Premier League and the generic ids.

**Coverage (all 23,132 matches).** There are 1,117 distinct event names (plus matches with none) and 1,445 (name, match type, gender, team type) rows. They map to 46 competition ids: intl_full 5,306 matches, intl_assoc 5,466, franchise_major 4,872, domestic_major 7,140, domestic_minor 348. All 89 matches without an event name are internationals. They map to their `intl_*` id with `event_id = intl_unnamed`, which is the only generic mapping in this build. No club match falls back to a generic id. Cricsheet match ids are not all integers: 25 files are named `wi_2017xx` / `wi_21xxxx`, and both modules key them as strings.

## The rules timeline

`config/cricket-rules.json` is a list of layers. Each layer has a `when` filter (format, gender, team type, competition, tier, event, official, associate, `teams_any`, `teams_all`, `knockout` from the Cricsheet stage, `stage_regex`), a half-open date range `[from, until)`, the fields it sets, a `source` (`memory`, `data` or `memory+data`) and a note. Layers apply in file order, and later ones override earlier ones field by field. The order is: format defaults, then international DRS by era, team and event exceptions (India, associates, women's series, ICC events), then each domestic competition. `match_overrides` mark the known four-day men's Tests: South Africa v Zimbabwe 2017, England v Ireland 2019 and 2023, Ireland v Zimbabwe 2024, England v Zimbabwe 2025. They also mark the five-day 2023 women's Ashes Test. `scheduled_days_rules` sets 98 overs a day and a 150-run follow-on for a four-day Test.

Main eras (`d` = the value comes from Cricsheet data, `m` = from memory):

| Field | Tests (men) | ODIs (men) | T20Is | Leagues and domestic |
| --- | --- | --- | --- | --- |
| DRS | trial Jul 2008 (3 reviews, d); selected series 2009; all from 2009-11-24 (d); India none 2008-08 to 2016-10 (d) | from Jan 2011 (d); India none in bilaterals 2008-2016 except ICC events (d); associates none outside World Cups and the Asia Cup (d) | from Oct 2017 (d); women only in ICC events and big-five series from 2022 (d) | IPL 2018, PSL 2018 (2017 playoffs), BPL 2018/19, LPL 2020, CPL 2022 (2018 playoffs), BBL 2022/23, WBBL selected 2022-24 then all, Hundred 2021, SA20/ILT20/MLC/WPL from the start; Blast and SMAT knockouts only (all d) |
| Reviews per innings | 2; top-up after 80 overs 2013-10 to 2017-09 (d); 3 from Jul 2020 (d) | 2 Jan-Apr 2011 (d); 1 to Jun 2020; 2 from Jul 2020 (d) | 1; 2 from Jul 2020 (d) | 1 at first; 2 from IPL 2022, PSL 2021, BPL/LPL 2021; Hundred, BBL and WBBL stay at 1 (d) |
| Umpire's call retains review | from 2017-09-28 (m+d) | same | same | same |
| Free hit | none | none; front foot Oct 2007 (d); all no-balls Jul 2015 (m+d) | front foot 2007; all Jul 2015 (m+d) | ECB white ball and Hundred front foot to 2024, all from 2025 (d); BBL none in 2011-13 (d) |
| Powerplays | - | 1-15 to Jul 2005 (m); 1-10 + two fielding blocks; 2008 one batting + one fielding; Oct 2011 both in 16-40; Oct 2012 batting only; Jul 2015 1-10/11-40/41-50 (all d) | overs 1-6 (d) | BBL power surge from 2020/21 and WBBL from 2022/23 (4 + 2, d); LPL second block overs 16-17 from 2024 (d); Hundred 25 balls (d) |
| No-ball penalty | 1 | 1 | 1 | 2 in the County Championship; 2 in Blast, One-Day Cup and Hundred to 2025, then 1 (d) |
| Days, overs per day, follow-on | 5 days, 90 overs, 200 (d); four-day Tests 98 overs, 150 (m); women 4 days, 100 overs, 150 (d) | - | - | County, Shield, Plunket: 4 days, 96 overs, 150; finals 5 days (d); SLC Major League 3 days, 90 overs (d) |
| Super over | none | ties stand; ICC knockouts from 2011; repeat in the Super League era 2020-23, ICC events from 2023, women from 2020, men's bilaterals from 2025 (d, low confidence) | bowl-out to 2008, then single, repeat from Oct 2019 (m+d) | repeat in franchise leagues; Blast, Hundred, Super Smash and CSA group ties stand (d) |
| Minimum overs for a result | - | 20 (d); English domestic 10 (d) | 5 (d) | Hundred 25 balls (m) |
| Tactical subs | - | supersub Jul 2005 to Mar 2006 (d) | supersub 2005 (d) | BBL X-factor 2020-22 (d); impact player IPL 2023+, ILT20 2023/24+, SMAT 2022-24, LPL 2026 (d) |
| Two new balls | - | Oct 2011 (m); two balls until over 34 from Jul 2025 (m) | - | Oct 2011 (m) |
| Caught: crossing counts | to 2022-09 (m+d) | to 2022-09 (m+d) | to 2022-09 (m+d) | ECB domestic and IPL to 2021, Australian domestic to Aug 2022, the Hundred never (d) |
| New ball available | after 80 overs (m) | - | - | after 80 overs (m) |
| Informational | stop clock from Jun 2025 (m) | stop clock from Jun 2024 (m) | slow-over-rate fielding penalty from Jan 2022; stop clock Jun 2024 (m) | slow-over-rate penalty in the Hundred and in IPL from 2023 (m); concussion substitutes in internationals from Aug 2019 (d) |

The Hundred is encoded as Cricsheet stores it: 20 "overs" of 5 balls. The quota is 4 sets (20 balls), the powerplay is sets 1-5, and the data never shows more than two consecutive sets (10 balls) by one bowler.

## Validation against Cricsheet

`validate` evaluates `rules_for_match` for every match and compares it with what the data shows. The table below gives the status counts in `reports/cricket-rules-validation.json`. "explained" means a documented data anomaly (listed below), and "partial_selected" means competitions where `drs_scope = selected`.

| Check | Rows | Result |
| --- | --- | --- |
| (a) DRS observed (any review; matches whose `info.missing` lists reviews are excluded) | 175 competition-seasons | 167 ok, 8 partial (women's internationals in some years, WBBL 2022-24, 2011 Tests where India's England series used DRS) |
| (b) most unsuccessful reviews by one team in an innings | 255 competition-years and families, 9,474 team-innings | all ok; one "limit not reached" (MLC 2023, one innings at 2); 3 single-innings anomalies; no failed review in a match whose rules have no DRS (`n_failed_without_drs_in_rules`, 54 team-innings in 34 matches before the associate layers of conflict 19 were added) |
| (c) powerplay windows from `innings.powerplays` | 413 competition-seasons, 23,338 full-length innings | all ok (mandatory windows match in at least 80% of innings, optional blocks sit inside the rules' windows) |
| (d) overs per innings, balls per over, bowler quotas | 46 competitions | all ok; `info.overs` is 50 in 19 T20Is, and 8 innings credit one bowler with one over too many |
| (e) follow-ons | 6 competitions, 353 follow-ons | min leads: Tests 180 (day-1 washout, explained), women's Tests 165, county 150, Plunket 153, Shield 170, SLC 150. Enforcement rate when allowed: Tests 51%, county 75%, Shield 15% |
| (f) impact player and other tactical replacements | 16 competition-seasons | ok; one explained WBBL record |
| free hit (protected dismissals on balls after a no-ball) | 58 competition-rule cells | all ok |
| caught crossing (old non-striker on strike after a mid-over catch) | 76 competition-rule cells | all ok: 27-55% (white ball) and 5-7% (first-class) while crossing counts, 17 of 28,548 international catches after October 2022 |
| no-ball penalty (1 vs 2 extras) | 413 competition-years | all ok |
| super overs in ties | 47 cells | all ok; 4 explained single ties |
| minimum overs in D/L results | 32 competitions | ok; one explained 19.5-over target |
| Test days and overs per day in draws | 6 competitions | all ok |

Headline data facts behind the plan's section 5: the largest number of unsuccessful, non-umpire's-call reviews by one team in one Test innings is 3 in every year from 2020 to 2026. In ODIs and T20Is the maximum is 2 from 2020 and never reaches 3. In T20Is it is 1 from 2017 to 2019. In club T20 it is 1 until 2020 and 2 from 2021, apart from a single 2019 PSL innings. Ball-after-no-ball protected dismissals run at 0.74 of the base rate when there is no free hit (ODIs 2002-07). Under front-foot-only free hits they run at 0.15-0.46 of it (0.66 in the small women's T20I sample). Under all-no-ball free hits they are zero in 17,976 balls.

## Data versus memory: conflicts and the final choice

Data wins wherever it can see the rule. Each conflict is also noted on its layer in the config.

1. **ODI free hit start.** The task brief put the ODI front-foot free hit in 2011. Data shows the ball after a no-ball ends in a bowled/caught/lbw/stumped dismissal 1.85% of the time to September 2007 (49 of 2,653). The rate is 0.81% from October 2007 to September 2011 (7 of 863), 0.89% from October 2011 to June 2015 (6 of 676), and 0 of 2,045 afterwards. Nothing changes in 2011. **Choice:** front foot from 2007-10-01, all no-balls from 2015-07-05.
2. **The 2020 extra review did not lapse.** From memory, the extra unsuccessful review added in July 2020 was a temporary measure. Data shows 3 non-umpire's-call failures by one team in a Test innings every year from 2020 to 2026, and 2 (never 3) in ODIs and T20Is. **Choice:** Tests 3 and white-ball internationals 2 from 2020-07-01, still in force.
3. **ODI reviews in early 2011.** From memory, ODIs allowed one unsuccessful review per innings from the start of DRS. In the January 2011 Australia v England ODIs and the 2011 World Cup, 37 of 137 team-innings with a failed review used two, and none used three. From August 2011 the maximum is one. **Choice:** 2 reviews until 2011-05-01, then 1.
4. **When T20 went to two reviews.** The plan states the pooled T20 data shows "1 until 2018 and 2 from 2019". The only 2019 innings with two failures is one Quetta Gladiators innings in the PSL. Every other 2019 team-innings, 146 of 147 in club T20, has at most one. The real step is August 2020 for T20Is and competition by competition in the leagues: PSL 2021, BPL and LPL 2021/22, IPL 2022, CPL, SA20, ILT20, MLC and WPL from their DRS start. The Hundred, BBL and WBBL stay at one. **Choice:** per-competition dates from data. The PSL 2019 innings is treated as an untagged umpire's call.
5. **ECB free hits were front-foot only until 2024.** The expectation was that domestic competitions followed the 2015 ICC change to free hits for all no-balls. In the Blast, protected dismissals still happen on free-hit balls in every season from 2014 to 2024 (43 of 1,832 balls, 0.44 of the base rate). The same holds in the One-Day Cup (2015-23), the Rachael Heyhoe Flint Trophy (2022-23), the Charlotte Edwards Cup (2024) and the Hundred (2022-23), and the rate is zero from 2025. **Choice:** front foot to 2024, all no-balls from 2025. The 2014 One-Day Cup has 4 protected dismissals in 133 such balls, above the base rate, so it is set to no free hit.
6. **Two-run no-balls beyond the County Championship.** From memory, only the County Championship has 2-run no-balls. Data shows every no-ball in the Blast, the One-Day Cup and both Hundreds carries 2 extras through 2025, and all of them carry 1 in 2026. The County Championship still carries 2 in 2026. ECB women's competitions and the Women's Cricket Super League from 2017 carry 1, and the 2016 Super League carried 2. **Choice:** data.
7. **BBL free hits in BBL|01-02.** The expectation was free hits from the first season. Data shows 4 protected dismissals in 35 balls after no-balls in 2011-13 (more than the base rate) and none in about 500 since. **Choice:** no free hit until 2013/14, then all no-balls.
8. **WBBL power surge.** The expectation was the BBL power surge (2020/21) in both leagues. The WBBL records a 6-over powerplay until 2021/22 and the 4 + 2 structure from 2022/23. **Choice:** data.
9. **DRS in the Blast and SMAT.** The expectation was no DRS. Data shows reviews only in knockouts: Blast Finals Day 2022 (not the quarter-finals), all knockouts in 2023 and 2025, none in 2024 or 2026, and SMAT knockouts from 2023/24. **Choice:** `drs_scope = knockouts` for those seasons (Blast 2022 uses a semi/final stage filter).
10. **Minimum overs in English one-day cricket.** From memory, the List A minimum is 20 overs. The One-Day Cup (2014, 2015) and the women's one-day competition (2023) have D/L results from 10-over chases. **Choice:** 10.
11. **ODI super overs.** From memory, bilateral ODI ties stand and only ICC knockouts use a super over. Data shows bilateral ties went to super overs in 2020-23, the Super League and Women's Championship period (Zimbabwe v Pakistan 2020, West Indies v South Africa women 2021 and 2022). The 2023 World Cup Qualifier group tie also went to one, as did League 2 ties in 2025 and Bangladesh v West Indies in October 2025. Sri Lanka v India in 2024 stood as a tie. **Choice:** the layered timeline in the config. The 2025 men's bilateral change rests on one match (low confidence).
12. **Women's ODI powerplays.** The expectation was the men's P1/P2/P3 structure from 2015. Cricsheet records only overs 1-10 for women's ODIs, plus a 5-over batting block (mostly overs 36-40) until 2021. **Choice:** `powerplay_overs` follows the recorded windows. `fielders_outside` keeps the memory value of 4 outside in overs 11-50, so any P3 effect is not modelled.
13. **Super Smash, CSA T20 and Women's Cricket Super League ties.** The expectation was super overs as in the franchise leagues. Ties since 2022/23 (five in the Super Smash) and most CSA T20 and WCSL ties stood. **Choice:** `knockout_only`.
14. **Asia Cup DRS.** The expectation was ICC-event conditions. No Asia Cup review appears in 2004-2016, and they appear in almost every match from 2018. **Choice:** DRS from 2018.
15. **Women's DRS.** The expectation was DRS in women's internationals from about 2017. Reviews appear in 27% of 2017 World Cup matches and in no women's T20I before the 2018 T20 World Cup. Since 2022 they appear in 87% of ODIs and 62% of T20Is between two of Australia, England, India, New Zealand and South Africa, against 0-30% elsewhere. **Choice:** `selected` by default, with DRS on for ICC events and big-five bilateral series from 2022.
16. **Sri Lanka Major League length.** The expectation was a four-day first-class competition. 83 of 84 draws span three dates, with overs per day at p90 88. The 2025 final spans four dates. **Choice:** 3 days and 90 overs, finals 4 days.
17. **Intercontinental Cup overs per day.** There is no firm memory. Its three drawn matches reach 93 overs per day, above any five-day Test draw (maximum 90.0). **Choice:** 96 (low confidence).
18. **The Hundred's DRS in 2021.** There was no firm memory either way. Reviews appear in 72-84% of 2021 matches, with at most one failure per team-innings. **Choice:** DRS from 2021 with one review.
19. **Associates against full members.** The first version set `drs_scope = none` for every associate match outside ICC events. Data shows reviews in 34 such matches: the Netherlands' CWC Super League ODIs (2021-2023), Ireland v South Africa and Australia (2016) and in England (2017), Barbados at the 2022 Commonwealth Games, Bangladesh v Netherlands T20Is (2025) and the Super Six of the 2023 World Cup Qualifier. **Choice:** `selected` for associate v full-member internationals (men from 2016, women from November 2018) and for associate matches of the 2023 Qualifier.
20. **Caught: does crossing count?** The plan gives 2022-10-01 internationally and IPL 2022. Data agrees and adds that ECB domestic competitions (County Championship, Blast, One-Day Cup, Charlotte Edwards Cup, Rachael Heyhoe Flint) switched for the 2022 season, the Marsh Cup from September 2022, and the Hundred never let crossing count. **Choice:** data.

The data agrees with memory on these points: the 2008 Test trial with 3 reviews; the official Test start in November 2009; India's refusal of DRS until November 2016; the Test top-up after 80 overs from October 2013 to September 2017; umpire's-call retention from 2017-09-28; T20I DRS from October 2017; IPL DRS from 2018 with 2 reviews from 2022; IPL impact player from 2023 (291 of 293 matches); ILT20 impact player from 2023/24; SMAT dropping the impact player in 2024/25; ODI supersubs from July 2005 to March 2006; the BBL X-factor in 2020-22; the ODI powerplay eras of 2005, 2008, 2011, 2012 and 2015; the 6-over T20 and 25-ball Hundred powerplays; 20-ball Hundred quotas with 5- or 10-ball ends; 90 overs a day and a 200-run follow-on in five-day Tests; 100 overs a day in women's Tests; and a 150-run follow-on in four-day cricket.

## Data anomalies (kept, marked "explained" in the report)

- Ireland v Pakistan 2018 (1127284): follow-on enforced with a lead of 180 in a five-day Test. Day 1 was washed out, so Law 14.1.3 applied the four-day threshold of 150. The timeline does not model lost days.
- PSL 2019 (1168827): one innings with two failed reviews against one allowed.
- Tests 892517 (Melbourne 2015) and 1104284 (Dhaka 2017): Australia credited with three failed fielding reviews before over 80, against two allowed. These are likely mis-attributed reviews.
- Marsh Cup 1322388: D/L result on a 19.5-over target.
- WBBL 2020/21: one supersub-coded replacement.
- `info.overs = 50` in 12 men's and 7 women's T20Is that have 20-over innings. Eight innings credit a bowler with 5 T20 overs or 11 ODI overs (attribution errors).
- Ties without the expected super over: Blast quarter-final 2020 (1207789), Scotland v Ireland T20I 2018 (1142504), Bangladesh v India women ODI 2023 (1382168). There is also one CSA T20 group tie with a super over (1299613).

## Limitations

- Several rules are invisible in Cricsheet: two new balls, the 2025 34-over ball change, fielders outside the circle outside recorded powerplays, stop clocks, slow-over-rate penalties, concussion-sub rules in domestic cricket, bouncer limits. These are marked `memory`, and the informational ones are not used by the engines.
- DRS availability is series-specific in some eras (India 2008-16, women's bilaterals, Zimbabwe, Bangladesh and West Indies hosts in early years). `drs_available` is the competition default. Fits on history should use each match's observed reviews (`drs_observed`), and `drs_scope = selected` flags the partial cases.
- Umpire's-call flags exist only from late 2017, so earlier review counts treat every failed review as lost. That is also the rule then, but it means a mislabelled review cannot be told apart.
- The knockout flag comes from the Cricsheet `event.stage` string, which many matches lack.
- Four-day men's Tests are listed by match id from memory. All five finished inside four dates, so the data is consistent with the list but cannot confirm it.
- The follow-on threshold after a lost first day (Law 14.1.3) and pro-rata powerplays and quotas in reduced matches are not resolved here. The simulator must apply them from the match state.
- The free-hit check compares against each competition's base rate of protected dismissals. Phase mix (no-balls cluster in some overs) moves the no-free-hit ratio to about 0.75 rather than 1.

## Deviations from the plan

- `competition_for` returns a frozen `Competition` dataclass, not a bare string. `str()` gives the `competition_id`, and the dataclass also carries `tier`, `fmt`, `event_id`, `assoc_match`, `official` and `generic`. Unmatched club events use `other_<fmt>_<m|w>` ids, which the plan does not list.
- `rules_for` takes extra keyword arguments (`event_id`, `teams`, `official`, `assoc_match`, `knockout`, `stage`, `scheduled_days`, `match_id`), because DRS, super overs and Test length depend on the event, the teams and the stage. It returns these fields beyond section 5: `balls_per_innings`, `bowler_quota_balls`, `fielders_outside`, `drs_scope`, `balls_in_use`, `tactical_sub`, `super_over_this_match`, `min_balls_for_result`, `max_consecutive_balls_per_end`, and informational `slow_over_rate_fielding_penalty`, `stop_clock` and `concussion_substitutes`.
- `powerplay_overs` uses 1-based over numbers in units of `balls_per_over`. For the Hundred that means 5-ball sets, so the 25-ball powerplay is sets 1-5.
- The plan's section 5 statement that T20 review limits went from 1 to 2 in 2019 is corrected by conflict 4 above.
- Cricsheet match ids are not all integers: 25 files start `wi_`. That matters for `matches.match_id` in plan 4.1.
- An extra derived file, `data/derived/cricket/competition-events.csv`, holds the full event list.
- Several section-5 fields use other names: `noball_extra_runs` (plan `noball_penalty_runs`), `test_days` (`scheduled_days`), `powerplay_overs` (`pp_windows`), `fielders_outside` (`field_restr`), `bowler_quota_overs` / `bowler_quota_balls` (`bowler_quota`), `balls_in_use` (`two_new_balls`) and `super_over` / `super_over_this_match` with values `none`, `bowl_out`, `single`, `repeat`, `knockout_only` (`tie_break` with `none`, `bowl_out`, `so_boundary_count`, `so_repeat`; `single` means one super over, then the boundary count where the event used it).
- Section-5 items not provided yet: `p_free_hit_given_nb` for front-foot eras (the free-hit check's ratios, 0.15-0.46, are the evidence), `ucall_zone_era`, `follow_on_lead` by days remaining (one static threshold per match), reduced-match quota and powerplay tables, and the series key of plan 4.2 (`competitions.py` has `season_key` only).
