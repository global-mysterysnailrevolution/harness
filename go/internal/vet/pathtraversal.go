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

// PathTraversalScanner detects path traversal patterns.
type PathTraversalScanner struct{}

// NewPathTraversalScanner creates a new path traversal scanner.
func NewPathTraversalScanner() *PathTraversalScanner {
	return &PathTraversalScanner{}
}

func (s *PathTraversalScanner) Name() string   { return "pathtraversal" }
func (s *PathTraversalScanner) Available() bool { return true }

type traversalPattern struct {
	name    string
	pattern *regexp.Regexp
}

var traversalPatterns = []traversalPattern{
	{
		name:    "dot-dot-slash traversal",
		pattern: regexp.MustCompile(`\.\.[/\\]`),
	},
	{
		name:    "URL-encoded traversal",
		pattern: regexp.MustCompile(`(?i)(%2e%2e|%252e%252e|\.%2e|%2e\.)[/\\%]`),
	},
	{
		name:    "null byte injection",
		pattern: regexp.MustCompile(`%00`),
	},
	{
		name:    "direct /etc/passwd access",
		pattern: regexp.MustCompile(`/etc/(passwd|shadow|hosts)`),
	},
	{
		name:    "Windows system path access",
		pattern: regexp.MustCompile(`(?i)(c:\\windows|c:\\system32|%systemroot%)`),
	},
}

func (s *PathTraversalScanner) Scan(ctx context.Context, path string) ([]Finding, error) {
	var findings []Finding

	err := filepath.Walk(path, func(fp string, info os.FileInfo, err error) error {
		if err != nil || info == nil {
			return nil
		}
		if info.IsDir() {
			base := filepath.Base(fp)
			if base == ".git" || base == "node_modules" || base == "vendor" {
				return filepath.SkipDir
			}
			return nil
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		ext := strings.ToLower(filepath.Ext(fp))
		if skipExtensions[ext] {
			return nil
		}
		if info.Size() > 1024*1024 {
			return nil
		}

		fileFindings, scanErr := s.scanFile(fp)
		if scanErr != nil {
			return nil
		}
		findings = append(findings, fileFindings...)
		return nil
	})

	return findings, err
}

func (s *PathTraversalScanner) scanFile(path string) ([]Finding, error) {
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
		for _, p := range traversalPatterns {
			if p.pattern.MatchString(line) {
				findings = append(findings, Finding{
					Scanner:  "pathtraversal",
					Severity: SevMedium,
					Title:    fmt.Sprintf("Potential %s", p.name),
					Detail:   fmt.Sprintf("Line %d matches path traversal pattern", lineNum),
					File:     path,
					Line:     lineNum,
					Rule:     p.name,
				})
			}
		}
	}
	return findings, scanner.Err()
}
