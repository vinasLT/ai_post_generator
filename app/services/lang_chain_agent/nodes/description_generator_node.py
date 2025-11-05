from typing import Any

from langgraph.runtime import Runtime

from app.services.lang_chain_agent.state_context import AgentsState, AgentsRuntimeContext


async def generate_descriptions_node(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> dict[str, Any]:
    pass
    #add a description generator node, for speed up flow, use semaphore here for process lots
