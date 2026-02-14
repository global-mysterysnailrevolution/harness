# ContextForge Landscape Research

## Comparison Table

| Project/Product | Key Features | Artifacts Generated | Strengths | Weaknesses | Security Risks | Steal / Avoid |
|---|---|---|---|---|---|---|
| **SummonAI Kit** | Repo analysis, tech stack detection, skill/agent/hook generation | `.claude/CLAUDE.md`, `skills/*.md`, `agents/*.md`, `hooks/`, `settings.json` | Complete artifact set; auto-detects 8+ languages and frameworks; generates hooks for auto-loading | Paid ($199-$599); Claude Code only; generated skills are generic templates, not deeply project-specific | Low (runs locally, no network calls during generation) | **Steal**: artifact structure (CLAUDE.md + skills/ + agents/); **Avoid**: generic framework skills that add bloat |
| **Repomix** | Codebase packing into AI-friendly single files; experimental skill generation | Single XML/MD/TXT file; or `.claude/skills/` directories | Tree-sitter powered compression; token counting; Secretlint security check; 21k+ stars | Produces one monolithic context dump (non-goal for us); skill generation is experimental | Low (local only; Secretlint catches secrets) | **Steal**: Tree-sitter for structure extraction; Secretlint integration; **Avoid**: mega-context-dump approach |
| **Claude Code Hooks** | 14 lifecycle events; deterministic shell/LLM triggers; exit-code control | Hook scripts in `.claude/settings.json` | True deterministic control; `PreToolUse`/`PostToolUse` for security gates; `PreCompact` for memory safety | Claude Code specific; hooks must be fast (<10s timeout); no cross-session state | Hook scripts run with user's full permissions; malicious hooks can exfiltrate data | **Steal**: exit-code-based control flow (0=ok, 2=block); hook lifecycle model; **Avoid**: LLM-type hooks for security-critical decisions |
| **Claude Code Skills** | Reusable markdown knowledge packs; slash-command invocation; can include scripts | `SKILL.md` + supporting scripts in skill directory | Clean abstraction; can bundle shell scripts for deterministic actions; personal vs project scoping | No formal schema; no versioning; no provenance headers; no validation | Skills from untrusted sources could contain prompt injection in markdown | **Steal**: SKILL.md + scripts pattern; personal/project scoping; **Avoid**: no-schema approach |
| **Claude Code Subagents** | Isolated execution contexts; parallel tasks; summarized results returned | Agent markdown definitions | True context isolation; prevents cross-contamination; lifecycle hooks (SubagentStart/Stop) | No built-in tool allowlists (must be configured manually); results are summarized (lossy) | Subagent can be tricked by injected context; isolation is context-level, not sandbox-level | **Steal**: context isolation pattern; lifecycle hooks; **Avoid**: assuming isolation = security |
| **OpenClaw memory-core** | File-backed memory; session memory search; hybrid vector+text query | `MEMORY.md`, `memory/YYYY-MM-DD.md` | Built-in to OpenClaw; hybrid search (0.7 vector + 0.3 text); session memory across conversations | No approval workflow for new rules; no provenance on memory entries; no pending/promoted states | Memory poisoning: injected content becomes permanent rules if compaction flush isn't guarded | **Steal**: hybrid search config; compaction safeguard mode; **Avoid**: trusting all compaction flushes equally |
| **OpenClaw memory-lancedb** | LanceDB vector backend for long-term memory; auto-recall/capture | Vector-indexed memory store | Better retrieval quality than file-based; auto-capture of relevant context | Separate plugin (not always available); no approval gates | Same poisoning risks as memory-core but harder to audit (binary vector store) | **Steal**: vector backend for search quality; **Avoid**: auto-capture without approval |
| **QMD (Quick Memory/Doc)** | BM25 + vector + reranking; MCP server interface | Indexed search results | Fast local search; multiple retrieval strategies; MCP-compatible | Separate service to maintain; requires openclaw-mcp-plugin (fragile integration) | MCP transport could be intercepted if not on localhost | **Steal**: multi-strategy retrieval; **Avoid**: depending on fragile MCP plugin integration |
| **MCPJungle** | MCP gateway; tool groups; auth; monitoring | Config-driven server registry | Centralized management; OpenTelemetry support; tool groups per agent | Another service to maintain; adds latency | Gateway is single point of compromise if breached | **Steal**: tool groups concept; centralized routing; **Avoid**: exposing gateway to public network |
| **Trivy/Gitleaks/Semgrep** | Vulnerability scanning, secret detection, static analysis | SARIF/JSON reports, SBOM (CycloneDX) | Industry standard; well-maintained; composable | Each is a separate install; some are slow on large repos | Low (read-only scanners) | **Steal**: all of them as pipeline stages; **Avoid**: making any single scanner a hard requirement |
| **LLM Guard** | Prompt injection detection via fine-tuned DeBERTa model | Confidence scores | Better than regex for detecting injection; local model (no API calls) | Python-only; model download required; false positives on legitimate instructions | Low (defensive tool) | **Steal**: as optional vetting stage; **Avoid**: using as sole injection defense |
| **GitHub MCP Server (Anthropic)** | Official GitHub integration via MCP | API access to repos, issues, PRs | Official support; comprehensive API coverage | Critical prompt injection vulnerability (May 2025): malicious issues can hijack agent | **HIGH**: PATs grant sweeping access; injected instructions in issues cause data exfiltration | **Steal**: nothing (use `gh` CLI with scoped tokens instead); **Avoid**: broad PAT permissions |
| **MCP Server Ecosystem** | 16k+ servers (as of mid-2025); growing rapidly | Varied | Huge ecosystem; many useful integrations | 48% recommend insecure credential storage; many have command injection flaws | **HIGH**: supply-chain poisoning; credential harvesting; command injection; no vetting standard | **Steal**: the useful tools (after vetting); **Avoid**: trusting any without quarantine+scan |
| **Cursor Rules / .cursorrules** | Project-level AI configuration | `.cursorrules` or `.cursor/rules/*.md` | Simple; works in Cursor IDE; can encode conventions | IDE-specific; no versioning; no provenance; easily overridden | Prompt injection via committed rules files | **Steal**: the idea of project-scoped conventions; **Avoid**: IDE-specific format lock-in |
| **AGENTS.md (OpenClaw)** | Agent instructions, personality, learning loop | Single markdown file in workspace | Simple; always loaded; includes memory safety rules | Single file grows unwieldy; no modularity; no schema | Content can be modified by the agent itself (self-modification risk) | **Steal**: Learning Loop pattern; memory safety guardrails; **Avoid**: monolithic agent instruction file |
| **Docker-based sandboxing** | Container isolation for tool execution | Containerized tool environments | True process-level isolation; filesystem restrictions; network control | Overhead; complexity; not all tools containerize easily | Container escape is rare but possible; shared volumes are attack surface | **Steal**: as the execution model for untrusted tools; **Avoid**: assuming containers are impenetrable |

## Design Principles (grounded in survey)

1. **Sidecar, not plugin.** ContextForge runs alongside OpenClaw as a standalone service. OpenClaw must boot and function even if ContextForge is down. (Grounded in: OpenClaw's `exit(1)` on unknown plugins; GitHub MCP server vulnerability showing fragile integrations.)

2. **Spec-first, generate-second.** Define formal schemas for every generated artifact (skills, agents, events, memory entries) before writing any generator code. (Grounded in: Claude Code skills have no formal schema, leading to inconsistent formats; SummonAI Kit's artifacts lack validation.)

3. **Deterministic gates, LLM reasoning only where necessary.** Security scanning, secret detection, config validation, and approval workflows must be deterministic (scripts, scanners, exit codes). LLM reasoning is only for analysis and generation, never for security decisions. (Grounded in: Claude Code hooks use exit codes for control; LLM Guard has false positives; prompt injection is structural.)

4. **Quarantine everything external.** Every new tool, skill, MCP server, or dependency passes through quarantine -> scan -> human approval -> promote. No exceptions. (Grounded in: 48% of MCP servers have insecure credential handling; GitHub MCP prompt injection; supply-chain poisoning.)

5. **Secrets never in context.** Secrets are never written to memory files, generated docs, logs, or prompts. Use env vars and secret stores. Redact aggressively at every boundary. (Grounded in: MCP credential leaks; memory poisoning risk; Gitleaks findings in real repos.)

6. **Pending-to-promoted for durable memory.** New rules/learnings go to a pending queue. A human (or trusted approval gate) must promote them to durable memory. This prevents prompt injection from becoming permanent rules. (Grounded in: OpenClaw memory-core has no approval workflow; AGENTS.md self-modification risk.)

7. **Provenance on every artifact.** Every generated file includes: generator version, timestamp, source commit hash, and analysis hash. This enables reproducibility auditing and "was this regenerated from the same source?" checks. (Grounded in: SummonAI Kit and Repomix generate files with no provenance.)

8. **Idempotent generation.** Running the generator twice on the same source must produce identical output. Non-deterministic LLM outputs are cached and pinned by source hash. (Grounded in: reproducibility requirement; prevents spurious diffs.)

9. **Minimal, not maximal context.** Generate only what's necessary. Avoid "mega context dumps" (explicit non-goal). Skills should be loaded on-demand, not all-at-once. (Grounded in: Repomix's monolithic approach wastes tokens; SummonAI Kit generates 15+ skills when 3-5 are typically useful.)

10. **Correlation IDs everywhere.** Every operation gets a `run_id`. Every tool call, memory write, artifact generation, and UI event is tagged with correlation IDs for end-to-end traceability. (Grounded in: existing harness audit log lacks global correlation; debugging without trace IDs is blind.)

11. **Graceful degradation, not crash loops.** Missing scanners skip with a warning. Unreachable services return degraded status. Failed health checks trigger rollback, not infinite restarts. (Grounded in: ConfigGuard's auto-rollback pattern; existing harness tool vetting graceful degradation.)

12. **Composable-tool escalation is a real threat.** Two individually safe tools can create an unsafe system when chained (e.g., Git + Filesystem = RCE). Runtime policy must classify action *chains*, not just individual calls. (Grounded in: Anthropic Git MCP vulnerability; MCP server command injection flaws.)

## Citations

- SummonAI Kit: https://summonaikit.com/docs
- Repomix: https://repomix.com/ / https://github.com/yamadashy/repomix
- Repomix Agent Skills: https://repomix.com/guide/agent-skills-generation
- Claude Code Hooks (14 events): https://claudefa.st/blog/tools/hooks/hooks-guide
- Claude Code Hooks Reference: https://docs.claude.com/en/docs/claude-code/hooks
- Claude Code Skills & Subagents: https://code.claude.com/docs/en/features-overview
- MCP Credential Exposure (48%): https://www.trendmicro.com/vinfo/ae/security/news/vulnerabilities-and-exploits/beware-of-mcp-hardcoded-credentials-a-perfect-target-for-threat-actors
- GitHub MCP Prompt Injection: https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/
- MCP Prompt Injection (Snyk): https://labs.snyk.io/resources/prompt-injection-mcp/
- MCP Server Security Guide (Snyk): https://snyk.io/articles/building-secure-mcp-servers/
- MCP Exploitation (GBHackers): https://gbhackers.com/mcp-servers/
