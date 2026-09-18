"""Bounded repository reads; the approved root is injected by trusted setup."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat

from services.agent_runtime.events.audit import _redact_str
from services.tools.base import Tool, ToolResult


MAX_BYTES = 65536
ALLOWED_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".json", ".md"})
BLOCKED_PARTS = frozenset({"node_modules", ".git", "dist", "build", "coverage", "vendor",
                           "data", "configs", "credentials", "secrets"})
SENSITIVE_NAME = re.compile(r"(?:secret|credential|password|token|private[_.-]?key|\.env)", re.I)
SENSITIVE_CONTENT = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[\"']?\s*[:=]\s*[\"'][^\"'\r\n]+",
    re.I,
)


class RepositoryReadTool(Tool):
    SUPPORTS_STRUCTURED_ARGS = True
    PROVIDES_CAPABILITIES = frozenset({"repo.read"})
    ARG_SCHEMA = {
        "type": "object", "additionalProperties": False, "required": ["path"],
        "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 240}},
    }

    def __init__(self, approved_root: Path) -> None:
        root = approved_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("REPOSITORY_ROOT_INVALID")
        self._root = root
        self._identity = (root.stat().st_dev, root.stat().st_ino)

    @property
    def name(self) -> str:
        return "repository_read"

    def can_handle(self, message: str) -> bool:
        return False

    def execute(self, message: str) -> dict:
        return {"success": False, "response": "Repository reads require a scoped agent task."}

    async def invoke(self, *, path: str) -> ToolResult:
        return await asyncio.to_thread(self._read, path)

    def _read(self, path: str) -> ToolResult:
        if not isinstance(path, str) or not 1 <= len(path) <= 240:
            return ToolResult(ok=False, error="REPOSITORY_PATH_DENIED")
        relative = PurePosixPath(path)
        parts = path.split("/")
        if (relative.is_absolute() or any(part in {"", ".", ".."} or part.startswith(".")
                                         or part.lower() in BLOCKED_PARTS for part in parts)
                or any(ord(character) < 32 for character in path) or "\\" in path
                or SENSITIVE_NAME.search(path) or relative.suffix.lower() not in ALLOWED_SUFFIXES):
            return ToolResult(ok=False, error="REPOSITORY_PATH_DENIED")
        descriptors = []
        try:
            directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(directory)
            root_info = os.fstat(directory)
            if (root_info.st_dev, root_info.st_ino) != self._identity:
                return ToolResult(ok=False, error="REPOSITORY_ROOT_CHANGED")
            for part in parts[:-1]:
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                descriptors.append(directory)
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            descriptors.append(descriptor)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
                return ToolResult(ok=False, error="REPOSITORY_FILE_DENIED")
            content = bytearray()
            while len(content) <= MAX_BYTES:
                chunk = os.read(descriptor, min(8192, MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            after = os.fstat(descriptor)
            if (len(content) > MAX_BYTES or len(content) != before.st_size
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                return ToolResult(ok=False, error="REPOSITORY_FILE_CHANGED_OR_TOO_LARGE")
            text = content.decode("utf-8")
            if "\x00" in text or any(ord(character) < 32 and character not in "\n\r\t" for character in text):
                return ToolResult(ok=False, error="REPOSITORY_BINARY_DENIED")
            if _redact_str(text) != text or SENSITIVE_CONTENT.search(text):
                return ToolResult(ok=False, error="REPOSITORY_SENSITIVE_CONTENT")
            return ToolResult(ok=True, data={"file": {"path": path, "text": text,
                "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}})
        except (OSError, UnicodeError, ValueError):
            return ToolResult(ok=False, error="REPOSITORY_READ_DENIED")
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)