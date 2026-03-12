package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var (
	cfgFile string
	verbose bool
	jsonOut bool
	quiet   bool
)

var rootCmd = &cobra.Command{
	Use:   "harness",
	Short: "Claude Code agent harness — runtime for security, routing, and orchestration",
	Long: `The Go harness binary replaces bash hooks, Node.js trace server, and prompt-encoded
runtime logic for the Claude Code agent harness. It operates as both a CLI and an MCP server.`,
	SilenceUsage:  true,
	SilenceErrors: true,
}

func Execute() error {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return err
	}
	return nil
}

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "Override config file path")
	rootCmd.PersistentFlags().BoolVar(&verbose, "verbose", false, "Verbose logging to stderr")
	rootCmd.PersistentFlags().BoolVar(&jsonOut, "json", false, "Force JSON output for all commands")
	rootCmd.PersistentFlags().BoolVar(&quiet, "quiet", false, "Suppress non-essential output")
}
