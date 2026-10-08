# theScore Bet Parlay+ redundant-leg screen (October 8, 2026)

**Result: yes, a redundant leg raises theScore Bet's same-game parlay price in the competitions where its Parlay+ engine has no correlation model.** Across 267 pregame events in 78 competitions on theScore Bet's Ohio board, 1,389 two-leg Parlay+ combinations were priced where winning leg A guarantees winning leg B. A fair engine returns A's straight price; 474 combinations (34%) paid more, and in ten competitions every combination priced as the plain product of the two legs: ATP Shanghai and an ATP Challenger doubles draw (tennis), UFC Fight Night (MMA), international boxing, AHL and SHL hockey, KBO baseball, CFL football, NBA Preseason and the Saudi Pro League. The headline leagues (NFL, NCAAF, MLB, NHL, the five big European soccer leagues, MLS, the English Championship) price the pair at A, apply a haircut below A, or refuse the combination.

Devigging the improved instances against FanDuel's New Jersey feed: 158 of 469 had a FanDuel fixture and the matching leg, 148 of those with an exhaustive (normalisable) FanDuel market. Under the harsher power devig **133 of the 148 are positive EV**, with medians of +55% to +71% per sport, while the same legs bet straight are −5% to −25% EV against the same fair prices. The best were a boxer's method of victory plus his own moneyline (+698%) and a tennis 2-0 set score plus the match winner (+360%). The 15 negative instances are short-priced favourites where the redundant moneyline adds only a few percent.

This is a price screen, not a demonstrated edge: no bet was placed, acceptance and limits are untested, the priced board is Ohio rather than Ontario, and FanDuel's reference prices on method, round and set-score markets carry 15–40% holds. Everything below is reproducible from `tools/screen_thescore_sgp_redundant_legs.py` and `tools/devig_thescore_sgp_instances.py`; the row-level outputs are in [`thescore-sgp-redundant-legs-2026-10-08.json`](thescore-sgp-redundant-legs-2026-10-08.json) and [`thescore-sgp-redundant-legs-fanduel-devig-2026-10-08.json`](thescore-sgp-redundant-legs-fanduel-devig-2026-10-08.json).

## 1. Access route

theScore Bet's web client (`sportsbook.thescore.bet`, `sportsbook.ca.thescore.bet`) talks to a GraphQL gateway at `https://sportsbook.<region>.thescore.bet/graphql` with Apollo persisted queries over GET and ordinary POST mutations. Free-form documents are accepted on the same endpoint (introspection is off), so [`beating/thescore.py`](../beating/thescore.py) uses the captured persisted hashes only for `Startup`, `SportsMenu`, `Marketplace` (event pages) and `BetslipAddMarketSelection`, and free-form queries for competition listings and betslip reads.

- `startup.anonymousToken` (sent as `x-anonymous-authorization: Bearer …`) gives an anonymous draft betslip. The slip is keyed by the `connectToken` passed to `Startup`; clients must use distinct connect tokens or they share one slip.
- `betslipAddMarketSelection` adds a leg; the `parlay.draftBets[0]` entry is the Parlay+ draft. Its `betToWinRatio`/`totalOdds` arrive asynchronously, about 0.3–0.5 seconds after the second leg; polling the betslip query is enough (the site's websocket subscription is not needed).
- Related legs are refused with `vegas.related.markets` (same market family, e.g. two total lines) or `vegas.correlated.markets` (e.g. NHL moneyline with the puck line).
- **Region gating.** The Ontario board (`ca-default`) answers every market query from anywhere, but with `regionalMetadata.validRegion=false` (this session's egress is in Columbus, Ohio) it never prices a same-game draft (`totalOdds` stays null, `isParlayPlusEligible=false`), while cross-game parlays still price. The US default board redirects to the state board for the caller's IP (`US-OH`), which prices Parlay+ for anonymous slips. All prices here are therefore **theScore Bet Ohio**. The engine is the same product in Ontario, but Ontario prices must be confirmed from an Ontario connection (`THESCORE_REGION=ca-default`).

FanDuel: the New Jersey API (`sbapi.nj.sportsbook.fanduel.com`) is reachable; the Ontario host is blocked from this session. Earlier work found New Jersey prices 99.3% identical to Ontario. Event pages need every `tab` of the layout fetched to see method, round, set-betting and correct-score markets.

## 2. Method

For each pregame event (up to 12 per competition, 72-hour horizon) the event page's markets were pulled and candidate pairs built where A implies B, at most two per rule, up to 14 per event:

| Rule | A implies B | Pairs priced | Exact (= A) | Below A | Above A | Refused |
|---|---|---:|---:|---:|---:|---:|
| `ml_spread` | moneyline ⇒ positive spread; negative spread ⇒ moneyline | 308 | 82 | 107 | 119 | 20 (NHL, correlated) |
| `win_type_moneyline` | method of victory, round, correct score, winning margin, HT/FT ⇒ that side's moneyline | 265 | 20 | 136 | 109 | 0 |
| `moneyline_double_chance` | moneyline ⇒ double chance / draw no bet with the same team | 237 | 16 | 137 | 84 | 1 |
| `correct_score_totals` | exact score ⇒ game Over/Under, both teams to score | 328 | 26 | 260 | 42 | 0 |
| `team_total_game_total` | team total Over L ⇒ game Over L′≤L; game Under ⇒ team Under | 102 | 12 | 49 | 41 | 0 |
| `set_score_set_winner` | tennis 2-0 ⇒ set 1 and set 2 winner | 26 | 0 | 0 | 26 | 0 |
| `round_under_rounds` | fighter wins in round N ⇒ Under L rounds, L>N | 24 | 0 | 0 | 24 | 0 |
| `decision_over_rounds` | by points/decision ⇒ Over L rounds | 24 | 0 | 0 | 24 | 0 |
| `cross_stat_ladder` | goals ⇒ points, home runs ⇒ hits/RBIs, rushing ⇒ rushing+receiving | 30 | 27 | 0 | 3 (≤5%) | 20 (correlated) |
| `ladder_over_twin` | "275+" ladder ⇒ Over 269.5 of the same stat | 25 | 23 | 0 | 2 (≤2%) | 3 |
| `first_scorer_anytime` | first touchdown scorer ⇒ 1+ touchdowns | 20 | 20 | 0 | 0 | 0 |

"Above A" counts improvements over 0.5% of A's decimal price. The Parlay+ price was read from an anonymous slip holding exactly those two legs (the tool verifies the leg count and ids on every read).

## 3. Engine behaviour by competition

Whether the engine prices the pair as the independent product (`vs_independent ≈ 0`) is a competition property, not a rule property:

| Competition | Pairs priced | Priced as independent product |
|---|---:|---:|
| ATP Shanghai, ATP Antofagasta Challenger doubles (tennis) | 52 | 100% |
| UFC Fight Night: Allen vs. Duncan (MMA) | 72 | 100% |
| International boxing | 12 | 100% |
| AHL, SHL (hockey) | 38 | 100% |
| KBO (baseball) | 6 | 100% |
| CFL (football) | 2 | 100% |
| NBA Preseason (basketball) | 12 | 100% |
| Saudi Professional League (soccer) | 86 | 100% |
| Liga MX, Primeira Liga, Greek Super League, League One | 269 | 5–14% |
| NFL, NCAAF, MLB, WNBA | 133 | 0% |
| Premier League, Championship, League Two, La Liga, Serie A, Bundesliga, Ligue 1, MLS | 707 | 0% |
| NHL | 0 (all 40 refused as correlated) | — |

In the 0% group the engine either returns A's price exactly (NFL moneyline + spread, MLB run line + moneyline, every first-scorer and ladder pair) or prices the pair *below* A: for example Arsenal 1-0 at +550 plus Arsenal to win returned +475, and Arsenal to win at −260 plus "Arsenal or draw" returned −286. Adding the redundant leg there costs the bettor. In the partial group some pairs multiply (Primeira Liga moneyline + double chance up to 8× the straight price) while most are haircut.

## 4. Instances and FanDuel devig

Only rows with an exhaustive FanDuel market (implied probabilities summing to at least 1) were devigged. `p_mult` divides by the overround; `p_power` solves Σq^k = 1 and is harsher on long shots, so its EV is reported first. The straight-leg EV uses the same fair probability on theScore's own single price.

| Sport / rule | n | +EV (power) | Median EV (power) | Median EV (mult) | Median straight-leg EV | Median price uplift |
|---|---:|---:|---:|---:|---:|---:|
| tennis `win_type_moneyline` (2-0 + match winner) | 24 | 24 | +71% | +68% | −12% | +91% |
| tennis `set_score_set_winner` (2-0 + set winner) | 24 | 24 | +70% | +67% | −11% | +87% |
| mma `win_type_moneyline` (method/round + moneyline) | 24 | 23 | +56% | +65% | −18% | +91% |
| mma `round_under_rounds` (round N + Under rounds) | 14 | 13 | +67% | +65% | −25% | +128% |
| mma `decision_over_rounds` (points + Over rounds) | 22 | 22 | +60% | +61% | −20% | +91% |
| boxing `win_type_moneyline` | 12 | 7 | +133% | +166% | −13% | +208% |
| basketball `ml_spread` (NBA Preseason) | 12 | 12 | +60% | +65% | −5% | +73% |
| baseball `ml_spread` (KBO) | 6 | 6 | +55% | +58% | −8% | +71% |
| football `ml_spread` (CFL) | 2 | 2 | +21% | +35% | −10% | +52% |
| soccer (Bundesliga, La Liga, Serie A; haircut pairs) | 8 | 0 | −64% | −62% | −70% | +17% |

Largest priced instances (theScore Ohio, 21:45–21:58 UTC; FanDuel NJ 22:00–22:08 UTC):

| Event | Leg A (theScore straight) | Redundant leg B | Parlay+ | FanDuel A | fair p (power) | EV (power) |
|---|---|---|---|---|---|---|
| Mathieu vs Shishkin (boxing) | Shishkin by KO/TKO/DQ +2000 | Shishkin ML +850 | +19850 | 16.00 | 4.0% | +698% |
| Khataev vs McCrory (boxing) | McCrory by KO/TKO/DQ +1600 | McCrory ML +1200 | +22000 | 15.00 | 3.3% | +626% |
| Santana vs Asanau (boxing) | Santana by KO/TKO/DQ +1400 | Santana ML +650 | +11150 | 13.00 | 5.2% | +482% |
| Schofield vs Bahdi (boxing) | Bahdi by KO/TKO/DQ +900 | Bahdi ML +600 | +6900 | 10.00 | 6.8% | +374% |
| Zverev vs Wu (ATP Shanghai) | Wu 2-0 +1000 | Wu to win +545 | +6995 | 11.00 | 6.5% | +360% |
| Shelton vs Altmaier (ATP Shanghai) | Altmaier 2-0 +1000 | Altmaier to win +500 | +6500 | 12.00 | 5.9% | +290% |
| Kareckaite vs Gatto (UFC) | Kareckaite in round 1 +1400 | Under 1.5 rounds +450 | +8150 | 17.00 | 4.3% | +258% |
| Pereira vs Zhelezniakova (UFC) | Zhelezniakova by KO/TKO/DQ +500 | Zhelezniakova ML +120 | +1220 | 3.30 | 27.0% | +256% |
| Sakamoto vs Rublev (ATP Shanghai) | Sakamoto 2-0 +450 | Sakamoto to win +210 | +1605 | 5.30 | 16.0% | +172% |
| Allen vs Duncan (UFC) | Allen by KO/TKO/DQ +850 | Allen ML −125 | +1610 | 10.00 | 8.0% | +36% |

The multiplier is exactly B's decimal price, so the uplift is largest when the redundant leg is itself a long shot (an underdog's moneyline next to his own knockout, or a set score next to the underdog's match price).

Coverage gaps. 311 of the 469 improved instances could not be devigged: FanDuel's front pages do not list the Saudi league, the English Championship, League One and Two, Primeira Liga, Liga MX, the Greek league, AHL or SHL (235 soccer and 38 hockey rows), 27 soccer team-total or alternate lines had no two-sided FanDuel line, ten MMA method-and-round combos only had a FanDuel market that omits decisions (not normalisable; their EV at FanDuel's raw implied probability is an upper bound and is also positive), and a few player and doubles legs had no FanDuel market.

## 5. What this does and does not show

- It shows that theScore's Parlay+ engine multiplies legs independently in secondary competitions, so an implied leg inflates the payout by its own price. The pattern held for every pair in those competitions over a 13-minute capture; it is a property of the pricing model, not a stale line.
- It does not show that such a parlay would be accepted, at what stake, or that the account survives. The prices come from an anonymous draft slip. Books treat "redundant" or "mutually implied" parlays as voidable under house rules in several jurisdictions; the Ontario rules were not reviewed here.
- The fair prices come from FanDuel's own exotic markets with 15–40% holds; power devig assigns most of that hold to the long shot. A sharper reference (Pinnacle for tennis moneylines and set betting, Pinnacle/Circa for MMA methods) would tighten the estimate; the straight-leg EVs of −5% to −25% say theScore's single prices are not generous, so the parlay EV is driven by the multiplier.
- Ontario board prices and eligibility were not observed. The same engine serves `ca-default`, but it refused to price Parlay+ for this US-hosted session.

## 6. Next steps

1. Re-run the screen from an Ontario connection with `THESCORE_REGION=ca-default` and compare with these Ohio rows (same tool; the board is recorded on every row).
2. Place one minimal-stake Parlay+ in the strongest class (tennis set score + match winner, or MMA method + moneyline) to test acceptance, delay and limits; record the ticket.
3. Add Pinnacle set betting and tennis moneylines as the reference for the tennis class, which has the most liquid fair prices.
4. Watch the behaviour over time: the competition-level pattern suggests a feed/model flag per competition that theScore could change at any moment.
