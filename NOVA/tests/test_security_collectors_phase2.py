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


def test_sbom_cyclonedx_document_shape():
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "sbom.py",
        "collector_sbom_module",
    )
    doc = module.build_cyclonedx_document([
        {"type": "library", "name": "openssl", "version": "3.0.2", "purl": "pkg:deb/openssl@3.0.2"}
    ])
    assert doc["bomFormat"] == "CycloneDX"
    assert doc["specVersion"] == "1.6"
    assert isinstance(doc.get("components"), list)


def test_cbom_key_metadata_does_not_expose_private_key_body(tmp_path: Path):
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "cbom.py",
        "collector_cbom_module",
    )

    key_file = tmp_path / "id_test_key"
    key_file.write_text("-----BEGIN PRIVATE KEY-----\nVERY_SECRET_KEY_MATERIAL\n-----END PRIVATE KEY-----\n")
    meta = module.inspect_key_metadata(key_file)

    assert isinstance(meta, dict)
    assert "public_fingerprint_sha256" in meta
    assert "encrypted" in meta
    assert "VERY_SECRET_KEY_MATERIAL" not in str(meta)


def test_hbom_cpu_vulnerability_parser(tmp_path: Path):
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "hbom.py",
        "collector_hbom_module",
    )

    vuln_dir = tmp_path / "vuln"
    vuln_dir.mkdir(parents=True)
    (vuln_dir / "spectre_v2").write_text("Mitigation: Full generic retpoline")
    parsed = module.parse_cpu_vulnerabilities(vuln_dir)

    assert parsed["spectre_v2"].startswith("Mitigation")
