package route

import (
	"sort"
	"strings"

	"github.com/global-mysterysnailrevolution/harness/internal/discover"
)

// Router matches tasks to capabilities.
type Router struct {
	registry *discover.Registry
}

// NewRouter creates a new task router.
func NewRouter(registry *discover.Registry) *Router {
	return &Router{registry: registry}
}

// Route matches a task description to capabilities.
func (r *Router) Route(task string) RouteResult {
	caps := r.registry.All()
	taskLower := strings.ToLower(task)
	words := strings.Fields(taskLower)

	var skills, tools, commands []MatchScore

	for _, cap := range caps {
		score := r.score(cap, taskLower, words)
		if score <= 0 {
			continue
		}
		ms := MatchScore{
			Name:      cap.Name,
			Score:     score,
			InvokeVia: cap.InvokeVia,
			Reason:    "keyword match",
		}

		switch cap.Kind {
		case "skill":
			skills = append(skills, ms)
		case "builtin":
			tools = append(tools, ms)
		case "command":
			commands = append(commands, ms)
		default:
			tools = append(tools, ms)
		}
	}

	sortMatches(skills)
	sortMatches(tools)
	sortMatches(commands)

	return RouteResult{
		Skills:   truncate(skills, 5),
		Tools:    truncate(tools, 5),
		Commands: truncate(commands, 5),
	}
}

func (r *Router) score(cap discover.Capability, taskLower string, words []string) float64 {
	var score float64

	nameLower := strings.ToLower(cap.Name)
	descLower := strings.ToLower(cap.Description)
	trigLower := strings.ToLower(cap.Triggers)

	// Name match
	if strings.Contains(taskLower, nameLower) {
		score += 2.0
	}

	// Trigger match
	if trigLower != "" {
		triggers := strings.Split(trigLower, ",")
		for _, t := range triggers {
			t = strings.TrimSpace(t)
			if t != "" && strings.Contains(taskLower, t) {
				score += 3.0
			}
		}
	}

	// Word overlap with description
	for _, w := range words {
		if len(w) < 3 {
			continue
		}
		if strings.Contains(descLower, w) {
			score += 0.5
		}
		if strings.Contains(nameLower, w) {
			score += 1.0
		}
	}

	return score
}

func sortMatches(ms []MatchScore) {
	sort.Slice(ms, func(i, j int) bool {
		return ms[i].Score > ms[j].Score
	})
}

func truncate(ms []MatchScore, max int) []MatchScore {
	if len(ms) > max {
		return ms[:max]
	}
	return ms
}
