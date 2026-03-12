package discover

// Capability represents a single discoverable capability.
type Capability struct {
	Name        string `json:"name"`
	Kind        string `json:"kind"`
	Source      string `json:"source"`
	Description string `json:"description"`
	Triggers    string `json:"triggers,omitempty"`
	InvokeVia   string `json:"invoke_via"`
}
