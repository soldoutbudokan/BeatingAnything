# N2: Challenger total games, frozen before holdout acquisition

Recorded 2026-09-08. N1 soccer failed and remains recorded. N2 uses the three remaining learned-model slots in the eight-model research family. No N2 2023–2025 outcome evaluation has occurred at registration. Development source inspection was limited to 2021/2022 examples.

## Market, sources and fixed sample

ATP Challenger men's singles, standard best-of-three sets, full-match total 21.5 games. Historical book: Pinnacle, from ordinary public TennisExplorer archived pages. This is a narrower physical scoring model; it is not FanDuel execution evidence. Challenger events continue into November; source verification is in the research source audit.

Acquire daily ATP singles results from 2021-01-01 through 2025-12-31 as lagged score history. Match detail sample: every Tuesday and Friday in those years, at most 12 Challenger matches per date, selected by ascending SHA-256 of `N2-v1|match_id`, before reading their odds or results. This limits acquisition using an outcome-independent sample. Keep failed downloads, missing markets and rejected inputs in the acquisition ledger. No replacing an inconvenient match with a profitable one.

Only current-match opening Pinnacle 21.5 over/under and opening match-winner pairs are features. Require the four literal opening timestamps to match at minute resolution, precede the reported start, and have valid finite decimal prices > 1. This avoids treating a days-old moneyline opener as still available when the totals market opened. Their exact subminute simultaneity remains unverified. Read no current rankings, present-day player summaries, later head-to-head data or final odds into features.

Record raw site-local dates/times and conversion using Europe/Prague, as indicated by the site's Prague/Berlin/Vienna timezone. Relative quote/start comparisons use the same displayed timezone. Exact historical first-serve time is not independently verified. Do not hide missing timestamps behind a scheduled-date substitute.

Entry acceptance does not depend on final-price activity, closing availability, outcome or retirement. A deactivated final market is missing closing evidence, not grounds to remove an entry bet. If a fixed 21.5 market is absent, record absence; do not choose another line after seeing its result.

## Reconstructed sport information

Parse actual set game scores from the daily result rows, removing superscript tiebreak point counts. Recognize completed conventional sets and two-set wins; keep noncompleted or ambiguous matches explicitly. No Valuebetennis dates or scores are used: the source audit found dates nearly two days early and truncated scores.

For a decision timestamp, permit historical scores only if their calendar date ended at least 48 hours earlier. This conservative delay prevents using a prior-round result before the opening quote. Use only the preceding 365 days and update player histories chronologically. Revisions and publication timing remain retrospective-source limitations.

For each player estimate the share of completed historical sets reaching 6-6, shrunk toward 0.12 with 50 prior sets. Average the two players' shrunk rates for the matchup. Use all surfaces together to avoid relying on unverified historical surface metadata. This is a deliberately small latent serving estimate reconstructed from score shapes, not a claim that tiebreak frequency is an unbiased service statistic. Record each player's historical set count and missing-history flags.

Infer two service-game hold probabilities in [0.5, 0.995] from this matchup tiebreak propensity and the synchronized opening moneyline's proportional no-vig match probability. Use deterministic bounded least squares, initial [0.75, 0.75], tolerances 1e-8. The scoring kernel follows standard advantage games, alternating servers, a tiebreak at 6-6 and best-of-three match termination. First server is unknown, integrated 50/50. Derive the full total-games distribution and P(over 21.5). Reject fits with maximum target-probability residual above 0.03 or failed convergence; use the same early-input-valid universe for every candidate.

Additional workload features, with the same 48-hour availability delay: sum of completed-match games played by both players in the preceding 7 days, capped at 240 and divided by 60; absolute difference in their 7-day game totals, capped at 120 and divided by 60. These are physical-load proxies, not current injury information.

## Models, chronology and policy

Development 2021–2022; validation 2023; untouched holdout 2024–2025. Before each holdout year refit on prior years only. No 2026 replication is included in this protocol; 2026 remains available for a separately frozen follow-up rather than silently extending the sample.

Three candidates use the no-vig opening Pinnacle total probability m as an offset:

1. Calibration: `logit(p) = logit(m) + intercept + beta*z(logit(m))`.
2. Set shape: calibration plus standardized `logit(kernel_over_probability)-logit(m)`.
3. Workload: set shape plus the two registered workload features.

Use existing ResidualLogistic normalization and penalties [0.001, 0.01, 0.1, 1]. Select each penalty and the research candidate by 2023 outcome log loss only. Report every candidate and validation grid. No league, surface, round, player or odds-subgroup selection from holdout returns.

Fixed decision: maximum-EV side at >=3% model EV, chosen decimal odds [1.20, 6], paired early overround [0, 0.10], one unit maximum per event, over on ties. No stake optimization or changing the 21.5 line. Report 2% net-winnings haircut sensitivity.

## Closing evidence, results and uncertainty

Primary CLV: selected entry decimal price times normalized same-line Pinnacle final paired probability minus 1. Both final cells must be active; literal last changes (or an explicitly unchanged opening price) must precede reported start, match the displayed final price and have paired overround [0, 0.15]. Retain differing last-change timestamps; they are price-change times, not proof of fresh observations. The source supplies opening and last change, not a complete intraday history. Label CLV source-designated and historical execution unverified. Power-method de-vig is a reported sensitivity, never a selectable favorable benchmark.

Completed normal matches settle by their game sum. Retirements, walkovers, disqualifications and ambiguous scores are NOT dropped from selected turnover and are not imputed as wins/losses. Until the relevant historical bookmaker settlement rule and status are verified, report them as ungraded with explicit worst/best outcome bounds; block any favorable full-ROI claim. Also report a clearly labeled complete-match-only simulation with its reduced denominator. All-event paired log loss uses the same completed-match outcome universe for model and market; counts and missingness must accompany it.

Report holdout and year splits, all-event outcome log loss/Brier, paired market loss difference, counts, turnover, ROI, haircut ROI, end-of-day drawdown, selected CLV coverage, no-vig closing EV and price-ratio CLV separately. Resample calendar weeks, 10,000 samples, seed 1729, 99.375% two-sided intervals, as in the frozen finite eight-model family. Missing selected closing evidence or ungraded selected outcomes blocks a favorable screen. A historical screen requires positive corrected lower haircut-ROI and closing-EV bounds and a negative corrected upper paired-loss bound. It cannot promote a FanDuel bet.

The prospective FanDuel gate in docs/protocol.md remains unchanged: independently reviewed frozen artifact, at least 1,000 settled bets and 90 days, corrected ROI/closing-EV/log-loss requirements, plus verified fresh executable paired quotes. No actual bets, purchases, contact with others or threshold relaxation.
