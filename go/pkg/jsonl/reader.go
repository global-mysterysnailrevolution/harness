package jsonl

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
)

// ReadFile reads all JSONL entries from a file into a slice of the given type.
func ReadFile[T any](path string) ([]T, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	defer f.Close()
	return Read[T](f)
}

// Read reads all JSONL entries from a reader.
func Read[T any](r io.Reader) ([]T, error) {
	var results []T
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var v T
		if err := json.Unmarshal(line, &v); err != nil {
			continue // skip malformed lines
		}
		results = append(results, v)
	}
	if err := scanner.Err(); err != nil {
		return results, fmt.Errorf("scan: %w", err)
	}
	return results, nil
}
