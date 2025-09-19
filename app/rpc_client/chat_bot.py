import os
import sys

import grpc

from app.config import settings
from app.rpc_client.base_client import BaseRpcClient, T

# Ensure generated proto packages (auction, carfax, payment) are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gen', 'python'))

from app.rpc_client.gen.python.chat_bot.v1 import chat_bot_pb2_grpc, chat_bot_pb2



class ChatBotRpcClient(BaseRpcClient[chat_bot_pb2_grpc.ChatBotServiceStub]):
    def __init__(self):
        super().__init__(server_url=settings.RPC_CHAT_BOT_URL)

    async def __aenter__(self):
        await self.connect()
        return self

    def _create_stub(self, channel: grpc.aio.Channel) -> T:
        return chat_bot_pb2_grpc.ChatBotServiceStub(channel)

    async def get_response_from_model(self, prompt: str, assistant_name: str) -> chat_bot_pb2.GetModelResponseResponse:
        data = chat_bot_pb2.GetModelResponseRequest(prompt=prompt, assistant_name=assistant_name)
        return await self._execute_request(self.stub.GetModelResponse, data, timeout=120)

    async def get_response_on_image(self, urls: list[str], assistant_name: str) -> chat_bot_pb2.GetModelImageResponseResponse:
        data = chat_bot_pb2.GetModelImageResponseRequest(urls=urls, assistant_name=assistant_name)
        return await self._execute_request(self.stub.GetModelImageResponse, data, timeout=120)

