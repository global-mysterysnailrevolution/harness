package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/global-mysterysnailrevolution/harness/internal/agents"
	"github.com/global-mysterysnailrevolution/harness/internal/audit"
	"github.com/global-mysterysnailrevolution/harness/internal/config"
	mcplib "github.com/mark3labs/mcp-go/mcp"
)

func (s *Server) handleVet(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	path := getStringArg(req, "path")
	if path == "" {
		return nil, fmt.Errorf("path is required")
	}
	scannersStr := getStringArg(req, "scanners")
	var scannerList []string
	if scannersStr != "" {
		for _, sc := range strings.Split(scannersStr, ",") {
			sc = strings.TrimSpace(sc)
			if sc != "" {
				scannerList = append(scannerList, sc)
			}
		}
	}
	report, err := s.pipeline.Run(ctx, path, scannerList)
	if err != nil {
		return nil, fmt.Errorf("vet scan: %w", err)
	}
	return jsonResult(report)
}

func (s *Server) handleClassify(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	tool := getStringArg(req, "tool")
	if tool == "" {
		return nil, fmt.Errorf("tool is required")
	}
	argsJSON := getStringArg(req, "args_json")
	var toolArgs map[string]any
	if argsJSON != "" {
		if err := json.Unmarshal([]byte(argsJSON), &toolArgs); err != nil {
			return nil, fmt.Errorf("parse args_json: %w", err)
		}
	}
	role := getStringArg(req, "agent_role")
	result := s.classifier.Classify(tool, toolArgs, role)
	return jsonResult(result)
}

func (s *Server) handleAuditQuery(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	reader := audit.NewReader(s.auditW.Dir())
	query := audit.AuditQuery{
		SessionID:   getStringArg(req, "sid"),
		Tool:        getStringArg(req, "tool"),
		ActionClass: getStringArg(req, "action_class"),
		Limit:       100,
	}
	entries, err := reader.Query(query)
	if err != nil {
		return nil, fmt.Errorf("query audit: %w", err)
	}
	return jsonResult(entries)
}

func (s *Server) handleAuditStats(_ context.Context, _ mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	reader := audit.NewReader(s.auditW.Dir())
	entries, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("read audit: %w", err)
	}
	stats := audit.ComputeStats(entries)
	return jsonResult(stats)
}

func (s *Server) handleRoute(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	task := getStringArg(req, "task")
	if task == "" {
		return nil, fmt.Errorf("task is required")
	}
	result := s.router.Route(task)
	return jsonResult(result)
}

func (s *Server) handleDiscover(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	search := getStringArg(req, "search")
	var caps interface{}
	if search != "" {
		caps = s.registry.Search(search)
	} else {
		caps = s.registry.All()
	}
	return jsonResult(caps)
}

func (s *Server) handleAllowlist(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	role := getStringArg(req, "role")
	if role == "" {
		return nil, fmt.Errorf("role is required")
	}
	al, ok := s.config.Allowlists[role]
	if !ok {
		return jsonResult(map[string]string{"error": fmt.Sprintf("no allowlist for role %q", role)})
	}
	return jsonResult(al)
}

func (s *Server) handleConfig(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	action := getStringArg(req, "action")
	switch action {
	case "validate":
		if err := config.Validate(s.config); err != nil {
			return jsonResult(map[string]string{"status": "invalid", "error": err.Error()})
		}
		return jsonResult(map[string]string{"status": "valid"})
	case "dump":
		return jsonResult(s.config)
	case "get":
		key := getStringArg(req, "key")
		data, _ := json.Marshal(s.config)
		var m map[string]any
		_ = json.Unmarshal(data, &m)
		val, ok := m[key]
		if !ok {
			return jsonResult(map[string]string{"error": fmt.Sprintf("key %q not found", key)})
		}
		return jsonResult(val)
	default:
		return nil, fmt.Errorf("unknown config action: %s", action)
	}
}

func (s *Server) handleAgentsList(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	if s.tracker == nil {
		return nil, fmt.Errorf("agent tracker not initialized")
	}
	filter := getStringArg(req, "filter")
	var list []*agents.AgentInfo
	if filter == "active" {
		list = s.tracker.Active()
	} else {
		list = s.tracker.List()
	}
	return jsonResult(list)
}

func (s *Server) handleAgentsCancel(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	if s.tracker == nil {
		return nil, fmt.Errorf("agent tracker not initialized")
	}
	id := getStringArg(req, "id")
	if id == "" {
		return nil, fmt.Errorf("id is required")
	}
	if err := s.tracker.Cancel(id); err != nil {
		return jsonResult(map[string]string{"error": err.Error()})
	}
	return jsonResult(map[string]string{"status": "cancelled", "id": id})
}

func (s *Server) handleAgentsRegister(_ context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
	if s.tracker == nil {
		return nil, fmt.Errorf("agent tracker not initialized")
	}
	id := getStringArg(req, "id")
	if id == "" {
		return nil, fmt.Errorf("id is required")
	}

	agentType := getStringArg(req, "type")
	description := getStringArg(req, "description")
	parentID := getStringArg(req, "parent_id")
	status := getStringArg(req, "status")
	progress := getStringArg(req, "progress")

	// If agent already exists, treat as an update
	existing := s.tracker.Get(id)
	if existing != nil {
		if status != "" {
			s.tracker.Update(id, agents.AgentStatus(status), progress)
		} else if progress != "" {
			s.tracker.Update(id, existing.Status, progress)
		}
		updated := s.tracker.Get(id)
		return jsonResult(updated)
	}

	// Register new agent
	if agentType == "" {
		agentType = "unknown"
	}
	s.tracker.Register(id, agentType, description, parentID)

	// If a non-pending status was provided, update immediately
	if status != "" && status != string(agents.StatusPending) {
		s.tracker.Update(id, agents.AgentStatus(status), progress)
	}

	info := s.tracker.Get(id)
	return jsonResult(info)
}
