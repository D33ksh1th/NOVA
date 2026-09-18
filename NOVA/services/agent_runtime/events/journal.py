"""POSIX append-only journal; operations run outside the event loop."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat

MAX_RECORD_BYTES = 1024 * 1024


class Journal:
    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        self.path = path
        self.failed = False
        self.closed = False
        if not readonly:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        flags = os.O_RDONLY if readonly else os.O_RDWR | os.O_CREAT | os.O_APPEND
        self.fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("audit path must be a regular file")
            fcntl.flock(self.fd, (fcntl.LOCK_SH if readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            self.identity = (info.st_dev, info.st_ino)
            self.size = info.st_size
            if not readonly:
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except BaseException:
            os.close(self.fd)
            self.closed = True
            raise

    def read_lines(self) -> list[bytes]:
        self._check()
        lines: list[bytes] = []
        with os.fdopen(os.dup(self.fd), "rb") as stream:
            stream.seek(0)
            while line := stream.readline(MAX_RECORD_BYTES + 1):
                if len(line) > MAX_RECORD_BYTES or not line.endswith(b"\n"):
                    raise ValueError(f"audit malformed record at index {len(lines)}")
                lines.append(line)
        return lines

    def _check(self) -> None:
        if self.closed or self.failed:
            raise RuntimeError("audit journal is closed or failed")
        info = self.path.lstat()
        if (info.st_dev, info.st_ino) != self.identity or info.st_size != self.size:
            self.failed = True
            raise ValueError("audit journal changed outside the writer")

    def write(self, record: bytes) -> None:
        self._check()
        if len(record) > MAX_RECORD_BYTES:
            raise ValueError("audit record exceeds size limit")
        try:
            remaining = memoryview(record)
            while remaining:
                written = os.write(self.fd, remaining)
                if written == 0:
                    raise OSError("audit write made no progress")
                remaining = remaining[written:]
            os.fsync(self.fd)
            self.size += len(record)
        except BaseException:
            self.failed = True
            raise

    def close(self) -> None:
        if not self.closed:
            os.close(self.fd)
            self.closed = True