import asyncio
import json
import logging
import os

import yaml
from aioredis import Redis

from utils.common import b64, vmess_to_clash


class ConverterSubscribe:

    def __init__(self, redis: Redis, request_session):
        self.redis = redis
        self.request_session = request_session
        self.logger = logging.getLogger('sanic.root')
        self.headers = {'User-Agent': 'clash-verge/v1.6.6.Meta'}
        self.subscribe_node_key = 'subscribe_node'
        self.subscribe_key = 'subscribes'

    async def init_subscribe(self):
        await self.redis.delete(self.subscribe_key)

    async def run(self, force=False):
        subscribes = await self.redis.hgetall(self.subscribe_key)
        if not subscribes:
            self.logger.warning('Please add a subscription.')
            return

        self.logger.info('Start to update subscribe.')
        for name, url in subscribes.items():
            data = await self.redis.hget(self.subscribe_node_key, name)
            if data and not force:
                self.logger.info(name)
                continue

            self.logger.info(f'Downloading {url}')
            try:
                response = await self.fetch(url)
                if not response:
                    continue

                html = await response.text()
                data = await self.parse_subscribe(html)
                if data:
                    await self.redis.hset(self.subscribe_node_key, name, json.dumps(data, ensure_ascii=False))
            except Exception as e:
                self.logger.exception(f'<Error: {url} {e}>')
        self.logger.info('Finish to update subscribe.')

    async def convert_providers(self, url: str, name: str, is_force=None):
        # 优先取缓存
        if not is_force:
            data = await self.redis.hget(self.subscribe_node_key, name)
            data = json.loads(data)
        else:
            response = await self.fetch(url)
            if not response:
                return None

            html = await response.text()
            data = await self.parse_subscribe(html)
            if data:
                await self.redis.hset(self.subscribe_node_key, name, json.dumps(data, ensure_ascii=False))
        if data and isinstance(data, list):
            data.sort(key=lambda k: (k.get('name', 0)))
        return data

    async def parse_subscribe(self, html):
        if 'proxies' in html:
            data = yaml.safe_load(html)
            return data['proxies']
        if '<html' not in html:
            html = b64(html)
            if 'vmess' in html:
                return await self.parse_vmess(html)
        return []

    async def parse_vmess(self, html) -> list:
        node_items = html.split('\n')
        data = []
        for node_item in node_items:
            if 'vmess' not in node_item:
                continue

            node_item = node_item.replace('vmess://', '')
            node = b64(node_item)
            if not node:
                self.logger.warning(f'<Error: {node_item} >')
                continue

            node = json.loads(node)
            node = vmess_to_clash(node)
            data.append(node)
        return data

    async def fetch(self, url: str, method='GET', **request_config):
        try:
            request_config.setdefault('ssl', False)
            request_config.setdefault('timeout', 30)
            request_config.setdefault('headers', self.headers)
            if 'data' in request_config or 'json' in request_config:
                method = 'POST'
            response = await self.request_session.request(method, url, **request_config)
            if not response.ok:
                self.logger.error(f"<Error: {url} {response.status}>")
                return None
            return response
        except asyncio.TimeoutError:
            self.logger.error(f"<Error: {url} Timeout>")
        except Exception as e:
            self.logger.error(f"<Error: {url} {e}>")
        return None
