package agents

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

// AgentStatus represents the current status of an agent.
type AgentStatus string

const (
	StatusPending   AgentStatus = "pending"
	StatusRunning   AgentStatus = "running"
	StatusComplete  AgentStatus = "complete"
	StatusFailed    AgentStatus = "failed"
	StatusCancelled AgentStatus = "cancelled"
)

// AgentInfo holds metadata about a running or completed agent.
type AgentInfo struct {
	ID          string      `json:"id"`
	Type        string      `json:"type"`
	Description string      `json:"description"`
	Status      AgentStatus `json:"status"`
	StartedAt   time.Time   `json:"started_at"`
	UpdatedAt   time.Time   `json:"updated_at"`
	Duration    string      `json:"duration"`
	Progress    string      `json:"progress"`
	ParentID    string      `json:"parent_id,omitempty"`
}

// AgentEvent represents a lifecycle event for an agent.
type AgentEvent struct {
	Type      string    `json:"type"`
	AgentID   string    `json:"agent_id"`
	Timestamp time.Time `json:"ts"`
	Detail    string    `json:"detail"`
}

const maxEvents = 100

// Tracker provides concurrent-safe in-memory tracking of agent status.
// It persists state to disk and supports SSE subscribers.
type Tracker struct {
	mu       sync.RWMutex
	agents   map[string]*AgentInfo
	events   []AgentEvent
	subs     []chan AgentEvent
	stateDir string // directory for agents.json and cancel signals
}

// NewTracker creates a new Tracker that persists state under stateDir.
// It loads any previously persisted state from stateDir/agents.json.
func NewTracker(stateDir string) (*Tracker, error) {
	t := &Tracker{
		agents:   make(map[string]*AgentInfo),
		events:   make([]AgentEvent, 0, maxEvents),
		stateDir: stateDir,
	}

	// Ensure directories exist
	if err := os.MkdirAll(stateDir, 0o755); err != nil {
		return nil, fmt.Errorf("create state dir: %w", err)
	}
	cancelDir := filepath.Join(stateDir, "cancel")
	if err := os.MkdirAll(cancelDir, 0o755); err != nil {
		return nil, fmt.Errorf("create cancel dir: %w", err)
	}

	// Load persisted state
	if err := t.load(); err != nil && !os.IsNotExist(err) {
		// Non-fatal: log to stderr and start fresh
		fmt.Fprintf(os.Stderr, "warning: could not load agent state: %v\n", err)
	}

	return t, nil
}

// Register adds a new agent to the tracker.
func (t *Tracker) Register(id, agentType, description, parentID string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	now := time.Now()
	info := &AgentInfo{
		ID:          id,
		Type:        agentType,
		Description: description,
		Status:      StatusPending,
		StartedAt:   now,
		UpdatedAt:   now,
		Duration:    "0s",
		ParentID:    parentID,
	}
	t.agents[id] = info
	t.addEvent(AgentEvent{
		Type:      "spawn",
		AgentID:   id,
		Timestamp: now,
		Detail:    fmt.Sprintf("Agent %s (%s) registered: %s", id, agentType, description),
	})
	t.persistLocked()
}

// Update changes the status and progress of an existing agent.
func (t *Tracker) Update(id string, status AgentStatus, progress string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	info, ok := t.agents[id]
	if !ok {
		return
	}

	now := time.Now()
	info.Status = status
	info.Progress = progress
	info.UpdatedAt = now
	info.Duration = formatDuration(now.Sub(info.StartedAt))

	eventType := "update"
	switch status {
	case StatusComplete:
		eventType = "complete"
	case StatusFailed:
		eventType = "fail"
	case StatusCancelled:
		eventType = "cancel"
	}

	t.addEvent(AgentEvent{
		Type:      eventType,
		AgentID:   id,
		Timestamp: now,
		Detail:    fmt.Sprintf("Agent %s -> %s: %s", id, status, progress),
	})
	t.persistLocked()
}

// Cancel marks an agent as cancelled and writes a cancel signal file.
func (t *Tracker) Cancel(id string) error {
	t.mu.Lock()
	defer t.mu.Unlock()

	info, ok := t.agents[id]
	if !ok {
		return fmt.Errorf("agent %q not found", id)
	}
	if info.Status != StatusPending && info.Status != StatusRunning {
		return fmt.Errorf("agent %q is %s, cannot cancel", id, info.Status)
	}

	now := time.Now()
	info.Status = StatusCancelled
	info.UpdatedAt = now
	info.Duration = formatDuration(now.Sub(info.StartedAt))

	// Write cancel signal file
	cancelFile := filepath.Join(t.stateDir, "cancel", id)
	if err := os.WriteFile(cancelFile, []byte(now.Format(time.RFC3339)), 0o644); err != nil {
		return fmt.Errorf("write cancel signal: %w", err)
	}

	t.addEvent(AgentEvent{
		Type:      "cancel",
		AgentID:   id,
		Timestamp: now,
		Detail:    fmt.Sprintf("Agent %s cancelled", id),
	})
	t.persistLocked()
	return nil
}

// Get returns a single agent's info, or nil if not found.
func (t *Tracker) Get(id string) *AgentInfo {
	t.mu.RLock()
	defer t.mu.RUnlock()

	info, ok := t.agents[id]
	if !ok {
		return nil
	}
	// Return a copy with updated duration
	cp := *info
	if cp.Status == StatusRunning || cp.Status == StatusPending {
		cp.Duration = formatDuration(time.Since(cp.StartedAt))
	}
	return &cp
}

// List returns all agents sorted by start time (newest first).
func (t *Tracker) List() []*AgentInfo {
	t.mu.RLock()
	defer t.mu.RUnlock()

	result := make([]*AgentInfo, 0, len(t.agents))
	for _, info := range t.agents {
		cp := *info
		if cp.Status == StatusRunning || cp.Status == StatusPending {
			cp.Duration = formatDuration(time.Since(cp.StartedAt))
		}
		result = append(result, &cp)
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].StartedAt.After(result[j].StartedAt)
	})
	return result
}

// Active returns only agents with pending or running status.
func (t *Tracker) Active() []*AgentInfo {
	all := t.List()
	active := make([]*AgentInfo, 0)
	for _, a := range all {
		if a.Status == StatusPending || a.Status == StatusRunning {
			active = append(active, a)
		}
	}
	return active
}

// Events returns events that occurred after since.
func (t *Tracker) Events(since time.Time) []AgentEvent {
	t.mu.RLock()
	defer t.mu.RUnlock()

	result := make([]AgentEvent, 0)
	for _, ev := range t.events {
		if ev.Timestamp.After(since) {
			result = append(result, ev)
		}
	}
	return result
}

// Subscribe returns a channel that receives agent events, plus an unsubscribe function.
func (t *Tracker) Subscribe() (<-chan AgentEvent, func()) {
	ch := make(chan AgentEvent, 32)
	t.mu.Lock()
	t.subs = append(t.subs, ch)
	t.mu.Unlock()

	unsubscribe := func() {
		t.mu.Lock()
		defer t.mu.Unlock()
		for i, sub := range t.subs {
			if sub == ch {
				t.subs = append(t.subs[:i], t.subs[i+1:]...)
				close(ch)
				return
			}
		}
	}
	return ch, unsubscribe
}

// addEvent appends an event to the ring buffer and notifies subscribers.
// Must be called with t.mu held.
func (t *Tracker) addEvent(ev AgentEvent) {
	if len(t.events) >= maxEvents {
		t.events = t.events[1:]
	}
	t.events = append(t.events, ev)

	// Notify all subscribers (non-blocking)
	for _, ch := range t.subs {
		select {
		case ch <- ev:
		default:
			// Drop event if subscriber is slow
		}
	}
}

// persistLocked saves agent state to disk. Must be called with t.mu held.
func (t *Tracker) persistLocked() {
	path := filepath.Join(t.stateDir, "agents.json")
	data, err := json.MarshalIndent(t.agents, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "warning: marshal agents: %v\n", err)
		return
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "warning: persist agents: %v\n", err)
	}
}

// load reads persisted agent state from disk.
func (t *Tracker) load() error {
	path := filepath.Join(t.stateDir, "agents.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, &t.agents)
}

// formatDuration produces a human-readable duration string.
func formatDuration(d time.Duration) string {
	if d < time.Second {
		return "0s"
	}
	d = d.Round(time.Second)
	h := int(d.Hours())
	m := int(d.Minutes()) % 60
	s := int(d.Seconds()) % 60

	if h > 0 {
		return fmt.Sprintf("%dh %dm %ds", h, m, s)
	}
	if m > 0 {
		return fmt.Sprintf("%dm %ds", m, s)
	}
	return fmt.Sprintf("%ds", s)
}
