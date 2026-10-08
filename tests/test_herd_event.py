import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "herd_event", Path(__file__).resolve().parents[1] / "tools/herd-event.py")
herd_event = importlib.util.module_from_spec(spec)
spec.loader.exec_module(herd_event)


class TrimTests(unittest.TestCase):
    def test_a_log_past_the_cap_keeps_its_newest_whole_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            lines = [f'{{"n": {n}, "pad": "{"x" * 100}"}}\n' for n in range(20000)]
            path.write_text("".join(lines))
            with patch.object(herd_event, "EVENTS", str(path)):
                herd_event.trim()
            kept = path.read_text()
            self.assertLessEqual(len(kept), herd_event.KEPT)
            self.assertTrue(kept.startswith('{"n": '))
            self.assertTrue(kept.endswith(lines[-1]))
            self.assertEqual(os.listdir(directory), ["events.jsonl"])

    def test_a_small_log_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text('{"n": 1}\n')
            with patch.object(herd_event, "EVENTS", str(path)):
                herd_event.trim()
            self.assertEqual(path.read_text(), '{"n": 1}\n')


if __name__ == "__main__":
    unittest.main()
