package vet

import "context"

// Scanner is the interface that all security scanners must implement.
type Scanner interface {
	// Name returns the scanner identifier.
	Name() string
	// Available returns true if the scanner binary is installed and reachable.
	Available() bool
	// Scan runs the scanner against the given path and returns findings.
	Scan(ctx context.Context, path string) ([]Finding, error)
}

// ScannerRegistry holds all known scanners.
type ScannerRegistry struct {
	scanners []Scanner
}

// NewScannerRegistry creates a registry with all known scanners.
func NewScannerRegistry(paths map[string]string) *ScannerRegistry {
	return &ScannerRegistry{
		scanners: []Scanner{
			NewTrivyScanner(paths["trivy"]),
			NewGitleaksScanner(paths["gitleaks"]),
			NewSemgrepScanner(paths["semgrep"]),
			NewSecretScanScanner(),
			NewPathTraversalScanner(),
		},
	}
}

// Select returns scanners matching the requested names. If names is empty, returns all.
func (r *ScannerRegistry) Select(names []string) []Scanner {
	if len(names) == 0 {
		return r.scanners
	}
	nameSet := make(map[string]bool)
	for _, n := range names {
		nameSet[n] = true
	}
	var result []Scanner
	for _, s := range r.scanners {
		if nameSet[s.Name()] {
			result = append(result, s)
		}
	}
	return result
}
