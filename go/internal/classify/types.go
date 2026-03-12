package classify

// ActionClass represents a classification of a tool action.
type ActionClass string

const (
	ActionRead        ActionClass = "read"
	ActionWrite       ActionClass = "write"
	ActionExec        ActionClass = "exec"
	ActionNetwork     ActionClass = "network"
	ActionCredential  ActionClass = "credential"
	ActionDestructive ActionClass = "destructive"
)

// ClassifyResult holds the result of classifying a tool action.
type ClassifyResult struct {
	Tool        string      `json:"tool"`
	ActionClass ActionClass `json:"action_class"`
	Score       float64     `json:"score"`
	Allowed     bool        `json:"allowed"`
	DenyReason  string      `json:"deny_reason,omitempty"`
	Keywords    []string    `json:"matched_keywords,omitempty"`
}
