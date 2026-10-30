# -*- coding: UTF-8 -*-

"""检查能否调通中转站 codego（或 DeepSeek 官方等 OpenAI 兼容接口）。只发一句很短的请求，几乎不花钱。

在 PyCharm 里：右键本文件 → Run 'check_api'；或在终端运行  python check_api.py
要换模型或地址，改下面两行，或在终端运行  python check_api.py --model 模型名 --base-url 地址
想试遍中转站目录里的所有模型：python check_api.py --scan（每个模型只花几十个 token）

密钥（任选一种）：
1. 环境变量 CODEGO_API_KEY（PyCharm：Run → Edit Configurations → Environment variables）；
2. 在 innovation_talent/talent_data/ 下新建 codego_key.txt，里面只写密钥一行（这个目录不会提交到 GitHub）。
用 DeepSeek 官方时把 PROVIDER 改为 'deepseek'，对应 DEEPSEEK_API_KEY / deepseek_key.txt。

几种失败的含义（脚本会自己判断并打印）：
401 密钥无效；402 余额不足；404 地址不对；
503 + code=model_not_found：密钥能过鉴权，但它所在的分组没有任何可用渠道
（先用 /v1/models 看密钥可见的模型：返回空列表就是这个原因），到中转站控制台改令牌分组。
"""
import argparse
import json
import os
import sys

PROVIDER = 'codego'
MODEL = 'deepseek-v4-flash'              # 不对时，运行后看打印出的模型列表，改成其中的 DeepSeek 名称
BASE_URL = 'https://codegoai.com/v1'

HINTS = {
    401: '密钥不对或没有生效：检查环境变量或 talent_data/ 下的密钥文件',
    402: '账户余额不足，请到控制台充值',
    403: '密钥没有该模型的权限：检查令牌的分组（group）',
    404: '接口地址不对：检查 --base-url（DeepSeek 官方为 https://api.deepseek.com）',
    422: '请求参数不被接受，多半是模型名不对',
    429: '请求太频繁或额度受限，稍后再试，正式运行时把 --workers 调小',
    503: '网关返回“模型服务暂不可用”。密钥能通过鉴权（否则会是 401），'
         '说明它所在的分组没有任何可用渠道：到中转站控制台把令牌的分组改成有渠道的分组'
         '（本中转站目录里的 free、CN-Model-… 等），或改用官方 DeepSeek。',
}


def origin_of(base):
    """https://host/v1 → https://host（中转站的公开目录 /api/pricing 在根路径下）。"""
    return base.rstrip('/')[:-3].rstrip('/') if base.rstrip('/').endswith('/v1') else base.rstrip('/')


def token_models(requests, base, headers):
    """GET /v1/models：该密钥当前可用的模型名。返回 (列表或 None, 状态码)。

    空列表＝这个令牌的分组里没有任何可用渠道，此时任何模型名都会报
    “model_not_found / 当前模型服务暂不可用”。
    """
    try:
        r = requests.get(base + '/models', headers=headers, timeout=30)
        if r.status_code != 200:
            return None, r.status_code
        return [m.get('id') for m in (r.json().get('data') or [])], 200
    except (requests.RequestException, ValueError, AttributeError):
        return None, None


def catalog(requests, base):
    """公开的 /api/pricing：中转站现在有哪些模型、各自开放给哪些分组。不需要密钥。"""
    try:
        r = requests.get(origin_of(base) + '/api/pricing', timeout=30)
        return (r.json().get('data') or []) if r.status_code == 200 else []
    except (requests.RequestException, ValueError, AttributeError):
        return []


def print_catalog(requests, base):
    rows = catalog(requests, base)
    if not rows:
        print('（该地址没有公开的模型目录 /api/pricing，直接到控制台看模型列表）')
        return []
    names = []
    print('该地址目录里的模型（★＝开放给 free 分组，可以先试这些）：')
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = item.get('model_name') or item.get('model')
        groups = item.get('enable_groups') or []
        star = '★' if 'free' in groups else ' '
        names.append(name)
        print('  %s %-24s 分组 %d 个：%s' % (
            star, name, len(groups), ', '.join(groups[:4]) + ('…' if len(groups) > 4 else '')))
    return [n for n in names if n]


def list_models(requests, base, headers):
    """打印该密钥可见的模型（/v1/models）；失败时退回公开目录。"""
    names, code = token_models(requests, base, headers)
    if names is None:
        print('该密钥看不到模型列表（/v1/models 返回 %s）。' % code)
        return []
    if not names:
        print('该密钥可见的模型：0 个 —— 令牌所在分组没有任何可用渠道，这就是连不上的原因。')
        return []
    ds = [n for n in names if 'deepseek' in str(n).lower()]
    print('该密钥可见的模型（含 deepseek 的）：', ds or '（没有含 deepseek 的模型）')
    print('全部模型共 %d 个：%s' % (len(names), ', '.join(map(str, names[:60]))))
    return names


def try_model(requests, base, headers, model, verbose=False):
    """对单个模型发一句很短的请求，返回 (是否成功, 状态码, 说明文本)。"""
    body = {'model': model, 'max_tokens': 50, 'temperature': 0,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'user', 'content': '请只输出 JSON：{"ok": true}'}]}
    try:
        r = requests.post(base + '/chat/completions', headers=headers, json=body, timeout=120)
    except requests.RequestException as e:
        return False, None, '连不上接口：%s' % e
    if r.status_code == 200:
        data = r.json()
        text = ((data.get('choices') or [{}])[0].get('message') or {}).get('content', '')
        note = '成功，实际作答模型：%s；回复：%s' % (data.get('model'), text.strip()[:200])
        if verbose:
            note += '；用量：' + json.dumps(data.get('usage'), ensure_ascii=False)
        return True, 200, note
    return False, r.status_code, ' '.join(r.text.split())[:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', default=PROVIDER)
    ap.add_argument('--model', default=MODEL)
    ap.add_argument('--base-url', default=BASE_URL)
    ap.add_argument('--scan', action='store_true',
                    help='把该地址目录里的模型逐个试一遍，找出能用的那个')
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    from talent_corpus.coding.person import PROVIDERS, read_key_file

    print('Python:', sys.version.split()[0])
    try:
        import requests
    except ImportError:
        print('失败：缺少 requests，请运行  pip install requests')
        return 1
    env = PROVIDERS[args.provider][1]
    key = os.environ.get(env) or read_key_file(args.provider)
    if not key:
        print('失败：没有找到密钥。设置环境变量 %s，或新建 talent_data/%s_key.txt 写入密钥。'
              % (env, args.provider))
        return 1
    print('密钥：已找到（%s…%s）' % (key[:5], key[-4:]))
    base = args.base_url.rstrip('/')
    print('地址：%s    模型：%s' % (base, args.model))

    headers = {'Authorization': 'Bearer ' + key}
    visible = list_models(requests, base, headers)

    if args.scan:
        names = visible or print_catalog(requests, base) or [args.model]
        print('\n逐个试 %d 个模型……' % len(names))
        ok = []
        for m in names:
            good, code, note = try_model(requests, base, headers, m, verbose=True)
            print('  %-28s %s %s' % (m, '可用' if good else '不可用', note))
            if good:
                ok.append(m)
        print('\n能用的模型：', ok or '一个都不能用（见上面的状态码与提示）')
        return 0 if ok else 1

    body_ok, status, note = try_model(requests, base, headers, args.model, verbose=True)
    if body_ok:
        if base != args.base_url.rstrip('/'):
            print('注意：可用的地址是 %s，正式运行时请用这个地址。' % base)
        print(note)
        print('\n可以开始正式运行，例如：\n  python -m talent_corpus person-code --provider %s '
              '--model %s --base-url %s --subset cn_report,cn_first_person --limit 20'
              % (args.provider, args.model, base))
        return 0

    print('HTTP 状态码：', status)
    if status in (404, 405) and not base.endswith('/v1'):
        print('地址 %s 返回 %s，改用 %s/v1 重试……' % (base, status, base))
        base += '/v1'
        body_ok, status, note = try_model(requests, base, headers, args.model)
        if body_ok:
            print('成功（地址应为 %s）：%s' % (base, note))
            return 0
        print('HTTP 状态码：', status)
    print('失败：', HINTS.get(status, '见下方返回内容'))
    if status == 400:
        print('（400 多半是模型名不对，或该模型不支持 JSON 模式；模型名以控制台为准）')
    if status == 503:
        print('（--scan 可以把目录里的模型逐个试一遍，看是否只是个别模型没渠道）')
    print('返回内容：', note)
    if status != 401:
        print()
        print_catalog(requests, base)
    return 1


if __name__ == '__main__':
    sys.exit(main())
