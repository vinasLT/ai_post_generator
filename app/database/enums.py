import enum


class AuctionEnum(str, enum.Enum):
    COPART = 'copart'
    IAAI = 'iaai'

class RequestStage(str, enum.Enum):
    FAILED = 'failed'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
