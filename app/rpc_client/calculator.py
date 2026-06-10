import os
import sys

import grpc

from app.config import settings
from app.core.agent_debug_log import agent_debug_log
from app.core.logger import logger
from app.database.enums import AuctionEnum
from app.rpc_client.base_client import BaseRpcClient, T
from app.rpc_client.gen.python.auction.v1 import lot_pb2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gen', 'python'))

from app.rpc_client.gen.python.calculator.v1 import calculator_pb2, calculator_pb2_grpc
from app.rpc_client.gen.python.calculator.v1.calculator_pb2 import GetCalculatorBatchRequest, \
    GetCalculatorWithDataRequest, GetCalculatorWithDataBatchRequest


def normalize_vehicle_type(vehicle_type: str | None) -> str:
    if not vehicle_type:
        return "CAR"
    if vehicle_type == "Automobile":
        return "CAR"
    return vehicle_type


def is_valid_calculator_response(
    response: calculator_pb2.GetCalculatorWithDataResponse | None,
) -> bool:
    if response is None:
        return False
    calculator = response.data.calculator if response.data else None
    return bool(
        calculator
        and calculator.transportation_price
        and calculator.ocean_ship
    )


def calculator_response_from_batch_item(
    item: calculator_pb2.CalculatorBatchItem,
) -> calculator_pb2.GetCalculatorWithDataResponse | None:
    if not item.calculator or not item.calculator.calculator:
        return None
    calculator = item.calculator.calculator
    if not calculator.transportation_price or not calculator.ocean_ship:
        return None
    return calculator_pb2.GetCalculatorWithDataResponse(data=item.calculator, success=True)


def get_broker_fee_from_calculator(
    response: calculator_pb2.GetCalculatorWithDataResponse,
) -> int:
    calculator = response.data.calculator if response.data else None
    if calculator and calculator.broker_fee:
        return calculator.broker_fee
    return 299


class CalculatorRcpClient(BaseRpcClient[calculator_pb2_grpc.CalculatorServiceStub]):
    def __init__(self):
        super().__init__(server_url=settings.RCP_CALCULATOR_URL)

    async def __aenter__(self):
        await self.connect()
        return self

    def _create_stub(self, channel: grpc.aio.Channel) -> T:
        return calculator_pb2_grpc.CalculatorServiceStub(channel)

    async def get_calculator_with_data(
        self,
        price: int,
        auction: AuctionEnum,
        vehicle_type: str,
        location: str,
        destination: str | None = None,
        fee_type: str | None = None,
    ) -> calculator_pb2.GetCalculatorWithDataResponse | None:
        vt_sent = normalize_vehicle_type(vehicle_type)
        data = calculator_pb2.GetCalculatorWithDataRequest(
            price=price,
            auction=auction.upper(),
            vehicle_type=vt_sent,
            location=location,
            destination=destination,
            fee_type=fee_type,
        )
        # #region agent log
        agent_debug_log(
            "H3",
            "calculator.py:get_calculator_with_data",
            "protobuf_request",
            {
                "auction_enum": str(auction),
                "auction_field": auction.upper(),
                "vehicle_type_raw": vehicle_type,
                "vehicle_type_sent": vt_sent,
                "location_preview": (location or "")[:160],
            },
        )
        # #endregion
        response = await self._execute_request(self.stub.GetCalculatorWithData, data, timeout=120)
        if not is_valid_calculator_response(response):
            logger.debug(
                "Calculator returned no pricing data",
                extra={
                    "auction": auction.upper(),
                    "location": location,
                    "vehicle_type": vt_sent,
                    "response_is_none": response is None,
                },
            )
            return None
        return response

    async def get_batch_calculators_with_data(
        self, lots: list[lot_pb2.Lot]
    ) -> calculator_pb2.GetCalculatorWithDataBatchResponse | None:
        calculator_data: list[GetCalculatorBatchRequest] = []

        for lot in lots:
            calculator_data.append(
                GetCalculatorBatchRequest(
                    data=GetCalculatorWithDataRequest(
                        price=1,
                        auction=AuctionEnum(lot.base_site.lower()).upper(),
                        vehicle_type=normalize_vehicle_type(lot.vehicle_type),
                        location=lot.location,
                    ),
                    lot_id=str(lot.lot_id),
                )
            )
        data = GetCalculatorWithDataBatchRequest(data=calculator_data)

        return await self._execute_request(self.stub.GetCalculatorWithDataBatch, data, timeout=120)




