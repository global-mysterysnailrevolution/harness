package route

// RouteResult holds routing results.
type RouteResult struct {
	Skills   []MatchScore `json:"skills"`
	Tools    []MatchScore `json:"tools"`
	Commands []MatchScore `json:"commands"`
}

// MatchScore represents a scored match.
type MatchScore struct {
	Name      string  `json:"name"`
	Score     float64 `json:"score"`
	InvokeVia string  `json:"invoke_via"`
	Reason    string  `json:"reason"`
}
