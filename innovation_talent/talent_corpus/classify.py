# -*- coding: UTF-8 -*-
"""样本初步分类：国家奖学金获得者不等于创新型人才，先按成就类型分组再分析。

规则分类只看文本中的成就信号词：每句按命中的不同信号词计数（每句最多计 2 个），
具体事件句里的命中乘 2，其他句子乘 1，口号句不计。大模型编码时也会给出类型判断，
两者不一致的样本建议人工复核。
"""

from . import load_codebook, load_lexicon


def type_scores(doc, lexicon=None):
    lx = lexicon or load_lexicon()
    signals = lx['sample_type_signals']
    scores = {t: 0 for t in signals}
    sentences = doc.get('sentences')
    if not sentences:
        sentences = [{'text': doc.get('text', ''), 'kind': 'other'}]
    for s in sentences:
        if s['kind'] == 'rhetoric':
            continue
        w = 2 if s['kind'] == 'event' else 1
        for t, words in signals.items():
            hits = sum(1 for word in words if word in s['text'])
            scores[t] += w * min(hits, 2)
    return scores


def classify(doc, lexicon=None, codebook=None, min_score=2, min_innov=4):
    """返回 {primary, secondary, innovation, scores}。

    primary 需要得分不低于 min_score，否则记为 unclear。
    innovation 为 True 的条件：科研、科技竞赛或成果转化中任一类得分不低于 min_innov
    （约相当于两处事件句命中），且不低于最高分的一半。
    这样“成绩好、顺带参加过一次竞赛”的样本不会被归入创新型。
    """
    cb = codebook or load_codebook()
    scores = type_scores(doc, lexicon)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top = ranked[0][1]
    primary = ranked[0][0] if top >= min_score else 'unclear'
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] >= min_score \
        else ''
    innov_types = cb['innovation_types']
    innovation = any(scores[t] >= min_innov and scores[t] >= top / 2
                     for t in innov_types)
    return {'primary': primary, 'secondary': secondary,
            'innovation': innovation, 'scores': scores}
