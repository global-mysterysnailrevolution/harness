package agents

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func tempDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	return dir
}

func TestNewTracker(t *testing.T) {
	dir := tempDir(t)
	tracker, err := NewTracker(dir)
	if err != nil {
		t.Fatalf("NewTracker failed: %v", err)
	}
	if tracker == nil {
		t.Fatal("tracker is nil")
	}
	// Cancel dir should exist
	cancelDir := filepath.Join(dir, "cancel")
	if _, err := os.Stat(cancelDir); os.IsNotExist(err) {
		t.Error("cancel directory was not created")
	}
}

func TestRegisterAndGet(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("agent-1", "implementer", "Build feature X", "")
	info := tracker.Get("agent-1")
	if info == nil {
		t.Fatal("agent-1 not found")
	}
	if info.ID != "agent-1" {
		t.Errorf("expected ID agent-1, got %s", info.ID)
	}
	if info.Type != "implementer" {
		t.Errorf("expected type implementer, got %s", info.Type)
	}
	if info.Description != "Build feature X" {
		t.Errorf("unexpected description: %s", info.Description)
	}
	if info.Status != StatusPending {
		t.Errorf("expected pending, got %s", info.Status)
	}
}

func TestGetNotFound(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	info := tracker.Get("nonexistent")
	if info != nil {
		t.Error("expected nil for nonexistent agent")
	}
}

func TestUpdate(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("agent-2", "researcher", "Research topic Y", "")
	tracker.Update("agent-2", StatusRunning, "Starting research")

	info := tracker.Get("agent-2")
	if info.Status != StatusRunning {
		t.Errorf("expected running, got %s", info.Status)
	}
	if info.Progress != "Starting research" {
		t.Errorf("unexpected progress: %s", info.Progress)
	}
}

func TestUpdateNonexistent(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)
	// Should not panic
	tracker.Update("ghost", StatusRunning, "boo")
}

func TestCancel(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("agent-3", "implementer", "Build feature Z", "")
	tracker.Update("agent-3", StatusRunning, "Working")

	err := tracker.Cancel("agent-3")
	if err != nil {
		t.Fatalf("Cancel failed: %v", err)
	}

	info := tracker.Get("agent-3")
	if info.Status != StatusCancelled {
		t.Errorf("expected cancelled, got %s", info.Status)
	}

	// Cancel signal file should exist
	cancelFile := filepath.Join(dir, "cancel", "agent-3")
	if _, err := os.Stat(cancelFile); os.IsNotExist(err) {
		t.Error("cancel signal file not created")
	}
}

func TestCancelNotFound(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	err := tracker.Cancel("nonexistent")
	if err == nil {
		t.Error("expected error for nonexistent agent")
	}
}

func TestCancelAlreadyComplete(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("agent-4", "tester", "Run tests", "")
	tracker.Update("agent-4", StatusComplete, "Done")

	err := tracker.Cancel("agent-4")
	if err == nil {
		t.Error("expected error for completed agent")
	}
}

func TestList(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("a1", "implementer", "Task 1", "")
	time.Sleep(10 * time.Millisecond) // ensure different timestamps
	tracker.Register("a2", "researcher", "Task 2", "")
	time.Sleep(10 * time.Millisecond)
	tracker.Register("a3", "tester", "Task 3", "a1")

	list := tracker.List()
	if len(list) != 3 {
		t.Fatalf("expected 3 agents, got %d", len(list))
	}
	// Newest first
	if list[0].ID != "a3" {
		t.Errorf("expected a3 first, got %s", list[0].ID)
	}
}

func TestActive(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("a1", "implementer", "Task 1", "")
	tracker.Register("a2", "researcher", "Task 2", "")
	tracker.Update("a1", StatusRunning, "Working")
	tracker.Update("a2", StatusComplete, "Done")

	active := tracker.Active()
	if len(active) != 1 {
		t.Fatalf("expected 1 active, got %d", len(active))
	}
	if active[0].ID != "a1" {
		t.Errorf("expected a1 active, got %s", active[0].ID)
	}
}

func TestEvents(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	before := time.Now().Add(-time.Second)
	tracker.Register("a1", "implementer", "Task 1", "")
	tracker.Update("a1", StatusRunning, "Working")
	tracker.Update("a1", StatusComplete, "Done")

	events := tracker.Events(before)
	if len(events) != 3 {
		t.Fatalf("expected 3 events, got %d", len(events))
	}
	if events[0].Type != "spawn" {
		t.Errorf("expected spawn event first, got %s", events[0].Type)
	}
	if events[2].Type != "complete" {
		t.Errorf("expected complete event last, got %s", events[2].Type)
	}
}

func TestSubscribe(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	ch, unsub := tracker.Subscribe()
	defer unsub()

	tracker.Register("a1", "implementer", "Task 1", "")

	select {
	case ev := <-ch:
		if ev.Type != "spawn" {
			t.Errorf("expected spawn event, got %s", ev.Type)
		}
		if ev.AgentID != "a1" {
			t.Errorf("expected agent a1, got %s", ev.AgentID)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for event")
	}
}

func TestPersistAndLoad(t *testing.T) {
	dir := tempDir(t)

	// Create and populate a tracker
	tracker1, _ := NewTracker(dir)
	tracker1.Register("a1", "implementer", "Task 1", "")
	tracker1.Update("a1", StatusRunning, "Working")

	// Create a new tracker that loads from the same dir
	tracker2, err := NewTracker(dir)
	if err != nil {
		t.Fatalf("NewTracker (reload) failed: %v", err)
	}

	info := tracker2.Get("a1")
	if info == nil {
		t.Fatal("a1 not found after reload")
	}
	if info.Status != StatusRunning {
		t.Errorf("expected running after reload, got %s", info.Status)
	}
	if info.Progress != "Working" {
		t.Errorf("expected progress 'Working' after reload, got %s", info.Progress)
	}
}

func TestEventRingBuffer(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	// Generate more than maxEvents
	for i := 0; i < maxEvents+20; i++ {
		tracker.Register(
			"agent-overflow-"+time.Now().Format("150405.000000000"),
			"tester",
			"overflow test",
			"",
		)
	}

	before := time.Time{}
	events := tracker.Events(before)
	if len(events) > maxEvents {
		t.Errorf("expected at most %d events, got %d", maxEvents, len(events))
	}
}

func TestFormatDuration(t *testing.T) {
	tests := []struct {
		d    time.Duration
		want string
	}{
		{0, "0s"},
		{500 * time.Millisecond, "0s"},
		{5 * time.Second, "5s"},
		{90 * time.Second, "1m 30s"},
		{3661 * time.Second, "1h 1m 1s"},
	}

	for _, tt := range tests {
		got := formatDuration(tt.d)
		if got != tt.want {
			t.Errorf("formatDuration(%v) = %q, want %q", tt.d, got, tt.want)
		}
	}
}

func TestParentID(t *testing.T) {
	dir := tempDir(t)
	tracker, _ := NewTracker(dir)

	tracker.Register("parent", "orchestrator", "Main task", "")
	tracker.Register("child", "implementer", "Sub task", "parent")

	child := tracker.Get("child")
	if child.ParentID != "parent" {
		t.Errorf("expected parent_id 'parent', got %q", child.ParentID)
	}
}
