from pydantic import BaseModel, Field, ConfigDict, field_validator
from langchain_core.output_parsers import PydanticOutputParser


class LotObject(BaseModel):
    lot_id: int = Field(..., description="Lot ID")
    small_description: str = Field(..., description="Small description of the vehicle, 1 sentence")
    whats_bad: str = Field(..., description="Describe in few words what's bad about the vehicle, for example: 'Front end Damage', few words")
    whats_good: str = Field(..., description="Describe in few words what's good about the vehicle, few words")


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lots: list[LotObject] | None = Field(
        None, min_length=30, max_length=60,
        description="Lots that you choose (ONLY UNIQUE VALUES)"
    )
    is_error: bool = False
    error_detail: str | None = None



    @field_validator("lots")
    @classmethod
    def ensure_unique(cls, v: list[LotObject]) -> list[LotObject]:
        if v:
            lot_ids = [lot.lot_id for lot in v]
            repeated = []

            for lot in v:
                if lot.lot_id in lot_ids:
                    repeated.append(lot.lot_id)
            if repeated:
                raise ValueError("lot_ids must contain only unique values, replace this lot_ids: ", repeated)
        return v


def get_agent_result_parser(lots_min: int = 30, lots_max: int = 60) -> type[AgentResult]:
    class LimitedAgentResult(AgentResult):
        lot_ids: list[LotObject] = Field(
            ..., min_length=lots_min, max_length=lots_max,
            description="Lots that you choose (ONLY UNIQUE VALUES)"
        )
    return LimitedAgentResult

def get_best_lot_chooser_schema()-> type[BaseModel]:
    class BestLotChooserResult(BaseModel):
        lot_ids: list[int] = Field(..., description="Lot IDs of vehicles that you choose (ONLY UNIQUE VALUES)")

    return BestLotChooserResult

