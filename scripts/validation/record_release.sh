#!/usr/bin/env bash
set -Eeuo pipefail

: "${RELEASE_ENVIRONMENT:?Set RELEASE_ENVIRONMENT}"
: "${GIT_COMMIT:?Set GIT_COMMIT}"
: "${IMAGE_DIGESTS_JSON:?Set IMAGE_DIGESTS_JSON}"
: "${MANIFEST_VERSION:?Set MANIFEST_VERSION}"
: "${SCORING_VERSION:?Set SCORING_VERSION}"
: "${MIGRATION_VERSION:?Set MIGRATION_VERSION}"
: "${DEPLOYMENT_ACTOR:?Set DEPLOYMENT_ACTOR}"
: "${VALIDATION_RESULT:?Set VALIDATION_RESULT}"

output=${RELEASE_RECORD_PATH:-artifacts/deployment/release.json}
mkdir -p "$(dirname "$output")"

jq -e 'type == "object" and length == 4 and all(.[]; test("@sha256:[a-f0-9]{64}$"))' \
  <<<"$IMAGE_DIGESTS_JSON" >/dev/null

jq -n \
  --arg environment "$RELEASE_ENVIRONMENT" \
  --arg git_commit "$GIT_COMMIT" \
  --argjson image_digests "$IMAGE_DIGESTS_JSON" \
  --arg manifest_version "$MANIFEST_VERSION" \
  --arg scoring_version "$SCORING_VERSION" \
  --arg migration_version "$MIGRATION_VERSION" \
  --arg deployment_actor "$DEPLOYMENT_ACTOR" \
  --arg dev_validation "$VALIDATION_RESULT" \
  --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    environment: $environment,
    git_commit: $git_commit,
    image_digests: $image_digests,
    manifest_version: $manifest_version,
    scoring_version: $scoring_version,
    migration_version: $migration_version,
    deployment_actor: $deployment_actor,
    timestamp: $timestamp,
    dev_validation: $dev_validation
  }' >"$output"

echo "Release metadata recorded at $output"
