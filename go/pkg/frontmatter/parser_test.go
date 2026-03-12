package frontmatter

import (
	"testing"
)

func TestParseBasicFrontmatter(t *testing.T) {
	content := `---
name: my-skill
triggers: /myskill, myskill
---
# My Skill

This is a skill description.
`
	meta, body := Parse(content)
	if meta == nil {
		t.Fatal("expected non-nil metadata")
	}
	if meta["name"] != "my-skill" {
		t.Errorf("expected name 'my-skill', got %q", meta["name"])
	}
	if meta["triggers"] != "/myskill, myskill" {
		t.Errorf("expected triggers '/myskill, myskill', got %q", meta["triggers"])
	}
	if body == "" {
		t.Error("expected non-empty body")
	}
	if body[:10] != "# My Skill" {
		t.Errorf("expected body to start with '# My Skill', got %q", body[:10])
	}
}

func TestParseNoFrontmatter(t *testing.T) {
	content := `# Just a regular markdown file

No frontmatter here.
`
	meta, body := Parse(content)
	if meta != nil {
		t.Errorf("expected nil metadata, got %v", meta)
	}
	if body != content {
		t.Error("expected body to equal original content")
	}
}

func TestParseEmptyFrontmatter(t *testing.T) {
	content := `---
---
# Content after empty frontmatter
`
	meta, body := Parse(content)
	if meta == nil {
		t.Fatal("expected non-nil metadata (empty map)")
	}
	if len(meta) != 0 {
		t.Errorf("expected empty metadata, got %v", meta)
	}
	if body == "" {
		t.Error("expected non-empty body")
	}
}

func TestParseMultipleValues(t *testing.T) {
	content := `---
name: test-skill
version: "1.0"
description: A test skill for testing
---
Body content here.
`
	meta, _ := Parse(content)
	if meta == nil {
		t.Fatal("expected non-nil metadata")
	}
	if meta["name"] != "test-skill" {
		t.Errorf("expected name 'test-skill', got %q", meta["name"])
	}
	if meta["version"] != "1.0" {
		t.Errorf("expected version '1.0', got %q", meta["version"])
	}
	if meta["description"] != "A test skill for testing" {
		t.Errorf("expected description, got %q", meta["description"])
	}
}

func TestParseMalformedYAML(t *testing.T) {
	content := `---
: invalid yaml [[[
---
Body.
`
	meta, body := Parse(content)
	// Should return nil meta and original content on parse error
	if meta != nil {
		t.Errorf("expected nil meta for malformed YAML, got %v", meta)
	}
	if body != content {
		t.Error("expected body to equal original content on parse error")
	}
}

func TestParseNoClosingDelimiter(t *testing.T) {
	content := `---
name: test
This never closes.
`
	meta, body := Parse(content)
	if meta != nil {
		t.Error("expected nil meta when closing delimiter is missing")
	}
	if body != content {
		t.Error("expected body to equal original content")
	}
}
