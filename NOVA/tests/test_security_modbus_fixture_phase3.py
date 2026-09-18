from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_modbus_request_builder_is_fc43_mei14_only():
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "ot.py",
        "collector_ot_modbus_builder",
    )

    request = module.build_modbus_fc43_request(transaction_id=7, unit_id=1)
    assert request[7] == 0x2B
    assert request[8] == 0x0E
    assert request[9] == 0x01
    assert request[10] == 0x00
