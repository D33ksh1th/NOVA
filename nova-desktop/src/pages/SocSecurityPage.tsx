import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Database, FileCode2, GitBranch, KeyRound, Loader2, Microchip, Network, Target } from "lucide-react";

import { apiSecurityAgents, apiSecurityAssets, apiSecurityFindings } from "@/services/api";
import type { SecurityAgentRecord, SecurityAsset, SecurityFinding, SecurityBomHashes, SecurityCorrelationTelemetry, SecurityOtIdentityTelemetry } from "@/types";

export function SocSecurityPage() {
  const [agents, setAgents] = useState<SecurityAgentRecord[]>([]);
  const [assets, setAssets] = useState<SecurityAsset[]>([]);
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [agentRes, assetsRes, findingsRes] = await Promise.all([
          apiSecurityAgents(),
          apiSecurityAssets(),
          apiSecurityFindings(),
        ]);
        if (cancelled) return;
        setAgents(agentRes.agents || []);
        setAssets(assetsRes.assets || []);
        setFindings(findingsRes.findings || []);
      } catch (ex) {
        if (!cancelled) {
          setError(ex instanceof Error ? ex.message : "Failed to load SOC telemetry");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const primaryAgent = agents[0] || null;
  const telemetry = primaryAgent?.telemetry || {};
  const bomHashes = (telemetry.bom_hashes || {}) as SecurityBomHashes;
  const correlation = (telemetry.correlation || {}) as SecurityCorrelationTelemetry;
  const otIdentity = (telemetry.ot_identity || {}) as SecurityOtIdentityTelemetry;

  const livePillars = useMemo(() => {
    const sbomCount = Number((telemetry.sbom as { components?: unknown[] } | undefined)?.components?.length || 0);
    const cbom = telemetry.cbom as { certificates?: unknown[]; keys?: unknown[] } | undefined;
    const hbom = telemetry.hbom as { cpu_vulnerabilities?: Record<string, string>; dmi?: Record<string, string> } | undefined;
    return [
      {
        id: "SBOM",
        icon: <FileCode2 size={16} />,
        title: "Software Bill of Materials",
        summary: `${sbomCount || 0} components in current document`,
        points: [
          `Hash: ${shortHash(bomHashes.sbom)}`,
          `Queued findings tied to software: ${findings.filter((item) => item.tags.includes("patching") || item.tags.includes("packages")).length}`,
          `Asset inventory available: ${assets.length}`,
        ],
      },
      {
        id: "CBOM",
        icon: <KeyRound size={16} />,
        title: "Cryptographic Bill of Materials",
        summary: `${Number(cbom?.certificates?.length || 0)} certificates, ${Number(cbom?.keys?.length || 0)} key records`,
        points: [
          `Hash: ${shortHash(bomHashes.cbom)}`,
          `Crypto-related findings: ${findings.filter((item) => item.tags.includes("crypto") || item.tags.includes("tls")).length}`,
          `Correlation queue items: ${Number(correlation.queue_size || 0)}`,
        ],
      },
      {
        id: "HBOM",
        icon: <Microchip size={16} />,
        title: "Hardware Bill of Materials",
        summary: `${Object.keys(hbom?.cpu_vulnerabilities || {}).length} CPU vulnerability entries parsed`,
        points: [
          `Hash: ${shortHash(bomHashes.hbom)}`,
          `DMI vendor: ${String(hbom?.dmi?.manufacturer || "unknown")}`,
          `Discovered assets: ${assets.length}`,
        ],
      },
    ];
  }, [telemetry, bomHashes.sbom, bomHashes.cbom, bomHashes.hbom, findings, assets.length, correlation.queue_size]);

  const priorityStages = useMemo(() => {
    const queue = correlation.queue || [];
    return [
      { label: "KEV", value: queue.filter((item) => item.kev).length },
      { label: "EPSS > 0.1", value: queue.filter((item) => Number(item.epss || 0) > 0.1).length },
      { label: "Reachable", value: queue.filter((item) => item.reachable).length },
      { label: "Cross-Zone", value: queue.filter((item) => item.cross_zone_exposed).length },
      { label: "Queued", value: Number(correlation.queue_size || 0) },
    ];
  }, [correlation]);

  const dataModel = [
    ["asset count", String(assets.length)],
    ["agent count", String(agents.length)],
    ["finding count", String(findings.length)],
    ["queue size", String(correlation.queue_size || 0)],
  ];

  const delivery = [
    `OT mode: ${String(otIdentity.mode || "passive_only")}`,
    `DNP3 policy: ${String(otIdentity.dnp3_mode || "passive_only")}`,
    `Circuit breaker: ${otIdentity.circuit_breaker_tripped ? "tripped" : "clear"}`,
    `OT records this window: ${Number(otIdentity.results?.length || 0)}`,
  ];

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 bg-[radial-gradient(circle_at_top,rgba(251,191,36,0.09),transparent_42%)]">
      <header>
        <p className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-amber-300">
          SOC Design
        </p>
        <h2 className="font-display text-2xl font-bold text-text-primary mt-1">Security Enrichment Program Dashboard</h2>
        <p className="text-text-muted text-sm mt-2 max-w-5xl">
          Live program view for SBOM, CBOM, HBOM, OT identity, and prioritization. This page now reflects current agent telemetry instead of static architecture-only content.
        </p>
      </header>

      {error && (
        <div className="rounded-2xl border border-red-500/25 bg-red-500/10 p-4 text-sm text-red-200 inline-flex items-center gap-2">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {loading && (
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-200 inline-flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" />
          Loading SOC telemetry...
        </div>
      )}

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {livePillars.map((pillar) => (
          <article key={pillar.id} className="rounded-2xl border border-border bg-bg-secondary p-4">
            <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
              {pillar.icon}
              {pillar.title}
            </div>
            <p className="text-xs text-amber-300 mt-1">{pillar.id}</p>
            <p className="text-xs text-text-muted mt-2">{pillar.summary}</p>
            <div className="mt-3 space-y-2">
              {pillar.points.map((point) => (
                <p key={point} className="text-xs text-text-muted rounded-lg border border-border bg-bg-card px-3 py-2">
                  {point}
                </p>
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <article className="rounded-2xl border border-border bg-bg-secondary p-4">
          <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
            <Target size={16} />
            Priority Funnel
          </div>
          <p className="text-xs text-text-muted mt-1">Live queue uses KEV/EPSS plus reachability and cross-zone exposure.</p>
          <div className="mt-3 space-y-2">
            {priorityStages.map((item, idx) => (
              <div key={item.label} className="rounded-xl border border-border bg-bg-card p-3 flex items-center justify-between gap-3">
                <span className="text-xs text-text-primary font-medium">{item.label}</span>
                <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">{item.value} item{item.value === 1 ? "" : "s"} / Stage {idx + 1}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-border bg-bg-secondary p-4">
          <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
            <Database size={16} />
            Data Model
          </div>
          <div className="mt-3 overflow-auto rounded-xl border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-bg-elevated text-text-muted uppercase tracking-[0.12em]">
                <tr>
                  <th className="px-3 py-2">Metric</th>
                  <th className="px-3 py-2">Value</th>
                </tr>
              </thead>
              <tbody>
                {dataModel.map((row) => (
                  <tr key={row[0]} className="border-t border-border">
                    <td className="px-3 py-2 text-text-primary font-medium">{row[0]}</td>
                    <td className="px-3 py-2 text-text-muted">{row[1]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="rounded-2xl border border-border bg-bg-secondary p-4">
        <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
          <GitBranch size={16} />
          Live Delivery Shape
        </div>
        <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-2">
          {delivery.map((item) => (
            <p key={item} className="text-xs text-text-muted rounded-xl border border-border bg-bg-card px-3 py-2">
              {item}
            </p>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-bg-secondary p-4">
        <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
          <Network size={16} />
          Queue Detail
        </div>
        <div className="mt-3 space-y-2 max-h-[280px] overflow-auto pr-1">
          {(correlation.queue || []).length === 0 ? (
            <p className="text-xs text-text-muted rounded-xl border border-border bg-bg-card px-3 py-3">No prioritized items in the current telemetry window.</p>
          ) : (
            (correlation.queue || []).map((item, index) => (
              <div key={`${item.vuln_id}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold text-text-primary">{item.vuln_id || "Unknown vuln"}</p>
                    <p className="text-xs text-text-muted mt-1">{item.component || "unknown component"} on {item.asset || "unknown asset"}</p>
                  </div>
                  <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">EPSS {Number(item.epss || 0).toFixed(2)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function shortHash(value?: string) {
  if (!value) return "No hash yet";
  if (value.length <= 16) return value;
  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}
