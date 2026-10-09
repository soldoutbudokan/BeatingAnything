# theScore Bet Parlay+ redundant-leg screen (October 8, 2026; corrected October 9)

**Result: the two-leg screen finds no bettable redundant-leg improvement. The combinations that priced as the plain product of their legs are drafts the book refuses.** Across 267 pregame events in 78 competitions on theScore Bet's Ohio board, 1,433 two-leg Parlay+ combinations were built where winning leg A guarantees winning leg B. The book accepted 1,087 of them as Parlay+ drafts; of those, 172 (16%) paid more than A's straight price, by a median of 5% and at most 32%, almost all of them below what independent legs would pay and every one with a FanDuel reference negative EV. The other 302 drafts, every pair in tennis, UFC, boxing, AHL, SHL, KBO, CFL, NBA Preseason and the Saudi Pro League, carry a placeholder equal to the product of the two prices together with the error `vegas.not.parlayable`, which the site shows as "Parlay not available". The first version of this report counted those placeholders as quotes and claimed a large edge in those competitions; that claim was wrong and is withdrawn.

The one bettable case of a redundant leg raising the price is the construction the user documented from the Ontario site in [PR 4](https://github.com/soldoutbudokan/BeatingAnything/pull/4): on an NFL rushing-plus-receiving Over and rushing Under base, a receiving leg implied by the conjunction of the two base legs is absorbed on its own, but added next to its twin ladder leg it multiplies the price. Those drafts are Parlay+ eligible with no error, and they reproduce through the API on the Ohio board at the same numbers (McCaffrey +483 → +854, Harvey +498 → +703). PR 4's FanDuel lower bound for the McCaffrey construction is +12.8% under power devig and +6.1% additive.

Everything below is reproducible from `tools/screen_thescore_sgp_redundant_legs.py` and `tools/devig_thescore_sgp_instances.py`; row-level outputs are in [`thescore-sgp-redundant-legs-2026-10-08.json`](thescore-sgp-redundant-legs-2026-10-08.json) and [`thescore-sgp-redundant-legs-fanduel-devig-2026-10-09.json`](thescore-sgp-redundant-legs-fanduel-devig-2026-10-09.json). No bet was placed.

## 1. Access route

theScore Bet's web client (`sportsbook.thescore.bet`, `sportsbook.ca.thescore.bet`) talks to a GraphQL gateway at `https://sportsbook.<region>.thescore.bet/graphql` with Apollo persisted queries over GET and ordinary POST mutations. Free-form documents are accepted on the same endpoint (introspection is off), so [`beating/thescore.py`](../beating/thescore.py) uses the captured persisted hashes only for `Startup`, `SportsMenu`, `Marketplace` (event pages) and `BetslipAddMarketSelection`, and free-form queries for competition listings and betslip reads.

- `startup.anonymousToken` (sent as `x-anonymous-authorization: Bearer …`) gives an anonymous draft betslip. The slip is keyed by the `connectToken` passed to `Startup`; clients must use distinct connect tokens or they share one slip.
- `betslipAddMarketSelection` adds a leg; `parlay.draftBets[0]` is the Parlay+ draft. Its `betToWinRatio` and `totalOdds` settle about 0.3–0.5 seconds after the second leg; polling the betslip query is enough.
- **A settled draft is a quote only when `isParlayPlusEligible` is true and the draft carries no error.** A draft the book refuses still shows `betToWinRatio` equal to the plain product of the legs, with `errors: [{code: "vegas.not.parlayable", message: "These selections cannot be parlayed. Please adjust your selections."}]`. Related legs are refused with `vegas.related.markets` (two lines of one market) or `vegas.correlated.markets` (NHL moneyline with the puck line) and carry no placeholder.
- **Region gating.** The Ontario board (`ca-default`) answers every market query from anywhere, but with `regionalMetadata.validRegion=false` (this session's egress is in Columbus, Ohio) it never prices a same-game draft, while cross-game parlays still price. The US default board redirects to the state board for the caller's IP (`US-OH`), which prices Parlay+ for anonymous slips. All prices here are therefore **theScore Bet Ohio**. PR 4's Ontario observations of the same NFL constructions match the Ohio API numbers to the point.

FanDuel: the New Jersey API (`sbapi.nj.sportsbook.fanduel.com`) is reachable; the Ontario host is blocked from this session. Earlier work found New Jersey prices 99.3% identical to Ontario. Event pages need every `tab` of the layout fetched to see method, round, set-betting and correct-score markets.

## 2. Method

For each pregame event (up to 12 per competition, 72-hour horizon) the event page's markets were pulled and candidate pairs built where A implies B, at most two per rule, up to 14 per event. Each pair was placed on an anonymous slip holding exactly those two legs (the tool verifies the leg count and ids), and the settled draft was read.

| Rule | A implies B | Pairs | Accepted | Exact (= A) | Below A | Above A | Refused, placeholder | Refused, error |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `ml_spread` | moneyline ⇒ positive spread; negative spread ⇒ moneyline | 328 | 232 | 82 | 107 | 43 | 76 | 20 |
| `win_type_moneyline` | method, round, correct score, margin, HT/FT ⇒ that side's moneyline | 265 | 183 | 20 | 136 | 27 | 82 | 0 |
| `moneyline_double_chance` | moneyline ⇒ double chance / draw no bet with the same team | 238 | 199 | 16 | 137 | 46 | 38 | 1 |
| `correct_score_totals` | exact score ⇒ game Over/Under, both teams to score | 328 | 296 | 26 | 260 | 10 | 32 | 0 |
| `team_total_game_total` | team total Over L ⇒ game Over L′≤L; game Under ⇒ team Under | 102 | 102 | 12 | 49 | 41 | 0 | 0 |
| `cross_stat_ladder` | goals ⇒ points, home runs ⇒ hits/RBIs, rushing ⇒ rushing+receiving | 50 | 30 | 27 | 0 | 3 | 0 | 20 |
| `ladder_over_twin` | "275+" ladder ⇒ Over 269.5 of the same stat | 28 | 25 | 23 | 0 | 2 | 0 | 3 |
| `first_scorer_anytime` | first touchdown scorer ⇒ 1+ touchdowns | 20 | 20 | 20 | 0 | 0 | 0 | 0 |
| `set_score_set_winner` | tennis 2-0 ⇒ set 1 and set 2 winner | 26 | 0 | 0 | 0 | 0 | 26 | 0 |
| `round_under_rounds` | fighter wins in round N ⇒ Under L rounds, L>N | 24 | 0 | 0 | 0 | 0 | 24 | 0 |
| `decision_over_rounds` | by points/decision ⇒ Over L rounds | 24 | 0 | 0 | 0 | 0 | 24 | 0 |

"Above A" counts accepted drafts more than 0.5% above A's decimal price.

## 3. Engine behaviour by competition

The placeholder product appears for every pair in a fixed set of competitions, so Parlay+ availability is a competition property:

| Competition | Pairs | Accepted | Refused with placeholder | Accepted above A |
|---|---:|---:|---:|---:|
| ATP Shanghai, ATP Antofagasta Challenger doubles (tennis) | 52 | 0 | 52 | 0 |
| UFC Fight Night: Allen vs. Duncan (MMA) | 72 | 0 | 72 | 0 |
| International boxing | 12 | 0 | 12 | 0 |
| AHL, SHL (hockey) | 38 | 0 | 38 | 0 |
| KBO (baseball) | 6 | 0 | 6 | 0 |
| CFL (football) | 2 | 0 | 2 | 0 |
| NBA Preseason (basketball) | 12 | 0 | 12 | 0 |
| Saudi Professional League (soccer) | 86 | 0 | 86 | 0 |
| Primeira Liga, Liga MX, Greek Super League, League One (soccer) | 269 | 247 | 22 | 58 |
| NFL, NCAAF, MLB, WNBA | 136 | 133 | 0 | 6 |
| Premier League, Championship, League Two, La Liga, Serie A, Bundesliga, Ligue 1, MLS | 708 | 707 | 0 | 108 |
| NHL | 40 | 0 | 0 (all refused as correlated) | 0 |

Among accepted drafts the engine either returns A's price exactly (NFL moneyline + spread, MLB run line + moneyline, every first-scorer and ladder pair) or moves it. Most moves are down: Arsenal 1-0 at +550 plus Arsenal to win returned +475, and Arsenal to win at −260 plus "Arsenal or draw" returned −286, so adding the redundant leg costs the bettor. The 172 moves up are concentrated in soccer (166), WNBA ladders (5) and one NCAAF spread; the median uplift is 5% and the largest 32% (Augsburg 1-0 at +3000 plus Augsburg to win, +4000). All but four sit well below the independent product, and those four are pairs whose redundant leg is priced −1200 to −10000, where product and straight differ by 1–3%.

## 4. FanDuel devig of the accepted improvements

Only rows with an exhaustive FanDuel market (implied probabilities summing to at least 1) were devigged; `p_power` solves Σq^k = 1 and is harsher on long shots than the multiplicative devig.

| Rows | Count |
|---|---:|
| Accepted drafts above A | 172 |
| With a FanDuel fixture and the same leg | 8 |
| Positive EV, power devig | 0 |
| Positive EV, multiplicative devig | 0 |

The eight matched rows are Bundesliga, La Liga and Serie A correct scores and a Real Madrid moneyline plus double chance; their EV runs from −3% to −97%, with the straight leg equally bad. The other 164 had no FanDuel reference: FanDuel's front pages omit the English Championship, Leagues One and Two, Primeira Liga, Liga MX and the Greek league (128 rows), 30 team-total or alternate lines had no two-sided FanDuel line, and five WNBA ladders had no FanDuel market.

## 5. The conjunction case (PR 4) reproduced through the API

PR 4 records, from the Ontario site, that adding an already-implied receiving leg to an NFL rushing-plus-receiving construction raised the Parlay+ price, and bounds the McCaffrey version against FanDuel's four-cell SGP partition at +12.8% (power) and +6.1% (additive). The same constructions on the Ohio board through this client, read with the eligibility and error checks:

| Construction | Ohio API | PR 4 (Ontario, Oct 8) | Eligible, no error |
|---|---|---|---|
| McCaffrey combined 90+ and rushing under 54.5 | +391 | +391 | yes |
| plus receiving over 34.5 (implied: receiving ≥ 36) | +467 | +466 | yes |
| plus receiving 40+ instead | +483 | +483 | yes |
| plus receiving 40+ and receiving over 34.5 | **+854** | **+854** | yes |
| Harvey combined over 54.5 and rushing under 19.5 | +507 | +498 | yes |
| plus receiving over 24.5 | +525 | +507 | yes |
| plus receiving 20+ and receiving over 24.5 | **+703** | **+703** | yes |

A single implied receiving leg is absorbed or priced in with a small haircut; the ladder leg and the Over line together, both implied by the base, multiply the price by 1.4 to 2.2. The two-leg screen could not see this because it never stacked two twin legs on a two-leg base. The McCaffrey construction is the only placeable positive-EV instance either investigation has found, and PR 4's margin is thin and model-dependent.

## 6. What this does and does not show

- Two-leg redundant pairs are not mispriced on theScore Bet: the engine collapses, discounts or refuses them. Where the price rose, it rose modestly and still below fair.
- The plain-product placeholders on refused drafts are not quotes. The site shows "Parlay not available" for them, and the API error says the selections cannot be parlayed.
- The conjunction construction is mispriced and accepted as a draft, but acceptance at the counter, stake limits and the house rule on implied legs were not tested; FanDuel's four-cell partitions carry 18–22% overround, so the EV bound depends on the devig model.
- Ontario board prices were not observed here. PR 4's Ontario numbers for the NFL constructions match the Ohio API numbers, which is the only cross-board evidence available.

## 7. Next steps

1. Extend the screen to three- and four-leg constructions: for every player with a combined-yards Over, a rushing Under and receiving twins, price the base, each implied leg alone, and both together; do the same for other conjunction families (home runs plus hits plus total bases, goals plus assists plus points).
2. Devig those against FanDuel's four-cell SGP partition the way PR 4 does, and against Pinnacle where a two-way line exists.
3. Place one minimal-stake McCaffrey-type construction from an Ontario connection to test acceptance and limits; record the ticket.
4. Keep the eligibility and error checks in every price read; a settled ratio is not a quote.
