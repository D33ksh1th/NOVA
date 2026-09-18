from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_scope_module():
    scope_path = Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "scope.py"
    spec = importlib.util.spec_from_file_location("security_scope_module", scope_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["security_scope_module"] = module
    spec.loader.exec_module(module)
    return module


def test_scope_engine_refuses_unset_allow_list():
    scope = _load_scope_module()
    engine = scope.DiscoveryScopeEngine(allow_cidrs=[], deny_cidrs=[], zone_map={})
    assert engine.has_allow_scope() is False
    assert engine.is_allowed("10.20.40.10") is False


def test_deny_beats_allow():
    scope = _load_scope_module()
    engine = scope.DiscoveryScopeEngine(
        allow_cidrs=["10.20.40.0/24"],
        deny_cidrs=["10.20.40.144/32"],
        zone_map={"10.20.40.0/24": "it"},
    )
    assert engine.is_allowed("10.20.40.144") is False
    assert engine.is_allowed("10.20.40.143") is True


def test_ot_zone_cannot_exceed_tier_zero():
    scope = _load_scope_module()
    engine = scope.DiscoveryScopeEngine(
        allow_cidrs=["10.20.40.0/24"],
        deny_cidrs=[],
        zone_map={"10.20.40.0/24": "ot"},
    )
    assert engine.effective_tier_for_ip("10.20.40.44", requested_tier=3) == 0


def test_ot_rate_ceiling_cannot_be_raised_by_config():
    scope = _load_scope_module()
    engine = scope.DiscoveryScopeEngine(
        allow_cidrs=["10.20.40.0/24"],
        deny_cidrs=[],
        zone_map={"10.20.40.0/24": "ot"},
    )
    policy = engine.policy_for_ip(
        target="10.20.40.44",
        requested_tier=3,
        requested_concurrency=128,
        requested_pps=10000,
    )
    assert policy.concurrency == 1
    assert policy.packets_per_second == 5
    assert max(policy.tiers) == 0


def test_unknown_zone_is_treated_as_ot_equivalent_ceiling():
    scope = _load_scope_module()
    engine = scope.DiscoveryScopeEngine(
        allow_cidrs=["10.20.40.0/24"],
        deny_cidrs=[],
        zone_map={"10.20.40.0/24": "medical"},
    )
    policy = engine.policy_for_ip(
        target="10.20.40.77",
        requested_tier=3,
        requested_concurrency=64,
        requested_pps=10000,
    )
    assert max(policy.tiers) == 0
    assert policy.concurrency == 1
    assert policy.packets_per_second == 5
