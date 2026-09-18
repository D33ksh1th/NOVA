"""NOVA Voice CLI — Entry point for the speech layer.

Commands:
  nova voice start           — Start the always-listening daemon
  nova voice test            — Speak one line per emotion for tuning
  nova voice generate-greetings — Pre-synthesize the 40 greeting WAVs
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml


def load_config(path: str = None) -> dict:
    if path is None:
        path = str(Path(__file__).parent / "config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    level = getattr(logging, config["logging"]["level"].upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_start(args):
    """Start the NOVA speech daemon."""
    config = load_config(args.config)
    if args.no_fx:
        config["fx"]["enabled"] = False
    setup_logging(config)

    from .orchestrator import NovaOrchestrator
    orch = NovaOrchestrator(args.config)
    orch.start()


def cmd_test(args):
    """Speak one test line per emotion for A/B tuning."""
    config = load_config(args.config)
    if args.no_fx:
        config["fx"]["enabled"] = False
    setup_logging(config)

    from .fx import NovaFX
    from .voice import NovaVoice

    fx = NovaFX(config)
    fx.load()
    voice = NovaVoice(config, fx_processor=fx if not args.no_fx else None)
    voice.load()

    test_lines = {
        "neutral": "Systems are operating within normal parameters.",
        "warm": "It's good to hear from you again.",
        "amused": "Well, that's one way to solve the problem.",
        "urgent": "Priority alert. Action required immediately.",
        "serious": "The situation has changed — significantly.",
        "concerned": "I should flag something for your attention.",
        "confident": "I've already handled it. You're clear.",
    }

    import sounddevice as sd

    profile = config["tts"]["profiles"][config["tts"]["active_profile"]]
    base_speed = profile["speed"]

    print(f"\n  NOVA Voice Test — Profile: {config['tts']['active_profile']}")
    print(f"  FX: {'ON' if not args.no_fx else 'OFF'}")
    print(f"  {'─' * 50}\n")

    for emotion, text in test_lines.items():
        processed, speed_mult, pause_ms = voice.apply_emotion(text, emotion)
        speed = base_speed * speed_mult

        print(f"  [{emotion:>10}] {processed}")
        print(f"             speed={speed:.2f}, pause={pause_ms}ms")

        audio = voice.synthesize_sentence(processed, profile["voice"], speed)
        if fx.enabled:
            audio = fx.process(audio, config["tts"]["sample_rate"])

        sd.play(audio, config["tts"]["sample_rate"])
        sd.wait()
        time.sleep(0.5)

    print(f"\n  {'─' * 50}")
    print("  Done.\n")


def cmd_generate_greetings(args):
    """Pre-synthesize the 40 greeting WAVs."""
    config = load_config(args.config)
    setup_logging(config)

    from .fx import NovaFX
    from .voice import NovaVoice
    from .greet import NovaGreet

    fx = NovaFX(config)
    fx.load()
    voice = NovaVoice(config, fx_processor=fx)
    voice.load()

    def tts_fn(text, v, speed):
        audio = voice.speak_sync(text, v, speed)
        if fx.enabled:
            audio = fx.process(audio, config["tts"]["sample_rate"])
        return audio

    NovaGreet.generate_bank(tts_fn, config)
    print("Greeting bank generated.")


def main():
    parser = argparse.ArgumentParser(prog="nova-voice", description="NOVA Speech Layer")
    parser.add_argument("--config", "-c", help="Path to config.yaml")
    parser.add_argument("--no-fx", action="store_true", help="Disable audio FX for A/B comparison")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start", help="Start the always-listening daemon")
    sub.add_parser("test", help="Speak one line per emotion for tuning")
    sub.add_parser("generate-greetings", help="Pre-synthesize greeting WAVs")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "generate-greetings":
        cmd_generate_greetings(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
