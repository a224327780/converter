import copy
from pathlib import Path
from urllib.parse import quote, unquote

import yaml
from aioredis import Redis
from sanic import Blueprint, Request, text
from sanic.log import logger

from utils.common import serializer, to_yaml
from utils.converter import ConverterSubscribe

subscribe_groups_key = 'subscribe_groups'

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
    provider_template = {
        'interval': 7200, 'url': '', 'type': 'http', 'path': '',
        'health-check': {'enable': True, 'interval': 7200, 'url': test_url}
    }

    subscribe_list = await redis.hgetall(subscribe_groups_key)
    if subscribe_list:
        code['proxy-providers'] = []
        code['proxy-groups'] = [
            {'name': '全局选择', 'type': 'select', 'proxies': ['故障转移', '自动选择', '机场节点']},
            {'name': '机场节点', 'type': 'select', 'proxies': []},
            {'name': '故障转移', 'type': 'fallback', 'proxies': [], 'interval': 7200, 'url': test_url},
            {'name': '自动选择', 'type': 'url-test', 'use': [], 'interval': 7200, 'url': test_url},
        ]
        _proxies_names = []
        _proxies = []
        for name, value in subscribe_list.items():
            value = quote(value, safe='')
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
    return text(to_yaml(code))


@bp_api.route('/subscribes', methods=['GET', 'POST'])
@serializer()
async def subscribe_groups(request: Request):
    redis: Redis = request.app.ctx.redis
    if request.method == 'POST':
        for key in request.form:
            v = request.form.getlist(key)
            if len(v) > 1:
                v = ','.join(v)
            else:
                v = v[0]
            key = key.replace('[]', '')
            await redis.hset(subscribe_groups_key, key, v)
    return await redis.hgetall(subscribe_groups_key)


@bp_api.get('/convert', name='convert')
async def convert(request):
    url = request.args.get('url').strip()
    is_force = request.args.get('force')

    url = unquote(url)
    converter = ConverterSubscribe(request.app.ctx.redis, request.app.ctx.request_session)
    data = await converter.convert_providers(url, is_force)
    text_data = to_yaml({'proxies': data}) if data else ''
    return text(text_data)
