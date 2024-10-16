import asyncio
import copy
from pathlib import Path
from urllib.parse import quote, unquote

import yaml
from aioredis import Redis
from sanic import Blueprint, Request, text
from sanic.log import logger

from utils.common import serializer, to_yaml
from utils.converter import ConverterSubscribe

dev_rule = [
    'DOMAIN-KEYWORD,360.cn,全局选择',
    'DOMAIN-KEYWORD,hdslb,全局选择',
    'DOMAIN-KEYWORD,qpic,全局选择',
    'DOMAIN-KEYWORD,qlogo,全局选择',
    'DOMAIN-KEYWORD,weibo,全局选择',
    'DOMAIN-KEYWORD,baidu,全局选择',
    'DOMAIN-KEYWORD,aliyundrive,全局选择',
    'DOMAIN-KEYWORD,bilibili,全局选择',
    'DOMAIN-KEYWORD,weixin,全局选择',
    'DOMAIN-KEYWORD,qq,全局选择',
    'DOMAIN-KEYWORD,taobao,全局选择'
]

bp_api = Blueprint('api', url_prefix='/api')


@bp_api.get('/subscribe', name='get_subscribe')
async def get_subscribe(request: Request):
    redis: Redis = request.app.ctx.redis
    converter: ConverterSubscribe = request.app.ctx.converter

    is_dev = request.args.get('dev')
    test_url = 'http://www.gstatic.com/generate_204'

    p = Path(__file__).parent.parent / 'clash.yml'
    code = yaml.safe_load(p.read_text(encoding='utf-8'))
    provider_template = {
        'interval': 7200, 'url': '', 'type': 'http', 'path': '',
        'health-check': {'enable': True, 'interval': 7200, 'url': test_url}
    }

    subscribe_list = await redis.hgetall(converter.subscribe_key)
    if subscribe_list:
        code['proxy-providers'] = {}
        code['proxy-groups'] = [
            {'name': '全局选择', 'type': 'select', 'proxies': ['故障转移', '自动选择', '机场节点']},
            {'name': '机场节点', 'type': 'select', 'proxies': []},
            {'name': '故障转移', 'type': 'fallback', 'proxies': [], 'interval': 86400, 'url': test_url},
            {'name': '自动选择', 'type': 'url-test', 'use': [], 'interval': 86400, 'url': test_url},
        ]
        _proxies_names = []
        i = 2
        for name, value in subscribe_list.items():
            value = quote(value, safe='')
            provider = copy.deepcopy(provider_template)
            provider['url'] = request.url_for(f'api.convert', url=value, name=name)
            provider['path'] = f'provider/{name}.yaml'
            _proxies_names.append(name)
            code['proxy-providers'][name] = provider

            code['proxy-groups'].insert(i, {'name': name, 'type': 'select', 'use': [name]})
            i += 1
        code['proxy-groups'][1]['proxies'] = _proxies_names
        code['proxy-groups'][-2]['proxies'] = _proxies_names[0:3]
        code['proxy-groups'][-1]['use'] = _proxies_names[0:3]
    if is_dev:
        for rule in dev_rule:
            code['rules'].insert(0, rule)
    return text(to_yaml(code))


@bp_api.signal("subscribe.created.update")
async def update_subscribe(**context):
    logger.info('signal subscribe.created')
    force = context.get('force', False)
    await asyncio.sleep(1)
    await context['converter'].run(force)


@bp_api.post('/subscribe/save')
@serializer()
async def subscribe_save(request: Request):
    redis: Redis = request.app.ctx.redis
    converter: ConverterSubscribe = request.app.ctx.converter

    await redis.delete(converter.subscribe_key)

    for key, value in request.form.items():
        logger.info(f'{key}: {value}')
        await redis.hset(converter.subscribe_key, key, value[0])

    await request.app.dispatch("subscribe.created.update", context={'converter': converter})
    return await redis.hgetall(converter.subscribe_key)


@bp_api.get('/convert', name='convert')
async def convert_subscribe(request):
    url = request.args.get('url')
    name = request.args.get('name')
    if not url:
        return text('')

    is_force = request.args.get('force')
    url = unquote(url).strip()
    logger.info(url)
    converter: ConverterSubscribe = request.app.ctx.converter
    data = await converter.convert_providers(url, name, is_force)
    text_data = to_yaml({'proxies': data}) if data else ''
    return text(text_data)


@bp_api.get('/refresh')
@serializer()
async def refresh_subscribe(request):
    converter: ConverterSubscribe = request.app.ctx.converter
    await request.app.dispatch("subscribe.created.update", context={'converter': converter, 'force': True})
    return []


@bp_api.get('/proxy-pass')
async def proxy_pass(request):
    url = request.args.get('url')
    if not url:
        url = 'https://httpbin.org/ip'

    url = unquote(url).strip()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36'
    }

    html = ''
    try:
        response = await request.app.ctx.request_session.get(url, timeout=40, headers=headers, ssl=False)
        status_code = response.status
        html = await response.text()
    except Exception as e:
        status_code = 500
        logger.error(e)
    return text(html, status_code)
