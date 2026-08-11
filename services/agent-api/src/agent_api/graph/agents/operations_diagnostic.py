from agent_api.graph.agents.base import BoundedSpecialistAgent
from agent_api.graph.intents import Intent


class OperationsDiagnosticAgent(BoundedSpecialistAgent):
    name = "operations_diagnostic"
    intents = frozenset({Intent.OPERATIONS_DIAGNOSIS})
    allowed_tools = frozenset({"diagnose_operations_read_only"})
