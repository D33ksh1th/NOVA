"""
Filesystem Tool
"""

import re
from pathlib import Path

from services.tools.base import Tool


class FileSystemTool(Tool):

    @property
    def name(self):
        return "filesystem"

    def can_handle(self, message: str) -> bool:

        text = message.lower()

        keywords = [
            "list files",
            "list all files",
            "show files",
            "current directory",
            "working directory",
            "read file",
            "open file",
            "file exists",
            "find file",
            "search file",
            "file named",
        ]

        return any(keyword in text for keyword in keywords)

    def _wants_file_listing(self, text: str) -> bool:
        return bool(
            re.search(r"\blist (the )?files\b", text)
            or re.search(r"\bshow (me )?(the )?files\b", text)
            or "list files" in text
            or "show files" in text
        )

    def execute(self, message: str):

        text = message.lower()

        # Find file by name (recursive under current dir / Downloads based on prompt)
        if "find file" in text or "search file" in text or "file named" in text:
            target_name = self._extract_filename(message)
            if not target_name:
                return {
                    "action": "filesystem",
                    "success": False,
                    "response": "Tell me the file name to search for, for example: find file app.js",
                }

            roots = [self._resolve_base_path(message)]
            if roots[0] != Path.cwd():
                roots.append(Path.cwd())

            matches = []
            for root in roots:
                try:
                    for p in root.rglob("*"):
                        if p.is_file() and p.name.lower() == target_name.lower():
                            matches.append(str(p))
                            if len(matches) >= 25:
                                break
                    if matches:
                        break
                except Exception:
                    continue

            if not matches:
                return {
                    "action": "filesystem",
                    "success": False,
                    "response": f"No file named '{target_name}' found.",
                }

            return {
                "action": "filesystem",
                "success": True,
                "matches": matches,
                "response": "\n".join(matches),
            }

        # Current directory
        if "current directory" in text or "working directory" in text:

            return {
                "action": "filesystem",
                "response": str(Path.cwd())
            }

        # List files
        if self._wants_file_listing(text):
            base = self._resolve_base_path(message)
            files = sorted([f.name for f in base.iterdir()])

            return {
                "action": "filesystem",
                "path": str(base),
                "files": files,
                "response": "\n".join(files) if files else f"No files found in {base}",
            }

        # Recursive list all files in a directory
        if "list all files" in text:
            base = self._resolve_base_path(message)
            matches = []
            try:
                for p in base.rglob("*"):
                    if p.is_file():
                        matches.append(str(p))
                        if len(matches) >= 200:
                            break
            except Exception as ex:
                return {
                    "action": "filesystem",
                    "success": False,
                    "response": f"Failed to list files: {ex}",
                }

            return {
                "action": "filesystem",
                "path": str(base),
                "files": matches,
                "response": "\n".join(matches) if matches else f"No files found in {base}",
            }

        # Read file
        if "read file" in text or "open file" in text:

            filename = (
                message.replace("read file", "")
                .replace("open file", "")
                .strip()
            )

            path = Path(filename)

            if not path.exists():

                return {
                    "action": "filesystem",
                    "success": False,
                    "response": "File not found."
                }

            return {
                "action": "filesystem",
                "filename": filename,
                "content": path.read_text()
            }

        return None

    def _resolve_base_path(self, message: str) -> Path:
        text = message.lower()
        if "downloads" in text or "download folder" in text or "download directory" in text:
            return Path.home() / "Downloads"
        return Path.cwd()

    def _extract_filename(self, message: str) -> str:
        patterns = [
            r"file named\s+['\"]?([^'\"\n]+)['\"]?",
            r"find file\s+['\"]?([^'\"\n]+)['\"]?",
            r"search file\s+['\"]?([^'\"\n]+)['\"]?",
            r"find\s+['\"]?([\w\-. ]+\.[\w\-]+)['\"]?",
        ]

        for pattern in patterns:
            m = re.search(pattern, message, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""