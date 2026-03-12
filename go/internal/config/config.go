package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// Config holds all harness configuration.
type Config struct {
	ClaudeDir      string                `json:"-"`
	AuditDir       string                `json:"audit_dir"`
	AuditMaxBytes  int64                 `json:"audit_max_bytes"`
	AuditMaxFiles  int                   `json:"audit_max_files"`
	ActionPolicy   ActionPolicy          `json:"action_policy"`
	VettingPolicy  VettingPolicy         `json:"vetting_policy"`
	Allowlists     map[string]Allowlist  `json:"allowlists"`
	ScannerPaths   map[string]string     `json:"scanner_paths"`
	TokenEstimates map[string]TokenEst   `json:"token_estimates"`
	ModelCosts     map[string]CostRate   `json:"model_costs"`
}

// ActionPolicy holds rules for classifying tool actions.
type ActionPolicy struct {
	Rules []ActionRule `json:"rules"`
}

// ActionRule is a single classification rule.
type ActionRule struct {
	Pattern  string   `json:"pattern"`
	Class    string   `json:"class"`
	Keywords []string `json:"keywords"`
	Weight   float64  `json:"weight"`
}

// VettingPolicy controls the vetting pipeline.
type VettingPolicy struct {
	Scanners       []string       `json:"scanners"`
	FailThresholds map[string]int `json:"fail_thresholds"`
	BlockPatterns  []string       `json:"block_patterns"`
}

// Allowlist defines tool permissions for an agent role.
type Allowlist struct {
	Tools  []string `json:"tools"`
	Denied []string `json:"denied"`
	Reason string   `json:"reason"`
}

// TokenEst holds token estimation parameters.
type TokenEst struct {
	InputRate  float64 `json:"input_rate"`
	OutputRate float64 `json:"output_rate"`
}

// CostRate holds model cost rates per 1K tokens.
type CostRate struct {
	InputPer1K  float64 `json:"input_per_1k"`
	OutputPer1K float64 `json:"output_per_1k"`
}

// Load loads configuration from the merge chain:
// defaults -> ~/.claude/harness/config.json -> project/.claude/harness.json -> env -> flags
func Load(overridePath string) (*Config, error) {
	cfg := Defaults()

	// Resolve ClaudeDir
	home, err := os.UserHomeDir()
	if err != nil {
		home = "."
	}
	cfg.ClaudeDir = filepath.Join(home, ".claude")

	// Layer 2: Global user config
	globalPath := filepath.Join(cfg.ClaudeDir, "harness", "config.json")
	if err := mergeFromFile(cfg, globalPath); err != nil && !os.IsNotExist(err) {
		return nil, fmt.Errorf("load global config %s: %w", globalPath, err)
	}

	// Layer 3: Project config (cwd-based)
	cwd, _ := os.Getwd()
	projPath := filepath.Join(cwd, ".claude", "harness.json")
	if err := mergeFromFile(cfg, projPath); err != nil && !os.IsNotExist(err) {
		return nil, fmt.Errorf("load project config %s: %w", projPath, err)
	}

	// Layer 4: Override file from CLI flag
	if overridePath != "" {
		if err := mergeFromFile(cfg, overridePath); err != nil {
			return nil, fmt.Errorf("load override config %s: %w", overridePath, err)
		}
	}

	// Layer 5: Environment variables
	applyEnv(cfg)

	// Resolve paths
	cfg.AuditDir = expandPath(cfg.AuditDir, home)

	return cfg, nil
}

// Validate checks configuration for required fields and consistency.
func Validate(cfg *Config) error {
	if cfg.AuditDir == "" {
		return fmt.Errorf("audit_dir must not be empty")
	}
	if cfg.AuditMaxBytes <= 0 {
		return fmt.Errorf("audit_max_bytes must be positive")
	}
	if cfg.AuditMaxFiles <= 0 {
		return fmt.Errorf("audit_max_files must be positive")
	}
	return nil
}

func mergeFromFile(cfg *Config, path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, cfg)
}

func applyEnv(cfg *Config) {
	if v := os.Getenv("HARNESS_AUDIT_DIR"); v != "" {
		cfg.AuditDir = v
	}
	if v := os.Getenv("HARNESS_CLAUDE_DIR"); v != "" {
		cfg.ClaudeDir = v
	}
}

func expandPath(p string, home string) string {
	if strings.HasPrefix(p, "~/") || strings.HasPrefix(p, "~\\") {
		p = filepath.Join(home, p[2:])
	}
	if runtime.GOOS == "windows" {
		p = strings.ReplaceAll(p, "/", "\\")
	}
	return p
}
