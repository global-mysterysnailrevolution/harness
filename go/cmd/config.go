package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/global-mysterysnailrevolution/harness/internal/config"
	"github.com/spf13/cobra"
)

var configCmd = &cobra.Command{
	Use:   "config [get|set|validate|init]",
	Short: "Manage harness configuration",
	Long:  "Read, write, or validate harness configuration files.",
}

var configGetCmd = &cobra.Command{
	Use:   "get <key>",
	Short: "Get a configuration value",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}
		data, _ := json.MarshalIndent(cfg, "", "  ")
		// Simple key lookup from JSON
		var m map[string]any
		if err := json.Unmarshal(data, &m); err != nil {
			return err
		}
		val, ok := m[args[0]]
		if !ok {
			return fmt.Errorf("key %q not found", args[0])
		}
		out, _ := json.MarshalIndent(val, "", "  ")
		fmt.Println(string(out))
		return nil
	},
}

var configValidateCmd = &cobra.Command{
	Use:   "validate",
	Short: "Validate current configuration",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("config invalid: %w", err)
		}
		if err := config.Validate(cfg); err != nil {
			return fmt.Errorf("config validation failed: %w", err)
		}
		fmt.Println("Configuration is valid.")
		return nil
	},
}

var configInitCmd = &cobra.Command{
	Use:   "init",
	Short: "Create default configuration file",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg := config.Defaults()
		data, _ := json.MarshalIndent(cfg, "", "  ")
		fmt.Println(string(data))
		return nil
	},
}

func init() {
	configCmd.AddCommand(configGetCmd)
	configCmd.AddCommand(configValidateCmd)
	configCmd.AddCommand(configInitCmd)
	rootCmd.AddCommand(configCmd)
}
