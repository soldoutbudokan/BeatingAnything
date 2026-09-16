# A verified operational weather archive for 2025 golf

**Found and decoded:** NOAA's public GFS bucket retains a genuine operational forecast initialized on **Wednesday, July 16, 2025 at 12:00 UTC**. Three wind fields for Thursday at 12:00 UTC were downloaded through ordinary anonymous byte-range requests. This resolves the existence and decoding prerequisite for a historical weather screen; it does not establish a golf effect or betting edge. [Full retained evidence](../reports/golf-weather-archive-source.json).

## Source and scope

The [NOAA-managed AWS registry](https://registry.opendata.aws/noaa-gfs-bdp-pds/) identifies `noaa-gfs-bdp-pds` as its public GFS bucket, explicitly supports access without an AWS account, and permits reuse with NOAA attribution. No account, subscription or credential was used.

The sampled object is:

```text
https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20250716/12/atmos/gfs.t12z.pgrb2.0p25.f024
```

Its adjacent `.idx` file supplies byte offsets and identifies `UGRD` and `VGRD` at 10 metres above ground plus surface `GUST`, all as 24-hour forecasts. Each requested field returned HTTP **206**, an exact `Content-Range`, and a complete single GRIB2 message. Raw responses, headers, local request/receipt clocks and SHA-256 hashes are under `data/raw/golf-weather-source/`.

The [NCEI overview](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast) describes a 30-day cloud window. The successful July 2025 S3 response shows that text cannot be treated as a hard retention bound today. Its alternative THREDDS catalogs also list July 2025, but the daily catalog timed out once. Only **one run and one lead** were decoded here; all-event and all-hour coverage remains to be measured.

## What the decoded file proves

ecCodes reads the following metadata independently of the filename:

| Field | Observed value |
| --- | --- |
| Centre | `kwbc`, numeric code 7 |
| Production status | 0: operational products |
| Data type | 1: forecast products |
| Initialization | July 16, 2025, 12:00 UTC |
| Lead / valid time | 24 hours / July 17, 2025, 12:00 UTC |
| Grid | Global 0.25°, 1,440 × 721 points |
| Wind units | metres per second |

The operational and forecast classifications follow the [production-status code table](https://codes.ecmwf.int/grib/format/grib2/ctables/1/3/) and [data-type code table](https://codes.ecmwf.int/grib/format/grib2/ctables/1/4/). These are archived operational forecast fields, rather than a retrospective hindcast inferred from a date parameter. No specific GFS software version was inferred from the file.

A decoding example requested 55.2°N, 6.65°W. The nearest grid point, 55.25°N, 6.75°W, is 8.43 km away. It has U = **−3.5718 m/s**, V = **6.8221 m/s**, derived speed **27.7219 km/h**, and gust **11.3112 m/s**. This approximate Portrush location is not a validated course coordinate or a measured course wind; coastal grid choice needs attention in the sport-side work.

## Keep the clocks separate

| Clock | Retained value |
| --- | --- |
| Model initialization | 2025-07-16 12:00:00 UTC |
| Forecast object's S3 Last-Modified | 2025-07-16 15:38:40 UTC |
| Index object's S3 Last-Modified | 2025-07-16 15:39:22 UTC |
| Forecast target hour | 2025-07-17 12:00:00 UTC |
| Our retrieval | September 15, 2026 UTC |

[AWS defines Last-Modified](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingMetadata.html) as system-controlled object creation/modification metadata; multipart creation can refer to upload initiation. It is useful historical evidence, but it does not independently prove when public access was enabled or when a historical client received the data. A conservative assumed publication lag must remain labeled as an assumption.

Check the object and index clocks for **every required lead**. Do not use the initialization hour, one analysis file's timestamp, or our 2026 receipt time as the publication time for an entire run. The [previously found FanDuel article](golf-price-source-continuation.md) was published at 14:07 UTC that Wednesday, before this forecast object's 15:38 timestamp; this run cannot support a predecision analysis of those article prices.

## Reproduce and budget

ecCodes 2.48.0 and its native library were installed only in `/tmp/golf-weather-eccodes`; the main research dependency lock and the research runtime's installed packages were not changed. The retained script validates GRIB message boundaries, initialization, valid time, operational status and finite nearest-point values:

```sh
state/runtime/research-venv/bin/python -m pip install --target /tmp/golf-weather-eccodes -r requirements-golf-weather.txt
PYTHONPATH=/tmp/golf-weather-eccodes state/runtime/research-venv/bin/python data/raw/golf-weather-source/decode_grib_sample.py
```

[requirements-golf-weather.txt](../requirements-golf-weather.txt) pins the eight packages used by this isolated decoder installation. The main research dependency lock remains unchanged.

The full forecast object is **540.73 MB**. Selected U/V messages total **1.921 MB**; adding gusts raises the transfer to **2.536 MB**, plus a 41 KB index. At these observed compressed sizes, 40 events × 36 forecast hours would require approximately **2.77 GB** for U/V or **3.65 GB** including gusts. These are planning estimates, not downloads performed or guaranteed future sizes.

The subsequent bounded acquisition, described below, fixed event, venue, model-run, valid-hour and timing rules and is now complete. Missing files and source clocks remain explicit; a sport-side effect is required before a FanDuel price test.

## Declared cohort acquisition

[acquire_golf_weather.py](../tools/acquire_golf_weather.py) implements the subsequent [G10 declaration](../reports/golf-weather-declaration-2026-09-14.md). Its default command writes a cost plan without network access; `--execute` freezes the inventory, venue and declaration hashes and starts acquisition:

```sh
PYTHONPATH=/tmp/golf-weather-eccodes state/runtime/research-venv/bin/python tools/acquire_golf_weather.py
PYTHONPATH=/tmp/golf-weather-eccodes state/runtime/research-venv/bin/python tools/acquire_golf_weather.py --execute
```

The final venue map retains all 40 events, admitting 38 and leaving Detroit's subcourse location and El Cardonal's coordinates unresolved. The dry plan contains 1,027 event-hours but only 940 distinct global forecast files, because concurrent events reuse files. Estimated acquisition is 1,880 requests and 1.845 GB including indices. This process requests U/V wind only, combining their adjacent GRIB records into one range per hour.

The single worker spaces request starts by at least one second, uses a 45-second socket timeout plus a 45-second total-response deadline, and caps cumulative acquisition at **3,000 requests / 3 GB**. It retains raw bytes and hashes, rejects incorrect times, variables, units, grid or missing nearest-point values, and checks each forecast object's modification time against the declared cutoff. HTTP 404 becomes a missing hour; denials and ineligible network errors persistently block further requests. An interrupted unrecorded socket is charged its reserved byte bound and left for investigation.

`data/raw/golf-weather/rounds.json` contains every declared course-round with `classified`, `volatile`, the full hourly wind vector and timestamps, missing reasons and source paths. `hours.json` retains individual clocks and grid values. The acquisition summary records hashes of both files and the frozen plan. **A partial acquisition has `complete=false` and pending hours; it must not become a selected download subset for scoring.** Missing venue or terminal 404 outcomes remain explicit attrition when acquisition has otherwise completed.

A transport disconnect after request 490 returned no HTTP status or response bytes. One explicitly authorized recovery retained the failed attempt intact, preserved cumulative counters and resumed the same plan after a 176-second backoff. The `--resume-remote-disconnected-once` option is restricted to that failure class with no HTTP response, requires at least 60 seconds of backoff, and consumes a single persisted allowance. It cannot retry an HTTP denial or silently reset budgets. The original failure and recovery audit remain under `data/raw/golf-weather/retained-failed-attempts/`.

A later interrupted HTTP 206 had the exact requested range and announced length, but delivered only part of its body. The [administrative recovery policy](../reports/golf-weather-acquisition-policy-2026-09-14.md), recorded before resumption, permits `--recover-transport`: at most five total eligible transport recoveries including the original one, once per exact URL and Range, each after at least 60 seconds. Eligibility requires an allowlisted transport exception and either no response or a verified partial success response; denials, protocol errors and integrity failures remain terminal. Every failed body, original metadata and charged byte remains retained. The same policy adds the tested total-response deadline after the socket-only timeout allowed a prolonged trickle response. No scientific inputs or thresholds change.

## Completed cohort and source audit

The acquisition completed at **2026-09-15 03:08:53 UTC**. All **1,027 planned event-hours** succeeded, covering 940 distinct forecast objects and their 940 indices. The final manifest retains all **40 events / 80 rounds**; 76 rounds have complete declared weather inputs, while Detroit and El Cardonal retain their four intentional missing-venue rows. There are zero pending or failed forecast hours.

The [acquisition summary](../reports/golf-weather-acquisition-2026-09-14.json) records **1,882 requests and 1,838,505,980 retained body bytes**, including both failed attempts. Two recoveries were used; the second resumed process completed without further interruption. The [source coverage audit](../reports/golf-weather-source-coverage-2026-09-14.json) verifies every retained body hash, both original failure-metadata hashes, cumulative accounting, and frozen plan, input, manifest and recovery-policy hashes.

No forecast object's LastModified equals or exceeds its declared decision cutoff. The smallest margin is **48,201 seconds (13 hours, 23 minutes, 21 seconds)** before cutoff. All index clocks are present and valid; none equals or exceeds cutoff, with a minimum margin of 48,173 seconds. Index clocks remain descriptive metadata and did not change the declared object eligibility gate. These checks do not independently prove historical public availability and do not establish a score effect or FanDuel price edge.

The source-only audit can be reproduced after acquisition completes:

```sh
state/runtime/research-venv/bin/python data/raw/golf-weather/source-coverage-audit.py
```
