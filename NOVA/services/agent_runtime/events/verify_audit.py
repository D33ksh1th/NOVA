"""Read-only verifier: python -m services.agent_runtime.events.verify_audit PATH."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from services.agent_runtime.events.audit import AuditLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a closed NOVA audit journal without modifying it.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-head", help="Previously retained trusted head hash")
    args = parser.parse_args(argv)
    report = asyncio.run(AuditLog.check_file(args.path, expected_head=args.expected_head))
    print(json.dumps(asdict(report), sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())