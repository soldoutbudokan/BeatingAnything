# Golf weather acquisition: administrative transport recovery

Recorded before resuming the interrupted acquisition on 2026-09-15 UTC. This changes transport handling only. No outcomes were loaded; the cohort, coordinates, model run, forecast windows, availability gate, volatility threshold, and estimators remain unchanged.

## Frozen scientific inputs

- Plan SHA256: `bfcdb5bb03765e0f6afbe74165157fff6af94b568882210c668a015e2c75c172`.
- Declaration SHA256: `c29f1cf95910caf34f061cfb83512e5008340631d220f9836d58d52e91e5a3aa`.
- Inventory SHA256: `e7d5b0a2532c5573069129f8ba834624e1ae5f87280a7613b141e26b88b75af2`.
- Venue SHA256: `02150c6cc0249b7a0b003a8e80efafe846f84d05faeeaac9d71fc58da5e44dfe`.

## Evidence motivating recovery

The first run stopped after a `RemoteDisconnected` with no HTTP response or body. Its explicitly authorized single retry occurred 176 seconds later, retained the failed attempt, and succeeded.

The next interruption was a `BrokenPipeError` while reading an otherwise valid HTTP 206 response for `gfs.20250521/00/atmos/gfs.t00z.pgrb2.0p25.f042`. The requested range was `426758092-428698705`; the response reported exactly that range and a Content-Length of 1,940,614 bytes. The retained partial body has 1,871,729 bytes, SHA256 `5529e6660a06070ce9af6162a98fe636ed6a86b218446485e83ca6a950846b3d`. Cumulative counts before resuming are 911 requests and 878,715,436 body bytes. This attempt took approximately 951 seconds despite the socket timeout, motivating a total-response deadline.

## Authorized bounded policy

- Enable explicitly with `--execute --recover-transport`.
- At most **five total recoveries**, including the first recovery already used. Each exact URL plus Range may be retried once.
- Wait at least 60 seconds after the recorded failed response receipt before retrying.
- Eligible exceptions are `RemoteDisconnected`, `BrokenPipeError`, `ConnectionResetError`, and `TimeoutError`. A urllib `URLError` is normalized only when its underlying exception is one of these.
- The retained attempt must have either no HTTP response, headers, or body; or a verified interrupted success response. HTTP 206 requires the exact requested Content-Range, matching expected Content-Length, and a body shorter than announced. HTTP 200 is eligible only for an index, without Range, announced at most 1 MiB, with a shorter retained body.
- Never recover an HTTP denial, wrong range, protocol mismatch, integrity failure, repeated request, or acquisition cap. Keep the original stop reason for non-transport stops.
- Preserve every failed body and original metadata under `retained-failed-attempts/`, with an audit mapping the original and retained paths. Failed bytes and requests remain charged to cumulative limits.
- The original **3,000 requests / 3,000,000,000 bytes** limits and single-worker request spacing remain unchanged.
- Apply a real **45-second total-response deadline** with POSIX SIGALRM, in addition to the socket timeout. Restore the previous signal handler and timer in `finally`.
- Subsequent eligible failures may continue automatically within these limits. Any ineligible failure stops the acquisition as incomplete. Partial acquisition is never scored.

## Validation before launch

`state/runtime/research-venv/bin/python -m unittest tests.test_golf_weather_acquire -v`: **15 tests passed**. Coverage includes actual total-deadline interruption and signal restoration, partial-body preservation and charging, exact range validation, denial rejection, retained-history recovery cap, repeated-request rejection, original non-transport stop reasons, allowlisted urllib wrapping, request and byte limits, cache integrity, and complete-window classification.

The final source review will separately count any object LastModified exactly equal to the declared cutoff, and missing/invalid/after-cutoff index timestamps. Index clocks remain recorded metadata, not a new eligibility gate.
