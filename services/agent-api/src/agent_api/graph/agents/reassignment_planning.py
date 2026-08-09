from agent_api.graph.agents.base import BoundedSpecialistAgent
from agent_api.graph.intents import Intent


class ReassignmentPlanningAgent(BoundedSpecialistAgent):
    name = "reassignment_planning"
    intents = frozenset({Intent.REASSIGNMENT_CANDIDATES, Intent.WHAT_IF_SIMULATION})
    allowed_tools = frozenset({"get_reassignment_candidates", "simulate_reassignment"})
