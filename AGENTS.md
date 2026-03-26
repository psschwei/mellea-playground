# Agent Instructions

## Repository

- **Host**: github.com
- **Repo**: psschwei/mellea-playground
- **Remote**: git@github.com:psschwei/mellea-playground.git

## Python Commands

All Python commands should be run using **uv**. This ensures consistent dependency management and virtual environment handling.

```bash
# Examples
uv run pytest                    # Run tests
uv run python script.py          # Run a script
uv run mypy .                    # Type checking
uv run ruff check .              # Linting
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
4. **Clean up** - Clear stashes, prune remote branches
5. **Verify** - All changes committed AND pushed
6. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

---

## Multi-Agent Collaboration

When multiple agents work on this repository simultaneously, follow these practices to avoid conflicts and ensure smooth collaboration.

### Use Git Worktrees (Required)

Each agent MUST use a dedicated git worktree for their work. This isolates changes and prevents file-level conflicts.

```bash
# Create a worktree for your task (from the main repo)
git worktree add ../mellea-<issue-id> -b <issue-id>

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
<type>/<description> # e.g., feature/add-auth, fix/login-bug

# Always create branches from latest main
git fetch origin
git checkout -b <branch> origin/main
```

### Collision Prevention

1. **Keep changes focused** - One issue per branch, minimal file changes
2. **Pull frequently** - Rebase onto main regularly to catch conflicts early
3. **Don't modify shared files unnecessarily** - If you must edit a shared file (e.g., config), coordinate via issues
4. **Small, atomic commits** - Easier to resolve conflicts and review

### Pull Request Workflow

For non-trivial changes, create a PR instead of pushing directly to main:

```bash
# Push your branch
git push -u origin <branch>

# Create PR (use gh CLI)
gh pr create --title "Brief description" \
  --body "## Summary
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
git rebase origin/main

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
- [ ] Create a worktree: `git worktree add ../mellea-<issue-id> -b <issue-id>`
- [ ] Navigate to worktree and verify you're on the right branch

**During work:**
- [ ] Make small, focused commits
- [ ] Rebase onto main periodically
- [ ] Run tests before committing

**Finishing work:**
- [ ] Run all quality gates (test, lint, build)
- [ ] Create PR for significant changes (or push directly for trivial fixes)
- [ ] Remove worktree: `git worktree remove ../mellea-<issue-id>`
