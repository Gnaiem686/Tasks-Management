# CI/CD promotion design

## Objective

Automatically deploy every reviewed merge to `dev`, require validation of the
exact merge commit before AWS mutation, and preserve `main` as the protected
production boundary.

## Workflow responsibilities

- `ci.yml` is reusable through `workflow_call`, validates pull requests to
  `dev` and `main`, and validates direct production-branch events.
- `deploy-dev.yml` triggers on pushes to `dev` and manual dispatch. It invokes
  the reusable CI workflow for the exact commit, then deploys only when that
  gate succeeds.
- `promote-prod.yml` is a protected, manually approved production promotion.
  It consumes immutable dev-tested image digest and release metadata rather
  than rebuilding images.
- `terraform-plan.yml` and `terraform-apply.yml` retain separate infrastructure
  responsibilities and serialized applies.

## Dev flow

```text
feature or fix pull request
  -> ci.yml
  -> merge to dev
  -> deploy-dev.yml
       -> reusable ci.yml on the merge commit
       -> build and scan images
       -> resolve immutable ECR digests
       -> render and validate manifests
       -> checksum release bundle
       -> SSM deployment under Bash
       -> migration and rollout gates
       -> smoke tests and release evidence
```

The AWS deployment job has `needs: quality`, uses the `dev` GitHub Environment,
and is serialized with `concurrency: deploy-dev`. A failed quality, migration,
rollout, image scan, or smoke test prevents a successful release.

## Production flow

```text
dev release evidence
  -> dev-to-main pull request and CI
  -> main
  -> manual promote-prod dispatch
  -> protected production Environment approval
  -> verify dev release commit and immutable digests
  -> deploy exact digests to prod
  -> non-destructive production smoke tests
```

Production does not rebuild application images and never performs destructive
database rollback. Missing or inconsistent release evidence fails closed.

## Failure handling

- SSM commands explicitly invoke Bash; no command relies on `/bin/sh`
  supporting `pipefail`.
- Deployments use bounded GitHub job timeouts and environment concurrency.
- Codecov is best-effort until the repository is onboarded; coverage XML,
  JUnit, audit, SBOM, Kubernetes, and deployment artifacts remain mandatory CI
  artifacts.
- Secrets are read only from protected GitHub environments or short-lived AWS
  OIDC credentials and are never printed.
- A failed or ambiguous deployment does not trigger production promotion.

## Required GitHub configuration

- `dev` and `main` require pull requests and the `ci` status check.
- Direct pushes to protected branches are disabled.
- The `production` GitHub Environment requires manual approval.
- The `dev` and `production` environments hold environment-scoped variables
  and secrets; dev identities cannot access production resources.

## Acceptance criteria

- A green feature PR merged to `dev` automatically starts `deploy-dev.yml`.
- The deployment job cannot start until reusable CI passes on the merge commit.
- The SSM release command runs under Bash and verifies the bundle checksum.
- The dev deployment records immutable image digests and validation evidence.
- Production promotion is approval-protected and consumes exact dev-tested
  digests without rebuilding.
- Workflow-policy tests reject incorrect branch triggers, missing quality
  dependencies, mutable image promotion, or unprotected production jobs.
