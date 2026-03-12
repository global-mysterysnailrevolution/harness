package discover

import (
	"os"
	"path/filepath"
)

// ScanPlugins scans the plugins directory.
func ScanPlugins(claudeDir string) []Capability {
	pluginsDir := filepath.Join(claudeDir, "plugins")
	var caps []Capability

	entries, err := os.ReadDir(pluginsDir)
	if err != nil {
		return caps
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		name := entry.Name()
		caps = append(caps, Capability{
			Name:        name,
			Kind:        "plugin",
			Source:      filepath.Join(pluginsDir, name),
			Description: "Plugin: " + name,
			InvokeVia:   "plugin:" + name,
		})
	}
	return caps
}
