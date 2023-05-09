import base64
import hashlib
import math
from datetime import timezone, timedelta, datetime
from functools import wraps
from inspect import isawaitable

import yaml
from sanic import HTTPResponse, Request, response
from sanic.response import ResponseStream


def b64(code):
    code = code.ljust(int(math.ceil(len(code) / 4)) * 4, '=')
    try:
        return base64.b64decode(code)
    except ValueError:
        return None


def vmess_to_clash(vmess_data):
    tls = vmess_data.get('tls')
    tls = False if not tls or tls == 'none' else True
    network = vmess_data['net']
    data = {
        "name": vmess_data['ps'],
        "server": vmess_data['add'],
        "port": vmess_data['port'],
        "type": "vmess",
        "uuid": vmess_data['id'],
        "alterId": vmess_data['aid'],
        "cipher": "auto",
        "tls": tls,
        "skip-cert-verify": True,
    }
    if network == 'ws':
        host = vmess_data['host']
        if not host or host == 'none':
            host = vmess_data['add']
        data['network'] = network
        data['ws-opts'] = {
            "path": vmess_data['path'],
            "headers": {
                "Host": host
            }
        }
    return data


def to_yaml(data):
    return yaml.dump(data, sort_keys=False, allow_unicode=True)


def get_bj_date(add_seconds=None, fmt='%Y-%m-%d %H:%M:%S'):
    sh_tz = timezone(
        timedelta(hours=8),
        name='Asia/Shanghai',
    )
    utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    bj_now = utc_dt.astimezone(sh_tz)
    if add_seconds:
        bj_now += timedelta(seconds=add_seconds)
    return bj_now.strftime(fmt)


def get_utc_date():
    utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    return utc_dt.strftime('%Y-%m-%d %H:%M:%S')


def md5(string: str):
    m = hashlib.md5()
    m.update(string.encode('utf-8'))
    _md5 = m.hexdigest()
    return _md5[8:-8].upper()


def diff_date_seconds(last_date):
    a = datetime.strptime(last_date, '%Y-%m-%d %H:%M:%S')
    b = datetime.strptime(get_bj_date(), '%Y-%m-%d %H:%M:%S')
    return (b - a).seconds


def get_uptime(last_date, uptime=0):
    return diff_date_seconds(last_date) + uptime


def format_date(last_date):
    s = diff_date_seconds(last_date)
    if s <= 0:
        s = 1
    date_name = ['seconds ago', 'minutes ago', 'hours ago']
    i = int(math.floor(math.log(s, 60)))
    if i > len(date_name):
        return last_date

    p = math.pow(60, i)
    return f'{int(s / p)} {date_name[i]}'


def format_uptime(uptime):
    s = int(uptime) / 3600
    if s < 1:
        return f'{int(s * 60)}分钟'
    if s < 24:
        return f'{int(s)}小时'
    return f'{int(s / 24)}天'


def success(data=None, message=''):
    if not data:
        data = []
    return {'code': 0, 'msg': message, 'data': data}


def fail(message='', data=None, code=1):
    if not data:
        data = []
    return {'code': code, 'msg': message, 'data': data}


def serializer():
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            retval = f(*args, **kwargs)
            if isawaitable(retval):
                retval = await retval
            if type(retval) in [HTTPResponse, ResponseStream]:
                return retval
            if type(retval) != dict or not retval.get('code'):
                retval = success(retval)
            if isinstance(args[0], Request):
                _request: Request = args[0]
                # retval['request-id'] = _request.headers
            return response.json(retval)

        return decorated_function

    return decorator
