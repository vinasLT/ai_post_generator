from pydantic import BaseModel, Field, ConfigDict, field_validator
from langchain_core.output_parsers import PydanticOutputParser



def get_agent_result_parser(lots_min: int = 30, lots_max: int = 60) -> PydanticOutputParser:
    class AgentResult(BaseModel):
        model_config = ConfigDict(extra="forbid")

        lot_ids: list[int] = Field(
            ..., min_length=lots_min, max_length=lots_max,
            description="Lot IDs of vehicles that you choose (ONLY UNIQUE VALUES)"
        )
        is_error: bool = False
        error_detail: str | None = None

        @field_validator("lot_ids")
        @classmethod
        def ensure_unique(cls, v: list[int]) -> list[int]:
            if len(v) != len(set(v)):
                raise ValueError("lot_ids must contain only unique values")
            return v
    return PydanticOutputParser(pydantic_object=AgentResult)
