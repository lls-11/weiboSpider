# -*- coding: UTF-8 -*-
"""礼貌抓取：按站点限速、遵守 robots.txt、本地缓存原始网页。

原始网页缓存在 cache_dir 下，重复运行不会重复请求同一地址，
也便于日后用新的抽取规则重新解析。
"""

import hashlib
import logging
import os
import random
import re
import time
from urllib import robotparser
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('talent_corpus.fetch')

DEFAULT_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0 Safari/537.36 '
              'talent-corpus-research')

_META_CHARSET = re.compile(
    rb'<meta[^>]+charset=["\']?\s*([A-Za-z0-9_\-]+)', re.I)


def decode_html(content, header_encoding=None):
    """优先用网页 meta 声明的编码；GB2312/GBK 一律按 GB18030 解码。"""
    enc = None
    m = _META_CHARSET.search(content[:4096])
    if m:
        enc = m.group(1).decode('ascii', 'ignore').lower()
    elif header_encoding and header_encoding.lower() != 'iso-8859-1':
        enc = header_encoding.lower()
    if enc in ('gb2312', 'gbk', 'gb_2312-80', 'x-gbk'):
        enc = 'gb18030'
    for e in (enc, 'utf-8', 'gb18030'):
        if not e:
            continue
        try:
            return content.decode(e)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode('utf-8', 'replace')


class Fetcher:
    def __init__(self, cache_dir='talent_data/cache', delay=(2.0, 4.0),
                 timeout=20, respect_robots=True, user_agent=DEFAULT_UA):
        self.cache_dir = cache_dir
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self._last = {}
        self._robots = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        retry = Retry(total=3, backoff_factor=2,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=('GET', ))
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, url):
        h = hashlib.sha1(url.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, h[:2], h + '.html')

    def _allowed(self, url):
        if not self.respect_robots:
            return True
        p = urlparse(url)
        base = p.scheme + '://' + p.netloc
        if base not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.session.get(base + '/robots.txt', timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[base] = rp
        return self._robots[base].can_fetch(self.user_agent, url)

    def _wait(self, host):
        last = self._last.get(host)
        if last is not None:
            gap = random.uniform(*self.delay)
            remaining = last + gap - time.time()
            if remaining > 0:
                time.sleep(remaining)
        self._last[host] = time.time()

    def get(self, url, use_cache=True):
        """返回网页文本；404 或被 robots.txt 禁止时返回 None。"""
        if use_cache and self.cache_dir:
            cp = self._cache_path(url)
            if os.path.exists(cp):
                with open(cp, 'rb') as f:
                    return decode_html(f.read())
        if not self._allowed(url):
            logger.warning('robots.txt 不允许抓取，已跳过：%s', url)
            return None
        self._wait(urlparse(url).netloc)
        try:
            r = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as e:
            logger.warning('请求失败 %s：%s', url, e)
            return None
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            logger.warning('HTTP %s：%s', r.status_code, url)
            return None
        if use_cache and self.cache_dir:
            cp = self._cache_path(url)
            os.makedirs(os.path.dirname(cp), exist_ok=True)
            with open(cp, 'wb') as f:
                f.write(r.content)
        return decode_html(r.content, r.encoding)

    def get_json(self, url, params=None):
        self._wait(urlparse(url).netloc)
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()
