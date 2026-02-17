# Context Pack Skill

This skill defines how you build, verify, and use structured context packs for projects and modules. Context packs are reusable artifacts that save tokens by pre-compiling the knowledge an agent needs to work effectively on a codebase.

## Why Context Packs

Without a context pack, every new session re-discovers the same things: file structure, stack, how to run tests, key decisions. This burns tokens and time. A context pack captures it once and reuses it many times.

**Cost impact:** A typical codebase scan costs 5,000-15,000 tokens. A context pack injection costs 500-1,500 tokens. Over 10 sessions, that's a 10x savings.

## When to Build a Context Pack

Build a context pack when:
- Starting work on a new project or module
- The user asks you to understand a codebase
- You notice you keep re-reading the same files across sessions
- No existing pack covers the scope you need

Do NOT build a pack for:
- A one-off question about a single file
- Tasks where the context is already in the conversation
- Trivially small scopes (single script, config file)

## The Verify Loop

Context packs follow a build-verify-patch loop:

```
draft -> verify -> patch gaps -> verify -> done
```

### Step 1: Build a draft

Use the builder to auto-generate a draft:

```bash
python3 /data/harness/scripts/compilers/build_context_pack.py --scope /path/to/project --name "project-name"
```

This auto-detects: stack, key files, run commands, external dependencies, README goal. It leaves placeholders for sections that need agent/human input.

### Step 2: Fill in placeholders

The builder leaves `_italic placeholder_` markers for sections it can't auto-detect. Fill these in by reading the codebase:

- **Architecture:** Read the main files and describe components
- **Interfaces:** List API endpoints, events, data models
- **Constraints:** Note security requirements, performance targets, tech limitations
- **Key Decisions:** Capture any design decisions you find (comments, docs, commit messages)
- **Open Questions:** List anything you're not sure about

### Step 3: Verify

Run the verifier:

```bash
python3 /data/harness/scripts/compilers/verify_context_pack.py context/project-name.md
```

The verifier checks:
- All required sections exist
- Enough concrete file paths (grounding)
- Enough concrete commands (how to run/test/build)
- No obvious contradictions
- Open questions listed for anything uncertain
- Tables aren't all empty

### Step 4: Patch and re-verify

Fix any issues the verifier reports. Re-run the verifier. Repeat until it passes.

For strict mode (higher thresholds):

```bash
python3 /data/harness/scripts/compilers/verify_context_pack.py context/project-name.md --strict
```

## Scope

Every pack declares its scope at the top:

```
> Scope: `/services/api` + `/packages/shared`
```

Types of scope:
- **Whole project:** `--scope /path/to/repo`
- **Module/folder:** `--scope /path/to/repo/src/auth --name "auth-module"`
- **Feature (cross-cutting):** Build manually by referencing files across directories

## Where to Store Packs

Store context packs relative to the project root:

```
project/
  context/
    project.md          # whole-project pack
    auth-module.md      # module-specific pack
    payments.md         # feature-specific pack
```

For the harness itself:

```
harness/
  context/
    harness.md
    igfetch.md
    self-update.md
```

## How to Use Packs

When starting work on a scope that has a context pack:

1. **Load the pack** -- read the context pack file first
2. **Check freshness** -- if the pack is old (check the Generated timestamp), rebuild it
3. **Start working** -- use the pack as your baseline knowledge; only read individual files when you need detail the pack doesn't cover

When another agent or subagent needs context for a scope:
- Inject the context pack into its prompt
- This is far cheaper than having the subagent re-scan the codebase

## Template

The context pack template is at:

```
/data/harness/scripts/compilers/context_pack_template.md
```

Required sections:
- Goal
- Non-Goals
- Current State
- Architecture
- Interfaces
- Constraints
- Key Decisions
- How to Run / Test / Build
- File Map
- External Dependencies
- Open Questions / Risks
- Next Actions

## Rules

1. **Always verify before calling a pack "done."** Unverified packs create false confidence.
2. **Always list open questions.** Unknown things should be explicit, not silently omitted.
3. **Keep packs under 3,000 tokens.** If it's longer, split into multiple scoped packs.
4. **Update packs when the project changes significantly.** Stale packs are worse than no packs.
5. **Don't duplicate the entire codebase.** Packs summarize structure and decisions, not code.
