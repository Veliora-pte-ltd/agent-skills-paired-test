"""End-to-end runs of the reusable runner against a fake `claude` (tests/fake_claude.py):
no model is called and nothing is spent."""
import gzip
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from helpers import ROOT, fake_claude
from pairedtest.report import load as load_runs, summarise
from pairedtest.runner import Config, Runner, child_env, claude_cmd, make_plan
from pairedtest.suite import load

SUITE = load(ROOT / "template" / "suite")
FAKE_KEY = "test-key-not-real-0123456789"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pairedtest-test-"))
        self._env = dict(os.environ)
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cfg(self, mode="", **kw):
        kw.setdefault("budget", 1.0)
        kw.setdefault("cap", 0.05)
        return Config(out=self.tmp / "out", claude=fake_claude(self.tmp, mode), scratch=self.tmp / "scratch", **kw)

    def quiet(self, runner, plan):
        return runner.run(plan, log=lambda *_: None)


class TestPlan(unittest.TestCase):
    def test_plan_is_balanced_and_deterministic(self):
        p = make_plan(["a", "b", "c"], ["none", "compact"], ["m1", "m2"], 3, seed=1)
        self.assertEqual(p, make_plan(["a", "b", "c"], ["none", "compact"], ["m1", "m2"], 3, seed=1))
        self.assertEqual(len(p), 36)
        block = p[:12]  # the first repeat is complete before the second starts
        self.assertEqual({x[3] for x in block}, {0})
        self.assertEqual(Counter(x[1] for x in block), {"none": 6, "compact": 6})

    def test_command_flags(self):
        cfg = Config(out=Path("/tmp/x"))
        cmd = claude_cmd(cfg, "do it", "claude-sonnet-5-5", 1.0)
        for flag in ("--setting-sources", "--disallowedTools", "--max-budget-usd", "--no-session-persistence"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "project")
        self.assertNotIn("--max-budget-usd", claude_cmd(cfg, "x", "m", 0))


class TestRunner(Base):
    def test_skill_condition_passes_and_baseline_fails(self):
        r = Runner(SUITE, self.cfg())
        res = self.quiet(r, make_plan(list(SUITE.TASKS), ["none", "compact"], ["claude-sonnet-5-5"], 2))
        self.assertEqual((res["ran"], res["stopped"]), (8, None))
        runs = load_runs(self.tmp / "out" / "runs.jsonl")
        by = Counter((x["condition"], x["passed"]) for x in runs)
        self.assertEqual(by, {("compact", True): 4, ("none", False): 4})
        failed = Counter(c["name"] for x in runs if x["condition"] == "none" for c in x["checks"] if not c["ok"])
        self.assertEqual(failed, {"status_proposed": 4, "index_row": 4})
        self.assertTrue(all(x["skill_calls"] == ["adr"] for x in runs if x["condition"] == "compact"))
        s = summarise(runs)["models"]["claude-sonnet-5-5"]
        self.assertEqual(s["paired"]["compact"]["all"]["diff"], 1.0)
        # list price: 5 input, 100 cache write, 900 cache read, 200 output tokens on Sonnet 5.5
        self.assertAlmostEqual(runs[0]["cost_usd"], (5 * 2 + 100 * 2.5 + 900 * 0.1 + (200 if runs[0]["condition"] == "compact" else 300) * 10) / 1e6)
        ledger = [json.loads(l) for l in (self.tmp / "out" / "spend.jsonl").read_text().splitlines()]
        self.assertEqual(len(ledger), 8)
        # the account-like field in the fake init event is scrubbed from the saved transcript
        t = gzip.open(next((self.tmp / "out" / "transcripts").glob("*.gz")), "rt").read()
        self.assertNotIn("someone@example.org", t)
        self.assertEqual(len(list((self.tmp / "scratch" / "runs").glob("*"))), 0)  # run copies deleted

    def test_resume_skips_scored_runs(self):
        plan = make_plan(list(SUITE.TASKS), ["none"], ["claude-sonnet-5-5"], 1)
        r = Runner(SUITE, self.cfg())
        self.quiet(r, plan)
        res = self.quiet(Runner(SUITE, self.cfg()), plan)
        self.assertEqual(res["ran"], 0)

    def test_budget_stop(self):
        # the ledger total plus this run's cap would pass the budget, so nothing runs
        res = self.quiet(Runner(SUITE, self.cfg(budget=0.04, cap=0.05)), make_plan(list(SUITE.TASKS), ["none"], ["m"], 1))
        self.assertEqual((res["ran"], res["stopped"]), (0, "budget"))
        self.assertFalse((self.tmp / "out" / "runs.jsonl").exists())

    def test_api_key_never_saved(self):
        self.quiet(Runner(SUITE, self.cfg("leak")), make_plan(["adr-queue"], ["none"], ["claude-sonnet-5-5"], 1))
        out = self.tmp / "out"
        blob = (out / "runs.jsonl").read_text() + "".join(gzip.open(f, "rt").read() for f in (out / "transcripts").glob("*.gz"))
        self.assertNotIn(FAKE_KEY, blob)
        self.assertIn("[REDACTED]", blob)

    def test_subscription_mode_has_no_key_and_stops_at_limit(self):
        conf = self.tmp / "claude-config"; conf.mkdir()
        cfg = self.cfg(auth="subscription", config_dir=conf, cap=0)
        env = child_env(cfg, self.tmp / "envcheck", SUITE)
        self.assertFalse(any(k in env for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")))
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(conf))
        res = self.quiet(Runner(SUITE, cfg), make_plan(["adr-queue"], ["none", "compact"], ["m"], 1))
        runs = load_runs(self.tmp / "out" / "runs.jsonl")
        self.assertTrue(all(x["api_key_source"] == "none" and x["cost_source"] == "cli_estimate" for x in runs))
        self.assertFalse((self.tmp / "out" / "spend.jsonl").exists())
        lim = self.cfg("limit", auth="subscription", config_dir=conf, cap=0)
        lim.out = self.tmp / "out-limit"
        res = self.quiet(Runner(SUITE, lim), make_plan(["adr-queue", "adr-postgres"], ["none"], ["m"], 1))
        self.assertEqual((res["ran"], res["stopped"]), (0, "limit"))
        self.assertEqual(len(load_runs(lim.out / "runs.jsonl")), 1)

    def test_api_mode_requires_a_cap(self):
        with self.assertRaises(SystemExit):
            Runner(SUITE, self.cfg(cap=0))


if __name__ == "__main__":
    unittest.main()
