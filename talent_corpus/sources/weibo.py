# -*- coding: UTF-8 -*-
"""衔接本仓库的微博爬虫：从 weibo_spider 的 CSV 结果中筛选人物事迹微博。

用法：先按 docs/settings.md 配置 weibo_spider，把高校官方微博、团委、
@中国大学生在线 等账号的 user_id 写入 user_id_list，运行
    python3 -m weibo_spider
得到 weibo/<账号>/<user_id>.csv 后，再用本模块按关键词与名录姓名筛选。
微博正文较短，主要用途是：(1) 找到“头条文章”长文地址，交给文章采集；
(2) 补充学生本人账号的第一人称表述。
"""

import csv
import glob
import os

from .. import corpus

DEFAULT_KEYWORDS = ('国家奖学金', '国奖', '年度人物', '特等奖学金', '五四奖章',
                    '自强之星', '学霸', '榜样')


def read_spider_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def collect(weibo_dir, keywords=DEFAULT_KEYWORDS, entries=None):
    """返回 (文档列表, 头条文章行列表)。

    entries 为名录条目（含 name、school、person_id）时，正文同时出现姓名与院校简称的
    微博会关联到该人物。
    """
    people = []
    for e in entries or []:
        short = e.get('school', '')[:4]
        people.append((e['name'], short, e.get('person_id', '')))
    docs, article_rows = [], []
    for path in glob.glob(os.path.join(weibo_dir, '*', '*.csv')):
        account = os.path.basename(os.path.dirname(path))
        for row in read_spider_csv(path):
            text = row.get('微博正文', '')
            matched = [p for p in people if p[0] in text and
                       (not p[1] or p[1] in text)]
            if not matched and not any(k in text for k in keywords):
                continue
            name, _, pid = matched[0] if matched else ('', '', '')
            url = 'https://weibo.cn/comment/' + row.get('微博id', '')
            docs.append(corpus.new_doc(
                'weibo', 'weibo', url, '', text, name=name, pid=pid or None,
                account=account, publish_time=row.get('发布时间', ''),
                matched_names=[p[0] for p in matched]))
            art = (row.get('头条文章url') or '').strip()
            if art:
                article_rows.append({'url': art, 'name': name, 'school': '',
                                     'corpus': 'weibo_article',
                                     'source_type': 'news', 'person_id': pid,
                                     'note': 'from ' + account})
    return docs, article_rows
