package dashboard

import (
	"embed"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/global-mysterysnailrevolution/harness/internal/agents"
)

//go:embed index.html
var content embed.FS

// Handler returns an http.Handler that serves the dashboard and its API.
func Handler(tracker *agents.Tracker) http.Handler {
	mux := http.NewServeMux()

	// Serve embedded HTML at root
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		data, err := content.ReadFile("index.html")
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(data)
	})

	// JSON API: list agents
	mux.HandleFunc("/api/agents", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		list := tracker.List()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(list)
	})

	// JSON API: cancel agent
	// Matches /api/agents/{id}/cancel
	mux.HandleFunc("/api/agents/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/api/agents/")
		if !strings.HasSuffix(path, "/cancel") {
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		id := strings.TrimSuffix(path, "/cancel")
		if id == "" {
			http.Error(w, "missing agent id", http.StatusBadRequest)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		if err := tracker.Cancel(id); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}
		json.NewEncoder(w).Encode(map[string]string{"status": "cancelled", "id": id})
	})

	// SSE: stream agent events
	mux.HandleFunc("/events", func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming not supported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		flusher.Flush()

		ch, unsub := tracker.Subscribe()
		defer unsub()

		for {
			select {
			case ev, ok := <-ch:
				if !ok {
					return
				}
				data, err := json.Marshal(ev)
				if err != nil {
					continue
				}
				fmt.Fprintf(w, "data: %s\n\n", data)
				flusher.Flush()
			case <-r.Context().Done():
				return
			}
		}
	})

	return mux
}
