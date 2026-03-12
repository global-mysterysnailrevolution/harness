package audit

// Stats computes aggregate statistics from audit entries.
type Stats struct {
	TotalEntries int            `json:"total_entries"`
	ToolCounts   map[string]int `json:"tool_counts"`
	ClassCounts  map[string]int `json:"class_counts"`
	ErrorCount   int            `json:"error_count"`
	DeniedCount  int            `json:"denied_count"`
}

// ComputeStats computes statistics from a set of entries.
func ComputeStats(entries []AuditEntry) Stats {
	stats := Stats{
		ToolCounts:  make(map[string]int),
		ClassCounts: make(map[string]int),
	}
	for _, e := range entries {
		stats.TotalEntries++
		stats.ToolCounts[e.Tool]++
		stats.ClassCounts[e.ActionClass]++
		if e.HasError {
			stats.ErrorCount++
		}
		if !e.Allowed {
			stats.DeniedCount++
		}
	}
	return stats
}
