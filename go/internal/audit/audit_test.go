package audit

import (
	"testing"
	"time"
)

func TestWriteAndQuery(t *testing.T) {
	dir := t.TempDir()

	w, err := NewWriter(dir, 10*1024*1024, 5)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Write entries
	entries := []AuditEntry{
		{
			Timestamp:   time.Now().Add(-2 * time.Hour),
			SessionID:   "session-1",
			Tool:        "Read",
			ActionClass: "read",
			Phase:       "pre",
			Allowed:     true,
		},
		{
			Timestamp:   time.Now().Add(-1 * time.Hour),
			SessionID:   "session-1",
			Tool:        "Bash",
			ActionClass: "exec",
			Phase:       "pre",
			Allowed:     true,
			AgentRole:   "implementer",
		},
		{
			Timestamp:   time.Now(),
			SessionID:   "session-2",
			Tool:        "Write",
			ActionClass: "write",
			Phase:       "post",
			Allowed:     false,
			DenyReason:  "not allowed for scanner",
			HasError:    true,
		},
	}

	for _, e := range entries {
		if err := w.Write(e); err != nil {
			t.Fatal(err)
		}
	}

	// Query all
	reader := NewReader(dir)
	results, err := reader.Query(AuditQuery{Limit: 100})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 3 {
		t.Errorf("expected 3 entries, got %d", len(results))
	}

	// Query by tool
	results, err = reader.Query(AuditQuery{Tool: "Bash", Limit: 100})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 {
		t.Errorf("expected 1 Bash entry, got %d", len(results))
	}

	// Query by session
	results, err = reader.Query(AuditQuery{SessionID: "session-2", Limit: 100})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 {
		t.Errorf("expected 1 session-2 entry, got %d", len(results))
	}

	// Query errors
	errFlag := true
	results, err = reader.Query(AuditQuery{HasError: &errFlag, Limit: 100})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 {
		t.Errorf("expected 1 error entry, got %d", len(results))
	}

	// Query by action class
	results, err = reader.Query(AuditQuery{ActionClass: "read", Limit: 100})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 {
		t.Errorf("expected 1 read entry, got %d", len(results))
	}
}

func TestRotation(t *testing.T) {
	dir := t.TempDir()

	// Small max size to trigger rotation
	w, err := NewWriter(dir, 100, 3)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Write enough entries to trigger rotation
	for i := 0; i < 20; i++ {
		e := AuditEntry{
			Timestamp:   time.Now(),
			SessionID:   "session-test",
			Tool:        "Read",
			ActionClass: "read",
			Phase:       "pre",
			Allowed:     true,
		}
		if err := w.Write(e); err != nil {
			t.Fatal(err)
		}
	}

	// Should still be able to query
	reader := NewReader(dir)
	results, err := reader.ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(results) == 0 {
		t.Error("expected some entries after rotation")
	}
}

func TestComputeStats(t *testing.T) {
	entries := []AuditEntry{
		{Tool: "Read", ActionClass: "read", Allowed: true},
		{Tool: "Read", ActionClass: "read", Allowed: true},
		{Tool: "Bash", ActionClass: "exec", Allowed: true},
		{Tool: "Write", ActionClass: "write", Allowed: false, HasError: true},
	}

	stats := ComputeStats(entries)

	if stats.TotalEntries != 4 {
		t.Errorf("expected 4 total, got %d", stats.TotalEntries)
	}
	if stats.ToolCounts["Read"] != 2 {
		t.Errorf("expected 2 Read, got %d", stats.ToolCounts["Read"])
	}
	if stats.ErrorCount != 1 {
		t.Errorf("expected 1 error, got %d", stats.ErrorCount)
	}
	if stats.DeniedCount != 1 {
		t.Errorf("expected 1 denied, got %d", stats.DeniedCount)
	}
}

func TestQueryWithLimit(t *testing.T) {
	dir := t.TempDir()

	w, err := NewWriter(dir, 10*1024*1024, 5)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	for i := 0; i < 10; i++ {
		_ = w.Write(AuditEntry{
			Timestamp: time.Now(),
			Tool:      "Read",
			Allowed:   true,
		})
	}

	reader := NewReader(dir)
	results, err := reader.Query(AuditQuery{Limit: 3})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 3 {
		t.Errorf("expected 3 entries with limit, got %d", len(results))
	}
}
