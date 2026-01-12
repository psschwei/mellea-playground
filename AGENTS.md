# Agent Instructions

## Repository

- **Host**: github.com
- **Repo**: psschwei/mellea-playground
- **Remote**: git@github.com:psschwei/mellea-playground.git

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds


<!-- bv-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View issues (launches TUI - avoid in automated sessions)
bv

# CLI commands for agents (use these instead)
bd ready              # Show issues ready to work (no blockers)
bd list --status=open # All open issues
bd show <id>          # Full issue details with dependencies
bd create --title="..." --type=task --priority=2
bd update <id> --status=in_progress
bd close <id> --reason="Completed"
bd close <id1> <id2>  # Close multiple issues at once
bd sync               # Commit and push changes
```

### Workflow Pattern

1. **Start**: Run `bd ready` to find actionable work
2. **Claim**: Use `bd update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `bd close <id>`
5. **Sync**: Always run `bd sync` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `bd ready` shows only unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers, not words)
- **Types**: task, bug, feature, epic, question, docs
- **Blocking**: `bd dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
bd sync                 # Commit beads changes
git commit -m "..."     # Commit code
bd sync                 # Commit any new beads changes
git push                # Push to remote
```

### Best Practices

- Check `bd ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `bd create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always `bd sync` before ending session

<!-- end-bv-agent-instructions -->

---

## Multi-Agent Collaboration

When multiple agents work on this repository simultaneously, follow these practices to avoid conflicts and ensure smooth collaboration.

### Use Git Worktrees (Required)

Each agent MUST use a dedicated git worktree for their work. This isolates changes and prevents file-level conflicts.

```bash
# Create a worktree for your task (from the main repo)
git worktree add ../mellea-<issue-id> -b <issue-id>

# Example: Working on beads-abc123
git worktree add ../mellea-beads-abc123 -b beads-abc123

# Navigate to your worktree
cd ../mellea-beads-abc123

# When done, clean up the worktree
git worktree remove ../mellea-<issue-id>
```

**Worktree Rules:**
- One worktree per issue/task
- Branch name should match the issue ID
- Always work in your worktree, not the main repo
- Remove worktrees after merging

### Branch Strategy

```bash
# Branch naming convention
<issue-id>           # e.g., beads-abc123
<type>/<description> # e.g., feature/add-auth, fix/login-bug

# Always create branches from latest main
git fetch origin
git checkout -b <branch> origin/main
```

### Collision Prevention

1. **Claim work before starting** - Use `bd update <id> --status=in_progress` so other agents know you're working on it
2. **Keep changes focused** - One issue per branch, minimal file changes
3. **Pull frequently** - Rebase onto main regularly to catch conflicts early
4. **Don't modify shared files unnecessarily** - If you must edit a shared file (e.g., config), coordinate via issues
5. **Small, atomic commits** - Easier to resolve conflicts and review

### Pull Request Workflow

For non-trivial changes, create a PR instead of pushing directly to main:

```bash
# Push your branch
git push -u origin <branch>

# Create PR (use gh CLI)
gh pr create --title "<issue-id>: Brief description" \
  --body "Closes #<issue-number-if-applicable>

## Summary
- What changed

## Test Plan
- How to verify"

# After approval, merge
gh pr merge --squash --delete-branch
```

**When to use PRs:**
- Any feature or significant change
- Changes affecting shared code or APIs
- When you want review before merging

**When direct push is OK:**
- Trivial fixes (typos, formatting)
- Documentation updates
- Issue tracking updates (bd sync)

### Quality Gates (Pre-Push Hooks)

This repo has **automatic pre-push hooks** that run CI checks before allowing a push. To enable them:

```bash
make setup-hooks   # One-time setup
```

The pre-push hook runs the same checks as CI:
- Backend: ruff lint, mypy type check, pytest
- Frontend: eslint, type-check

**If the hook blocks your push**, fix the issues and try again. To bypass (NOT recommended):
```bash
git push --no-verify
```

**Manual CI checks:**
```bash
make ci-check      # Run all CI checks
make lint          # Just linting
make test          # Just tests
```

**Rule: Never push code that breaks tests or fails linting.**

### Sync Protocol for Multiple Agents

```bash
# Before starting work
git fetch origin
git rebase origin/main  # or merge if you prefer

# During work (periodically)
git fetch origin
git rebase origin/main  # Resolve conflicts early

# Before pushing
git fetch origin
git rebase origin/main
# Run quality gates
git push

# If push is rejected (someone else pushed)
git fetch origin
git rebase origin/main
# Re-run quality gates
git push
```

### Communication via Issues

Use beads issues to coordinate:

```bash
# Signal that you're working on something
bd update <id> --status=in_progress

# Add comments to share context
bd comments <id> add "Starting work on the API endpoints"

# Create blocking issues for discovered dependencies
bd create --title="Need to refactor X first" --type=task
bd dep add <original-issue> <new-issue>

# Check what others are working on
bd list --status=in_progress
```

### Conflict Resolution

If you encounter merge conflicts:

1. **Don't panic** - Conflicts are normal in collaborative development
2. **Understand both changes** - Read what you changed vs what they changed
3. **Preserve intent** - Keep the functionality both changes intended
4. **Re-run tests** - After resolving, verify everything still works
5. **Ask for help** - If unsure, create an issue and ask

```bash
# After resolving conflicts
git add <resolved-files>
git rebase --continue  # or git merge --continue
make test              # Verify resolution didn't break anything
```

### Summary Checklist

**Starting work:**
- [ ] Check `bd ready` for available work
- [ ] Claim the issue with `bd update <id> --status=in_progress`
- [ ] Create a worktree: `git worktree add ../mellea-<issue-id> -b <issue-id>`
- [ ] Navigate to worktree and verify you're on the right branch

**During work:**
- [ ] Make small, focused commits
- [ ] Rebase onto main periodically
- [ ] Run tests before committing

**Finishing work:**
- [ ] Run all quality gates (test, lint, build)
- [ ] Create PR for significant changes (or push directly for trivial fixes)
- [ ] Close the issue: `bd close <id>`
- [ ] Sync beads: `bd sync`
- [ ] Remove worktree: `git worktree remove ../mellea-<issue-id>`
