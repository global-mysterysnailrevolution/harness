package audit

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Tail watches the audit log for new entries and sends them to the callback.
// It uses polling as a fallback. For production, fsnotify could be used.
func Tail(ctx context.Context, dir string, cb func(AuditEntry)) error {
	path := filepath.Join(dir, "audit.jsonl")

	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("open audit file for tail: %w", err)
	}
	defer f.Close()

	// Seek to end
	if _, err := f.Seek(0, 2); err != nil {
		return fmt.Errorf("seek to end: %w", err)
	}

	scanner := bufio.NewScanner(f)
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			for scanner.Scan() {
				var entry AuditEntry
				if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
					continue
				}
				cb(entry)
			}
		}
	}
}
