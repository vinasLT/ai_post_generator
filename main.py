import asyncio
import signal
from aio_pika import connect_robust
from app.config import settings
from app.services.rabbit.rabbit_consumer import RabbitPostsConsumer, PostsRoutingKeys

async def main():
    connection = await connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        consumer = RabbitPostsConsumer(connection, [rk.value for rk in PostsRoutingKeys])
        await consumer.set_up()
        await consumer.start_consuming()
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(s, stop_event.set)
            except NotImplementedError:
                pass
        await stop_event.wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
