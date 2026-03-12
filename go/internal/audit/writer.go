package audit

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// Writer is a mutex-protected append-only JSONL writer with rotation.
type Writer struct {
	mu        sync.Mutex
	dir       string
	maxBytes  int64
	maxFiles  int
	file      *os.File
	written   int64
}

// NewWriter creates a new audit log writer.
func NewWriter(dir string, maxBytes int64, maxFiles int) (*Writer, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create audit dir %s: %w", dir, err)
	}

	w := &Writer{
		dir:      dir,
		maxBytes: maxBytes,
		maxFiles: maxFiles,
	}

	if err := w.openCurrent(); err != nil {
		return nil, err
	}

	return w, nil
}

// Write appends an audit entry to the log file.
func (w *Writer) Write(entry AuditEntry) error {
	data, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("marshal audit entry: %w", err)
	}
	data = append(data, '\n')

	w.mu.Lock()
	defer w.mu.Unlock()

	// Check rotation
	if w.written+int64(len(data)) > w.maxBytes && w.maxBytes > 0 {
		if err := w.rotate(); err != nil {
			return fmt.Errorf("rotate audit log: %w", err)
		}
	}

	n, err := w.file.Write(data)
	if err != nil {
		return fmt.Errorf("write audit entry: %w", err)
	}
	w.written += int64(n)

	return nil
}

// Close closes the underlying file.
func (w *Writer) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.file != nil {
		return w.file.Close()
	}
	return nil
}

// Dir returns the audit directory path.
func (w *Writer) Dir() string {
	return w.dir
}

func (w *Writer) currentPath() string {
	return filepath.Join(w.dir, "audit.jsonl")
}

func (w *Writer) openCurrent() error {
	p := w.currentPath()
	f, err := os.OpenFile(p, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open audit file %s: %w", p, err)
	}
	info, err := f.Stat()
	if err != nil {
		f.Close()
		return fmt.Errorf("stat audit file: %w", err)
	}
	w.file = f
	w.written = info.Size()
	return nil
}

func (w *Writer) rotate() error {
	if w.file != nil {
		w.file.Close()
	}

	// Shift existing rotated files
	for i := w.maxFiles - 1; i >= 1; i-- {
		old := filepath.Join(w.dir, fmt.Sprintf("audit.%d.jsonl", i))
		next := filepath.Join(w.dir, fmt.Sprintf("audit.%d.jsonl", i+1))
		os.Rename(old, next) // ignore errors for missing files
	}

	// Move current to .1
	current := w.currentPath()
	first := filepath.Join(w.dir, "audit.1.jsonl")
	if err := os.Rename(current, first); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("rename current to .1: %w", err)
	}

	// Remove oldest if it exceeds maxFiles
	oldest := filepath.Join(w.dir, fmt.Sprintf("audit.%d.jsonl", w.maxFiles+1))
	os.Remove(oldest)

	return w.openCurrent()
}
