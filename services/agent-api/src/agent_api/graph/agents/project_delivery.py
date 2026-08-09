from agent_api.graph.agents.base import BoundedSpecialistAgent
from agent_api.graph.intents import Intent


class ProjectDeliveryAgent(BoundedSpecialistAgent):
    name = "project_delivery"
    intents = frozenset({Intent.EXPLAIN_PROJECT_RISK, Intent.EXPLAIN_HISTORY})
    allowed_tools = frozenset({"get_project_risk", "get_risk_history"})
