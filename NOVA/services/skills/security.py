"""
Security Skill

Answers IP-focused security questions using Security Center asset and finding data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from services.brain.intent import Intent
from services.skills.base import Skill, SkillContext


_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _extract_ipv4(text: str) -> str:
	match = _IP_RE.search(text or "")
	return match.group(0) if match else ""


def _contains_ip(value: Any, ip: str) -> bool:
	if isinstance(value, str):
		return ip in value
	if isinstance(value, dict):
		return any(_contains_ip(item, ip) for item in value.values())
	if isinstance(value, list):
		return any(_contains_ip(item, ip) for item in value)
	return False


def _risk_rank(risk: str) -> int:
	order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
	return order.get(str(risk or "").lower(), 0)


class SecuritySkill(Skill):
	@property
	def name(self) -> str:
		return "security"

	def can_handle(self, ctx: SkillContext) -> bool:
		text = (ctx.message or "").lower()
		has_ip = bool(_extract_ipv4(text))

		ip_os_keywords = (
			"operating system",
			"what os",
			"which os",
			"os of",
			"security finding",
			"security findings",
			"risk on",
			"findings on",
			"for this ip",
			"of this ip",
			"that ip",
		)

		if has_ip and any(keyword in text for keyword in ip_os_keywords):
			return True

		if has_ip and ctx.intent == Intent.SECURITY_SCAN:
			return True

		return False

	def execute(self, ctx: SkillContext) -> dict:
		from packages.registry import registry

		message = ctx.message or ""
		ip = _extract_ipv4(message)
		if not ip:
			return {
				"action": "security_lookup",
				"intent": ctx.intent.value,
				"response": "Please provide a valid IPv4 address, for example 10.20.40.144.",
			}

		assets = registry.security_center.list_assets()
		findings = registry.security_center.list_findings()

		matching_assets = [
			item for item in assets
			if isinstance(item, dict) and str(item.get("ip") or "").strip() == ip
		]
		matching_assets.sort(
			key=lambda item: str(item.get("last_seen") or ""),
			reverse=True,
		)

		ip_findings: List[Dict[str, Any]] = []
		for finding in findings:
			if not isinstance(finding, dict):
				continue
			haystacks: Iterable[Any] = (
				finding.get("title"),
				finding.get("summary"),
				finding.get("evidence"),
			)
			if any(_contains_ip(value, ip) for value in haystacks):
				ip_findings.append(finding)

		ip_findings.sort(
			key=lambda finding: (
				_risk_rank(str(finding.get("risk") or "low")),
				float(finding.get("confidence", 0.0) or 0.0),
			),
			reverse=True,
		)

		if not matching_assets and not ip_findings:
			return {
				"action": "security_lookup",
				"intent": ctx.intent.value,
				"response": (
					f"I do not have data for {ip} yet. "
					"Run discovery/pull again, then ask me for OS or findings on that IP."
				),
			}

		lines: List[str] = [f"Security view for {ip}:"]
		if matching_assets:
			asset = matching_assets[0]
			os_name = str(asset.get("os_name") or asset.get("os_hint") or "Unknown")
			confidence = float(asset.get("os_confidence", 0.0) or 0.0)
			confidence_pct = int(round(max(0.0, min(1.0, confidence)) * 100))
			lines.append(
				f"OS: {os_name} (confidence {confidence_pct}%), risk: {asset.get('risk_level', 'low')}, exposure: {asset.get('exposure_score', 0)}."
			)
			lines.append(
				f"Host: {asset.get('hostname') or 'unresolved'}, open ports: {', '.join(str(port) for port in (asset.get('open_ports') or [])) or 'none'}."
			)

		if ip_findings:
			lines.append(f"Findings linked to {ip}: {len(ip_findings)}")
			for item in ip_findings[:5]:
				lines.append(f"- [{str(item.get('risk') or 'low').upper()}] {item.get('title', 'Untitled finding')}")
		else:
			lines.append("No direct findings currently linked to this IP.")

		return {
			"action": "security_lookup",
			"intent": ctx.intent.value,
			"data": {
				"ip": ip,
				"asset_count": len(matching_assets),
				"finding_count": len(ip_findings),
			},
			"response": "\n".join(lines),
		}
