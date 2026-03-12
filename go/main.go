package main

import (
	"os"

	"github.com/global-mysterysnailrevolution/harness/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
