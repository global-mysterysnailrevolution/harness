package audit

import "time"

// AuditEntry represents a single audit log entry.
type AuditEntry struct {
	Timestamp  time.Time      `json:"ts"`
	SessionID  string         `json:"sid"`
	Project    string         `json:"project"`
	CWD        string         `json:"cwd"`
	Phase      string         `json:"phase"`
	Tool       string         `json:"tool"`
	ActionClass string        `json:"action_class"`
	AgentRole  string         `json:"agent_role,omitempty"`
	Input      map[string]any `json:"input,omitempty"`
	Output     map[string]any `json:"output,omitempty"`
	HasError   bool           `json:"has_error,omitempty"`
	DurationMs int64          `json:"duration_ms,omitempty"`
	Allowed    bool           `json:"allowed"`
	DenyReason string         `json:"deny_reason,omitempty"`
}

// AuditQuery defines filters for querying the audit log.
type AuditQuery struct {
	SessionID   string    `json:"sid,omitempty"`
	Tool        string    `json:"tool,omitempty"`
	ActionClass string    `json:"action_class,omitempty"`
	AgentRole   string    `json:"agent_role,omitempty"`
	Since       time.Time `json:"since,omitempty"`
	Until       time.Time `json:"until,omitempty"`
	HasError    *bool     `json:"has_error,omitempty"`
	Limit       int       `json:"limit,omitempty"`
}
