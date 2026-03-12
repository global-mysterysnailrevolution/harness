package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/global-mysterysnailrevolution/harness/internal/vet"
	"github.com/spf13/cobra"
)

var vetScanners string
var vetFormat string

var vetCmd = &cobra.Command{
	Use:   "vet <path>",
	Short: "Run security vetting pipeline on a file or directory",
	Long:  "Orchestrates trivy, gitleaks, semgrep, and built-in scanners to produce a security report.",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		pipeline := vet.NewPipeline(cfg.VettingPolicy, cfg.ScannerPaths)

		var scannerList []string
		if vetScanners != "" {
			for _, s := range splitComma(vetScanners) {
				scannerList = append(scannerList, s)
			}
		}

		report, err := pipeline.Run(cmd.Context(), args[0], scannerList)
		if err != nil {
			return fmt.Errorf("vet scan: %w", err)
		}

		if jsonOut || vetFormat == "json" {
			data, _ := json.MarshalIndent(report, "", "  ")
			fmt.Println(string(data))
		} else {
			fmt.Printf("Vet Report: %s\n", report.Path)
			fmt.Printf("Scanners run: %v\n", report.Scanners)
			if len(report.Unavailable) > 0 {
				fmt.Printf("Unavailable: %v\n", report.Unavailable)
			}
			fmt.Printf("Findings: critical=%d high=%d medium=%d low=%d info=%d\n",
				report.Summary.Critical, report.Summary.High, report.Summary.Medium,
				report.Summary.Low, report.Summary.Info)
			fmt.Printf("Policy passed: %v\n", report.PassedPolicy)
			for _, f := range report.Findings {
				fmt.Printf("  [%s] %s: %s\n", f.Severity, f.Scanner, f.Title)
			}
		}
		return nil
	},
}

func init() {
	vetCmd.Flags().StringVar(&vetScanners, "scanners", "", "Comma-separated scanner names (default: all available)")
	vetCmd.Flags().StringVar(&vetFormat, "format", "text", "Output format: json, text, md")
	rootCmd.AddCommand(vetCmd)
}

func splitComma(s string) []string {
	var result []string
	current := ""
	for _, c := range s {
		if c == ',' {
			if current != "" {
				result = append(result, current)
			}
			current = ""
		} else {
			current += string(c)
		}
	}
	if current != "" {
		result = append(result, current)
	}
	return result
}
