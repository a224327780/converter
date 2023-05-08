import json
import logging

import yaml
from aioredis import Redis

from utils.common import b64, vmess_to_clash


class ConverterSubscribe:

    def __init__(self, redis: Redis, request_session):
        self.redis = redis
        self.request_session = request_session
        self.logger = logging.getLogger('sanic.root')
        self.headers = {'User-Agent': 'ClashMetaForAndroid/2.7.1.Meta-Alpha (Prefer ClashMeta Format)'}
        self.subscribe_url_fail_key = 'subscribe_url_fail'
        self.subscribe_node_key = 'subscribe_node'

    async def run(self):
        subscribes = await self.redis.hgetall('subscribe_url')
        if not subscribes:
            self.logger.warning('Please add a subscription.')
            return

        subscribe_data = []
        for name, url in subscribes.items():
            self.logger.info(f'Downloading {url} ...')
            try:
                response = await self.fetch(url)
                if not response.ok:
                    await self.subscribe_fail(name)
                    continue

                await self.redis.hdel(self.subscribe_url_fail_key, name)
                html = await response.text()
                data = await self.parse_subscribe(html)
                subscribe_data.extend(data)
            except Exception as e:
                self.logger.error(f'<Error: {url} {e}>')
        self.logger.info(len(subscribe_data))

        if subscribe_data:
            await self.redis.delete(self.subscribe_node_key)
            for item in subscribe_data:
                self.logger.info(item['name'])
                await self.redis.hset(self.subscribe_node_key, item['name'], json.dumps(item, ensure_ascii=False))
            self.logger.info('done')

    async def providers(self, url):
        response = await self.fetch(url)
        if not response.ok:
            return []
        html = await response.text()
        return await self.parse_subscribe(html)

    async def parse_subscribe(self, html):
        if 'proxies' in html:
            data = yaml.safe_load(html)
            return data['proxies']

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

    async def subscribe_fail(self, name):
        fail_count = await self.redis.hset(self.subscribe_url_fail_key, name)
        if not fail_count:
            fail_count = 0
        fail_count = int(fail_count) + 1
        if fail_count >= 5:
            await self.redis.hdel('subscribe_url', name)
            return
        await self.redis.hset(self.subscribe_url_fail_key, name, fail_count)

    async def fetch(self, url: str, method='GET', **request_config):
        request_config.setdefault('ssl', False)
        request_config.setdefault('timeout', 20)
        request_config.setdefault('headers', self.headers)
        if 'data' in request_config or 'json' in request_config:
            method = 'POST'
        return await self.request_session.request(method, url, **request_config)
