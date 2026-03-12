package classify

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/global-mysterysnailrevolution/harness/internal/config"
)

// Classifier classifies tool actions by risk level.
type Classifier struct {
	policy     config.ActionPolicy
	allowlists map[string]config.Allowlist
	compiled   []compiledRule
}

type compiledRule struct {
	pattern  *regexp.Regexp
	class    ActionClass
	keywords []string
	weight   float64
}

// New creates a new action classifier.
func New(policy config.ActionPolicy, allowlists map[string]config.Allowlist) *Classifier {
	c := &Classifier{
		policy:     policy,
		allowlists: allowlists,
	}
	for _, r := range policy.Rules {
		re, err := regexp.Compile(r.Pattern)
		if err != nil {
			continue
		}
		c.compiled = append(c.compiled, compiledRule{
			pattern:  re,
			class:    ActionClass(r.Class),
			keywords: r.Keywords,
			weight:   r.Weight,
		})
	}
	return c
}

// Classify classifies a tool action and checks allowlists.
func (c *Classifier) Classify(tool string, args map[string]any, agentRole string) ClassifyResult {
	result := ClassifyResult{
		Tool:    tool,
		Allowed: true,
	}

	// Step 1: Match tool against rules (baseline classification)
	var baseScore float64
	var baseClass ActionClass
	var matchedKeywords []string

	for _, rule := range c.compiled {
		if rule.pattern.MatchString(tool) {
			baseClass = rule.class
			baseScore = rule.weight
			matchedKeywords = append(matchedKeywords, rule.keywords...)
			break
		}
	}

	bestClass := baseClass
	bestScore := baseScore

	// Step 2: Deep classify Bash commands — deep results override baseline
	if tool == "Bash" {
		cmdStr := extractCommand(args)
		deepClass, deepScore, deepKeywords := classifyBashCommand(cmdStr)
		matchedKeywords = append(matchedKeywords, deepKeywords...)
		// Deep classification always wins for Bash if it found a specific class
		if deepClass != ActionExec || deepScore > baseScore {
			bestClass = deepClass
			bestScore = deepScore
		}
	}

	// Step 3: Scan all args for credential patterns
	credScore, credKeywords := scanForCredentials(args)
	if credScore > 0 {
		matchedKeywords = append(matchedKeywords, credKeywords...)
		if credScore > bestScore || (bestClass != ActionDestructive) {
			bestClass = ActionCredential
			bestScore = credScore
		}
	}

	// Default class if no match
	if bestClass == "" {
		bestClass = ActionRead
		bestScore = 0.1
	}

	result.ActionClass = bestClass
	result.Score = bestScore
	result.Keywords = matchedKeywords

	// Step 4: Check allowlist
	if agentRole != "" {
		if al, ok := c.allowlists[agentRole]; ok {
			allowed := false
			for _, t := range al.Tools {
				if t == tool {
					allowed = true
					break
				}
			}
			for _, d := range al.Denied {
				if d == tool {
					allowed = false
					result.DenyReason = fmt.Sprintf("tool %s is denied for role %s: %s", tool, agentRole, al.Reason)
					break
				}
			}
			if len(al.Tools) > 0 && !allowed {
				if result.DenyReason == "" {
					result.DenyReason = fmt.Sprintf("tool %s not in allowlist for role %s", tool, agentRole)
				}
			}
			result.Allowed = allowed
		}
	}

	return result
}

func extractCommand(args map[string]any) string {
	if args == nil {
		return ""
	}
	if cmd, ok := args["command"]; ok {
		if s, ok := cmd.(string); ok {
			return s
		}
	}
	return ""
}

// destructiveKeywords maps substring keywords to their danger scores.
var destructiveKeywords = map[string]float64{
	"rm -rf":            0.9,
	"rm -r":             0.8,
	"rmdir":             0.5,
	"git reset --hard":  0.9,
	"git push --force":  0.9,
	"git push -f":       0.9,
	"git clean -f":      0.8,
	"git checkout -- .": 0.7,
	"drop table":        0.9,
	"drop database":     0.9,
	"truncate":          0.8,
	"format c:":         1.0,
	"mkfs":              1.0,
	"dd if=":            0.9,
	"chmod 777":         0.7,
	"chown root":        0.7,
	"> /dev/sda":        1.0,
	"shutdown":          0.8,
	"reboot":            0.7,
	"kill -9":           0.6,
	"pkill":             0.5,
	"npm publish":       0.6,
}

// destructiveRegexPatterns detect patterns that require regex (e.g., piped commands).
var destructiveRegexPatterns = []struct {
	name    string
	pattern *regexp.Regexp
	score   float64
}{
	{"pipe to bash", regexp.MustCompile(`(?i)(curl|wget)\s+.*\|\s*(ba)?sh`), 0.9},
	{"pipe to shell", regexp.MustCompile(`(?i)\|\s*(ba)?sh\b`), 0.85},
	{"pip install force", regexp.MustCompile(`(?i)pip\s+install\s+--force`), 0.5},
}

// credentialKeywords are patterns that suggest credential handling.
var credentialKeywords = map[string]float64{
	"password":    0.8,
	"passwd":      0.8,
	"secret":      0.7,
	"api_key":     0.8,
	"apikey":      0.8,
	"api-key":     0.8,
	"token":       0.6,
	"private_key": 0.9,
	"private-key": 0.9,
	"aws_secret":  0.9,
	"ssh-keygen":  0.7,
	"credentials": 0.7,
	".env":        0.6,
	"bearer":      0.6,
}

func classifyBashCommand(cmd string) (ActionClass, float64, []string) {
	lower := strings.ToLower(cmd)
	var maxScore float64
	var matched []string
	class := ActionExec

	// Check substring keywords
	for keyword, score := range destructiveKeywords {
		if strings.Contains(lower, keyword) {
			matched = append(matched, keyword)
			if score > maxScore {
				maxScore = score
				class = ActionDestructive
			}
		}
	}

	// Check regex patterns
	for _, rp := range destructiveRegexPatterns {
		if rp.pattern.MatchString(lower) {
			matched = append(matched, rp.name)
			if rp.score > maxScore {
				maxScore = rp.score
				class = ActionDestructive
			}
		}
	}

	if class == ActionDestructive {
		return class, maxScore, matched
	}

	// Check for network commands
	networkPatterns := []string{"curl", "wget", "ssh", "scp", "rsync", "nc ", "netcat", "nmap"}
	for _, p := range networkPatterns {
		if strings.Contains(lower, p) {
			matched = append(matched, p)
			class = ActionNetwork
			if 0.5 > maxScore {
				maxScore = 0.5
			}
		}
	}

	if class != ActionExec {
		return class, maxScore, matched
	}

	// Baseline exec score
	return ActionExec, 0.3, matched
}

func scanForCredentials(args map[string]any) (float64, []string) {
	if args == nil {
		return 0, nil
	}
	var maxScore float64
	var matched []string

	argsStr := fmt.Sprintf("%v", args)
	lower := strings.ToLower(argsStr)

	for keyword, score := range credentialKeywords {
		if strings.Contains(lower, keyword) {
			matched = append(matched, keyword)
			if score > maxScore {
				maxScore = score
			}
		}
	}

	return maxScore, matched
}
