"""Stream parsing, stop classification and scrubbing, on synthetic Claude Code events."""
import json
import unittest

import helpers  # noqa: F401
from pairedtest.stream import classify, parse_stream, scrub

J = lambda *evs: [json.dumps(e) for e in evs]
INIT = {"type": "system", "subtype": "init", "apiKeySource": "none", "skills": ["release"], "claude_code_version": "x"}


class TestStream(unittest.TestCase):
    def test_cost_from_model_usage_at_list_price(self):
        lines = J(INIT,
                  {"type": "assistant", "message": {"id": "a", "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "release"}}],
                                                    "usage": {"input_tokens": 1, "cache_read_input_tokens": 10}}},
                  {"type": "result", "num_turns": 2, "total_cost_usd": 9.9,
                   "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 1_000_000, "outputTokens": 100_000}}})
        info = parse_stream(lines)
        self.assertAlmostEqual(info["cost_usd"], 2.00 + 1.00)
        self.assertEqual(info["cost_source"], "list_price")
        self.assertEqual(info["skill_calls"], ["release"])
        self.assertEqual(info["api_calls"], 1)

    def test_unknown_model_falls_back_to_cli_estimate(self):
        info = parse_stream(J({"type": "result", "modelUsage": {"some-new-model": {"inputTokens": 5, "costUSD": 0.25}}}))
        self.assertEqual((info["cost_usd"], info["cost_source"]), (0.25, "cli_estimate"))

    def test_reading_skill_md_counts_as_a_load(self):
        lines = J({"type": "assistant", "message": {"id": "a", "content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": ".claude/skills/release/SKILL.md"}}]}})
        self.assertTrue(parse_stream(lines)["skill_calls"][0].startswith("read:"))

    def test_classify(self):
        ok = J(INIT, {"type": "result", "is_error": False, "result": "done"})
        self.assertIsNone(classify(ok, "", 0))
        lim = J(INIT, {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}, {"type": "result", "is_error": True})
        self.assertEqual(classify(lim, "", 1), "limit")
        key = J(dict(INIT, apiKeySource="ANTHROPIC_API_KEY"), {"type": "result", "is_error": False})
        self.assertEqual(classify(key, "", 0, auth="subscription"), "auth")
        self.assertIsNone(classify(key, "", 0, auth="api"))
        self.assertEqual(classify(J({"type": "result", "api_error_status": 401}), "", 1), "auth")
        self.assertIsNone(classify(J({"type": "result", "subtype": "error_max_budget_usd", "is_error": True}), "", 1))
        self.assertEqual(classify([], "boom", 1), "api_error")

    def test_scrub_removes_account_fields(self):
        s = scrub({"a": 1, "account": {"email": "x@y"}, "list": [{"orgId": "o", "ok": 2}],
                   "hasChargeableSavedPaymentMethod": True})
        self.assertEqual(s, {"a": 1, "account": "[removed]", "list": [{"orgId": "[removed]", "ok": 2}],
                             "hasChargeableSavedPaymentMethod": "[removed]"})


if __name__ == "__main__":
    unittest.main()
