import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import install
from codex_client import CodexClient


class CodexRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "config.toml"
        for override in [patch.object(install, "CODEX", self.root),
                         patch.object(install, "CODEX_CONFIG", self.config),
                         patch.dict(os.environ, {"CODEX_HOME": str(self.root)})]:
            override.start()
            self.addCleanup(override.stop)

    def test_fallback_round_trip_preserves_other_settings_and_formatting(self):
        before = ('# User settings\nproject_doc_fallback_filenames = ["TEAM.md"]\n'
                  '[features]\nhooks = true\n[projects."/tmp/acme"]\ntrust_level = "trusted"\n')
        self.config.write_text(before)
        record = install.codex_fallback(True, False, {})
        self.assertEqual(tomllib.loads(self.config.read_text())["project_doc_fallback_filenames"],
                         ["TEAM.md", "CLAUDE.md"])
        modified = self.config.stat().st_mtime_ns
        self.assertEqual(install.codex_fallback(True, False, record), record)
        self.assertEqual(self.config.stat().st_mtime_ns, modified)
        install.codex_fallback(False, False, record)
        self.assertEqual(self.config.read_text(), before)

    def test_uninstall_removes_only_the_installed_fallback(self):
        self.config.write_text('# User settings\n')
        record = install.codex_fallback(True, False, {})
        with CodexClient(self.root) as client:
            client.request("config/value/write", {
                "keyPath": "project_doc_fallback_filenames", "value": ["CLAUDE.md", "TEAM.md"],
                "mergeStrategy": "replace",
            })
        install.codex_fallback(False, False, record)
        self.assertEqual(tomllib.loads(self.config.read_text())["project_doc_fallback_filenames"], ["TEAM.md"])

    def test_codex_rejects_a_write_over_concurrent_config_changes(self):
        self.config.write_text('# Original settings\n')
        with CodexClient(self.root) as client:
            layers = client.request("config/read", {"includeLayers": True})["layers"]
            user = next(layer for layer in layers if layer["name"]["type"] == "user")
            changed = '# Changed by the user\nmodel = "example"\n'
            self.config.write_text(changed)
            with self.assertRaises(RuntimeError):
                client.request("config/value/write", {
                    "keyPath": "project_doc_fallback_filenames", "value": ["CLAUDE.md"],
                    "mergeStrategy": "replace", "expectedVersion": user["version"],
                })
            self.assertEqual(self.config.read_text(), changed)


if __name__ == "__main__":
    unittest.main()
