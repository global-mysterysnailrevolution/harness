package discover

import "strings"

// Registry holds all discovered capabilities.
type Registry struct {
	claudeDir    string
	capabilities []Capability
	loaded       bool
}

// NewRegistry creates a new capability registry.
func NewRegistry(claudeDir string) *Registry {
	return &Registry{claudeDir: claudeDir}
}

// All returns all discovered capabilities.
func (r *Registry) All() []Capability {
	r.ensureLoaded()
	return r.capabilities
}

// Search returns capabilities matching the search term.
func (r *Registry) Search(term string) []Capability {
	r.ensureLoaded()
	if term == "" {
		return r.capabilities
	}
	lower := strings.ToLower(term)
	var matches []Capability
	for _, c := range r.capabilities {
		if strings.Contains(strings.ToLower(c.Name), lower) ||
			strings.Contains(strings.ToLower(c.Description), lower) ||
			strings.Contains(strings.ToLower(c.Triggers), lower) {
			matches = append(matches, c)
		}
	}
	return matches
}

func (r *Registry) ensureLoaded() {
	if r.loaded {
		return
	}
	r.loaded = true

	// Scan all sources
	r.capabilities = append(r.capabilities, ScanSkills(r.claudeDir)...)
	r.capabilities = append(r.capabilities, ScanPlugins(r.claudeDir)...)
	r.capabilities = append(r.capabilities, ScanMCP(r.claudeDir)...)

	// Add builtins
	r.capabilities = append(r.capabilities, builtinCapabilities()...)
}

func builtinCapabilities() []Capability {
	return []Capability{
		{Name: "Read", Kind: "builtin", Source: "builtin", Description: "Read a file", InvokeVia: "tool:Read"},
		{Name: "Write", Kind: "builtin", Source: "builtin", Description: "Write a file", InvokeVia: "tool:Write"},
		{Name: "Edit", Kind: "builtin", Source: "builtin", Description: "Edit a file", InvokeVia: "tool:Edit"},
		{Name: "Bash", Kind: "builtin", Source: "builtin", Description: "Execute a bash command", InvokeVia: "tool:Bash"},
		{Name: "Glob", Kind: "builtin", Source: "builtin", Description: "File pattern matching", InvokeVia: "tool:Glob"},
		{Name: "Grep", Kind: "builtin", Source: "builtin", Description: "Search file contents", InvokeVia: "tool:Grep"},
		{Name: "WebFetch", Kind: "builtin", Source: "builtin", Description: "Fetch web page content", InvokeVia: "tool:WebFetch"},
	}
}
