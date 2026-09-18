"""Anomaly detection engine — layered, cheapest first.

Layer 1: Statistical baseline (EWMA + robust z-score per metric)
Layer 2: ML multivariate (Isolation Forest for correlated signals)
Layer 3: LLM triage (only anomalies surviving L1-L2 reach the LLM)

Suppression: fingerprint dedup with configurable auto-suppress.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from packages.common import logger
from packages.events import bus


# ── Layer 1: Statistical Baseline ───────────────────────────────

@dataclass
class MetricBaseline:
    """EWMA + MAD-based robust z-score for a single metric."""
    mean: float = 0.0
    mad: float = 1.0  # median absolute deviation
    count: int = 0
    alpha: float = 0.05  # EWMA smoothing factor
    last_value: float = 0.0
    last_updated: float = 0.0

    def update(self, value: float) -> float:
        """Update baseline and return z-score for this observation."""
        self.count += 1
        self.last_value = value
        self.last_updated = time.time()

        if self.count <= 5:
            # Warmup: accumulate without scoring
            self.mean = (self.mean * (self.count - 1) + value) / self.count
            self.mad = max(0.1, abs(value - self.mean))
            return 0.0

        # EWMA update
        old_mean = self.mean
        self.mean = self.alpha * value + (1 - self.alpha) * self.mean
        self.mad = self.alpha * abs(value - old_mean) + (1 - self.alpha) * self.mad

        # Robust z-score (MAD-based)
        if self.mad < 0.001:
            return 0.0
        z = abs(value - self.mean) / (self.mad * 1.4826)  # 1.4826 = consistency constant
        return z


class StatisticalDetector:
    """Per-metric EWMA baselines with robust z-scoring."""

    ANOMALY_THRESHOLD = 3.0  # z-score above which we flag

    def __init__(self):
        self._baselines: Dict[str, MetricBaseline] = defaultdict(MetricBaseline)

    def observe(self, metric_name: str, value: float) -> Optional[Dict[str, Any]]:
        baseline = self._baselines[metric_name]
        z = baseline.update(value)

        if z > self.ANOMALY_THRESHOLD and baseline.count > 10:
            return {
                "metric": metric_name,
                "value": round(value, 2),
                "baseline_mean": round(baseline.mean, 2),
                "z_score": round(z, 2),
                "observations": baseline.count,
                "layer": 1,
            }
        return None

    def observe_telemetry(self, telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract and observe standard metrics from agent telemetry."""
        anomalies = []

        # CPU
        cpu = telemetry.get("cpu_percent")
        if cpu is not None:
            a = self.observe("cpu_percent", float(cpu))
            if a:
                anomalies.append(a)

        # Memory
        mem = telemetry.get("memory_percent")
        if mem is not None:
            a = self.observe("memory_percent", float(mem))
            if a:
                anomalies.append(a)

        # Connection count
        conns = telemetry.get("connections", {})
        if isinstance(conns, dict):
            est = conns.get("established", 0)
            a = self.observe("established_connections", float(est))
            if a:
                anomalies.append(a)

            remote = conns.get("unique_remote_hosts", 0)
            a = self.observe("unique_remote_hosts", float(remote))
            if a:
                anomalies.append(a)

        # Process count
        proc_count = telemetry.get("process_count")
        if proc_count is not None:
            a = self.observe("process_count", float(proc_count))
            if a:
                anomalies.append(a)

        # Listening ports count
        ports = telemetry.get("listening_ports", [])
        if isinstance(ports, list):
            a = self.observe("listening_port_count", float(len(ports)))
            if a:
                anomalies.append(a)

        return anomalies

    def baseline_summary(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "mean": round(b.mean, 2),
                "mad": round(b.mad, 2),
                "count": b.count,
                "last_value": round(b.last_value, 2),
            }
            for name, b in self._baselines.items()
        }


# ── Layer 2: ML Multivariate (Isolation Forest) ─────────────────

class MultivariateDetector:
    """Isolation Forest for correlated anomalies across metrics."""

    def __init__(self):
        self._model = None
        self._feature_names = ["cpu_percent", "memory_percent", "established_connections", "unique_remote_hosts", "process_count", "listening_port_count"]
        self._history: List[List[float]] = []
        self._fitted = False

    def _extract_features(self, telemetry: Dict[str, Any]) -> List[float]:
        conns = telemetry.get("connections", {}) if isinstance(telemetry.get("connections"), dict) else {}
        ports = telemetry.get("listening_ports", []) if isinstance(telemetry.get("listening_ports"), list) else []
        return [
            float(telemetry.get("cpu_percent", 0)),
            float(telemetry.get("memory_percent", 0)),
            float(conns.get("established", 0)),
            float(conns.get("unique_remote_hosts", 0)),
            float(telemetry.get("process_count", 0)),
            float(len(ports)),
        ]

    def observe(self, telemetry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        features = self._extract_features(telemetry)
        self._history.append(features)

        # Need at least 50 observations to fit
        if len(self._history) < 50:
            return None

        # Fit/refit every 100 observations
        if not self._fitted or len(self._history) % 100 == 0:
            self._fit()

        if self._model is None:
            return None

        try:
            import numpy as np
            score = self._model.decision_function(np.array([features]))[0]
            pred = self._model.predict(np.array([features]))[0]
            if pred == -1:  # anomaly
                return {
                    "features": dict(zip(self._feature_names, [round(f, 1) for f in features])),
                    "isolation_score": round(float(score), 4),
                    "layer": 2,
                }
        except Exception as ex:
            logger.warning(f"MultivariateDetector: predict failed: {ex}")
        return None

    def _fit(self) -> None:
        try:
            from sklearn.ensemble import IsolationForest
            import numpy as np
            data = np.array(self._history[-500:])
            self._model = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
            self._model.fit(data)
            self._fitted = True
            logger.info(f"MultivariateDetector: fitted on {len(data)} observations")
        except ImportError:
            logger.info("MultivariateDetector: sklearn not available, skipping Layer 2")
            self._model = None
        except Exception as ex:
            logger.warning(f"MultivariateDetector: fit failed: {ex}")


# ── Layer 3: LLM Triage ─────────────────────────────────────────

class LLMTriageEngine:
    """Send surviving anomalies to LLM for explanation."""

    def explain(self, anomaly: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            from packages.config import settings
            from services.llm import LLMClient, LLMRequest

            prompt = self._build_prompt(anomaly, context)
            client = LLMClient()
            response = client.generate(LLMRequest(
                prompt=prompt,
                model=settings.CHAT_MODEL,
            ))
            return {
                "explanation": response.text,
                "anomaly": anomaly,
                "layer": 3,
            }
        except Exception as ex:
            logger.warning(f"LLMTriageEngine: explain failed: {ex}")
            return None

    def _build_prompt(self, anomaly: Dict[str, Any], context: Dict[str, Any]) -> str:
        return f"""You are a security analyst AI. Analyze this anomaly and explain it concisely.

ANOMALY:
{anomaly}

CONTEXT (last 24h):
- Host: {context.get('hostname', 'unknown')}
- Platform: {context.get('platform', 'unknown')}
- Normal baseline mean: {anomaly.get('baseline_mean', 'N/A')}

Respond with EXACTLY this structure (no extra text):
1. WHAT HAPPENED: (one sentence)
2. WHY IT MATTERS: (one sentence)
3. RECOMMENDED ACTION: (one sentence)
4. REQUIRES USER INPUT: (yes/no and what)"""


# ── Suppression ──────────────────────────────────────────────────

class AnomalySuppressor:
    """Dedup and auto-suppress repeated anomalies."""

    def __init__(self, suppress_after: int = 2, window_seconds: float = 3600):
        self._seen: Dict[str, Dict[str, Any]] = {}
        self._suppress_after = suppress_after
        self._window = window_seconds

    def fingerprint(self, anomaly: Dict[str, Any]) -> str:
        key = f"{anomaly.get('metric', '')}{anomaly.get('layer', '')}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def should_suppress(self, anomaly: Dict[str, Any]) -> bool:
        fp = self.fingerprint(anomaly)
        now = time.time()

        if fp in self._seen:
            entry = self._seen[fp]
            if now - entry["first_seen"] < self._window:
                entry["count"] += 1
                if entry["count"] > self._suppress_after:
                    return True
            else:
                self._seen[fp] = {"first_seen": now, "count": 1}
        else:
            self._seen[fp] = {"first_seen": now, "count": 1}
        return False


# ── Orchestrator ─────────────────────────────────────────────────

class AnomalyDetectionEngine:
    """Orchestrates all three layers + suppression."""

    def __init__(self):
        self.layer1 = StatisticalDetector()
        self.layer2 = MultivariateDetector()
        self.layer3 = LLMTriageEngine()
        self.suppressor = AnomalySuppressor()
        self._anomaly_count = 0

    def process_telemetry(self, telemetry: Dict[str, Any], context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """Run telemetry through all detection layers."""
        results = []

        # Layer 1: statistical
        l1_anomalies = self.layer1.observe_telemetry(telemetry)
        for a in l1_anomalies:
            if self.suppressor.should_suppress(a):
                continue
            a["title"] = f"Statistical anomaly: {a['metric']} z={a['z_score']}"
            a["risk"] = "high" if a["z_score"] > 5 else "medium"
            results.append(a)

        # Layer 2: multivariate
        l2 = self.layer2.observe(telemetry)
        if l2 and not self.suppressor.should_suppress(l2):
            l2["title"] = "Multivariate anomaly: correlated metric deviation"
            l2["risk"] = "high"
            results.append(l2)

        # Layer 3: LLM triage (only for high-severity L1/L2 anomalies)
        for anomaly in results:
            if anomaly.get("risk") == "high" and anomaly.get("layer") in (1, 2):
                explanation = self.layer3.explain(anomaly, context or {})
                if explanation:
                    anomaly["explanation"] = explanation.get("explanation", "")

        # Publish to event bus
        for anomaly in results:
            self._anomaly_count += 1
            severity = 3 if anomaly.get("risk") == "high" else 2
            bus.emit(
                "nova.security.anomaly",
                source="anomaly-engine",
                payload=anomaly,
                severity=severity,
                requires_speech=severity >= 3,
            )

        return results

    def stats(self) -> Dict[str, Any]:
        return {
            "baselines": self.layer1.baseline_summary(),
            "l2_observations": len(self.layer2._history),
            "l2_fitted": self.layer2._fitted,
            "total_anomalies": self._anomaly_count,
        }
