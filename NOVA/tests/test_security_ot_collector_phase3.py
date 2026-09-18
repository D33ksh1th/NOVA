from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSocket:
    def __init__(self, response_hex: str):
        self.sent: list[bytes] = []
        self.response = bytes.fromhex(response_hex)

    def settimeout(self, timeout: float):
        return None

    def connect(self, addr):
        return None

    def sendall(self, data: bytes):
        self.sent.append(data)

    def recv(self, n: int):
        return self.response

    def close(self):
        return None


def test_modbus_probe_emits_fc43_only_fixture_based():
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "ot.py",
        "collector_ot_module",
    )

    fixture = (Path(__file__).resolve().parent / "fixtures" / "modbus_fc43_response.hex").read_text().strip()
    fake_sock = _FakeSocket(fixture)

    result = module.probe_modbus_fc43_identity(
        target_ip="10.20.40.44",
        transport_factory=lambda: fake_sock,
    )

    assert result["ok"] is True
    assert fake_sock.sent, "probe did not send any payload"
    request = fake_sock.sent[0]

    # FC43/MEI 14 only
    assert request[7] == 0x2B
    assert request[8] == 0x0E

    # Ensure prohibited write/read opcodes (FC1-6) are not used as primary function code
    assert request[7] not in {0x01, 0x02, 0x03, 0x04, 0x05, 0x06}


def test_ot_active_probe_requires_valid_authorization(tmp_path: Path):
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "ot.py",
        "collector_ot_module_auth",
    )

    result = module.collect_ot_identity_snapshot(
        targets=["10.20.40.44"],
        audit_probe=lambda target, port: None,
        auth_record=None,
        kill_switch=False,
        latency_breaker_ms=2000,
    )
    assert result["mode"] == "passive_only"

    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "approver": "soc_admin",
                "ticket": "CHG-1001",
                "auth_ref": "CHG-1001",
                "window_start_epoch": int(time.time()) - 10,
                "window_end_epoch": int(time.time()) + 120,
            }
        )
    )
    record = module._load_auth_record(str(auth_file))
    assert module._is_authorized(record) is True


def test_ot_collector_kill_switch_and_dnp3_passive(tmp_path: Path):
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "ot.py",
        "collector_ot_module_killswitch",
    )

    os.environ["NOVA_SECURITY_ACTIVE_PROBING_KILL_SWITCH"] = "true"
    collector = module.OtCollector(targets_fn=lambda: ["10.20.40.44"], audit_probe=lambda target, port: None)
    payload = collector.collect()

    ot_identity = payload["ot_identity"]
    assert ot_identity["mode"] == "active_halted"
    assert ot_identity["dnp3_mode"] == "passive_only"
