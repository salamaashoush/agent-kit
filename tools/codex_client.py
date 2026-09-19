import json
import queue
import subprocess
import threading
import time


class CodexClient:
    def __init__(self, cwd, timeout=15):
        self.cwd = cwd
        self.timeout = timeout
        self.messages = queue.Queue()
        self.sequence = 0

    def __enter__(self):
        self.process = subprocess.Popen(
            ["codex", "app-server", "--stdio"], cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
        )
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        try:
            self.request("initialize", {"clientInfo": {"name": "agent-kit", "version": "1"}})
            self.send({"method": "initialized"})
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except (ValueError, OSError) as error:
            self.messages.put(error)
        finally:
            self.messages.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.sequence += 1
        self.send({"id": self.sequence, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Codex {method} timed out")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError(f"Codex {method} timed out") from error
            if message is None or isinstance(message, Exception):
                raise RuntimeError(f"Codex stopped while handling {method}")
            if message.get("id") != self.sequence:
                continue
            if "error" in message:
                raise RuntimeError(f"Codex {method}: {message['error']['message']}")
            return message["result"]

    def __exit__(self, *_):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.reader.join(timeout=2)
        self.process.stdout.close()
