# -*- coding: UTF-8 -*-
"""以人为单位的指标编码（提示词 prompts/person_coding_v1.md），并生成每人一行的分析表。

流程：
1. group_people 把同一 person_id 的多篇文本合成一份材料；中文材料先删去只罗列奖项和成果的句子
   （blind_zh），减少光环效应；
2. 模型对每人输出 text_type、学历、学科、性别、事件数，以及踩中的指标（level 1 声明 / 2 行为、
   阶段、原文引语）；只列踩中的指标，控制输出长度；
3. verify 核对引语是否出现在发给模型的材料中，核对不过的标记为未核实（不删除）；
   并用 mark_shared 标出“同一句引语被多个指标共用”的判断（shared_quote 0—3），供人工复核；
4. build_table 合并程序计算的变量（文本量、来源、获奖等级、论文专利奖项数、套话比例、
   第一人称比例）和模型输出，写出 persons.csv（每人一行）与 codes.csv（每条判断一行）。
   persons.csv 同时给出两套计数口径：n_behavior/n_statement（每条判断都算）与
   n_behavior_dedup/n_statement_dedup（逐字相同的引语只算 level 最高的一条）。

获奖等级按来源判定（见 AWARD_LEVEL），是近似值：清华特奖答辩材料中有未获奖的候选人。
"""

import csv
import json
import logging
import math
import os
import re
import time
from datetime import datetime

from .. import corpus, criteria, load_lexicon
from ..narrative import HABIT_MARKERS, PROCESS_MARKERS, REPORTED_MARKERS
from .evidence import DEFAULT_MODEL, FALLBACK_BETA, _usage, load_prompt

logger = logging.getLogger('talent_corpus.person')

PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'prompts',
                           'person_coding_v1.md')
INDICATORS = ['C%02d' % i for i in range(1, 34) if i not in (12, 13, 15, 17)]
DIM_OF = {c: d for d, ids in {
    1: range(1, 6), 2: range(6, 12), 3: range(12, 16), 4: range(16, 23),
    5: range(23, 28), 6: range(28, 34)}.items() for c in ['C%02d' % i for i in ids]}
STAGES = ['中学及以前', '本科', '研究生', '工作后', '不详']
EDUCATION = ['本科', '硕士', '博士', '博士后或已工作', '不详']
DISCIPLINE = ['理学', '工学', '医学', '农学', '人文', '社科', '经管', '艺术体育', '不详']

# 获奖等级（按来源，有序）：1 国家奖学金；2 校级最高荣誉；3 全国大学生年度人物；4 诺贝尔奖
AWARD_LEVEL = {
    'univ_profile': (1, '国家奖学金'), 'univ_interview': (1, '国家奖学金'),
    'rmrb_scholarship': (1, '国家奖学金'),
    'tsinghua_special': (2, '清华特等奖学金（含答辩候选人）'),
    'zju_zhu': (2, '浙大竺可桢奖学金'), 'pku_annual': (2, '北大学生年度人物'),
    'sjtu_star': (2, '上海交大学术之星或年度人物'),
    'cn_annual': (3, '中国大学生年度人物'), 'nobel': (4, '诺贝尔奖'),
}

_HONOR_ONLY = re.compile(r'荣获|曾获|获评|获得|入选|发表|授权|论文|专利|称号|奖学金|等奖|金奖|银奖|铜奖|冠军|'
                         r'亚军|季军|SCI|EI|影响因子|优秀学生|三好|标兵|先进个人')
_KEEP = PROCESS_MARKERS + HABIT_MARKERS + REPORTED_MARKERS + (
    '兴趣', '历经', '波折', '坎坷', '梳理', '花了', '用了', '创始', '创办', '发起', '牵头')
_SENT_ZH = re.compile(r'(?<=[。！？!?；;])')


def is_honor_list(s):
    """荣誉清单句：含 2 个以上荣誉词，或用顿号罗列荣誉；且没有任何过程、做法、转述标记。
    只含一个“发表”“获得”的叙述句（如“曾用八个月时间梳理……发表文章”）保留。"""
    hits = _HONOR_ONLY.findall(s)
    if not hits or any(m in s for m in _KEEP):
        return False
    return len(hits) >= 2 or '、' in s


def blind_zh(text):
    """删去荣誉清单句（is_honor_list）。返回 (文本, 删去句数)。"""
    out, removed = [], 0
    for line in text.split('\n'):
        kept = []
        for s in _SENT_ZH.split(line):
            if s.strip() and is_honor_list(s):
                removed += 1
                continue
            kept.append(s)
        line = ''.join(kept).strip()
        if line:
            out.append(line)
    return '\n'.join(out), removed


def group_people(docs):
    """按 person_id 合并；返回 [{person_id, name, docs, text, removed}]，保持首次出现的顺序。"""
    people = {}
    for d in docs:
        if not d.get('person_id') or not d.get('name'):
            continue
        people.setdefault(d['person_id'], []).append(d)
    out = []
    for pid, ds in people.items():
        parts, removed = [], 0
        for i, d in enumerate(ds, 1):
            text = d['text']
            if d.get('language', 'zh') == 'zh':
                text, n = blind_zh(text)
                removed += n
            parts.append('【材料%d：%s】\n%s' % (i, d.get('title', ''), text))
        out.append({'person_id': pid, 'name': ds[0]['name'], 'docs': ds,
                    'text': '\n\n'.join(parts), 'removed': removed})
    return out


def build_user_message(person):
    return '目标人物：%s\n\n%s' % (person['name'], person['text'])


def output_schema():
    s = {'type': 'string'}

    def obj(props):
        return {'type': 'object', 'properties': props, 'required': list(props),
                'additionalProperties': False}

    code = obj({'id': {'type': 'string', 'enum': INDICATORS},
                'level': {'type': 'integer', 'enum': [1, 2]},
                'stage': {'type': 'string', 'enum': STAGES},
                'quote': s})
    return obj({
        'text_type': {'type': 'string', 'enum': ['过程叙述', '荣誉罗列或通报']},
        'education': {'type': 'string', 'enum': EDUCATION},
        'discipline': {'type': 'string', 'enum': DISCIPLINE},
        'gender': {'type': 'string', 'enum': ['男', '女', '不详']},
        'n_events': {'type': 'integer'},
        'codes': {'type': 'array', 'items': code},
    })


_NORM = re.compile(r'[\s　"“”‘’\'「」『』，,。．.、；;：:！!？?（）()…—\-]+')


def _norm(s):
    return _NORM.sub('', s or '').lower()


SHARED_EXACT, SHARED_CONTAIN, SHARED_OVERLAP, SHARED_MIN_JACCARD = 1, 2, 3, 0.8


def _share_level(a, b):
    """两条引语的复用程度：1 完全相同，2 一句包含另一句，3 字符高度重叠，0 无关。"""
    if not a or not b:
        return 0
    if a == b:
        return SHARED_EXACT
    if a in b or b in a:
        return SHARED_CONTAIN
    sa, sb = set(a), set(b)
    if len(sa & sb) / len(sa | sb) > SHARED_MIN_JACCARD:
        return SHARED_OVERLAP
    return 0


def mark_shared(codes):
    """标出“同一句引语被多个指标使用”的判断，供人工复核；不删数据。

    每条判断加两个字段：shared_quote（0—3，越大越可疑）与 shared_with（共用的指标编号）。
    同一对指标之间可以合法共用引语（如 C01 目标内容与 C02 目标理由），所以这只是标记。
    """
    nq = [_norm(c.get('quote')) for c in codes]
    for i, c in enumerate(codes):
        best, with_ = 0, []
        for j, other in enumerate(codes):
            if i == j:
                continue
            s = _share_level(nq[i], nq[j])
            if s:
                best = max(best, s)
                with_.append(other['id'])
        c['shared_quote'] = best
        c['shared_with'] = ','.join(with_)
    return codes


def dedup_codes(codes):
    """完全相同的引语只保留 level 最高的一条，用于“每条判断都算 / 去重后”两套口径对比。

    只合并逐字相同（去空白标点后）的引语；包含与重叠关系不合并，避免误删。
    """
    best = {}
    for c in codes:
        k = _norm(c.get('quote')) or '#' + c['id']
        old = best.get(k)
        if old is None or c['level'] > old['level']:
            best[k] = c
    return [best[k] for k in best]


def verify(person, result):
    """核对引语；同一指标出现多次时保留 level 最高且已核实的一条；并标记共用引语。"""
    text = _norm(person['text'])
    best = {}
    for c in result.get('codes', []):
        c = dict(c, verified=bool(_norm(c.get('quote')) and _norm(c.get('quote')) in text))
        old = best.get(c['id'])
        if old is None or (c['verified'], c['level']) > (old['verified'], old['level']):
            best[c['id']] = c
    return dict(result, codes=mark_shared([best[k] for k in INDICATORS if k in best]))


def make_record(person, model, parsed=None, error='', stop_reason='', usage=None,
                served_by=None, prompt_version=''):
    rec = {'person_id': person['person_id'], 'name': person['name'],
           'doc_ids': [d['doc_id'] for d in person['docs']], 'model': model,
           'served_by': served_by, 'prompt_version': prompt_version,
           'coded_at': datetime.now().isoformat(timespec='seconds'),
           'stop_reason': stop_reason, 'error': error, 'usage': usage or {}}
    if parsed is not None:
        rec['result'] = verify(person, parsed)
    return rec


class PersonCoder:
    def __init__(self, model=DEFAULT_MODEL, effort='medium', max_tokens=8000,
                 prompt_path=PROMPT_PATH, client=True):
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        self.system, self.meta = load_prompt(prompt_path)
        self.schema = output_schema()
        if client:
            import anthropic
            self.anthropic = anthropic
            self.client = anthropic.Anthropic(max_retries=5)

    def params(self, person):
        return {'model': self.model, 'max_tokens': self.max_tokens,
                'system': [{'type': 'text', 'text': self.system,
                            'cache_control': {'type': 'ephemeral'}}],
                'output_config': {'effort': self.effort,
                                  'format': {'type': 'json_schema', 'schema': self.schema}},
                'messages': [{'role': 'user', 'content': build_user_message(person)}]}

    def _record(self, person, **kw):
        return make_record(person, self.model,
                           prompt_version=self.meta.get('prompt_version', ''), **kw)

    def code(self, person):
        a = self.anthropic
        try:
            msg = self.client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks='default', **self.params(person))
        except a.BadRequestError as e:
            return self._record(person, error='bad_request: %s' % e.message)
        except a.RateLimitError:
            time.sleep(60)
            return self._record(person, error='rate_limited')
        except a.APIStatusError as e:
            return self._record(person, error='api_status_%s: %s' % (e.status_code, e.message))
        except a.APIConnectionError as e:
            return self._record(person, error='connection: %s' % e)
        return self.from_message(person, msg)

    def from_message(self, person, msg):
        usage = _usage(msg.usage)
        served = getattr(msg, 'model', self.model)
        if msg.stop_reason in ('refusal', 'max_tokens'):
            return self._record(person, error=msg.stop_reason, stop_reason=msg.stop_reason,
                                usage=usage, served_by=served)
        text = next((b.text for b in msg.content if b.type == 'text'), '')
        try:
            parsed = json.loads(text)
        except ValueError:
            return self._record(person, error='invalid_json', stop_reason=msg.stop_reason,
                                usage=usage, served_by=served)
        return self._record(person, parsed=parsed, stop_reason=msg.stop_reason,
                            usage=usage, served_by=served)

    # Message Batches：异步、半价；不支持 fallbacks
    def submit_batch(self, people):
        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request
        reqs = [Request(custom_id=p['person_id'],
                        params=MessageCreateParamsNonStreaming(**self.params(p)))
                for p in people]
        return self.client.messages.batches.create(requests=reqs).id

    def collect_batch(self, batch_id, people_by_id):
        out = []
        for r in self.client.messages.batches.results(batch_id):
            p = people_by_id.get(r.custom_id)
            if p is None:
                continue
            if r.result.type == 'succeeded':
                out.append(self.from_message(p, r.result.message))
            else:
                out.append(self._record(p, error='batch_' + r.result.type))
        return out


# ---------------------------------------------------------------- DeepSeek 等 OpenAI 兼容接口

OUTPUT_FORMAT = """

## 输出格式

只输出一个 JSON 对象，不要输出其他文字。字段与取值：
{"text_type": "过程叙述" 或 "荣誉罗列或通报",
 "education": "本科" | "硕士" | "博士" | "博士后或已工作" | "不详",
 "discipline": "理学" | "工学" | "医学" | "农学" | "人文" | "社科" | "经管" | "艺术体育" | "不详",
 "gender": "男" | "女" | "不详",
 "n_events": 整数,
 "codes": [{"id": "C30", "level": 2, "stage": "研究生", "quote": "逐字原文"}]}
codes 只列体现了的指标；id 只能取上面列出的编号；level 只能是 1 或 2；
stage 只能是 中学及以前、本科、研究生、工作后、不详。
"""

# 服务商：(接口地址, 密钥环境变量, 默认模型名)。密钥也可写在 talent_data/<服务商>_key.txt。
# codego 是中转站；默认模型名需以中转站的模型列表为准（运行 check_api.py 可列出）。
PROVIDERS = {
    'deepseek': ('https://api.deepseek.com', 'DEEPSEEK_API_KEY', 'deepseek-chat'),
    'codego': ('https://codegoai.com/v1', 'CODEGO_API_KEY', 'deepseek-v4'),
}


KEY_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'talent_data')


def read_key_file(provider):
    """环境变量没有设置时，读取 talent_data/<provider>_key.txt（talent_data 不提交到 Git）。"""
    path = os.path.join(KEY_DIR, '%s_key.txt' % provider)
    try:
        with open(path, encoding='utf-8') as f:
            # 从网页或记事本复制时容易带上引号，去掉免得 401
            return f.read().strip().strip('"\'').strip()
    except OSError:
        return ''


def _parse_json(text):
    """去掉可能的 ```json 包裹后解析。"""
    t = (text or '').strip()
    m = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if m:
        t = m.group(1)
    i, j = t.find('{'), t.rfind('}')
    return json.loads(t[i:j + 1] if i >= 0 and j > i else t)


def clean_result(res):
    """JSON 模式不保证取值合法：越界的字段改为“不详”，非法的指标判断丢弃，并记录丢弃数。"""
    out = {
        'text_type': res.get('text_type') if res.get('text_type') in ('过程叙述', '荣誉罗列或通报')
        else '过程叙述',
        'education': res.get('education') if res.get('education') in EDUCATION else '不详',
        'discipline': res.get('discipline') if res.get('discipline') in DISCIPLINE else '不详',
        'gender': res.get('gender') if res.get('gender') in ('男', '女', '不详') else '不详',
    }
    try:
        out['n_events'] = int(res.get('n_events') or 0)
    except (TypeError, ValueError):
        out['n_events'] = 0
    codes, dropped = [], 0
    for c in res.get('codes') or []:
        if not isinstance(c, dict):
            dropped += 1
            continue
        cid = str(c.get('id', '')).strip().upper()
        try:
            level = int(c.get('level'))
        except (TypeError, ValueError):
            level = 0
        if cid not in INDICATORS or level not in (1, 2):
            dropped += 1
            continue
        stage = c.get('stage') if c.get('stage') in STAGES else '不详'
        codes.append({'id': cid, 'level': level, 'stage': stage, 'quote': str(c.get('quote') or '')})
    out['codes'] = codes
    out['dropped_invalid'] = dropped
    return out


class CompatCoder:
    """OpenAI 兼容的 chat/completions 接口（默认 DeepSeek）。用 requests 直接调用，不需要额外安装包。

    DeepSeek 会自动缓存相同的前缀（系统提示），重复部分按缓存价计费。没有批量接口，
    用 workers 并发提速。
    """

    def __init__(self, provider='deepseek', model=None, base_url=None, api_key=None,
                 max_tokens=8000, temperature=0.0, prompt_path=PROMPT_PATH, timeout=600):
        base, env, default_model = PROVIDERS[provider]
        self.base_url = (base_url or base).rstrip('/')
        self.model = model or default_model
        self.api_key = api_key or os.environ.get(env, '') or read_key_file(provider)
        self.env = env
        self.max_tokens, self.temperature, self.timeout = max_tokens, temperature, timeout
        system, self.meta = load_prompt(prompt_path)
        self.system = system + OUTPUT_FORMAT
        self.json_mode = True

    def params(self, person):
        p = {'model': self.model, 'max_tokens': self.max_tokens,
             'messages': [{'role': 'system', 'content': self.system},
                          {'role': 'user', 'content': build_user_message(person)}]}
        if self.temperature is not None:
            p['temperature'] = self.temperature
        if self.json_mode:
            p['response_format'] = {'type': 'json_object'}
        return p

    def _record(self, person, **kw):
        return make_record(person, self.model,
                           prompt_version=self.meta.get('prompt_version', ''), **kw)

    def code(self, person, retries=4):
        import requests
        if not self.api_key:
            raise RuntimeError('未找到 API 密钥：请设置环境变量 %s' % self.env)
        url = self.base_url + '/chat/completions'
        headers = {'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json'}
        for attempt in range(retries + 1):
            try:
                r = requests.post(url, headers=headers, json=self.params(person), timeout=self.timeout)
            except requests.RequestException as e:
                if attempt == retries:
                    return self._record(person, error='connection: %s' % e)
                time.sleep(2 ** attempt * 5)
                continue
            if r.status_code == 400 and self.json_mode and 'response_format' in r.text:
                self.json_mode = False          # 有的模型不支持 JSON 模式，改为只靠提示词
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt * 5)
                continue
            if r.status_code != 200:
                return self._record(person, error='api_status_%s: %s' % (r.status_code, r.text[:300]))
            return self.from_response(person, r.json())
        return self._record(person, error='retries_exhausted')

    def from_response(self, person, data):
        choice = (data.get('choices') or [{}])[0]
        u = data.get('usage') or {}
        usage = {'input_tokens': u.get('prompt_tokens'), 'output_tokens': u.get('completion_tokens'),
                 'cache_read_input_tokens': u.get('prompt_cache_hit_tokens')}
        served = data.get('model', self.model)
        finish = choice.get('finish_reason', '')
        if finish == 'length':
            return self._record(person, error='max_tokens', stop_reason=finish, usage=usage,
                                served_by=served)
        text = (choice.get('message') or {}).get('content', '')
        try:
            parsed = clean_result(_parse_json(text))
        except ValueError:
            return self._record(person, error='invalid_json', stop_reason=finish, usage=usage,
                                served_by=served)
        return self._record(person, parsed=parsed, stop_reason=finish, usage=usage, served_by=served)


# ---------------------------------------------------------------- 分析表

def _cliche_ratio(text, lang, lx):
    words = lx['cliches_en'] if lang == 'en' else lx['cliches']
    sents = [s for s in re.split(r'(?<=[。！？!?.])\s*', text) if s.strip()]
    if not sents:
        return 0.0
    hit = sum(1 for s in sents if any(w.lower() in s.lower() for w in words))
    return round(hit / len(sents), 3)


def _first_person_share(text, lang):
    sents = [s for s in re.split(r'(?<=[。！？!?.])\s*', text) if s.strip()]
    if not sents:
        return 0.0
    pat = re.compile(r'\b(I|my|me)\b') if lang == 'en' else re.compile('我')
    return round(sum(1 for s in sents if pat.search(s)) / len(sents), 3)


def program_vars(person, rmrb_names=None, lexicon=None):
    """不经过模型的变量。"""
    lx = lexicon or load_lexicon()
    ds = person['docs']
    raw = '\n'.join(d['text'] for d in ds)
    lang = ds[0].get('language') or ('en' if ds[0].get('corpus') == 'nobel' else 'zh')
    levels = [AWARD_LEVEL.get(d.get('corpus'), (0, '未知')) for d in ds]
    level, label = max(levels)
    school = next((d.get('school') for d in ds if d.get('school')), '')
    row = {
        'person_id': person['person_id'], 'name': person['name'],
        'group': 'nobel' if lang == 'en' else 'cn', 'language': lang,
        'subsets': ';'.join(sorted({d.get('subset', '') for d in ds})),
        'corpora': ';'.join(sorted({d.get('corpus', '') for d in ds})),
        'source_types': ';'.join(sorted({d.get('source_type', '') for d in ds})),
        'school': school, 'category': ds[0].get('category', ''),
        'award_year': ds[0].get('award_year', ''), 'birth_year': ds[0].get('birth_year', ''),
        'n_texts': len(ds), 'chars': len(raw), 'log_chars': round(math.log(max(len(raw), 1)), 3),
        'chars_sent': len(person['text']), 'honor_sentences_removed': person['removed'],
        'first_person_share': _first_person_share(raw, lang),
        'cliche_ratio': _cliche_ratio(raw, lang, lx),
        'award_level': level, 'award_label': label,
        'in_rmrb_list': int((person['name'], school) in (rmrb_names or set())),
    }
    if lang == 'zh':
        c = criteria.extract(raw)
        for k in ('papers', 'papers_first_author', 'patents', 'patents_granted', 'projects_led',
                  'awards', 'awards_international', 'awards_national', 'awards_provincial',
                  'award_best_grade', 'honors'):
            row['crit_' + k] = c.get(k)
    return row


LLM_COLS = ['text_type', 'education', 'discipline', 'gender', 'n_events']


def llm_vars(rec, verified_only=True):
    res = rec.get('result') or {}
    row = {k: res.get(k, '') for k in LLM_COLS}
    level = {c: 0 for c in INDICATORS}
    n_unverified, counted = 0, []
    # 老记录可能没有 shared_quote 字段，这里统一补上（不重新调用模型）
    for c in mark_shared([dict(c) for c in res.get('codes', [])]):
        if not c.get('verified'):
            n_unverified += 1
            if verified_only:
                continue
        level[c['id']] = c['level']
        counted.append(c)
    row.update(level)
    for d in range(1, 7):
        ids = [c for c in INDICATORS if DIM_OF[c] == d]
        row['D%d_behavior' % d] = sum(1 for c in ids if level[c] == 2)
        row['D%d_any' % d] = sum(1 for c in ids if level[c] >= 1)
    row['n_behavior'] = sum(1 for v in level.values() if v == 2)
    row['n_statement'] = sum(1 for v in level.values() if v == 1)
    # 去重口径：逐字相同的引语只保留 level 最高的一条，供两套口径对比
    ded = dedup_codes(counted)
    row['n_behavior_dedup'] = sum(1 for c in ded if c['level'] == 2)
    row['n_statement_dedup'] = sum(1 for c in ded if c['level'] == 1)
    row['n_codes'] = len(counted)
    row['n_shared_quote'] = sum(1 for c in counted if c.get('shared_quote'))
    row['n_shared_exact'] = sum(1 for c in counted if c.get('shared_quote') == SHARED_EXACT)
    row['n_unverified'] = n_unverified
    row['n_dropped_invalid'] = res.get('dropped_invalid', 0)
    row['coding_error'] = rec.get('error', '')
    return row


def latest(records, prompt_version=None):
    best = {}
    for r in records:
        if r.get('error') or (prompt_version and r.get('prompt_version') != prompt_version):
            continue
        best[r['person_id']] = r
    return best


def build_table(people, records, out_dir, rmrb_names=None, verified_only=True):
    os.makedirs(out_dir, exist_ok=True)
    recs = latest(records)
    lx = load_lexicon()
    rows, codes = [], []
    for p in people:
        row = program_vars(p, rmrb_names, lx)
        rec = recs.get(p['person_id'])
        row['coded'] = int(rec is not None)
        if rec:
            row.update(llm_vars(rec, verified_only))
            for c in mark_shared([dict(c) for c in rec['result'].get('codes', [])]):
                codes.append({'person_id': p['person_id'], 'name': p['name'],
                              'group': row['group'], 'indicator': c['id'],
                              'dimension': DIM_OF[c['id']], 'level': c['level'],
                              'stage': c['stage'], 'verified': int(c['verified']),
                              'shared_quote': c.get('shared_quote', 0),
                              'shared_with': c.get('shared_with', ''),
                              'quote': c['quote']})
        rows.append(row)
    cols = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    paths = {'persons': os.path.join(out_dir, 'persons.csv'),
             'codes': os.path.join(out_dir, 'codes.csv')}
    with open(paths['persons'], 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(paths['codes'], 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['person_id', 'name', 'group', 'indicator', 'dimension',
                                          'level', 'stage', 'verified', 'shared_quote',
                                          'shared_with', 'quote'])
        w.writeheader()
        w.writerows(codes)
    return paths, len(rows), sum(r['coded'] for r in rows)


def rmrb_name_set(path):
    return {(d['name'], d.get('school', '')) for d in corpus.read_jsonl(path)}
