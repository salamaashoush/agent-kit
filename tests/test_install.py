import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("installer", ROOT / "tools/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_codex_gets_no_hook_from_a_tool_whose_requirement_fails(self):
        registry = {"acme": {"codex_requires": "exit 2", "hooks": [
            {"event": "PreToolUse", "matcher": "Bash", "command": "acme hook"}]}}
        with patch.object(installer, "registry", return_value=registry):
            steps = installer.codex_plan()
        self.assertEqual(steps["hooks"], [])
        self.assertEqual(steps["refused"], [("acme", "`exit 2` failed")])

    def test_setup_runs_the_tool_installer_and_tears_down_a_dropped_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wanted = {"acme": {"run": [f"touch {root}/acme"], "undo": [f"rm {root}/acme"]}}
            previous = {"gone": [f"touch {root}/gone-undone"]}
            record, ok = installer.run_setup(wanted, previous, False)
            self.assertTrue(ok)
            self.assertTrue((root / "acme").exists())
            self.assertTrue((root / "gone-undone").exists())
            self.assertEqual(record, {"acme": [f"rm {root}/acme"]})

    def test_dry_run_setup_runs_nothing_and_a_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ran"
            _, ok = installer.run_setup({"acme": {"run": [f"touch {marker}"], "undo": []}}, {}, True)
            self.assertTrue(ok)
            self.assertFalse(marker.exists())
            _, ok = installer.run_setup({"acme": {"run": ["exit 3"], "undo": []}}, {}, False)
            self.assertFalse(ok)

    def test_a_tool_dropped_from_the_registry_is_unwired(self):
        kept = {"type": "command", "command": "acme-guard"}
        settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "bash /home/sashoush/.claude/skills/gone/check.sh"}, kept]}],
            "Stop": [{"hooks": [{"type": "command", "command": "python3 acme-stop"}]}]}}
        previous = [{"event": "PreToolUse", "matcher": "Bash", "had": False, "was": None, "index": None,
                     "command": "bash /home/sashoush/.claude/skills/gone/check.sh"},
                    {"event": "Stop", "matcher": None, "had": False, "was": None, "index": None,
                     "command": "python3 acme-stop"}]
        planned = [{"event": "Stop", "matcher": None, "command": "python3 acme-stop"}]
        installer.unwire_hooks(settings, installer.retired(previous, planned))
        self.assertEqual(settings["hooks"]["PreToolUse"], [{"matcher": "Bash", "hooks": [kept]}])
        self.assertEqual(settings["hooks"]["Stop"][0]["hooks"][0]["command"], "python3 acme-stop")

    def test_retiring_the_last_hook_of_an_event_drops_the_event(self):
        settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "acme-guard"}]}]}}
        previous = [{"event": "PreToolUse", "matcher": "Bash", "command": "acme-guard",
                     "had": False, "was": None, "index": None}]
        installer.unwire_hooks(settings, installer.retired(previous, []))
        self.assertEqual(settings, {})

    def test_existing_settings_keep_their_bytes_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            original = '{ "label": "caf\u00e9" }'
            path.write_text(original)
            before = path.stat().st_mtime_ns
            with patch.object(installer, "SETTINGS", path):
                self.assertFalse(installer.write_settings(json.loads(original), False))
            self.assertEqual(path.read_text(), original)
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_custom_mcp_configuration_is_preserved(self):
        config = {"mcp_servers": {"acme": {"command": "custom", "env": {"API_TOKEN": "fixture"}}}}
        with patch.object(installer, "codex_run") as command:
            record, changes = installer.merge_codex_mcp(config, {"acme": {"command": "acme"}}, False)
        command.assert_not_called()
        self.assertEqual(changes, [])
        self.assertTrue(record[0]["had"])
        self.assertEqual(config["mcp_servers"]["acme"]["env"]["API_TOKEN"], "fixture")

    def test_real_file_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AGENTS.md"
            path.write_text("user instructions")
            self.assertEqual(installer.link(ROOT / "CLAUDE.md", path, False), "keep")
            self.assertEqual(path.read_text(), "user instructions")

    def test_doctor_does_not_treat_an_untrusted_hook_as_active(self):
        client = unittest.mock.MagicMock()
        client.request.side_effect = [
            {"data": [{"hooks": [{"command": "acme", "eventName": "stop", "matcher": None,
                                   "enabled": True, "trustStatus": "untrusted"}], "errors": []}]},
            {"data": [{"skills": [], "errors": []}]},
        ]
        verdicts = []
        steps = {"hooks": [{"command": "acme", "event": "Stop", "matcher": None, "tool": "acme"}],
                 "links": []}
        with patch.object(installer, "CodexClient") as factory:
            factory.return_value.__enter__.return_value = client
            installer.codex_runtime_checks(steps, lambda *args: verdicts.append(args))
        self.assertEqual(verdicts[0], ("active hook acme", False, "untrusted"))

    def test_tool_notes_are_readable_without_import_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("Run acme doctor before using acme.\n")
            with patch.object(installer, "REPO", root), patch.object(installer, "TOOLS_LOCAL", root / "tools.local.md"):
                installer.write_tools_local(["note.md"], False)
                self.assertIn("Run acme doctor", (root / "tools.local.md").read_text())
                self.assertFalse(installer.write_tools_local(["note.md"], False))

    def test_foreign_symlink_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            original.write_text("user work")
            link = root / "skill"
            link.symlink_to(original)
            self.assertEqual(installer.link(ROOT / "CLAUDE.md", link, False), "keep")
            self.assertEqual(link.resolve(), original)


if __name__ == "__main__":
    unittest.main()
