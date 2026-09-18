import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Download, ExternalLink, FileSearch, Image, Search } from "lucide-react";
import { apiResearchReport, apiResearchReports } from "@/services/api";
import type { ResearchReport, ResearchReportSummary, SearchRelevance } from "@/services/api";
import { useAppStore } from "@/stores/useAppStore";

const stateLabel = (value: string) => value.toLowerCase().replace(/_/g, " ");
const imageHosts = new Set(["external-content.duckduckgo.com", "tse1.mm.bing.net", "tse2.mm.bing.net", "tse3.mm.bing.net", "tse4.mm.bing.net", "ts1.mm.bing.net", "ts2.mm.bing.net", "ts3.mm.bing.net", "ts4.mm.bing.net"]);
const dateLabel = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
const stateColor = (state: string) => state === "COMPLETED" || state === "SUCCESS" ? "text-accent-green"
  : ["FAILED", "CANCELLED", "INTERRUPTED"].includes(state) ? "text-accent-red" : "text-nova-amber";

export function safeSourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

function Citations({ identities, report }: { identities: string[]; report: ResearchReport }) {
  return <span className="inline-flex flex-wrap gap-2 ml-2">{identities.map((identity) => {
    const index = report.sources.findIndex((source) => source.id === identity);
    const source = report.sources[index];
    const href = source && safeSourceUrl(source.url);
    if (source?.kind === "file_content") return <span key={identity} className="text-xs text-accent-blue" title={source.url}>[{index + 1}] {source.url.replace(/^repo:/, "")}</span>;
    return href ? <a key={identity} href={href} target="_blank" rel="noopener noreferrer" className="text-nova-orange text-xs hover:underline" title={source.domain}>[{index + 1}]</a> : null;
  })}</span>;
}

function Relevance({ value }: { value?: SearchRelevance | null }) {
  if (!value || !Number.isFinite(value.score) || value.score < 0 || value.score > 100) return null;
  return <details className="mt-3 text-xs text-text-secondary break-words">
    <summary className="cursor-pointer text-accent-blue" title="Lexical query match, not factual confidence">Relevance: {Math.round(value.score)}/100</summary>
    <dl className="mt-2 space-y-2">
      <div><dt className="font-semibold">Query</dt><dd>{value.query}</dd></div>
      <div><dt className="font-semibold">Matched terms</dt><dd>{value.matched_terms.join(", ") || "None"}</dd></div>
      <div><dt className="font-semibold">Missing terms</dt><dd>{value.missing_terms.join(", ") || "None"}</dd></div>
      <div><dt className="font-semibold">Method</dt><dd>{value.method} / Text match, not factual or visual verification</dd></div>
    </dl>
  </details>;
}

function ReportImages({ report }: { report: ResearchReport }) {
  const [enabled, setEnabled] = useState(false);
  const [broken, setBroken] = useState<string[]>([]);
  function sourcePage(value: string) {
    const safe = safeSourceUrl(value);
    if (!safe) return undefined;
    const url = new URL(safe);
    url.hash = "";
    return url.href;
  }
  const citedIds = new Set(report.findings.flatMap(finding => finding.source_ids));
  const citedPages = new Set(report.sources.filter(source => citedIds.has(source.id))
    .map(source => sourcePage(source.url)).filter((page): page is string => !!page));
  const images = (report.images || []).filter((image) => {
    const url = safeSourceUrl(image.url);
    const page = sourcePage(image.source_url);
    return url && new URL(url).protocol === "https:" && imageHosts.has(new URL(url).hostname) && page && citedPages.has(page);
  });
  if (!images.length) return <p className="text-sm text-text-secondary">No images matched the cited findings.</p>;
  return <>
    <div className="flex flex-wrap items-center justify-between gap-3 mb-5"><p className="text-xs text-text-secondary">Images associated with cited source pages. Depicted subjects are not visually verified.</p><label className="flex items-center gap-2 text-sm shrink-0"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="accent-nova-orange" />Load external images</label></div>
    <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">{images.map((image) => <figure key={image.id} className="border border-border rounded-lg overflow-hidden">
      <div className="aspect-[4/3] bg-bg-secondary flex items-center justify-center overflow-hidden">{enabled && !broken.includes(image.id)
        ? <img src={image.url} alt={image.title} loading="lazy" referrerPolicy="no-referrer" className="w-full h-full object-contain" onError={() => setBroken((current) => [...current, image.id])} />
        : <div className="text-center text-text-secondary"><Image size={24} className="mx-auto mb-2" /><span className="text-xs">{broken.includes(image.id) ? "Image unavailable" : "Image not loaded"}</span></div>}</div>
      <figcaption className="p-3"><p className="text-sm break-words">{image.title}</p><Relevance value={image.relevance} /><a href={safeSourceUrl(image.source_url)} target="_blank" rel="noopener noreferrer" className="inline-flex gap-2 items-center mt-3 text-xs text-nova-orange">Source page<ExternalLink size={12} /></a></figcaption>
    </figure>)}</div>
  </>;
}

export function ResearchReports({ revision = 0 }: { revision?: number }) {
  const requestedId = useAppStore((state) => state.activeReportId);
  const openReport = useAppStore((state) => state.openReport);
  const [items, setItems] = useState<ResearchReportSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState("Overview");
  const selectedId = requestedId || items[0]?.id;

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function refresh() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      try {
        const next = await apiResearchReports(query, offset, controller.signal);
        if (!disposed) { setItems(next.items); setTotal(next.total); setHistoryError(""); setLoaded(true); }
      } catch {
        if (!disposed) { setHistoryError("Saved history is unavailable. Check the backend connection."); setLoaded(true); }
      } finally {
        clearTimeout(timeout);
        if (!disposed) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
  }, [query, offset, revision]);

  useEffect(() => {
    setReport(null); setDetailError(""); setTab("Overview");
    if (!selectedId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function refresh() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      try {
        const next = await apiResearchReport(selectedId!, controller.signal);
        if (!disposed) {
          setReport(next); setDetailError("");
          if (["QUEUED", "RUNNING"].includes(next.status)) timer = setTimeout(refresh, 2500);
        }
      } catch {
        if (!disposed) { setDetailError("Report unavailable. It may still be saving, or the backend is disconnected."); timer = setTimeout(refresh, 5000); }
      } finally { clearTimeout(timeout); }
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
  }, [selectedId, revision]);

  function download() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${report.id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  const overview = report && (report.findings.some((finding) => finding.task_id === "prism")
    ? report.findings.filter((finding) => finding.task_id === "prism") : report.findings);
  const pageReads = report?.coverage?.page_reads || [];
  const downloadedPages = pageReads.filter(page => page.status === "READ").length;
  const suppliedPages = pageReads.filter(page => page.supplied_to_model).length;

  return <section aria-label="Saved research reports" className="py-6">
    <div className="grid lg:grid-cols-[240px_minmax(0,1fr)] gap-6">
      <aside aria-label="Research history" className="min-w-0 lg:border-r border-border lg:pr-5">
        <div className="flex items-center justify-between mb-4"><h2 className="nova-panel-heading">Saved research</h2><span className="text-xs text-text-secondary font-mono">{total}</span></div>
        <label className="flex items-center gap-2 border border-border rounded-md bg-bg-secondary px-2"><Search size={15} className="shrink-0 text-text-secondary" /><input aria-label="Search research history" placeholder="Search topics" value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} className="min-w-0 w-full h-10 bg-transparent outline-none text-sm" /></label>
        {historyError && <p role="alert" className="mt-3 text-xs text-nova-amber">{historyError}</p>}
        <div className="mt-3 max-h-64 lg:max-h-[560px] overflow-y-auto divide-y divide-border">
          {items.map((item) => <button key={item.id} onClick={() => openReport(item.id)} aria-pressed={selectedId === item.id} className={`block w-full text-left py-4 px-2 border-l-2 ${selectedId === item.id ? "border-nova-orange bg-nova-orange/5" : "border-transparent hover:bg-bg-secondary"}`}>
            <span className="block text-sm font-medium break-words">{item.topic}</span><span className={`block text-xs mt-2 ${stateColor(item.status)}`}>{stateLabel(item.status)}</span><span className="block text-[11px] text-text-secondary mt-1">{dateLabel(item.created_at)}</span>
          </button>)}
        </div>
        {!items.length && !historyError && <p className="py-5 text-sm text-text-secondary">{!loaded ? "Loading history..." : query ? "No matching reports." : "No saved research yet."}</p>}
        {total > 30 && <div className="flex items-center justify-between mt-3 text-xs text-text-secondary"><button aria-label="Previous reports" title="Previous reports" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))} className="p-2 disabled:opacity-30"><ArrowLeft size={16} /></button><span>{offset + 1}-{Math.min(offset + 30, total)} / {total}</span><button aria-label="Next reports" title="Next reports" disabled={offset + 30 >= total} onClick={() => setOffset(offset + 30)} className="p-2 disabled:opacity-30"><ArrowRight size={16} /></button></div>}
      </aside>
      <article aria-label="Research report" className="min-w-0">
        {detailError && <p role="alert" className="mb-4 text-sm text-nova-amber">{detailError}</p>}
        {!report ? <div className="py-16 text-center text-text-secondary"><FileSearch size={32} className="mx-auto mb-4 text-accent-blue" /><h2 className="font-display text-lg text-text-primary">{selectedId ? "Loading report" : "Research reports"}</h2><p className="text-sm mt-2">{selectedId ? "Waiting for saved findings." : "No report selected."}</p></div> : <>
          <header className="pb-6 border-b border-border">
            <p className="nova-panel-heading mb-3">{report.kind === "repository_review" ? "Repository review" : "Research report"}</p>
            {report.scope && <div className="mb-4 text-xs text-text-secondary break-words"><p>{report.scope.repository} / {report.scope.mode}</p><ul className="mt-2 font-mono">{report.scope.files.map(path => <li key={path}>{path}</li>)}</ul></div>}
            <div className="flex justify-between gap-3 items-start"><h2 className="font-display text-xl font-semibold break-words min-w-0">{report.topic}</h2><button onClick={download} aria-label="Download report" title="Download report as JSON" className="p-2 border border-border rounded-md shrink-0 text-text-secondary hover:text-nova-orange"><Download size={17} /></button></div>
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-text-secondary mt-3"><span className={stateColor(report.status)}>{stateLabel(report.status)}</span><span>{dateLabel(report.created_at)}</span><span>{report.findings.length} findings</span><span>{report.sources.length} citations</span></div>
          </header>
          <nav aria-label="Report views" className="flex flex-wrap gap-1 border-b border-border" role="tablist">{(report.kind === "repository_review" ? ["Overview", "Sources", "Activity"] : ["Overview", "Comparison", "Coverage", "Images", "Sources", "Activity"]).map((view) => <button key={view} role="tab" aria-selected={tab === view} onClick={() => setTab(view)} className={`px-3 py-3 text-sm border-b-2 ${tab === view ? "border-nova-orange text-nova-orange" : "border-transparent text-text-secondary hover:text-text-primary"}`}>{view}</button>)}</nav>
          <div role="tabpanel" aria-label={tab} className="py-5">
            {tab === "Images" && <ReportImages key={report.id} report={report} />}
            {tab === "Overview" && <>
              {!!report.key_takeaways?.length && report.kind !== "repository_review" && <section aria-label="Key takeaways" className="mb-7 border-l-4 border-accent-blue bg-[#f4d96f] text-[#202124] px-4 sm:px-5 py-5">
                <p className="text-[10px] uppercase font-semibold mb-2">Prism / Decision brief</p>
                <h3 className="font-display text-lg font-semibold mb-4">Key takeaways</h3>
                <ol className="space-y-4">{report.key_takeaways.map((finding, index) => <li key={index} className="text-sm leading-6 break-words">
                  <span className="block text-xs font-semibold mb-1">{finding.subject || stateLabel(finding.category || "finding")}</span>
                  {finding.text}<span className="inline-flex flex-wrap gap-2 ml-2">{finding.source_ids.map(identity => {
                    const sourceIndex = report.sources.findIndex(source => source.id === identity);
                    const source = report.sources[sourceIndex];
                    return source && safeSourceUrl(source.url) ? <a key={identity} href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer" className="underline font-semibold text-[#204d75]" title={source.domain}>[{sourceIndex + 1}]</a> : null;
                  })}</span>
                </li>)}</ol>
              </section>}
              {report.kind === "repository_review" ? <p className="text-xs text-text-secondary mb-5">Selected-file evidence. No tests executed or files changed.</p> : report.coverage && <p className="text-xs text-text-secondary mb-5">{report.coverage.searches.length} searches / {report.coverage.cited_domains} cited domains. {suppliedPages ? `${suppliedPages} page extracts supplied to the model; extracts may be truncated. Not an exhaustive crawl.` : "Search-result evidence; source pages have not been read in full."}</p>}
              <h3 className="font-display font-semibold mb-4">{report.findings.some((finding) => finding.task_id === "prism") ? "Comparison findings" : "Available findings"}</h3>
              <ul className="space-y-5">{overview?.map((finding, index) => <li key={index} className="text-sm leading-7 grid grid-cols-[24px_minmax(0,1fr)] gap-3 break-words"><span className="text-nova-orange/70 font-mono text-xs pt-1">{String(index + 1).padStart(2, "0")}</span><div>{finding.text}<Citations identities={finding.source_ids} report={report} /></div></li>)}</ul>
              {!report.findings.length && <p className="text-sm text-text-secondary">{["RUNNING", "QUEUED"].includes(report.status) ? "Research is in progress. Verified findings will appear when the run finishes." : "This run produced no verified findings."}</p>}
              {!!report.gaps.length && <div className="mt-7 border-t border-border pt-4"><h3 className="text-sm font-semibold text-nova-amber mb-3">Unresolved</h3>{report.gaps.map((gap, index) => <p key={index} className="text-sm text-text-secondary mb-2"><strong>{gap.name}:</strong> {gap.reason}</p>)}</div>}
            </>}
            {tab === "Comparison" && <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm table-fixed"><thead className="text-xs text-text-secondary border-b border-border"><tr><th className="w-20 py-3">Researcher</th><th className="w-32 p-3">Focus</th><th className="p-3">Evidence-backed comparison</th></tr></thead><tbody>{report.findings.map((finding, index) => <tr key={index} className="border-b border-border align-top"><td className="py-4 text-text-secondary break-words">{finding.agent_name}</td><td className="p-3 break-words"><span className="block text-text-primary">{finding.subject || "General"}</span><span className={finding.category === "contradiction" ? "text-accent-red text-xs" : "text-accent-blue text-xs"}>{stateLabel(finding.category || "finding")}</span></td><td className="p-3 leading-7 break-words">{finding.text}<Citations identities={finding.source_ids} report={report} /></td></tr>)}</tbody></table>{!report.findings.length && <p className="py-5 text-sm text-text-secondary">No verified comparison data.</p>}</div>}
            {tab === "Coverage" && <section aria-label="Search coverage">
              <h3 className="font-display text-lg mb-3">Research coverage</h3>
              <p className="text-xs text-text-secondary mb-5">{report.coverage ? `${report.coverage.cited_domains} cited domains. Retrieved records may repeat across queries; domain variety alone is not independent confirmation.` : "Search coverage was not recorded for this older report."}</p>
              <h4 className="font-semibold text-sm mb-2">Page reads</h4>
              <p className="text-xs text-text-secondary mb-3">{downloadedPages} extracts downloaded / {pageReads.length} attempts / {suppliedPages} supplied to the model. Repeated URLs count per attempt.</p>
              <div className="divide-y divide-border mb-5">{pageReads.map((page, index) => <div key={index} className="py-3 text-xs">
                <div className="flex flex-wrap justify-between gap-2"><span className="text-accent-blue">{page.agent_name}</span><span className={page.supplied_to_model ? "text-accent-green" : "text-nova-amber"}>{page.status === "READ" ? page.supplied_to_model ? "Extract supplied" : "Downloaded; excluded from context" : "Unavailable or denied"}</span></div>
                <a href={safeSourceUrl(page.url)} target="_blank" rel="noopener noreferrer" className="block mt-2 break-all text-text-secondary">{page.url}</a>
                {page.truncated && <p className="mt-2 text-text-secondary">Truncated extract</p>}
              </div>)}</div>
              <h4 className="font-semibold text-sm">Search queries</h4>
              <div className="divide-y divide-border">{report.coverage?.searches.map((search, index) => <div key={index} className="py-4">
                <div className="flex flex-wrap justify-between gap-2 text-xs"><span className="text-accent-blue">{search.agent_name}</span><span className={search.status === "OK" ? "text-accent-green" : "text-nova-amber"}>{stateLabel(search.status)}</span></div>
                <p className="text-sm leading-6 break-words mt-2">{search.query}</p><p className="text-xs text-text-secondary mt-2">{search.sources} retrieved records / {search.reviewed_sources} supplied to the model</p>
                {search.retrieval && <p className="text-xs text-text-secondary mt-2">{search.retrieval.candidate_sources ?? "Unknown"} unique eligible source candidates / {search.retrieval.providers_requested?.length ?? "Unknown"} providers requested / Search snippets</p>}
              </div>)}</div>
            </section>}
            {tab === "Sources" && <div className="divide-y divide-border">{report.sources.map((source, index) => <div key={source.id} className="py-4">{source.kind === "file_content" ? <p className="text-sm text-accent-blue break-all">[{index + 1}] {source.url.replace(/^repo:/, "")}</p> : <a href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-2 text-sm text-nova-orange break-all">[{index + 1}] {source.title || source.domain}<ExternalLink size={14} className="shrink-0 mt-1" /></a>}<p className="text-xs text-text-secondary break-all mt-2">{source.url}</p><Relevance value={source.relevance} /><p className="text-xs text-text-secondary mt-2">Retrieved {dateLabel(source.retrieved_at)}</p><details className="mt-2 text-xs text-text-secondary"><summary className="cursor-pointer">Evidence record</summary><p className="break-all mt-2">{source.id}</p><p className="break-all mt-1">SHA-256: {source.digest}</p></details></div>)}{!report.sources.length && <p className="text-sm text-text-secondary">No cited sources.</p>}</div>}
            {tab === "Activity" && <div className="divide-y divide-border">{report.tasks.map((task) => <div key={task.id} className="py-4"><div className="flex flex-wrap justify-between gap-2"><h3 className="font-medium text-sm">{task.name}</h3><span className={`text-xs ${stateColor(task.result_status || task.state)}`}>{stateLabel(task.state === "COMPLETED" ? task.result_status || task.state : task.state)}</span></div><p className="text-xs text-text-secondary mt-2">{task.attempts} attempts / {task.depends_on.length ? `Depends on ${task.depends_on.join(", ")}` : "Independent task"}</p></div>)}<p className="text-xs text-text-secondary mt-5">Recorded runtime: {(report.elapsed_ms / 1000).toFixed(1)}s</p></div>}
          </div>
        </>}
      </article>
    </div>
  </section>;
}