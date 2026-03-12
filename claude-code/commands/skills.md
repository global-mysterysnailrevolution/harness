---
name: skills
description: >
  List, search, and manage installed skills. Shows what skills are available,
  their trigger conditions, and context cost. Use: /skills [search-term]
---

# Skill Manager: /skills

## If $ARGUMENTS is empty: List All Skills

Scan all installed skill locations and present a summary table:

1. Glob for `~/.claude/plugins/**/SKILL.md`
2. For each SKILL.md, read ONLY the frontmatter (name + description) — stop at the closing `---`
3. Present as a compact table:

```
| Skill | Trigger | Source |
|-------|---------|--------|
| skill-creator | "create a skill", "improve skill" | plugin: skill-creator |
| frontend-design | "design", "UI", "component" | plugin: frontend-design |
| ... | ... | ... |
```

4. Show total count and estimated context cost if ALL were loaded vs. selective loading

## If $ARGUMENTS has a search term: Find Matching Skills

1. Search skill descriptions for the term
2. Show matching skills with relevance ranking
3. Suggest which skill to use for the user's task

## Skill Context Budget

Skills use progressive disclosure to minimize context cost:

| Layer | When Loaded | Token Cost |
|-------|-------------|-----------|
| Metadata (name + description) | Always registered | ~50 tokens/skill |
| SKILL.md instructions | On trigger match | ~500-2000 tokens |
| References/assets | On explicit need | Varies |

**Current budget**: ~[N] skills registered × ~50 tokens = ~[total] tokens baseline.
Full load of all skills would cost ~[estimate] tokens.

## Creating New Skills

Use `/skill-creator` to create a new skill with the full eval pipeline, or
create a quick skill manually:

```
~/.claude/commands/my-skill.md   ← global command (available everywhere)
.claude/commands/my-skill.md     ← project command (project-specific)
```

Minimal format:
```markdown
---
name: my-skill
description: When to trigger this skill
---
# Instructions for Claude when this skill is active
```
