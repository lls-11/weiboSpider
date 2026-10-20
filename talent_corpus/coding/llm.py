# -*- coding: UTF-8 -*-
"""用 Claude 按编码手册对文本做指标编码，并逐条核对引文。

流程：
1. 预处理后的文档按句编号（[S001] ……），连同人物信息发给模型；
2. 模型按 JSON Schema 返回：指标、阶段锚点、证据质量、引文（句子编号 + 原文）、
   本土化编码、口号句编号、样本类型；
3. verify_result 检查每条引文是否确实出现在所引句子中：
   句子编号错但引文能在别处找到的，改正编号；找不到的引文删除；
   没有任何有效引文的指标编码整条删除。

编码手册放在 system 提示中并开启提示缓存，批量编码时只有第一篇文档需要完整计费。
需要安装 anthropic（pip install -r talent_corpus/requirements.txt）并配置 API 凭据。
"""

import json
import logging
import re
import time
from datetime import datetime

from .. import codable_indicators, load_codebook
from ..preprocess import numbered_text

logger = logging.getLogger('talent_corpus.llm')

DEFAULT_MODEL = 'claude-opus-5-5'
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
PERIODS = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5', 'PX']


def build_system_prompt(codebook=None, levels=('高', '中', '低')):
    cb = codebook or load_codebook()
    ids = set(codable_indicators(levels, cb))
    out = [
        '你是心理学研究项目的文本编码员。研究者正在用公开的回顾性叙事文本（获奖事迹、人物通讯、'
        '自传、访谈、演讲）初步检验一个创新人才识别模型。你的编码会与人工编码比对，并用于检验'
        '模型中各项指标在不同发展阶段的权重假设，所以宁缺毋滥：没有具体事件支撑的指标不要编码，'
        '文本未提及的指标会按缺失处理，不会被当作低分。',
        '',
        '## 编码规则',
    ]
    out += ['- ' + r for r in cb['coding_rules']]
    out += ['', '## 证据质量 evidence_quality']
    out += ['- %s：%s' % kv for kv in cb['evidence_quality'].items()]
    out += ['', '## 叙述归属 attribution']
    out += ['- %s：%s' % kv for kv in cb['attribution'].items()]
    out += ['', '## 人生时期 life_period（事件发生的时期，与 anchor_stage 分开判断）']
    out += ['- %s：%s' % (k, v['label']) for k, v in cb['life_periods'].items()]
    out += ['', '## TAD 四个发展阶段（anchor_stage 的含义）']
    for k, s in cb['stages'].items():
        out.append('- 阶段 %s %s：%s 外部评价来源：%s' %
                   (k, s['name'], s['text_signature'], s['external_evaluation']))
    out += ['', '## 指标与阶段锚点',
            '每项指标列出：文本中要找什么、不编码什么，以及阶段 1–4 的行为锚点。'
            'anchor_stage 取该行为最接近的锚点。可观测性为“低”的指标只在证据非常明确时编码。']
    dims = cb['dimensions']
    for ind in cb['indicators']:
        if ind['id'] not in ids:
            continue
        a = ind['anchors']
        out.append(
            '\n### %s %s（类别 %s %s；可观测性 %s）\n找：%s\n不编码：%s\n'
            '锚点 1：%s\n锚点 2：%s\n锚点 3：%s\n锚点 4：%s' %
            (ind['id'], ind['name'], ind['dim'], dims[str(ind['dim'])]['name'],
             ind['observability'], ind['look_for'], ind['exclude'],
             a['1'], a['2'], a['3'], a['4']))
    out += ['', '## 本土化候选编码（探索性，不计分）',
            '下列特征可能是本土叙事的特点。出现具体表述时记录；发现手册未覆盖、'
            '但对理解人物成长重要的具体行为，用 NEW 记录并给出简短标签。']
    out += ['- %s %s：%s' % (c['id'], c['label'], c['look_for'])
            for c in cb['local_codes']]
    out += ['', '## 样本类型 sample_type']
    out += ['- %s：%s' % kv for kv in cb['sample_types'].items()]
    out += ['- unclear：文本信息不足以判断。',
            '', '## 输出',
            '按给定 JSON Schema 输出。quote 必须逐字摘自所引句子（可以只摘句子的一部分），'
            '英文文本保留英文原文；rationale 用中文简要说明为什么符合该锚点。'
            'rhetoric_sentence_ids 列出只有口号或评价、没有具体事件的句子编号。']
    return '\n'.join(out)


def output_schema(codebook=None, levels=('高', '中', '低')):
    cb = codebook or load_codebook()
    ids = codable_indicators(levels, cb)
    local = [c['id'] for c in cb['local_codes']] + ['NEW']
    types = list(cb['sample_types']) + ['unclear']

    def obj(props, required=None):
        return {'type': 'object', 'properties': props,
                'required': required or list(props),
                'additionalProperties': False}

    evidence = obj({
        'sentence_id': {'type': 'string'},
        'quote': {'type': 'string'},
        'life_period': {'type': 'string', 'enum': PERIODS},
        'attribution': {'type': 'string', 'enum': ['self', 'narrator', 'other']},
    })
    code = obj({
        'indicator': {'type': 'string', 'enum': ids},
        'anchor_stage': {'type': 'integer', 'enum': [1, 2, 3, 4]},
        'evidence_quality': {'type': 'integer', 'enum': [1, 2, 3]},
        'evidence': {'type': 'array', 'items': evidence},
        'rationale': {'type': 'string'},
    })
    local_code = obj({
        'code': {'type': 'string', 'enum': local},
        'label': {'type': 'string'},
        'sentence_id': {'type': 'string'},
        'quote': {'type': 'string'},
    })
    return obj({
        'target_person': {'type': 'string'},
        'sample_type': obj({
            'primary': {'type': 'string', 'enum': types},
            'innovation': {'type': 'boolean'},
            'rationale': {'type': 'string'},
        }),
        'codes': {'type': 'array', 'items': code},
        'local_codes': {'type': 'array', 'items': local_code},
        'rhetoric_sentence_ids': {'type': 'array', 'items': {'type': 'string'}},
        'notes': {'type': 'string'},
    })


def build_user_message(doc, kinds=None):
    meta = ['目标人物：%s' % (doc.get('name') or '（见正文）'),
            '语料：%s；文本类型：%s' % (
                doc.get('corpus', ''), doc.get('source_type', ''))]
    for k, label in (('school', '院校'), ('level', '层次'),
                     ('award_year', '获奖年度'), ('category', '奖项领域'),
                     ('narrative_voice', '叙述人称'), ('title', '标题')):
        if doc.get(k):
            meta.append('%s：%s' % (label, doc[k]))
    return '\n'.join(meta) + '\n\n正文（按句编号）：\n' + \
        numbered_text(doc, kinds)


_NORM = re.compile(r'[\s　"“”‘’\'「」『』，,。．.、；;：:！!？?（）()…—\-]+')


def _norm(s):
    return _NORM.sub('', s or '').lower()


def verify_result(result, doc, codebook=None, levels=('高', '中', '低')):
    """核对引文，返回清洗后的结果与核对统计。"""
    allowed = set(codable_indicators(levels, codebook))
    sents = {s['sid']: _norm(s['text']) for s in doc['sentences']}
    stats = {'n_evidence': 0, 'n_dropped': 0, 'n_sid_fixed': 0,
             'n_codes_dropped': 0}

    def locate(sid, quote):
        q = _norm(quote)
        if not q:
            return None
        if sid in sents and q in sents[sid]:
            return sid
        for other, text in sents.items():
            if q in text:
                stats['n_sid_fixed'] += 1
                return other
        return None

    codes = []
    for c in result.get('codes', []):
        if c.get('indicator') not in allowed:
            stats['n_codes_dropped'] += 1
            continue
        ev = []
        for e in c.get('evidence', []):
            stats['n_evidence'] += 1
            sid = locate(e.get('sentence_id'), e.get('quote'))
            if sid is None:
                stats['n_dropped'] += 1
                continue
            ev.append(dict(e, sentence_id=sid))
        if ev:
            codes.append(dict(c, evidence=ev))
        else:
            stats['n_codes_dropped'] += 1
    local = []
    for lc in result.get('local_codes', []):
        sid = locate(lc.get('sentence_id'), lc.get('quote'))
        if sid:
            local.append(dict(lc, sentence_id=sid))
    rhet = [s for s in result.get('rhetoric_sentence_ids', []) if s in sents]
    clean = dict(result, codes=codes, local_codes=local,
                 rhetoric_sentence_ids=rhet)
    return clean, stats


def _record(doc, coder, parsed=None, error='', stop_reason='', usage=None):
    rec = {'doc_id': doc['doc_id'], 'person_id': doc.get('person_id', ''),
           'coder': coder, 'coded_at': datetime.now().isoformat(
               timespec='seconds'),
           'stop_reason': stop_reason, 'error': error, 'usage': usage or {}}
    if parsed is not None:
        clean, stats = verify_result(parsed, doc)
        rec.update(clean)
        rec['verification'] = stats
    return rec


def _usage(u):
    if u is None:
        return {}
    keys = ('input_tokens', 'output_tokens', 'cache_read_input_tokens',
            'cache_creation_input_tokens')
    return {k: getattr(u, k, None) for k in keys}


def _first_text(content):
    return next((b.text for b in content if b.type == 'text'), '')


class LLMCoder:
    def __init__(self, model=DEFAULT_MODEL, effort='medium', kinds=None,
                 max_tokens=16000, codebook=None):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=5)
        self.model = model
        self.effort = effort
        self.kinds = kinds
        self.max_tokens = max_tokens
        self.system = build_system_prompt(codebook)
        self.schema = output_schema(codebook)

    def _system_blocks(self):
        return [{'type': 'text', 'text': self.system,
                 'cache_control': {'type': 'ephemeral'}}]

    def _output_config(self):
        return {'effort': self.effort,
                'format': {'type': 'json_schema', 'schema': self.schema}}

    def code(self, doc):
        """同步编码一篇文档；被安全分类器拒绝时由服务端自动换用备用模型重试。"""
        a = self.anthropic
        try:
            resp = self.client.beta.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                betas=[FALLBACK_BETA], fallbacks='default',
                system=self._system_blocks(),
                output_config=self._output_config(),
                messages=[{'role': 'user',
                           'content': build_user_message(doc, self.kinds)}])
        except a.BadRequestError as e:
            return _record(doc, self.model, error='bad_request: %s' % e.message)
        except a.RateLimitError:
            time.sleep(60)
            return _record(doc, self.model, error='rate_limited')
        except a.APIStatusError as e:
            return _record(doc, self.model, error='api_status_%s: %s' % (
                e.status_code, e.message))
        except a.APIConnectionError as e:
            return _record(doc, self.model, error='connection: %s' % e)
        return self._from_message(doc, resp)

    def _from_message(self, doc, msg):
        # coder 记请求的模型，便于分析时按编码者归并；served_by 记实际作答的模型
        # （安全分类器拒绝后由备用模型作答时二者不同）
        usage = _usage(msg.usage)
        rec = self._parse(doc, msg, usage)
        rec['served_by'] = getattr(msg, 'model', self.model)
        return rec

    def _parse(self, doc, msg, usage):
        if msg.stop_reason == 'refusal':
            return _record(doc, self.model, error='refusal',
                           stop_reason='refusal', usage=usage)
        if msg.stop_reason == 'max_tokens':
            return _record(doc, self.model, error='truncated',
                           stop_reason='max_tokens', usage=usage)
        try:
            parsed = json.loads(_first_text(msg.content))
        except ValueError:
            return _record(doc, self.model, error='invalid_json',
                           stop_reason=msg.stop_reason, usage=usage)
        return _record(doc, self.model, parsed, stop_reason=msg.stop_reason,
                       usage=usage)

    # ---- Message Batches：异步、半价，适合几百篇文档；不支持 fallbacks 参数 ----

    def submit_batch(self, docs):
        from anthropic.types.message_create_params import \
            MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request
        requests = []
        for d in docs:
            params = MessageCreateParamsNonStreaming(
                model=self.model, max_tokens=self.max_tokens,
                system=self._system_blocks(),
                output_config=self._output_config(),
                messages=[{'role': 'user',
                           'content': build_user_message(d, self.kinds)}])
            requests.append(Request(custom_id=d['doc_id'], params=params))
        batch = self.client.messages.batches.create(requests=requests)
        return batch.id

    def batch_status(self, batch_id):
        return self.client.messages.batches.retrieve(batch_id)

    def collect_batch(self, batch_id, docs_by_id):
        records = []
        for r in self.client.messages.batches.results(batch_id):
            doc = docs_by_id.get(r.custom_id)
            if doc is None:
                continue
            if r.result.type == 'succeeded':
                records.append(self._from_message(doc, r.result.message))
            else:
                records.append(_record(doc, self.model,
                                       error='batch_' + r.result.type))
        return records
