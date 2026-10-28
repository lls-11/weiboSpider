# -*- coding: UTF-8 -*-
"""从已有语料中筛出“自述类、有过程描写”的文本，写入 data/self_narrative/。

纳入三类：
1. 诺奖本人自传（narrative_voice=self）：去掉文末奖项、出处等列表行；
2. 诺奖深度访谈文字稿：只取正式访谈的 transcript，去掉获奖当天的电话访谈、
   视频简介和圆桌节目介绍；一页有多份正式访谈的，各成一篇；
3. 国内文本：本人第一人称叙述占正文三成五以上、且不少于 800 字的专访
   （获奖感言、寄语式合辑不纳入）。

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

OUT = os.path.join(HERE, 'self_narrative')
MIN_PROCESS_EN = 15
MIN_FP_SHARE_ZH = 0.35
MIN_FP_CHARS_ZH = 800
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


def main():
    rows, docs = [], []
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
            n = n_process_en(text)
            keep = n >= MIN_PROCESS_EN
            nd = dict(d, doc_id='%s_t%d' % (d['doc_id'], k),
                      parent_doc_id=d['doc_id'], text=text,
                      title=d['title'] + ' — ' + desc[:80],
                      subset='nobel_interview', n_process=n,
                      interview_desc=desc)
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
    for s in ('nobel_autobiography', 'nobel_interview', 'cn_first_person'):
        cand = [r for r in rows if r[1] == s]
        kept = [r for r in cand if r[4]]
        print('%s：候选 %d，纳入 %d（%d 人）' % (
            s, len(cand), len(kept), len({r[0]['person_id'] for r in kept})))
    print('合计 %d 篇，%d 人' % (len(docs), len({d['person_id'] for d in docs})))


if __name__ == '__main__':
    main()
