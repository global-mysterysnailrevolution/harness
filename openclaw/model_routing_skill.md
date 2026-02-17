# Model Routing Skill

This skill defines how you choose which model to use for each task. The goal is to minimize cost by routing cheap tasks to cheap models and only using expensive models when the task genuinely requires it.

## The Three Tiers

| Tier | Models | Cost | Use when |
|------|--------|------|----------|
| **Fast** | Gemini 3 Flash Preview, GPT 5 Mini | ~1/10th cost | Structured, routine, low-risk |
| **Standard** | ChatGPT 5.2 | Baseline | Reasoning, coding, multi-step |
| **Deep** | Claude Sonnet 4.5 | ~2x cost | Nuance, security, architecture |

## Decision Rubric

Before each task, ask these four questions:

### Q1: Is this structured/routine?

If YES -> **Fast tier**

Examples of structured/routine tasks:
- Formatting, reformatting, converting between formats
- Status checks ("is X running?", "what's the current state?")
- File reads, listing, summarizing known content
- Boilerplate generation (Dockerfiles, configs, package.json)
- Simple text transforms (rename, reword, translate)
- Log parsing and filtering
- Answering factual questions from provided context

### Q2: Does this need reasoning or code accuracy?

If YES -> **Standard tier**

Examples of reasoning/coding tasks:
- Writing new code (features, tools, scripts)
- Debugging errors
- Multi-step tool use (propose + validate + apply)
- Planning (breaking down a problem into steps)
- Comparing options with tradeoffs
- Interpreting ambiguous requirements

### Q3: Does this involve security, architecture, or high stakes?

If YES -> **Deep tier**

Examples of high-stakes tasks:
- Security analysis, audit, or hardening
- Architecture decisions (what to build, how to structure)
- Anything that could break production
- Reviewing code for subtle bugs
- Writing or modifying access control rules
- Evaluating risks and tradeoffs with significant consequences

### Q4: Does this need creative nuance or brand-sensitive output?

If YES -> **Deep tier**

Examples:
- Writing that represents the user publicly
- Explaining complex topics to non-technical people
- Anything where tone and phrasing matter significantly

## Fallback Rule

**Try Fast first. If it fails twice, escalate.**

If you're uncertain about the tier:
1. Start with Fast
2. If the output is wrong, incomplete, or low-quality, retry once
3. If it fails again, escalate to Standard
4. Never escalate past Standard unless Q3 or Q4 apply

This prevents premature escalation while keeping reliability.

## User Overrides

The user can explicitly request a tier:

| User says | Tier |
|-----------|------|
| "use mini", "cheap mode", "fast mode" | Fast |
| "use 5.2", "normal mode", "standard" | Standard |
| "use sonnet", "deep mode", "full power", "think hard" | Deep |

User overrides always take priority over the rubric.

## Red Flags (don't ignore these)

### Never use Fast for:
- Security analysis or access control changes
- Writing or modifying systemd units, sudoers, firewall rules
- Self-update proposals (always Standard or Deep)
- Anything involving secrets, keys, or credentials

### Never use Deep for:
- Simple status checks or file listings
- Formatting or boilerplate
- Tasks the user explicitly asked to be cheap

## How to Switch Models

When you decide the tier, switch by specifying the model in your response or subagent config:

- **Fast:** Use `Gemini 3 Flash Preview` or `GPT 5 Mini`
- **Standard:** Use `ChatGPT 5.2` (the default)
- **Deep:** Use `Claude Sonnet 4.5`

For subagents, set the model in the subagent spawn config.

## Cost Awareness

Rough cost ratios per 1M tokens:
- Fast: ~$0.10-0.30
- Standard: ~$2-5
- Deep: ~$5-15

A single task that uses Standard (~2000 tokens) costs what 10-20 Fast tasks cost. Route accordingly.

Over a day of mixed tasks (status checks, file reads, coding, planning), proper routing can reduce costs by 60-80% compared to running everything on Standard.

## Default Behavior

- **If no user instruction about model:** Use the rubric above.
- **If unsure:** Default to Standard (the safe middle ground).
- **For subagents doing research/discovery:** Always use Fast.
- **For subagents doing implementation:** Use Standard.
- **For the main orchestrator making decisions:** Use Standard or Deep based on stakes.
