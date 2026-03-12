package mcp

import (
	mcplib "github.com/mark3labs/mcp-go/mcp"
)

// ToolDefinitions returns all MCP tool definitions.
func ToolDefinitions() []mcplib.Tool {
	return []mcplib.Tool{
		mcplib.NewTool("harness_vet",
			mcplib.WithDescription("Run security vetting pipeline on a file or directory."),
			mcplib.WithString("path", mcplib.Required(), mcplib.Description("Path to scan")),
			mcplib.WithString("scanners", mcplib.Description("Comma-separated scanner names")),
		),
		mcplib.NewTool("harness_classify",
			mcplib.WithDescription("Classify a tool action by risk level."),
			mcplib.WithString("tool", mcplib.Required(), mcplib.Description("Tool name")),
			mcplib.WithString("args_json", mcplib.Description("Tool arguments as JSON string")),
			mcplib.WithString("agent_role", mcplib.Description("Agent role for allowlist check")),
		),
		mcplib.NewTool("harness_audit_query",
			mcplib.WithDescription("Query the audit log."),
			mcplib.WithString("sid", mcplib.Description("Filter by session ID")),
			mcplib.WithString("tool", mcplib.Description("Filter by tool name")),
			mcplib.WithString("action_class", mcplib.Description("Filter by action class")),
		),
		mcplib.NewTool("harness_audit_stats",
			mcplib.WithDescription("Get aggregate statistics from the audit log."),
			mcplib.WithString("sid", mcplib.Description("Filter stats to a specific session")),
		),
		mcplib.NewTool("harness_route",
			mcplib.WithDescription("Route a task to the best matching skills and tools."),
			mcplib.WithString("task", mcplib.Required(), mcplib.Description("Task description")),
		),
		mcplib.NewTool("harness_discover",
			mcplib.WithDescription("Discover all available capabilities."),
			mcplib.WithString("search", mcplib.Description("Optional search term")),
		),
		mcplib.NewTool("harness_allowlist",
			mcplib.WithDescription("Get the tool allowlist for a specific agent role."),
			mcplib.WithString("role", mcplib.Required(), mcplib.Description("Agent role")),
		),
		mcplib.NewTool("harness_config",
			mcplib.WithDescription("Read or validate harness configuration."),
			mcplib.WithString("action", mcplib.Required(), mcplib.Description("get, validate, or dump")),
			mcplib.WithString("key", mcplib.Description("Config key to get")),
		),
	}
}
