# -*- coding: UTF-8 -*-
"""预处理：分句、区分“具体事件句”与“口号评价句”、标注叙述归属与人生时期。

这些规则是轻量启发式，作用有二：
1. 给编码员和大模型提供句子编号与时期线索；
2. 计算文档的刻板叙事比例，用于样本筛选与偏差分析。
指标得分不由这里产生。
"""

import re

from . import load_lexicon

_ZH_SPLIT = re.compile(r'([^。！？；!?\n]*[。！？；!?]+[”’」』）)]*|[^。！？；!?\n]+)')
_EN_SPLIT = re.compile(r'(?<=[.!?])["”\']?\s+(?=[A-Z"“])')
# 缩写与姓名首字母（Willard S. Boyle、U.S. Navy）后的句点不是句末
_EN_ABBR = re.compile(r'(\b(Dr|Mr|Mrs|Ms|Prof|St|Jr|Sr|vs|e\.g|i\.e|cf|Fig|No|Inc|Co|Ltd|Ph\.D|U\.S|U\.K)'
                      r'|(^|[\s(])[A-Z])\.$')


def detect_lang(text):
    han = sum(1 for ch in text[:2000] if '一' <= ch <= '鿿')
    return 'zh' if han >= 20 else 'en'


def split_sentences(text, lang=None):
    lang = lang or detect_lang(text)
    out = []
    for para in text.split('\n'):
        para = para.strip()
        if not para:
            continue
        if lang == 'zh':
            parts = [m.group(0).strip() for m in _ZH_SPLIT.finditer(para)]
        else:
            parts, buf = [], ''
            for piece in _EN_SPLIT.split(para):
                buf = (buf + ' ' + piece).strip() if buf else piece
                if not _EN_ABBR.search(buf):
                    parts.append(buf)
                    buf = ''
            if buf:
                parts.append(buf)
        out.extend(p for p in parts if len(p) >= 2)
    return out


class Tagger:
    def __init__(self, lexicon=None):
        lx = lexicon or load_lexicon()
        self.cliches = {'zh': lx['cliches'], 'en': lx.get('cliches_en', [])}
        self.evaluative = lx['evaluative_terms']
        self.markers = {
            'zh': {k: re.compile(v) for k, v in lx['event_markers'].items()},
            'en': {k: re.compile(v, re.I if k != 'first_person' else 0)
                   for k, v in lx['event_markers_en'].items()},
        }
        self.periods = {
            'zh': [(k, re.compile(v))
                   for k, v in lx['life_period_patterns'].items()],
            'en': [(k, re.compile(v, re.I))
                   for k, v in lx['life_period_patterns_en'].items()],
        }
        am = lx['attribution_markers']
        self.quote_open = re.compile(am['quote_open'])
        self.speech = re.compile(am['speech_verbs'])
        self.roles = re.compile(am['other_roles'])

    def tag(self, sentence, lang):
        m = self.markers[lang]
        hits = {k: bool(rx.search(sentence)) for k, rx in m.items()}
        event_score = sum(hits[k] for k in ('time', 'quantity', 'action',
                                            'artifact'))
        cliches = [c for c in self.cliches[lang] if c.lower() in
                   sentence.lower()]
        evaluative = lang == 'zh' and any(t in sentence for t in
                                          self.evaluative)
        if event_score >= 2 or (hits['action'] and hits['first_person']):
            kind = 'event'
        elif cliches or (evaluative and event_score == 0):
            kind = 'rhetoric'
        else:
            kind = 'other'
        return {'kind': kind, 'event_score': event_score, 'cliches': cliches,
                'first_person': hits['first_person'],
                'attribution': self.attribution(sentence, lang, hits)}

    def attribution(self, sentence, lang, hits):
        if lang == 'en':
            return 'self' if hits['first_person'] else 'narrator'
        quoted = bool(self.quote_open.search(sentence))
        if quoted and self.roles.search(sentence) and \
                self.speech.search(sentence):
            return 'other'
        if quoted or (hits['first_person'] and not self.roles.search(
                sentence)):
            return 'self'
        return 'narrator'

    def period(self, sentence, lang):
        for code, rx in self.periods[lang]:
            if rx.search(sentence):
                return code
        return None


def prepare(doc, tagger=None, sticky_period=True):
    """为文档补充 sentences 与 stats 字段。

    sticky_period：叙事通常按时间顺序展开，未出现时期标记的句子沿用上一句的时期。
    """
    tagger = tagger or Tagger()
    lang = doc.get('language') or detect_lang(doc.get('text', ''))
    sents, last = [], 'PX'
    for i, s in enumerate(split_sentences(doc.get('text', ''), lang), 1):
        t = tagger.tag(s, lang)
        p = tagger.period(s, lang)
        if p:
            last = p
        t.update({'sid': 'S%03d' % i, 'text': s,
                  'period': p or (last if sticky_period else 'PX'),
                  'period_explicit': bool(p)})
        sents.append(t)
    n = len(sents) or 1
    stats = {
        'n_sentences': len(sents),
        'n_event': sum(s['kind'] == 'event' for s in sents),
        'n_rhetoric': sum(s['kind'] == 'rhetoric' for s in sents),
        'n_self': sum(s['attribution'] == 'self' for s in sents),
    }
    stats['event_ratio'] = stats['n_event'] / n
    stats['rhetoric_ratio'] = stats['n_rhetoric'] / n
    stats['self_ratio'] = stats['n_self'] / n
    out = dict(doc)
    out.update({'language': lang, 'sentences': sents, 'stats': stats})
    return out


def numbered_text(doc, kinds=None):
    """生成带句子编号的正文，供人工或大模型编码。kinds 可只保留部分句子类型。"""
    lines = []
    for s in doc['sentences']:
        if kinds and s['kind'] not in kinds:
            continue
        lines.append('[%s] %s' % (s['sid'], s['text']))
    return '\n'.join(lines)
