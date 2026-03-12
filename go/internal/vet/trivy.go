package vet

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strings"
)

// TrivyScanner wraps the trivy CLI for vulnerability scanning.
type TrivyScanner struct {
	binPath string
}

// NewTrivyScanner creates a new trivy scanner adapter.
func NewTrivyScanner(override string) *TrivyScanner {
	bin := "trivy"
	if override != "" {
		bin = override
	}
	return &TrivyScanner{binPath: bin}
}

func (s *TrivyScanner) Name() string { return "trivy" }

func (s *TrivyScanner) Available() bool {
	_, err := exec.LookPath(s.binPath)
	return err == nil
}

func (s *TrivyScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
	cmd := exec.CommandContext(ctx, s.binPath, "fs", "--format", "json", "--severity", "CRITICAL,HIGH,MEDIUM", path)
	out, err := cmd.Output()
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) && len(exitErr.Stderr) > 0 {
			return nil, fmt.Errorf("trivy error: %s", exitErr.Stderr)
		}
	}
	return parseTrivyOutput(out)
}

type trivyReport struct {
	Results []trivyResult `json:"Results"`
}

type trivyResult struct {
	Target          string         `json:"Target"`
	Vulnerabilities []trivyVuln    `json:"Vulnerabilities"`
}

type trivyVuln struct {
	VulnerabilityID string `json:"VulnerabilityID"`
	Title           string `json:"Title"`
	Description     string `json:"Description"`
	Severity        string `json:"Severity"`
}

func parseTrivyOutput(data []byte) ([]Finding, error) {
	if len(data) == 0 {
		return nil, nil
	}
	var report trivyReport
	if err := json.Unmarshal(data, &report); err != nil {
		return nil, fmt.Errorf("parse trivy output: %w", err)
	}
	var findings []Finding
	for _, result := range report.Results {
		for _, vuln := range result.Vulnerabilities {
			findings = append(findings, Finding{
				Scanner:  "trivy",
				Severity: normalizeSeverity(vuln.Severity),
				Title:    vuln.VulnerabilityID + ": " + vuln.Title,
				Detail:   vuln.Description,
				File:     result.Target,
				Rule:     vuln.VulnerabilityID,
			})
		}
	}
	return findings, nil
}

func normalizeSeverity(s string) Severity {
	switch strings.ToLower(s) {
	case "critical":
		return SevCritical
	case "high":
		return SevHigh
	case "medium":
		return SevMedium
	case "low":
		return SevLow
	default:
		return SevInfo
	}
}
