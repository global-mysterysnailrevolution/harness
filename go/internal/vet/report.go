package vet

import (
	"fmt"
	"strings"
)

// FormatText returns a human-readable text representation of the report.
func (r *VetReport) FormatText() string {
	var b strings.Builder
	fmt.Fprintf(&b, "=== Vet Report: %s ===\n", r.Path)
	fmt.Fprintf(&b, "Time: %s\n", r.Timestamp.Format("2006-01-02 15:04:05"))
	fmt.Fprintf(&b, "Scanners: %s\n", strings.Join(r.Scanners, ", "))
	if len(r.Unavailable) > 0 {
		fmt.Fprintf(&b, "Unavailable: %s\n", strings.Join(r.Unavailable, ", "))
	}
	fmt.Fprintf(&b, "\nSummary: critical=%d high=%d medium=%d low=%d info=%d\n",
		r.Summary.Critical, r.Summary.High, r.Summary.Medium, r.Summary.Low, r.Summary.Info)
	fmt.Fprintf(&b, "Policy: %s\n\n", map[bool]string{true: "PASSED", false: "FAILED"}[r.PassedPolicy])

	for _, f := range r.Findings {
		fmt.Fprintf(&b, "[%s] %s: %s\n", f.Severity, f.Scanner, f.Title)
		if f.File != "" {
			fmt.Fprintf(&b, "  File: %s", f.File)
			if f.Line > 0 {
				fmt.Fprintf(&b, ":%d", f.Line)
			}
			fmt.Fprintln(&b)
		}
		if f.Detail != "" {
			fmt.Fprintf(&b, "  %s\n", f.Detail)
		}
	}
	return b.String()
}
