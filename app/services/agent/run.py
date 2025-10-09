import os
import json
import asyncio
import inspect
from typing import Any, Dict, List
from openai import AsyncOpenAI
from openai.types import ResponsesModel

from app.config import settings
from app.services.agent.response_schemas.main_agent import MAIN_AGENT_JSON_SCHEMA
from app.services.agent.tools import tools, tool_mapping

MODEL: ResponsesModel = "gpt-5"



async def execute_tool(call_id: str, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    fn = tool_mapping.get(name)
    if not fn:
        out = {"error": "unknown_tool", "name": name}
    else:
        try:
            if inspect.iscoroutinefunction(fn):
                res = await fn(**args)
            else:
                res = await asyncio.to_thread(fn, **args)
            out = res
        except Exception as e:
            out = {"error": "tool_execution_error", "message": str(e)}
    return {"type": "function_call_output", "call_id": call_id, "output": json.dumps(out, ensure_ascii=False)}

def parse_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}

async def collect_outputs_async(response) -> List[Dict[str, Any]]:
    tasks: List[asyncio.Task] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "function_call":
            name = getattr(item, "name", "")
            call_id = getattr(item, "call_id", "")
            args = parse_args(getattr(item, "arguments", {}))
            tasks.append(asyncio.create_task(execute_tool(call_id, name, args)))
    if not tasks:
        return []
    return await asyncio.gather(*tasks)

async def run_agent_async(prompt: str) -> str:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    with open('instructions/main_agent.txt', 'r') as f:
        instructions = f.read()
    response = await client.responses.create(model=MODEL, text=MAIN_AGENT_JSON_SCHEMA, instructions=instructions, input=prompt, tools=tools, parallel_tool_calls=True)
    while True:
        outputs = await collect_outputs_async(response)
        if not outputs:
            return response.output_text
        response = await client.responses.create(model=MODEL, text=MAIN_AGENT_JSON_SCHEMA, input=outputs, previous_response_id=response.id, tools=tools, parallel_tool_calls=True)

async def main():
    text = await run_agent_async("Get lots for IAAI auction and BMW make")
    print(text)

if __name__ == "__main__":
    asyncio.run(main())
