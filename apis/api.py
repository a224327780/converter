import copy
import json
from pathlib import Path
from typing import Optional

import yaml
from aioredis import Redis
from sanic import Blueprint, Request, text
from sanic.log import logger

from utils.common import serializer
from utils.converter import ConverterSubscribe

subscribe_list_key = 'subscribe_list'
bp_api = Blueprint('api', url_prefix='/api')
dev_rule = [
    'DOMAIN-KEYWORD,qq,全局选择',
    'DOMAIN-KEYWORD,weixin,全局选择',
    'DOMAIN-KEYWORD,bilibili,全局选择',
    'DOMAIN-KEYWORD,aliyundrive,全局选择',
    'DOMAIN-KEYWORD,baidu,全局选择',
    'DOMAIN-KEYWORD,weibo,全局选择',
    'DOMAIN-KEYWORD,qlogo,全局选择',
    'DOMAIN-KEYWORD,qpic,全局选择',
    'DOMAIN-KEYWORD,hdslb,全局选择',
    'DOMAIN-KEYWORD,360.cn,全局选择'
]


@bp_api.get('/subscribe')
async def subscribe(request: Request):
    redis: Redis = request.app.ctx.redis
    is_dev = request.args.get('dev')
    test_url = 'http://www.gstatic.com/generate_204'

    p = Path(__file__).parent.parent / 'clash.yml'
    code = yaml.safe_load(p.read_text(encoding='utf-8'))
    provider_template = {'interval': 7200, 'url': '', 'type': 'http', 'path': '',
                         'health-check': {'enable': True, 'interval': 7200, 'url': test_url}}

    subscribe_list = await redis.hgetall(subscribe_list_key)
    if subscribe_list:
        code['proxy-providers'] = []
        code['proxy-groups'] = [
            {'name': '全局选择', 'type': 'select', 'proxies': ['故障转移', '自动选择', '机场节点']},
            {'name': '机场节点', 'type': 'select', 'proxies': []},
            {'name': '故障转移', 'type': 'fallback', 'proxies': [], 'interval': 7200,
             'url': test_url},
            {'name': '自动选择', 'type': 'url-test', 'use': [], 'interval': 7200,
             'url': test_url},
        ]
        _proxies_names = []
        _proxies = []
        for name, value in subscribe_list.items():
            logger.info(f'{name} {value}')
            provider = copy.deepcopy(provider_template)
            provider['url'] = request.url_for(f'api.convert', url=value)
            provider['path'] = f'provider/{name}.yaml'
            _proxies_names.append(name)
            _proxies.append({'name': name, 'type': 'select', 'use': [name]})
            code['proxy-providers'].append(provider)
        code['proxy-groups'].insert(2, _proxies)
        code['proxy-groups'][1]['proxies'] = _proxies_names
        code['proxy-groups'][3]['proxies'] = _proxies_names
        code['proxy-groups'][4]['use'] = _proxies_names
    if is_dev:
        code['rules'].extend(dev_rule)
    clash_data = yaml.dump(code, sort_keys=False, allow_unicode=True)
    return text(clash_data)


@bp_api.get('/subscribe_c')
async def subscribe_c(request: Request):
    return text('')


@bp_api.post('/subscribe')
@serializer()
async def subscribe_add(request: Request):
    redis: Redis = request.app.ctx.redis
    for key in request.form:
        v = request.form.getlist(key)
        if len(v) > 1:
            v = ','.join(v)
        else:
            v = v[0]
        key = key.replace('[]', '')
        await redis.hset(subscribe_list_key, key, v)
    return await redis.hgetall(subscribe_list_key)


@bp_api.get('/proxies')
async def proxies(request):
    redis: Redis = request.app.ctx.redis
    data = await redis.hgetall('subscribe_node')
    proxies_data = []
    for name, node in data.items():
        node = json.loads(node)
        logger.info(node)
        proxies_data.append(node)
    clash_data = yaml.dump({'proxies': proxies_data}, sort_keys=False, indent=2, allow_unicode=True)
    return text(clash_data)


@bp_api.get('/convert', name='convert')
@bp_api.get('/convert/<url:.+>', name='convert')
async def convert(request, url: str = Optional[None]):
    if not url:
        url = request.args.get('url')
    url = url.strip()
    data = await ConverterSubscribe(request.app.ctx.redis, request.app.ctx.request_session).providers(url)
    clash_data = yaml.dump({'proxies': data}, sort_keys=False, indent=2, allow_unicode=True)
    return text(clash_data)
