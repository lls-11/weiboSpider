# -*- coding: UTF-8 -*-
"""从已有语料中筛出“自述类、有过程描写”的文本，写入 data/self_narrative/。

纳入三类：
1. 诺奖本人自传（narrative_voice=self）：去掉文末奖项、出处等列表行；
2. 诺奖深度访谈文字稿：只取正式访谈的 transcript，去掉获奖当天的电话访谈、
   视频简介和圆桌节目介绍；一页有多份正式访谈的，各成一篇；
3. 国内第一人称专访：本人第一人称叙述占正文三成五以上、且不少于 800 字
   （获奖感言、寄语式合辑不纳入）；
4. 国内报道：不要求第一人称，记者转述的做法、经历同样有信息（如分享会通讯稿中
   “他说，看文献的习惯就像喝咖啡……”）。只排除一句过程或做法描写都没有的荣誉罗列。
   过程句与做法句合计 ≥ 3 的为 cn_report，1—2 句的为 cn_report_short（多为一两百字的
   答辩会、分享会段落，信息有限，是否可用交给编码时的 screening 判断）。

质量指标 n_process：第一人称且含过程词（尝试、失败、意识到、决定、问题、实验……）
的句子数。英文文本要求 n_process ≥ 15。阈值依据 5 篇试编：Boyle 自传为 6，
人工判断其内容几乎全是履历。

运行：python data/build_self_narrative.py
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from talent_corpus import corpus  # noqa: E402
from talent_corpus.narrative import assess  # noqa: E402

OUT = os.path.join(HERE, 'self_narrative')
MIN_PROCESS_EN = 15
MIN_FP_SHARE_ZH = 0.35
MIN_FP_CHARS_ZH = 800
MIN_PROCESS_ZH_REPORT = 3
# 第一人称比例达标、但内容是获奖感言或寄语模板的合辑，人工排除
EXCLUDE_ZH = {'univ_article_f3c187cd839f', 'univ_profile_29ec9b4dd961',
              'univ_profile_3d2a743af92d', 'univ_profile_4b36aa9ef253'}

FP_EN = re.compile(r"\b(I|my|me|we|our)\b")
PROC_EN = re.compile(
    r"\b(tri(?:ed|es|y)|fail\w*|reali[sz]\w*|decid\w*|wonder\w*|puzzl\w*|"
    r"discover\w*|notic\w*|struggl\w*|problem\w*|question\w*|idea\w*|"
    r"experiment\w*|interest\w*|fascinat\w*|curio\w*|surpris\w*|difficult\w*|"
    r"chang\w*|switch\w*|learn\w*|understand\w*|explor\w*|chose|choose|"
    r"disappoint\w*)\b", re.I)
PROC_ZH = re.compile(r'尝试|失败|意识到|发现|决定|问题|实验|困难|调整|改进|思考|兴趣|好奇|探索|'
                     r'挫|瓶颈|重新|反复|验证|想法|思路|方向|选择|困惑|不懂|看不懂')

# 访谈页的分节标题
SECTION = re.compile(r'^(Interview, [A-Z][a-z]+ \d{4}|Telephone interview, [A-Z][a-z]+ \d{4}|'
                     r'Nobel Minds|Nobel Prize Talks|Nobel Prize Conversations|'
                     r'Podcast|Interview with the \d{4})')
TRANSCRIPT = re.compile(r'^(Interview transcript|Transcript of the interview|Transcript)\s*$')
PHONE = re.compile(r'[Tt]elephone|phone interview|following the announcement|'
                   r'immediately after the announcement')
BIO_TAIL = re.compile(r'^(•|From Les Prix Nobel|From Nobel Lectures|This autobiography/biography|'
                      r'Copyright|Selected (publications|references)|Awards|Honours|Honors)')


def sentences_en(text):
    return [s for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def n_process_en(text):
    return sum(1 for s in sentences_en(text)
               if FP_EN.search(s) and PROC_EN.search(s))


def clean_bio(text):
    lines = [ln for ln in text.split('\n') if ln.strip()]
    return '\n'.join(ln for ln in lines if not BIO_TAIL.match(ln.strip()))


def interview_transcripts(text):
    """返回 [(说明, 文字稿)]，说明取 transcript 前最近的分节标题及其后的介绍。"""
    lines = text.split('\n')
    out, cur, header = [], None, []
    for ln in lines:
        s = ln.strip()
        if TRANSCRIPT.match(s):
            cur = {'desc': ' '.join(header), 'lines': []}
            out.append(cur)
            continue
        if SECTION.match(s):
            cur, header = None, [s]
            continue
        if cur is not None:
            cur['lines'].append(ln)
        elif header and len(header) < 3:
            header.append(s)
    return [(b['desc'], '\n'.join(b['lines']).strip()) for b in out]


def zh_first_person(text):
    sents = [s for s in re.split(r'(?<=[。！？!?])', text) if s.strip()]
    fp = [s for s in sents if '我' in s]
    chars = sum(len(s) for s in fp)
    return chars, chars / max(1, len(text)), sum(1 for s in fp if PROC_ZH.search(s))


# ---------------------------------------------------------------- 多人联合访谈按发言人切分
# 诺贝尔访谈里常见一场访谈请两三位获奖者同台，如果整篇挂到每个人名下，
# 会让 A 的编码里混进 B、C 的话。这里按“人名:”标记切开，只留目标人物的发言。
SPEAKER = re.compile(r"^\s*([A-Z][A-Za-z.'\-]*(?:\s+[A-Z][A-Za-z.'\-]*){0,3})\s*:\s")
HONORIFIC = {'sir', 'dame', 'dr', 'prof', 'professor', 'mr', 'mrs', 'ms', 'sir.'}
NAME_NOISE = {'jr', 'sr', 'ii', 'iii'}


def _name_tokens(s):
    return [t for t in re.split(r"[\s.,'\-]+", (s or '').lower())
            if t and t not in HONORIFIC and t not in NAME_NOISE]


def same_speaker(label, name):
    """行首标记与目标人名是否同一人：姓相同，且名字部分有交集。

    这样 “Hamilton Smith” 认得出 “Hamilton O. Smith”、“Eric R Kandel” 认得出 “Eric Kandel”，
    而 “Andrew Davis” 不会被当作 “Raymond Davis Jr.”。
    """
    a, b = _name_tokens(label), _name_tokens(name)
    if not a or not b or a[-1] != b[-1]:
        return False
    given_a, given_b = set(a[:-1]), set(b[:-1])
    return not given_a or not given_b or bool(given_a & given_b)


_SPLIT_SENT = re.compile(r'(?<=[.!?])\s+')
_FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|I'll|my|me|mine|we|our|us)\b", re.I)


def strip_prompts(body):
    """去掉混进本人发言里的访问者提问：以问号结尾、且没有第一人称的句子。

    这些访谈的原文把访问者的追问并进了受访者的段落（如“…My answer is no. Paul Greengard?”），
    留着会让访问者的提问被当成本人的话。
    """
    out = []
    for line in body.split('\n'):
        sents = [s for s in _SPLIT_SENT.split(line) if s.strip()]
        keep = [s for s in sents
                if not (s.rstrip().endswith('?') and not _FIRST_PERSON.search(s))]
        cleaned = ' '.join(keep).strip()
        if cleaned:
            out.append(cleaned)
    return '\n'.join(out)


def split_interview(text, name):
    """按发言人切开多人访谈，返回 (目标人物发言文本, 信息)。

    没有标记、或标记里认不出目标人物时原样返回文本，信息里 matched 为 False。
    """
    turns, cur = [], None
    for line in text.split('\n'):
        m = SPEAKER.match(line)
        if m:
            cur = [m.group(1).strip(), [line[m.end():].strip()]]
            turns.append(cur)
        elif cur is not None:
            cur[1].append(line)          # 同一发言人后续的段落
    labels = [t[0] for t in turns]
    info = {'matched': False, 'speakers': sorted(set(labels)), 'own_turns': 0}
    if len(set(labels)) < 2:             # 单人访谈，不用切
        return text, info
    own = [lab for lab in labels if same_speaker(lab, name)]
    if not own:
        return text, info
    kept = []
    for lab, lines in turns:
        if same_speaker(lab, name):
            body = strip_prompts('\n'.join(lines))
            if body.strip():
                kept.append(body.strip())
    if not kept:
        return text, info
    info.update(matched=True, own_turns=len(kept), speaker_label=own[0])
    return '\n\n'.join(kept), info


def main():
    rows, docs = [], []
    n_split = 0                          # 按发言人切开的多人联合访谈篇数
    nobel_dir = os.path.join(HERE, 'nobel', 'texts')
    for d in corpus.read_jsonl(os.path.join(nobel_dir, 'biographical.jsonl')):
        if d.get('narrative_voice') != 'self':
            continue
        text = clean_bio(d['text'])
        n = n_process_en(text)
        keep = n >= MIN_PROCESS_EN
        rows.append((d, 'nobel_autobiography', n, len(text), keep))
        if keep:
            docs.append(dict(d, text=text, subset='nobel_autobiography', n_process=n))
    for d in corpus.read_jsonl(os.path.join(nobel_dir, 'interview.jsonl')):
        k = 0
        for desc, text in interview_transcripts(d['text']):
            if PHONE.search(desc):
                continue
            k += 1
            text, split = split_interview(text, d.get('name') or '')
            if split['matched']:
                n_split += 1
            n = n_process_en(text)
            keep = n >= MIN_PROCESS_EN
            nd = dict(d, doc_id='%s_t%d' % (d['doc_id'], k),
                      parent_doc_id=d['doc_id'], text=text,
                      title=d['title'] + ' — ' + desc[:80],
                      subset='nobel_interview', n_process=n,
                      interview_desc=desc)
            if split['matched']:
                nd['speaker_split'] = split['speaker_label']
                nd['own_turns'] = split['own_turns']
            rows.append((nd, 'nobel_interview', n, len(text), keep))
            if keep:
                docs.append(nd)
    zh = corpus.read_jsonl(os.path.join(HERE, 'long_texts', 'persons.jsonl'))
    # 整篇专访没有切分步骤，person_id 可能为空：沿用同名同校的已有编号
    known = {(d['name'], d.get('school', '')): d['person_id'] for d in zh
             if d.get('name') and d.get('person_id')}
    for d in zh:
        if d.get('name') and not d.get('person_id'):
            d['person_id'] = known.get((d['name'], d.get('school', ''))) or \
                corpus.person_id(d['name'], d.get('school', ''))
        chars, share, n = zh_first_person(d['text'])
        keep = (bool(d.get('name')) and d['doc_id'] not in EXCLUDE_ZH and
                share >= MIN_FP_SHARE_ZH and chars >= MIN_FP_CHARS_ZH)
        if share >= 0.2 or keep:
            rows.append((d, 'cn_first_person', n, len(d['text']), keep))
        if keep:
            docs.append(dict(d, subset='cn_first_person', n_process=n,
                             first_person_share=round(share, 2)))
            continue
        # 不是第一人称、但写到了过程或做法的报道（含转述）；纯荣誉罗列（0 句）不收
        if not d.get('name') or d['doc_id'] in EXCLUDE_ZH:
            continue
        a = assess(d['text'])
        k = a['n_process'] + a['n_practice']
        if k == 0:
            continue
        subset = 'cn_report' if k >= MIN_PROCESS_ZH_REPORT else 'cn_report_short'
        rows.append((d, subset, k, len(d['text']), True))
        docs.append(dict(d, subset=subset, n_process=k))

    os.makedirs(OUT, exist_ok=True)
    corpus.write_jsonl(os.path.join(OUT, 'analysis_set.jsonl'), docs)
    with open(os.path.join(OUT, 'index.csv'), 'w', encoding='utf-8-sig',
              newline='') as f:
        w = csv.writer(f)
        w.writerow(['doc_id', 'person_id', 'name', 'subset', 'category',
                    'award_year', 'n_process', 'chars', 'included', 'title', 'url'])
        for d, subset, n, chars, keep in rows:
            w.writerow([d['doc_id'], d.get('person_id', ''), d.get('name', ''),
                        subset, d.get('category', ''), d.get('award_year', ''),
                        n, chars, int(keep), d.get('title', ''), d.get('url', '')])
    for s in ('nobel_autobiography', 'nobel_interview', 'cn_first_person',
              'cn_report', 'cn_report_short'):
        cand = [r for r in rows if r[1] == s]
        kept = [r for r in cand if r[4]]
        print('%s：候选 %d，纳入 %d（%d 人）' % (
            s, len(cand), len(kept), len({r[0]['person_id'] for r in kept})))
    print('其中多人联合访谈按发言人切分 %d 篇' % n_split)
    print('合计 %d 篇，%d 人' % (len(docs), len({d['person_id'] for d in docs})))


if __name__ == '__main__':
    main()
