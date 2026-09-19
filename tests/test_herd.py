import argparse
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("herd", Path(__file__).resolve().parents[1] / "tools/herd.py")
herd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(herd)


class CodexLaunchTests(unittest.TestCase):
    def launch(self, yolo=False, agent="codex"):
        args = argparse.Namespace(name="browser", agent=agent, yolo=yolo,
                                  worktree=False, brief=None, repo=None,
                                  cwd="/tmp", branch=None, model=None)
        with patch.object(herd, "inside"), patch.object(herd, "sessions", return_value=[]), \
             patch.object(herd, "herdr", return_value={"root_pane": {"pane_id": "test"}}) as api:
            herd.start(args)
        return api.call_args_list[-1].args

    def test_codex_yolo_passes_explicit_bypass(self):
        self.assertEqual(self.launch(True)[-2:], ("--", "--dangerously-bypass-approvals-and-sandbox"))

    def test_default_codex_keeps_workspace_sandbox(self):
        self.assertEqual(self.launch()[-4:], ("--ask-for-approval", "never", "--sandbox", "workspace-write"))

    def test_claude_yolo_preserves_remote_control(self):
        self.assertEqual(self.launch(True, "claude")[-4:],
                         ("--", "--remote-control", "browser", "--dangerously-skip-permissions"))

    def test_default_claude_does_not_bypass_permissions(self):
        self.assertEqual(self.launch(False, "claude")[-3:], ("--", "--remote-control", "browser"))

    def test_antigravity_yolo_does_not_duplicate_its_default(self):
        self.assertEqual(self.launch(True, "antigravity")[-2:], ("--", "--dangerously-skip-permissions"))
