package jsonl

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
)

// WriteFile appends a value as a JSON line to the given file.
func WriteFile(path string, v any) error {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open %s: %w", path, err)
	}
	defer f.Close()
	return Write(f, v)
}

// Write writes a value as a JSON line to the writer.
func Write(w io.Writer, v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	data = append(data, '\n')
	_, err = w.Write(data)
	return err
}
