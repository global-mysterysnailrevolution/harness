package cmd

import (
	"fmt"
	"net/http"
	"path/filepath"

	"github.com/global-mysterysnailrevolution/harness/internal/agents"
	"github.com/global-mysterysnailrevolution/harness/internal/dashboard"
	"github.com/spf13/cobra"
)

var dashboardPort int

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

		// Initialize agent tracker
		stateDir := filepath.Join(cfg.ClaudeDir, "harness")
		tracker, err := agents.NewTracker(stateDir)
		if err != nil {
			return fmt.Errorf("init agent tracker: %w", err)
		}
		srv.SetTracker(tracker)

		// Start dashboard HTTP server if enabled
		if dashboardPort > 0 {
			go func() {
				addr := fmt.Sprintf(":%d", dashboardPort)
				fmt.Fprintf(cmd.ErrOrStderr(), "Dashboard at http://localhost%s\n", addr)
				if err := http.ListenAndServe(addr, dashboard.Handler(tracker)); err != nil {
					fmt.Fprintf(cmd.ErrOrStderr(), "Dashboard server error: %v\n", err)
				}
			}()
		}

		return srv.Run(cmd.Context())
	},
}

func init() {
	serveCmd.Flags().IntVar(&dashboardPort, "dashboard", 3210, "Dashboard HTTP port (0 to disable)")
	rootCmd.AddCommand(serveCmd)
}
