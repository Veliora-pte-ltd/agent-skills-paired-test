"""Guard for the published data: no credentials, personal addresses or machine paths in any file,
including the gzipped transcripts."""
import gzip
import re
import unittest

from helpers import ROOT

SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}|"
                    r"xox[abp]-[A-Za-z0-9-]{10,}|(?i:authorization:\s*bearer\s+[A-Za-z0-9._-]{12,})|(?i:x-api-key:\s*[A-Za-z0-9._-]{12,})")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"@(?:[a-z0-9-]+\.)*(?:example|example\.com|example\.org|tillroll\.example|x\.com)$|^noreply@anthropic\.com$|^contact@veliora\.works$")
HOME_PATH = re.compile(r"(?<![\w.-])(?:/home/[a-z]|/Users/[A-Za-z]|/root/|/workspace/|[A-Z]:\\\\Users\\\\)")
GIT_AUTODETECT = re.compile(r"[\w.-]+@[\w.-]+\.\(none\)")  # git's "unable to auto-detect email address (got 'user@host.(none)')"
SKIP = {".git"}


def files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not SKIP & set(p.relative_to(ROOT).parts) and "__pycache__" not in p.parts:
            yield p


def text(p):
    if p.suffix == ".gz":
        return gzip.open(p, "rt", errors="replace").read()
    if p.suffix in (".png", ".ttf", ".pyc"):
        return ""
    return p.read_text(errors="replace")


class TestPublishedFiles(unittest.TestCase):
    def test_no_secrets_personal_emails_or_machine_paths(self):
        bad = []
        n = 0
        for p in files():
            t = text(p)
            n += 1
            rel = p.relative_to(ROOT)
            if rel.parts[0] == "tests" and p.name == "test_published_files.py":
                continue
            bad += [f"{rel}: secret-like {m.group(0)[:12]}…" for m in SECRET.finditer(t)]
            bad += [f"{rel}: email {e}" for e in set(EMAIL.findall(t)) if not ALLOWED_EMAIL.search(e)]
            bad += [f"{rel}: machine identity {m}" for m in set(GIT_AUTODETECT.findall(t)) if m != "user@host.(none)"]
            bad += [f"{rel}: machine path {m.group(0)}" for m in HOME_PATH.finditer(t)][:3]
        self.assertGreater(n, 1000)
        self.assertEqual(bad, [], "\n".join(bad[:40]))


if __name__ == "__main__":
    unittest.main()
