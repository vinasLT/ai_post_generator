from pydantic import BaseModel


class RabbitChatBotTextMessage(BaseModel):
    request_id: int
    response: str

class RabbitChatBotImageMessage(RabbitChatBotTextMessage):
    lot_id: int