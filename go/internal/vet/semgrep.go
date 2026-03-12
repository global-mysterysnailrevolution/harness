package vet

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
)

// SemgrepScanner wraps the semgrep CLI for SAST analysis.
type SemgrepScanner struct {
	binPath string
}

// NewSemgrepScanner creates a new semgrep scanner adapter.
func NewSemgrepScanner(override string) *SemgrepScanner {
	bin := "semgrep"
	if override != "" {
		bin = override
	}
	return &SemgrepScanner{binPath: bin}
}

func (s *SemgrepScanner) Name() string { return "semgrep" }

func (s *SemgrepScanner) Available() bool {
	_, err := exec.LookPath(s.binPath)
	return err == nil
}

func (s *SemgrepScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
	cmd := exec.CommandContext(ctx, s.binPath, "scan", "--json", "--config", "auto", path)
	out, err := cmd.Output()
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && len(out) > 0 {
			return parseSemgrepOutput(out)
		}
		return nil, fmt.Errorf("semgrep error: %w", err)
	}
	return parseSemgrepOutput(out)
}

type semgrepOutput struct {
	Results []semgrepResult `json:"results"`
}

type semgrepResult struct {
	CheckID string        `json:"check_id"`
	Path    string        `json:"path"`
	Start   semgrepPos    `json:"start"`
	Extra   semgrepExtra  `json:"extra"`
}

type semgrepPos struct {
	Line int `json:"line"`
}

type semgrepExtra struct {
	Message  string `json:"message"`
	Severity string `json:"severity"`
}

func parseSemgrepOutput(data []byte) ([]Finding, error) {
	if len(data) == 0 {
		return nil, nil
	}
	var output semgrepOutput
	if err := json.Unmarshal(data, &output); err != nil {
		return nil, fmt.Errorf("parse semgrep output: %w", err)
	}
	var findings []Finding
	for _, r := range output.Results {
		findings = append(findings, Finding{
			Scanner:  "semgrep",
			Severity: normalizeSeverity(r.Extra.Severity),
			Title:    r.CheckID,
			Detail:   r.Extra.Message,
			File:     r.Path,
			Line:     r.Start.Line,
			Rule:     r.CheckID,
		})
	}
	return findings, nil
}
