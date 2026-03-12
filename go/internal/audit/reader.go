package audit

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

// Reader reads and queries audit log files.
type Reader struct {
	dir string
}

// NewReader creates a reader for the given audit directory.
func NewReader(dir string) *Reader {
	return &Reader{dir: dir}
}

// Query returns audit entries matching the given query.
func (r *Reader) Query(q AuditQuery) ([]AuditEntry, error) {
	files, err := r.listLogFiles()
	if err != nil {
		return nil, fmt.Errorf("list audit log files: %w", err)
	}

	var entries []AuditEntry
	limit := q.Limit
	if limit <= 0 {
		limit = 100
	}

	for _, f := range files {
		fileEntries, err := r.readFile(f)
		if err != nil {
			continue // skip unreadable files
		}
		for _, e := range fileEntries {
			if matchesQuery(e, q) {
				entries = append(entries, e)
				if len(entries) >= limit {
					return entries, nil
				}
			}
		}
	}

	return entries, nil
}

// ReadAll returns all audit entries from all log files.
func (r *Reader) ReadAll() ([]AuditEntry, error) {
	files, err := r.listLogFiles()
	if err != nil {
		return nil, fmt.Errorf("list audit log files: %w", err)
	}

	var entries []AuditEntry
	for _, f := range files {
		fileEntries, err := r.readFile(f)
		if err != nil {
			continue
		}
		entries = append(entries, fileEntries...)
	}
	return entries, nil
}

func (r *Reader) listLogFiles() ([]string, error) {
	pattern := filepath.Join(r.dir, "audit*.jsonl")
	files, err := filepath.Glob(pattern)
	if err != nil {
		return nil, err
	}
	// Sort: current first, then rotated in order
	sort.Strings(files)
	return files, nil
}

func (r *Reader) readFile(path string) ([]AuditEntry, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var entries []AuditEntry
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024) // 1MB max line
	for scanner.Scan() {
		var entry AuditEntry
		if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
			continue // skip malformed lines
		}
		entries = append(entries, entry)
	}
	return entries, scanner.Err()
}

func matchesQuery(e AuditEntry, q AuditQuery) bool {
	if q.SessionID != "" && e.SessionID != q.SessionID {
		return false
	}
	if q.Tool != "" && e.Tool != q.Tool {
		return false
	}
	if q.ActionClass != "" && e.ActionClass != q.ActionClass {
		return false
	}
	if q.AgentRole != "" && e.AgentRole != q.AgentRole {
		return false
	}
	if !q.Since.IsZero() && e.Timestamp.Before(q.Since) {
		return false
	}
	if !q.Until.IsZero() && e.Timestamp.After(q.Until) {
		return false
	}
	if q.HasError != nil && e.HasError != *q.HasError {
		return false
	}
	return true
}
