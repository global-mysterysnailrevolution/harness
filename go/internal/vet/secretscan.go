package vet

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// SecretScanScanner is a built-in scanner for detecting hardcoded secrets.
type SecretScanScanner struct{}

// NewSecretScanScanner creates a new secret scan scanner.
func NewSecretScanScanner() *SecretScanScanner {
	return &SecretScanScanner{}
}

func (s *SecretScanScanner) Name() string    { return "secretscan" }
func (s *SecretScanScanner) Available() bool  { return true } // always available (built-in)

type secretPattern struct {
	name     string
	severity Severity
	pattern  *regexp.Regexp
}

var secretPatterns = []secretPattern{
	{
		name:     "AWS Access Key",
		severity: SevCritical,
		pattern:  regexp.MustCompile(`(?i)AKIA[0-9A-Z]{16}`),
	},
	{
		name:     "AWS Secret Key",
		severity: SevCritical,
		pattern:  regexp.MustCompile("(?i)aws[_-]?secret[_-]?access[_-]?key\\s*[=:]\\s*['\"]?[A-Za-z0-9/+=]{40}"),
	},
	{
		name:     "Private Key Block",
		severity: SevCritical,
		pattern:  regexp.MustCompile(`-----BEGIN\s+(RSA|DSA|EC|OPENSSH)?\s*PRIVATE KEY-----`),
	},
	{
		name:     "Generic API Key",
		severity: SevHigh,
		pattern:  regexp.MustCompile(`(?i)(api[_\-]?key|apikey)\s*[=:]\s*['"][A-Za-z0-9_\-]{20,}['"]`),
	},
	{
		name:     "Generic Secret",
		severity: SevHigh,
		pattern:  regexp.MustCompile(`(?i)(secret|password|passwd|pwd)\s*[=:]\s*['"][^'"]{8,}['"]`),
	},
	{
		name:     "JWT Token",
		severity: SevHigh,
		pattern:  regexp.MustCompile(`eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-]{10,}`),
	},
	{
		name:     "GitHub Token",
		severity: SevCritical,
		pattern:  regexp.MustCompile(`(?i)(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}`),
	},
	{
		name:     "Slack Token",
		severity: SevHigh,
		pattern:  regexp.MustCompile(`xox[bprs]-[0-9]{10,}-[0-9A-Za-z-]+`),
	},
}

// skipExtensions are file types we should not scan for secrets.
var skipExtensions = map[string]bool{
	".exe": true, ".dll": true, ".so": true, ".dylib": true,
	".png": true, ".jpg": true, ".jpeg": true, ".gif": true, ".ico": true,
	".woff": true, ".woff2": true, ".ttf": true, ".eot": true,
	".zip": true, ".tar": true, ".gz": true, ".bz2": true,
	".pdf": true, ".mp3": true, ".mp4": true, ".avi": true,
}

func (s *SecretScanScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
	var findings []Finding

	err := filepath.Walk(path, func(fp string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // skip errors
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if info.IsDir() {
			base := filepath.Base(fp)
			if base == ".git" || base == "node_modules" || base == "vendor" || base == "__pycache__" {
				return filepath.SkipDir
			}
			return nil
		}
		// Skip binary/large files
		ext := strings.ToLower(filepath.Ext(fp))
		if skipExtensions[ext] {
			return nil
		}
		if info.Size() > 1024*1024 { // skip files >1MB
			return nil
		}

		fileFindings, err := s.scanFile(fp)
		if err != nil {
			return nil // skip unreadable files
		}
		findings = append(findings, fileFindings...)
		return nil
	})

	return findings, err
}

func (s *SecretScanScanner) scanFile(path string) ([]Finding, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var findings []Finding
	scanner := bufio.NewScanner(f)
	lineNum := 0
	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		for _, p := range secretPatterns {
			if p.pattern.MatchString(line) {
				findings = append(findings, Finding{
					Scanner:  "secretscan",
					Severity: p.severity,
					Title:    fmt.Sprintf("Potential %s detected", p.name),
					Detail:   fmt.Sprintf("Line %d matches pattern for %s", lineNum, p.name),
					File:     path,
					Line:     lineNum,
					Rule:     p.name,
				})
			}
		}
	}
	return findings, scanner.Err()
}
