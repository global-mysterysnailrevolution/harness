package cmd

import (
	"fmt"
	"os/exec"

	"github.com/spf13/cobra"
)

var dashboardOpenPort int

var dashboardCmd = &cobra.Command{
	Use:   "dashboard",
	Short: "Open the agent dashboard in your browser",
	Long:  "Opens the harness agent dashboard in your default web browser.",
	RunE: func(cmd *cobra.Command, args []string) error {
		url := fmt.Sprintf("http://localhost:%d", dashboardOpenPort)
		fmt.Fprintf(cmd.ErrOrStderr(), "Opening %s ...\n", url)
		return exec.Command("cmd", "/c", "start", url).Run()
	},
}

func init() {
	dashboardCmd.Flags().IntVar(&dashboardOpenPort, "port", 3210, "Dashboard port to open")
	rootCmd.AddCommand(dashboardCmd)
}
