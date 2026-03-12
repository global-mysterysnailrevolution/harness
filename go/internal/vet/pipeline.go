package vet

import (
	"context"
	"time"

	"github.com/global-mysterysnailrevolution/harness/internal/config"
)

// Pipeline orchestrates multiple scanners in parallel.
type Pipeline struct {
	registry *ScannerRegistry
	policy   config.VettingPolicy
}

// NewPipeline creates a new vetting pipeline.
func NewPipeline(policy config.VettingPolicy, scannerPaths map[string]string) *Pipeline {
	return &Pipeline{
		registry: NewScannerRegistry(scannerPaths),
		policy:   policy,
	}
}

// Run executes the pipeline against a path.
func (p *Pipeline) Run(ctx context.Context, path string, requested []string) (*VetReport, error) {
	scanners := p.registry.Select(requested)

	var available []Scanner
	var unavailable []string
	for _, s := range scanners {
		if s.Available() {
			available = append(available, s)
		} else {
			unavailable = append(unavailable, s.Name())
		}
	}

	type result struct {
		findings []Finding
		err      error
		scanner  string
	}

	results := make(chan result, len(available))
	for _, s := range available {
		go func(scanner Scanner) {
			findings, err := scanner.Scan(ctx, path)
			results <- result{findings: findings, err: err, scanner: scanner.Name()}
		}(s)
	}

	var allFindings []Finding
	var scannersRun []string
	for i := 0; i < len(available); i++ {
		r := <-results
		scannersRun = append(scannersRun, r.scanner)
		if r.err == nil {
			allFindings = append(allFindings, r.findings...)
		}
	}

	report := &VetReport{
		Path:        path,
		Timestamp:   time.Now(),
		Scanners:    scannersRun,
		Unavailable: unavailable,
		Findings:    allFindings,
	}

	// Compute summary
	report.Summary = computeSummary(allFindings)

	// Evaluate policy
	report.PassedPolicy = evaluatePolicy(report.Summary, p.policy)

	return report, nil
}

func computeSummary(findings []Finding) Summary {
	var s Summary
	for _, f := range findings {
		switch f.Severity {
		case SevCritical:
			s.Critical++
		case SevHigh:
			s.High++
		case SevMedium:
			s.Medium++
		case SevLow:
			s.Low++
		case SevInfo:
			s.Info++
		}
	}
	return s
}

func evaluatePolicy(s Summary, policy config.VettingPolicy) bool {
	for sev, max := range policy.FailThresholds {
		switch Severity(sev) {
		case SevCritical:
			if s.Critical > max {
				return false
			}
		case SevHigh:
			if s.High > max {
				return false
			}
		case SevMedium:
			if s.Medium > max {
				return false
			}
		case SevLow:
			if s.Low > max {
				return false
			}
		}
	}
	return true
}
