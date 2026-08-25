# CI/CD dev deployment and production promotion plan

> Execute this plan with `superpowers:executing-plans` and test workflow policy changes first.

## Task 1 — Reusable, branch-aware CI

1. Add a failing workflow-policy test requiring `ci.yml` to support
   `workflow_call`, PRs to `dev` and `main`, and pushes to `main`.
2. Run the focused test and confirm the expected failure.
3. Update `.github/workflows/ci.yml` minimally and rerun the test.
4. Commit: `ci: make validation workflow reusable`.

## Task 2 — Quality-gated automatic dev deployment

1. Add failing policy tests requiring `deploy-dev.yml` to trigger on `dev`, call
   reusable CI, make deployment depend on that quality job, persist digest
   evidence, and execute SSM payloads explicitly through Bash.
2. Run the focused tests and confirm the expected failures.
3. Update `.github/workflows/deploy-dev.yml`, preserving the existing immutable
   image, migration, rollout, and smoke-test gates.
4. Validate YAML and rerun workflow-policy tests.
5. Commit: `ci: gate automatic dev deployment`.

## Task 3 — Approval-protected immutable production promotion

1. Add failing policy tests requiring `.github/workflows/promote-prod.yml` to
   use manual dispatch, the `production` environment, immutable dev evidence,
   no image rebuild, explicit Bash for SSM, and non-destructive verification.
2. Run the tests and confirm the missing-workflow failure.
3. Implement the workflow to download dev release evidence, validate the commit
   and digests, render prod manifests with those exact digests, deploy through
   S3/SSM, and run non-destructive smoke checks.
4. Validate YAML and rerun policy tests.
5. Commit: `ci: add protected production promotion`.

## Task 4 — Full verification and integration handoff

1. Run formatting, linting, typing, workflow-policy tests, and the full test
   suite.
2. Inspect the diff for secrets, mutable tags, accidental application changes,
   and `/bin/sh` `pipefail` regressions.
3. Push the feature branch and open a PR to `dev`.
4. Verify required checks and merge only when green.
5. Configure or report any remaining GitHub Environment or branch-protection
   prerequisites before claiming automatic deployment is operational.
