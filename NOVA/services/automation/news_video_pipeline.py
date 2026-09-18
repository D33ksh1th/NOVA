"""
Local autonomous pipeline:
news -> research -> script -> scenes -> images -> voice -> captions -> video -> seo
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import textwrap
import uuid
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from packages.common import logger
from services.automation.workflow import WorkflowAgent, WorkflowContext, WorkflowEngine, WorkflowRun

try:
    from PIL import Image, ImageDraw, ImageFilter
except Exception:  # pragma: no cover - optional runtime dependency in some envs
    Image = None
    ImageDraw = None
    ImageFilter = None


NEWS_SOURCES = [
    "https://news.google.com/rss/search?q=artificial+intelligence",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://hnrss.org/frontpage",
    "https://www.reddit.com/r/artificial/.rss",
]


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\-\s]", "", value)
    cleaned = re.sub(r"\s+", "-", cleaned.strip().lower())
    return cleaned[:80] or "untitled"


def _strip_html(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _wrap_text(text: str, width: int) -> List[str]:
    wrapped = textwrap.wrap((text or "").strip(), width=width)
    return wrapped or [""]


def _split_sentences(text: str) -> List[str]:
    pieces = re.split(r"(?<=[\.!?])\s+", (text or "").strip())
    return [p.strip() for p in pieces if p.strip()]


def _read_url(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NOVA)"})
    insecure = os.environ.get("NOVA_PIPELINE_INSECURE_SSL", "1").strip().lower() in {"1", "true", "yes"}
    context = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()


@dataclass
class PipelinePaths:
    run_root: Path
    scripts_dir: Path
    audio_dir: Path
    images_dir: Path
    captions_dir: Path
    videos_dir: Path
    seo_dir: Path
    temp_dir: Path

    @classmethod
    def create(cls, base_dir: Path, run_id: str) -> "PipelinePaths":
        run_root = base_dir / run_id
        scripts_dir = run_root / "scripts"
        audio_dir = run_root / "audio"
        images_dir = run_root / "images"
        captions_dir = run_root / "captions"
        videos_dir = run_root / "videos"
        seo_dir = run_root / "seo"
        temp_dir = run_root / "temp"
        for d in (scripts_dir, audio_dir, images_dir, captions_dir, videos_dir, seo_dir, temp_dir):
            d.mkdir(parents=True, exist_ok=True)
        return cls(
            run_root=run_root,
            scripts_dir=scripts_dir,
            audio_dir=audio_dir,
            images_dir=images_dir,
            captions_dir=captions_dir,
            videos_dir=videos_dir,
            seo_dir=seo_dir,
            temp_dir=temp_dir,
        )


class NewsAgent:
    name = "news_agent"

    def __init__(self, max_articles: int = 10):
        self.max_articles = max_articles

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        articles: List[Dict[str, str]] = []
        for source in NEWS_SOURCES:
            try:
                data = _read_url(source)
                root = ET.fromstring(data)
                for item in root.findall(".//item"):
                    title = _strip_html(item.findtext("title", default=""))
                    link = _strip_html(item.findtext("link", default=""))
                    summary = _strip_html(item.findtext("description", default=""))
                    pub_date = _strip_html(item.findtext("pubDate", default=""))
                    if not title or not link:
                        continue
                    articles.append(
                        {
                            "title": title,
                            "link": link,
                            "summary": summary,
                            "published": pub_date,
                            "source": source,
                        }
                    )
            except Exception as exc:
                logger.warning("NewsAgent: source failed", source=source, error=str(exc))

        dedup: Dict[str, Dict[str, str]] = {}
        for item in articles:
            dedup[item["link"]] = item
        picked = list(dedup.values())[: self.max_articles]

        if not picked:
            picked = [
                {
                    "title": "Open-source AI models gain enterprise adoption for coding and copilots",
                    "link": "https://example.local/ai-enterprise-adoption",
                    "summary": "Teams are adopting open models for cost control, privacy, and faster iteration across internal tools.",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "local_fallback",
                },
                {
                    "title": "New multimodal AI assistants improve reasoning over text, image, and audio",
                    "link": "https://example.local/multimodal-assistants",
                    "summary": "Vendors are shipping assistants that combine voice, vision, and planning for daily workflows.",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "source": "local_fallback",
                },
            ]
            logger.warning("NewsAgent: all feeds unavailable, using local fallback headlines")

        context.set("news_articles", picked)
        return {"count": len(picked)}


class ResearchAgent:
    name = "research_agent"

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        articles = context.get("news_articles", [])
        research = []
        for item in articles:
            summary = item.get("summary") or item.get("title")
            research.append(
                {
                    "title": item.get("title", ""),
                    "summary": summary[:700],
                    "link": item.get("link", ""),
                    "source": item.get("source", ""),
                }
            )
        context.set("research_notes", research)
        return {"count": len(research)}


class PlannerAgent:
    name = "planner_agent"

    KEYWORDS = ["openai", "gemini", "anthropic", "apple", "meta", "nvidia", "microsoft", "ai"]

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        research = context.get("research_notes", [])
        if not research:
            raise RuntimeError("No research notes available")

        def _score(item: Dict[str, str]) -> int:
            text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            score = 0
            for word in self.KEYWORDS:
                if word in text:
                    score += 10
            score += min(20, len(item.get("summary", "")) // 40)
            return score

        ranked = sorted(research, key=_score, reverse=True)
        chosen = ranked[0]
        context.set("selected_news", chosen)
        context.set("ranked_news", ranked)
        return {"selected_title": chosen.get("title", "")}


class ScriptAgent:
    name = "script_agent"

    def __init__(self, target_words: int = 150):
        self.target_words = target_words

    def _generate_with_ollama(self, prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        host = os.environ.get("NOVA_OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{host}/api/generate"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("response") or "").strip()

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        selected = context.get("selected_news", {})
        if not selected:
            raise RuntimeError("No selected news in context")

        title = selected.get("title", "")
        summary = selected.get("summary", "")
        prompt = textwrap.dedent(
            f"""
            Write a {self.target_words}-word script for a 60-second AI news short.
            Style: energetic, clear, simple English.
            Must include:
            - one opening hook sentence
            - key update summary
            - why it matters
            - one closing line

            Topic title: {title}
            Source notes: {summary}
            """
        ).strip()

        generated = ""
        try:
            model = os.environ.get("NOVA_SCRIPT_MODEL", "gemma3:12b")
            generated = self._generate_with_ollama(prompt=prompt, model=model)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("ScriptAgent: ollama generation failed", error=str(exc))

        if not generated:
            generated = (
                f"Big AI update today: {title}. "
                f"Here is what happened. {summary[:220]}. "
                "The bigger story is how fast major labs are shipping real features and raising the bar for everyone else. "
                "For users, this means better tools, faster workflows, and stronger competition across the AI ecosystem. "
                "For builders, it means now is the time to experiment and move quickly. "
                "Stay with us for the next AI update."
            )

        script = re.sub(r"\s+", " ", generated).strip()
        paths: PipelinePaths = context.get("paths")
        script_path = paths.scripts_dir / "script.txt"
        script_path.write_text(script, encoding="utf-8")
        context.set("script", script)
        context.set("script_path", str(script_path))

        return {
            "script_path": str(script_path),
            "word_count": len(script.split()),
        }


class SceneAgent:
    name = "scene_agent"

    def __init__(self, scene_count: int = 8):
        self.scene_count = scene_count

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        script = context.get("script", "")
        if not script:
            raise RuntimeError("No script available")

        lines = _split_sentences(script)
        if len(lines) < self.scene_count:
            lines = lines + ["Stay tuned for more AI updates."] * (self.scene_count - len(lines))

        scenes = []
        for i in range(self.scene_count):
            line = lines[i % len(lines)]
            scenes.append(
                {
                    "index": i + 1,
                    "headline": f"AI NEWS // {i + 1:02d}",
                    "caption": line,
                    "presenter": "Astra",
                    "image_prompt": f"One cartoon female news presenter named Astra in a futuristic newsroom, expressive pose, animated broadcast style, scene about: {line}",
                }
            )

        paths: PipelinePaths = context.get("paths")
        scene_path = paths.scripts_dir / "scenes.json"
        scene_path.write_text(json.dumps(scenes, indent=2), encoding="utf-8")
        context.set("scenes", scenes)
        context.set("scene_path", str(scene_path))
        return {"scene_count": len(scenes), "scene_path": str(scene_path)}


class ImageAgent:
    name = "image_agent"

    def _run_command(self, cmd: Sequence[str]) -> None:
        subprocess.run(list(cmd), check=True, capture_output=True, text=True)

    def _draw_astra_professional(self, draw: "ImageDraw", x: int, y: int, scene_index: int) -> None:
        """Draw a professional-looking news presenter Astra on the right side of the frame."""
        # Skin, hair, clothing colors for a polished broadcast look
        skin = (248, 215, 195)
        hair_dark = (41, 28, 20)
        eyes_dark = (34, 34, 34)
        mouth = (215, 106, 94)
        blazer = (211, 89, 72)
        shirt_white = (248, 248, 248)
        
        # Head
        draw.ellipse([x, y, x + 150, y + 160], fill=skin, outline=(240, 225, 210), width=4)
        
        # Hair (longer, professional)
        draw.pieslice([x - 10, y - 20, x + 160, y + 150], start=180, end=360, fill=hair_dark, outline=hair_dark)
        draw.arc([x + 5, y, x + 145, y + 140], start=0, end=180, fill=hair_dark, width=6)
        
        # Eyes (more expressive)
        eye_y = y + 50
        draw.ellipse([x + 35, eye_y, x + 55, eye_y + 20], fill=eyes_dark, outline=eyes_dark)
        draw.ellipse([x + 95, eye_y, x + 115, eye_y + 20], fill=eyes_dark, outline=eyes_dark)
        draw.ellipse([x + 40, eye_y + 2, x + 50, eye_y + 12], fill=(255, 255, 255), outline=eyes_dark)
        draw.ellipse([x + 100, eye_y + 2, x + 110, eye_y + 12], fill=(255, 255, 255), outline=eyes_dark)
        
        # Eyebrows
        draw.arc([x + 30, eye_y - 15, x + 60, eye_y], start=0, end=180, fill=hair_dark, width=3)
        draw.arc([x + 90, eye_y - 15, x + 120, eye_y], start=0, end=180, fill=hair_dark, width=3)
        
        # Nose
        draw.polygon([(x + 75, y + 65), (x + 70, y + 90), (x + 80, y + 90)], fill=skin, outline=mouth)
        
        # Mouth (friendly smile that varies by scene)
        mouth_width = 35 if scene_index % 2 == 0 else 30
        draw.arc([x + 75 - mouth_width // 2, y + 95, x + 75 + mouth_width // 2, y + 115], start=0, end=180, fill=mouth, width=3)
        
        # Neck
        draw.rectangle([x + 60, y + 155, x + 90, y + 175], fill=skin, outline=skin)
        
        # Blazer (professional broadcast outfit)
        draw.polygon([
            (x - 5, y + 175),
            (x + 155, y + 175),
            (x + 165, y + 300),
            (x - 15, y + 300)
        ], fill=blazer, outline=(180, 70, 55))
        
        # Shirt collar and tie area
        draw.rectangle([x + 55, y + 175, x + 95, y + 220], fill=shirt_white, outline=(220, 220, 220))
        draw.polygon([(x + 68, y + 175), (x + 82, y + 225), (x + 75, y + 225)], fill=(190, 60, 45))
        
        # Shoulders and depth
        draw.ellipse([x - 10, y + 290, x + 30, y + 320], fill=(180, 70, 55), outline=(150, 50, 35))
        draw.ellipse([x + 120, y + 290, x + 160, y + 320], fill=(180, 70, 55), outline=(150, 50, 35))

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        scenes = context.get("scenes", [])
        if not scenes:
            raise RuntimeError("No scenes to render")

        paths: PipelinePaths = context.get("paths")
        output_paths = []

        if Image is None or ImageDraw is None:
            if not shutil.which("ffmpeg"):
                raise RuntimeError("Pillow is missing and ffmpeg is not available for fallback image rendering")

            palette = ["0x10263d", "0x17395a", "0x21496f", "0x0f314f", "0x20476a", "0x1a3a59", "0x18324f", "0x264f75"]
            for scene in scenes:
                idx = int(scene["index"])
                image_path = paths.images_dir / f"scene_{idx:02d}.png"
                color = palette[(idx - 1) % len(palette)]
                self._run_command([
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:s=1280x720:d=1",
                    "-frames:v",
                    "1",
                    str(image_path),
                ])
                output_paths.append(str(image_path))

            context.set("image_paths", output_paths)
            return {"image_count": len(output_paths), "renderer": "ffmpeg_fallback"}

        for scene in scenes:
            idx = int(scene["index"])
            caption = scene["caption"]
            headline = str(scene.get("headline") or f"AI NEWS // {idx:02d}")
            image_path = paths.images_dir / f"scene_{idx:02d}.png"

            # Create broadcast-style frame: news graphics on left, Astra on right
            img = Image.new("RGB", (1280, 720), color=(8, 18, 32))
            draw = ImageDraw.Draw(img)

            # Left panel: News content area
            draw.rectangle([16, 16, 820, 704], fill=(16, 36, 62), outline=(96, 178, 225), width=4)
            
            # Header bar with animation stripe
            draw.rectangle([20, 20, 816, 90], fill=(22, 50, 88), outline=(140, 200, 255), width=3)
            draw.rectangle([20, 20, 20 + (idx * 15) % 796, 25], fill=(255, 178, 74))
            draw.text((30, 35), headline, fill=(240, 255, 255))
            draw.text((30, 60), "Breaking News Update", fill=(160, 210, 255))
            
            # News content boxes (animated look with staggered placement)
            box_y = 110
            draw.rectangle([30, box_y, 806, box_y + 160], fill=(18, 40, 70), outline=(100, 180, 240), width=2)
            wrapped = _wrap_text(caption, width=80)
            text_y = box_y + 15
            for i, line in enumerate(wrapped[:5]):
                draw.text((45, text_y), line, fill=(220, 240, 255))
                text_y += 28
            
            # Bottom news ticker area
            draw.rectangle([30, 600, 806, 690], fill=(14, 30, 52), outline=(75, 140, 200), width=2)
            ticker_text = f"AI Update {idx} • Stay Informed • Technology News"
            draw.text((45, 650), ticker_text, fill=(180, 220, 255))

            # Right panel: Astra presenter
            self._draw_astra_professional(draw, 850, 120, idx)
            
            # Speech bubble from Astra (top right)
            bubble_x, bubble_y = 900, 320
            bubble_width, bubble_height = 340, 120
            draw.rounded_rectangle(
                [bubble_x, bubble_y, bubble_x + bubble_width, bubble_y + bubble_height],
                radius=20,
                fill=(245, 250, 255),
                outline=(96, 160, 220),
                width=3
            )
            # Pointer to Astra
            draw.polygon([
                (bubble_x + 80, bubble_y + bubble_height),
                (bubble_x + 100, bubble_y + bubble_height + 25),
                (bubble_x + 60, bubble_y + bubble_height)
            ], fill=(245, 250, 255), outline=(96, 160, 220))
            
            speech_lines = _wrap_text(caption, width=40)
            speech_y = bubble_y + 20
            for line in speech_lines[:3]:
                draw.text((bubble_x + 15, speech_y), line, fill=(18, 32, 56))
                speech_y += 30

            # Branding bar at bottom
            draw.rectangle([850, 680, 1260, 704], fill=(14, 28, 50), outline=(96, 160, 220), width=2)
            draw.text((880, 685), "AI News Briefing • Astra Presenting", fill=(180, 220, 255))

            if ImageFilter is not None:
                img = img.filter(ImageFilter.SMOOTH_MORE)

            img.save(image_path)
            output_paths.append(str(image_path))

        context.set("image_paths", output_paths)
        return {"image_count": len(output_paths), "renderer": "pillow"}


class VoiceAgent:
    name = "voice_agent"

    def _run_command(self, cmd: Sequence[str], input_text: str | None = None) -> None:
        subprocess.run(
            list(cmd),
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
        )

    def _find_piper_binary(self) -> str:
        candidates = [
            PROJECT_ROOT / ".venv" / "bin" / "piper",
            Path(sys.executable).resolve().parent / "piper",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        found = shutil.which("piper")
        return found or ""

    def _select_piper_model(self) -> Path:
        preferred = os.environ.get("VIDEO_PRESENTER_VOICE", "english_amy").strip().lower() or "english_amy"
        model_map = {
            "english_amy": PROJECT_ROOT / "assets/voices/piper/en_US_amy_medium/en_US-amy-medium.onnx",
            "english_lessac": PROJECT_ROOT / "assets/voices/piper/en_US_lessac_medium/en_US-lessac-medium.onnx",
            "english_ryan": PROJECT_ROOT / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx",
        }
        model = model_map.get(preferred, model_map["english_amy"])
        if model.exists():
            return model
        for fallback in model_map.values():
            if fallback.exists():
                return fallback
        raise RuntimeError("No bundled Piper model is available")

    def _synthesize_with_piper(self, text: str, out_path: Path) -> bool:
        piper_bin = self._find_piper_binary()
        if not piper_bin:
            return False

        model_path = self._select_piper_model()
        cmd = [
            piper_bin,
            "--model",
            str(model_path),
            "--length_scale",
            "1.06",
            "--noise_scale",
            "0.45",
            "--noise_w_scale",
            "0.62",
            "--sentence_silence",
            "0.18",
            "--output_file",
            str(out_path),
        ]
        self._run_command(cmd, input_text=text)
        return out_path.exists()

    def _synthesize_with_say(self, text: str, out_path: Path) -> None:
        aiff_path = out_path.with_suffix(".aiff")
        self._run_command(["say", "-v", "Ava", "-r", "188", "-o", str(aiff_path), text])
        if shutil.which("ffmpeg"):
            self._run_command([
                "ffmpeg",
                "-y",
                "-i",
                str(aiff_path),
                "-af",
                "volume=2.2,loudnorm",
                str(out_path),
            ])
        else:
            raise RuntimeError("ffmpeg is required to convert narration audio on macOS")

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        script = context.get("script", "")
        if not script:
            raise RuntimeError("No script for narration")

        paths: PipelinePaths = context.get("paths")
        wav_path = paths.audio_dir / "narration.wav"
        context.set("presenter_name", "Astra")

        used_backend = ""
        if self._synthesize_with_piper(script, wav_path):
            used_backend = "piper"
        elif shutil.which("say"):
            self._synthesize_with_say(script, wav_path)
            used_backend = "say"
        elif shutil.which("espeak"):
            self._run_command(["espeak", "-s", "180", "-w", str(wav_path), script])
            used_backend = "espeak"
        else:
            raise RuntimeError("No local TTS backend found (expected Piper, macOS say, or espeak)")

        context.set("narration_path", str(wav_path))
        context.set("narration_backend", used_backend)
        return {"narration_path": str(wav_path), "backend": used_backend}


class CaptionsAgent:
    name = "captions_agent"

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        script = context.get("script", "")
        if not script:
            raise RuntimeError("No script available for captions")

        paths: PipelinePaths = context.get("paths")
        srt_path = paths.captions_dir / "captions.srt"
        sentences = _split_sentences(script)
        if not sentences:
            sentences = [script]

        total_secs = 60.0
        slot = max(2.0, total_secs / max(1, len(sentences)))

        def _ts(sec: float) -> str:
            ms = int(sec * 1000)
            hh = ms // 3600000
            mm = (ms % 3600000) // 60000
            ss = (ms % 60000) // 1000
            mmm = ms % 1000
            return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"

        lines = []
        for i, sentence in enumerate(sentences, 1):
            start = (i - 1) * slot
            end = min(total_secs, i * slot)
            lines.append(str(i))
            lines.append(f"{_ts(start)} --> {_ts(end)}")
            lines.append(sentence)
            lines.append("")

        srt_path.write_text("\n".join(lines), encoding="utf-8")
        context.set("captions_path", str(srt_path))
        return {"captions_path": str(srt_path), "caption_count": len(sentences)}


class EditorAgent:
    name = "editor_agent"

    def _run_command(self, cmd: Sequence[str], cwd: Path | None = None) -> None:
        subprocess.run(list(cmd), check=True, capture_output=True, text=True, cwd=str(cwd) if cwd else None)

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg is required for video assembly")

        image_paths = context.get("image_paths", [])
        narration_path = context.get("narration_path", "")
        captions_path = context.get("captions_path", "")
        if not image_paths or not narration_path or not captions_path:
            raise RuntimeError("Missing image/audio/captions artifacts")

        paths: PipelinePaths = context.get("paths")
        per_scene_seconds = round(60 / max(1, len(image_paths)), 2)

        clip_paths: List[Path] = []
        for idx, image in enumerate(image_paths, 1):
            clip = paths.temp_dir / f"clip_{idx:02d}.mp4"
            vf = "scale=1280:720,zoompan=z='min(zoom+0.0012,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720,format=yuv420p"
            self._run_command([
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                image,
                "-vf",
                vf,
                "-t",
                str(per_scene_seconds),
                "-r",
                "24",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ])
            clip_paths.append(clip)

        concat_file = paths.temp_dir / "clips.txt"
        concat_lines = []
        for clip in clip_paths:
            safe = str(clip.resolve()).replace("'", "'\\''")
            concat_lines.append(f"file '{safe}'")
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

        merged = paths.temp_dir / "video_merged.mp4"
        self._run_command([
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(merged),
        ])

        final_video = paths.videos_dir / "ai_news_short.mp4"
        self._run_command([
            "ffmpeg",
            "-y",
            "-i",
            "temp/video_merged.mp4",
            "-i",
            "audio/narration.wav",
            "-i",
            "captions/captions.srt",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            "-shortest",
            "videos/ai_news_short.mp4",
        ], cwd=paths.run_root)

        context.set("video_path", str(final_video))
        return {"video_path": str(final_video)}


class SEOAgent:
    name = "seo_agent"

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        selected = context.get("selected_news", {})
        title = selected.get("title", "AI update")
        short = title[:72]
        seo = {
            "title": f"{short} | AI News Update",
            "description": (
                "Daily AI news update with a cartoon presenter. "
                f"Today: {title}. #AI #MachineLearning #TechNews"
            ),
            "tags": ["AI", "Artificial Intelligence", "AI News", "Tech", "Innovation"],
        }
        paths: PipelinePaths = context.get("paths")
        seo_path = paths.seo_dir / "seo.json"
        seo_path.write_text(json.dumps(seo, indent=2), encoding="utf-8")
        context.set("seo_path", str(seo_path))
        return {"seo_path": str(seo_path)}


class UploaderAgent:
    name = "uploader_agent"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        if not self.enabled:
            return {"uploaded": False, "reason": "phase_1_local_only"}
        raise RuntimeError("UploaderAgent is reserved for phase 2 YouTube API integration")


class LocalNewsVideoPipeline:
    """
    A reusable pipeline that can run with zero manual interaction.
    """

    def __init__(self, output_root: str = "generated", enable_upload: bool = False):
        self.output_root = Path(output_root)
        self.enable_upload = enable_upload
        self.engine = WorkflowEngine()

    def _build_agents(self) -> List[WorkflowAgent]:
        return [
            NewsAgent(max_articles=10),
            ResearchAgent(),
            PlannerAgent(),
            ScriptAgent(target_words=150),
            SceneAgent(scene_count=8),
            ImageAgent(),
            VoiceAgent(),
            CaptionsAgent(),
            EditorAgent(),
            SEOAgent(),
            UploaderAgent(enabled=self.enable_upload),
        ]

    def run_once(self) -> WorkflowRun:
        run_id = f"ai-news-{_utc_now_compact()}-{uuid.uuid4().hex[:6]}"
        paths = PipelinePaths.create(self.output_root, run_id)
        seed = {
            "paths": paths,
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        result = self.engine.run(run_id=run_id, agents=self._build_agents(), seed_context=seed)

        # Persist run metadata for external schedulers/analytics.
        meta = {
            "run_id": result.run_id,
            "status": result.status,
            "started_at": result.started_at,
            "ended_at": result.ended_at,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                    "error": s.error,
                }
                for s in result.steps
            ],
            "video_path": result.context.get("video_path", ""),
            "seo_path": result.context.get("seo_path", ""),
        }
        (paths.run_root / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return result
