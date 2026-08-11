from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ManagedProcess:
    name: str
    port: int
    process: subprocess.Popen[str]

    @property
    def pid(self) -> int:
        return self.process.pid

    def output(self) -> str:
        if self.process.stdout is None:
            return ""
        return self.process.stdout.read()

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def allocate_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_python_process(
    *,
    name: str,
    port: int,
    module: str,
    root: Path,
    environment: dict[str, str],
    arguments: tuple[str, ...] = (),
) -> ManagedProcess:
    process_environment = os.environ.copy()
    process_environment.update(environment)
    process = subprocess.Popen(
        [sys.executable, "-m", module, *arguments],
        cwd=root,
        env=process_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    managed = ManagedProcess(name=name, port=port, process=process)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited during startup: {managed.output()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return managed
        except OSError:
            time.sleep(0.05)
    managed.stop()
    raise RuntimeError(f"{name} did not bind port {port}: {managed.output()}")


class ProcessGroup(ExitStack):
    def add(self, process: ManagedProcess) -> ManagedProcess:
        self.callback(process.stop)
        return process
