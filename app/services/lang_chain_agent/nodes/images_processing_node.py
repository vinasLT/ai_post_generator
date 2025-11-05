import asyncio
import json
from typing import Any, Dict

from asyncio import Semaphore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from app.config import settings
from app.database.crud.post import PostService
from app.database.db.session import get_async_db
from app.services.lang_chain_agent.schemas import ImageProcessingSchema, ImageProcessingResult
from app.services.lang_chain_agent.state_context import AgentsRuntimeContext, AgentsState
from app.services.lang_chain_agent.tools import get_instructions

llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=settings.OPENAI_API_KEY, use_responses_api=True)

image_processing_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_instructions}"),
        MessagesPlaceholder(variable_name="images"),
        (
            "human",
            "Analyze this 5 lots and make little summary based on it (one sentence)\n"
            "Additional info about vehicle:\n"
            "Name of vehicle: {title}\n"
            "Primary Damage: {primary_damage}\n"
        ),
    ]
)

async def images_processing_agent(state: AgentsState, runtime: Runtime[AgentsRuntimeContext]) -> Dict[str, Any]:
    request_id = runtime.context["request_id"]

    async with get_async_db() as db:
        posts_service = PostService(db)
        posts = await posts_service.get_by_request_id(request_id)

    semaphore = Semaphore(10)
    results: list[ImageProcessingResult] = []

    async def analyze_post(post) -> None:
        async with semaphore:
            if not post.images:
                return
            images_urls = [u.strip() for u in post.images.split(",") if u.strip()][:5]
            if not images_urls:
                return

            image_message = HumanMessage(
                content=[{"type": "image_url", "image_url": {"url": url}} for url in images_urls]
            )

            prompt_messages = image_processing_prompt.format_messages(
                system_instructions=get_instructions("image_analyzer.md"),
                title=post.title or "",
                primary_damage=post.primary_damage or "",
                images=[image_message],
            )

            structured_llm = llm.with_structured_output(ImageProcessingSchema)
            response: ImageProcessingSchema = await structured_llm.ainvoke(prompt_messages)

            results.append(ImageProcessingResult(lot_id=post.lot_id, descriptions=response))

    tasks = [asyncio.create_task(analyze_post(post)) for post in posts]
    await asyncio.gather(*tasks)

    ai_msg = AIMessage(content=str([result.model_dump_json() for result in results]))
    return {"lots_images_descriptions": results, "messages": [ai_msg]}

class DummyRuntime:
    def __init__(self, context: dict[str, Any]):
        self.context = context

async def _main() -> None:
    runtime = DummyRuntime({"request_id": 4})
    state: Dict[str, Any] = {}
    result = await images_processing_agent(state, runtime)  # type: ignore[arg-type]
    if "lots_images_descriptions" in result:
        printable = {
            "lots_images_descriptions": [
                {"lot_id": r.lot_id, "descriptions": json.loads(r.descriptions.model_dump_json()) if hasattr(r.descriptions, "model_dump_json") else r.descriptions}  # type: ignore[attr-defined]
                for r in result["lots_images_descriptions"]
            ]
        }
        print(json.dumps(printable, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(_main())
