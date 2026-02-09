# Cursor Worktrees Guide

## Overview

Git worktrees allow you to work on multiple branches simultaneously, which is perfect for parallel feature development with the harness.

## Setup

### Create a Worktree

```powershell
# Create worktree for feature branch
git worktree add ../my-repo-feature feature/new-feature

# Or create in specific location
git worktree add C:\Projects\my-repo-feature feature/new-feature
```

### List Worktrees

```powershell
git worktree list
```

### Remove Worktree

```powershell
# Remove worktree (keeps branch)
git worktree remove ../my-repo-feature

# Remove worktree and branch
git worktree remove -b feature/new-feature
```

## Harness Integration

Each worktree has its own harness instance:

```
my-repo/
├── .git/
├── ai/              # Main harness
└── ...

my-repo-feature/
├── .git (worktree)
├── ai/              # Feature harness (separate context)
└── ...
```

## Best Practices

1. **Separate Context**: Each worktree maintains its own `ai/context/` and `ai/memory/`
2. **Shared Research**: Consider symlinking `ai/research/` for shared findings
3. **Lock Coordination**: Locks in `ai/_locks/` are per-worktree
4. **Parallel Development**: Use worktrees to implement multiple features simultaneously

## Cursor Integration

Cursor automatically detects worktrees. The harness hooks run independently in each worktree context.

## Example Workflow

```powershell
# Main branch
cd my-repo
# Work on main features

# Feature branch (parallel)
cd ../my-repo-feature
# Work on new feature
# Harness runs independently here
```
