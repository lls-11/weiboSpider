# -*- coding: UTF-8 -*-
"""词典辅助特征。

只统计相关表述在“具体事件句”和“口号评价句”中各出现多少次，用作：
- 对照大模型编码（词典命中但模型未编码的样本值得人工复查）；
- 描述宣传文本的话语特点。
它不替代指标得分：宣传稿的用词首先反映作者，而不是人物本人。
"""

from .. import load_lexicon


def features(doc, lexicon=None):
    lx = lexicon or load_lexicon()
    cues = {k: v for k, v in lx['indicator_cues'].items()
            if not k.startswith('_')}
    out = {'doc_id': doc['doc_id'], 'person_id': doc.get('person_id', '')}
    chars = sum(len(s['text']) for s in doc['sentences']) or 1
    for iid, words in cues.items():
        ev = rh = 0
        for s in doc['sentences']:
            n = sum(s['text'].count(w) for w in words)
            if s['kind'] == 'event':
                ev += n
            elif s['kind'] == 'rhetoric':
                rh += n
        out[iid + '_event'] = ev
        out[iid + '_rhetoric'] = rh
        out[iid + '_per_k'] = round(ev * 1000 / chars, 3)
    for code, words in lx['local_code_cues'].items():
        out[code] = sum(s['text'].count(w) for s in doc['sentences']
                        for w in words)
    out.update({'n_sentences': doc['stats']['n_sentences'],
                'event_ratio': round(doc['stats']['event_ratio'], 3),
                'rhetoric_ratio': round(doc['stats']['rhetoric_ratio'], 3),
                'self_ratio': round(doc['stats']['self_ratio'], 3)})
    return out
