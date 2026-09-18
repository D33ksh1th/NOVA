"""Nova system status skill — instant response without LLM.

Handles: 'system status', 'nova status', 'are you working', 'health check',
'what is running', 'diagnostics'
"""

import re
import time
import platform
import socket
from services.skills.base import Skill, SkillContext

_TRIGGERS = [
    r"\bsystem status\b",
    r"\bnova status\b",
    r"\bhealth (check|status)\b",
    r"\bare you (working|online|running|ok|okay)\b",
    r"\bis everything (working|running|ok|up)\b",
    r"\bdiagnostics\b",
    r"\bstatus report\b",
    r"\bwhat is running\b",
    r"\bcheck (all )?systems\b",
    r"\bshow (system |nova )?(status|health)\b",
    r"\bsystem vitals\b",
    r"\bmy system (status|info|vitals|specs)\b",
    r"\b(cpu|ram|memory|battery|disk|storage) (usage|status|info)\b",
    r"\bhow much (ram|memory|cpu|storage|disk|battery)\b",
    r"\bdevice (status|info|specs)\b",
]


class NovaStatusSkill(Skill):
    @property
    def name(self) -> str:
        return "nova_status"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        return any(re.search(p, text) for p in _TRIGGERS)

    def execute(self, ctx: SkillContext) -> dict:
        from packages.config import settings

        services = {}
        issues = []

        # Backend
        services["backend"] = {"status": "online", "host": settings.API_HOST, "port": settings.API_PORT}

        # LLM
        try:
            import requests
            r = requests.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=3)
            models = [m["name"] for m in r.json().get("models", [])] if r.ok else []
            services["llm"] = {"status": "online", "provider": "ollama", "model": settings.CHAT_MODEL, "available_models": models[:5]}
        except Exception:
            services["llm"] = {"status": "offline", "provider": "ollama"}
            issues.append("LLM (Ollama) is not reachable")

        # Voice
        try:
            from packages.registry import registry
            ve = registry.voice_engine
            services["voice"] = {
                "status": "online" if ve.enabled else "disabled",
                "tts": ve.synthesizer.__class__.__name__,
                "stt": ve.recognizer.__class__.__name__,
                "wake_word": settings.WAKE_WORD,
            }
            try:
                from services.voice.tts import KokoroSpeechSynthesizer
                services["voice"]["persona"] = getattr(KokoroSpeechSynthesizer, '_active_persona', 'jarvis')
            except Exception:
                pass
        except Exception:
            services["voice"] = {"status": "unknown"}

        # Security
        try:
            from packages.registry import registry
            sc = registry.security_center
            services["security"] = {
                "status": "online",
                "findings": len(sc.findings),
                "agents": len(sc.agents),
                "assets": len(sc.assets),
            }
        except Exception:
            services["security"] = {"status": "unknown"}

        # Vision
        services["vision"] = {"status": "enabled" if settings.ENABLE_VISION else "disabled"}

        # Memory
        try:
            from packages.registry import registry
            profiles = registry.voice_engine.pipeline.speaker_registry.all_profiles()
            services["identity"] = {
                "enrolled_speakers": len(profiles),
                "speakers": [p.name for p in profiles],
                "recognition_gate": "on" if settings.VOICE_RECOGNITION_GATE else "off",
            }
        except Exception:
            services["identity"] = {"enrolled_speakers": 0}

        # System hardware vitals
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_if_addrs()
        primary_ip = "unknown"
        for iface, addrs in net.items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    primary_ip = addr.address
                    break
            if primary_ip != "unknown":
                break

        battery_info = None
        try:
            bat = psutil.sensors_battery()
            if bat:
                battery_info = {
                    "percent": bat.percent,
                    "plugged_in": bat.power_plugged,
                    "time_left": f"{bat.secsleft // 3600}h {(bat.secsleft % 3600) // 60}m" if bat.secsleft > 0 else "charging" if bat.power_plugged else "unknown",
                }
        except Exception:
            pass

        services["system"] = {
            "status": "online",
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cpu": f"{cpu}%",
            "memory": f"{mem.percent}% ({round(mem.used / (1024**3), 1)}/{round(mem.total / (1024**3), 1)} GB)",
            "disk": f"{disk.percent}% ({round(disk.used / (1024**3), 1)}/{round(disk.total / (1024**3), 1)} GB)",
            "ip": primary_ip,
            "uptime": f"{round((time.time() - psutil.boot_time()) / 3600, 1)}h",
        }
        if battery_info:
            services["battery"] = {
                "status": "charging" if battery_info["plugged_in"] else "on_battery",
                "level": f"{battery_info['percent']}%",
                "time_left": battery_info["time_left"],
            }

        all_ok = len(issues) == 0
        sys_info = services.get("system", {})

        spoken = f"All systems operational, sir. " if all_ok else f"{len(issues)} issue detected. "
        spoken += f"CPU at {sys_info.get('cpu', '?')}, memory at {mem.percent}%, disk at {disk.percent}%."
        if battery_info:
            spoken += f" Battery at {battery_info['percent']}%"
            spoken += ", plugged in." if battery_info["plugged_in"] else f", {battery_info['time_left']} remaining."
        if not all_ok:
            spoken += " " + ". ".join(issues) + "."

        return {
            "response": spoken,
            "action": "nova_status",
            "intent": "system_status",
            "data": {
                "type": "nova_status",
                "all_ok": all_ok,
                "issues": issues,
                "services": services,
            },
        }
