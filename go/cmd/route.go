package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/global-mysterysnailrevolution/harness/internal/discover"
	"github.com/global-mysterysnailrevolution/harness/internal/route"
	"github.com/spf13/cobra"
)

var routeFormat string

var routeCmd = &cobra.Command{
	Use:   "route <task-description>",
	Short: "Route a task to the best matching skills and tools",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		registry := discover.NewRegistry(cfg.ClaudeDir)
		router := route.NewRouter(registry)
		result := router.Route(args[0])

		if jsonOut || routeFormat == "json" {
			data, _ := json.MarshalIndent(result, "", "  ")
			fmt.Println(string(data))
		} else {
			fmt.Println("=== Route Results ===")
			if len(result.Skills) > 0 {
				fmt.Println("Skills:")
				for _, m := range result.Skills {
					fmt.Printf("  %.2f %s — %s\n", m.Score, m.Name, m.Reason)
				}
			}
			if len(result.Tools) > 0 {
				fmt.Println("Tools:")
				for _, m := range result.Tools {
					fmt.Printf("  %.2f %s — %s\n", m.Score, m.Name, m.Reason)
				}
			}
			if len(result.Commands) > 0 {
				fmt.Println("Commands:")
				for _, m := range result.Commands {
					fmt.Printf("  %.2f %s — %s\n", m.Score, m.Name, m.Reason)
				}
			}
		}
		return nil
	},
}

func init() {
	routeCmd.Flags().StringVar(&routeFormat, "format", "text", "Output format: json, text")
	rootCmd.AddCommand(routeCmd)
}
