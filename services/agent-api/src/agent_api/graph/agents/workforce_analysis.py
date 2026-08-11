from agent_api.graph.agents.base import BoundedSpecialistAgent
from agent_api.graph.intents import Intent


class WorkforceAnalysisAgent(BoundedSpecialistAgent):
    name = "workforce_analysis"
    intents = frozenset({Intent.EXPLAIN_EMPLOYEE_OVERLOAD, Intent.EVALUATE_TASK_FIT})
    allowed_tools = frozenset({"get_employee_overload_risk", "get_task_fit_risk"})
