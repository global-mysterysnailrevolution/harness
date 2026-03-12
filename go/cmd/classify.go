package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/global-mysterysnailrevolution/harness/internal/classify"
	"github.com/spf13/cobra"
)

var classifyRole string
var classifyFormat string

var classifyCmd = &cobra.Command{
	Use:   "classify <tool> [args-json]",
	Short: "Classify a tool action by risk level",
	Long:  "Classifies a tool action and returns action class, risk score, and allowlist status.",
	Args:  cobra.RangeArgs(1, 2),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		tool := args[0]
		var toolArgs map[string]any
		if len(args) > 1 {
			if err := json.Unmarshal([]byte(args[1]), &toolArgs); err != nil {
				return fmt.Errorf("parse args JSON: %w", err)
			}
		}

		classifier := classify.New(cfg.ActionPolicy, cfg.Allowlists)
		result := classifier.Classify(tool, toolArgs, classifyRole)

		if jsonOut || classifyFormat == "json" {
			data, _ := json.MarshalIndent(result, "", "  ")
			fmt.Println(string(data))
		} else {
			fmt.Printf("Tool:     %s\n", result.Tool)
			fmt.Printf("Class:    %s\n", result.ActionClass)
			fmt.Printf("Score:    %.2f\n", result.Score)
			fmt.Printf("Allowed:  %v\n", result.Allowed)
			if result.DenyReason != "" {
				fmt.Printf("Denied:   %s\n", result.DenyReason)
			}
			if len(result.Keywords) > 0 {
				fmt.Printf("Keywords: %v\n", result.Keywords)
			}
		}
		return nil
	},
}

func init() {
	classifyCmd.Flags().StringVar(&classifyRole, "role", "", "Agent role for allowlist check")
	classifyCmd.Flags().StringVar(&classifyFormat, "format", "text", "Output format: json, text")
	rootCmd.AddCommand(classifyCmd)
}
