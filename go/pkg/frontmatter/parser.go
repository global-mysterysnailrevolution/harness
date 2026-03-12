package frontmatter

import (
	"strings"

	"gopkg.in/yaml.v3"
)

// Parse extracts YAML frontmatter from a markdown document.
// Returns the parsed metadata map and the body without frontmatter.
// If no valid frontmatter is found, returns nil and the original content unchanged.
func Parse(content string) (map[string]string, string) {
	trimmed := strings.TrimSpace(content)

	// Must start with ---
	if !strings.HasPrefix(trimmed, "---") {
		return nil, content
	}

	// Find closing ---
	rest := trimmed[3:]
	// Must have a newline after opening ---
	nlIdx := strings.IndexByte(rest, '\n')
	if nlIdx < 0 {
		return nil, content
	}

	// Look for closing --- on its own line
	afterFirst := rest[nlIdx+1:]
	idx := strings.Index(afterFirst, "\n---")
	if idx < 0 {
		// Check if --- is at the very start of afterFirst (empty frontmatter with immediate close)
		if strings.HasPrefix(afterFirst, "---") {
			// Empty frontmatter
			body := strings.TrimSpace(afterFirst[3:])
			return make(map[string]string), body
		}
		return nil, content
	}

	frontmatterStr := rest[nlIdx+1:][:idx]
	body := strings.TrimSpace(afterFirst[idx+4:])

	var raw map[string]interface{}
	if err := yaml.Unmarshal([]byte(frontmatterStr), &raw); err != nil {
		return nil, content
	}

	// nil raw means empty YAML (e.g., empty string between ---)
	if raw == nil {
		return make(map[string]string), body
	}

	result := make(map[string]string)
	for k, v := range raw {
		switch val := v.(type) {
		case string:
			result[k] = val
		default:
			b, _ := yaml.Marshal(v)
			result[k] = strings.TrimSpace(string(b))
		}
	}

	return result, body
}
