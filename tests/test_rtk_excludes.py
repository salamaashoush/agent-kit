import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "rtk_excludes", Path(__file__).resolve().parents[1] / "tools/rtk-excludes.py")
rtk_excludes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rtk_excludes)

PATTERNS = rtk_excludes.PATTERNS


def excludes(text):
    return tomllib.loads(text).get("hooks", {}).get("exclude_commands")


class WithExcludesTests(unittest.TestCase):
    def test_an_empty_config_gets_a_hooks_table(self):
        self.assertEqual(excludes(rtk_excludes.with_excludes("", PATTERNS)), PATTERNS)

    def test_other_tables_keep_their_bytes(self):
        original = '[tracking]\nenabled = true\nhistory_days = 90\n\n[tee]\nmode = "failures"\n'
        updated = rtk_excludes.with_excludes(original, PATTERNS)
        self.assertTrue(updated.startswith(original))
        self.assertEqual(excludes(updated), PATTERNS)

    def test_a_hooks_table_without_the_key_gains_it(self):
        original = '[hooks]\nsuppress_hook_warning = true\n\n[display]\ncolors = true\n'
        updated = rtk_excludes.with_excludes(original, PATTERNS)
        self.assertEqual(excludes(updated), PATTERNS)
        self.assertTrue(tomllib.loads(updated)["hooks"]["suppress_hook_warning"])
        self.assertTrue(tomllib.loads(updated)["display"]["colors"])

    def test_a_multiline_array_with_comments_and_brackets_is_replaced_whole(self):
        original = ('[hooks]\nexclude_commands = [\n  "curl",  # network\n'
                    '  "^make\\\\s[a-z]+",\n]\nsuppress_hook_warning = false\n')
        wanted = ["curl", r"^make\s[a-z]+"] + PATTERNS
        updated = rtk_excludes.with_excludes(original, wanted)
        self.assertEqual(excludes(updated), wanted)
        self.assertFalse(tomllib.loads(updated)["hooks"]["suppress_hook_warning"])


class MainTests(unittest.TestCase):
    def run_action(self, action, text=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rtk" / "config.toml"
            if text is not None:
                path.parent.mkdir()
                path.write_text(text)
            with patch.object(rtk_excludes, "config_path", return_value=path), \
                 patch.object(rtk_excludes.sys, "argv", ["rtk-excludes.py", action]):
                self.assertEqual(rtk_excludes.main(), 0)
            return path.read_text() if path.exists() else None

    def test_add_is_idempotent_and_keeps_user_patterns(self):
        once = self.run_action("add", '[hooks]\nexclude_commands = ["curl"]\n')
        self.assertEqual(excludes(once), ["curl"] + PATTERNS)
        self.assertEqual(self.run_action("add", once), once)

    def test_remove_takes_back_only_its_own_patterns(self):
        text = self.run_action("add", '[hooks]\nexclude_commands = ["curl"]\n')
        self.assertEqual(excludes(self.run_action("remove", text)), ["curl"])

    def test_remove_without_rtk_is_a_no_op(self):
        with patch.object(rtk_excludes, "config_path", return_value=None), \
             patch.object(rtk_excludes.sys, "argv", ["rtk-excludes.py", "remove"]):
            self.assertEqual(rtk_excludes.main(), 0)


class PatternTests(unittest.TestCase):
    """The patterns rtk compiles, matched the way rtk anchors a leading ^."""

    def matches(self, command):
        import re
        return any(re.match(pattern, command) for pattern in PATTERNS)

    def test_the_rewrites_that_change_meaning_are_excluded(self):
        for command in ("grep -h foo a b", "grep -rh foo .", "grep -n -h foo a b",
                        "ls -l", "ls -la /tmp", "ls --color=never -al"):
            self.assertTrue(self.matches(command), command)

    def test_ordinary_commands_still_go_through_rtk(self):
        for command in ("grep -n foo a", "grep -rn foo .", "grep --with-filename foo a",
                        "ls", "ls -a", "ls -1 /tmp", "ls --color=always",
                        "git log -h", "lsblk -l"):
            self.assertFalse(self.matches(command), command)


if __name__ == "__main__":
    unittest.main()
