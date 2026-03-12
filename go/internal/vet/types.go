package vet

import "time"

// Severity represents the severity level of a finding.
type Severity string

const (
	SevCritical Severity = "critical"
	SevHigh     Severity = "high"
	SevMedium   Severity = "medium"
	SevLow      Severity = "low"
	SevInfo     Severity = "info"
)

// Finding represents a single security finding.
type Finding struct {
	Scanner  string   `json:"scanner"`
	Severity Severity `json:"severity"`
	Title    string   `json:"title"`
	Detail   string   `json:"detail"`
	File     string   `json:"file,omitempty"`
	Line     int      `json:"line,omitempty"`
	Rule     string   `json:"rule,omitempty"`
}

// VetReport is the complete output of a vetting run.
type VetReport struct {
	Path         string    `json:"path"`
	Timestamp    time.Time `json:"timestamp"`
	Scanners     []string  `json:"scanners_run"`
	Unavailable  []string  `json:"scanners_unavailable"`
	Findings     []Finding `json:"findings"`
	PassedPolicy bool      `json:"passed_policy"`
	Summary      Summary   `json:"summary"`
}

// Summary counts findings by severity.
type Summary struct {
	Critical int `json:"critical"`
	High     int `json:"high"`
	Medium   int `json:"medium"`
	Low      int `json:"low"`
	Info     int `json:"info"`
}
