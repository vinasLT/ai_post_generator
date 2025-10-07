import grpc

from app.config import settings
from app.database.enums import AuctionEnum
from app.rpc_client.base_client import BaseRpcClient, T
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.calculator.v1 import calculator_pb2, calculator_pb2_grpc
from app.rpc_client.gen.python.calculator.v1.calculator_pb2 import GetCalculatorBatchRequest, \
    GetCalculatorWithDataRequest, GetCalculatorWithDataBatchRequest


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
        return await self._execute_request(self.stub.GetCalculatorWithData, data, timeout=120)


    async def get_batch_calculators_with_data(self, lots: list[lot_pb2.Lot])-> calculator_pb2.GetCalculatorWithDataBatchResponse:
        calculator_data: list[GetCalculatorBatchRequest] = []

        for lot in lots:
            calculator_data.append(GetCalculatorBatchRequest(
                data=GetCalculatorWithDataRequest(price=1,
                                                  auction=AuctionEnum(lot.base_site.lower()),
                                                  vehicle_type='CAR' if lot.vehicle_type == 'Automobile' else 'MOTO',
                                                  location=lot.location),
                lot_id=str(lot.lot_id)
            ))
        data = GetCalculatorWithDataBatchRequest(data=calculator_data)

        return await self._execute_request(self.stub.GetCalculatorWithDataBatch, data, timeout=120)




