# -*- coding: UTF-8 -*-
"""检查能否调通中转站 codego（或 DeepSeek 官方等 OpenAI 兼容接口）。只发一句很短的请求，几乎不花钱。

在 PyCharm 里：右键本文件 → Run 'check_api'；或在终端运行  python check_api.py
要换模型或地址，改下面两行，或在终端运行  python check_api.py --model 模型名 --base-url 地址

密钥（任选一种）：
1. 环境变量 CODEGO_API_KEY（PyCharm：Run → Edit Configurations → Environment variables）；
2. 在 innovation_talent/talent_data/ 下新建 codego_key.txt，里面只写密钥一行（这个目录不会提交到 GitHub）。
用 DeepSeek 官方时把 PROVIDER 改为 'deepseek'，对应 DEEPSEEK_API_KEY / deepseek_key.txt。
"""
import argparse
import json
import os
import sys

PROVIDER = 'codego'
MODEL = 'deepseek-v4'              # 不对时，运行后看打印出的模型列表，改成其中的 DeepSeek V4 名称
BASE_URL = 'https://codegoai.com/v1'

HINTS = {
    401: '密钥不对或没有生效：检查环境变量或 talent_data/ 下的密钥文件',
    402: '账户余额不足，请到 DeepSeek 控制台充值',
    404: '接口地址不对：检查 --base-url（DeepSeek 官方为 https://api.deepseek.com）',
    422: '请求参数不被接受，多半是模型名不对',
    429: '请求太频繁或额度受限，稍后再试，正式运行时把 --workers 调小',
}


def list_models(requests, base, headers):
    """多数中转站支持 GET /models：列出可用模型名，方便核对 --model。"""
    try:
        r = requests.get(base + '/models', headers=headers, timeout=30)
        names = [m.get('id') for m in r.json().get('data', [])] if r.status_code == 200 else []
    except (requests.RequestException, ValueError, AttributeError):
        names = []
    if names:
        ds = [n for n in names if 'deepseek' in str(n).lower()]
        print('该地址可用的模型（含 deepseek 的）：', ds or '（没有含 deepseek 的模型）')
        print('全部模型共 %d 个：%s' % (len(names), ', '.join(map(str, names[:60]))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', default=PROVIDER)
    ap.add_argument('--model', default=MODEL)
    ap.add_argument('--base-url', default=BASE_URL)
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
    print('地址：%s    模型：%s' % (args.base_url, args.model))

    body = {'model': args.model, 'max_tokens': 50, 'temperature': 0,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'user', 'content': '请只输出 JSON：{"ok": true}'}]}
    base = args.base_url.rstrip('/')
    headers = {'Authorization': 'Bearer ' + key}
    try:
        r = requests.post(base + '/chat/completions', headers=headers, json=body, timeout=60)
        if r.status_code in (404, 405) and not base.endswith('/v1'):
            print('地址 %s 返回 %d，改用 %s/v1 重试……' % (base, r.status_code, base))
            base += '/v1'
            r = requests.post(base + '/chat/completions', headers=headers, json=body, timeout=60)
    except requests.RequestException as e:
        print('失败：连不上接口。检查网络、代理或 --base-url。\n详细：', e)
        return 1
    print('HTTP 状态码：', r.status_code)
    if r.status_code != 200:
        list_models(requests, base, headers)
        print('失败：', HINTS.get(r.status_code, '见下方返回内容'))
        if r.status_code == 400:
            print('（400 多半是模型名不对，或该模型不支持 JSON 模式；模型名以控制台为准）')
        print('返回内容：', r.text[:500])
        return 1
    data = r.json()
    if base != args.base_url.rstrip('/'):
        print('注意：可用的地址是 %s，正式运行时请用这个地址。' % base)
    print('成功！实际作答的模型：', data.get('model'))
    print('模型回复：', data['choices'][0]['message']['content'])
    print('用量：', json.dumps(data.get('usage'), ensure_ascii=False))
    print('\n可以开始正式运行，例如：\n  python -m talent_corpus person-code --provider %s '
          '--model %s --base-url %s --subset cn_report,cn_first_person --limit 20'
          % (args.provider, args.model, base))
    return 0


if __name__ == '__main__':
    sys.exit(main())
