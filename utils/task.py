import asyncio

from sanic.log import logger

from utils.converter import ConverterSubscribe


async def converter_subscribe_task(app):
    converter: ConverterSubscribe = app.ctx.converter
    await asyncio.sleep(3)
    i = 0
    while 1:
        is_force = False if i <= 0 else True
        logger.info(f'is_force: {is_force}')
        try:
            await converter.run(is_force)
        except Exception as e:
            logger.exception(e)
        finally:
            i += 1
            await asyncio.sleep(3600 * 12 + 60)
