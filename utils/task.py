import asyncio

from sanic.log import logger

from utils.converter import ConverterSubscribe


async def converter_subscribe_task(app):
    converter: ConverterSubscribe = app.ctx.converter
    await asyncio.sleep(3)
    while 1:
        try:
            await converter.run(False)
        except Exception as e:
            logger.exception(e)
        finally:
            await asyncio.sleep(3600 + 60)
