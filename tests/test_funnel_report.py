import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "ledom-growth" / "scripts" / "funnel_report.py"
spec = importlib.util.spec_from_file_location("funnel_report", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEADER = "lead_id created_at source medium is_test qualification deal_status".split()


class FunnelReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "snapshot.csv"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows):
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(rows)

    def run_report(self):
        return module.report(self.path, "2026-10-01", "2026-11-01")

    def test_cohort_boundaries_tests_pending_and_reconciliation(self):
        self.write([
            ["a", "2026-09-30T21:00:00Z", "yandex", "organic", "false", "qualified", "won"],
            ["b", "2026-10-10T10:00:00+03:00", "google", "organic", "false", "pending", "open"],
            ["c", "2026-10-12T10:00:00+03:00", "yandex", "organic", "true", "qualified", "open"],
            ["d", "2026-10-31T21:00:00Z", "yandex", "organic", "false", "unqualified", "lost"],
            ["e", "2026-10-12T10:00:00+03:00", "unknown", "unknown", "0", "unknown", "unknown"],
        ])
        result = self.run_report()
        self.assertEqual(result["rows_read"], 5)
        self.assertEqual(result["test_rows_excluded"], 1)
        self.assertEqual(result["outside_cohort"], 1)
        self.assertEqual(result["totals"]["leads"], 3)
        self.assertEqual(result["totals"]["qualified"], 1)
        self.assertEqual(result["totals"]["qualification_pending"], 1)
        self.assertEqual(result["totals"]["qualification_unknown"], 1)
        self.assertEqual(result["totals"]["lost"], 0)
        self.assertEqual(sum(x["leads"] for x in result["by_source"]), 3)
        # CLI must produce parseable aggregates without lead identifiers.
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.path), "--start", "2026-10-01", "--end", "2026-11-01"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["totals"]["won"], 1)
        self.assertNotIn("lead_id", proc.stdout)

    def test_duplicate_snapshot_fails(self):
        row = ["duplicate", "2026-10-10T10:00:00Z", "yandex", "organic", "false", "pending", "open"]
        self.write([row, row])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.run_report()

    def test_ambiguous_timezone_fails(self):
        self.write([["a", "2026-10-10T10:00:00", "yandex", "organic", "false", "pending", "open"]])
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.run_report()

    def test_contradictory_sale_status_fails(self):
        self.write([["a", "2026-10-10T10:00:00Z", "yandex", "organic", "false", "unqualified", "won"]])
        with self.assertRaisesRegex(ValueError, "reconcile"):
            self.run_report()

    def test_empty_input_is_zero_not_conversion(self):
        self.write([])
        result = self.run_report()
        self.assertEqual(result["totals"]["leads"], 0)
        self.assertEqual(result["by_source"], [])
        self.assertNotIn("conversion_rate", result)

    def test_missing_columns_fail(self):
        self.path.write_text("lead_id,source\na,yandex\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "required"):
            self.run_report()


if __name__ == "__main__":
    unittest.main()
