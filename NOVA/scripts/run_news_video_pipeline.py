"""
Run the Phase 1 autonomous AI-news cartoon video pipeline.

Usage:
  python scripts/run_news_video_pipeline.py
  python scripts/run_news_video_pipeline.py --output-root generated --enable-upload
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

if (
    VENV_PYTHON.exists()
    and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
    and os.environ.get("NOVA_PIPELINE_VENV_ACTIVE") != "1"
):
    os.environ["NOVA_PIPELINE_VENV_ACTIVE"] = "1"
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.automation import LocalNewsVideoPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NOVA local AI news video automation")
    parser.add_argument("--output-root", default="generated", help="Base output directory")
    parser.add_argument(
        "--enable-upload",
        action="store_true",
        help="Reserved for phase 2. For now this will fail intentionally.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline = LocalNewsVideoPipeline(output_root=args.output_root, enable_upload=args.enable_upload)
    run = pipeline.run_once()

    payload = {
        "run_id": run.run_id,
        "status": run.status,
        "video_path": run.context.get("video_path", ""),
        "script_path": run.context.get("script_path", ""),
        "captions_path": run.context.get("captions_path", ""),
        "seo_path": run.context.get("seo_path", ""),
        "steps": [{"name": s.name, "status": s.status, "error": s.error} for s in run.steps],
    }
    print(json.dumps(payload, indent=2))

    return 0 if run.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
