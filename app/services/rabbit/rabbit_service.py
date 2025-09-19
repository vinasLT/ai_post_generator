import asyncio
import json
import uuid
from datetime import datetime, UTC

from aio_pika import connect_robust, Message, ExchangeType, DeliveryMode

from app.config import settings

import asyncio
import json
import uuid
from datetime import datetime, UTC
from typing import Any
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType, Queue

from app.core.logger import logger


class RabbitMQPublisher:
    def __init__(self, exchange_type: ExchangeType = ExchangeType.TOPIC):
        self.url = settings.RABBITMQ_URL
        self.exchange_name = settings.RABBITMQ_EXCHANGE_NAME
        self.exchange_type = exchange_type
        self.connection = None
        self.channel = None
        self.exchange = None

        # RPC functionality
        self.callback_queue: Queue | None = None
        self.pending_requests: dict[str, asyncio.Future] = {}
        self.consumer_tag: str | None = None

    async def connect(self):
        """Подключение к RabbitMQ"""
        self.connection = await connect_robust(self.url)
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
            self.exchange_name,
            type=self.exchange_type,
            durable=True
        )

        # Создаем временную очередь для RPC ответов
        await self._setup_rpc_queue()

    async def _setup_rpc_queue(self):
        """Настройка очереди для получения RPC ответов"""
        self.callback_queue = await self.channel.declare_queue(
            exclusive=True,
            auto_delete=True
        )

        # Начинаем слушать ответы
        self.consumer_tag = await self.callback_queue.consume(
            self._on_rpc_response,
            no_ack=True
        )
        logger.info(f"RPC callback queue created: {self.callback_queue.name}")

    async def _on_rpc_response(self, message):
        """Обработчик RPC ответов"""
        correlation_id = message.correlation_id

        if correlation_id in self.pending_requests:
            future = self.pending_requests.pop(correlation_id)

            if not future.cancelled():
                try:
                    response_data = json.loads(message.body.decode())
                    future.set_result(response_data)
                    logger.info(f"Received RPC response for correlation_id: {correlation_id}")
                except json.JSONDecodeError as e:
                    future.set_exception(ValueError(f"Invalid JSON response: {e}"))
                except Exception as e:
                    future.set_exception(e)

    async def publish(self, routing_key: str, payload: dict):
        """Обычная публикация сообщения (fire-and-forget)"""
        if self.exchange is None:
            await self.connect()

        correlation_id = str(uuid.uuid4())
        message_body = json.dumps({
            "type": routing_key,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": correlation_id
        }).encode()

        message = Message(
            message_body,
            content_type="application/json",
            correlation_id=correlation_id,
            delivery_mode=DeliveryMode.PERSISTENT
        )

        await self.exchange.publish(message, routing_key=routing_key)
        logger.info(f"Published message with routing_key: {routing_key}")

    async def publish_and_wait_response(
            self,
            routing_key: str,
            payload: dict,
            timeout: int = 30
    ) -> dict[Any, Any]:
        """
        Отправляет сообщение и ждет ответ (RPC pattern)

        Args:
            routing_key: Ключ маршрутизации
            payload: Данные сообщения
            timeout: Таймаут ожидания ответа в секундах

        Returns:
            Ответ от сервиса

        Raises:
            TimeoutError: Если ответ не получен в течение timeout
            ConnectionError: Если нет подключения
        """
        if self.exchange is None:
            await self.connect()

        if self.callback_queue is None:
            raise ConnectionError("RPC callback queue not initialized")

        correlation_id = str(uuid.uuid4())
        future = asyncio.Future()
        self.pending_requests[correlation_id] = future

        try:
            message_body = json.dumps({
                "action": routing_key,
                "data": payload,
                "timestamp": datetime.now(UTC).isoformat(),
                "correlation_id": correlation_id,
                "rpc": True  # Флаг что это RPC запрос
            }).encode()

            message = Message(
                message_body,
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,  # Указываем куда отправить ответ
                delivery_mode=DeliveryMode.PERSISTENT
            )

            await self.exchange.publish(message, routing_key=routing_key)
            logger.info(f"Published RPC request with routing_key: {routing_key}, correlation_id: {correlation_id}")

            # Ждем ответ с таймаутом
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            self.pending_requests.pop(correlation_id, None)
            raise TimeoutError(f"RPC timeout for routing_key: {routing_key}")
        except Exception as e:
            self.pending_requests.pop(correlation_id, None)
            logger.error(f"Error in RPC request: {e}")
            raise

    async def send_rpc_request(
            self,
            service_queue: str,
            action: str,
            data: dict = None,
            timeout: int = 30
    ) -> dict[Any, Any]:
        """
        Отправляет RPC запрос напрямую в очередь (без exchange)

        Args:
            service_queue: Имя очереди сервиса
            action: Действие для выполнения
            data: Дополнительные данные
            timeout: Таймаут ожидания

        Returns:
            Ответ от сервиса
        """
        if self.connection is None:
            await self.connect()

        if self.callback_queue is None:
            raise ConnectionError("RPC callback queue not initialized")

        correlation_id = str(uuid.uuid4())
        future = asyncio.Future()
        self.pending_requests[correlation_id] = future

        try:
            request_payload = {
                "action": action,
                "data": data or {},
                "timestamp": datetime.now(UTC).isoformat(),
                "correlation_id": correlation_id
            }

            message = Message(
                json.dumps(request_payload).encode(),
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
                delivery_mode=DeliveryMode.PERSISTENT
            )

            # Отправляем напрямую в очередь
            await self.channel.default_exchange.publish(
                message,
                routing_key=service_queue
            )

            logger.info(f"Sent RPC request to queue: {service_queue}, action: {action}")

            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            self.pending_requests.pop(correlation_id, None)
            raise TimeoutError(f"RPC timeout for queue: {service_queue}, action: {action}")
        except Exception as e:
            self.pending_requests.pop(correlation_id, None)
            logger.error(f"Error in RPC request to {service_queue}: {e}")
            raise

    async def send_multiple_rpc_requests(
            self,
            requests: list,
            timeout: int = 30
    ) -> list:
        """
        Отправляет несколько RPC запросов параллельно

        Args:
            requests: Список словарей с параметрами запросов
                     [{"service_queue": "user_service", "action": "get_user", "data": {"id": 1}}]
            timeout: Общий таймаут для всех запросов

        Returns:
            Список ответов в том же порядке
        """
        tasks = []

        for request in requests:
            task = self.send_rpc_request(
                service_queue=request["service_queue"],
                action=request["action"],
                data=request.get("data"),
                timeout=timeout
            )
            tasks.append(task)
            print('task added')

        try:
            responses = await asyncio.gather(*tasks)
            return responses
        except Exception as e:
            logger.error(f"Error in multiple RPC requests: {e}")
            raise

    async def close(self):
        """Закрытие соединения"""
        # Отменяем все pending запросы
        for correlation_id, future in self.pending_requests.items():
            if not future.cancelled():
                future.cancel()
        self.pending_requests.clear()

        # Останавливаем consumer
        if self.consumer_tag and self.callback_queue:
            await self.callback_queue.cancel(self.consumer_tag)

        if self.connection:
            await self.connection.close()
            logger.info("RabbitMQ connection closed")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


if __name__ == "__main__":
    async def main():
        publisher = RabbitMQPublisher()
        await publisher.connect()
        payload = {"user_uuid": str(uuid.uuid4()),
                   'code': '123456',
                   'destination': 'email',
                   'first_name': 'John',
                   'last_name': 'Doe',
                   'email': 'peyrovskaaa@gmail.com',
                   'expire_minutes': 15,
                   'phone_number': '32452937423'}
        await publisher.publish(routing_key="notification.auth.send_code", payload=payload)
        await publisher.close()

    asyncio.run(main())