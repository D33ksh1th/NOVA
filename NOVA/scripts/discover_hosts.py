#!/usr/bin/env python3
from __future__ import annotations

import json

from scripts.security_agent import host_discovery


def main() -> int:
    data = host_discovery()
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
