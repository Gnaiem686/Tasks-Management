from agent_api.graph.intents import READ_ONLY_TOOL_ALLOWLISTS, Intent


def test_conversational_graph_has_no_mutation_or_domain_decision_tools() -> None:
    forbidden = {"editJiraIssue", "approve", "execute", "create_proposal", "score"}
    all_tools = {tool for tools in READ_ONLY_TOOL_ALLOWLISTS.values() for tool in tools}
    assert forbidden.isdisjoint(all_tools)
    assert Intent.UNSUPPORTED not in READ_ONLY_TOOL_ALLOWLISTS
