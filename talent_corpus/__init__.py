# -*- coding: UTF-8 -*-
"""创新人才识别模型的公开文本语料：采集、预处理、编码与分析。"""

import json
import os
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


@lru_cache(maxsize=None)
def load_codebook(path=None):
    with open(path or os.path.join(DATA_DIR, 'codebook.json'),
              encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load_lexicon(path=None):
    with open(path or os.path.join(DATA_DIR, 'lexicon.json'),
              encoding='utf-8') as f:
        return json.load(f)


def codable_indicators(levels=('高', '中'), codebook=None):
    """返回可观测性属于 levels 的指标编号列表。"""
    cb = codebook or load_codebook()
    return [i['id'] for i in cb['indicators'] if i['observability'] in levels]
