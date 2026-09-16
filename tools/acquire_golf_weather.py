#!/usr/bin/env python3
"""Acquire the declared G10 operational wind inputs, without loading scores.

Run with PYTHONPATH=/tmp/golf-weather-eccodes and the research Python runtime.
The default is a dry cost plan. Pass --execute after the venue map is final.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import http.client
import json
import math
from pathlib import Path
import re
import signal
import time
import urllib.error
import urllib.request


UTC = timezone.utc
BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
REQUEST_DEADLINE_SECONDS = 45
TRANSPORT_EXCEPTIONS = (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError, TimeoutError)
TRANSPORT_FAILURES = {"network_error:" + error.__name__ for error in TRANSPORT_EXCEPTIONS}


class ResponseDeadline:
    """A total response deadline for this single-worker POSIX CLI."""
    def __init__(self, seconds: float):
        self.seconds = seconds

    def start(self) -> None:
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        self.previous_timer = signal.getitimer(signal.ITIMER_REAL)
        self.started = time.monotonic()
        signal.signal(signal.SIGALRM, self.expired)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)

    @staticmethod
    def expired(signum, frame) -> None:
        raise TimeoutError("total response deadline exceeded")

    def restore(self) -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)
        delay, interval = self.previous_timer
        if delay:
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, delay - (time.monotonic() - self.started)), interval)


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def read_tee_sheet(path: Path) -> dict:
    data = json.loads(path.read_text())
    return json.loads(gzip.decompress(base64.b64decode(
        data["data"]["teeTimesCompressedV2"]["payload"]
    )))


def make_plan(inventory_path: Path, venues_path: Path) -> dict:
    inventory = json.loads(inventory_path.read_text())
    venues = json.loads(venues_path.read_text()) if venues_path.exists() else {"events": []}
    venue_map = {row["pga_id"]: row for row in venues["events"]}
    if len(venue_map) != len(venues["events"]):
        raise ValueError("duplicate venue event ID")
    records = []
    source_hours = set()
    for event in inventory["events"]:
        source_path = Path(event["source"]["file"])
        if digest(source_path) != event["source"]["sha256"]:
            raise ValueError(f"tee-sheet hash mismatch: {source_path}")
        tee_sheet = read_tee_sheet(source_path)
        rounds = {r["roundInt"]: r for r in tee_sheet["rounds"] if r["roundInt"] in (1, 2)}
        if set(rounds) != {1, 2}:
            raise ValueError(f"missing opening-round tee sheet: {event['pga_id']}")
        first_times = [g.get("teeTime") for g in rounds[1]["groups"]]
        first_valid = [t for t in first_times if type(t) in (int, float) and math.isfinite(t)]
        if not first_valid:
            raise ValueError(f"no first-round tee times: {event['pga_id']}")
        first_tee = datetime.fromtimestamp(min(first_valid) / 1000, UTC)
        run = first_tee.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        cutoff = first_tee - timedelta(hours=12)
        venue = venue_map.get(event["pga_id"], {})
        lat, lon = venue.get("latitude"), venue.get("longitude")
        venue_ok = (type(lat) in (int, float) and type(lon) in (int, float)
                    and math.isfinite(lat) and math.isfinite(lon)
                    and -90 <= lat <= 90 and -180 <= lon <= 180
                    and not venue.get("ambiguous", True))
        mapped_courses = {str(c["id"]) for c in venue.get("courses", [])}
        for number in (1, 2):
            groups = rounds[number]["groups"]
            course_ids = {str(g.get("courseId")) for g in groups}
            times = [g.get("teeTime") for g in groups]
            missing_times = any(type(t) not in (int, float) or not math.isfinite(t) for t in times)
            reason = None
            if missing_times or len(first_valid) != len(first_times):
                reason = "missing_tee_time"
            elif len(course_ids) != 1:
                reason = "non_single_course_round"
            elif not venue_ok:
                reason = "missing_venue"
            elif not course_ids.issubset(mapped_courses):
                reason = "venue_course_id_mismatch"
            hours = []
            if not missing_times:
                start = math.floor(min(times) / 3_600_000)
                end = math.ceil(max(times) / 3_600_000 + 5)
                hours = [stamp(datetime.fromtimestamp(h * 3600, UTC)) for h in range(start, end + 1)]
            if reason is None:
                for hour in hours:
                    lead = int((parse_stamp(hour) - run).total_seconds() // 3600)
                    if not 0 <= lead <= 120:
                        raise ValueError("declared hourly window exceeds supported hourly lead range")
                    source_hours.add((stamp(run), lead))
            records.append({
                "pga_id": event["pga_id"], "round": number,
                "course_id": next(iter(course_ids)) if len(course_ids) == 1 else None,
                "run_utc": stamp(run), "decision_cutoff_utc": stamp(cutoff),
                "valid_times_utc": hours, "latitude": lat, "longitude": lon,
                "precheck_reason": reason, "tee_sheet_source": event["source"],
            })
    return {
        "inventory": {"path": str(inventory_path), "sha256": digest(inventory_path)},
        "venues": {"path": str(venues_path), "sha256": digest(venues_path) if venues_path.exists() else None},
        "events": len(inventory["events"]), "rounds": len(records),
        "eligible_rounds": sum(r["precheck_reason"] is None for r in records),
        "event_hours": sum(len(r["valid_times_utc"]) for r in records if r["precheck_reason"] is None),
        "unique_source_hours": len(source_hours),
        "estimated_http_requests": len(source_hours) * 2,
        "estimated_uv_bytes_at_source_sample_size": len(source_hours) * 1_921_000,
        "estimated_index_bytes_at_source_sample_size": len(source_hours) * 41_252,
        "records": records,
    }


class StopAcquisition(Exception):
    pass


class MissingSource(Exception):
    pass


class Downloader:
    def __init__(self, output: Path, max_requests: int, max_bytes: int):
        self.output = output
        self.state_path = output / "network-state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {
            "network_requests": 0, "network_bytes": 0, "source_blocked": None,
            "first_started_at_utc": stamp(datetime.now(UTC)),
        }
        if self.state.get("inflight_byte_reservation"):
            # An interrupted socket may have delivered bytes that were never saved.
            # Charge its full bound and require explicit investigation before resuming.
            self.state["network_bytes"] += self.state.pop("inflight_byte_reservation")
            self.state["source_blocked"] = "unresolved_interrupted_request"
            self.persist()
        self.max_requests, self.max_bytes = max_requests, max_bytes
        self.last_start = 0.0

    def persist(self) -> None:
        self.state["updated_at_utc"] = stamp(datetime.now(UTC))
        write_json(self.state_path, self.state)

    def resume_remote_disconnected_once(self) -> None:
        """Spend the one explicitly authorized transport recovery allowance."""
        if self.state.get("remote_disconnected_resume_used"):
            raise StopAcquisition("remote_disconnected_resume_allowance_already_used")
        if self.state["source_blocked"] != "network_error:RemoteDisconnected":
            raise StopAcquisition("resume_requires_remote_disconnected_without_http_response")
        self.recover_transport(permit_partial_success=False)
        self.state["remote_disconnected_resume_used"] = True
        self.persist()

    def recover_transport(self, *, permit_partial_success: bool = True) -> None:
        """Recover at most five verified transport failures, once per URL/range."""
        if self.state["source_blocked"] not in TRANSPORT_FAILURES:
            raise StopAcquisition("transport_recovery_ineligible_error")
        prior = []
        for record in (self.output / "retained-failed-attempts").glob("*/recovery.json"):
            audit = json.loads(record.read_text())
            original = json.loads(Path(audit["retained_metadata_file"]).read_text())
            prior.append((original["url"], original.get("request_headers", {}).get("Range")))
        if len(prior) >= 5:
            raise StopAcquisition("transport_recovery_cap_five")
        failures = []
        for meta_path in (self.output / "raw").rglob("*.meta.json"):
            meta = json.loads(meta_path.read_text())
            if meta.get("failure") == self.state["source_blocked"]:
                failures.append((meta_path, meta))
        if len(failures) != 1:
            raise StopAcquisition("transport_recovery_requires_one_failed_attempt")
        meta_path, meta = failures[0]
        body_path = Path(meta["body_file"])
        if digest(body_path) != meta["sha256"] or body_path.stat().st_size != meta.get("bytes", 0):
            raise StopAcquisition("failed_attempt_integrity_error")
        identity = (meta["url"], meta.get("request_headers", {}).get("Range"))
        if identity in prior:
            raise StopAcquisition("same_url_range_already_retried")
        headers = {key.lower(): value for key, value in meta.get("headers", {}).items()}
        status, size = meta["status"], body_path.stat().st_size
        eligible = status is None and not headers and size == 0
        if permit_partial_success and status in (200, 206):
            try:
                announced = int(headers["content-length"])
            except (KeyError, ValueError):
                announced = -1
            if status == 200:
                eligible = (identity[1] is None and meta["url"].endswith(".idx")
                            and 0 <= size < announced <= 1024 * 1024)
            else:
                requested = re.fullmatch(r"bytes=(\d+)-(\d+)", identity[1] or "")
                returned = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("content-range", ""))
                eligible = bool(requested and returned)
                if eligible:
                    start, end = map(int, requested.groups())
                    actual_start, actual_end, total = map(int, returned.groups())
                    eligible = (0 <= start <= end < total and (start, end) == (actual_start, actual_end)
                                and announced == end - start + 1 and 0 <= size < announced <= 16 * 1024 * 1024)
        if not eligible:
            raise StopAcquisition("transport_recovery_refuses_denial_protocol_or_complete_response")
        received = parse_stamp(meta["received_at_utc"])
        elapsed = (datetime.now(UTC) - received).total_seconds()
        if elapsed < 0:
            raise StopAcquisition("failure_receipt_clock_in_future")
        if elapsed < 60:
            print(json.dumps({"transport_backoff_seconds": 60 - elapsed}), flush=True)
            time.sleep(60 - elapsed)
        archive = self.output / "retained-failed-attempts" / f"transport-{len(prior) + 1}"
        archive.mkdir(parents=True, exist_ok=False)
        retained_body, retained_meta = archive / "body", archive / "metadata.original.json"
        recovery = {
            "reason": meta["failure"], "url": meta["url"], "status": meta["status"],
            "failure_received_at_utc": meta["received_at_utc"],
            "earliest_retry_at_utc": stamp(received + timedelta(seconds=60)),
            "resumed_at_utc": stamp(datetime.now(UTC)),
            "original_body_file": str(body_path), "original_metadata_file": str(meta_path),
            "retained_body_file": str(retained_body), "retained_metadata_file": str(retained_meta),
            "body_sha256": digest(body_path), "metadata_sha256": digest(meta_path),
            "cumulative_requests_before_retry": self.state["network_requests"],
            "cumulative_bytes_before_retry": self.state["network_bytes"],
            "recovery_number": len(prior) + 1, "maximum_total_recoveries": 5,
            "request_identity": {"url": identity[0], "range": identity[1]},
            "note": "Original failed bytes and metadata moved intact; original metadata retains its capture-time body path. Counters and frozen plan are unchanged. One retry per URL/range, at most five transport recoveries. No HTTP denial, protocol mismatch or integrity failure is eligible.",
        }
        write_json(archive / "recovery.json", recovery)
        body_path.rename(retained_body)
        meta_path.rename(retained_meta)
        self.state["transport_recoveries_used"] = len(prior) + 1
        self.state["transport_recovery_file"] = str(archive / "recovery.json")
        self.state["source_blocked"] = None
        self.persist()

    def recover_after_stop(self, error: StopAcquisition) -> None:
        """Preserve the original reason for every non-transport stop."""
        reason = str(error)
        if reason not in TRANSPORT_FAILURES or reason != self.state["source_blocked"]:
            raise error
        self.recover_transport()

    def fetch(self, url: str, path: Path, *, byte_range: tuple[int, int] | None = None) -> dict:
        meta_path = path.with_name(path.name + ".meta.json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            expected_headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
            if (meta["url"] != url or digest(path) != meta["sha256"]
                    or meta["request_headers"] != expected_headers):
                raise StopAcquisition(f"cache_integrity_error:{path}")
            if meta.get("failure"):
                raise MissingSource(meta["failure"])
            return meta
        if path.exists():
            raise StopAcquisition(f"unrecorded_cache_file:{path}")
        if self.state["source_blocked"]:
            raise StopAcquisition(self.state["source_blocked"])
        if self.state["network_requests"] >= self.max_requests:
            raise StopAcquisition("request_cap")
        remaining = self.max_bytes - self.state["network_bytes"]
        expected_bytes = byte_range[1] - byte_range[0] + 1 if byte_range else None
        if remaining <= 0 or (expected_bytes is not None and expected_bytes > remaining):
            raise StopAcquisition("byte_cap")
        if expected_bytes is not None and expected_bytes > 16 * 1024 * 1024:
            raise MissingSource("wind_range_exceeds_16MiB")
        time.sleep(max(0.0, 1.0 - (time.monotonic() - self.last_start)))
        headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
        request = urllib.request.Request(url, headers=headers)
        started = stamp(datetime.now(UTC))
        self.last_start = time.monotonic()
        self.state["network_requests"] += 1
        self.state["inflight_byte_reservation"] = min(remaining, expected_bytes or 1024 * 1024)
        self.persist()
        body = b""
        chunks = []
        response_headers = {}
        status = None
        failure = None
        stop = False
        deadline = ResponseDeadline(REQUEST_DEADLINE_SECONDS)
        deadline.start()
        try:
            try:
                response = urllib.request.urlopen(request, timeout=45)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.status
                response_headers = dict(response.headers)
                lower = {key.lower(): value for key, value in response_headers.items()}
                if status != (206 if byte_range else 200):
                    failure = f"http_{status}"
                    stop = status != 404
                    if stop:
                        self.state["source_blocked"] = failure
                elif byte_range:
                    content_range = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", lower.get("content-range", ""))
                    if not content_range or tuple(map(int, content_range.groups()[:2])) != byte_range:
                        failure, stop = "invalid_content_range", True
                limit = min(remaining, expected_bytes if expected_bytes else 1024 * 1024)
                announced = int(lower["content-length"]) if "content-length" in lower else None
                if announced is not None and announced > limit and failure is None:
                    failure, stop = "response_exceeds_byte_limit", True
                # Never read a full forecast object when a server ignores Range.
                if not (byte_range and status == 200) and not (failure and status in (200, 206)):
                    read_limit = min(limit, 64 * 1024) if failure else limit
                    consumed = 0
                    while consumed < read_limit:
                        chunk = response.read(min(64 * 1024, read_limit - consumed))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        consumed += len(chunk)
                    body = b"".join(chunks)
                    if failure is None and (announced is None or len(body) != announced):
                        failure = "unverified_or_incomplete_content_length"
                    if failure is None and expected_bytes is not None and len(body) != expected_bytes:
                        failure = "incomplete_range"
        except (OSError, ValueError) as error:
            # urllib wraps some socket exceptions; unwrap only this allowlist.
            if isinstance(error, urllib.error.URLError) and isinstance(error.reason, TRANSPORT_EXCEPTIONS):
                error = error.reason
            if failure is None:
                failure = f"network_error:{type(error).__name__}"
            stop = True
        finally:
            deadline.restore()
        body = b"".join(chunks)
        self.state["network_bytes"] += len(body)
        self.state.pop("inflight_byte_reservation", None)
        if stop:
            self.state["source_blocked"] = failure
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(body)
        meta = {
            "url": url, "request_headers": headers, "status": status,
            "request_started_at_utc": started, "received_at_utc": stamp(datetime.now(UTC)),
            "headers": response_headers, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "body_file": str(path), "failure": failure,
        }
        write_json(meta_path, meta)
        self.persist()
        if stop:
            raise StopAcquisition(failure)
        if failure:
            raise MissingSource(failure)
        return meta


def wind_byte_range(index: str) -> tuple[int, int]:
    lines = [line.split(":") for line in index.splitlines() if line.strip()]
    u = [i for i, fields in enumerate(lines) if fields[3:5] == ["UGRD", "10 m above ground"]]
    v = [i for i, fields in enumerate(lines) if fields[3:5] == ["VGRD", "10 m above ground"]]
    if len(u) != 1 or len(v) != 1 or v[0] != u[0] + 1 or v[0] + 1 >= len(lines):
        raise MissingSource("missing_or_nonadjacent_10m_wind_records")
    start, end = int(lines[u[0]][1]), int(lines[v[0] + 1][1]) - 1
    if start < 0 or end <= start:
        raise MissingSource("invalid_index_offsets")
    return start, end


def decode_uv(path: Path, run: datetime, valid: datetime, lat: float, lon: float) -> dict:
    import eccodes
    values = {}
    with path.open("rb") as stream:
        while (gid := eccodes.codes_grib_new_from_file(stream)) is not None:
            try:
                name = eccodes.codes_get(gid, "shortName")
                checks = {
                    "edition": 2, "centre": 7, "productionStatusOfProcessedData": 0,
                    "typeOfProcessedData": 1, "dataDate": int(run.strftime("%Y%m%d")),
                    "dataTime": int(run.strftime("%H%M")), "validityDate": int(valid.strftime("%Y%m%d")),
                    "validityTime": int(valid.strftime("%H%M")), "level": 10,
                    "forecastTime": int((valid - run).total_seconds() / 3600), "stepUnits": 1,
                }
                if name not in ("10u", "10v") or name in values:
                    raise MissingSource("invalid_grib_variable_identity")
                if any(eccodes.codes_get(gid, key, int) != value for key, value in checks.items()):
                    raise MissingSource("invalid_grib_time_or_operational_identity")
                if (eccodes.codes_get(gid, "gridType") != "regular_ll"
                        or eccodes.codes_get(gid, "iDirectionIncrementInDegrees") != 0.25
                        or eccodes.codes_get(gid, "jDirectionIncrementInDegrees") != 0.25
                        or eccodes.codes_get(gid, "typeOfLevel") != "heightAboveGround"
                        or eccodes.codes_get(gid, "stepType") != "instant"
                        or eccodes.codes_get(gid, "units") != "m s**-1"):
                    raise MissingSource("invalid_grib_grid_level_units")
                point = eccodes.codes_grib_find_nearest(gid, lat, lon, is_lsm=False, npoints=1)[0]
                if (eccodes.codes_get(gid, "numberOfMissing", int) > 0
                        and point["value"] == eccodes.codes_get(gid, "missingValue")):
                    raise MissingSource("missing_nearest_wind_value")
                values[name] = {key: point[key] for key in ("lat", "lon", "value", "distance", "index")}
            finally:
                eccodes.codes_release(gid)
    if set(values) != {"10u", "10v"}:
        raise MissingSource("incomplete_uv_messages")
    u, v = values["10u"], values["10v"]
    if u["index"] != v["index"] or any(not math.isfinite(p["value"]) for p in (u, v)):
        raise MissingSource("invalid_nearest_wind_values")
    return {"wind_kmh": 3.6 * math.hypot(u["value"], v["value"]), "u_mps": u["value"],
            "v_mps": v["value"], "grid_latitude": u["lat"],
            "grid_longitude": (u["lon"] + 180) % 360 - 180, "grid_distance_km": u["distance"]}


def acquire_hour(downloader: Downloader, row: dict, valid_string: str) -> dict:
    run, valid = parse_stamp(row["run_utc"]), parse_stamp(valid_string)
    lead = int((valid - run).total_seconds() / 3600)
    key = f"gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f{lead:03d}"
    index_path = downloader.output / "raw" / (key + ".idx")
    body_path = downloader.output / "raw" / (key + ".uv.grib2")
    index_meta = downloader.fetch(BASE + key + ".idx", index_path)
    byte_range = wind_byte_range(index_path.read_text())
    body_meta = downloader.fetch(BASE + key, body_path, byte_range=byte_range)
    headers = {k.lower(): v for k, v in body_meta["headers"].items()}
    index_headers = {k.lower(): v for k, v in index_meta["headers"].items()}
    if "last-modified" not in headers:
        raise MissingSource("missing_object_last_modified")
    modified = parsedate_to_datetime(headers["last-modified"]).astimezone(UTC)
    if modified > parse_stamp(row["decision_cutoff_utc"]):
        raise MissingSource("object_after_decision_cutoff")
    import eccodes
    try:
        decoded = decode_uv(body_path, run, valid, row["latitude"], row["longitude"])
    except eccodes.CodesInternalError as error:
        raise MissingSource(f"invalid_grib_decode:{type(error).__name__}") from error
    return {**decoded, "valid_time_utc": valid_string, "run_utc": row["run_utc"],
            "object_last_modified_utc": stamp(modified),
            "index_last_modified": index_headers.get("last-modified"),
            "source_files": [str(index_path), str(body_path)],
            "object_metadata_file": str(body_path) + ".meta.json",
            "index_metadata_file": str(index_path) + ".meta.json"}


def summarize_rounds(plan: dict, hours: dict) -> list[dict]:
    records = []
    for row in plan["records"]:
        samples = [hours.get(row["pga_id"] + "/" + valid) for valid in row["valid_times_utc"]]
        errors = {valid: sample.get("reason") if sample else "pending"
                  for valid, sample in zip(row["valid_times_utc"], samples)
                  if sample is None or not sample.get("success")}
        reason = row["precheck_reason"] or ("missing_forecast_hours" if errors else None)
        values = [sample["wind_kmh"] if sample and sample.get("success") else None for sample in samples]
        wind_range = max(values) - min(values) if reason is None and values else None
        records.append({
            "pga_id": row["pga_id"], "round": row["round"], "course_id": row["course_id"],
            "classified": reason is None and wind_range is not None,
            "volatile": wind_range >= 10 if wind_range is not None else None,
            "wind_range_kmh": wind_range, "wind_values_kmh": values,
            "valid_times_utc": row["valid_times_utc"], "reason": reason,
            "run_utc": row["run_utc"], "decision_cutoff_utc": row["decision_cutoff_utc"],
            "source_files": sorted({path for sample in samples if sample and sample.get("success")
                                    for path in sample["source_files"]}),
            "hour_errors": errors,
        })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("reports/golf-weather-group-inventory-2026-09-14.json"))
    parser.add_argument("--venues", type=Path, default=Path("config/golf-weather-venues-2025.json"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/golf-weather"))
    parser.add_argument("--summary", type=Path, default=Path("reports/golf-weather-acquisition-2026-09-14.json"))
    parser.add_argument("--max-requests", type=int, default=3000)
    parser.add_argument("--max-bytes", type=int, default=3_000_000_000)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume-remote-disconnected-once", action="store_true")
    parser.add_argument("--recover-transport", action="store_true")
    args = parser.parse_args()
    recovery_policy = Path("reports/golf-weather-acquisition-policy-2026-09-14.md")
    if not 1 <= args.max_requests <= 3000 or not 1 <= args.max_bytes <= 3_000_000_000:
        parser.error("limits must be positive and no larger than 3000 requests / 3 GB")
    if args.resume_remote_disconnected_once and not args.execute:
        parser.error("transport resume requires --execute")
    if args.recover_transport and (not args.execute or args.resume_remote_disconnected_once):
        parser.error("--recover-transport requires --execute and cannot be combined with the legacy resume flag")
    if args.recover_transport and not recovery_policy.exists():
        parser.error("record the administrative transport policy before resuming")
    plan = make_plan(args.inventory, args.venues)
    declaration = Path("reports/golf-weather-declaration-2026-09-14.md")
    plan["declaration_sha256"] = digest(declaration)
    if not args.execute:
        write_json(args.output / "cost-plan.json", plan)
        print(json.dumps({key: value for key, value in plan.items() if key != "records"}, indent=2))
        return 0
    if not args.venues.exists():
        parser.error("final venue map is required for execution")
    import eccodes
    plan_path = args.output / "plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError("Frozen acquisition plan changed; do not merge different cohorts or coordinates")
    write_json(plan_path, plan)
    hours_path = args.output / "hours.json"
    hours = json.loads(hours_path.read_text()) if hours_path.exists() else {}
    downloader = Downloader(args.output, args.max_requests, args.max_bytes)
    if args.resume_remote_disconnected_once:
        downloader.resume_remote_disconnected_once()
    if args.recover_transport and downloader.state["source_blocked"]:
        downloader.recover_transport()
    stop_reason = None
    tasks = {(row["pga_id"], valid): row for row in plan["records"]
             if row["precheck_reason"] is None for valid in row["valid_times_utc"]}

    def checkpoint() -> dict:
        records = summarize_rounds(plan, hours)
        pending = sum(pga_id + "/" + valid not in hours for pga_id, valid in tasks)
        summary = {
            "complete": pending == 0 and stop_reason is None and not downloader.state["source_blocked"],
            "pending_event_hours": pending, "pending_http_requests_upper_bound": pending * 2,
            "events": plan["events"], "rounds": plan["rounds"], "planned_event_hours": len(tasks),
            "unique_source_hours": plan["unique_source_hours"], "stop_reason": stop_reason,
            "successful_event_hours": sum(x.get("success", False) for x in hours.values()),
            "failed_event_hours": sum(not x.get("success", False) for x in hours.values()),
            "classified_rounds": sum(r["classified"] for r in records),
            "volatile_rounds": sum(r["volatile"] is True for r in records),
            "unclassified_rounds": [{"pga_id": r["pga_id"], "round": r["round"], "reason": r["reason"]}
                                    for r in records if not r["classified"]],
            "network": downloader.state, "caps": {"requests": args.max_requests, "bytes": args.max_bytes},
            "request_spacing_seconds": 1, "network_timeout_seconds": 45,
            "total_response_deadline_seconds": REQUEST_DEADLINE_SECONDS,
            "transport_recovery_enabled": args.recover_transport,
            "transport_recovery_policy": {"path": str(recovery_policy), "sha256": digest(recovery_policy)}
            if args.recover_transport else None,
            "decoder_version": eccodes.codes_get_api_version(),
            "plan_file": str(plan_path), "plan_sha256": digest(plan_path),
            "rounds_file": str(args.output / "rounds.json"),
            "recorded_at_utc": stamp(datetime.now(UTC)),
            "historical_public_availability_proven": False, "outcomes_loaded": False,
        }
        write_json(hours_path, hours)
        write_json(args.output / "rounds.json", records)
        summary["hours_sha256"] = digest(hours_path)
        summary["rounds_sha256"] = digest(args.output / "rounds.json")
        write_json(args.summary, summary)
        return summary

    checkpoint()
    try:
        for (pga_id, valid), row in tasks.items():
            hour_key = pga_id + "/" + valid
            if hour_key in hours:
                continue
            try:
                while True:
                    try:
                        sample = acquire_hour(downloader, row, valid)
                        break
                    except StopAcquisition as error:
                        if not args.recover_transport:
                            raise
                        downloader.recover_after_stop(error)
                hours[hour_key] = {"success": True, **sample}
            except MissingSource as error:
                hours[hour_key] = {"success": False, "reason": str(error), "valid_time_utc": valid}
            checkpoint()
            if len(hours) % 20 == 0:
                print(json.dumps({"processed_hours": len(hours), "total_hours": len(tasks),
                                  "requests": downloader.state["network_requests"],
                                  "bytes": downloader.state["network_bytes"]}), flush=True)
    except StopAcquisition as error:
        stop_reason = str(error)
    except KeyboardInterrupt:
        stop_reason = "interrupted"
    finally:
        summary = checkpoint()
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
