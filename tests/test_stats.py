"""The reusable statistics reproduce the published summaries exactly (no model calls)."""
import json
import unittest

from helpers import ROOT
from pairedtest.report import load, summarise
from pairedtest.stats import paired_diff, wilson

RES = ROOT / "results"
S = json.loads((RES / "summary.json").read_text())
SUB = json.loads((RES / "subscription-summary.json").read_text())
MAIN = [r for r in load(RES / "main.jsonl") if "passed" in r]


class TestStats(unittest.TestCase):
    def test_wilson_known_values(self):
        lo, hi = wilson(6, 24)
        self.assertEqual((round(lo * 100), round(hi * 100)), (12, 45))
        self.assertEqual(wilson(24, 24)[1], 1.0)

    def test_paired_diffs_match_summary_json(self):
        n = 0
        for model, m in S["models"].items():
            mr = [r for r in MAIN if r["model"] == model]
            for cond, p in m["paired"].items():
                for key, metric, fam in (("all", "passed", None), ("migration", "passed", "migration"),
                                         ("release", "passed", "release"), ("cost_all", "cost_usd", None)):
                    rs = [r for r in mr if fam is None or r["family"] == fam]
                    got = paired_diff(rs, cond, metric)
                    want = p[key]
                    if not want:
                        self.assertEqual(got, {})
                        continue
                    self.assertAlmostEqual(got["diff"], want["diff"], places=12)
                    self.assertAlmostEqual(got["ci"][0], want["ci"][0], places=12)
                    self.assertAlmostEqual(got["ci"][1], want["ci"][1], places=12)
                    self.assertAlmostEqual(got["p_perm"], want["p_perm"], places=12)
                    n += 1
        self.assertGreater(n, 20)

    def test_subscription_paired_diff(self):
        rs = [r for r in load(RES / "subscription-rerun.jsonl") if "passed" in r]
        got = paired_diff(rs, "compact")
        want = SUB["subscription"]["claude-opus-5-5"]["paired_compact"]
        self.assertAlmostEqual(got["diff"], want["diff"], places=12)
        self.assertEqual(list(got["ci"]), list(want["ci"]))
        self.assertEqual(got["tasks_better"], 5)

    def test_report_cells_match_summary_json(self):
        s = summarise(MAIN)
        for model, m in S["models"].items():
            for cond, c in m["conditions"].items():
                got = s["models"][model]["conditions"][cond]
                self.assertEqual((got["passed"], got["n"]), (c["passed"], c["n"]), (model, cond))
                self.assertAlmostEqual(got["cost_mean"], c["cost_mean"], places=12)


if __name__ == "__main__":
    unittest.main()
