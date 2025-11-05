from pydantic import BaseModel, Field, ConfigDict, field_validator, conlist


def get_chooser_response_schema(min_lot: int = 50, max_lot: int = 60) -> type[BaseModel]:
    LotIDsType = conlist(int, min_length=min_lot, max_length=max_lot)

    class LotChooserResponse(BaseModel):
        lot_ids: LotIDsType = Field(..., description="List of lot ids")
        is_error: bool = Field(False, description="Error flag")
        error_detail: str | None = Field(None, description="Error detail")

    return LotChooserResponse



class LotObject(BaseModel):
    lot_id: int = Field(..., description="Lot ID")
    description: str = Field(..., description="Describe in few words what's good and what's bad about the lot")


class ImageProcessingSchema(BaseModel):
    description: str = Field(..., description="Describe this vehicle")
    bad_aspect: str = Field(..., description="What aspect of the vehicle is bad?")
    good_aspect: str = Field(..., description="What aspect of the vehicle is good?")

class ImageProcessingResult(BaseModel):
    lot_id: int = Field(..., description="Lot ID")
    descriptions: ImageProcessingSchema


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lots: list[LotObject] | None = Field(
        None,
        description="Lots that you choose (ONLY UNIQUE VALUES)"
    )
    is_error: bool = False
    error_detail: str | None = None

    @field_validator("lots")
    @classmethod
    def ensure_unique(cls, v: list[LotObject] | None) -> list[LotObject] | None:
        if not v:
            return v

        seen: set[int] = set()
        duplicates: set[int] = set()
        for lot in v:
            lot_id = lot.lot_id
            if lot_id in seen:
                duplicates.add(lot_id)
            else:
                seen.add(lot_id)

        if duplicates:
            duplicated_values = ", ".join(str(x) for x in sorted(duplicates))
            raise ValueError(f"lot_ids must contain only unique values, duplicates found: {duplicated_values}")

        return v


def get_agent_result_parser(lots_min: int, lots_max: int) -> type[AgentResult]:
    class LimitedAgentResult(AgentResult):
        lots: list[LotObject] = Field(
            ...,
            min_length=lots_min,
            max_length=lots_max,
            description="Lots that you choose (ONLY UNIQUE VALUES)"
        )

    return LimitedAgentResult
