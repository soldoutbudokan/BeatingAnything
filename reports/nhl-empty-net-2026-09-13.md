# NHL empty-net exposure — September 13, 2026

**Unresolved: official data access blocked. No sport-side test or pricing test completed.**

Ordinary requests to the NHL's [play-by-play endpoint](https://api-web.nhle.com/v1/gamecenter/2024020001/play-by-play), [shift-chart endpoint](https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId=2024020001), [season schedule](https://api-web.nhle.com/v1/club-schedule-season/TOR/20242025), and [published time-on-ice report](https://www.nhl.com/scores/htmlreports/20242025/TH020001.HTM) returned HTTP 403 in this workspace. Source probing stopped. No access restriction was bypassed.

The official [time-on-ice](https://www.nhl.com/scores/htmlreports/20242025/TH020001.HTM) and [play-by-play](https://www.nhl.com/scores/htmlreports/20242025/PL020001.HTM) pages were readable through web retrieval. Those individual pages are evidence of available official reports, not an adequate season dataset. No paired raw game inputs were acquired; all hazard estimates and exposure counts remain unavailable.

The missing quantity is **time exposed with the trailing goalie absent**, intersected with a one-goal deficit in the final 180 seconds. An empty-net flag on a shot or goal does not locate the goalie pull between events. Counting flagged goals or carrying an event state across an unknown interval would give an unreliable denominator.

After access is available, identify each team's goalies from the roster and union exact shift intervals. Reconstruct the score immediately before every goal, assign that goal to its pre-event state, then update the score. Split exposure at score and goalie transitions and at clock strata. Compare combined, leading-team, and trailing-team goals per second with both-goalies exposure at the same deficit and clock. Resolve goalie-return timestamps coincident with goals using event state; leave inconsistent timing unresolved. Report pull-selection and manpower confounding. The card's 200-segment and 50% relative-rate criteria have not been evaluated.

`tools/explore_nhl_empty_net.py` is a small resumable downloader, **not a completed analysis**. Its default is one source/schema probe. On a connection that permits the public endpoints, the planned full-season acquisition is:

```bash
python tools/explore_nhl_empty_net.py --last-game 1312
```

It caches official inputs under ignored `data/raw/nhl-empty-net/`, stops on a failed input without retrying, and writes an explicit incomplete/pending report. Actual response-schema inspection, shift completeness checks, and hazard calculation remain pending. No background collector is running.
