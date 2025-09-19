import grpc

from app.config import settings
from app.database.enums import AuctionEnum
from app.rpc_client.base_client import BaseRpcClient, T
from app.rpc_client.gen.python.calculator.v1 import calculator_pb2, calculator_pb2_grpc


class CalculatorRcpClient(BaseRpcClient[calculator_pb2_grpc.CalculatorServiceStub]):
    def __init__(self):
        super().__init__(server_url=settings.RCP_CALCULATOR_URL)

    async def __aenter__(self):
        await self.connect()
        return self

    def _create_stub(self, channel: grpc.aio.Channel) -> T:
        return calculator_pb2_grpc.CalculatorServiceStub(channel)

    async def get_calculator_with_data(self, price: int, auction: AuctionEnum,
                                       vehicle_type: str, location:str,
                                       destination: str | None = None, fee_type: str | None = None)-> calculator_pb2.GetCalculatorWithDataResponse:
        data = calculator_pb2.GetCalculatorWithDataRequest(price=price, auction=auction.upper(), vehicle_type='CAR' if vehicle_type == 'Automobile' else vehicle_type,
                                                           location=location, destination=destination, fee_type=fee_type)
        return await self._execute_request(self.stub.GetCalculatorWithData, data)



