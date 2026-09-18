# Deeper Research and the Next Agents

## Natural Commands Available Now

Chat and transcribed voice share the same deterministic router. No agent name is required:

| Request | Current behavior |
| --- | --- |
| "Search about Python releases" / "search on solar energy" | Delegate the topic to Scout, Atlas and Prism |
| "Google FastAPI authentication" / "find out about local speech models" | Delegate public-web research |
| "I need you to search for SQLite WAL" | Delegate the exact extracted question |
| "Research status" / "how is my research going?" | Read actual runtime progress |
| "What did you find?" / "show me the research results" | Return available findings/report information |
| "Play a game" / "quiz me" | Start Arcade's five-question developer quiz |
| "Answer B" / "skip question" / "quiz status" / "stop game" | Operate the current quiz without invoking the model |

Local file, inbox and repository searches are excluded from public-web delegation, including explicit requests to the research agent. Negative requests and explanations about searching do not start research. Matching phrases is not general language understanding: ambiguous project work should require clarification and must not be silently converted into web research or claimed as executed.

Arcade is an implemented local conversation game, not a registered governed agent. It has deterministic answer validation, explanations, score, repeat, skip and stop. Five questions are sampled from a small curated developer question bank. It has no LLM, filesystem, network or shell access, does not appear as a research graph, and stores no durable score. State belongs to the current backend conversation-service instance; this is a single-user local feature, not isolated multi-user sessions. Bare A/B/C answers are consumed only during an active quiz; unrelated conversation and research requests still route normally.

## Accessible Task Updates

The native Agents view in NOVA at `http://127.0.0.1:1420/` and the standalone backend monitor at `/agents` have polite, atomic screen-reader status regions for the selected run. They announce actual run/task states and finished/successful counts when they change, not on every poll or elapsed-time update. A labelled, keyboard-operable volume button optionally speaks the same updates. Speech starts off, uses only an English voice marked local by the browser, and is disabled if none is available. Turning it off or hiding/leaving the view stops its speech. A lost connection announces unavailable status rather than stale success. Screen-reader announcements remain available without browser speech; use one mechanism to avoid double speech.

This is task-status accessibility, as requested, not screen capture or reading other applications. No microphone, camera or accessibility permission is requested. Browser speech requires the monitor page to remain open and is separate from desktop Speak Back. Actual VoiceOver/audible hardware acceptance remains outstanding; tests intercepted speech rather than playing it.

## Implemented Research Workflow

Scout, Atlas and Prism are named tasks using the governed `research_agent`, not separate capability grants.

| Task | Searches | Page attempts | Purpose |
| --- | --- | --- | --- |
| Scout | Up to 2 | Up to 1 | Topic overview and official/primary-source discovery |
| Atlas | Up to 2 | Up to 1 | Independent sources, evaluation and limitations |
| Prism | Up to 3 | Up to 2 | Direct synthesis, corroboration and conditional recommendations |

Page reads are enabled at startup by `AGENT_RUNTIME_READ_PAGES=True`. Disabling the setting restores the previous 3/3/5 search-only allocation. Grants cannot be expanded by an agent during a run.

All Scout and Atlas comparison points are supplied to Prism as untrusted context. Their citations are not transferred as if Prism produced them: Prism must cite evidence obtained through its own broker calls. Search expansions remain anchored to the original question rather than appending potentially unrelated upstream claims. The exact question is included in the model input, with instructions to exclude tangents and similarly named entities. This examines available evidence, not every possible source or option.

Each search queries DuckDuckGo, Bing, Brave and Google concurrently through DDGS, requesting up to 20 candidates per provider before filtering and URL deduplication. Candidates are ranked against the original question, not the expanded search phrase. Source and image scores range from 0 to 100 and include matched/missing terms; these are lexical relevance scores, not factual confidence or visual verification. Hostname diversity breaks ranking ties. Explicitly quoted phrases must appear in the title or snippet; this conservative filter can miss relevant pages with incomplete snippets. One provider can fail without discarding another's results. All providers failing is a retrieval failure, not an empty successful answer. These providers do not cover every website or subject exhaustively.

Each broker search returns at most eight text records. At most five previously unreviewed source URLs per query are supplied to the model. Page-enabled tasks reserve 6,000 characters for search snippets within the existing 14,000-character evidence-block ceiling; each HTML extract is capped at 3,000 text characters. Extracts that do not fit after wrapping are recorded as downloaded but excluded from context. The adapter also enforces its tokenizer-based context and output limits. Coverage separates retrieved records, downloaded extracts and evidence actually supplied to the model. These are not counts of independent studies.

The page tool reads only HTTPS URLs discovered by a search in the same task, selecting higher relevance scores first. Every request resolves all DNS addresses, rejects disallowed addresses, and connects to a pinned address with the original Host and TLS name. Robots rules are checked; unavailable rules, crawl-delay/request-rate requirements and cross-host redirects are denied. At most three same-host redirects are followed, with fresh DNS and policy checks. Each invocation has a 12-second limit, a 512 KiB HTML download cap and a 64 KiB robots cap. Compressed/non-HTML responses, authenticated URLs, cookies and proxy inheritance are not supported. No links are recursively followed. HTML parsing uses a bounded input and network-disabled lxml parser, not a process sandbox. Page extracts are wrapped as untrusted content and receive task-owned evidence IDs; raw page bodies are not stored in reports or audit records.

The graph allows up to 11 broker tool calls and 48,000 metered model tokens total. Each task remains inside the existing 120-second static grant, with a six-minute graph ceiling and two concurrent research tasks. Smaller existing plans retain their own tool-call limits. Search-provider requests and image lookups inside a tool invocation are not separate broker tool calls. No write, shell, private-file or arbitrary network-fetch permission was added.

Research requests use Ollama's schema-constrained JSON generation, followed by the existing strict validation and manager-owned citation checks. Schema errors produce a safe failure code without logging raw output. The previous unbudgeted schema-repair call has been removed: these plans grant zero retries. Unknown model usage still fails closed, reserves the remaining allowance, and is never retried. If one independent researcher fails, the other can finish; Prism is skipped when required inputs are unavailable. Budget exhaustion and explicit cancellation still stop the graph.

## Prism Reports

- A bright Key takeaways section shows up to three priority-ranked Prism findings with source links.
- Findings can identify a subject and be classified as a finding, agreement, trade-off, contradiction or recommendation.
- Comparison shows the researcher, subject, category and cited statement.
- Coverage shows each query, provider candidate counts, retrieved/model-supplied records and cited domains. Page attempts separately show downloaded, supplied, truncated, unavailable or denied outcomes; repeated URLs count per attempt.
- Missing searches and failed providers do not justify a complete-evidence claim. Rejected Prism findings never enter the highlighted summary.
- Reports distinguish provider outages, invalid token accounting, model timeouts, rejected requests, schema failures and skipped synthesis. Empty relevant claims are partial, never unsupported success.
- Existing saved reports remain readable. The extra fields appear on newly generated reports, not by silently rewriting history.
- Existing brief acknowledgement, completion speech and report navigation remain in place.

## Image Relevance

Image lookup is constrained to the exact pages returned by the same text search, ignoring URL fragments but not treating other pages on the same domain as equivalent. Candidate titles must overlap meaningful source-title terms, retain numeric identifiers from that title and match explicitly quoted query phrases. URL and thumbnail-host protections remain unchanged. No qualifying candidate means no images; a separate generic image result is never used as filler.

Final reports publish an image only when its page is cited by a valid finding from the same accepted researcher task. An available but uncited source is insufficient. The native port-1420 Images tab also filters older saved candidates against source pages cited by findings, without modifying saved reports. External image loading remains opt-in.

These conservative checks can exclude useful pictures and do not inspect image pixels, verify identity or prove that a thumbnail depicts the requested subject. New retrieval/report filtering requires the owner to reload the backend; the native legacy-image display filter is frontend-only. Verification: 313 backend tests and 88 desktop tests passed. The open native report's Images tab showed the empty matched-image state with zero loaded images and no horizontal overflow; no live search or backend restart was performed.

## What This Does Not Prove

This workflow reads search snippets and bounded HTML extracts, not every page, complete long documents, PDFs or JavaScript-rendered content. Primary-source search wording does not authenticate a page as primary evidence. Hostname diversity is not proof of independence: different sites may syndicate the same material. Current citation verification establishes evidence identity and task ownership; it does not automatically establish that every cited statement is factually correct or fully entailed by the source. Prompts request balanced comparisons, but there is no guarantee of exhaustive coverage or a correct winner.

Broader searches can take longer, and slow providers may exhaust the unchanged deadlines. Results then remain partial or failed. Section-aware extraction, isolated PDF parsing and stronger independent claim verification remain future work.

Latest offline verification: 343 backend tests and 90 desktop tests passed. The page graph tests cover the unchanged 11-call budget, four page attempts, page citations, unavailable-page fallback and persisted coverage. Simulated native coverage was checked at 1440x1000 and 390x844 with no horizontal overflow. No live research/model job or backend restart was performed for this slice; production-build errors recorded in the platform handoff remain unresolved.

## Next Agents, in Order

These are proposals, not implemented agents or activated grants.

| Agent | Deliverable | Prerequisites and limits |
| --- | --- | --- |
| Reader | Section-aware HTML and PDF passages with section/page references | Bounded broker-owned HTML retrieval is implemented above. A dedicated Reader agent, isolated PDF parsing and passage-level references are still proposed. Start without authenticated sites. |
| Verifier | Claim-by-claim support, contradictions, freshness and unresolved questions | Reader evidence; separate executor/verifier identities; explicit support checks and calibrated tests. Citation presence alone cannot count as verification. |
| Watch | Changes to approved topics, products, releases or advisories | User-approved topics and schedule, bounded recurring budgets, persisted deduplication, quiet hours and stop controls. No unrestricted background searches. |
| Code Reviewer | Architecture review, risk list and proposed changes for a selected repository | Read-only repository tool with path scope and secret filtering. No edits or shell execution in the first version. |
| QA Runner | Reproducible test results for approved code changes | Isolated workspace, structured allowlisted test commands, hard time/resource limits and evidence from actual execution. Remain independent of the coding agent. |
| Security Analyst | Read-only asset/CVE correlation and prioritized remediation proposals | Explicitly scoped inventory/advisory connectors and read-only database access. Credentials remain opaque handles. Remediation is a separate approval-bound workflow. |

Recommended next milestone: Reader + Verifier on public documentation, with an offline fixture suite covering redirect/SSRF denial, malicious page instructions, unsupported claims, repeated sources and stale evidence. Only after that should NOVA add recurring Watch jobs or code execution.

## Daily Developer Agent Roadmap

The following names describe proposed roles, not registrations, tools, background jobs or capabilities already enabled. Prefer a few verifiable workers over a large collection of prompts pretending to be independent agents. Build on the P1 connection scope and P3/P4 worker isolation in the companion roadmap.

| Role | Natural request | Artifact and verification gate |
| --- | --- | --- |
| Compass: task planner | "Add login to this project" | Clarified goal, repository identity, acceptance checks, task graph, budgets and required approvals; never executes its own plan |
| Repo Reader | "Explain how authentication works here" | Scoped file/symbol references and dependency map; deny paths outside the approved root, symlink escapes and secrets |
| Debugger | "Fix this failing test" | Reproduce a specific failure in an isolated copy, record sanitized evidence and a testable hypothesis; no guessed root-cause claims |
| Forge: patch builder | "Create a paginated API" | Proposed diff and tests in a disposable worktree/copy; preserve dirty files, deny host writes and require action-bound approval before applying to the chosen working tree |
| QA Runner | "Test the change" | Execute discovered project tests in a resource-bounded sandbox with no production credentials or default network; report commands, exit codes, coverage and exclusions |
| API Examiner | "Test my API validations" | OpenAPI-derived request/auth/error matrix against an explicitly approved disposable endpoint; use existing frameworks such as Schemathesis where appropriate, never destructive production testing |
| Reviewer | "Review this patch before applying it" | Independent diff review, regression/security findings and acceptance evidence; cannot self-certify Forge's work |
| Docs and Release Assistant | "Update the docs for this change" | Diff-backed documentation and draft release notes; publishing, committing, tagging and pushing require separate approval |
| Dependency Analyst | "Which dependencies need attention?" | Lockfile/SBOM-backed outdated and vulnerability findings, licenses and proposed upgrade diff; no automatic installs or upgrades |
| Daily Briefing / Organizer | "Summarize today's approved project work" | Task, build and PR summaries with source times; calendars, inboxes, tickets and reminders need scoped connectors and explicit scheduling consent |
| Arcade extensions | "Give me a debugging puzzle" | Curated code-reading puzzles, language/topic selection and opt-in local scores; executing submitted code requires the same sandbox as QA |

### Proposed Project Workflow

1. Interpret the desired outcome rather than requiring an agent name. Resolve the selected repository, branch/worktree, permitted paths and acceptance checks. Ask one focused question if the target or requested effect is ambiguous. Treat "this" as unresolved unless an explicit selected-project context exists.
2. Create a durable task identity and show its scope, plan, budget and approval requirements before scheduling. A model may propose an intent, but strict schemas and manager policy decide which registered tools can run. Never grant permissions from confidence scores or a conversational "yes" detached from an exact action.
3. Read and reproduce in an isolated workspace. Record the baseline and preserve unrelated changes. Inspect project scripts as untrusted code; a disposable Git worktree alone is not filesystem/process/network isolation.
4. Build the patch and have a separate worker run verification. Attach the patch, test evidence and reviewer findings to the same task. Test failures remain failures even if the code-generating agent says the task is complete.
5. Present a reviewable diff and exact action-bound approval to apply changes. Changed patches invalidate approvals. On interruption, reconcile unknown write outcomes before retrying. Do not auto-commit, push, deploy or run migrations.
6. Provide a concise outcome, changed paths, test results and remaining gaps; retain inspectable artifacts. Announce real transitions using the task-update controls, not invented percentages or periodic "still working" messages.

Planned task phases: `NEEDS_SCOPE -> PLANNED -> AWAITING_APPROVAL -> QUEUED -> RUNNING -> VERIFYING -> NEEDS_REVIEW -> COMPLETED`, with explicit `BLOCKED`, `FAILED`, `PARTIAL`, `CANCELLED` and `OUTCOME_UNKNOWN` outcomes. These are proposed product phases, not additions to the current runtime enum. The future task screen should show current worker, last real event, elapsed time, acceptance checks, blockers, artifact links and cancel control. Current monitor announcements cover actual graph/task states, including the repository reader.

### Delivery Order

1. Delivered in this slice: ordinary research commands, natural progress/results commands, accessible research status and the local developer quiz.
2. Implemented coding slice: explicit-file read-only repository review, scoped durable reports and native Agents submission. Live model and owner acceptance remain pending; this is not a repository-wide autonomous coding workflow.
3. After isolation and approval tests: reproduce one failing test, propose one patch, independently verify, then apply only the approved diff to the pilot repository.
4. Extend to API validation, documentation, dependency checks and scheduled briefings after the corresponding connectors and acceptance gates exist. Reader/Verifier improvements remain the next research-specific slice.

The project-writing pipeline is not implemented by this roadmap update. No new write grants, arbitrary shell channel, screen capture, private-account connector or scheduled job is enabled.

### Repository Reader

The user selected `nova-desktop` as the read-only developer-agent pilot. The first boundary is implemented in [RepositoryReadTool](../../services/tools/repository_read_tool.py), with an approved root injected by trusted setup, not supplied in model tool arguments. Each call reads one explicit relative UTF-8 source/document file, capped at 64 KiB, and returns its content digest. It does not enumerate the repository, execute scripts, write files or use the network.

Descriptor-relative opens reject symlinks; checks also deny traversal, hidden paths, dependency/build/data/config directories, hard-linked files, special files, oversized/binary content, replaced roots and detected changes during reading. Sensitive names and recognized secret patterns fail closed without returning file content. Secret detection is heuristic, not a guarantee that arbitrary source files contain no private data; it can also reject harmless fixtures or identifiers.

The [repository worker](../../services/agent_runtime/agents/repository_reader.py) is now wired through the governed runtime. Startup adds the separate static [repository policy](../../services/agent_runtime/policy/repository_capabilities.yaml) only when `AGENT_RUNTIME_REPOSITORY_ENABLED` is true (default), the fixed sibling `nova-desktop` directory exists without being a symlink, and durable report storage is available. It is not registered with the legacy chat tool router. The broker enforces `repo.read`, the fixed repository identity and the exact file list on every invocation; web search, shell and writes are not granted.

In NOVA at `http://127.0.0.1:1420/`, open **Agents > Repository review**, enter a question and one to three explicit relative file paths, and submit. The UI requires the backend to advertise `repo_reader`; an older running backend will leave submission disabled until its owner reloads it. `POST /api/agent-runtime/repository-review` uses the existing local-client/host/origin guard, a fixed repository identifier, and strict request fields. There is no automatic discovery, general path selector or natural-language routing to private files.

The service persists the selected scope before acknowledging the queued task. A single Repo Reader graph uses the existing cancellation, audit, model metering and independent manager citation checks. Budgets are 120 seconds, three tool calls, 16,000 model tokens, zero retries and zero monetary budget; the existing configured local runtime model remains unchanged. At most 18,000 characters of wrapped file content are supplied; excluded or unavailable files produce a partial outcome. The broker recomputes file content hashes, mints task-owned `file_content` evidence and wraps source text as untrusted. Audit records contain scope and evidence metadata, not raw file contents. Saved reports contain selected paths, findings, evidence references/digests and task outcomes, not full source snapshots. Sources render as non-navigating file references. Restart recovery marks unfinished reports interrupted.

Tests use temporary source fixtures and a fake model, not the user's repository contents. Real local model review quality and live startup remain unverified. A matching evidence ID proves source ownership, not factual entailment or a sound code review; secrets filtering is heuristic and tests are never claimed to have run. Preserve the selected pilot and do not broaden access or enable shell/write grants. Offline tests live in [repository reader tests](../../tests/test_repository_read_tool.py).

## Useful Workflows

The current trio can prepare source-linked product comparisons, technology evaluations, initial literature surveys, alternatives/risks briefs and implementation research. Reader and Verifier would make those briefs more dependable. Code Reviewer and QA Runner would then support a supervised research-to-implementation loop: research options, propose a change, obtain approval, test in isolation and report actual evidence.

## Validation

Offline checks cover topic-sensitive queries, objective propagation, task budgets, same-task citation ownership, source deduplication, provider fallback, quoted-entity filtering, partial retrieval, independent-task survival, safe failure reporting and rejection of unsupported highlights.

2026-09-16 verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests/test_agent_runtime_*.py tests/test_web_search_structured.py -q` passed 245 tests. An isolated live public-topic graph using the configured Qwen/Ollama adapter completed Scout, Atlas and Prism with 17 findings, 18 cited sources and 11 searches. Atlas succeeded; Scout and Prism were partial because three search invocations failed across providers. The audit chain verified. Live testing also caught unsupported grammar from additional field-length constraints; those additions were removed and the existing strict schema passed a synthetic probe and the full live graph.

Live checks used in-memory report/audit storage and isolated legacy event/audit sinks while retaining the real broker and authorization gate. No saved user reports were modified. The main backend was not restarted; its status endpoint timed out during the initial check. Reload it to load these changes. Historical desktop/mobile previews used simulated report data; this change did not revalidate the desktop UI. Provider availability and factual relevance still require evaluation on the user's actual questions; this is not exhaustive web coverage or full-page verification.

2026-09-17 natural-command/game/accessibility slice: `node --check services/gateway/ui/agents.js` passed. `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests/test_agent_runtime_*.py tests/test_web_search_structured.py tests/test_developer_quiz.py tests/test_voice_conversation_turns.py -q` passed 304 tests. Browser tests on an isolated monitor verified default-off speech, keyboard toggle, unchanged-snapshot deduplication, accurate partial outcomes and rejection of non-local voices. Desktop 1440x1000 and mobile 390x844 checks had no horizontal overflow; screenshots inspected. Speech and task data were simulated, no audio or real research started, and the fixtures were removed. The main backend's `/agents` request timed out and it was not restarted. Reload it for new natural commands and the quiz; refresh the monitor for status speech. End-to-end validation in the live desktop remains an owner acceptance step.