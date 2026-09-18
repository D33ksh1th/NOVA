# NOVA Next Automation Blueprint

## Objective

Deliver a zero-manual pipeline that runs locally:

1. Fetch latest AI news
2. Research and rank candidate stories
3. Generate a short script (about 150 words)
4. Build scene plan
5. Generate cartoon-style visual assets
6. Narrate with local TTS
7. Build captions
8. Assemble a polished 60-second MP4
9. Prepare SEO metadata
10. Upload (Phase 2)

## Implemented In This Milestone

- Generic workflow engine:
  - `services/automation/workflow.py`
- Reusable agent pipeline for YouTube-style short generation:
  - `services/automation/news_video_pipeline.py`
- One-command runner:
  - `scripts/run_news_video_pipeline.py`

## Agent Chain (Current)

1. `news_agent`
2. `research_agent`
3. `planner_agent`
4. `script_agent`
5. `scene_agent`
6. `image_agent`
7. `voice_agent`
8. `captions_agent`
9. `editor_agent`
10. `seo_agent`
11. `uploader_agent` (placeholder; disabled by default)

## Output Layout

Each run creates:

- `generated/<run_id>/scripts/script.txt`
- `generated/<run_id>/scripts/scenes.json`
- `generated/<run_id>/images/scene_01.png` ... `scene_08.png`
- `generated/<run_id>/audio/narration.wav`
- `generated/<run_id>/captions/captions.srt`
- `generated/<run_id>/videos/ai_news_short.mp4`
- `generated/<run_id>/seo/seo.json`
- `generated/<run_id>/run.json`

## How To Run

From the NOVA root:

```bash
python scripts/run_news_video_pipeline.py
```

Optional:

```bash
python scripts/run_news_video_pipeline.py --output-root generated
```

## Runtime Requirements

- Python dependencies from `requirements.txt`
- `ffmpeg` installed and available on PATH
- Local TTS backend:
  - macOS: `say` (default path)
  - Linux: `espeak`
- Internet access for RSS feeds

## Why This Design Supports Future Automations

The workflow engine is generic and can run any ordered agent chain with shared context.

This makes YouTube only one pipeline among several:

- YouTube Shorts
- Blog generator
- Podcast creator
- Social media clips
- Future autonomous workflows

## Next Phases

## Phase 1.5 (Stability)

1. Add retry and timeout policy per agent.
2. Add structured metrics and run history table.
3. Add quality checks for script length, scene count, and final duration.

## Phase 2 (Production Media Quality)

1. Integrate optional local image generation adapter (Flux).
2. Add template-based overlays, logo animation, and audio ducking.
3. Add Whisper word-level subtitle timing.

## Phase 3 (Upload + Multi-Channel)

1. Implement YouTube uploader agent via Data API.
2. Add channel profile abstraction:
   - tone
   - tags
   - target audience
   - posting windows
3. Add per-channel title/description optimization.

## Phase 4 (Analytics Feedback Loop)

1. Pull watch-time and retention signals.
2. Feed results into planner memory.
3. Auto-tune scripts, scene pacing, and thumbnail prompts per channel.
