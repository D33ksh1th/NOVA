import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { clsx } from "clsx";
import {
  Activity,
  AlertTriangle,
  Clock3,
  Cpu,
  Loader2,
  Network,
  Package,
  RefreshCw,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  apiSecurityAgents,
  apiSecurityAssets,
  apiSecurityFindings,
  apiSecurityPull,
  apiSecurityScan,
  apiSecurityStatus,
  apiSecurityTimeline,
} from "@/services/api";
import type {
  SecurityAgentRecord,
  SecurityAsset,
  SecurityFinding,
  SecurityStatusResponse,
  SecurityTimelineEvent,
} from "@/types";

interface DiscoveryHost {
  ip: string;
  hostname?: string;
  open_ports?: number[];
  role?: string;
  hostType?: string;
  osHint?: string;
  osName?: string;
  exposureScore?: number;
  riskLevel?: string;
}

interface HostDiscovery {
  enabled?: boolean;
  interface?: string;
  self_ip?: string;
  subnet?: string;
  discovered_count?: number;
  discovered_hosts?: DiscoveryHost[];
  reason?: string;
}

interface PackagePosture {
  manager?: string;
  total_packages?: number;
  upgradable_count?: number;
  upgradable?: Array<{ package?: string; raw?: string }>;
}

interface ProcessTelemetryItem {
  pid?: number;
  ppid?: number;
  name?: string;
  user?: string;
  cpu_percent?: number;
  memory_percent?: number;
  exe?: string;
  cmdline?: string;
  status?: string;
  created_at?: number;
  threads?: number;
}

interface ListeningPortItem {
  ip?: string;
  port?: number;
  pid?: number;
}

interface MountedDriveItem {
  device?: string;
  mountpoint?: string;
  fstype?: string;
  opts?: string;
}

interface PersistenceTelemetry {
  launch_agents?: string[];
  systemd_units?: string[];
  systemd_timers?: string[];
  cron_entries?: string[];
  autostart_entries?: string[];
}

interface ConnectionDetailItem {
  local?: string;
  remote?: string;
  pid?: number;
  family?: string;
  type?: string;
  status?: string;
}

interface BomHashes {
  sbom?: string;
  cbom?: string;
  hbom?: string;
}

interface BomDocumentState {
  hash?: string;
  deferred?: boolean;
}

interface CorrelationQueueItem {
  vuln_id?: string;
  asset?: string;
  component?: string;
  severity?: string;
  reachable?: boolean;
  cross_zone_exposed?: boolean;
  epss?: number;
  kev?: boolean;
}

interface CorrelationTelemetry {
  queue_size?: number;
  queue?: CorrelationQueueItem[];
}

interface OtIdentityResult {
  protocol?: string;
  primitive?: string;
  target?: string;
  elapsed_ms?: number;
  auth_ref?: string;
  approver?: string;
  error?: string;
}

interface OtIdentityTelemetry {
  mode?: string;
  reason?: string;
  results?: OtIdentityResult[];
  circuit_breaker_tripped?: boolean;
  authorization?: {
    auth_ref?: string;
    approver?: string;
    ticket?: string;
  };
  dnp3_mode?: string;
}

interface BomDocuments {
  sbom?: {
    bomFormat?: string;
    specVersion?: string;
    components?: Array<{
      name?: string;
      version?: string;
      purl?: string;
      type?: string;
    }>;
    vulnerabilities?: Array<{ id?: string }>;
  };
  cbom?: {
    certificates?: Array<{
      path?: string;
      subject?: string;
      issuer?: string;
      not_after?: string;
      self_signed?: boolean;
      world_readable?: boolean;
    }>;
    keys?: Array<{
      path?: string;
      algorithm?: string;
      key_size?: number;
      mode?: string;
      encrypted?: boolean;
      public_fingerprint_sha256?: string;
    }>;
  };
  hbom?: {
    dmi?: Record<string, string>;
    cpu_vulnerabilities?: Record<string, string>;
  };
}

type SecurityTab = "overview" | "bom" | "ot" | "correlation" | "raw";

export function SecurityPage() {
  const savedAgentUrl = window.localStorage.getItem("nova.security.agent_url") || "http://10.20.40.144:3009";
  const [status, setStatus] = useState<SecurityStatusResponse | null>(null);
  const [agents, setAgents] = useState<SecurityAgentRecord[]>([]);
  const [assets, setAssets] = useState<SecurityAsset[]>([]);
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const [timeline, setTimeline] = useState<SecurityTimelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [pullAgentUrl, setPullAgentUrl] = useState(savedAgentUrl);
  const [pullToken, setPullToken] = useState("");
  const [pulling, setPulling] = useState(false);
  const [pullMessage, setPullMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SecurityTab>("overview");
  const loadInFlightRef = useRef(false);

  const loadAll = useCallback(async () => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      await apiSecurityScan().catch(() => undefined);
      const [statusRes, agentRes, assetsRes, findingsRes, timelineRes] = await Promise.all([
        apiSecurityStatus(),
        apiSecurityAgents(),
        apiSecurityAssets(),
        apiSecurityFindings(),
        apiSecurityTimeline(20),
      ]);
      setStatus(statusRes);
      setAgents(agentRes.agents || []);
      setAssets(assetsRes.assets || []);
      setFindings(findingsRes.findings || []);
      setTimeline(timelineRes.events || []);
      setLastSyncedAt(new Date().toISOString());
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Failed to load Security Center");
    } finally {
      setLoading(false);
      loadInFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    void loadAll();
    const onFocus = () => void loadAll();
    const onVisibility = () => {
      if (document.visibilityState === "visible") void loadAll();
    };
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadAll();
    }, 15000);

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [loadAll]);

  async function pullFromAgent() {
    const url = pullAgentUrl.trim();
    if (!url) {
      setPullMessage("Agent URL is required.");
      return;
    }

    setPulling(true);
    setPullMessage(null);
    try {
      const result = await apiSecurityPull({
        agent_url: url,
        token: pullToken.trim() || undefined,
        timeout: 45,
        verify_ssl: false,
      });
      window.localStorage.setItem("nova.security.agent_url", url);
      setPullMessage(`Pulled agent ${result.agent.agent_id} from ${result.pulled_from}`);
      await loadAll();
    } catch (ex) {
      setPullMessage(ex instanceof Error ? ex.message : "Failed to pull agent snapshot");
    } finally {
      setPulling(false);
    }
  }

  const primaryAgent = useMemo(() => {
    if (agents.length === 0) return null;
    const rank = (agent: SecurityAgentRecord) => {
      const ts = Date.parse(agent.last_seen || "") || 0;
      const telemetryObject = agent.telemetry || {};
      const telemetryWeight = Object.keys(telemetryObject).length;
      const hasBomHashes = Boolean((telemetryObject as Record<string, unknown>).bom_hashes);
      return ts + telemetryWeight + (hasBomHashes ? 1000 : 0);
    };
    return [...agents].sort((a, b) => rank(b) - rank(a))[0] || null;
  }, [agents]);

  const telemetry = (primaryAgent?.telemetry || {}) as Record<string, unknown>;
  const hostDiscovery = (telemetry.host_discovery || {}) as HostDiscovery;
  const packagePosture = (telemetry.packages || {}) as PackagePosture;
  const bomHashes = (telemetry.bom_hashes || {}) as BomHashes;
  const correlation = (telemetry.correlation || {}) as CorrelationTelemetry;
  const otIdentity = (telemetry.ot_identity || {}) as OtIdentityTelemetry;
  const sbomState = (telemetry.sbom || {}) as BomDocumentState;
  const cbomState = (telemetry.cbom || {}) as BomDocumentState;
  const hbomState = (telemetry.hbom || {}) as BomDocumentState;
  const bomDocuments = (telemetry.bom_documents || {}) as BomDocuments;
  const sbomDoc = (bomDocuments.sbom || ((telemetry.sbom && !sbomState.deferred) ? telemetry.sbom : undefined)) as BomDocuments["sbom"];
  const cbomDoc = (bomDocuments.cbom || ((telemetry.cbom && !cbomState.deferred) ? telemetry.cbom : undefined)) as BomDocuments["cbom"];
  const hbomDoc = (bomDocuments.hbom || ((telemetry.hbom && !hbomState.deferred) ? telemetry.hbom : undefined)) as BomDocuments["hbom"];
  const sbomDeferredOnly = Boolean(sbomState.deferred) && !sbomDoc;
  const cbomDeferredOnly = Boolean(cbomState.deferred) && !cbomDoc;
  const hbomDeferredOnly = Boolean(hbomState.deferred) && !hbomDoc;
  const hasAnyDeferredOnlyBom = sbomDeferredOnly || cbomDeferredOnly || hbomDeferredOnly;

  const processes = Array.isArray(telemetry.processes)
    ? (telemetry.processes as ProcessTelemetryItem[])
    : (Array.isArray(telemetry.top_processes) ? (telemetry.top_processes as ProcessTelemetryItem[]) : []);
  const listeningPorts = Array.isArray(telemetry.listening_ports) ? (telemetry.listening_ports as ListeningPortItem[]) : [];
  const mountedDrives = Array.isArray(telemetry.mounted_drives) ? (telemetry.mounted_drives as MountedDriveItem[]) : [];
  const persistence = (telemetry.persistence || {}) as PersistenceTelemetry;
  const loginSnapshot = Array.isArray(telemetry.login_snapshot) ? (telemetry.login_snapshot as string[]) : [];
  const connections = (telemetry.connections || {}) as { established?: number; unique_remote_hosts?: number };
  const connectionDetails = Array.isArray(telemetry.connection_details) ? (telemetry.connection_details as ConnectionDetailItem[]) : [];

  const hostRows = useMemo(() => {
    if (assets.length > 0) {
      return assets
        .filter((asset) => (asset.ip || "").trim() !== "")
        .map((asset) => ({
          ip: String(asset.ip || ""),
          hostname: String(asset.hostname || ""),
          osName: String(asset.os_name || asset.os_hint || "Unknown"),
          hostType: String(asset.host_type || "unknown"),
          openPorts: Array.isArray(asset.open_ports) ? asset.open_ports : [],
          riskLevel: String(asset.risk_level || "low"),
          exposureScore: Number(asset.exposure_score || 0),
          role: String(asset.role || ""),
        }));
    }
    return (hostDiscovery.discovered_hosts || []).map((node) => ({
      ip: String(node.ip || ""),
      hostname: String(node.hostname || ""),
      osName: String(node.osName || node.osHint || "Unknown"),
      hostType: String(node.hostType || "unknown"),
      openPorts: Array.isArray(node.open_ports) ? node.open_ports : [],
      riskLevel: String(node.riskLevel || "low"),
      exposureScore: Number(node.exposureScore || 0),
      role: String(node.role || ""),
    }));
  }, [assets, hostDiscovery.discovered_hosts]);

  const narrative = useMemo(() => {
    if (!primaryAgent) {
      return "No endpoint agent has checked in yet. Deploy the agent to a host and NOVA will start building a live security picture.";
    }
    const highOrCritical = findings.filter((finding) => finding.risk === "high" || finding.risk === "critical");
    const patchBacklog = Number(packagePosture.upgradable_count || 0);
    const discoveredCount = Math.max(Number(hostDiscovery.discovered_count || 0), hostRows.length);
    const hostname = primaryAgent.hostname;
    if (highOrCritical.length > 0) {
      return `${hostname} checked in with ${highOrCritical.length} elevated-risk finding${highOrCritical.length === 1 ? "" : "s"}. NOVA mapped ${discoveredCount} nearby hosts and sees ${patchBacklog} pending package updates.`;
    }
    return `${hostname} is connected and reporting normally. NOVA currently sees ${discoveredCount} nearby hosts on ${hostDiscovery.subnet || "the local subnet"} and ${patchBacklog} pending package updates.`;
  }, [primaryAgent, findings, packagePosture.upgradable_count, hostDiscovery.discovered_count, hostDiscovery.subnet, hostRows.length]);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 bg-[radial-gradient(circle_at_top,rgba(14,165,233,0.09),transparent_38%)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-[#38bdf8]">Security Center</p>
          <h2 className="font-display text-2xl font-bold text-text-primary mt-1">Personal AI SOC Analyst</h2>
          <p className="text-text-muted text-sm mt-1 max-w-4xl">{narrative}</p>
          <p className="text-text-muted text-xs mt-2">Last sync: {lastSyncedAt ? formatTimestamp(lastSyncedAt) : "Not synced yet"}</p>
        </div>
        <button onClick={loadAll} className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold border border-border bg-bg-elevated hover:bg-bg-card transition">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">Pull Remote Agent Snapshot</p>
            <p className="text-xs text-text-muted mt-1">Ingest a remote agent into NOVA and refresh Security telemetry immediately.</p>
          </div>
          <button onClick={pullFromAgent} disabled={pulling} className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold border border-border bg-bg-elevated hover:bg-bg-card transition disabled:opacity-60">
            {pulling ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
            {pulling ? "Pulling..." : "Pull Agent"}
          </button>
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mt-3">
          <label className="rounded-xl border border-border bg-bg-card px-3 py-2 text-xs text-text-muted">
            <span className="block text-[10px] uppercase tracking-[0.16em] mb-1">Agent URL</span>
            <input value={pullAgentUrl} onChange={(event) => setPullAgentUrl(event.target.value)} placeholder="http://10.20.40.144:3009" className="w-full bg-transparent text-text-primary outline-none placeholder:text-text-muted" />
          </label>
          <label className="rounded-xl border border-border bg-bg-card px-3 py-2 text-xs text-text-muted">
            <span className="block text-[10px] uppercase tracking-[0.16em] mb-1">Agent Token (optional)</span>
            <input value={pullToken} onChange={(event) => setPullToken(event.target.value)} placeholder="demo-token" className="w-full bg-transparent text-text-primary outline-none placeholder:text-text-muted" />
          </label>
        </div>
        {pullMessage && <p className="mt-3 text-xs text-text-muted">{pullMessage}</p>}
      </Card>

      {error && <InlineInfo icon={<AlertTriangle size={14} />} text={error} tone="danger" />}
      {loading && <InlineInfo icon={<Loader2 size={14} className="animate-spin" />} text="Refreshing security telemetry..." tone="info" />}

      {status && (
        <div className="grid grid-cols-2 xl:grid-cols-6 gap-3">
          <ScoreCard label="Overall" value={status.scores.overall} accent="cyan" icon={<Shield size={16} />} />
          <ScoreCard label="Host" value={status.scores.host} accent="orange" icon={<Server size={16} />} />
          <ScoreCard label="Browser" value={status.scores.browser} accent="blue" icon={<ShieldCheck size={16} />} />
          <ScoreCard label="Network" value={status.scores.network} accent="indigo" icon={<Network size={16} />} />
          <ScoreCard label="Identity" value={status.scores.identity} accent="green" icon={<ShieldAlert size={16} />} />
          <SummaryCard label="Connected Agents" value={status.connected_agents} helper={`${status.active_findings} active findings`} icon={<Activity size={16} />} />
        </div>
      )}

      <div className="inline-flex flex-wrap gap-2 rounded-2xl border border-border bg-bg-secondary p-2">
        {([
          ["overview", "Overview"],
          ["bom", "BOMs"],
          ["ot", "OT"],
          ["correlation", "Correlation"],
          ["raw", "Raw"],
        ] as Array<[SecurityTab, string]>).map(([tabId, label]) => (
          <button
            key={tabId}
            onClick={() => setActiveTab(tabId)}
            className={clsx(
              "px-3 py-2 rounded-xl text-sm border transition",
              activeTab === tabId ? "border-sky-500/30 bg-sky-500/10 text-sky-300" : "border-border bg-bg-card text-text-muted hover:text-text-primary"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 2xl:grid-cols-[1.35fr_1fr] gap-4">
            <Card>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-text-primary font-semibold"><Network size={16} /> Asset Overview</div>
                <div className="text-xs text-text-muted text-right">
                  <div>{hostDiscovery.subnet || "No subnet yet"}</div>
                  <div className="mt-1">{hostRows.length} visible assets</div>
                </div>
              </div>
              <div className="mt-4 max-h-[540px] overflow-auto rounded-xl border border-border">
                <div className="grid grid-cols-[1.2fr_1fr_1fr_0.8fr_0.8fr_1fr] gap-3 px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-text-muted bg-bg-elevated sticky top-0">
                  <span>Asset</span>
                  <span>Hostname</span>
                  <span>OS</span>
                  <span>Type</span>
                  <span>Risk</span>
                  <span>Ports</span>
                </div>
                <div className="divide-y divide-border">
                  {hostRows.length === 0 ? (
                    <EmptyPanel text="No discovered assets yet." compact />
                  ) : (
                    hostRows.map((node, idx) => (
                      <div key={`${node.ip}-${idx}`} className="grid grid-cols-[1.2fr_1fr_1fr_0.8fr_0.8fr_1fr] gap-3 px-3 py-3 text-xs bg-transparent">
                        <span className="text-text-primary truncate">{node.ip}</span>
                        <span className="text-text-muted truncate">{node.hostname || "unresolved"}</span>
                        <span className="text-sky-300 truncate">{node.osName || "Unknown"}</span>
                        <span className="text-text-secondary truncate">{node.hostType || "unknown"}</span>
                        <span className="text-text-secondary truncate">{node.riskLevel || "low"}</span>
                        <span className="text-text-muted truncate">{node.openPorts.join(", ") || "-"}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </Card>

            <div className="space-y-4">
              <Card>
                <div className="flex items-center gap-2 text-text-primary font-semibold"><Package size={16} /> Package Posture</div>
                {primaryAgent ? (
                  <div className="mt-4 space-y-3">
                    <MetricRow label="Package Manager" value={String(packagePosture.manager || "unknown")} />
                    <MetricRow label="Installed Packages" value={String(packagePosture.total_packages || 0)} />
                    <MetricRow label="Pending Upgrades" value={String(packagePosture.upgradable_count || 0)} highlight={Number(packagePosture.upgradable_count || 0) > 20} />
                    <div className="rounded-xl bg-bg-card border border-border p-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Upgradable samples</p>
                      <div className="mt-2 space-y-1.5 text-xs text-text-secondary max-h-[170px] overflow-auto pr-1">
                        {(packagePosture.upgradable || []).slice(0, 10).map((item, idx) => (
                          <div key={`${item.package}-${idx}`} className="flex items-start justify-between gap-3">
                            <span className="font-medium text-text-primary">{item.package || "unknown"}</span>
                            <span className="text-text-muted text-right break-all">{item.raw || ""}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <EmptyPanel text="Package posture will appear once an agent reports in." compact />
                )}
              </Card>

              <Card>
                <div className="flex items-center gap-2 text-text-primary font-semibold"><Shield size={16} /> Collector Readiness</div>
                <div className="mt-3 space-y-2">
                  {status ? Object.values(status.collectors).map((collector) => (
                    <div key={collector.name} className="rounded-xl border border-border bg-bg-card p-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-text-primary">{collector.name.replace(/_/g, " ")}</p>
                        <span className="text-[11px] px-2 py-1 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20">{collector.state}</span>
                      </div>
                      <p className="text-xs text-text-muted mt-1">{collector.description}</p>
                    </div>
                  )) : <EmptyPanel text="Collector state unavailable." compact />}
                </div>
              </Card>
            </div>
          </div>

          <Card>
            <div className="flex items-center gap-2 text-text-primary font-semibold"><Server size={16} /> Host Runtime Signals</div>
            {!primaryAgent ? <div className="mt-4"><EmptyPanel text="Runtime signals will appear when an agent reports telemetry." compact /></div> : (
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                  <MetricTile label="Processes" value={String(processes.length)} />
                  <MetricTile label="Listening Ports" value={String(listeningPorts.length)} />
                  <MetricTile label="Mounted Drives" value={String(mountedDrives.length)} />
                  <MetricTile label="Systemd Units" value={String((persistence.systemd_units || []).length)} />
                  <MetricTile label="Timers/Cron" value={`${(persistence.systemd_timers || []).length} / ${(persistence.cron_entries || []).length}`} />
                  <MetricTile label="Connections" value={`${Number(connections.established || 0)} / ${Number(connections.unique_remote_hosts || 0)} hosts`} />
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <div className="rounded-xl border border-border bg-bg-card p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Processes</p>
                    <div className="mt-2 space-y-2 max-h-[220px] overflow-auto pr-1">
                      {processes.length === 0 ? <EmptyPanel text="No process inventory in current payload." compact /> : processes.slice(0, 15).map((proc, index) => (
                        <div key={`${proc.pid}-${index}`} className="rounded-lg border border-border bg-bg-elevated p-2">
                          <p className="text-xs font-semibold text-text-primary">{proc.name || "unknown"} ({proc.pid || 0})</p>
                          <p className="text-xs text-text-muted mt-1">{proc.user || "unknown user"} | CPU {Number(proc.cpu_percent || 0).toFixed(1)}% | MEM {Number(proc.memory_percent || 0).toFixed(2)}%</p>
                          <p className="text-xs text-text-muted mt-1 break-all">{proc.exe || proc.cmdline || "no executable path"}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-border bg-bg-card p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Network and Logins</p>
                    <div className="mt-2 space-y-2 max-h-[140px] overflow-auto pr-1">
                      {listeningPorts.length === 0 ? <EmptyPanel text="No listening port data in current payload." compact /> : listeningPorts.slice(0, 20).map((portRow, index) => (
                        <div key={`${portRow.ip}-${portRow.port}-${index}`} className="rounded-lg border border-border bg-bg-elevated p-2">
                          <p className="text-xs font-semibold text-text-primary">{portRow.ip || "0.0.0.0"}:{portRow.port || 0}</p>
                          <p className="text-xs text-text-muted mt-1">PID {portRow.pid || 0}</p>
                        </div>
                      ))}
                    </div>

                    <div className="mt-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Established Connections</p>
                      <div className="mt-2 space-y-1.5 max-h-[120px] overflow-auto pr-1">
                        {connectionDetails.length === 0 ? <EmptyPanel text="No established connection details in current payload." compact /> : connectionDetails.slice(0, 20).map((item, idx) => (
                          <div key={`${item.local}-${item.remote}-${idx}`} className="rounded-lg border border-border bg-bg-elevated p-2">
                            <p className="text-xs font-semibold text-text-primary break-all">{item.local || ""} -&gt; {item.remote || ""}</p>
                            <p className="text-xs text-text-muted mt-1">PID {item.pid || 0} | {item.status || "unknown"}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="mt-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Login Snapshot</p>
                      <div className="mt-2 space-y-1.5 max-h-[120px] overflow-auto pr-1">
                        {loginSnapshot.length === 0 ? <EmptyPanel text="No login snapshot in current payload." compact /> : loginSnapshot.slice(0, 10).map((line, idx) => (
                          <p key={`${line}-${idx}`} className="text-xs text-text-muted break-all">{line}</p>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-bg-card p-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Persistence Paths</p>
                  <div className="mt-2 grid grid-cols-1 xl:grid-cols-2 gap-3">
                    <div className="space-y-1.5 max-h-[140px] overflow-auto pr-1">
                      <p className="text-xs font-semibold text-text-primary">Systemd Units</p>
                      {(persistence.systemd_units || []).slice(0, 20).map((entry, idx) => <p key={`${entry}-${idx}`} className="text-xs text-text-muted break-all">{entry}</p>)}
                    </div>
                    <div className="space-y-1.5 max-h-[140px] overflow-auto pr-1">
                      <p className="text-xs font-semibold text-text-primary">Timers and Autostart</p>
                      {[...(persistence.systemd_timers || []).slice(0, 10), ...(persistence.autostart_entries || []).slice(0, 10)].map((entry, idx) => <p key={`${entry}-${idx}`} className="text-xs text-text-muted break-all">{entry}</p>)}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {activeTab === "bom" && (
        <div className="space-y-4">
          {hasAnyDeferredOnlyBom && (
            <InlineInfo
              icon={<AlertTriangle size={14} />}
              text="Current payload is in hash-only deferred BOM mode for one or more BOM types. Full component/certificate/hardware documents are not in this snapshot window yet."
              tone="info"
            />
          )}

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card>
              <div className="flex items-center gap-2 text-text-primary font-semibold"><Package size={16} /> BOM Transport State</div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                <BomCard label="SBOM" hash={bomHashes.sbom || sbomState.hash} deferred={Boolean(sbomState.deferred)} />
                <BomCard label="CBOM" hash={bomHashes.cbom || cbomState.hash} deferred={Boolean(cbomState.deferred)} />
                <BomCard label="HBOM" hash={bomHashes.hbom || hbomState.hash} deferred={Boolean(hbomState.deferred)} />
              </div>
            </Card>
            <Card>
              <div className="flex items-center gap-2 text-text-primary font-semibold"><Cpu size={16} /> BOM Summary</div>
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricTile label="SBOM Components" value={String(sbomDoc?.components?.length || 0)} />
                <MetricTile label="SBOM Vulns" value={String(sbomDoc?.vulnerabilities?.length || 0)} />
                <MetricTile label="CBOM Certs" value={String(cbomDoc?.certificates?.length || 0)} />
                <MetricTile label="CBOM Keys" value={String(cbomDoc?.keys?.length || 0)} />
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card>
              <div className="flex items-center gap-2 text-text-primary font-semibold"><Package size={16} /> SBOM Components</div>
              <div className="mt-4 space-y-2 max-h-[360px] overflow-auto pr-1">
                {(sbomDoc?.components || []).length > 0 ? (
                  (sbomDoc?.components || []).slice(0, 50).map((component, index) => (
                    <div key={`${component.purl || component.name}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                      <p className="text-sm font-semibold text-text-primary">{component.name || "unknown component"}</p>
                      <p className="text-xs text-sky-300 mt-1">{component.version || "unknown version"}</p>
                      <p className="text-xs text-text-muted mt-1 break-all">{component.purl || component.type || "no purl"}</p>
                    </div>
                  ))
                ) : (packagePosture.upgradable || []).length > 0 ? (
                  (packagePosture.upgradable || []).slice(0, 50).map((item, index) => (
                    <div key={`${item.package}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                      <p className="text-sm font-semibold text-text-primary">{item.package || "unknown package"}</p>
                      <p className="text-xs text-text-muted mt-1 break-all">{item.raw || "No package detail line provided"}</p>
                    </div>
                  ))
                ) : (
                  <EmptyPanel text="No SBOM component document stored in the current payload window." compact />
                )}
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-2 text-text-primary font-semibold"><Shield size={16} /> CBOM Certificates and Keys</div>
              <div className="mt-4 grid grid-cols-1 gap-4">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Certificates</p>
                  <div className="mt-2 space-y-2 max-h-[160px] overflow-auto pr-1">
                    {(cbomDoc?.certificates || []).length === 0 ? <EmptyPanel text="No certificate inventory stored in the current payload." compact /> : (cbomDoc?.certificates || []).slice(0, 20).map((cert, index) => (
                      <div key={`${cert.path}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                        <p className="text-xs font-semibold text-text-primary break-all">{cert.path || "unknown path"}</p>
                        <p className="text-xs text-text-muted mt-1 break-all">{cert.subject || cert.issuer || "subject unavailable"}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">Keys</p>
                  <div className="mt-2 space-y-2 max-h-[160px] overflow-auto pr-1">
                    {(cbomDoc?.keys || []).length === 0 ? <EmptyPanel text="No key metadata stored in the current payload." compact /> : (cbomDoc?.keys || []).slice(0, 20).map((keyRow, index) => (
                      <div key={`${keyRow.path}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                        <p className="text-xs font-semibold text-text-primary break-all">{keyRow.path || "unknown path"}</p>
                        <p className="text-xs text-text-muted mt-1">{keyRow.algorithm || "unknown algorithm"}{keyRow.key_size ? ` | ${keyRow.key_size}` : ""}{keyRow.encrypted ? " | encrypted" : ""}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <Card>
            <div className="flex items-center gap-2 text-text-primary font-semibold"><Server size={16} /> HBOM Details</div>
            <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="rounded-xl border border-border bg-bg-card p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">DMI</p>
                <div className="mt-3 space-y-2">
                  {Object.entries(hbomDoc?.dmi || {}).length === 0 ? <EmptyPanel text="No DMI values stored in the current payload." compact /> : Object.entries(hbomDoc?.dmi || {}).map(([key, value]) => <MetricRow key={key} label={key} value={String(value || "unknown")} />)}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-bg-card p-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">CPU Vulnerabilities</p>
                <div className="mt-3 space-y-2 max-h-[220px] overflow-auto pr-1">
                  {Object.entries(hbomDoc?.cpu_vulnerabilities || {}).length === 0 ? <EmptyPanel text="No CPU vulnerability entries stored in the current payload." compact /> : Object.entries(hbomDoc?.cpu_vulnerabilities || {}).map(([key, value]) => (
                    <div key={key} className="rounded-lg border border-border bg-bg-elevated p-2">
                      <p className="text-xs font-semibold text-text-primary">{key}</p>
                      <p className="text-xs text-text-muted mt-1">{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          {hasAnyDeferredOnlyBom && (
            <Card>
              <div className="flex items-center gap-2 text-text-primary font-semibold"><Server size={16} /> Deferred BOM Raw Objects</div>
              <p className="text-xs text-text-muted mt-2">These are the current payload objects for SBOM, CBOM, and HBOM in deferred mode.</p>
              <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-3">
                <div className="rounded-xl border border-border bg-bg-card p-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">SBOM</p>
                  <pre className="mt-2 text-[11px] leading-5 text-text-muted whitespace-pre-wrap break-words">{JSON.stringify(telemetry.sbom || {}, null, 2)}</pre>
                </div>
                <div className="rounded-xl border border-border bg-bg-card p-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">CBOM</p>
                  <pre className="mt-2 text-[11px] leading-5 text-text-muted whitespace-pre-wrap break-words">{JSON.stringify(telemetry.cbom || {}, null, 2)}</pre>
                </div>
                <div className="rounded-xl border border-border bg-bg-card p-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted font-mono">HBOM</p>
                  <pre className="mt-2 text-[11px] leading-5 text-text-muted whitespace-pre-wrap break-words">{JSON.stringify(telemetry.hbom || {}, null, 2)}</pre>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      {activeTab === "ot" && (
        <Card>
          <div className="flex items-center gap-2 text-text-primary font-semibold"><Network size={16} /> OT Identity Audit</div>
          {!primaryAgent ? <div className="mt-4"><EmptyPanel text="OT identity data will appear when an agent reports OT or unknown-zone targets." compact /></div> : (
            <div className="mt-4 space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricTile label="Mode" value={String(otIdentity.mode || "passive_only")} />
                <MetricTile label="DNP3" value={String(otIdentity.dnp3_mode || "passive_only")} />
                <MetricTile label="Circuit Breaker" value={otIdentity.circuit_breaker_tripped ? "Tripped" : "Clear"} tone={otIdentity.circuit_breaker_tripped ? "warn" : "normal"} />
                <MetricTile label="Auth Ref" value={String(otIdentity.authorization?.auth_ref || otIdentity.reason || "Not available")} />
              </div>
              <div className="space-y-2 max-h-[320px] overflow-auto pr-1">
                {(otIdentity.results || []).length === 0 ? <EmptyPanel text="No active OT identity probe records in the current telemetry window." compact /> : (otIdentity.results || []).map((item, index) => (
                  <div key={`${item.target}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">{item.target || "Unknown target"}</p>
                        <p className="text-xs text-text-muted mt-1">{item.protocol || "protocol"} / {item.primitive || "identity"}</p>
                      </div>
                      <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">{item.elapsed_ms || 0} ms</span>
                    </div>
                    <p className="text-xs text-text-muted mt-2">Approver: {item.approver || otIdentity.authorization?.approver || "n/a"} | Auth: {item.auth_ref || otIdentity.authorization?.auth_ref || "n/a"}</p>
                    {item.error && <p className="text-xs text-orange-300 mt-2">{item.error}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {activeTab === "correlation" && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-center gap-2 text-text-primary font-semibold"><ShieldAlert size={16} /> Correlation Work Queue</div>
            {!primaryAgent ? <div className="mt-4"><EmptyPanel text="Correlation queue will appear after BOM and vulnerability inputs are available." compact /></div> : (
              <div className="mt-4 space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <MetricTile label="Queued" value={String(correlation.queue_size || 0)} tone={Number(correlation.queue_size || 0) > 0 ? "warn" : "normal"} />
                  <MetricTile label="KEV/EPSS" value="Reachable Only" />
                  <MetricTile label="Exposure" value="Cross-Zone Required" />
                </div>
                <div className="space-y-2 max-h-[320px] overflow-auto pr-1">
                  {(correlation.queue || []).length === 0 ? <EmptyPanel text="No prioritized items yet. Items enter this queue only when reachable and cross-zone exposed." compact /> : (correlation.queue || []).map((item, index) => (
                    <div key={`${item.vuln_id}-${index}`} className="rounded-xl border border-border bg-bg-card p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-text-primary">{item.vuln_id || "Unknown vuln"}</p>
                          <p className="text-xs text-text-muted mt-1">{item.component || "unknown component"} on {item.asset || "unknown asset"}</p>
                        </div>
                        <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">EPSS {(item.epss || 0).toFixed(2)}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <span className="text-[10px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">{String(item.severity || "unknown").toUpperCase()}</span>
                        {item.kev && <span className="text-[10px] px-2 py-1 rounded-full border border-red-500/25 bg-red-500/10 text-red-300">KEV</span>}
                        {item.reachable && <span className="text-[10px] px-2 py-1 rounded-full border border-sky-500/25 bg-sky-500/10 text-sky-300">Reachable</span>}
                        {item.cross_zone_exposed && <span className="text-[10px] px-2 py-1 rounded-full border border-orange-500/25 bg-orange-500/10 text-orange-300">Cross-Zone</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center gap-2 text-text-primary font-semibold"><ShieldAlert size={16} /> Findings</div>
            <div className="mt-4 space-y-3 max-h-[420px] overflow-auto pr-1">
              {findings.length === 0 ? <EmptyPanel text="No findings yet." compact /> : findings.map((finding) => (
                <div key={finding.id} className="rounded-xl border border-border bg-bg-card p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-text-primary">{finding.title}</p>
                      <p className="text-xs text-text-muted mt-1">{finding.summary}</p>
                    </div>
                    <RiskBadge risk={finding.risk} />
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {finding.tags.map((tag) => <span key={tag} className="text-[10px] px-2 py-1 rounded-full border border-border bg-bg-elevated text-text-muted">{tag}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {activeTab === "raw" && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-center gap-2 text-text-primary font-semibold"><Clock3 size={16} /> Timeline</div>
            <div className="mt-4 space-y-3 max-h-[420px] overflow-auto pr-1">
              {timeline.length === 0 ? <EmptyPanel text="No timeline events yet." compact /> : timeline.map((event) => (
                <div key={event.id} className="relative pl-5">
                  <span className="absolute left-0 top-1.5 w-2.5 h-2.5 rounded-full bg-[#38bdf8] shadow-[0_0_12px_rgba(56,189,248,0.45)]" />
                  <div className="rounded-xl border border-border bg-bg-card p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-text-primary">{event.title}</p>
                      <span className="text-[11px] text-text-muted">{formatTimestamp(event.timestamp)}</span>
                    </div>
                    <p className="text-xs text-text-muted mt-1">{event.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-2 text-text-primary font-semibold"><Server size={16} /> Raw Telemetry Payload</div>
            <div className="mt-4 rounded-xl border border-border bg-bg-card p-3 max-h-[420px] overflow-auto">
              <pre className="text-[11px] leading-5 text-text-muted whitespace-pre-wrap break-words">{JSON.stringify(telemetry, null, 2)}</pre>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function ScoreCard({ label, value, icon, accent }: { label: string; value: number; icon: React.ReactNode; accent: "cyan" | "orange" | "blue" | "indigo" | "green" }) {
  const accentClasses = {
    cyan: "from-sky-500/20 to-sky-500/5 border-sky-500/20 text-sky-300",
    orange: "from-orange-500/20 to-orange-500/5 border-orange-500/20 text-orange-300",
    blue: "from-blue-500/20 to-blue-500/5 border-blue-500/20 text-blue-300",
    indigo: "from-indigo-500/20 to-indigo-500/5 border-indigo-500/20 text-indigo-300",
    green: "from-emerald-500/20 to-emerald-500/5 border-emerald-500/20 text-emerald-300",
  } as const;

  return (
    <div className={clsx("rounded-2xl border bg-gradient-to-br p-4", accentClasses[accent])}>
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-[0.18em] font-mono">{label}</p>
        {icon}
      </div>
      <p className="text-3xl font-bold text-text-primary mt-3">{value}</p>
    </div>
  );
}

function SummaryCard({ label, value, helper, icon }: { label: string; value: number; helper: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-bg-secondary p-4">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-[0.18em] font-mono text-text-muted">{label}</p>
        <span className="text-[#38bdf8]">{icon}</span>
      </div>
      <p className="text-3xl font-bold text-text-primary mt-3">{value}</p>
      <p className="text-xs text-text-muted mt-2">{helper}</p>
    </div>
  );
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx("rounded-2xl border border-border bg-bg-secondary p-4", className)}>{children}</div>;
}

function MetricRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-text-muted">{label}</span>
      <span className={clsx("font-semibold", highlight ? "text-amber-300" : "text-text-primary")}>{value}</span>
    </div>
  );
}

function RiskBadge({ risk }: { risk: SecurityFinding["risk"] }) {
  const styles = {
    critical: "bg-red-500/15 text-red-300 border-red-500/25",
    high: "bg-orange-500/15 text-orange-300 border-orange-500/25",
    medium: "bg-amber-500/15 text-amber-300 border-amber-500/25",
    low: "bg-sky-500/15 text-sky-300 border-sky-500/25",
  } as const;
  return <span className={clsx("text-[11px] px-2 py-1 rounded-full border font-semibold", styles[risk])}>{risk.toUpperCase()}</span>;
}

function InlineInfo({ icon, text, tone }: { icon: React.ReactNode; text: string; tone: "danger" | "info" }) {
  return (
    <div className={clsx("rounded-xl border px-3 py-2 text-sm inline-flex items-center gap-2", tone === "danger" ? "bg-red-500/10 border-red-500/20 text-red-200" : "bg-sky-500/10 border-sky-500/20 text-sky-200")}>
      {icon}
      {text}
    </div>
  );
}

function EmptyPanel({ text, compact = false }: { text: string; compact?: boolean }) {
  return <div className={clsx("rounded-xl border border-border bg-bg-card text-text-muted text-sm flex items-center justify-center text-center", compact ? "p-4" : "p-8 min-h-[120px]")}>{text}</div>;
}

function MetricTile({ label, value, tone = "normal" }: { label: string; value: string; tone?: "normal" | "warn" }) {
  return (
    <div className="rounded-xl border border-border bg-bg-card p-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-text-muted font-mono">{label}</p>
      <p className={clsx("text-sm font-semibold mt-2 break-all", tone === "warn" ? "text-orange-300" : "text-text-primary")}>{value}</p>
    </div>
  );
}

function BomCard({ label, hash, deferred }: { label: string; hash?: string; deferred: boolean }) {
  return (
    <div className="rounded-xl border border-border bg-bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] uppercase tracking-[0.16em] text-text-muted font-mono">{label}</p>
        <span className={clsx("text-[10px] px-2 py-1 rounded-full border", deferred ? "border-sky-500/25 bg-sky-500/10 text-sky-300" : "border-emerald-500/25 bg-emerald-500/10 text-emerald-300")}>{deferred ? "Hash Only" : "Full Doc"}</span>
      </div>
      <p className="text-xs text-text-primary font-mono mt-3 break-all">{hash || "No hash yet"}</p>
    </div>
  );
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
