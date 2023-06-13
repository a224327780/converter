import asyncio

from aioredis import Redis
from sanic.log import logger

from utils.converter import ConverterSubscribe


async def converter_subscribe_task(app):
    request_session = app.ctx.request_session
    redis: Redis = app.ctx.redis
    converter = ConverterSubscribe(redis, request_session)
    await asyncio.sleep(3)
    while 1:
        try:
            await converter.run(False)
        except Exception as e:
            logger.exception(e)
        finally:
            await asyncio.sleep(3600 + 60)
