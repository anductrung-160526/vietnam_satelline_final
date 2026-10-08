"""Regression checks for Earth Engine throttling; no credentials or live API needed."""
import os
import threading
import time
import tempfile
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(os.environ, {"VNGIS_SKIP_MAIN": "1"}):
    import vngis_2024 as v


class EarthEngineRequestTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("EE_SEM", threading.BoundedSemaphore(1)),
                            ("STOP_EVENT", threading.Event()), ("_ee_cooldown_until", 0.0),
                            ("EE_CREDENTIALS", None), ("communes_fc", None)):
            p = patch.object(v, name, value)
            p.start()
            self.addCleanup(p.stop)

    def fake_clock(self):
        now, waits = [0.0], []

        def wait(delay):
            waits.append(delay)
            now[0] += delay

        for p in (patch.object(v.time, "monotonic", side_effect=lambda: now[0]),
                  patch.object(v.STOP_EVENT, "wait", side_effect=wait),
                  patch.object(v.random, "uniform", return_value=0)):
            p.start()
            self.addCleanup(p.stop)
        return waits

    def test_queries_and_downloads_share_one_limit(self):
        lock = threading.Lock()
        active, peak, completed = 0, 0, 0

        def request(result):
            nonlocal active, peak, completed
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.003)
            with lock:
                active -= 1
                completed += 1
            return result

        obj = SimpleNamespace(getInfo=lambda: request({"ok": True}))
        image = SimpleNamespace(getDownloadURL=lambda params: request("https://example.invalid/tif"))
        response = SimpleNamespace(status_code=200, content=b"x" * 200)
        with patch.object(v, "_http_get", side_effect=lambda url: request(response)):
            with ThreadPoolExecutor(max_workers=12) as pool:
                jobs = [pool.submit(v.ee_getinfo, obj) if i % 2 else
                        pool.submit(v.fetch_geotiff_bytes, image, "region", 20) for i in range(24)]
                for job in jobs:
                    self.assertTrue(job.result())
        self.assertEqual(completed, 36)
        self.assertEqual(peak, 1)

    def test_getinfo_429_backoff_and_retry(self):
        waits = self.fake_clock()
        obj = SimpleNamespace(getInfo=Mock(side_effect=[v.ee.EEException("HTTP 429"),
                                                        v.ee.EEException("Too Many Requests"), {"ok": True}]))
        self.assertEqual(v.ee_getinfo(obj), {"ok": True})
        self.assertEqual(waits, [5, 10])

    def test_download_429_respects_retry_after(self):
        waits = self.fake_clock()
        image = SimpleNamespace(getDownloadURL=Mock(return_value="url"))
        limited = SimpleNamespace(status_code=429, text="Restricted Mode concurrency limit",
                                  headers={"Retry-After": "20"})
        ok = SimpleNamespace(status_code=200, content=b"x" * 200)
        with patch.object(v, "_http_get", side_effect=[limited, ok]) as http:
            self.assertEqual(v.fetch_geotiff_bytes(image, "region", 20), ok.content)
        self.assertEqual(http.call_count, 2)
        self.assertEqual(waits, [20])
        self.assertEqual(image.getDownloadURL.call_args.args[0]["scale"], 20)

    def test_url_generation_429_retries_before_download(self):
        waits = self.fake_clock()
        image = SimpleNamespace(getDownloadURL=Mock(side_effect=[v.ee.EEException("HTTP 429"), "url"]))
        response = SimpleNamespace(status_code=200, content=b"x" * 200)
        with patch.object(v, "_http_get", return_value=response) as http:
            self.assertEqual(v.fetch_geotiff_bytes(image, "region", 500), response.content)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(waits, [5])

    def test_final_429_pauses_other_queries_and_retries_are_bounded(self):
        waits = self.fake_clock()
        failing = Mock(side_effect=v.ee.EEException("HTTP 429"))
        with self.assertRaisesRegex(RuntimeError, "sau 2 lần"):
            v._ee_call(failing, max_retry=2)
        self.assertEqual(failing.call_count, 2)
        self.assertEqual(v.ee_getinfo(SimpleNamespace(getInfo=lambda: "ok")), "ok")
        self.assertEqual(waits, [5, 10])

    def test_stop_interrupts_backoff(self):
        failing = Mock(side_effect=v.ee.EEException("HTTP 429"))
        with patch.object(v.STOP_EVENT, "wait", side_effect=lambda delay: v.STOP_EVENT.set()):
            with self.assertRaises(v.StopRequested):
                v._ee_call(failing)
        self.assertEqual(failing.call_count, 1)

    def test_repeated_429_has_capped_backoff(self):
        waits = self.fake_clock()
        failing = Mock(side_effect=v.ee.EEException("HTTP 429"))
        with self.assertRaisesRegex(RuntimeError, "sau 8 lần"):
            v._ee_call(failing, max_retry=8)
        self.assertEqual(waits, [5, 10, 20, 40, 60, 60, 60])
        self.assertEqual(failing.call_count, 8)

    def test_permission_and_size_errors_do_not_retry(self):
        with patch.object(v.STOP_EVENT, "wait") as wait:
            for message, error in (("HTTP 403 permission denied", v.PermanentError),
                                   ("Pixel grid dimensions too large", v.TooLargeError)):
                call = Mock(side_effect=v.ee.EEException(message))
                with self.assertRaises(error):
                    v._ee_call(call)
                self.assertEqual(call.call_count, 1)
            wait.assert_not_called()

    def test_http_403_remains_permanent(self):
        image = SimpleNamespace(getDownloadURL=lambda params: "url")
        response = SimpleNamespace(status_code=403, text="Forbidden")
        with patch.object(v, "_http_get", return_value=response) as http:
            with self.assertRaises(v.PermanentError):
                v.fetch_geotiff_bytes(image, "region", 20)
            self.assertEqual(http.call_count, 1)

    def test_bbox_uses_limited_query(self):
        geometry = Mock()
        with patch.object(v, "ee_getinfo", return_value={"coordinates": [[[1, 2], [3, 4]]]}) as query:
            self.assertEqual(v._bbox(geometry), (1, 2, 3, 4))
        geometry.bounds.assert_called_once_with(maxError=1)
        query.assert_called_once_with(geometry.bounds.return_value)

    def test_retry_after_http_date_and_invalid_values(self):
        with patch.object(v.time, "time", return_value=1000):
            self.assertEqual(v._retry_after_seconds(formatdate(1020, usegmt=True)), 20)
        for value in (None, "invalid", "-5"):
            self.assertEqual(v._retry_after_seconds(value), 0)

    def test_project_is_explicit_and_logged_independently_of_account_email(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as key:
            json.dump({"client_email": "runner@other-project.iam.gserviceaccount.com"}, key)
            key.flush()
            with patch.object(v, "EE_KEY_FILE", key.name), patch.object(v, "PROJECT_ID", "vngis-ee-2"), \
                 patch.object(v, "EE_HIGH_VOLUME", False), \
                 patch.object(v.ee, "ServiceAccountCredentials", return_value="fake-credentials"), \
                 patch.object(v.ee, "Initialize") as initialize, \
                 patch.object(v.ee.data, "setDeadline"), patch.object(v.ee, "FeatureCollection"), \
                 self.assertLogs(v.log, level="INFO") as logs:
                v.init_earth_engine()
        initialize.assert_called_once_with(credentials="fake-credentials", project="vngis-ee-2")
        self.assertIn("project=vngis-ee-2", logs.output[0])
        self.assertIn("runner@other-project", logs.output[0])


if __name__ == "__main__":
    unittest.main()
