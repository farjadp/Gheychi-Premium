"""
Regression tests: the backup fired on every container start, not every 24 h.

Five deploys on the night of 2026-09-06 produced five archives in the channel
within 90 minutes, because run_backup_loop() called run_backup_once() before
its first sleep and a deploy restarts the process.
"""
import os
import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BackupScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import backup
        self.backup = backup
        self._orig_dir = backup.DATA_DIR
        backup.DATA_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.backup.DATA_DIR = self._orig_dir
        self.tmp.cleanup()

    def _write_state(self, moment):
        (Path(self.tmp.name) / self.backup.STATE_FILE).write_text(
            json.dumps({"last_backup_at": moment.isoformat()}), encoding="utf-8")

    def test_with_no_history_a_backup_is_due_immediately(self):
        self.assertEqual(self.backup.seconds_until_due(), 0.0)

    def test_a_restart_minutes_after_a_backup_does_not_trigger_another(self):
        """The exact failure: deploy, restart, second archive four minutes later."""
        now = datetime.now(timezone.utc)
        self._write_state(now - timedelta(minutes=4))
        wait = self.backup.seconds_until_due(now)
        self.assertGreater(wait, 0)
        self.assertAlmostEqual(wait, 24 * 3600 - 240, delta=2)

    def test_a_backup_becomes_due_again_after_the_interval(self):
        now = datetime.now(timezone.utc)
        self._write_state(now - timedelta(hours=24, minutes=1))
        self.assertEqual(self.backup.seconds_until_due(now), 0.0)

    def test_a_long_outage_still_backs_up_on_return(self):
        now = datetime.now(timezone.utc)
        self._write_state(now - timedelta(days=9))
        self.assertEqual(self.backup.seconds_until_due(now), 0.0)

    def test_a_corrupt_or_missing_state_file_falls_back_to_backing_up(self):
        # Better an extra archive than a silent gap.
        (Path(self.tmp.name) / self.backup.STATE_FILE).write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.backup.last_backup_at())
        self.assertEqual(self.backup.seconds_until_due(), 0.0)

    def test_the_state_file_is_kept_out_of_the_archive(self):
        import zipfile
        self._write_state(datetime.now(timezone.utc))
        (Path(self.tmp.name) / "plans.json").write_text("{}", encoding="utf-8")
        with tempfile.TemporaryDirectory() as out:
            archive = self.backup.build_backup_archive(out)
            names = zipfile.ZipFile(archive).namelist()
        # Restoring an archive must not resurrect a stale timestamp and cause
        # the next backup to be skipped.
        self.assertIn("plans.json", names)
        self.assertNotIn(self.backup.STATE_FILE, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
