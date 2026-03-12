I now have a comprehensive understanding of the entire current harness. Let me compile the architecture plan.

---

# Go Harness Architecture Plan

## Overview

Replace the current distributed harness (bash hooks, Node.js trace server, markdown-encoded Python/PowerShell logic that runs "in the LLM's head") with a single Go binary that operates in two modes: direct CLI and MCP server. The markdown agent/command/skill files stay untouched -- Claude Code reads them natively. The Go binary handles all the runtime logic that currently lives as prompt-engineering-encoded behavior.

## 1. Go Module Structure

### Repository Layout

```
harness/
  go.mod                          # module github.com/global-mysterysnailrevolution/harness
  go.sum
  main.go                         # single entrypoint → cmd.Execute()
  
  cmd/
    root.go                       # cobra root command, global flags (--config, --verbose, --json)
    serve.go                      # harness serve → MCP server mode
    vet.go                        # harness vet <path>
    audit.go                      # harness audit [--query] [--filter] [--tail]
    classify.go                   # harness classify <tool-id> [args-json]
    route.go                      # harness route <task-description>
    intake.go                     # harness intake <project-path>
    supervise.go                  # harness supervise <task>
    forge.go                      # harness forge <name> [url]
    checkpoint.go                 # harness checkpoint
    config.go                     # harness config [get|set|validate]
    version.go                    # harness version
  
  internal/
    config/
      config.go                   # Config struct, loader, validator
      defaults.go                 # Default policies, allowlists
      schema.go                   # JSON Schema validation for policy files
    
    audit/
      writer.go                   # JSONL append-only writer with file locking
      rotation.go                 # Log rotation (size-based, count-based)
      reader.go                   # JSONL reader with streaming
      query.go                    # Filter engine (agent, tool, action class, time range)
      tail.go                     # Real-time tail mode (fsnotify)
      types.go                    # AuditEntry, AuditQuery, AuditFilter
    
    classify/
      classifier.go              # Action classifier (keyword scoring)
      policy.go                   # Policy evaluation against allowlists
      types.go                    # ActionClass enum, ClassifyResult, AllowlistEntry
    
    vet/
      pipeline.go                # Scanner orchestration (parallel exec, collect results)
      scanner.go                  # Scanner interface + registry
      trivy.go                    # trivy scanner adapter
      gitleaks.go                 # gitleaks scanner adapter
      semgrep.go                  # semgrep scanner adapter
      licensee.go                 # license checker adapter
      depcheck.go                 # dependency checker adapter
      secretscan.go               # pattern-based secret scanner (built-in)
      pathtraversal.go            # path traversal detector (built-in)
      report.go                   # VettingReport generation, policy evaluation
      types.go                    # ScanResult, ScanFinding, Severity
    
    discover/
      skills.go                   # Scan ~/.claude/skills/, ~/.claude/commands/
      plugins.go                  # Scan ~/.claude/plugins/
      mcp.go                      # Parse .mcp.json files
      registry.go                 # Unified capability registry
      types.go                    # Capability, SkillMeta, PluginMeta
    
    route/
      router.go                   # Task→skill matching (keyword + domain scoring)
      scorer.go                   # Scoring algorithm
      types.go                    # RouteResult, MatchScore
    
    intake/
      scanner.go                  # Project scanner (detect stack, conventions, tools)
      detectors.go                # Per-stack detectors (node, python, go, rust, etc.)
      types.go                    # IntakeResult, StackInfo, Conventions
    
    supervisor/
      supervisor.go               # Orchestration loop (task classification, gating)
      gates.go                    # Gate enforcement (wheel-scout, budget)
      decompose.go                # Task decomposition → dependency graph → waves
      types.go                    # TaskPlan, Wave, SubTask, SupervisorState
    
    mcp/
      server.go                   # MCP server implementation (stdio transport)
      tools.go                    # Tool definitions → MCP tool schemas
      handler.go                  # Request handler (routes MCP calls → internal functions)
      types.go                    # MCP protocol types (if not using a library)
    
    forge/
      generator.go               # MCP server generator from API specs
      openapi.go                  # OpenAPI/Swagger spec parser
      templates.go                # Go templates for generated code
      types.go                    # ForgeSpec, Endpoint, ForgeResult
    
    checkpoint/
      writer.go                   # Memory checkpoint writer
      types.go                    # CheckpointState
  
  pkg/
    frontmatter/
      parser.go                   # YAML frontmatter parser for .md files
    
    jsonl/
      reader.go                   # Generic JSONL reader/writer
      writer.go
    
    exec/
      runner.go                   # Subprocess runner with timeout, output capture
```

### Key Types (defined across the `types.go` files above)

```go
// internal/config/config.go
type Config struct {
    ClaudeDir      string              `json:"-"` // resolved at startup
    AuditDir       string              `json:"audit_dir"`
    AuditMaxBytes  int64               `json:"audit_max_bytes"`
    AuditMaxFiles  int                 `json:"audit_max_files"`
    ActionPolicy   ActionPolicy        `json:"action_policy"`
    VettingPolicy  VettingPolicy       `json:"vetting_policy"`
    Allowlists     map[string]Allowlist `json:"allowlists"`  // role → allowed tools
    ScannerPaths   map[string]string   `json:"scanner_paths"` // scanner → binary path override
    TokenEstimates map[string]TokenEst `json:"token_estimates"`
    ModelCosts     map[string]CostRate `json:"model_costs"`
}

type ActionPolicy struct {
    Rules []ActionRule `json:"rules"`
}

type ActionRule struct {
    Pattern  string   `json:"pattern"`   // regex for tool_name
    Class    string   `json:"class"`     // read, write, exec, network, credential
    Keywords []string `json:"keywords"`  // scoring keywords
    Weight   float64  `json:"weight"`    // keyword weight
}

type VettingPolicy struct {
    Scanners       []string           `json:"scanners"`        // enabled scanners
    FailThresholds map[string]int     `json:"fail_thresholds"` // severity → max count
    BlockPatterns  []string           `json:"block_patterns"`  // always-fail patterns
}

type Allowlist struct {
    Tools   []string `json:"tools"`
    Denied  []string `json:"denied"`
    Reason  string   `json:"reason"`
}

// internal/audit/types.go
type AuditEntry struct {
    Timestamp   time.Time              `json:"ts"`
    SessionID   string                 `json:"sid"`
    Project     string                 `json:"project"`
    CWD         string                 `json:"cwd"`
    Phase       string                 `json:"phase"`       // "pre" or "post"
    Tool        string                 `json:"tool"`
    ActionClass string                 `json:"action_class"`
    AgentRole   string                 `json:"agent_role,omitempty"`
    Input       map[string]any         `json:"input,omitempty"`
    Output      map[string]any         `json:"output,omitempty"`
    HasError    bool                   `json:"has_error,omitempty"`
    DurationMs  int64                  `json:"duration_ms,omitempty"`
    Allowed     bool                   `json:"allowed"`
    DenyReason  string                 `json:"deny_reason,omitempty"`
}

type AuditQuery struct {
    SessionID  string     `json:"sid,omitempty"`
    Tool       string     `json:"tool,omitempty"`
    ActionClass string    `json:"action_class,omitempty"`
    AgentRole  string     `json:"agent_role,omitempty"`
    Since      time.Time  `json:"since,omitempty"`
    Until      time.Time  `json:"until,omitempty"`
    HasError   *bool      `json:"has_error,omitempty"`
    Limit      int        `json:"limit,omitempty"`
}

// internal/classify/types.go
type ActionClass string
const (
    ActionRead       ActionClass = "read"
    ActionWrite      ActionClass = "write"
    ActionExec       ActionClass = "exec"
    ActionNetwork    ActionClass = "network"
    ActionCredential ActionClass = "credential"
    ActionDestructive ActionClass = "destructive"
)

type ClassifyResult struct {
    Tool        string      `json:"tool"`
    ActionClass ActionClass `json:"action_class"`
    Score       float64     `json:"score"`
    Allowed     bool        `json:"allowed"`
    DenyReason  string      `json:"deny_reason,omitempty"`
    Keywords    []string    `json:"matched_keywords,omitempty"`
}

// internal/vet/types.go
type Scanner interface {
    Name() string
    Available() bool                                    // exec.LookPath check
    Scan(ctx context.Context, path string) ([]Finding, error)
}

type Finding struct {
    Scanner    string   `json:"scanner"`
    Severity   Severity `json:"severity"`   // critical, high, medium, low, info
    Title      string   `json:"title"`
    Detail     string   `json:"detail"`
    File       string   `json:"file,omitempty"`
    Line       int      `json:"line,omitempty"`
    Rule       string   `json:"rule,omitempty"`
}

type Severity string
const (
    SevCritical Severity = "critical"
    SevHigh     Severity = "high"
    SevMedium   Severity = "medium"
    SevLow      Severity = "low"
    SevInfo     Severity = "info"
)

type VetReport struct {
    Path        string    `json:"path"`
    Timestamp   time.Time `json:"timestamp"`
    Scanners    []string  `json:"scanners_run"`
    Unavailable []string  `json:"scanners_unavailable"`
    Findings    []Finding `json:"findings"`
    PassedPolicy bool     `json:"passed_policy"`
    Summary     Summary   `json:"summary"`
}

type Summary struct {
    Critical int `json:"critical"`
    High     int `json:"high"`
    Medium   int `json:"medium"`
    Low      int `json:"low"`
    Info     int `json:"info"`
}

// internal/discover/types.go
type Capability struct {
    Name        string `json:"name"`
    Kind        string `json:"kind"`    // "skill", "command", "plugin", "mcp", "builtin"
    Source      string `json:"source"`  // file path or "builtin"
    Description string `json:"description"`
    Triggers    string `json:"triggers,omitempty"`
    InvokeVia   string `json:"invoke_via"` // "skill:name", "command:/name", "tool:Name"
}

// internal/route/types.go
type RouteResult struct {
    Skills   []MatchScore `json:"skills"`
    Tools    []MatchScore `json:"tools"`
    Commands []MatchScore `json:"commands"`
}

type MatchScore struct {
    Name      string  `json:"name"`
    Score     float64 `json:"score"`
    InvokeVia string  `json:"invoke_via"`
    Reason    string  `json:"reason"`
}

// internal/intake/types.go
type IntakeResult struct {
    Project     string      `json:"project"`
    Root        string      `json:"root"`
    Stack       StackInfo   `json:"stack"`
    Conventions Conventions `json:"conventions"`
    Memory      MemoryState `json:"memory"`
    Tools       ToolState   `json:"tools"`
    IntakeTime  time.Time   `json:"intake_time"`
}

type StackInfo struct {
    Languages      []string `json:"languages"`
    Frameworks     []string `json:"frameworks"`
    PackageManager string   `json:"package_manager"`
    Monorepo       bool     `json:"monorepo"`
    TestFramework  string   `json:"test_framework"`
    TestCmd        string   `json:"test_cmd"`
    BuildCmd       string   `json:"build_cmd"`
    DevCmd         string   `json:"dev_cmd"`
}
```

### Config Loading

Config loads from a merge chain with increasing precedence:
1. Built-in defaults (`internal/config/defaults.go`)
2. `~/.claude/harness/config.json` (global user config)
3. `<project>/.claude/harness.json` (project override)
4. Environment variables (`HARNESS_AUDIT_DIR`, etc.)
5. CLI flags

Validation uses `encoding/json` with struct tags. At startup, `config.Load()` merges all layers, validates required fields, resolves paths (expanding `~`), and returns a frozen `*Config` or a descriptive error.

## 2. CLI Design

Framework: **cobra** (`github.com/spf13/cobra`). It is the standard for Go CLIs, handles subcommands, flags, completions, and help generation.

### Command Hierarchy and Flag Design

```
harness
  ├── serve       [--port 0] [--transport stdio|sse]
  ├── vet         <path> [--scanners trivy,gitleaks] [--format json|text|md] [--policy path]
  ├── audit       [--query json] [--sid SID] [--tool TOOL] [--class CLASS] [--since TIME]
  │               [--until TIME] [--errors] [--limit N] [--tail] [--format json|text|table]
  ├── classify    <tool-id> [args-json] [--role ROLE] [--format json|text]
  ├── route       <task-description> [--format json|text]
  ├── intake      <project-path> [--output path] [--format json|text]
  ├── supervise   <task> [--dry-run] [--max-budget USD]
  ├── forge       <name> [url] [--output dir] [--framework fastmcp|custom]
  ├── checkpoint  [--project path] [--output path]
  ├── config      get <key> | set <key> <value> | validate [path] | init
  └── version     [--short]

Global flags (on root):
  --config PATH     Override config file path
  --verbose         Verbose logging to stderr
  --json            Force JSON output for all commands
  --quiet           Suppress non-essential output
```

### Usage Examples

```bash
# Run vetting pipeline
harness vet ./mcp-servers/my-tool-mcp --scanners trivy,gitleaks,secretscan

# Stream audit log in real time
harness audit --tail --sid current

# Query audit log for errors in the last hour
harness audit --errors --since 1h --format table

# Classify a tool action
harness classify Bash '{"command":"rm -rf /tmp/build"}'

# Route a task to skills
harness route "build a sensor dashboard with live data"

# Project intake
harness intake /c/Users/globa/physical-capability-cloud

# Start MCP server (Claude Code connects via stdio)
harness serve

# Full supervisor loop (would be called by the /go command wrapper)
harness supervise "add a sensor API endpoint and write tests"

# Config management
harness config init         # Create default config
harness config validate     # Validate current config
harness config get audit_dir
```

## 3. MCP Server Design

### How `harness serve` Works

`harness serve` starts an MCP server on **stdio** (the standard transport for Claude Code MCP servers). It implements the MCP protocol (JSON-RPC 2.0 over stdio) and exposes harness capabilities as typed tools.

The implementation uses `github.com/mark3labs/mcp-go` (the leading Go MCP SDK) which handles protocol negotiation, tool listing, and call routing.

### Tool Schemas

The MCP server exposes these tools:

```go
// internal/mcp/tools.go

var Tools = []mcp.Tool{
    {
        Name:        "harness_vet",
        Description: "Run security vetting pipeline on a file or directory. Orchestrates trivy, gitleaks, semgrep, and built-in scanners. Returns findings with severity levels.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "path":     {Type: "string", Description: "Path to scan"},
                "scanners": {Type: "string", Description: "Comma-separated scanner names (default: all available)"},
            },
            Required: []string{"path"},
        },
    },
    {
        Name:        "harness_classify",
        Description: "Classify a tool action by risk level. Returns action class (read/write/exec/network/credential/destructive), whether it's allowed for the given agent role, and matched keywords.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "tool":      {Type: "string", Description: "Tool name (e.g., Bash, Write, Edit)"},
                "args":      {Type: "object", Description: "Tool arguments as JSON object"},
                "agent_role": {Type: "string", Description: "Agent role for allowlist check (e.g., researcher, implementer, scanner)"},
            },
            Required: []string{"tool"},
        },
    },
    {
        Name:        "harness_audit_query",
        Description: "Query the audit log. Filter by session, tool, action class, time range, errors. Returns matching entries.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "sid":          {Type: "string", Description: "Filter by session ID"},
                "tool":         {Type: "string", Description: "Filter by tool name"},
                "action_class": {Type: "string", Description: "Filter by action class"},
                "agent_role":   {Type: "string", Description: "Filter by agent role"},
                "since":        {Type: "string", Description: "ISO 8601 timestamp or duration (e.g., '1h', '30m')"},
                "until":        {Type: "string", Description: "ISO 8601 timestamp"},
                "errors_only":  {Type: "boolean", Description: "Only return entries with errors"},
                "limit":        {Type: "integer", Description: "Max entries to return (default: 100)"},
            },
        },
    },
    {
        Name:        "harness_audit_stats",
        Description: "Get aggregate statistics from the audit log. Tool usage counts, error rates, cost estimates, session summaries.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "sid":   {Type: "string", Description: "Filter stats to a specific session"},
                "since": {Type: "string", Description: "Only include events after this time"},
            },
        },
    },
    {
        Name:        "harness_route",
        Description: "Route a task description to the best matching skills, tools, and commands. Returns scored matches with invoke instructions.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "task":      {Type: "string", Description: "Task description to route"},
                "max_results": {Type: "integer", Description: "Max results per category (default: 3)"},
            },
            Required: []string{"task"},
        },
    },
    {
        Name:        "harness_intake",
        Description: "Scan a project directory to detect stack, conventions, test setup, memory state, and available tools. Returns structured intake JSON.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "path": {Type: "string", Description: "Project root path"},
            },
            Required: []string{"path"},
        },
    },
    {
        Name:        "harness_discover",
        Description: "Discover all available capabilities: skills, commands, plugins, MCP servers, builtins. Returns the unified capability registry.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "search": {Type: "string", Description: "Optional search term to filter capabilities"},
            },
        },
    },
    {
        Name:        "harness_allowlist",
        Description: "Get the tool allowlist for a specific agent role. Returns allowed tools, denied tools with reasons.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "role": {Type: "string", Description: "Agent role (orchestrator, researcher, implementer, tester, scanner, forger, scout)"},
            },
            Required: []string{"role"},
        },
    },
    {
        Name:        "harness_decompose",
        Description: "Decompose a multi-step task into a dependency graph and execution waves. Returns sub-tasks grouped into parallel waves.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "task":        {Type: "string", Description: "Task description to decompose"},
                "project_ctx": {Type: "string", Description: "Optional project context (from intake)"},
            },
            Required: []string{"task"},
        },
    },
    {
        Name:        "harness_checkpoint",
        Description: "Generate a memory checkpoint. Gathers git state, recent changes, open tasks, and writes WORKING_MEMORY.md and DECISIONS.md.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "project_path": {Type: "string", Description: "Project root path"},
                "summary":      {Type: "string", Description: "Optional session summary to include"},
                "decisions":    {Type: "array", Description: "Array of decision objects [{title, context, decision, alternatives, consequences}]"},
            },
        },
    },
    {
        Name:        "harness_config",
        Description: "Read or validate harness configuration.",
        InputSchema: mcp.Schema{
            Type: "object",
            Properties: map[string]mcp.Property{
                "action": {Type: "string", Description: "get, validate, or dump"},
                "key":    {Type: "string", Description: "Config key to get (for action=get)"},
            },
            Required: []string{"action"},
        },
    },
}
```

### How Claude Code Discovers the Harness MCP Server

The `.mcp.json` config entry (at `~/.claude/.mcp.json` for global, or `<project>/.mcp.json` for per-project):

```json
{
  "mcpServers": {
    "harness": {
      "command": "harness",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

If `harness` is not on PATH, use the full path:
```json
{
  "mcpServers": {
    "harness": {
      "command": "C:\\Users\\globa\\go\\bin\\harness.exe",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

When Claude Code starts, it launches `harness serve` as a subprocess, connects via stdio, calls `tools/list` to discover available tools, and then can call any tool during conversations. Every tool call through the MCP server is automatically audit-logged.

### MCP Server Implementation

```go
// internal/mcp/server.go

type Server struct {
    config   *config.Config
    audit    *audit.Writer
    classify *classify.Classifier
    vet      *vet.Pipeline
    discover *discover.Registry
    router   *route.Router
    intake   *intake.Scanner
}

func NewServer(cfg *config.Config) (*Server, error) {
    auditWriter, err := audit.NewWriter(cfg.AuditDir, cfg.AuditMaxBytes, cfg.AuditMaxFiles)
    if err != nil {
        return nil, fmt.Errorf("init audit writer: %w", err)
    }
    
    return &Server{
        config:   cfg,
        audit:    auditWriter,
        classify: classify.New(cfg.ActionPolicy, cfg.Allowlists),
        vet:      vet.NewPipeline(cfg.VettingPolicy, cfg.ScannerPaths),
        discover: discover.NewRegistry(cfg.ClaudeDir),
        router:   route.NewRouter(discover.NewRegistry(cfg.ClaudeDir)),
        intake:   intake.NewScanner(),
    }, nil
}

func (s *Server) Run(ctx context.Context) error {
    mcpServer := mcp.NewServer("harness", "1.0.0")
    
    // Register all tools
    for _, tool := range Tools {
        mcpServer.AddTool(tool, s.handleTool)
    }
    
    // Wrap handler with audit logging
    // Every call gets logged to the JSONL audit log automatically
    
    // Start stdio transport
    transport := mcp.NewStdioTransport()
    return mcpServer.Serve(ctx, transport)
}

func (s *Server) handleTool(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    start := time.Now()
    
    // Pre-audit
    entry := audit.AuditEntry{
        Timestamp: start,
        Tool:      req.Name,
        Phase:     "pre",
        Input:     req.Arguments,
    }
    s.audit.Write(entry)
    
    // Dispatch to handler
    result, err := s.dispatch(ctx, req)
    
    // Post-audit
    entry.Phase = "post"
    entry.DurationMs = time.Since(start).Milliseconds()
    entry.HasError = err != nil
    s.audit.Write(entry)
    
    return result, err
}

func (s *Server) dispatch(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    switch req.Name {
    case "harness_vet":
        return s.handleVet(ctx, req)
    case "harness_classify":
        return s.handleClassify(ctx, req)
    case "harness_audit_query":
        return s.handleAuditQuery(ctx, req)
    case "harness_audit_stats":
        return s.handleAuditStats(ctx, req)
    case "harness_route":
        return s.handleRoute(ctx, req)
    case "harness_intake":
        return s.handleIntake(ctx, req)
    case "harness_discover":
        return s.handleDiscover(ctx, req)
    case "harness_allowlist":
        return s.handleAllowlist(ctx, req)
    case "harness_decompose":
        return s.handleDecompose(ctx, req)
    case "harness_checkpoint":
        return s.handleCheckpoint(ctx, req)
    case "harness_config":
        return s.handleConfig(ctx, req)
    default:
        return nil, fmt.Errorf("unknown tool: %s", req.Name)
    }
}
```

## 4. Vetting Pipeline in Go

### Scanner Interface

```go
// internal/vet/scanner.go

type Scanner interface {
    // Name returns the scanner's identifier (e.g., "trivy", "gitleaks")
    Name() string
    
    // Available returns true if the scanner binary is installed and reachable
    Available() bool
    
    // Scan runs the scanner against the given path and returns findings
    Scan(ctx context.Context, path string) ([]Finding, error)
}

// Registry of all known scanners
type ScannerRegistry struct {
    scanners []Scanner
}

func NewScannerRegistry(paths map[string]string) *ScannerRegistry {
    return &ScannerRegistry{
        scanners: []Scanner{
            NewTrivyScanner(paths["trivy"]),
            NewGitleaksScanner(paths["gitleaks"]),
            NewSemgrepScanner(paths["semgrep"]),
            NewLicenseeScanner(paths["licensee"]),
            NewDepCheckScanner(paths["depcheck"]),
            NewSecretScanScanner(),   // built-in, always available
            NewPathTraversalScanner(), // built-in, always available
        },
    }
}
```

### External Scanner Adapter Pattern

Each external scanner follows the same pattern:

```go
// internal/vet/trivy.go

type TrivyScanner struct {
    binPath string
}

func NewTrivyScanner(override string) *TrivyScanner {
    bin := "trivy"
    if override != "" {
        bin = override
    }
    return &TrivyScanner{binPath: bin}
}

func (s *TrivyScanner) Name() string { return "trivy" }

func (s *TrivyScanner) Available() bool {
    _, err := exec.LookPath(s.binPath)
    return err == nil
}

func (s *TrivyScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
    cmd := exec.CommandContext(ctx, s.binPath, "fs", "--format", "json", "--severity", "CRITICAL,HIGH,MEDIUM", path)
    out, err := cmd.Output()
    if err != nil {
        // trivy returns non-zero on findings — check if it's actual error vs findings
        var exitErr *exec.ExitError
        if errors.As(err, &exitErr) && len(exitErr.Stderr) > 0 {
            return nil, fmt.Errorf("trivy error: %s", exitErr.Stderr)
        }
        // Non-zero with output usually means findings were found
    }
    return parseTrivyOutput(out)
}

func parseTrivyOutput(data []byte) ([]Finding, error) {
    // Parse trivy JSON format → normalize to []Finding
    var report trivyReport
    if err := json.Unmarshal(data, &report); err != nil {
        return nil, err
    }
    var findings []Finding
    for _, result := range report.Results {
        for _, vuln := range result.Vulnerabilities {
            findings = append(findings, Finding{
                Scanner:  "trivy",
                Severity: normalizeSeverity(vuln.Severity),
                Title:    vuln.VulnerabilityID + ": " + vuln.Title,
                Detail:   vuln.Description,
                File:     result.Target,
                Rule:     vuln.VulnerabilityID,
            })
        }
    }
    return findings, nil
}
```

### Pipeline Orchestration

```go
// internal/vet/pipeline.go

type Pipeline struct {
    registry *ScannerRegistry
    policy   VettingPolicy
}

func (p *Pipeline) Run(ctx context.Context, path string, requested []string) (*VetReport, error) {
    scanners := p.registry.Select(requested) // filter to requested scanners, or all if empty
    
    // Check availability
    var available []Scanner
    var unavailable []string
    for _, s := range scanners {
        if s.Available() {
            available = append(available, s)
        } else {
            unavailable = append(unavailable, s.Name())
        }
    }
    
    // Run available scanners in parallel
    type result struct {
        findings []Finding
        err      error
        scanner  string
    }
    
    results := make(chan result, len(available))
    for _, s := range available {
        go func(scanner Scanner) {
            findings, err := scanner.Scan(ctx, path)
            results <- result{findings: findings, err: err, scanner: scanner.Name()}
        }(s)
    }
    
    // Collect
    var allFindings []Finding
    var scannersRun []string
    for i := 0; i < len(available); i++ {
        r := <-results
        if r.err != nil {
            // Log error but don't fail the pipeline — graceful degradation
            allFindings = append(allFindings, Finding{
                Scanner:  r.scanner,
                Severity: SevInfo,
                Title:    fmt.Sprintf("Scanner error: %s", r.err),
            })
        } else {
            allFindings = append(allFindings, r.findings...)
        }
        scannersRun = append(scannersRun, r.scanner)
    }
    
    // Evaluate against policy
    report := &VetReport{
        Path:        path,
        Timestamp:   time.Now(),
        Scanners:    scannersRun,
        Unavailable: unavailable,
        Findings:    allFindings,
        Summary:     summarize(allFindings),
    }
    report.PassedPolicy = p.evaluatePolicy(report)
    
    return report, nil
}

func (p *Pipeline) evaluatePolicy(report *VetReport) bool {
    for sev, maxCount := range p.policy.FailThresholds {
        actual := countBySeverity(report.Findings, Severity(sev))
        if actual > maxCount {
            return false
        }
    }
    return true
}
```

### Built-in Scanners (no external binary needed)

```go
// internal/vet/secretscan.go — always available

type SecretScanScanner struct{}

func (s *SecretScanScanner) Name() string    { return "secretscan" }
func (s *SecretScanScanner) Available() bool { return true }

func (s *SecretScanScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
    var findings []Finding
    patterns := []struct {
        name    string
        regex   *regexp.Regexp
        severity Severity
    }{
        {"AWS Key", regexp.MustCompile(`AKIA[0-9A-Z]{16}`), SevCritical},
        {"Private Key", regexp.MustCompile(`-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----`), SevCritical},
        {"Generic API Key", regexp.MustCompile(`(?i)(api[_-]?key|apikey|secret[_-]?key)\s*[:=]\s*['"][a-zA-Z0-9]{20,}['"]`), SevHigh},
        {"Password in Code", regexp.MustCompile(`(?i)(password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]`), SevHigh},
        {"JWT Token", regexp.MustCompile(`eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}`), SevHigh},
    }
    
    filepath.WalkDir(path, func(p string, d fs.DirEntry, err error) error {
        if err != nil || d.IsDir() || isBinaryOrIgnored(p) {
            return nil
        }
        data, err := os.ReadFile(p)
        if err != nil {
            return nil
        }
        for _, pat := range patterns {
            if locs := pat.regex.FindAllIndex(data, -1); len(locs) > 0 {
                for _, loc := range locs {
                    line := countLines(data[:loc[0]])
                    findings = append(findings, Finding{
                        Scanner:  "secretscan",
                        Severity: pat.severity,
                        Title:    pat.name + " detected",
                        File:     p,
                        Line:     line,
                        Rule:     pat.name,
                    })
                }
            }
        }
        return nil
    })
    
    return findings, nil
}
```

## 5. Audit System in Go

### JSONL Writer with File Locking

```go
// internal/audit/writer.go

type Writer struct {
    mu        sync.Mutex
    file      *os.File
    path      string
    maxBytes  int64
    maxFiles  int
    encoder   *json.Encoder
}

func NewWriter(dir string, maxBytes int64, maxFiles int) (*Writer, error) {
    if err := os.MkdirAll(dir, 0755); err != nil {
        return nil, err
    }
    path := filepath.Join(dir, "audit.jsonl")
    f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
    if err != nil {
        return nil, err
    }
    return &Writer{
        file:     f,
        path:     path,
        maxBytes: maxBytes,
        maxFiles: maxFiles,
        encoder:  json.NewEncoder(f),
    }, nil
}

func (w *Writer) Write(entry AuditEntry) error {
    w.mu.Lock()
    defer w.mu.Unlock()
    
    // Check rotation
    if info, err := w.file.Stat(); err == nil && info.Size() >= w.maxBytes {
        if err := w.rotate(); err != nil {
            // Log rotation error but don't fail the write
            fmt.Fprintf(os.Stderr, "audit rotation error: %v\n", err)
        }
    }
    
    return w.encoder.Encode(entry)
}

func (w *Writer) rotate() error {
    w.file.Close()
    
    // Shift existing rotated files: audit.2.jsonl → audit.3.jsonl, etc.
    for i := w.maxFiles - 1; i >= 1; i-- {
        old := fmt.Sprintf("%s.%d", w.path, i)
        new := fmt.Sprintf("%s.%d", w.path, i+1)
        os.Rename(old, new)
    }
    
    // Current → .1
    os.Rename(w.path, w.path+".1")
    
    // Delete excess
    excess := fmt.Sprintf("%s.%d", w.path, w.maxFiles+1)
    os.Remove(excess)
    
    // Open new
    f, err := os.OpenFile(w.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
    if err != nil {
        return err
    }
    w.file = f
    w.encoder = json.NewEncoder(f)
    return nil
}
```

### Query Engine

```go
// internal/audit/query.go

type QueryEngine struct {
    dir string
}

func (q *QueryEngine) Query(query AuditQuery) ([]AuditEntry, error) {
    files := q.auditFiles() // current + rotated, newest first
    
    var results []AuditEntry
    for _, file := range files {
        entries, err := q.scanFile(file, query)
        if err != nil {
            continue // skip corrupt files
        }
        results = append(results, entries...)
        if query.Limit > 0 && len(results) >= query.Limit {
            results = results[:query.Limit]
            break
        }
    }
    return results, nil
}

func (q *QueryEngine) scanFile(path string, query AuditQuery) ([]AuditEntry, error) {
    f, err := os.Open(path)
    if err != nil {
        return nil, err
    }
    defer f.Close()
    
    var entries []AuditEntry
    scanner := bufio.NewScanner(f)
    scanner.Buffer(make([]byte, 0, 1024*1024), 10*1024*1024) // 10MB max line
    
    for scanner.Scan() {
        var entry AuditEntry
        if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
            continue
        }
        if matchesQuery(entry, query) {
            entries = append(entries, entry)
        }
    }
    return entries, nil
}

func matchesQuery(entry AuditEntry, q AuditQuery) bool {
    if q.SessionID != "" && entry.SessionID != q.SessionID { return false }
    if q.Tool != "" && entry.Tool != q.Tool { return false }
    if q.ActionClass != "" && entry.ActionClass != q.ActionClass { return false }
    if q.AgentRole != "" && entry.AgentRole != q.AgentRole { return false }
    if !q.Since.IsZero() && entry.Timestamp.Before(q.Since) { return false }
    if !q.Until.IsZero() && entry.Timestamp.After(q.Until) { return false }
    if q.HasError != nil && entry.HasError != *q.HasError { return false }
    return true
}
```

### Real-time Tail Mode

```go
// internal/audit/tail.go

func (q *QueryEngine) Tail(ctx context.Context, query AuditQuery, out chan<- AuditEntry) error {
    path := filepath.Join(q.dir, "audit.jsonl")
    
    watcher, err := fsnotify.NewWatcher()
    if err != nil {
        return err
    }
    defer watcher.Close()
    
    if err := watcher.Add(q.dir); err != nil {
        return err
    }
    
    f, err := os.Open(path)
    if err != nil {
        return err
    }
    defer f.Close()
    
    // Seek to end
    f.Seek(0, io.SeekEnd)
    reader := bufio.NewReader(f)
    
    for {
        select {
        case <-ctx.Done():
            return nil
        case event := <-watcher.Events:
            if event.Op&fsnotify.Write != 0 {
                for {
                    line, err := reader.ReadBytes('\n')
                    if err != nil {
                        break
                    }
                    var entry AuditEntry
                    if json.Unmarshal(line, &entry) == nil && matchesQuery(entry, query) {
                        out <- entry
                    }
                }
            }
        }
    }
}
```

## 6. Action Classifier in Go

### Keyword Scoring Algorithm

This is a direct port of the behavior currently encoded in the tool-broker agent's prompt (the security policy section):

```go
// internal/classify/classifier.go

type Classifier struct {
    rules      []ActionRule
    allowlists map[string]Allowlist
}

func New(policy ActionPolicy, allowlists map[string]Allowlist) *Classifier {
    return &Classifier{
        rules:      policy.Rules,
        allowlists: allowlists,
    }
}

// Built-in classification rules (these serve as defaults — config can override)
var DefaultRules = []ActionRule{
    // Read tools
    {Pattern: "^(Read|Glob|Grep|WebFetch|WebSearch|ToolSearch)$", Class: "read"},
    
    // Write tools
    {Pattern: "^(Write|Edit|NotebookEdit)$", Class: "write"},
    
    // Exec tools — further classified by command content
    {Pattern: "^Bash$", Class: "exec"},
    
    // Network tools
    {Pattern: "^(WebFetch|WebSearch)$", Class: "network"},
    
    // Agent spawning
    {Pattern: "^Agent$", Class: "exec"},
}

// Destructive command keywords (scored)
var DestructiveKeywords = map[string]float64{
    "rm -rf":           1.0,
    "rm -r":            0.9,
    "rmdir":            0.7,
    "git reset --hard": 1.0,
    "git push --force": 1.0,
    "git clean -f":     0.9,
    "drop table":       1.0,
    "truncate":         0.8,
    "format":           0.6,
    "> /dev/null":      0.3,
    "chmod 777":        0.7,
    "curl | sh":        1.0,
    "curl | bash":      1.0,
    "eval(":            0.8,
}

// Credential keywords
var CredentialKeywords = map[string]float64{
    "_KEY=":    0.9,
    "_TOKEN=":  0.9,
    "_SECRET=": 0.9,
    "password": 0.7,
    "passwd":   0.7,
    "credentials": 0.8,
    "BEGIN PRIVATE KEY": 1.0,
    "BEGIN RSA":  1.0,
}

func (c *Classifier) Classify(tool string, args map[string]any, agentRole string) ClassifyResult {
    result := ClassifyResult{Tool: tool}
    
    // Step 1: Base classification from tool name
    for _, rule := range append(DefaultRules, c.rules...) {
        matched, _ := regexp.MatchString(rule.Pattern, tool)
        if matched {
            result.ActionClass = ActionClass(rule.Class)
            break
        }
    }
    
    // Step 2: Deep classification for Bash commands — scan content
    if tool == "Bash" {
        cmd, _ := args["command"].(string)
        result = c.classifyBashCommand(cmd, result)
    }
    
    // Step 3: Deep classification for Write/Edit — check for credential content
    if tool == "Write" || tool == "Edit" {
        content := extractContent(args)
        credScore, keywords := c.scoreKeywords(content, CredentialKeywords)
        if credScore > 0.5 {
            result.ActionClass = ActionCredential
            result.Keywords = keywords
        }
    }
    
    // Step 4: Allowlist check
    if agentRole != "" {
        result.Allowed, result.DenyReason = c.checkAllowlist(agentRole, tool, result.ActionClass)
    } else {
        result.Allowed = true // no role = no restriction
    }
    
    return result
}

func (c *Classifier) classifyBashCommand(cmd string, base ClassifyResult) ClassifyResult {
    // Check destructive keywords
    destructiveScore, keywords := c.scoreKeywords(cmd, DestructiveKeywords)
    if destructiveScore > 0.5 {
        base.ActionClass = ActionDestructive
        base.Score = destructiveScore
        base.Keywords = keywords
        return base
    }
    
    // Check credential keywords
    credScore, credKeywords := c.scoreKeywords(cmd, CredentialKeywords)
    if credScore > 0.5 {
        base.ActionClass = ActionCredential
        base.Score = credScore
        base.Keywords = credKeywords
        return base
    }
    
    // Check if it's a read-only command
    readOnlyPrefixes := []string{"ls", "cat", "head", "tail", "find", "grep", "rg", "wc",
        "git log", "git status", "git diff", "git branch", "git remote",
        "echo", "pwd", "which", "type", "file", "stat", "du", "df"}
    cmdTrimmed := strings.TrimSpace(cmd)
    for _, prefix := range readOnlyPrefixes {
        if strings.HasPrefix(cmdTrimmed, prefix) {
            base.ActionClass = ActionRead
            return base
        }
    }
    
    // Check for shell injection patterns
    injectionPatterns := []string{"; rm", "| rm", "$(", "`", "&& rm"}
    for _, pat := range injectionPatterns {
        if strings.Contains(cmd, pat) {
            base.Keywords = append(base.Keywords, "shell_injection: "+pat)
        }
    }
    
    base.ActionClass = ActionExec
    return base
}

func (c *Classifier) scoreKeywords(text string, keywords map[string]float64) (float64, []string) {
    var maxScore float64
    var matched []string
    lower := strings.ToLower(text)
    
    for kw, weight := range keywords {
        if strings.Contains(lower, strings.ToLower(kw)) {
            if weight > maxScore {
                maxScore = weight
            }
            matched = append(matched, kw)
        }
    }
    return maxScore, matched
}

func (c *Classifier) checkAllowlist(role, tool string, class ActionClass) (bool, string) {
    al, ok := c.allowlists[role]
    if !ok {
        return false, fmt.Sprintf("unknown role: %s", role)
    }
    
    // Check denied first
    for _, denied := range al.Denied {
        if denied == tool || denied == string(class) {
            return false, fmt.Sprintf("role %s denied access to %s", role, tool)
        }
    }
    
    // Check allowed
    for _, allowed := range al.Tools {
        if allowed == tool || allowed == "*" {
            return true, ""
        }
    }
    
    return false, fmt.Sprintf("tool %s not in allowlist for role %s", tool, role)
}
```

### Default Allowlists (matches the current agent definitions)

```go
// internal/config/defaults.go

var DefaultAllowlists = map[string]Allowlist{
    "orchestrator": {Tools: []string{"*"}, Reason: "full access"},
    "researcher":   {Tools: []string{"Read", "Glob", "Grep", "WebSearch", "WebFetch"}, Denied: []string{"Write", "Edit", "Bash"}, Reason: "read-only"},
    "implementer":  {Tools: []string{"Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent"}, Denied: []string{"WebSearch", "WebFetch"}, Reason: "code only, no web"},
    "tester":       {Tools: []string{"Read", "Bash", "Glob", "Grep"}, Denied: []string{"Write", "Edit"}, Reason: "test execution only"},
    "scanner":      {Tools: []string{"Read", "Glob", "Grep"}, Denied: []string{"Write", "Edit", "Bash", "WebSearch", "WebFetch"}, Reason: "read-only, no exec"},
    "forger":       {Tools: []string{"Read", "Write", "Edit", "Bash", "WebFetch", "WebSearch", "Glob", "Grep"}, Reason: "full build + web access"},
    "scout":        {Tools: []string{"WebSearch", "WebFetch", "Read", "Glob", "Grep"}, Denied: []string{"Write", "Edit", "Bash"}, Reason: "research only"},
}
```

## 7. Integration with Claude Code

### What Stays as Markdown vs What Moves to Go

**STAYS as markdown** (Claude Code reads these natively, they define agent personas and prompt logic):
- `~/.claude/agents/*.md` — agent definitions (supervisor, implementer, etc.)
- `~/.claude/commands/*.md` — command wrappers (/go, /intake, /forge, etc.)
- `~/.claude/skills/*/SKILL.md` — skill definitions
- `~/.claude/CLAUDE.md` — global instructions

**MOVES to Go** (runtime logic that currently lives as prompt-described behavior or scripts):
- Bash hooks (`trace-pre.sh`, `trace-post.sh`) → replaced by MCP server audit logging
- Node.js trace server (`trace/server.js`) → replaced by `harness audit` CLI + MCP tools
- Action classification (described in tool-broker.md) → `harness_classify` MCP tool
- Skill routing (described in skill-router.md) → `harness_route` MCP tool
- Project intake (described in intake.md) → `harness_intake` MCP tool
- Vetting pipeline (described in tool-broker.md) → `harness_vet` MCP tool
- Allowlist management (described in tool-broker.md) → `harness_allowlist` MCP tool
- Config validation → `harness config validate`
- Capability discovery → `harness_discover` MCP tool

### How Markdown Command Wrappers Call the Go Binary

The thin `.md` wrappers get simplified. Instead of encoding the full algorithm in prompt text, they now say "call the harness MCP tool, then act on its output." Example rewrite for `/intake`:

**Before** (current `intake.md` — 102 lines of prompt-encoded logic):
The LLM must run `ls`, `git remote`, read config files, detect stack, detect conventions, check memory, check tools, and write JSON — all by interpreting natural language instructions.

**After** (simplified `intake.md` — ~15 lines):
```markdown
---
name: intake
description: Pre-swarm project intake scan
---
# Project Intake: /intake

Call the harness MCP tool to scan the project:

1. Call `mcp__harness__harness_intake` with `path` = current working directory
2. The tool returns structured JSON with: project name, stack, conventions, memory state, tools
3. Save the result to `ai/supervisor/intake.json`
4. Present a summary:
   - Project: [name] ([stack])
   - Structure: [monorepo? packages?]
   - Test: [framework + command]
   - Memory: [restored / fresh]
   - Tools: [N MCP servers, M agents, K commands]
```

The key insight: the heavy lifting (file system scanning, pattern matching, convention detection) moves to the Go binary. The markdown wrapper only needs to call one tool and format the output. This reduces the prompt token cost by 80%+ per command invocation.

### How the MCP Server Replaces Prompt-Based Behavior

Currently, the tool-broker agent uses ~90 lines of prompt text to describe action classification. When invoked, the LLM must simulate the algorithm by reading the prompt and generating text. This is:
- Expensive (haiku invocation + prompt tokens)
- Unreliable (the LLM might skip steps or misclassify)
- Slow (full inference cycle for what is a deterministic algorithm)

With the Go binary, the supervisor/tool-broker agents instead call `mcp__harness__harness_classify`, which returns a deterministic JSON result in milliseconds. The agent prompt shrinks to: "Call harness_classify to check if this tool is allowed for this agent's role."

Similarly, the skill-router agent currently:
1. Globs for skill files (~200ms prompt + inference)
2. Reads frontmatter from each (~500ms per file)
3. Scores matches against the task (~inference time)
4. Formats output (~inference time)

Total: ~5-10 seconds of haiku time, ~2K tokens.

With `harness_route`: single MCP call, ~50ms, deterministic, zero inference tokens for the routing logic itself.

### The .mcp.json Config

For global installation (all projects get harness tools):

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "harness": {
      "command": "harness",
      "args": ["serve"]
    }
  }
}
```

Or per-project in `<project>/.mcp.json`:
```json
{
  "mcpServers": {
    "harness": {
      "command": "harness",
      "args": ["serve", "--config", ".claude/harness.json"]
    }
  }
}
```

### Hook Migration

The current `settings.json` has PreToolUse/PostToolUse hooks that shell out to bash scripts for every tool call. These get replaced by the MCP server's built-in audit logging.

**Before** (`settings.json`):
```json
{
  "hooks": {
    "PreToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "bash \"$HOME/.claude/hooks/trace-pre.sh\""}]}],
    "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "bash \"$HOME/.claude/hooks/trace-post.sh\""}]}]
  }
}
```

**After**: The hooks are removed from `settings.json` entirely. When `harness serve` is running as an MCP server, it automatically logs every tool call routed through it. For tools NOT routed through harness (native Claude Code tools like Read, Write, etc.), the hooks can optionally remain, but now they call `harness` instead of bash:

```json
{
  "hooks": {
    "PreToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "harness audit log --phase pre"}]}],
    "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "harness audit log --phase post"}]}]
  }
}
```

This is faster than bash (compiled binary vs script interpreter) and uses the same JSONL format. Or, for maximum simplicity, just keep the hooks as-is during the transition and deprecate them later once all critical paths go through MCP tools.

## 8. Build and Distribution

### goreleaser Configuration

```yaml
# .goreleaser.yaml
project_name: harness
version: 2

builds:
  - main: ./main.go
    binary: harness
    env:
      - CGO_ENABLED=0
    goos:
      - windows
      - linux
      - darwin
    goarch:
      - amd64
      - arm64
    ldflags:
      - -s -w
      - -X main.version={{.Version}}
      - -X main.commit={{.Commit}}
      - -X main.date={{.Date}}

archives:
  - format: tar.gz
    format_overrides:
      - goos: windows
        format: zip
    name_template: "{{ .ProjectName }}_{{ .Os }}_{{ .Arch }}"

checksum:
  name_template: "checksums.txt"

changelog:
  sort: asc
  filters:
    exclude:
      - "^docs:"
      - "^test:"
```

### Installation Methods

```bash
# Method 1: go install (requires Go toolchain)
go install github.com/global-mysterysnailrevolution/harness@latest

# Method 2: Pre-built binary (from GitHub Releases)
# Windows
curl -L https://github.com/global-mysterysnailrevolution/harness/releases/latest/download/harness_windows_amd64.zip -o harness.zip
unzip harness.zip -d $HOME/go/bin/

# Linux/macOS
curl -L https://github.com/global-mysterysnailrevolution/harness/releases/latest/download/harness_linux_amd64.tar.gz | tar xz -C $HOME/go/bin/

# Method 3: Scoop (Windows)
scoop install harness

# Method 4: Self-update (built into binary)
harness self-update
```

### Self-Update Mechanism

```go
// cmd/selfupdate.go

func runSelfUpdate() error {
    // Check latest release from GitHub API
    resp, err := http.Get("https://api.github.com/repos/global-mysterysnailrevolution/harness/releases/latest")
    // Compare version tag with embedded version
    // Download appropriate binary for GOOS/GOARCH
    // Replace self (os.Rename on Unix, write-and-relaunch on Windows)
    // Use github.com/minio/selfupdate or similar
}
```

## Dependencies

Minimal dependency set to keep the binary small and compilation fast:

```
github.com/spf13/cobra          # CLI framework
github.com/mark3labs/mcp-go     # MCP protocol implementation
github.com/fsnotify/fsnotify    # File watching for audit tail
gopkg.in/yaml.v3                # YAML frontmatter parsing
```

No framework bloat. Standard library for JSON, HTTP, file I/O, concurrency, and regexp. The binary should be under 15MB.

## Implementation Sequence

**Phase 1 — Foundation (1 week)**
1. Go module scaffold with `cmd/root.go` and cobra
2. `internal/config/` — config loading, validation, defaults
3. `internal/audit/` — writer, reader, query engine, tail
4. `cmd/audit.go` — the first working subcommand
5. `cmd/version.go`

**Phase 2 — Core Tools (1 week)**
6. `internal/classify/` — action classifier with keyword scoring
7. `internal/discover/` — skill/plugin/command scanner
8. `internal/route/` — task routing
9. `cmd/classify.go`, `cmd/route.go`
10. `pkg/frontmatter/` — YAML frontmatter parser

**Phase 3 — Vetting Pipeline (1 week)**
11. `internal/vet/` — Scanner interface, built-in scanners
12. External scanner adapters (trivy, gitleaks, semgrep)
13. Pipeline orchestration with parallel execution
14. `cmd/vet.go`

**Phase 4 — MCP Server (1 week)**
15. `internal/mcp/` — server, tools, handler
16. Wire all internal packages to MCP tool handlers
17. `cmd/serve.go`
18. Test with Claude Code via `.mcp.json`

**Phase 5 — Higher-Level Commands (1 week)**
19. `internal/intake/` — project scanner
20. `internal/checkpoint/` — memory checkpoint writer
21. `internal/supervisor/` — task decomposition
22. `cmd/intake.go`, `cmd/checkpoint.go`, `cmd/supervise.go`

**Phase 6 — Polish & Distribution (3 days)**
23. goreleaser setup
24. Self-update mechanism
25. Simplified markdown command wrappers
26. Migration from bash hooks to harness binary
27. README and docs

## Potential Challenges

1. **MCP protocol compatibility**: The `mcp-go` library must match the exact protocol version Claude Code expects. If there is a version mismatch, we would need to implement the JSON-RPC layer manually (straightforward but tedious).

2. **Windows file locking**: JSONL append-only writes on Windows require careful handling. `sync.Mutex` handles in-process locking, but cross-process locking (if multiple `harness` instances run) needs `LockFileEx` via `syscall` or `golang.org/x/sys/windows`.

3. **fsnotify on Windows**: The `fsnotify` library works on Windows but uses `ReadDirectoryChangesW` which has known edge cases with rapid writes. The tail mode might need a polling fallback.

4. **Supervisor decomposition**: The `harness_decompose` tool is the trickiest — it needs to parse natural language task descriptions into dependency graphs. This likely stays as a prompt-assisted operation (the Go binary provides the data structures and the LLM provides the decomposition logic) rather than pure Go. The tool would provide a structured schema that the LLM fills in.

5. **Hook stdin format**: Claude Code hooks receive JSON on stdin. The `harness audit log --phase pre` hook command needs to read stdin, parse it, and write to the JSONL file. This is a hot path — every tool call goes through it. The compiled Go binary will handle this in ~5ms vs ~200ms for the current bash scripts.

---

### Critical Files for Implementation
- `C:/Users/globa/.claude/settings.json` — Must be modified to register the MCP server and migrate hooks from bash scripts to the harness binary
- `C:/Users/globa/.claude/hooks/trace-pre.sh` — Primary file to replace; its JSONL output format (phase, ts, sid, cwd, project, tool, event) defines the audit entry schema the Go binary must maintain backward compatibility with
- `C:/Users/globa/.claude/agents/tool-broker.md` — Contains the action classification logic, allowlist definitions, and security policy that must be ported precisely to `internal/classify/`
- `C:/Users/globa/.claude/agents/skill-router.md` — Contains the scoring algorithm and capability registry scan logic that must be ported to `internal/route/` and `internal/discover/`
- `C:/Users/globa/.claude/trace/server.js` — The Node.js trace server contains the session registry, tree builder, token estimation, and cost calculation logic that must be ported to `internal/audit/` — this is the most complex existing runtime code