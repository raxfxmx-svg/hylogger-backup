"""Offline checks for the 150-hole background download; no network requests."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import download as d


class DownloadSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.temp.name)
        d.CONTROL = None

    def tearDown(self):
        d.CONTROL = None
        assert self.root.resolve().parent == Path(__file__).resolve().parent
        self.temp.cleanup()

    def downloader(self, hole="TEST"):
        return d.HoleDownloader(hole, "wa", self.root, self.root / "cache")

    def test_real_source_ids_stay_distinct_and_within_raw(self):
        source = ["79/9D1", "79%2F9D1", "Akubra 1", "19AFRD2003", "..", "CON", "foo."]
        names = [d.local_hole_name(x) for x in source]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[0], "79%2F9D1")
        self.assertEqual(names[2], "Akubra 1")
        self.assertEqual(names[3], "19AFRD2003")
        for hole in source:
            obj = self.downloader(hole)
            self.assertEqual(obj.raw_dir.resolve().parent, (self.root / "raw").resolve())
            self.assertEqual(obj.hole_id, hole)
        with self.assertRaises(ValueError):
            d.load_download_hole_ids(["abc", "ABC"], None)

    def test_spectrum_continues_at_next_sample(self):
        obj = self.downloader()
        obj.reader = Mock()
        obj.reader.get_spectrallog_datasets.return_value = struct.pack("<ff", 2, 3)
        folder = obj.raw_dir / "spectral"
        folder.mkdir()
        part = folder / "log_Base.f32.part"
        part.write_bytes(struct.pack("<f", 1))
        result = obj.download_spectra([{"log_id": "log", "log_name": "Base", "sample_count": 3, "wavelengths": [100]}])
        obj.reader.get_spectrallog_datasets.assert_called_once_with("log", start_sample_no="1", end_sample_no="2")
        self.assertEqual((folder / "log_Base.f32").read_bytes(), struct.pack("<fff", 1, 2, 3))
        self.assertFalse(part.exists())
        self.assertEqual(result[0]["status"], "complete")

    def test_profile_continues_at_next_record(self):
        obj = self.downloader()
        obj.reader = Mock()
        obj.reader.get_profilometer_datasets.return_value = [{"n": 1}, {"n": 2}]
        folder = obj.raw_dir / "profilometer"
        folder.mkdir()
        part = folder / "log_Profile.jsonl.part"
        part.write_text('{"n": 0}\n', encoding="utf-8")
        result = obj.download_profilometer([{"log_id": "log", "log_name": "Profile", "sample_count": 3}])
        obj.reader.get_profilometer_datasets.assert_called_once_with("log", start_sample_no="1", end_sample_no="2")
        self.assertEqual(result[0]["records"], 3)
        self.assertEqual([json.loads(x)["n"] for x in (folder / "log_Profile.jsonl").read_text().splitlines()], [0, 1, 2])

    def test_each_dataset_gets_thumbnails_but_no_full_images(self):
        obj = self.downloader()
        reader = obj.reader = Mock()
        reader.get_tray_thumb_imglogs.side_effect = lambda did: [{"log_id": did + "thumb", "log_name": "Tray Thumbnail Images", "sample_count": 1}]
        reader.get_all_imglogs.side_effect = lambda did: [
            {"log_id": did + "thumb", "log_name": "Tray Thumbnail Images", "sample_count": 1},
            {"log_id": did + "tray", "log_name": "Tray Images", "sample_count": 10},
            {"log_id": did + "img", "log_name": "Imagery", "sample_count": 1000},
        ]
        reader.get_tray_depths.return_value = [{"sample_no": 0, "start_value": 10, "end_value": 20}]
        reader.get_tray_thumb_jpg.return_value = b"\xff\xd8OK\xff\xd9"
        result = obj.download_images([{"dataset_id": "a"}, {"dataset_id": "b"}])
        self.assertEqual({x["dataset_id"] for x in result["files"]}, {"a", "b"})
        self.assertEqual(reader.get_tray_thumb_jpg.call_count, 2)
        reader.get_image.assert_not_called()
        omitted = [x for x in result["logs"] if x["log_name"] in {"Tray Images", "Imagery"}]
        self.assertEqual(len(omitted), 4)
        self.assertTrue(all(x["status"] == "metadata_only" and x["downloaded"] == 0 for x in omitted))

    def test_space_pause_preserves_breakpoint_and_queued_holes_do_not_start(self):
        obj = self.downloader()
        folder = obj.raw_dir / "spectral"
        folder.mkdir()
        part = folder / "log_Base.f32.part"
        original = struct.pack("<f", 1)
        part.write_bytes(original)
        d.CONTROL = d.DownloadControl([self.root], 100)
        obj.reader = Mock()
        with patch.object(d.shutil, "disk_usage", return_value=SimpleNamespace(free=99)):
            with self.assertRaises(d.DownloadPaused):
                obj.download_spectra([{"log_id": "log", "log_name": "Base", "sample_count": 3, "wavelengths": [100]}])
        self.assertEqual(part.read_bytes(), original)
        obj.reader.get_spectrallog_datasets.assert_not_called()
        queued = d.download_one("NEXT", "wa", self.root, self.root / "cache")
        self.assertEqual(queued.status, "paused")
        self.assertFalse((self.root / "raw" / "NEXT").exists())

    def test_optional_call_does_not_swallow_pause(self):
        obj = self.downloader()
        with self.assertRaises(d.DownloadPaused):
            obj.call("optional", Mock(side_effect=d.DownloadPaused("test")), optional=True)
        self.assertFalse(obj.warnings)

    def test_stop_file_and_atomic_write_respect_pause(self):
        stop = self.root / "stop"
        stop.touch()
        d.CONTROL = d.DownloadControl([self.root], stop_file=stop)
        with self.assertRaises(d.DownloadPaused):
            d.atomic_write_bytes(self.root / "new.bin", b"data")
        self.assertFalse((self.root / "new.bin").exists())

    def test_second_run_cannot_acquire_output_lock(self):
        with d.output_lock(self.root):
            with self.assertRaises((RuntimeError, OSError)):
                with d.output_lock(self.root):
                    self.fail("duplicate lock acquired")
        with d.output_lock(self.root):
            pass

    def test_batch_pause_reports_exit_code_and_all_pending_holes(self):
        stop = self.root / "stop"
        stop.touch()
        progress = self.root / "progress.json"
        argv = ["download.py", "A", "B", "C", "D", "E", "F", "--out", str(self.root),
                "--workers", "5", "--stop-file", str(stop), "--progress-file", str(progress)]
        with patch.object(sys, "argv", argv), patch.object(d.HoleDownloader, "run") as run:
            self.assertEqual(d.main(), 2)
        run.assert_not_called()
        summary = json.loads(progress.read_text(encoding="utf-8"))
        self.assertEqual((summary["status"], summary["paused"], summary["failed"]), ("paused", 6, 0))
        self.assertFalse((self.root / "raw").exists())


if __name__ == "__main__":
    unittest.main()
