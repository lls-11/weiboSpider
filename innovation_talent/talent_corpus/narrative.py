# -*- coding: UTF-8 -*-
"""区分“叙事文本”与“成就清单”，只把叙事文本纳入指标编码。

研究组约定：只陈列奖项、论文、荣誉的文本不做文本分析（成就数量可另作校标，
见 criteria.py）。判别依据是有没有过程性描写：本人做了什么、遇到了什么、
怎样调整。规则如下：
- 过程句：出现过程标记词（尝试、失败、调整、发现、请教、当时……）且不是口号句；
- 强过程句：同一句出现两个以上不同的过程标记词；
- 至少 1 个强过程句，或至少 2 个过程句，判为叙事文本（narrative），否则为成就清单（list_only）。
标记词表是可改的初始版本，用人工判断过的样本校准（见 tests）。
"""

import re

from . import load_lexicon
from .preprocess import split_sentences

PROCESS_MARKERS = (
    # 行动与调整
    '尝试', '试了', '试过', '失败', '拒稿', '被拒', '落选', '重新', '重做', '重写', '反复',
    '调整', '改用', '改为', '转向', '转而', '换了', '放弃', '推翻', '摸索', '迭代', '修改',
    '调试', '搭建', '推导', '设计了', '验证', '复盘',
    # 发现与判断
    '发现', '意识到', '注意到', '决定', '选择了', '怀疑', '质疑', '思考', '启发', '灵感',
    '想到', '想法',
    # 求助与交流
    '请教', '联系了', '主动联系', '写信', '邮件', '讨论',
    # 困难
    '困惑', '迷茫', '焦虑', '难以', '无从下手', '瓶颈', '卡住', '挫折', '不顺', '失误', '困难', '堵点',
    # 时间经过
    '当时', '起初', '刚开始', '刚进', '后来', '第一次', '那段时间', '那时', '回忆', '记得',
)
_ACHIEVE = re.compile(r'(获|荣获|曾获|获评|获得|入选|发表|授权|论文|专利|称号|奖|担任|任)')


def assess(text, lexicon=None):
    lx = lexicon or load_lexicon()
    cliches = lx['cliches']
    n_process = n_strong = n_achieve = 0
    sentences = split_sentences(text, 'zh')
    for s in sentences:
        hits = {m for m in PROCESS_MARKERS if m in s}
        cliche = any(c in s for c in cliches)
        if hits and not (cliche and len(hits) < 2) and len(s) >= 12:
            n_process += 1
            if len(hits) >= 2:
                n_strong += 1
        elif _ACHIEVE.search(s):
            n_achieve += 1
    narrative = n_strong >= 1 or n_process >= 2
    return {
        'text_type': 'narrative' if narrative else 'list_only',
        'n_sentences': len(sentences),
        'n_process': n_process,
        'n_strong_process': n_strong,
        'n_achievement': n_achieve,
    }
