# Rugby union: next try after a yellow card

**Sport / market / book:** Gallagher Premiership and United Rugby Championship; FanDuel live next-try team or team-try totals. Actual offerings and settlement rules remain unverified.

**Structural fact:** A yellow card suspends a player for ten playing minutes, temporarily thinning the defensive line. Twenty-minute replacement reds are a separate rule and are excluded.

**Predicted behavior (measurable):** The opponent's try rate in the next ten playing minutes rises at least 30% against comparable card-free windows.

**Why FanDuel's price ignores it:** A derivative might retain a full-strength scoring rate during the suspension. This is an unverified pricing hypothesis; prompt, adequate repricing kills the book-side idea.

**Trigger (observable, timestamped):** First isolated yellow card, otherwise full strength, with ten regulation minutes left in that half. Exclude red-card matches and penalty tries at the card's exact clock time. Retain later cards in the outcome window.

**Sport-side test: data source, cost, kill criterion:** Written September 13, 2026 before outcomes: full 2024–25 official URC timelines, with one official alternate if blocked. The landing request returned 403; the fixed fallback was PREM's public InCrowd feed. Compare opponent tries in a fixed ten-minute exposure with card-free windows from other matches, standardized within season by team, ten-minute start bin and score band (more than seven behind, within seven, more than seven ahead). Require at least 100 matched windows and a relative increase of at least 30%; adequate coverage with a smaller effect kills it. Inadequate clocks or sample size leave it unresolved. This measures trigger windows, not verified continuous 15-versus-14 exposure or causality.

**Sampling decisions:** The 2023–24 extension was declared before either season's conditional result, because the 93-game pilot could never supply 100 first-card exposures. After the positive 44-window 2024–25 result, a final 2022–23 extension was declared if the first two seasons remained below 100; they supplied 81. Stop after three seasons regardless of outcome. Preserve individual seasons; the combined result is exploratory, not untouched confirmation.

**Book-side test:** Verify an actual FanDuel live market, then capture paired prices, rules, suspension state and card/quote timestamps. A next-try price also requires competing scoring and no-further-try probabilities; the sport-side rate alone cannot price it.

**Price-source checkpoint:** [The September 13 check](../rugby-market-access-2026-09-13.md) found general FanDuel rugby settlement rules, but no verified PREM/URC next-try offering or usable price route. The Odds API's listed union coverage is Six Nations; its Australian rugby-league try props do not fill this gap. Do not repeat this unchanged catalog check or assume an API key would solve it.

**Status:** sport-side confirmed (exploratory conditional effect only)

**Result:** [The completed screen](../../reports/rugby-yellow-card-2026-09-13.md) recovered all 306 published match feeds: 133 matched windows across 273 eligible matches, 122 tries in 1,330 playing minutes, **0.917 tries per ten minutes versus 0.419 controls (+119.17%)**. Every season was positive. Field position, possession, card selection and retrospective red exclusions limit interpretation. No FanDuel quotes or verified betting edge. PREM and URC run September 2026–June 2027. Next: actual book-side availability and repricing, with no further historical expansion.
