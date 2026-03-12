package cmd

import (
	"encoding/json"
	"fmt"

	"github.com/spf13/cobra"
)

var (
	// Set via ldflags at build time
	Version   = "dev"
	Commit    = "unknown"
	BuildDate = "unknown"
)

var shortVersion bool

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print harness version information",
	RunE: func(cmd *cobra.Command, args []string) error {
		if shortVersion {
			fmt.Println(Version)
			return nil
		}
		if jsonOut {
			data, _ := json.MarshalIndent(map[string]string{
				"version":    Version,
				"commit":     Commit,
				"build_date": BuildDate,
			}, "", "  ")
			fmt.Println(string(data))
			return nil
		}
		fmt.Printf("harness %s (commit: %s, built: %s)\n", Version, Commit, BuildDate)
		return nil
	},
}

func init() {
	versionCmd.Flags().BoolVar(&shortVersion, "short", false, "Print version number only")
	rootCmd.AddCommand(versionCmd)
}
