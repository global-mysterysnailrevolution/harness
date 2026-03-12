package exec

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"time"
)

// Result holds the output of a subprocess run.
type Result struct {
	ExitCode int    `json:"exit_code"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	Duration time.Duration `json:"duration"`
}

// Run executes a command with timeout and captures output.
func Run(ctx context.Context, name string, args ...string) (*Result, error) {
	cmd := exec.CommandContext(ctx, name, args...)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	start := time.Now()
	err := cmd.Run()
	duration := time.Since(start)

	result := &Result{
		Stdout:   stdout.String(),
		Stderr:   stderr.String(),
		Duration: duration,
	}

	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			result.ExitCode = exitErr.ExitCode()
		} else {
			return result, fmt.Errorf("run %s: %w", name, err)
		}
	}

	return result, nil
}

// RunWithTimeout executes a command with the given timeout.
func RunWithTimeout(timeout time.Duration, name string, args ...string) (*Result, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return Run(ctx, name, args...)
}
