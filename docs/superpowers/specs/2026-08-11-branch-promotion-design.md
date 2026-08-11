# Branch and release-promotion design

## Objective

Use Git branches and pull-request gates to separate feature development, dev
integration, and production promotion without rebuilding artifacts between
environments.

## Branch roles

- `main` is the protected production branch.
- `dev` is the protected integration branch and deploys to the dev environment.
- Short-lived `feature/*` and `fix/*` branches start from the latest `dev` and
  return to `dev` through pull requests.
- The existing `implementation/mvp` branch enters the workflow through an
  initial pull request to `dev`.

## Promotion flow

```text
feature/* or fix/*
        -> pull request and required CI checks
dev
        -> automatic dev deployment and smoke tests
        -> protected promotion pull request
main
        -> explicit production-environment approval
        -> production deploy of the exact dev-tested image digests
```

Direct feature work and direct pushes to `dev` or `main` are prohibited. A
failed validation stops promotion. Production is not rebuilt from source;
immutable ECR digests validated in dev are promoted.

## Immediate sequence

1. Create remote `dev` from `origin/main`.
2. Open and validate a pull request from `implementation/mvp` to `dev`.
3. Implement or correct CI/CD behavior on a branch created from `dev` and merge
   it through a pull request.
4. Create `feature/bedrock-explanations` from the updated `dev`, validate it in
   AWS dev, and merge it through a pull request.
5. Promote `dev` to `main` only after dev smoke tests pass and production
   approval is explicitly granted.

## Safety boundaries

- Terraform plan files, Terraform state, credentials, API keys, and generated
  secret material are never committed.
- Pull-request checks must include tests and security validation.
- Deployments are serialized per environment.
- Infrastructure applies and production deployments require protected approval.
- An ambiguous deployment or external mutation is not retried automatically.

## Success criteria

- GitHub shows protected `dev` and `main` branches.
- All changes reach `dev` through pull requests with passing checks.
- Dev deploys automatically and records immutable release metadata.
- Production promotion uses the exact dev-tested image digests and requires an
  explicit approval gate.
