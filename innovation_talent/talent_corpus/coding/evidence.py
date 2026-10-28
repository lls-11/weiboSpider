# -*- coding: UTF-8 -*-
"""按《创造性人才指标文本证据编码手册》试用版 1.0 做 T01—T14 证据编码。

与 llm.py（C 指标锚点编码）分开：本模块不打分，只产出“指标证据档案”。

流程：
1. load_prompt 读取 prompts/evidence_coding_v1.0.md，“提示词正文”标记之后作为系统提示；
2. prepare_doc 把正文按段编号为 L1、L2……（过长的段在句末切开），固定为 fixed_text，
   并生成 run 记录（run_id、手册与提示词版本、模型、text_version 等）；
3. 模型按 output_schema 返回 screening 与 evidence；
4. validate 检查 14 项覆盖、编号唯一、人物归属、证据互引，逐条核对引文并计算字符偏移
   （fixed_text 中的 Unicode 字符位置，start 含、end 不含）。核对不过的证据不删除，
   写入 flags 交人工复核；
5. export_tables 把结果展开为 screening.csv、evidence.csv，附空白人工复核列。

需要 anthropic（pip install -r talent_corpus/requirements.txt）与 API 凭据；
--dry-run 只生成请求，不调用 API。
"""

import csv
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime

logger = logging.getLogger('talent_corpus.evidence')

DEFAULT_MODEL = 'claude-opus-5-5'
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'prompts',
                           'evidence_coding_v1.0.md')
MARKER = '<!-- 提示词正文 -->'
MAX_PARA = 1200

INDICATORS = ['T%02d' % i for i in range(1, 15)]
SUBCODES = {'T06': ['T06a', 'T06b', 'T06c'], 'T07': ['T07a', 'T07b'],
            'T08': ['T08a', 'T08b'], 'T11': ['T11a', 'T11b']}
# 各指标必提字段；带子码的指标再按子码细分（未列出的子码用指标的公共字段）
DETAIL_FIELDS = {
    'T01': ['goal_content', 'goal_background', 'related_choice', 'goal_change'],
    'T02': ['choice', 'endorsed_reason', 'external_requirement'],
    'T03': ['unknown_question', 'search_action', 'prompted_by_other',
            'finding'],
    'T04': ['interest_domain', 'time_basis', 'participation',
            'interest_expression'],
    'T05': ['initiative_scope', 'proposer', 'first_action', 'co_initiators'],
    'T06a': ['plan_content'], 'T06b': ['monitor_basis'],
    'T06c': ['before', 'after'],
    'T07a': ['obstacle', 'subsequent_action', 'support'],
    'T07b': ['obstacle', 'subsequent_action', 'strategy_before',
             'strategy_after', 'support'],
    'T08': ['source_knowledge', 'target_problem', 'mapping'],
    'T09': ['shared_problem', 'perspective_1', 'perspective_2',
            'consideration_action'],
    'T10': ['prior_experience', 'new_demand', 'choice', 'action'],
    'T11': ['before', 'new_evidence', 'after'],
    'T12': ['representation_before', 'representation_after',
            'changed_element', 'path_change'],
    'T13': ['check_target', 'dimensions_or_comparison', 'action',
            'observation'],
    'T14': ['uncertainty', 'response', 'support'],
}
STATUS = ['completed', 'partial', 'unusable', 'not_run']
FORM = ['行为', '声明', '材料不足']
DIRECTION = ['支持', '相反表现', '定义边界', '不确定']
CONTEXT = ['明确', '可能', '未建立']
LINK = ['P0', 'P1', 'P2', 'P3']
ATTRIBUTION = ['本人', '记者或传记作者', '其他当事人', '多人', '无归因', '无法判断']
PHASE = ['方向选择', '学习准备', '问题发现', '想法生成', '求解', '评价验证',
         '实施迭代', '未明确']
VOICE = ['本人', '记者或作者', '其他人', '无法判断']
ELICITATION = ['自发叙述', '一般经历提问', '直接特征提问', '引导性提问', '未知']

# 本项目语料的 source_type → 手册中的材料类型
SOURCE_TYPES = {'biographical': '个人传记', 'interview': '访谈转录',
                'speech': '演讲', 'lecture': '讲座', 'news': '人物报道',
                'wechat': '人物报道', 'list_entry': '事迹简介',
                'weibo': '社交媒体'}
INTERVIEW_CORPORA = {'univ_interview'}


# ---------------------------------------------------------------- 提示词

def load_prompt(path=PROMPT_PATH):
    """返回 (系统提示, 元数据)。元数据取自文件开头 --- 之间的 key: value 行。"""
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    meta = {}
    m = re.match(r'---\n(.*?)\n---\n', raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                meta[k.strip()] = v.strip().strip('"\'')
    if MARKER not in raw:
        raise ValueError('提示词文件缺少标记 %s：%s' % (MARKER, path))
    return raw.split(MARKER, 1)[1].strip(), meta


# ---------------------------------------------------------------- 输入

_SENT_END = re.compile(r'(?<=[。！？!?；;])|(?<=[.!?])\s+(?=[A-Z"“(])')


def _chunks(line, limit=MAX_PARA):
    """过长的段按句末切成不超过 limit 字符的块；块拼回去与原段完全相同。"""
    if len(line) <= limit:
        return [line]
    pieces, last = [], 0
    for m in _SENT_END.finditer(line):
        if m.end() > last:
            pieces.append(line[last:m.end()])
            last = m.end()
    pieces.append(line[last:])
    out, cur = [], ''
    for p in pieces:
        if cur and len(cur) + len(p) > limit:
            out.append(cur)
            cur = ''
        cur += p
    if cur:
        out.append(cur)
    return [c for c in out if c.strip()]


def paragraphs(text, limit=MAX_PARA):
    """非空行为段；返回 [(paragraph_id, 段文本, 在 fixed_text 中的起点)] 与 fixed_text。"""
    paras = []
    for line in (text or '').splitlines():
        line = line.strip()
        if line:
            paras.extend(_chunks(line, limit))
    out, pos = [], 0
    for i, p in enumerate(paras, 1):
        out.append(('L%d' % i, p, pos))
        pos += len(p) + 1
    return out, '\n'.join(paras)


def source_type_of(doc):
    if doc.get('corpus') in INTERVIEW_CORPORA:
        return '访谈'
    return SOURCE_TYPES.get(doc.get('source_type'), doc.get('source_type', ''))


def prepare_doc(doc, prompt_meta, model=DEFAULT_MODEL, families=None):
    """生成编码单元：段落、固定文本与 run 记录。"""
    paras, fixed = paragraphs(doc.get('text', ''))
    run = {
        'run_id': 'R' + uuid.uuid4().hex[:12],
        'codebook_version': prompt_meta.get('codebook_version', ''),
        'prompt_version': prompt_meta.get('prompt_version', ''),
        'model': model,
        'run_time': datetime.now().isoformat(timespec='seconds'),
        'doc_id': doc['doc_id'],
        'source_url': doc.get('url', ''),
        'source_type': source_type_of(doc),
        'source_family_id': (families or {}).get(doc['doc_id']),
        'text_version': hashlib.sha1(fixed.encode('utf-8')).hexdigest()[:16],
        'target_person_ids': [doc['person_id']],
        'read_scope': '全文（%d 段）' % len(paras) + (
            '；切分自 %s' % doc['parent_doc_id']
            if doc.get('parent_doc_id') else ''),
    }
    return {'doc': doc, 'paragraphs': paras, 'fixed_text': fixed, 'run': run}


def build_user_message(unit):
    doc = unit['doc']
    lines = ['doc_id：%s' % doc['doc_id'],
             '目标人物：%s（person_id：%s）' % (
                 doc.get('name', ''), doc['person_id']),
             'source_type：%s' % unit['run']['source_type'],
             '材料范围：%s' % unit['run']['read_scope']]
    if doc.get('title'):
        lines.append('标题：%s' % doc['title'])
    lines += ['', '正文（按段编号）：']
    lines += ['[%s] %s' % (pid, text) for pid, text, _ in unit['paragraphs']]
    return '\n'.join(lines)


def select_docs(docs, corpora=None, doc_ids=None, self_only=True):
    """过滤可编码文档；没有姓名或 person_id 的（多人合辑未切开）跳过并记日志。"""
    out, skipped = [], 0
    for d in docs:
        if corpora and d.get('corpus') not in corpora:
            continue
        if doc_ids and d['doc_id'] not in doc_ids:
            continue
        if self_only and d.get('source_type') == 'biographical' and \
                d.get('narrative_voice') not in (None, 'self'):
            continue
        if not d.get('name') or not d.get('person_id') or \
                not (d.get('text') or '').strip():
            skipped += 1
            continue
        out.append(d)
    if skipped:
        logger.info('跳过 %d 篇没有目标人物或正文的文档', skipped)
    return out


# ---------------------------------------------------------------- 输出格式

def _obj(props, required=None):
    return {'type': 'object', 'properties': props,
            'required': required or list(props), 'additionalProperties': False}


def _nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


def _enum(values):
    return {'type': 'string', 'enum': values}


def output_schema():
    s = {'type': 'string'}
    subs = [c for v in SUBCODES.values() for c in v]
    screening = _obj({
        'person_id': s, 'indicator_id': _enum(INDICATORS),
        'status': _enum(STATUS), 'reason': s,
        'evidence_ids': {'type': 'array', 'items': s},
    })
    evidence = _obj({
        'evidence_id': s, 'person_id': s, 'event_id': s,
        'indicator_id': _enum(INDICATORS),
        'subcode': _nullable(_enum(subs)),
        'quotes': {'type': 'array',
                   'items': _obj({'paragraph_id': s, 'quote': s})},
        'form': _enum(FORM), 'direction': _enum(DIRECTION),
        'creative_context': _enum(CONTEXT), 'process_link': _enum(LINK),
        'attribution': _enum(ATTRIBUTION),
        'creative_phase': {'type': 'array', 'items': _enum(PHASE)},
        'voice': _enum(VOICE),
        'event_time': _nullable(s), 'age_at_event': _nullable(s),
        'age_basis': _nullable(s), 'education_stage': _nullable(s),
        'domain': _nullable(s), 'elicitation': _enum(ELICITATION),
        'context_support': {'type': 'array', 'items': s},
        'indicator_details': {'type': 'array', 'items': _obj(
            {'field': s, 'value': _nullable(s)})},
        'interpretation': s, 'limitation': s,
    })
    return _obj({'screening': {'type': 'array', 'items': screening},
                 'evidence': {'type': 'array', 'items': evidence}})


# ---------------------------------------------------------------- 核对

_WS = re.compile(r'\s+')
_QUOTE_MAP = str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'",
                            '「': '"', '」': '"', '　': ' '})


def _fuzzy_find(quote, text):
    """忽略空白差异和弯直引号差异查找，返回 (start, end) 或 None。"""
    q = _WS.sub(' ', quote.translate(_QUOTE_MAP)).strip()
    if not q:
        return None
    pat = r'\s*'.join(re.escape(ch) for ch in q.replace(' ', ''))
    m = re.search(pat, text.translate(_QUOTE_MAP))
    return (m.start(), m.end()) if m else None


def locate_quote(unit, paragraph_id, quote):
    """返回 (段号, start, end, 核对结果)。

    exact：在所引段中逐字找到；moved：在另一段中逐字找到，段号已改正；
    normalized：只有忽略空白或引号差异才找到；not_found：找不到。
    """
    paras = unit['paragraphs']
    by_id = {pid: (text, pos) for pid, text, pos in paras}
    if not quote:
        return paragraph_id, None, None, 'not_found'
    if paragraph_id in by_id:
        text, pos = by_id[paragraph_id]
        i = text.find(quote)
        if i >= 0:
            return paragraph_id, pos + i, pos + i + len(quote), 'exact'
    for pid, text, pos in paras:
        i = text.find(quote)
        if i >= 0:
            return pid, pos + i, pos + i + len(quote), 'moved'
    order = sorted(paras, key=lambda p: p[0] != paragraph_id)
    for pid, text, pos in order:
        hit = _fuzzy_find(quote, text)
        if hit:
            return pid, pos + hit[0], pos + hit[1], 'normalized'
    return paragraph_id, None, None, 'not_found'


def expected_fields(indicator_id, subcode):
    return DETAIL_FIELDS.get(subcode) or DETAIL_FIELDS.get(indicator_id, [])


def validate(unit, result):
    """核对模型输出；返回 (clean, problems)。clean 中每条证据带 flags 与 quotes 偏移。"""
    problems = []
    targets = set(unit['run']['target_person_ids'])
    evidence, seen = [], set()
    for e in result.get('evidence', []):
        e = dict(e)
        flags = []
        eid = e.get('evidence_id')
        if eid in seen:
            flags.append('duplicate_evidence_id')
        seen.add(eid)
        if e.get('person_id') not in targets:
            flags.append('unknown_person')
        ind, sub = e.get('indicator_id'), e.get('subcode')
        if ind in SUBCODES:
            if sub not in SUBCODES[ind]:
                flags.append('subcode_missing_or_mismatch')
        elif sub is not None:
            flags.append('subcode_not_allowed')
        quotes = []
        for q in e.get('quotes') or []:
            pid, start, end, how = locate_quote(
                unit, q.get('paragraph_id'), q.get('quote', ''))
            quotes.append(dict(q, paragraph_id=pid, char_start=start,
                               char_end=end, match=how,
                               original_paragraph_id=q.get('paragraph_id')))
            if how == 'not_found':
                flags.append('quote_not_found')
            elif how == 'normalized':
                flags.append('quote_normalized')
            elif how == 'moved':
                flags.append('paragraph_id_corrected')
        if not quotes:
            flags.append('no_quote')
        details = {}
        for d in e.get('indicator_details') or []:
            details[d.get('field')] = d.get('value')
        missing = [f for f in expected_fields(ind, sub) if f not in details]
        if missing:
            flags.append('details_missing:' + ','.join(missing))
        if e.get('form') == '行为' and e.get('direction') == '支持' and \
                e.get('process_link') == 'P3' and not e.get('limitation'):
            flags.append('p3_without_limitation')
        e.update(quotes=quotes, indicator_details=details,
                 flags=sorted(set(flags)))
        evidence.append(e)

    ids = {e.get('evidence_id') for e in evidence}
    screening, cover = [], {}
    for s in result.get('screening', []):
        s = dict(s)
        flags = []
        if s.get('person_id') not in targets:
            flags.append('unknown_person')
        bad = [x for x in s.get('evidence_ids') or [] if x not in ids]
        if bad:
            flags.append('evidence_id_not_found:' + ','.join(bad))
        linked = [e for e in evidence if e.get('evidence_id') in
                  (s.get('evidence_ids') or [])]
        if any(e.get('indicator_id') != s.get('indicator_id')
               for e in linked):
            flags.append('evidence_indicator_mismatch')
        if s.get('status') != 'completed' and s.get('evidence_ids'):
            flags.append('evidence_with_incomplete_status')
        key = (s.get('person_id'), s.get('indicator_id'))
        if key in cover:
            flags.append('duplicate_screening_row')
        cover[key] = s
        s['flags'] = flags
        screening.append(s)

    for p in targets:
        lacking = [t for t in INDICATORS if (p, t) not in cover]
        if lacking:
            problems.append('screening 缺少 %s：%s' % (p, ','.join(lacking)))
    listed = {x for s in screening for x in s.get('evidence_ids') or []}
    for e in evidence:
        if e.get('evidence_id') not in listed:
            e['flags'] = sorted(set(e['flags'] + ['not_in_screening']))
    n_flag = sum(1 for e in evidence if e['flags'])
    if n_flag:
        problems.append('%d 条证据需要复核' % n_flag)
    return {'screening': screening, 'evidence': evidence}, problems


# ---------------------------------------------------------------- 调用

def _usage(u):
    if u is None:
        return {}
    keys = ('input_tokens', 'output_tokens', 'cache_read_input_tokens',
            'cache_creation_input_tokens')
    return {k: getattr(u, k, None) for k in keys}


def make_record(unit, parsed=None, raw_text='', error='', stop_reason='',
                usage=None, served_by=None):
    rec = {'run': unit['run'], 'person_name': unit['doc'].get('name', ''),
           'served_by': served_by, 'stop_reason': stop_reason,
           'error': error, 'usage': usage or {}, 'raw_output': raw_text}
    if parsed is not None:
        clean, problems = validate(unit, parsed)
        rec.update(clean)
        rec['problems'] = problems
    return rec


class EvidenceCoder:
    def __init__(self, model=DEFAULT_MODEL, effort='high', max_tokens=32000,
                 prompt_path=PROMPT_PATH, families=None, client=True):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.system, self.meta = load_prompt(prompt_path)
        self.schema = output_schema()
        self.families = families or {}
        self.client = None
        if client:
            import anthropic
            self.anthropic = anthropic
            self.client = anthropic.Anthropic(max_retries=5)

    def unit(self, doc):
        return prepare_doc(doc, self.meta, self.model, self.families)

    def _system_blocks(self):
        return [{'type': 'text', 'text': self.system,
                 'cache_control': {'type': 'ephemeral'}}]

    def params(self, unit):
        return {'model': self.model, 'max_tokens': self.max_tokens,
                'system': self._system_blocks(),
                'output_config': {'effort': self.effort,
                                  'format': {'type': 'json_schema',
                                             'schema': self.schema}},
                'messages': [{'role': 'user',
                              'content': build_user_message(unit)}]}

    def code(self, unit):
        """同步编码一篇；被安全分类器拒绝时由服务端换用备用模型重试。"""
        a = self.anthropic
        try:
            with self.client.beta.messages.stream(
                    betas=[FALLBACK_BETA], fallbacks='default',
                    **self.params(unit)) as stream:
                msg = stream.get_final_message()
        except a.BadRequestError as e:
            return make_record(unit, error='bad_request: %s' % e.message)
        except a.RateLimitError:
            time.sleep(60)
            return make_record(unit, error='rate_limited')
        except a.APIStatusError as e:
            return make_record(unit, error='api_status_%s: %s' % (
                e.status_code, e.message))
        except a.APIConnectionError as e:
            return make_record(unit, error='connection: %s' % e)
        return self.from_message(unit, msg)

    def from_message(self, unit, msg):
        usage = _usage(msg.usage)
        served = getattr(msg, 'model', self.model)
        text = next((b.text for b in msg.content if b.type == 'text'), '')
        if msg.stop_reason == 'refusal':
            return make_record(unit, raw_text=text, error='refusal',
                               stop_reason='refusal', usage=usage,
                               served_by=served)
        if msg.stop_reason == 'max_tokens':
            return make_record(unit, raw_text=text, error='truncated',
                               stop_reason='max_tokens', usage=usage,
                               served_by=served)
        try:
            parsed = json.loads(text)
        except ValueError:
            return make_record(unit, raw_text=text, error='invalid_json',
                               stop_reason=msg.stop_reason, usage=usage,
                               served_by=served)
        return make_record(unit, parsed, raw_text=text,
                           stop_reason=msg.stop_reason, usage=usage,
                           served_by=served)

    # Message Batches：异步、半价；不支持 fallbacks 参数
    def submit_batch(self, units):
        from anthropic.types.message_create_params import \
            MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request
        reqs = [Request(custom_id=u['doc']['doc_id'],
                        params=MessageCreateParamsNonStreaming(
                            **self.params(u)))
                for u in units]
        return self.client.messages.batches.create(requests=reqs).id

    def collect_batch(self, batch_id, units_by_id):
        out = []
        for r in self.client.messages.batches.results(batch_id):
            u = units_by_id.get(r.custom_id)
            if u is None:
                continue
            if r.result.type == 'succeeded':
                out.append(self.from_message(u, r.result.message))
            else:
                out.append(make_record(u, error='batch_' + r.result.type))
        return out


# ---------------------------------------------------------------- 导出

REVIEW_COLS = ['reviewer_1', 'reviewer_2', 'original_codes', 'disagreements',
               'final_codes', 'decision_reason', 'review_status']
RUN_COLS = ['run_id', 'doc_id', 'codebook_version', 'prompt_version', 'model',
            'run_time', 'source_type', 'source_url', 'source_family_id',
            'text_version']
EVIDENCE_COLS = ['evidence_id', 'person_id', 'person_name', 'event_id',
                 'indicator_id', 'subcode', 'quote_text', 'paragraph_ids',
                 'char_offsets', 'quote_match', 'form', 'direction',
                 'creative_context', 'process_link', 'attribution',
                 'creative_phase', 'voice', 'event_time', 'age_at_event',
                 'age_basis', 'education_stage', 'domain', 'elicitation',
                 'context_support', 'indicator_details', 'interpretation',
                 'limitation', 'flags']
SCREENING_COLS = ['person_id', 'person_name', 'indicator_id', 'status',
                  'reason', 'evidence_ids', 'flags']


def latest_records(records):
    """同一 doc_id 只保留最新一次成功的运行（记录按追加顺序读入）。"""
    best = {}
    for r in records:
        if r.get('error'):
            continue
        best[r['run']['doc_id']] = r
    return list(best.values())


def _j(v):
    return json.dumps(v, ensure_ascii=False) if v not in (None, '') else ''


def export_tables(records, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    recs = latest_records(records)
    paths = {}
    for name, cols in (('screening', SCREENING_COLS),
                       ('evidence', EVIDENCE_COLS)):
        path = os.path.join(out_dir, name + '.csv')
        paths[name] = path
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(RUN_COLS + cols + REVIEW_COLS)
            for r in recs:
                run = [r['run'].get(c) for c in RUN_COLS]
                for row in r.get(name, []):
                    w.writerow(run + [_cell(name, row, c, r)
                                      for c in cols] + [''] * len(REVIEW_COLS))
    return paths


def _cell(table, row, col, rec):
    if col == 'person_name':
        return rec.get('person_name', '')
    q = row.get('quotes') or []
    if col == 'quote_text':
        return ' ‖ '.join(x.get('quote', '') for x in q)
    if col == 'paragraph_ids':
        return ','.join(x.get('paragraph_id') or '' for x in q)
    if col == 'char_offsets':
        return ','.join('%s-%s' % (x.get('char_start'), x.get('char_end'))
                        for x in q)
    if col == 'quote_match':
        return ','.join(x.get('match', '') for x in q)
    v = row.get(col)
    if col in ('flags', 'evidence_ids', 'creative_phase', 'context_support'):
        return '；'.join(v or [])
    if isinstance(v, (dict, list)):
        return _j(v)
    return '' if v is None else v


def summarize(records):
    recs = latest_records(records)
    n_ev = sum(len(r.get('evidence', [])) for r in recs)
    n_flag = sum(1 for r in recs for e in r.get('evidence', []) if e['flags'])
    errors = sum(1 for r in records if r.get('error'))
    return {'docs': len(recs), 'evidence': n_ev, 'flagged': n_flag,
            'error_runs': errors}


def load_families(path):
    """CSV（doc_id, source_family_id），由研究者填写同源材料归组。"""
    if not path:
        return {}
    with open(path, encoding='utf-8-sig') as f:
        return {r['doc_id']: r['source_family_id'] or None
                for r in csv.DictReader(f)}
