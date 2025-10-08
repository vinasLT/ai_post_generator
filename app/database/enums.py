import enum


class AuctionEnum(str, enum.Enum):
    COPART = 'copart'
    IAAI = 'iaai'

class RequestStage(str, enum.Enum):
    STARTING = 'starting'
    FILTERING_BY_TEXT = 'filtering_by_text'
    GENERATION_IMAGES_DESCRIPTION = 'generation_images_description'
    FILTERING_WITH_IMAGES_DESCRIPTION = 'filtering_with_images_description'
    COMPLETED = 'completed'
