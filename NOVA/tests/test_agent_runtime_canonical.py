"""Round-trip and stability tests for the canonical JSON / fingerprint layer (3F)."""

import unicodedata

import pytest

from services.agent_runtime.policy.canonical import (
    action_fingerprint,
    canonical_bytes,
    canonical_json,
)


def test_key_order_is_irrelevant():
    a = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    b = {"c": {"x": 2, "y": 1}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_no_insignificant_whitespace():
    out = canonical_json({"a": 1, "b": [1, 2, {"c": 3}]})
    assert " " not in out
    assert out == '{"a":1,"b":[1,2,{"c":3}]}'


def test_null_is_preserved_not_dropped():
    out = canonical_json({"a": None, "b": 1})
    assert out == '{"a":null,"b":1}'


def test_nfc_normalization_makes_equal_strings_canonical():
    # "é" as composed (NFC) vs decomposed (NFD) must canonicalize identically.
    composed = unicodedata.normalize("NFC", "café")
    decomposed = unicodedata.normalize("NFD", "café")
    assert composed != decomposed  # different byte sequences going in
    assert canonical_json({"k": composed}) == canonical_json({"k": decomposed})
    assert canonical_json({decomposed: 1}) == canonical_json({composed: 1})


def test_bytes_are_utf8():
    assert canonical_bytes({"k": "café"}) == '{"k":"café"}'.encode("utf-8")


def test_non_finite_float_rejected():
    with pytest.raises(ValueError):
        canonical_json({"x": float("inf")})
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_non_string_key_rejected():
    with pytest.raises(TypeError):
        canonical_json({1: "a"})


def test_unsupported_type_rejected():
    with pytest.raises(TypeError):
        canonical_json({"x": object()})


def test_fingerprint_is_stable_and_arg_order_independent():
    fp1 = action_fingerprint(
        tool="web_search_tool",
        args={"query": "offline tts", "max_results": 5},
        agent="research_agent",
        task_id="t_1",
    )
    fp2 = action_fingerprint(
        tool="web_search_tool",
        args={"max_results": 5, "query": "offline tts"},
        agent="research_agent",
        task_id="t_1",
    )
    assert fp1 == fp2
    assert len(fp1) == 64  # sha256 hex


def test_fingerprint_changes_on_one_byte_difference():
    base = dict(tool="web_search_tool", agent="research_agent", task_id="t_1")
    fp_a = action_fingerprint(args={"query": "a"}, **base)
    fp_b = action_fingerprint(args={"query": "a "}, **base)
    assert fp_a != fp_b
