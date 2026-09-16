"""Offline checks for the bounded operational-weather acquisition."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "golf_weather_acquire", Path(__file__).parents[1] / "tools/acquire_golf_weather.py"
)
acquire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acquire)


class Response(io.BytesIO):
    def __init__(self, data, status, headers):
        super().__init__(data)
        self.status, self.headers, self.reads = status, headers, 0

    def read(self, size=-1):
        self.reads += 1
        return super().read(size)


class WeatherAcquisitionTests(unittest.TestCase):
    def test_request_cap_prevents_network_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 1, 100)
            downloader.state["network_requests"] = 1
            with patch.object(acquire.urllib.request, "urlopen") as request:
                with self.assertRaisesRegex(acquire.StopAcquisition, "request_cap"):
                    downloader.fetch("https://example.invalid/file", Path(tmp) / "file")
                request.assert_not_called()

    def test_byte_cap_prevents_oversized_range_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 20)
            with patch.object(acquire.urllib.request, "urlopen") as request:
                with self.assertRaisesRegex(acquire.StopAcquisition, "byte_cap"):
                    downloader.fetch("https://example.invalid/file", Path(tmp) / "file", byte_range=(0, 20))
                request.assert_not_called()

    def test_ignored_range_never_reads_full_object(self):
        response = Response(b"full object", 200, {"Content-Length": "540000000"})
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 100)
            with patch.object(acquire.urllib.request, "urlopen", return_value=response):
                with self.assertRaises(acquire.StopAcquisition):
                    downloader.fetch("https://example.invalid/file", Path(tmp) / "file", byte_range=(0, 9))
            self.assertEqual(response.reads, 0)
            self.assertEqual(downloader.state["network_bytes"], 0)

    def test_partial_read_bytes_are_retained_and_counted(self):
        response = Response(b"abc", 206, {"Content-Length": "6", "Content-Range": "bytes 0-5/6"})
        original_read = response.read

        def fail_after_first(size):
            if response.reads:
                raise TimeoutError("read timed out")
            return original_read(size)

        response.read = fail_after_first
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 100)
            path = Path(tmp) / "file"
            with patch.object(acquire.urllib.request, "urlopen", return_value=response):
                with self.assertRaises(acquire.StopAcquisition):
                    downloader.fetch("https://example.invalid/file", path, byte_range=(0, 5))
            self.assertEqual(path.read_bytes(), b"abc")
            self.assertEqual(downloader.state["network_bytes"], 3)
            self.assertEqual(json.loads(Path(str(path) + ".meta.json").read_text())["bytes"], 3)

    def test_cache_integrity_failure_never_fetches(self):
        response = Response(b"abc", 200, {"Content-Length": "3"})
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 100)
            path = Path(tmp) / "file"
            with patch.object(acquire.urllib.request, "urlopen", return_value=response):
                downloader.fetch("https://example.invalid/file", path)
            path.write_bytes(b"modified")
            with patch.object(acquire.urllib.request, "urlopen") as request:
                with self.assertRaisesRegex(acquire.StopAcquisition, "cache_integrity_error"):
                    downloader.fetch("https://example.invalid/file", path)
                request.assert_not_called()

    def test_missing_hour_never_shortens_classification_window(self):
        row = {"pga_id": "R1", "round": 1, "course_id": "C1", "run_utc": "run",
               "decision_cutoff_utc": "cutoff", "valid_times_utc": ["h1", "h2", "h3"],
               "precheck_reason": None}
        hours = {"R1/h1": {"success": True, "wind_kmh": 0, "source_files": []},
                 "R1/h2": {"success": True, "wind_kmh": 10, "source_files": []}}
        result = acquire.summarize_rounds({"records": [row]}, hours)[0]
        self.assertFalse(result["classified"])
        self.assertIsNone(result["volatile"])
        self.assertIsNone(result["wind_range_kmh"])
        hours["R1/h3"] = {"success": True, "wind_kmh": 5, "source_files": []}
        result = acquire.summarize_rounds({"records": [row]}, hours)[0]
        self.assertTrue(result["classified"])
        self.assertTrue(result["volatile"])
        self.assertEqual(result["wind_range_kmh"], 10)

    def test_transport_resume_preserves_failed_attempt_and_counters_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            downloader = acquire.Downloader(output, 100, 10000)
            downloader.state.update(network_requests=12, network_bytes=1234,
                                    source_blocked="network_error:RemoteDisconnected")
            path = output / "raw" / "failed.grib2"
            path.parent.mkdir()
            path.write_bytes(b"")
            meta_path = Path(str(path) + ".meta.json")
            meta = {"body_file": str(path), "sha256": acquire.digest(path),
                    "url": "https://example.invalid/file", "status": None,
                    "failure": "network_error:RemoteDisconnected",
                    "received_at_utc": "2020-01-01T00:00:00Z"}
            acquire.write_json(meta_path, meta)
            original_meta = meta_path.read_bytes()
            with patch.object(acquire.urllib.request, "urlopen") as request:
                downloader.resume_remote_disconnected_once()
                request.assert_not_called()
            self.assertEqual(downloader.state["network_requests"], 12)
            self.assertEqual(downloader.state["network_bytes"], 1234)
            self.assertIsNone(downloader.state["source_blocked"])
            self.assertFalse(path.exists())
            retained = Path(downloader.state["transport_recovery_file"]).parent
            self.assertEqual((retained / "metadata.original.json").read_bytes(), original_meta)
            self.assertEqual((retained / "body").read_bytes(), b"")
            downloader.state["source_blocked"] = "network_error:RemoteDisconnected"
            with self.assertRaisesRegex(acquire.StopAcquisition, "allowance_already_used"):
                downloader.resume_remote_disconnected_once()

    def test_transport_resume_refuses_http_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 100, 10000)
            downloader.state["source_blocked"] = "http_403"
            with patch.object(acquire.urllib.request, "urlopen") as request:
                with self.assertRaisesRegex(acquire.StopAcquisition, "resume_requires_remote"):
                    downloader.resume_remote_disconnected_once()
                request.assert_not_called()

    def make_partial_failure(self, output, *, content_range="bytes 0-5/20", status=206):
        downloader = acquire.Downloader(output, 100, 10000)
        downloader.state.update(network_requests=12, network_bytes=1234,
                                source_blocked="network_error:BrokenPipeError")
        path = output / "raw" / "failed.grib2"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"abc")
        meta = {"body_file": str(path), "sha256": acquire.digest(path), "bytes": 3,
                "url": "https://example.invalid/file", "status": status,
                "request_headers": {"Range": "bytes=0-5"},
                "headers": {"Content-Range": content_range, "Content-Length": "6"},
                "failure": "network_error:BrokenPipeError", "received_at_utc": "2020-01-01T00:00:00Z"}
        acquire.write_json(Path(str(path) + ".meta.json"), meta)
        return downloader, path, meta

    def test_valid_partial_206_is_retained_and_same_request_cannot_retry_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader, path, meta = self.make_partial_failure(Path(tmp))
            downloader.recover_transport()
            retained = Path(downloader.state["transport_recovery_file"]).parent
            self.assertEqual((retained / "body").read_bytes(), b"abc")
            self.assertEqual(downloader.state["network_bytes"], 1234)
            self.assertEqual(downloader.state["transport_recoveries_used"], 1)
            path.write_bytes(b"abc")
            acquire.write_json(Path(str(path) + ".meta.json"), meta)
            downloader.state["source_blocked"] = "network_error:BrokenPipeError"
            with self.assertRaisesRegex(acquire.StopAcquisition, "same_url_range_already"):
                downloader.recover_transport()

    def test_partial_success_requires_exact_range_and_never_accepts_denial(self):
        for content_range, status in [("bytes 1-6/20", 206), ("bytes 0-5/20", 403)]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                downloader, _, _ = self.make_partial_failure(Path(tmp), content_range=content_range, status=status)
                with self.assertRaisesRegex(acquire.StopAcquisition, "refuses_denial_protocol"):
                    downloader.recover_transport()

    def test_global_transport_cap_includes_retained_old_recoveries(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            downloader, _, _ = self.make_partial_failure(output)
            for number in range(5):
                archive = output / "retained-failed-attempts" / str(number)
                original = archive / "metadata.original.json"
                acquire.write_json(original, {"url": f"https://example.invalid/{number}", "request_headers": {}})
                acquire.write_json(archive / "recovery.json", {"retained_metadata_file": str(original)})
            with self.assertRaisesRegex(acquire.StopAcquisition, "cap_five"):
                downloader.recover_transport()

    def test_total_deadline_interrupts_read_and_restores_alarm(self):
        response = Response(b"abc", 206, {"Content-Length": "6", "Content-Range": "bytes 0-5/6"})
        response.read = lambda size: time.sleep(1)
        previous = acquire.signal.getsignal(acquire.signal.SIGALRM)
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 100)
            started = time.monotonic()
            with patch.object(acquire, "REQUEST_DEADLINE_SECONDS", 0.05), \
                    patch.object(acquire.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(acquire.StopAcquisition, "TimeoutError"):
                    downloader.fetch("https://example.invalid/file", Path(tmp) / "file", byte_range=(0, 5))
            self.assertLess(time.monotonic() - started, 0.8)
            self.assertEqual(acquire.signal.getsignal(acquire.signal.SIGALRM), previous)
            self.assertEqual(acquire.signal.getitimer(acquire.signal.ITIMER_REAL), (0, 0))

    def test_non_transport_stop_keeps_original_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 100)
            for reason in ("request_cap", "byte_cap", "http_403", "invalid_content_range", "cache_integrity_error"):
                downloader.state["source_blocked"] = reason
                with self.subTest(reason=reason), patch.object(downloader, "recover_transport") as recovery:
                    with self.assertRaisesRegex(acquire.StopAcquisition, "^" + reason + "$"):
                        downloader.recover_after_stop(acquire.StopAcquisition(reason))
                    recovery.assert_not_called()
            downloader.state["source_blocked"] = "network_error:BrokenPipeError"
            with self.assertRaisesRegex(acquire.StopAcquisition, "TimeoutError"):
                downloader.recover_after_stop(acquire.StopAcquisition("network_error:TimeoutError"))

    def test_urlerror_normalizes_only_allowed_underlying_exception(self):
        for underlying, expected in ((TimeoutError("timeout"), "TimeoutError"), (OSError("other"), "URLError")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                downloader = acquire.Downloader(Path(tmp), 10, 100)
                with patch.object(acquire.urllib.request, "urlopen", side_effect=acquire.urllib.error.URLError(underlying)):
                    with self.assertRaisesRegex(acquire.StopAcquisition, "network_error:" + expected):
                        downloader.fetch("https://example.invalid/file.idx", Path(tmp) / "file.idx")

    def test_denial_body_transport_error_keeps_http_reason(self):
        response = Response(b"denial", 403, {"Content-Length": "6"})
        response.read = lambda size: (_ for _ in ()).throw(TimeoutError("timeout"))
        with tempfile.TemporaryDirectory() as tmp:
            downloader = acquire.Downloader(Path(tmp), 10, 100)
            with patch.object(acquire.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(acquire.StopAcquisition, "^http_403$"):
                    downloader.fetch("https://example.invalid/file.idx", Path(tmp) / "file.idx")


if __name__ == "__main__":
    unittest.main()
