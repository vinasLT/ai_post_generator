import json
import asyncio
import inspect
from typing import Any, Dict, List

from openai.types import ResponsesModel

from app.core.logger import logger
from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot
from app.services.agent.client import openai_client
from app.services.agent.response_schemas.main_agent import MAIN_AGENT_JSON_SCHEMA
from app.services.agent.ai_tools import ai_tools, tool_mapping, get_page_of_lots


class RunAgent:
    MODEL: ResponsesModel = "gpt-5"
    def __init__(self):
        self.lots: list[Lot] = []

    async def execute_tool(self, call_id: str, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        fn = tool_mapping.get(name)
        if not fn:
            out = {"error": "unknown_tool", "name": name}
        else:
            try:
                if inspect.iscoroutinefunction(fn):
                    res = await fn(**args, lots=self.lots)
                else:
                    res = await asyncio.to_thread(fn, **args, lots=self.lots)
                if fn == get_page_of_lots:
                    self.lots.extend(res[1])
                    res = res[0]

                out = res
            except Exception as e:
                logger.exception(f"Error executing tool {name} with args {args}")
                out = {"error": "tool_execution_error", "message": str(e)}
        return {"type": "function_call_output", "call_id": call_id, "output": json.dumps(out, ensure_ascii=False)}

    def parse_args(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                return json.loads(raw)
            except Exception:
                logger.exception(f"Error parsing args: {raw}")
                return {}
        return {}

    async def collect_outputs_async(self, response) -> List[Dict[str, Any]]:
        tasks: List[asyncio.Task] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "function_call":
                name = getattr(item, "name", "")
                call_id = getattr(item, "call_id", "")
                args = self.parse_args(getattr(item, "arguments", {}))
                tasks.append(asyncio.create_task(self.execute_tool(call_id, name, args)))
        if not tasks:
            return []
        return await asyncio.gather(*tasks)

    async def run_agent_async(self,  prompt: str) -> str:

        with open('instructions/main_agent.txt', 'r') as f:
            instructions = f.read()
        response = await openai_client.responses.create(model=self.MODEL, text=MAIN_AGENT_JSON_SCHEMA, instructions=instructions,
                                                 input=prompt, tools=ai_tools, parallel_tool_calls=True)
        while True:
            outputs = await self.collect_outputs_async(response)
            if not outputs:
                print(len(self.lots))
                return response.output_text
            print(len(self.lots))
            response = await openai_client.responses.create(model=self.MODEL, text=MAIN_AGENT_JSON_SCHEMA, input=outputs,
                                                     previous_response_id=response.id, tools=ai_tools,
                                                     parallel_tool_calls=True)



if __name__ == "__main__":
    async def main():
        agent = RunAgent()
        response = await agent.run_agent_async("Find lots for IAAI, make: BMW")
        print(response)

    asyncio.run(main())

