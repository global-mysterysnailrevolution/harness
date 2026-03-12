package cmd

import (
	"github.com/global-mysterysnailrevolution/harness/internal/config"
	intmcp "github.com/global-mysterysnailrevolution/harness/internal/mcp"
)

func loadConfig() (*config.Config, error) {
	return config.Load(cfgFile)
}

func newMCPServer(cfg *config.Config) (*intmcp.Server, error) {
	return intmcp.NewServer(cfg)
}
