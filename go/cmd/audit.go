package cmd

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/global-mysterysnailrevolution/harness/internal/audit"
	"github.com/spf13/cobra"
)

var (
	auditSID    string
	auditTool   string
	auditClass  string
	auditRole   string
	auditSince  string
	auditUntil  string
	auditErrors bool
	auditLimit  int
	auditTail   bool
	auditFormat string
)

var auditCmd = &cobra.Command{
	Use:   "audit",
	Short: "Query and manage the audit log",
	Long:  "Query, filter, and tail the JSONL audit log of all harness operations.",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		query := audit.AuditQuery{
			SessionID:   auditSID,
			Tool:        auditTool,
			ActionClass: auditClass,
			AgentRole:   auditRole,
			Limit:       auditLimit,
		}

		if auditSince != "" {
			t, err := parseTimeOrDuration(auditSince)
			if err != nil {
				return fmt.Errorf("parse --since: %w", err)
			}
			query.Since = t
		}
		if auditUntil != "" {
			t, err := parseTimeOrDuration(auditUntil)
			if err != nil {
				return fmt.Errorf("parse --until: %w", err)
			}
			query.Until = t
		}
		if auditErrors {
			b := true
			query.HasError = &b
		}

		reader := audit.NewReader(cfg.AuditDir)
		entries, err := reader.Query(query)
		if err != nil {
			return fmt.Errorf("query audit log: %w", err)
		}

		if jsonOut || auditFormat == "json" {
			data, _ := json.MarshalIndent(entries, "", "  ")
			fmt.Println(string(data))
		} else {
			for _, e := range entries {
				fmt.Printf("[%s] %s tool=%s class=%s allowed=%v\n",
					e.Timestamp.Format(time.RFC3339), e.Phase, e.Tool, e.ActionClass, e.Allowed)
			}
		}
		return nil
	},
}

func init() {
	auditCmd.Flags().StringVar(&auditSID, "sid", "", "Filter by session ID")
	auditCmd.Flags().StringVar(&auditTool, "tool", "", "Filter by tool name")
	auditCmd.Flags().StringVar(&auditClass, "class", "", "Filter by action class")
	auditCmd.Flags().StringVar(&auditRole, "role", "", "Filter by agent role")
	auditCmd.Flags().StringVar(&auditSince, "since", "", "Start time (ISO 8601 or duration like 1h)")
	auditCmd.Flags().StringVar(&auditUntil, "until", "", "End time (ISO 8601)")
	auditCmd.Flags().BoolVar(&auditErrors, "errors", false, "Only show entries with errors")
	auditCmd.Flags().IntVar(&auditLimit, "limit", 100, "Max entries to return")
	auditCmd.Flags().BoolVar(&auditTail, "tail", false, "Real-time tail mode")
	auditCmd.Flags().StringVar(&auditFormat, "format", "text", "Output format: json, text, table")
	rootCmd.AddCommand(auditCmd)
}

func parseTimeOrDuration(s string) (time.Time, error) {
	// Try ISO 8601 first
	t, err := time.Parse(time.RFC3339, s)
	if err == nil {
		return t, nil
	}
	// Try duration (e.g., "1h", "30m")
	d, err := time.ParseDuration(s)
	if err == nil {
		return time.Now().Add(-d), nil
	}
	return time.Time{}, fmt.Errorf("cannot parse %q as time or duration", s)
}
