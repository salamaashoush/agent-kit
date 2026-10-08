import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "mylint", Path(__file__).resolve().parents[1] / "tools/mylint.py")
mylint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mylint)


# Fixtures are assembled from pieces so this file never trips the scan it tests.
PUBLIC_IP = ".".join(["93", "184", "216", "34"])
REAL_EMAIL = "jane.doe" + "@" + "fastmail.com"


def finding(line, patterns=(), allow=()):
    return mylint.line_findings(line, list(patterns), tuple(allow))


class DetectorTests(unittest.TestCase):
    def test_secrets_are_caught(self):
        for line, why in [
            ("-----BEGIN OPENSSH " + "PRIVATE KEY-----", "private key"),
            ("aws_key = " + "AKIA" + "ABCDEFGHIJKLMNOP", "AWS access key"),
            ("GH_TOKEN=ghp_" + "a" * 36, "GitHub token"),
            ("ANTHROPIC_API_KEY=sk-ant-api03-" + "b" * 30, "Anthropic key"),
            ("slack: " + "xoxb" + "-1234567890-abcdefghij", "Slack token"),
            ("password = " + '"hunter2' + 'hunter2"', "credential"),
            ('"api_key": ' + '"q8f2kd93' + 'jd83kd92"', "credential"),
        ]:
            self.assertTrue((finding(line) or "").startswith(why), line)

    def test_placeholders_and_references_are_not_secrets(self):
        for line in ('password = "changeme123"', 'api_key = "${API_KEY}"',
                     'token: "<your token here>"', 'secret = "your-secret-here"',
                     "GITHUB_TOKEN=$(gh auth token)", "sk-ant- is the prefix"):
            self.assertIsNone(finding(line), line)

    def test_public_addresses_are_caught_and_documentation_ones_are_not(self):
        self.assertEqual(finding("router WAN: " + PUBLIC_IP), "public IP address: " + PUBLIC_IP)
        for line in ("router WAN: 203.0.113.10", "LAN 192.168.1.50", "pool 172.17.0.0/16",
                     "dns 1.1.1.1 and 8.8.8.8", "SSDP 239.255.255.250:1900",
                     "listen 0.0.0.0:8080", "v1.2.3.4 released", "version 2026.10.3.1"):
            self.assertIsNone(finding(line), line)

    def test_real_addresses_are_caught_and_placeholder_ones_are_not(self):
        self.assertEqual(finding("mail me at " + REAL_EMAIL), "email address: " + REAL_EMAIL)
        for line in ("developer@example.com", "git@github.com:acme/repo.git",
                     "noreply@anthropic.com", "123+bot@users.noreply.github.com",
                     "see @tools.local.md", "npm i @anthropic-ai/claude-code@2.1.0"):
            self.assertIsNone(finding(line), line)

    def test_the_names_list_and_its_allow_list_still_apply(self):
        patterns = [(r"\bacme\.com\b", "company URL")]
        self.assertEqual(finding("see https://acme.com/x", patterns), "company URL: acme.com")
        self.assertIsNone(finding("see https://acme.com/docs/public", patterns, ["acme.com/docs/public"]))


class HistoryTests(unittest.TestCase):
    def test_a_leak_removed_from_the_tree_is_still_found_in_history(self):
        with tempfile.TemporaryDirectory() as directory:
            git = ["git", "-C", directory, "-c", "user.name=Salama Ashoush",
                   "-c", "user.email=salama@example.com"]
            subprocess.run(["git", "init", "-q", directory], check=True)
            note = Path(directory) / "note.md"
            note.write_text(f"WAN {PUBLIC_IP}\n")
            subprocess.run(git + ["add", "."], check=True)
            subprocess.run(git + ["commit", "-qm", "docs: add note"], check=True)
            note.write_text("WAN 203.0.113.10\n")
            subprocess.run(git + ["commit", "-qam", "docs: scrub note"], check=True)
            self.assertEqual(list(mylint.check_private(directory, [], ())), [])
            history = list(mylint.check_history(directory, [], ()))
            self.assertEqual([why for _, _, why, _ in history], ["public IP address: " + PUBLIC_IP])


if __name__ == "__main__":
    unittest.main()
