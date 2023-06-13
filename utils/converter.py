import asyncio
import json
import logging
import os
import re
from urllib.parse import urlparse

import pyquery
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

    async def run(self, force=False):
        subscribes = await self.redis.hgetall('subscribe_groups')
        if not subscribes:
            self.logger.warning('Please add a subscription.')
            return

        self.logger.info('Start to update subscribe.')
        subscribe_data = []
        for key, value in subscribes.items():
            # self.logger.info(f'Update {key} ...')
            for url in value.split(','):
                name_key = f'{self.subscribe_node_key}_{key}'
                data = await self.redis.exists(name_key)
                if data and not force and 'cjy.me' not in url:
                    continue

                self.logger.info(f'Downloading {url} ...')
                try:
                    if 'cjy.me' in url:
                        data = await self.get_node_list()
                        data = await self.parse_vmess('\n'.join(data))
                    else:
                        response = await self.fetch(url)
                        if not response:
                            continue
                        await self.redis.hdel(self.subscribe_url_fail_key, url)
                        html = await response.text()
                        data = await self.parse_subscribe(html)
                    if data:
                        await self.cache_providers(name_key, data)
                    subscribe_data.extend(data)
                except Exception as e:
                    self.logger.exception(f'<Error: {url} {e}>')
        self.logger.info('Finish to update subscribe.')

    async def cache_providers(self, key, data):
        await self.redis.delete(key)
        for item in data:
            name = item.get('name')
            if name and 'ipv6' in name:
                continue
            try:
                await self.redis.sadd(key, json.dumps(item, ensure_ascii=False))
            except Exception as e:
                self.logger.error(f'<Error: {e} {item}>')
        await self.redis.expire(key, 3600 * 6)

    async def convert_providers(self, url: str, is_force=None, name=None):
        result = []
        result_map = {}
        for _url in url.split(','):
            name_key = f'{self.subscribe_node_key}_{urlparse(_url).netloc}'
            if name:
                name_key = f'{self.subscribe_node_key}_{name}'
            # 优先取缓存
            if not is_force:
                items = await self.redis.smembers(name_key)
                if items:
                    for item in items:
                        result.append(json.loads(item))
                    result_map[name_key] = 1

            if not result_map.get(name_key):
                if 'cjy.me' in _url:
                    data = await self.get_node_list()
                    data = await self.parse_vmess('\n'.join(data))
                else:
                    response = await self.fetch(_url)
                    if not response:
                        continue

                    html = await response.text()
                    data = await self.parse_subscribe(html)
                if data:
                    await self.cache_providers(name_key, data)
                    result.extend(data)
                    result_map[name_key] = 1
        if result:
            result.sort(key=lambda k: (k.get('name', 0)))
        return result

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
            request_config.setdefault('timeout', 50)
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

    async def login(self, username, password):
        self.logger.info('start login.')
        base_url = 'https://share.cjy.me'
        login_url = f'{base_url}/mjj6/'
        response = await self.fetch(f'{base_url}/mjj6')
        html = await response.text()
        token_re = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
        token = token_re.group(1)
        params = {'csrfmiddlewaretoken': token, 'username': username, 'password': password}
        self.headers['Referer'] = login_url

        await asyncio.sleep(2)

        response = await self.fetch(login_url, data=params, allow_redirects=False)
        if 'location' in response.headers and 'userinfo' in response.headers['location']:
            cookie = [f"{k}={v.value}" for k, v in response.cookies.items()]
            return ';'.join(cookie)
        return None

    async def get_node_list(self):
        cookie_key = 'share_cjy_me_cookie'
        cookie = await self.redis.get(cookie_key)
        if not cookie:
            cookie = await self.login('caoyufei', 'hack3321')
            if not cookie:
                self.logger.error('<Error: login failed>')
                return []
            await self.redis.set(cookie_key, cookie, ex=3600 * 24)
        self.headers['Cookie'] = cookie

        response = await self.fetch(f'https://share.cjy.me/nodeinfo')
        if not response:
            await self.redis.delete(cookie_key)
            return []

        html = await response.text()
        doc = pyquery.PyQuery(html)
        nodes = doc('.node-cell').items()
        data = []
        for node in nodes:
            title_class = node.find('.card-header-title span').attr('class')
            if 'is-danger' in title_class:
                continue
            vmess = node.find('.modal a').attr('href')
            data.append(vmess)
        self.logger.info(f'cjy node {len(data)}')
        return data
