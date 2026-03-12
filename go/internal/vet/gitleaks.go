package vet

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
)

// GitleaksScanner wraps the gitleaks CLI for secret detection.
type GitleaksScanner struct {
	binPath string
}

// NewGitleaksScanner creates a new gitleaks scanner adapter.
func NewGitleaksScanner(override string) *GitleaksScanner {
	bin := "gitleaks"
	if override != "" {
		bin = override
	}
	return &GitleaksScanner{binPath: bin}
}

func (s *GitleaksScanner) Name() string { return "gitleaks" }

func (s *GitleaksScanner) Available() bool {
	_, err := exec.LookPath(s.binPath)
	return err == nil
}

func (s *GitleaksScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
	cmd := exec.CommandContext(ctx, s.binPath, "detect", "--source", path, "--report-format", "json", "--no-git")
	out, err := cmd.Output()
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			// gitleaks returns exit code 1 when leaks are found
			if len(out) > 0 {
				return parseGitleaksOutput(out)
			}
			if len(exitErr.Stderr) > 0 {
				return nil, fmt.Errorf("gitleaks error: %s", exitErr.Stderr)
			}
		}
		return nil, nil
	}
	return parseGitleaksOutput(out)
}

type gitleaksFinding struct {
	Description string `json:"Description"`
	File        string `json:"File"`
	StartLine   int    `json:"StartLine"`
	RuleID      string `json:"RuleID"`
}

func parseGitleaksOutput(data []byte) ([]Finding, error) {
	if len(data) == 0 {
		return nil, nil
	}
	var results []gitleaksFinding
	if err := json.Unmarshal(data, &results); err != nil {
		return nil, fmt.Errorf("parse gitleaks output: %w", err)
	}
	var findings []Finding
	for _, r := range results {
		findings = append(findings, Finding{
			Scanner:  "gitleaks",
			Severity: SevHigh,
			Title:    r.Description,
			Detail:   fmt.Sprintf("Secret detected by rule %s", r.RuleID),
			File:     r.File,
			Line:     r.StartLine,
			Rule:     r.RuleID,
		})
	}
	return findings, nil
}
