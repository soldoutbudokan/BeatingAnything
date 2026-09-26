# Newer NBA injury reports: bounded quote-clock inventory

This declaration precedes the new injury-report/price join. The September 22 star-absence study is already inspected, positive but underpowered in its historical announced subset, and fading in its later ex-post comparison. This inventory does not redefine that result or create an untouched holdout. No scoring outcomes, player-minute values, star classifications, forecasts or returns will be extracted.

## Fixed price source and samples

Restore the existing exact pin `devlincorrigan/nba-props-threshold-app@233dbbc86b9c6e13df04d4e8b063581b3aa15abb`: 3,394 JSONs /397,273,601 bytes. Preserve publisher event mapping and all original clocks. The restored files were Git-blob verified before this declaration; their metadata have not yet been selected for this inventory.

Use publisher-mapped regular-season NBA IDs `00225*`. In each of **October 2025, January 2026 and April 2026**, choose the earliest original snapshot containing at least one preliminary qualifying FanDuel main-points pair; break ties by event ID. Month is the source fixture start's New York calendar month. The three months are a predetermined coverage sample, not an exhaustive newer-season cohort.

A preliminary pair requires one literal `fanduel` book and one `player_points` node, exactly one Over and Under for an exact full-name/half-point line, both decimal prices 1.20–6.00, paired overround 0–12%, and both book/market update ages 0–300 seconds at the original snapshot. Entry must precede the provider start. Do not infer player IDs from participation or repair future clocks. These are preliminary source checks: independent fixture identity, person IDs and target-team membership are not yet established by the publisher mapping.

## Fixed official report search

The two new official samples establish hourly filenames whose content may be 30 minutes later and a newer minute-qualified filename form. A header alone does not explicitly state its timezone; use the PDF's timezone-bearing CreationDate to corroborate its wall time. Game Time (ET) does not by itself establish report publication time.

For each selected snapshot, calculate the most recent half-hour boundary no later than **entry minus 90 minutes**, in America/New_York. Check that slot and the preceding five half-hour slots, newest first. For each slot, try the minute-qualified official NBA URL `Injury-Report_YYYY-MM-DD_HH_MMAM.pdf` (or PM); at :30 slots also try the older hourly form `..._HHAM.pdf` (or PM), because the observed hourly file contains a :30 header. Do not retry identical URLs; at most nine distinct candidate URLs per event, 27 total. Skip a cached identical URL. Stop at the first clock-qualified PDF, regardless of its player statuses or fixture content. A 404 is a missing filename; an access denial or transient server failure stops that event's remaining requests. No access workaround, account, purchase, background collection or season-wide download.

Preserve every URL/status/receipt, successful original PDF bytes, response headers and SHA-256. Retain the PDF header, CreationDate, any ModDate or XMP revision clock, and HTTP Last-Modified separately. Define the source-asserted available-after bound as the maximum of all interpretable creation/revision/Last-Modified clocks. Require timezone-bearing creation metadata, agreement with the printed header to the minute, no ambiguous revision clock, and this maximum at least 60 minutes but no more than six hours before entry. Later metadata cannot be ignored to qualify an old printed header. These are retrospective source assertions, not original contemporaneous receipts.

## Output and stopping rule

For each of the three selected fixtures, record all preliminary FanDuel pairs, original clocks, attempted report paths and source-clock checks. Report whether the first clock-qualified report contains the exact fixture/date and submitted statuses, explicit `NOT YET SUBMITTED`, or no matching fixture. Use the retained NBA team-abbreviation metadata only for ordered team identity. Do not search earlier reports for a favorable Out status or treat an unlisted player as healthy.

This pass establishes only whether actual retained prices can be paired with an appropriately earlier, fixture-specific official status report. It does not select an absent star or a bet, verify full-season coverage, or qualify historical execution/settlement. If samples qualify, a separate full cohort and prior-only forecasting declaration is still necessary; if they do not, retain the bounded failures without broadening this search. Keep the original code/results and evidence gates unchanged.
