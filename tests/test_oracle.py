"""Every checker can pass (reference solution) and fails on an untouched repository."""
import contextlib
import io
import unittest

from helpers import ROOT
from pairedtest.__main__ import oracle
from pairedtest.suite import load


class TestOracle(unittest.TestCase):
    def check(self, path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = oracle(load(path))
        self.assertEqual(rc, 0, buf.getvalue())

    def test_template_suite(self):
        self.check(ROOT / "template" / "suite")

    def test_published_tillroll_suite(self):
        self.check(ROOT / "skill_ab")


if __name__ == "__main__":
    unittest.main()
