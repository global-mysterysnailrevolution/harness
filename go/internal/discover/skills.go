package discover

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/global-mysterysnailrevolution/harness/pkg/frontmatter"
)

// ScanSkills scans the skills directory for SKILL.md files.
func ScanSkills(claudeDir string) []Capability {
	skillsDir := filepath.Join(claudeDir, "skills")
	var caps []Capability

	entries, err := os.ReadDir(skillsDir)
	if err != nil {
		return caps
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		skillFile := filepath.Join(skillsDir, entry.Name(), "SKILL.md")
		data, err := os.ReadFile(skillFile)
		if err != nil {
			continue
		}
		meta, body := frontmatter.Parse(string(data))
		desc := extractFirstLine(body)
		triggers := ""
		if t, ok := meta["triggers"]; ok {
			triggers = t
		}
		name := entry.Name()
		if n, ok := meta["name"]; ok {
			name = n
		}
		caps = append(caps, Capability{
			Name:        name,
			Kind:        "skill",
			Source:      skillFile,
			Description: desc,
			Triggers:    triggers,
			InvokeVia:   "skill:" + name,
		})
	}
	return caps
}

func extractFirstLine(s string) string {
	s = strings.TrimSpace(s)
	if idx := strings.IndexByte(s, '\n'); idx >= 0 {
		return strings.TrimSpace(s[:idx])
	}
	return s
}
