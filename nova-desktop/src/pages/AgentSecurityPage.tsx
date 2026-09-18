import { useEffect, useMemo, useState } from "react";
import { ShieldAlert, Network, Radar, Lock, Server, Activity, Loader2, AlertTriangle } from "lucide-react";

import { apiSecurityAgents } from "@/services/api";
import type { SecurityAgentRecord, SecurityHostDiscovery, SecurityOtIdentityTelemetry } from "@/types";

const BLOCKERS = [
  {
    issue: "Pull API exposed on 0.0.0.0 with optional empty token",
    impact: "Unauthenticated subnet, port, and persistence telemetry disclosure",
    action: "Default bind to 127.0.0.1, fail closed without token, require mTLS for remote pull",
  },
  {
    issue: "Token comparison uses direct equality",
    impact: "Token timing side-channel",
    action: "Use constant-time compare with compare_digest",
  },
  {
    issue: "No TLS pinning for push channel",
    impact: "Token and telemetry interception risk",
    action: "Enable pinned CA verification and optional client certificate",
  },
  {
    issue: "Discovery scans entire /24 concurrently",
    impact: "High risk in OT or medical VLANs",
    action: "Require CIDR allowlist plus denylist, apply zone-based scan profiles",
  },
  {
    issue: "No durable local spool",
    impact: "Data loss during collector outages",
    action: "Add SQLite WAL ring-buffer with replay on reconnect",
  },
  {
    issue: "Agent runtime overly privileged",
    impact: "Host compromise blast radius",
    action: "Use least-privilege caps and systemd hardening directives",
  },
];

const TIERS = [
  {
    tier: "Tier 0",
    mode: "Passive",
    scope: "All zones",
    details: "ARP/NDP cache, DHCP fingerprints, mDNS, LLDP/CDP, SSDP, flow observation",
  },
  {
    tier: "Tier 1",
    mode: "Light active",
    scope: "IT ranges only",
    details: "Adaptive TCP connect scan, jittered sequential probing, rate-limited",
  },
  {
    tier: "Tier 2",
    mode: "Deep active",
    scope: "IT ranges scheduled windows",
    details: "TLS/SSH handshakes, HTTP fingerprinting, SNMP metadata, SMB/RDP/LDAP facts",
  },
  {
    tier: "Tier 3",
    mode: "Credentialed",
    scope: "Approved hosts",
    details: "SSH/WinRM/SNMPv3/k8s/vSphere data with source-of-truth priority over inference",
  },
];

const OT_PROTOCOLS = [
  ["EtherNet/IP", "UDP 44818", "ListIdentity"],
  ["BACnet", "UDP 47808", "Who-Is and I-Am"],
  ["PROFINET", "L2", "DCP Identify All"],
  ["OPC UA", "4840", "GetEndpoints"],
  ["Modbus/TCP", "502", "FC43/MEI device identification only"],
  ["S7comm", "102", "COTP connect and SZL read"],
];

const RUNTIME_GUARDS = [
  "Pull API requires token and rejects insecure wildcard bind without TLS.",
  "Snapshot payloads are signed with Ed25519 before they leave the agent.",
  "Push mode requires HTTPS and a pinned CA bundle.",
  "SQLite WAL spool buffers outbound payloads during collector outages.",
  "Every active packet is audit logged with target, port, auth ref, and approver.",
];

type AgentTab = "hardening" | "discovery" | "ot" | "runtime";

export function AgentSecurityPage() {
  const [activeTab, setActiveTab] = useState<AgentTab>("hardening");
  const [agent, setAgent] = useState<SecurityAgentRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await apiSecurityAgents();
        if (cancelled) return;
        setAgent(result.agents?.[0] || null);
      } catch (ex) {
        if (!cancelled) {
          setError(ex instanceof Error ? ex.message : "Failed to load agent telemetry");
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

  const telemetry = agent?.telemetry || {};
  const hostDiscovery = (telemetry.host_discovery || {}) as SecurityHostDiscovery;
  const otIdentity = (telemetry.ot_identity || {}) as SecurityOtIdentityTelemetry;
  const hasBomHashes = Boolean((telemetry.bom_hashes as Record<string, unknown> | undefined)?.sbom || (telemetry.bom_hashes as Record<string, unknown> | undefined)?.cbom || (telemetry.bom_hashes as Record<string, unknown> | undefined)?.hbom);
  const runtimeSignals = useMemo(() => {
    return {
      hostname: String(agent?.hostname || "No agent"),
      platform: String(agent?.platform || "Unknown"),
      lastSeen: String(agent?.last_seen || "Unavailable"),
      discoveryEnabled: hostDiscovery.enabled ? "Enabled" : `Disabled${hostDiscovery.reason ? ` (${hostDiscovery.reason})` : ""}`,
      discoveredCount: String(hostDiscovery.discovered_count || 0),
      subnet: String(hostDiscovery.subnet || "Unavailable"),
      otMode: String(otIdentity.mode || "passive_only"),
      otRecords: String((otIdentity.results || []).length || 0),
      dnp3Mode: String(otIdentity.dnp3_mode || "passive_only"),
      bomState: hasBomHashes ? "Present" : "Not stored",
      correlationState: telemetry.correlation ? "Present" : "Not stored",
      spoolState: "SQLite WAL configured",
      signingState: telemetry.signature || telemetry.signature_key_id ? "Signed payload metadata present" : "Snapshot signed at agent runtime",
    };
  }, [agent, hostDiscovery.enabled, hostDiscovery.reason, hostDiscovery.discovered_count, hostDiscovery.subnet, otIdentity.mode, otIdentity.results, otIdentity.dnp3_mode, hasBomHashes, telemetry.correlation, telemetry.signature, telemetry.signature_key_id]);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.09),transparent_42%)]">
      <header>
        <p className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-[#38bdf8]">
          Agent Architecture
        </p>
        <h2 className="font-display text-2xl font-bold text-text-primary mt-1">Security Agent Hardening and Discovery Safety</h2>
        <p className="text-text-muted text-sm mt-2 max-w-5xl">
          This page tracks the agent-side controls required before expanding SBOM/CBOM/HBOM and active discovery across mixed IT and OT estates.
        </p>
        <p className="text-text-muted text-xs mt-2">
          Live agent: {runtimeSignals.hostname} | Platform: {runtimeSignals.platform} | Last seen: {runtimeSignals.lastSeen}
        </p>
      </header>

      {error && (
        <div className="rounded-2xl border border-red-500/25 bg-red-500/10 p-4 text-sm text-red-200 inline-flex items-center gap-2">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {loading && (
        <div className="rounded-2xl border border-sky-500/25 bg-sky-500/10 p-4 text-sm text-sky-200 inline-flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" />
          Loading agent runtime telemetry...
        </div>
      )}

      <div className="inline-flex flex-wrap gap-2 rounded-2xl border border-border bg-bg-secondary p-2">
        {([
          ["hardening", "Hardening"],
          ["discovery", "Discovery"],
          ["ot", "OT Policy"],
          ["runtime", "Runtime"],
        ] as Array<[AgentTab, string]>).map(([tabId, label]) => (
          <button
            key={tabId}
            onClick={() => setActiveTab(tabId)}
            className={activeTab === tabId
              ? "px-3 py-2 rounded-xl text-sm border border-sky-500/30 bg-sky-500/10 text-sky-300"
              : "px-3 py-2 rounded-xl text-sm border border-border bg-bg-card text-text-muted hover:text-text-primary transition"}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "hardening" && (
      <div className="space-y-4">
      <section className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        <MetricCard icon={<Lock size={16} />} title="Payload Signing" value={runtimeSignals.signingState} note="Ed25519 snapshot signing is enforced in the current agent path" />
        <MetricCard icon={<Server size={16} />} title="Spool" value={runtimeSignals.spoolState} note="Outbound payload buffering remains enabled" />
        <MetricCard icon={<Activity size={16} />} title="BOM State" value={runtimeSignals.bomState} note="Shows whether BOM hashes are visible in stored telemetry" />
        <MetricCard icon={<ShieldAlert size={16} />} title="Correlation" value={runtimeSignals.correlationState} note="Shows whether correlation queue data reached the UI path" />
      </section>

      <section className="rounded-2xl border border-red-500/25 bg-red-500/10 p-4">
        <div className="flex items-center gap-2 text-red-200 font-semibold text-sm">
          <ShieldAlert size={16} />
          Pre-Expansion Blockers
        </div>
        <div className="mt-3 space-y-3">
          {BLOCKERS.map((row) => (
            <div key={row.issue} className="rounded-xl border border-border bg-bg-secondary p-3">
              <p className="text-sm font-semibold text-text-primary">{row.issue}</p>
              <p className="text-xs text-red-200/90 mt-1">Risk: {row.impact}</p>
              <p className="text-xs text-text-muted mt-1">Fix: {row.action}</p>
            </div>
          ))}
        </div>
      </section>
      </div>
      )}

      {activeTab === "discovery" && (
      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <article className="rounded-2xl border border-border bg-bg-secondary p-4">
          <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
            <Radar size={16} />
            Discovery Tiers
          </div>
          <div className="mt-3 space-y-2">
            {TIERS.map((tier) => (
              <div key={tier.tier} className="rounded-xl border border-border bg-bg-card p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-text-primary">{tier.tier}</p>
                  <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">{tier.mode}</span>
                </div>
                <p className="text-xs text-sky-300 mt-1">Scope: {tier.scope}</p>
                <p className="text-xs text-text-muted mt-1">{tier.details}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-border bg-bg-secondary p-4">
          <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
            <Network size={16} />
            Discovery Controls
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <RuntimeRow label="Discovery" value={runtimeSignals.discoveryEnabled} />
            <RuntimeRow label="Subnet" value={runtimeSignals.subnet} />
            <RuntimeRow label="Discovered" value={runtimeSignals.discoveredCount} />
          </div>
          <div className="mt-3 space-y-2 text-xs text-text-muted">
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">Discovery refuses to run when `SCAN_ALLOW_CIDRS` is unset.</p>
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">Deny CIDRs are evaluated first and always win.</p>
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">Unknown or medical-like zones are clamped to OT-equivalent ceilings.</p>
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">Active probe authorization is mandatory before any non-passive host discovery.</p>
          </div>
        </article>
      </section>
      )}

      {activeTab === "ot" && (
      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <article className="rounded-2xl border border-border bg-bg-secondary p-4">
          <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
            <Network size={16} />
            OT Safe Protocol Identity
          </div>
          <div className="mt-3 overflow-auto rounded-xl border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-bg-elevated text-text-muted uppercase tracking-[0.12em]">
                <tr>
                  <th className="px-3 py-2">Protocol</th>
                  <th className="px-3 py-2">Port</th>
                  <th className="px-3 py-2">Safe Primitive</th>
                </tr>
              </thead>
              <tbody>
                {OT_PROTOCOLS.map((row) => (
                  <tr key={row[0]} className="border-t border-border">
                    <td className="px-3 py-2 text-text-primary font-medium">{row[0]}</td>
                    <td className="px-3 py-2 text-text-secondary">{row[1]}</td>
                    <td className="px-3 py-2 text-text-muted">{row[2]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="rounded-2xl border border-border bg-bg-secondary p-4">
          <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
            <ShieldAlert size={16} />
            OT Safeguards
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <RuntimeRow label="OT Mode" value={runtimeSignals.otMode} />
            <RuntimeRow label="DNP3" value={runtimeSignals.dnp3Mode} />
            <RuntimeRow label="Probe Records" value={runtimeSignals.otRecords} />
          </div>
          <div className="mt-3 space-y-2 text-xs text-text-muted">
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">Passive by default. Active OT identity requires a signed, time-boxed authorization record.</p>
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">One connection per device, sequential only, with at least 1 second between devices.</p>
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">Latency circuit breaker aborts the run if any target exceeds the configured threshold.</p>
            <p className="rounded-xl border border-border bg-bg-card px-3 py-2">DNP3 remains passive-only and is never actively probed.</p>
          </div>
        </article>
      </section>
      )}

      {activeTab === "runtime" && (
      <div className="space-y-4">
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <MetricCard icon={<Lock size={16} />} title="Transport Security" value="Pinned TLS + mTLS" note="No plaintext telemetry channels" />
        <MetricCard icon={<Server size={16} />} title="Execution Safety" value="Least Privilege Runtime" note="NoNewPrivileges + strict service sandbox" />
        <MetricCard icon={<Activity size={16} />} title="Auditability" value="Per-Probe Audit Trail" note="Target, port, time, auth reference, outcome" />
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        <RuntimeRow label="Host" value={runtimeSignals.hostname} />
        <RuntimeRow label="Platform" value={runtimeSignals.platform} />
        <RuntimeRow label="Last Seen" value={runtimeSignals.lastSeen} />
        <RuntimeRow label="Correlation" value={runtimeSignals.correlationState} />
      </section>

      <section className="rounded-2xl border border-border bg-bg-secondary p-4">
        <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
          <Server size={16} />
          Runtime Safeguards
        </div>
        <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-2">
          {RUNTIME_GUARDS.map((item) => (
            <p key={item} className="text-xs text-text-muted rounded-xl border border-border bg-bg-card px-3 py-2">
              {item}
            </p>
          ))}
        </div>
      </section>
      </div>
      )}
    </div>
  );
}

function RuntimeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-bg-card p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-text-muted font-mono">{label}</p>
      <p className="text-sm font-semibold text-text-primary mt-2 break-all">{value}</p>
    </div>
  );
}

function MetricCard({ icon, title, value, note }: { icon: React.ReactNode; title: string; value: string; note: string }) {
  return (
    <div className="rounded-2xl border border-border bg-bg-secondary p-4">
      <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
        {icon}
        {title}
      </div>
      <p className="text-lg font-bold text-sky-300 mt-2">{value}</p>
      <p className="text-xs text-text-muted mt-1">{note}</p>
    </div>
  );
}
