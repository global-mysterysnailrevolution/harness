package config

// Defaults returns the built-in default configuration.
func Defaults() *Config {
	return &Config{
		AuditDir:      "~/.claude/harness/audit",
		AuditMaxBytes: 10 * 1024 * 1024, // 10 MB
		AuditMaxFiles: 5,
		ActionPolicy: ActionPolicy{
			Rules: defaultActionRules(),
		},
		VettingPolicy: VettingPolicy{
			Scanners:       []string{"secretscan", "pathtraversal", "trivy", "gitleaks", "semgrep"},
			FailThresholds: map[string]int{"critical": 0, "high": 3, "medium": 10},
			BlockPatterns:  []string{},
		},
		Allowlists:     defaultAllowlists(),
		ScannerPaths:   map[string]string{},
		TokenEstimates: map[string]TokenEst{},
		ModelCosts:     map[string]CostRate{},
	}
}

func defaultActionRules() []ActionRule {
	return []ActionRule{
		{Pattern: "^Read$", Class: "read", Keywords: []string{"read", "file"}, Weight: 1.0},
		{Pattern: "^Glob$", Class: "read", Keywords: []string{"glob", "search", "find"}, Weight: 1.0},
		{Pattern: "^Grep$", Class: "read", Keywords: []string{"grep", "search", "pattern"}, Weight: 1.0},
		{Pattern: "^Write$", Class: "write", Keywords: []string{"write", "create", "overwrite"}, Weight: 1.0},
		{Pattern: "^Edit$", Class: "write", Keywords: []string{"edit", "replace", "modify"}, Weight: 1.0},
		{Pattern: "^Bash$", Class: "exec", Keywords: []string{"exec", "command", "shell", "bash"}, Weight: 1.5},
		{Pattern: "^WebFetch$", Class: "network", Keywords: []string{"fetch", "url", "http", "web"}, Weight: 1.0},
	}
}

func defaultAllowlists() map[string]Allowlist {
	return map[string]Allowlist{
		"researcher": {
			Tools:  []string{"Read", "Glob", "Grep", "WebFetch"},
			Denied: []string{"Write", "Edit", "Bash"},
			Reason: "Research agents are read-only",
		},
		"implementer": {
			Tools:  []string{"Read", "Glob", "Grep", "Write", "Edit", "Bash"},
			Denied: []string{},
			Reason: "Implementer agents have read-write access",
		},
		"tester": {
			Tools:  []string{"Read", "Glob", "Grep", "Bash"},
			Denied: []string{"Write", "Edit"},
			Reason: "Tester agents can read and execute",
		},
		"scanner": {
			Tools:  []string{"Read", "Glob", "Grep"},
			Denied: []string{"Write", "Edit", "Bash"},
			Reason: "Scanner agents are read-only",
		},
		"orchestrator": {
			Tools:  []string{"Read", "Glob", "Grep", "Write", "Edit", "Bash", "WebFetch"},
			Denied: []string{},
			Reason: "Orchestrator has full access",
		},
	}
}
