import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import yaml
from aioredis import Redis

from utils.common import b64, vmess_to_clash


class ConverterSubscribe:

    def __init__(self, redis: Redis, request_session):
        self.redis = redis
        self.request_session = request_session
        self.logger = logging.getLogger('sanic.root')
        self.headers = {'User-Agent': 'ClashMetaForAndroid/2.7.1.Meta-Alpha (Prefer ClashMeta Format)'}
        self.subscribe_url_fail_key = 'subscribe_groups_fail'
        self.subscribe_node_key = 'subscribe_node'

    async def run(self):
        subscribes = await self.redis.hgetall('subscribe_groups')
        if not subscribes:
            self.logger.warning('Please add a subscription.')
            return

        subscribe_data = []
        for key, value in subscribes.items():
            for url in value.split(','):
                name_key = f'{self.subscribe_node_key}_{urlparse(url).netloc}'
                data = await self.redis.hgetall(name_key)
                if data:
                    continue

                self.logger.info(f'Downloading {url} ...')
                try:
                    response = await self.fetch(url)
                    if not response:
                        self.logger.error(url)
                        await self.subscribe_fail(key, value, url)
                        continue

                    await self.redis.hdel(self.subscribe_url_fail_key, url)
                    html = await response.text()
                    data = await self.parse_subscribe(html)
                    if data:
                        await self.cache_providers(name_key, data)
                    subscribe_data.extend(data)
                except Exception as e:
                    self.logger.exception(f'<Error: {url} {e}>')

    async def cache_providers(self, name_key, data):
        await self.redis.delete(name_key)
        for item in data:
            await self.redis.hset(name_key, item['name'], json.dumps(item, ensure_ascii=False))

    async def convert_providers(self, url: str):
        result = []
        for _url in url.split(','):
            # name = urlparse(url).netloc
            # key = f'{self.subscribe_node_key}_{name}'
            # data = await self.redis.hgetall(key)
            response = await self.fetch(_url)
            if not response:
                return []

            html = await response.text()
            data = await self.parse_subscribe(html)
            if data:
                result.extend(data)
        return result

    async def parse_subscribe(self, html):
        if 'proxies' in html:
            data = yaml.safe_load(html)
            return data['proxies']
        if '<html' not in html:
            html = b64(html).decode('utf-8')
            if 'vmess' in html:
                return await self.parse_vmess(html)
        return []

    async def parse_vmess(self, html):
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

            node = json.loads(node.decode('utf-8'))
            node = vmess_to_clash(node)
            data.append(node)
        return data

    async def subscribe_fail(self, name: str, value: str, url: str):
        fail_count = await self.redis.hset(self.subscribe_url_fail_key, url)
        if not fail_count:
            fail_count = 0

        fail_count = int(fail_count) + 1
        if fail_count >= 48:
            value = value.replace(url, '').strip(',')
            await self.redis.hset('subscribe_groups', name, value)
            await self.redis.hdel(self.subscribe_url_fail_key, url)
            await self.notify(f'🔴<b>订阅被删除</b>\n\n{url}')
            return
        await self.redis.hset(self.subscribe_url_fail_key, url, fail_count)

    async def fetch(self, url: str, method='GET', **request_config):
        try:
            request_config.setdefault('ssl', False)
            request_config.setdefault('timeout', 20)
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

    async def notify(self, message, chat_id='-1001835884416'):
        key = os.getenv('API_KEY')
        api = f'https://api.telegram.org/bot{key}/sendMessage'
        data = {'text': message, 'chat_id': chat_id, 'parse_mode': 'HTML'}
        return await self.fetch(api, data=data)
