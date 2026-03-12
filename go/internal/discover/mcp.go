package discover

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type mcpConfig struct {
	MCPServers map[string]mcpServerEntry `json:"mcpServers"`
}

type mcpServerEntry struct {
	Command string   `json:"command"`
	Args    []string `json:"args"`
}

// ScanMCP scans .mcp.json files for MCP server definitions.
func ScanMCP(claudeDir string) []Capability {
	var caps []Capability

	mcpFile := filepath.Join(claudeDir, ".mcp.json")
	data, err := os.ReadFile(mcpFile)
	if err != nil {
		return caps
	}

	var cfg mcpConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		return caps
	}

	for name, entry := range cfg.MCPServers {
		caps = append(caps, Capability{
			Name:        name,
			Kind:        "mcp",
			Source:      mcpFile,
			Description: "MCP server: " + entry.Command,
			InvokeVia:   "mcp:" + name,
		})
	}
	return caps
}
