# Requirements-to-tests mapping

The authoritative requirements are the numbered rows in
`docs/spec.md` under **Project requirements traceability**. Paths may be created
in later tasks; `planned` never means implemented or passing.

| Requirement | Planned automated evidence | Primary command or gate | Status |
|---|---|---|---|
| 0.1 | `tests/test_spec_contract.py` | PR documentation gate | planned |
| 0.2 | `tests/test_test_plan_contract.py` | `make check` | implemented |
| 0.3 | `tests/security/test_implementation_gates.py` | PR gate | planned |
| 1.1 | `tests/e2e/test_seeded_workforce_risk.py` | E2E gate | planned |
| 1.2 | `domain/workforce_risk/tests/test_scoring.py` | unit and performance gates | planned |
| 1.3 | `services/agent-api/tests/test_graph_workflows.py` | unit gate | planned |
| 1.4 | `services/agent-api/tests/test_agent_handoffs.py` | unit and security gates | planned |
| 1.5 | `services/agent-api/tests/test_openapi_contract.py` | contract gate | planned |
| 1.6 | `services/agent-api/tests/ui/test_manager_ui.py` | UI gate | planned |
| 1.7 | `tests/security/test_resilience_policies.py` | failure-injection gate | planned |
| 1.8 | `tests/integration/test_write_closed.py` | integration gate | planned |
| 1.9 | `tests/security/test_prompt_policy.py` | security gate | planned |
| 1.10 | `domain/workforce_risk/tests/test_finding_score_families.py` | unit gate | planned |
| 1.11 | `tests/integration/test_comment_evidence_lifecycle.py` | unit and integration gates | planned |
| 1.12 | `services/agent-api/tests/test_general_question_matrix.py` and `test_universal_grounding.py` | generalized chat acceptance gate | implemented |
| 2.1 | `tests/contract/test_mcp_inventory.py` | contract gate | planned |
| 2.2 | `tests/integration/test_jira_mcp_transport.py` | dev integration gate | planned |
| 2.3 | `tests/security/test_no_runtime_rest_bypass.py` | security gate | planned |
| 2.4 | `tests/contract/test_workforce_mcp_transport.py` | real MCP transport gate | planned |
| 2.5 | `services/devops-mcp/tests/test_read_only_tools.py` | unit and transport gates | planned |
| 2.6 | `tests/e2e/test_real_manager_mcp_interaction.py` | E2E gate | planned |
| 3.1 | `tests/infrastructure/test_kubeadm_nodes.py` | infrastructure gate | planned |
| 3.2 | `tests/infrastructure/test_environment_isolation.py` | infrastructure gate | planned |
| 3.3 | `tests/infrastructure/test_workload_manifests.py` | manifest gate | planned |
| 3.4 | `tests/performance/test_production_hpa.py` | pre-production gate | planned |
| 3.5 | `tests/integration/test_aws_service_boundaries.py` | dev integration gate | planned |
| 3.6 | `tests/infrastructure/test_terraform.py` | Terraform gate | planned |
| 3.7 | `tests/integration/test_synthetic_seed.py` | dev Jira gate | planned |
| 3.8 | `tests/e2e/test_external_scenario_runner.py` | scenario workflow | planned |
| 4.1 | `.github/workflows/ci.yml` and deployment workflow rehearsals | GitHub Actions | partial |
| 4.2 | `tests/security/test_ci_artifact_contract.py` | CI artifact inspection | planned |
| 4.3 | `tests/infrastructure/test_digest_promotion.py` | deployment gate | planned |
| 4.4 | `tests/infrastructure/test_gitops_decision.py` | Phase 0/optional hardening gate | planned |
| 5.1 | `tests/contract/test_health_contracts.py` | contract gate | planned |
| 5.2 | `tests/infrastructure/test_observability_contract.py` | observability gate | planned |
| 5.3 | `tests/infrastructure/test_alert_rules.py` | controlled alert gate | planned |
| 5.4 | `tests/e2e/test_authenticated_dashboards.py` | dev smoke gate | planned |
| 6.1 | `tests/security/test_unit_isolation.py` | `make test-unit` | planned |
| 6.2 | `tests/integration/test_agent_workforce_mcp_streamable_http.py` | real MCP transport gate | planned |
| 6.3 | `tests/integration/test_dependency_failures.py` | integration gate | planned |
| 6.4 | `tests/e2e/test_verified_reassignment.py` | E2E gate | planned |
| 6.5 | `tests/performance/`, UI tests, and `tests/infrastructure/` | specialized gates | planned |
| 7.1 | `tests/integration/test_bedrock_smoke.py` | optional live Bedrock gate | planned |
| 7.2 | `tests/infrastructure/test_version_matrix.py` | pre-infrastructure gate | planned |
| 7.3 | `tests/performance/test_production_hpa.py` | pre-production gate | planned |
| 7.4 | `tests/e2e/test_demo_readiness.py` | demo rehearsal | planned |
| 8.1 | `skills/workforce-risk-triage/tests/` | skill verification | planned |
| 8.2 | `skills/deploy-and-verify-environment/tests/` | skill verification | planned |
| 8.3 | `skills/safe-jira-reassignment-demo/tests/` | skill verification | planned |

## Conversational evidence and Bedrock grounding

| Requirement | Automated evidence | Expected proof |
|---|---|---|
| Question-compatible evidence planning | `services/agent-api/tests/test_evidence_plan_normalizer.py` | Blocker, deadline, employee, capacity, skills, explicit issue, and follow-up wording select compatible read-only evidence without a fixed intent whitelist. |
| Focused structured evidence | `services/agent-api/tests/test_answer_evidence_focus.py` and `test_evidence_collectors.py` | Exact matching tasks and employees, blocker direction, deadline order, missing estimates, and deterministic levels are retained in `AnswerEvidenceSet`. |
| Conversation references | `services/agent-api/tests/test_conversation_references.py` and `test_general_question_matrix.py` | Task and employee referents survive across turns; ambiguous singular references are not guessed. |
| Bedrock-only final prose | `services/agent-api/tests/test_explanations.py` and `test_project_chat.py` | Every successful chat response reports `source=bedrock`; deterministic code supplies and validates facts but does not write final prose. |
| Focused factual grounding | `services/agent-api/tests/test_universal_grounding.py` | Unknown Jira issues, changed risk levels, invented dependencies, omitted exhaustive matches, and vague insufficiency despite usable evidence are rejected. |
| Precise last-resort missing data | `services/agent-api/tests/test_universal_grounding.py` | Bedrock may request an exact missing field for an exact entity only after focused evidence has been derived. |
| Persistent transient recovery | `services/agent-api/tests/ui/test_contextual_chat.py` | Retryable Bedrock timeouts/throttling keep the UI waiting and preserve the eventual Bedrock answer without showing a transient failure bubble. |
