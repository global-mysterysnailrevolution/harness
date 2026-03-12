package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Start the harness MCP server (stdio transport)",
	Long:  "Starts an MCP server on stdio. Claude Code connects to this as a subprocess.",
	RunE: func(cmd *cobra.Command, args []string) error {
		fmt.Fprintln(cmd.ErrOrStderr(), "MCP server starting on stdio transport...")

		cfg, err := loadConfig()
		if err != nil {
			return fmt.Errorf("load config: %w", err)
		}

		srv, err := newMCPServer(cfg)
		if err != nil {
			return fmt.Errorf("init MCP server: %w", err)
		}

		return srv.Run(cmd.Context())
	},
}

func init() {
	rootCmd.AddCommand(serveCmd)
}
