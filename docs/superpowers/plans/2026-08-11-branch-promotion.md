# Branch Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish `dev` as the integration branch, preserve `main` as the production branch, and bring the existing MVP implementation into `dev` through a reviewed pull request.

**Architecture:** Create `dev` from the current `origin/main` commit so GitHub records a clean initial integration PR from `implementation/mvp`. Future feature and fix branches start from `dev`; validated releases move from `dev` to `main` through a protected promotion PR.

**Tech Stack:** Git, GitHub CLI, GitHub pull requests, GitHub Actions

## Global Constraints

- Never commit Terraform plan files, Terraform state, API keys, credentials, or generated secret material.
- Do not rewrite or force-push shared history.
- `main` is the production branch; `dev` is the integration branch.
- Application changes enter `dev` through pull requests and required checks.
- Production promotion uses the exact immutable image digests validated in dev.

---

### Task 1: Create the remote integration branch

**Files:**
- No repository files modified.

**Interfaces:**
- Consumes: `origin/main` at commit `a85f19163db5f6a3d606c47bca6baf5f3ef410bb` or its verified descendant.
- Produces: remote branch `origin/dev` pointing to the verified `origin/main` commit.

- [ ] **Step 1: Verify sensitive generated files are not tracked**

Run:

```bash
git status --short
git ls-files 'infra/terraform/**/*.tfplan'
```

Expected: the two recovery plans may appear only as untracked files; `git ls-files` returns no plan files.

- [ ] **Step 2: Create and push `dev` without changing the active worktree**

Run:

```bash
git fetch origin --prune
git branch dev origin/main
git push --set-upstream origin dev
```

Expected: GitHub contains `dev` at the same commit as `origin/main`.

- [ ] **Step 3: Verify remote branch ancestry**

Run:

```bash
test "$(git rev-parse origin/dev)" = "$(git rev-parse origin/main)"
git merge-base --is-ancestor origin/dev implementation/mvp
```

Expected: both commands exit zero.

### Task 2: Open the initial implementation pull request

**Files:**
- No repository files modified.

**Interfaces:**
- Consumes: `origin/dev`, `origin/implementation/mvp`.
- Produces: GitHub pull request with base `dev` and head `implementation/mvp`.

- [ ] **Step 1: Run the complete local verification suite**

Run:

```bash
.venv/bin/pytest -q
git diff --check origin/dev...implementation/mvp
```

Expected: pytest exits zero and Git reports no whitespace errors.

- [ ] **Step 2: Create the pull request**

Run:

```bash
gh pr create \
  --base dev \
  --head implementation/mvp \
  --title "feat: integrate workforce risk MVP" \
  --body "Promotes the reviewed MVP implementation into the dev integration branch. Sensitive Terraform plans and credentials are excluded."
```

Expected: GitHub returns a pull-request URL whose base is `dev`.

- [ ] **Step 3: Inspect required checks**

Run:

```bash
gh pr checks --watch
```

Expected: all configured required checks pass. Any failure blocks merging and is corrected on `implementation/mvp` before retrying.

### Task 3: Merge and verify the integration branch

**Files:**
- No repository files modified.

**Interfaces:**
- Consumes: approved, green implementation pull request.
- Produces: updated `origin/dev` containing the complete MVP history.

- [ ] **Step 1: Merge without deleting the implementation branch**

Run:

```bash
gh pr merge --merge
```

Expected: GitHub reports the pull request merged into `dev`; the source branch remains available for audit until cleanup is separately approved.

- [ ] **Step 2: Verify the remote result**

Run:

```bash
git fetch origin --prune
git merge-base --is-ancestor implementation/mvp origin/dev
git rev-list --left-right --count origin/dev...implementation/mvp
```

Expected: the implementation commit is an ancestor of `origin/dev`; the comparison contains no implementation commits missing from `dev`.

### Task 4: Prepare the first CI/CD feature branch

**Files:**
- No files modified in this task; subsequent CI/CD work follows its own approved design and plan.

**Interfaces:**
- Consumes: verified `origin/dev`.
- Produces: remote-ready branch `feature/cicd-dev-promotion` based exactly on `origin/dev`.

- [ ] **Step 1: Create an isolated worktree and feature branch**

Run from the primary repository:

```bash
git fetch origin --prune
git worktree add .worktrees/cicd-dev-promotion -b feature/cicd-dev-promotion origin/dev
```

Expected: the new worktree is clean and its merge base with `origin/dev` equals `origin/dev`.

- [ ] **Step 2: Verify the starting point**

Run:

```bash
git -C .worktrees/cicd-dev-promotion status --short
test "$(git -C .worktrees/cicd-dev-promotion merge-base HEAD origin/dev)" = "$(git rev-parse origin/dev)"
```

Expected: no status output and the ancestry check exits zero.

## Self-review checklist

- The workflow preserves `main` as production and introduces only one integration branch.
- The current implementation enters `dev` through a visible PR.
- No sensitive `.tfplan` file is staged or committed.
- No command force-pushes, deletes a branch, or promotes to production.
- CI/CD implementation and Bedrock work remain separate feature branches and separate review cycles.
