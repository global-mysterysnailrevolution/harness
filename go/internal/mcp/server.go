package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/global-mysterysnailrevolution/harness/internal/audit"
	"github.com/global-mysterysnailrevolution/harness/internal/classify"
	"github.com/global-mysterysnailrevolution/harness/internal/config"
	"github.com/global-mysterysnailrevolution/harness/internal/discover"
	"github.com/global-mysterysnailrevolution/harness/internal/route"
	"github.com/global-mysterysnailrevolution/harness/internal/vet"
	mcplib "github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
)

// Server is the harness MCP server.
type Server struct {
	config     *config.Config
	auditW     *audit.Writer
	classifier *classify.Classifier
	pipeline   *vet.Pipeline
	registry   *discover.Registry
	router     *route.Router
}

// NewServer creates a new MCP server with all subsystems.
func NewServer(cfg *config.Config) (*Server, error) {
	auditWriter, err := audit.NewWriter(cfg.AuditDir, cfg.AuditMaxBytes, cfg.AuditMaxFiles)
	if err != nil {
		return nil, fmt.Errorf("init audit writer: %w", err)
	}

	reg := discover.NewRegistry(cfg.ClaudeDir)

	return &Server{
		config:     cfg,
		auditW:     auditWriter,
		classifier: classify.New(cfg.ActionPolicy, cfg.Allowlists),
		pipeline:   vet.NewPipeline(cfg.VettingPolicy, cfg.ScannerPaths),
		registry:   reg,
		router:     route.NewRouter(reg),
	}, nil
}

// Run starts the MCP server on stdio.
func (s *Server) Run(ctx context.Context) error {
	mcpServer := server.NewMCPServer("harness", "1.0.0")

	// Register all tools
	for _, td := range ToolDefinitions() {
		// Capture td for closure
		def := td
		mcpServer.AddTool(def, s.makeHandler(def.Name))
	}

	// Start stdio transport
	stdio := server.NewStdioServer(mcpServer)
	return stdio.Listen(ctx, nil, nil)
}

func (s *Server) makeHandler(toolName string) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
		start := time.Now()

		// Pre-audit
		entry := audit.AuditEntry{
			Timestamp: start,
			Tool:      req.Params.Name,
			Phase:     "pre",
			Allowed:   true,
		}
		_ = s.auditW.Write(entry)

		// Dispatch
		result, err := s.dispatch(ctx, req)

		// Post-audit
		entry.Phase = "post"
		entry.DurationMs = time.Since(start).Milliseconds()
		entry.HasError = err != nil
		_ = s.auditW.Write(entry)

		return result, err
	}
}

func (s *Server) dispatch(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	switch req.Params.Name {
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
	case "harness_discover":
		return s.handleDiscover(ctx, req)
	case "harness_allowlist":
		return s.handleAllowlist(ctx, req)
	case "harness_config":
		return s.handleConfig(ctx, req)
	default:
		return nil, fmt.Errorf("unknown tool: %s", req.Params.Name)
	}
}

// Helper: extract string arg from request
func getStringArg(req mcplib.CallToolRequest, key string) string {
	if v, ok := req.Params.Arguments[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

// Helper: JSON result
func jsonResult(v any) (*mcplib.CallToolResult, error) {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("marshal result: %w", err)
	}
	return mcplib.NewToolResultText(string(data)), nil
}
