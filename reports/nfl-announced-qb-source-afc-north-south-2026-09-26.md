# Announced quarterback replacement sources: AFC North and South

**The bounded search qualifies one team-game and five provisional receiving-yard receiver-games:** Jacksonville at Detroit, November 17, 2024. Five is a retrospective roster-compatible provisional count: two WR, one TE and two RB. It is not a rigorous eligibility ceiling. Counting all priced players on both sides gives an unconditional team-attribution ceiling of 11; opponents are not treated as eligible affected-team receivers. Prior membership, roles and availability remain unresolved. No forecasting, receiving-yard-share calculation or target-outcome-column inspection occurred.

Followed committed declaration `79b4bcc`: eight standardized team searches, 13 targeted follow-ups across seven candidate injury episodes, maximum two follow-ups per episode. The [JSON ledger](nfl-announced-qb-source-afc-north-south-2026-09-26.json) records 35 fixture cases, negative teams, source timestamps, receipt paths and query counts. Search logs and 20 primary-page HTML receipts are under `data/raw/nfl-announced-qb-expanded-2026-09-26/`. Incidental retrospective performance snippets appeared in search results; this is not an outcome-unread holdout.

| Team | Source disposition | Quote-compatible result |
| --- | --- | --- |
| BAL | No 2024 regular-season injury replacement found; prior-season rest and preseason backup material do not qualify | 0 |
| CIN | No qualifying 2024 fixture announcement found | 0 |
| CLE | Explicit Week 8 Winston announcement; later weekly confirmation not established; December healthy benching excluded | Week 8 has no retained quote |
| PIT | Week 1 page revised after quote; Weeks 2–3 conditional; Week 4 plan has no valid prices | 0 |
| HOU | No qualifying 2024 fixture announcement found | 0 |
| IND | Week 5/6 articles revised too late; Week 17 explicit confirmation but prices fail; Week 18 lacks prices | 0 |
| JAX | Week 10 conditional; Week 11 confirmed; subsequent IR establishes absence but does not confirm each later starter | **5** |
| TEN | Week 7 article revised too late; Week 8 unconfirmed; Week 9 conditional; December benching excluded | 0 |

The [Jaguars' Week 11 announcement](https://www.jaguars.com/news/k000015-jaguars-qb-mac-jones-will-make-the-start-for-the-jaguars-in-week-11) explicitly says: “Mac Jones will start a second consecutive game in place of Lawrence”. It separately attributes Lawrence's absence to the coach and identifies Detroit as the upcoming opponent. Article metadata gives publication `2024-11-13T22:39:47.048Z`, latest revision `2024-11-13T22:53:41.266Z`, before the paired-price snapshot `2024-11-17T17:25:38Z`. Raw HTML SHA-256: `eca8e6d924ed391e17ca65c3a4bd613dfdc39e614b37659c0584d5be381fb999`.

Source revision checks remove several superficially promising reports:

- [Pittsburgh Week 1](https://www.nfl.com/news/steelers-qb-russell-wilson-calf-won-t-play-justin-fields-to-start-vs-falcons): revision September 25, after September 8 quote.
- [Indianapolis Week 6](https://www.nfl.com/news/colts-qb-joe-flacco-to-start-vs-titans-with-anthony-richardson-oblique-inactive): revision `17:08:38.518Z`, after `16:25:38Z` quote on October 13.
- [Tennessee Week 7](https://www.nfl.com/news/titans-qb-mason-rudolph-will-start-sunday-vs-bills-as-will-levis-deals-with-shoulder-injury): revision November 1, after October 20 quote.

The [Colts' prequote Week 6 inactive list](https://www.colts.com/news/colts-announce-5-inactive-players-for-week-6-game-vs-tennessee-titans-anthony-richardson-inactive-as-emergency-third-quarterback) establishes Richardson's absence but does not explicitly choose Flacco over the other active quarterback. It cannot repair the replacement-confirmation gap. The [Browns' Week 8 confirmation](https://www.clevelandbrowns.com/news/jameis-winston-to-start-at-quarterback-in-week-8) has timely publication and revision, but that fixture lacks prices in the retained export.

Counts use the independent [price inventory](nfl-announced-qb-expanded-price-inventory-2026-09-26.json). Repeated player/line snapshots are not extra receiver-games: Cleveland Week 13 has nine reported compatible rows but only seven distinct players. The earlier one-snapshot characterization does not hold for every expanded-export event. This does not repair any weekly announcement gap.

The search cap is complete. Unlocated sources remain unresolved, rather than being treated as proof that no pregame announcement existed. Combine the 11-player both-team ceiling with the other declared divisions, separately retaining the five roster-compatible provisional receivers. Apply the separately declared prior-team membership rule before any role or outcome extraction. If the resulting national eligible upper bound stays below 100, stop this exact route under the declaration. No extra searches, later-label extraction or inferred failure of the underlying sporting effect follows.
