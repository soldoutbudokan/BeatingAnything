# G10 — Same-group shared weather and score-difference variance

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / pre-round 2-balls and 3-balls / FanDuel; original addition.

**Structural fact:** Players in one group share short-lived weather. Shared score variation cancels from score differences, while individual variation does not.

**Predicted behavior (measurable):** Actual same-group score-difference variance is >=10% lower than ability-matched different-time pairs in volatile weather.

**Why FanDuel's price ignores it:** Unverified: a derivative conversion uses independent player variances calibrated on all tee times, overstating within-group spread and understating ties.

**Trigger (observable, timestamped):** Group release and a pre-round forecast identifying weather variation over the playing window.

**Sport-side test: data source, cost, kill criterion:** Use >=300 actual groups across >=10 events with tee times and prior-20-round ability. Compare pair differences for same-group players against different-time players in the same course-round and 0.5-stroke ability-gap bins; bootstrap events. Predefine volatile rounds from forecast inter-hour wind range >=10 km/h. Kill if reduction <10%; missing group/weather data stays unresolved. Common additive wave shift alone is not evidence.

**Book-side test: what odds at trigger time, forward or historical:** After the screen, contrast variance-sensitive matchup/3-ball residuals with contemporaneous main lines. Kill if FanDuel implied probabilities already incorporate the narrower relative distribution. This tests covariance, separately from G3’s payout allocation.

**Status:** closed at the fixed sport-side screen

**Result:** The [declared screen](../../reports/golf-weather-screen-2026-09-14.md) finds **4.420% variance reduction**, below the fixed 10% requirement, across **1,377 actual groups /24 events**. The sample gate passes. There are 3,204 same-group pairs and 104,701 different-time controls; weighted variances are 15.4296 versus 16.1431. The 5,000-draw event-bootstrap interval is **−0.419% to +9.284%** reduction.

The fixed cohort retained all 40 events; completed NOAA acquisition classified 76 opening rounds, including 37 volatile rounds, and left four rounds unclassified for the two previously unresolved venues. This is an observational comparison with retrospective group schedules and noisy ability control. No FanDuel price effect was tested. Preserve the [declaration](../../reports/golf-weather-declaration-2026-09-14.md); do not rescue the result with stronger-wind subsets, new windows or replacement years.
