# -*- coding: UTF-8 -*-
"""命令行入口：python3 -m talent_corpus <子命令> -h 查看各子命令参数。

典型流程（默认数据目录 talent_data/）：
    rmrb → search-sheet →（人工检索填表）→ articles → nobel → prepare
    → classify / lexical → human-export → code → human-import → analyze
"""

import argparse
import glob
import json
import logging
import os
import sys

from . import corpus, load_codebook

logger = logging.getLogger('talent_corpus')

DATA = 'talent_data'


def _fetcher(args):
    from .fetch import Fetcher
    return Fetcher(cache_dir=args.cache_dir,
                   delay=(args.delay, args.delay * 2),
                   respect_robots=not args.ignore_robots)


def _years(spec):
    if '-' in spec:
        a, b = spec.split('-')
        return list(range(int(a), int(b) + 1))
    return [int(y) for y in spec.split(',')]


def cmd_rmrb(args):
    from datetime import date
    from .sources import rmrb
    f = None if args.from_raw else _fetcher(args)
    if args.dates:
        days = [date(*map(int, d.split('-'))) for d in args.dates.split(',')]
    else:
        days = rmrb.dates_for(_years(args.years), args.window.split(':'))
    if args.from_raw:
        # 不联网：用之前 --dump-raw 保存的原文重新切分条目，并覆盖输出文件
        arts = rmrb.dedupe_articles(rmrb.articles_from_dump(
            corpus.read_jsonl(args.from_raw)))
        docs = [d for a in arts for d in rmrb.to_docs(a, args.include_vocational)]
        rmrb.check_counts(docs)
        corpus.write_jsonl(args.out, docs)
        logger.info('由原文重建：名录 %d 份，条目 %d 条：%s', len(arts), len(docs),
                    args.out)
        return
    arts = []
    for d in days:
        arts.extend(rmrb.crawl_date(f, d, scan_all=args.scan_all))
    raw = [{k: a[k] for k in ('date', 'page', 'url', 'title', 'text')}
           for a in arts]
    arts = rmrb.dedupe_articles(arts)
    docs = [d for a in arts for d in rmrb.to_docs(a, args.include_vocational)]
    rmrb.check_counts(docs)
    if args.dump_raw:
        corpus.write_jsonl(args.dump_raw, raw)
    n = corpus.merge_jsonl(args.out, docs)
    logger.info('名录 %d 份，解析条目 %d 条，%s 共 %d 条', len(arts), len(docs),
                args.out, n)


def cmd_search_sheet(args):
    from .sources import articles
    entries = [d for d in corpus.read_jsonl(args.entries)
               if d['corpus'] == 'rmrb_scholarship']
    n = articles.make_search_sheet(entries, args.out)
    logger.info('检索工作表 %d 行：%s', n, args.out)


def cmd_articles(args):
    from .sources import articles
    if args.local_dir:
        docs, failed = articles.parse_local_dir(args.local_dir)
    else:
        docs, failed = articles.fetch_url_list(
            _fetcher(args), articles.read_url_list(args.urls))
    n = corpus.merge_jsonl(args.out, docs)
    if failed:
        from .analysis import write_csv
        fp = os.path.splitext(args.out)[0] + '_failed.csv'
        write_csv(fp, failed)
        logger.warning('%d 篇未取得正文（常见原因：微信验证、页面失效），清单见 %s',
                       len(failed), fp)
    logger.info('取得 %d 篇，%s 共 %d 条', len(docs), args.out, n)


def cmd_nobel(args):
    from .sources import nobel
    f = _fetcher(args)
    laureates = nobel.list_laureates(f, args.categories.split(','),
                                     args.year_from, args.year_to)
    logger.info('获奖者 %d 人', len(laureates))
    docs = []
    for lau in laureates:
        docs.extend(nobel.fetch_laureate_docs(f, lau, args.pages.split(',')))
    n = corpus.merge_jsonl(args.out, docs)
    logger.info('取得 %d 篇，%s 共 %d 条', len(docs), args.out, n)


def cmd_weibo(args):
    from .sources import weibo
    entries = corpus.read_jsonl(args.entries) if args.entries else []
    docs, rows = weibo.collect(args.weibo_dir, entries=entries)
    corpus.merge_jsonl(args.out, docs)
    if rows and args.article_list:
        from .analysis import write_csv
        write_csv(args.article_list, rows)
    logger.info('筛出微博 %d 条，头条文章 %d 篇', len(docs), len(rows))


def cmd_prepare(args):
    from .preprocess import Tagger, prepare
    tagger = Tagger()
    docs = []
    for pattern in args.inputs:
        for path in sorted(glob.glob(pattern)):
            docs.extend(corpus.read_jsonl(path))
    out = [prepare(d, tagger) for d in docs if d.get('text', '').strip()]
    out = [d for d in out if d['stats']['n_sentences'] >= args.min_sentences]
    corpus.write_jsonl(args.out, out)
    logger.info('预处理 %d 篇：%s', len(out), args.out)


def cmd_classify(args):
    from .analysis import build_persons, write_csv
    persons = build_persons(corpus.read_jsonl(args.inp))
    write_csv(args.out, persons.values(),
              ['person_id', 'name', 'corpus', 'level', 'program', 'school',
               'award_year', 'n_docs', 'sample_type', 'innovation', 'stage'])
    logger.info('人物 %d 名：%s', len(persons), args.out)


def cmd_lexical(args):
    from .analysis import write_csv
    from .coding.lexical import features
    rows = [features(d) for d in corpus.read_jsonl(args.inp)]
    write_csv(args.out, rows)
    logger.info('词典特征 %d 篇：%s', len(rows), args.out)


def _merge_codes(path, records):
    existing = {(r['doc_id'], r['coder']): r for r in corpus.read_jsonl(path)}
    for r in records:
        existing[(r['doc_id'], r['coder'])] = r
    corpus.write_jsonl(path, existing.values())


def cmd_code(args):
    from .coding.llm import LLMCoder
    docs = corpus.read_jsonl(args.inp)
    if args.corpus:
        docs = [d for d in docs if d['corpus'] in args.corpus.split(',')]
    if args.doc_ids:
        with open(args.doc_ids, encoding='utf-8') as f:
            wanted = {line.strip() for line in f if line.strip()}
        docs = [d for d in docs if d['doc_id'] in wanted]
    kinds = ('event', 'other') if args.events_only else None
    coder = LLMCoder(model=args.model, effort=args.effort, kinds=kinds)
    by_id = {d['doc_id']: d for d in docs}
    if args.batch_collect:
        recs = coder.collect_batch(args.batch_collect, by_id)
        _merge_codes(args.out, recs)
        logger.info('收回批量结果 %d 条', len(recs))
        return
    done = {r['doc_id'] for r in corpus.read_jsonl(args.out)
            if not r.get('error') and r['coder'] == args.model}
    todo = [d for d in docs if d['doc_id'] not in done][:args.limit or None]
    if args.batch_submit:
        bid = coder.submit_batch(todo)
        logger.info('已提交批量任务 %s（%d 篇），完成后运行 --batch-collect %s',
                    bid, len(todo), bid)
        return
    for i, d in enumerate(todo, 1):
        try:
            rec = coder.code(d)
        except TypeError as e:
            if 'authentication' not in str(e):
                raise
            logger.error('未找到 Anthropic API 凭据：请设置环境变量 ANTHROPIC_API_KEY，'
                         '或先运行 ant auth login。')
            return 1
        _merge_codes(args.out, [rec])
        logger.info('[%d/%d] %s %s %s', i, len(todo), d['doc_id'],
                    d.get('name', ''), rec.get('error') or
                    '%d 项指标' % len(rec.get('codes', [])))


# 默认只编自述类文本（data/build_self_narrative.py 生成）；要编报道类，显式传入其他文件
EVIDENCE_INPUTS = [os.path.join('data', 'self_narrative', 'analysis_set.jsonl')]


def cmd_evidence(args):
    from .coding import evidence as ev
    docs = [d for path in args.inputs for d in corpus.read_jsonl(path)]
    wanted = None
    if args.doc_ids:
        with open(args.doc_ids, encoding='utf-8') as f:
            wanted = {line.strip() for line in f if line.strip()}
    if args.subset:
        docs = [d for d in docs if d.get('subset') in args.subset.split(',')]
    docs = ev.select_docs(docs, args.corpus.split(',') if args.corpus else None,
                          wanted, self_only=not args.include_narrator)
    coder = ev.EvidenceCoder(model=args.model, effort=args.effort,
                             max_tokens=args.max_tokens, prompt_path=args.prompt or ev.PROMPT_PATH,
                             families=ev.load_families(args.families),
                             client=not args.dry_run)
    if args.batch_collect:
        units = {d['doc_id']: coder.unit(d) for d in docs}
        recs = coder.collect_batch(args.batch_collect, units)
        corpus.write_jsonl(args.out, recs, append=True)
        logger.info('收回批量结果 %d 条：%s', len(recs), args.out)
        return
    done = {r['run']['doc_id'] for r in corpus.read_jsonl(args.out)
            if not r.get('error') and
            r['run']['prompt_version'] == coder.meta.get('prompt_version') and
            r['run']['model'] == args.model}
    todo = [coder.unit(d) for d in docs if d['doc_id'] not in done]
    todo = todo[:args.limit or None]
    if args.dry_run:
        path = args.dry_run
        corpus.write_jsonl(path, [dict(coder.params(u), run=u['run'])
                                  for u in todo])
        chars = sum(len(u['fixed_text']) for u in todo)
        logger.info('试运行：%d 篇、正文共 %d 字符，请求已写入 %s（未调用 API）',
                    len(todo), chars, path)
        return
    if args.batch_submit:
        bid = coder.submit_batch(todo)
        logger.info('已提交批量任务 %s（%d 篇），完成后运行 --batch-collect %s',
                    bid, len(todo), bid)
        return
    for i, u in enumerate(todo, 1):
        try:
            rec = coder.code(u)
        except TypeError as e:
            if 'authentication' not in str(e):
                raise
            logger.error('未找到 Anthropic API 凭据：请设置环境变量 ANTHROPIC_API_KEY，'
                         '或先运行 ant auth login。')
            return 1
        corpus.write_jsonl(args.out, [rec], append=True)
        note = rec.get('error') or '证据 %d 条；%s' % (
            len(rec.get('evidence', [])),
            '；'.join(rec.get('problems', [])) or '核对通过')
        logger.info('[%d/%d] %s %s %s', i, len(todo), u['doc']['doc_id'],
                    u['doc'].get('name', ''), note)


def cmd_evidence_export(args):
    from .coding import evidence as ev
    recs = corpus.read_jsonl(args.inp)
    paths = ev.export_tables(recs, args.out_dir)
    logger.info('导出 %s；%s', '、'.join(paths.values()),
                json.dumps(ev.summarize(recs), ensure_ascii=False))


def cmd_human_export(args):
    from .coding import human
    docs = human.sample_docs(corpus.read_jsonl(args.inp), args.frac,
                             seed=args.seed)
    human.export_sheets(docs, args.out_dir)
    with open(os.path.join(args.out_dir, 'sample_ids.txt'), 'w',
              encoding='utf-8') as f:
        f.write('\n'.join(d['doc_id'] for d in docs))
    logger.info('抽取 %d 篇用于人工编码：%s', len(docs), args.out_dir)


def cmd_human_import(args):
    from .coding import human
    with open(args.sample_ids, encoding='utf-8') as f:
        ids = {line.strip() for line in f if line.strip()}
    docs = {d['doc_id']: d for d in corpus.read_jsonl(args.inp)
            if d['doc_id'] in ids}
    recs = human.import_codes(args.codes, docs, args.coder)
    _merge_codes(args.out, recs)
    logger.info('导入 %s 的编码 %d 篇', args.coder, len(recs))


def cmd_analyze(args):
    from . import analysis as A
    docs = corpus.read_jsonl(args.inp)
    records = corpus.read_jsonl(args.codes)
    overrides = A.read_stage_overrides(args.stages) if args.stages else None
    persons = A.build_persons(docs, overrides)
    levels = ('高', '中', '低') if args.include_low else ('高', '中')
    coder = args.coder or A.pick_coder(records)
    pcodes = A.person_codes(records, persons, coder)
    table = A.score_table(pcodes, persons, args.scale, levels)
    prof = A.profiles(table, persons, levels)
    sal, sal_dim, sal_sum = A.stage_salience(records, persons, coder=coder,
                                             levels=levels)
    students = {pid for pid, p in persons.items()
                if p['corpus'] != 'nobel'}
    innov = A.group_compare([r for r in prof if r['person_id'] in students],
                            table, 'innovation', True, False, levels)
    # 科学家本科至博士阶段的叙事 vs 学生：只计 P2–P4 时期证据
    early = A.person_codes(records, persons, coder,
                           periods={'P2', 'P3', 'P4'})
    early_table = A.score_table(early, persons, args.scale, levels)
    early_prof = A.profiles(early_table, persons, levels)
    for r in early_prof:
        r['group'] = 'nobel_early' if r['corpus'] == 'nobel' else (
            'student_innovation' if r['innovation'] else 'student_other')
    vs_nobel = A.group_compare(early_prof, early_table, 'group', 'nobel_early',
                               'student_innovation', levels)
    local, new_labels = A.local_code_summary(records, persons, coder)
    rhet = A.rhetoric_summary(docs, records, coder)
    sheet, sheet_fields = A.score_sheet_rows(table, persons)
    sheets = {
        '人物': (list(persons.values()), None),
        '学生得分格式': (sheet, sheet_fields),
        '六维画像': (prof, None),
        '阶段显著性_指标': (sal, None),
        '阶段显著性_类别': (sal_dim, None),
        '创新型vs非创新型': (innov, None),
        '科学家同期vs创新型学生': (vs_nobel, None),
        '本土化编码': (local, None),
        '新增编码标签': (new_labels, None),
        '刻板叙事': (rhet, None),
    }
    summary = {'coder': coder, 'scale': args.scale, 'levels': list(levels),
               'n_persons': len(persons), 'stage_salience': sal_sum}
    if args.reliability:
        ca, cb_ = args.reliability.split(',')
        rel, rel_sum = A.reliability(records, ca, cb_, levels=levels)
        sheets['编码一致性'] = (rel, None)
        summary['reliability'] = rel_sum
    path = A.export(args.out_dir, sheets)
    with open(os.path.join(args.out_dir, 'summary.json'), 'w',
              encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info('分析结果：%s %s', args.out_dir, path or '（未安装 openpyxl，只输出 CSV）')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_codebook(args):
    cb = load_codebook()
    lines = ['# ' + cb['title'], '', cb['scope'], '', '## 编码规则', '']
    lines += ['%d. %s' % (i, r) for i, r in enumerate(cb['coding_rules'], 1)]
    lines += ['', '## 各阶段的文本特征', '',
              '| 阶段 | 文本特征 | 外部评价来源 | 典型成果 |', '|---|---|---|---|']
    for k, s in cb['stages'].items():
        lines.append('| %s %s | %s | %s | %s |' % (
            k, s['name'], s['text_signature'], s['external_evaluation'],
            s['typical_outputs']))
    for dk, dim in cb['dimensions'].items():
        lines += ['', '## %s %s' % (dk, dim['name']), '', dim['question'], '',
                  '| 编号 | 指标 | 证据等级 | 可观测性 | 阶段 1 | 阶段 2 | 阶段 3 | 阶段 4 |',
                  '|---|---|---|---|---|---|---|---|']
        for ind in cb['indicators']:
            if str(ind['dim']) != dk:
                continue
            a = ind['anchors']
            lines.append('| %s | %s<br>找：%s<br>不编码：%s | %s | %s | %s | %s | %s | %s |'
                         % (ind['id'], ind['name'], ind['look_for'],
                            ind['exclude'], ind['grade'], ind['observability'],
                            a['1'], a['2'], a['3'], a['4']))
    lines += ['', '## 本土化候选编码（探索性，不计分）', '',
              '| 编号 | 名称 | 识别要点 | 与模型的关系 |', '|---|---|---|---|']
    lines += ['| %s | %s | %s | %s |' % (c['id'], c['label'], c['look_for'],
                                         c['related'])
              for c in cb['local_codes']]
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    logger.info('编码手册：%s', args.out)


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    p = argparse.ArgumentParser(prog='python3 -m talent_corpus')
    p.add_argument('--cache-dir', default=os.path.join(DATA, 'cache'),
                   help='原始网页缓存目录')
    p.add_argument('--delay', type=float, default=2.0, help='同一站点两次请求的最短间隔（秒）')
    p.add_argument('--ignore-robots', action='store_true')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('rmrb', help='抓取人民日报国家奖学金获奖学生代表名录')
    s.add_argument('--years', default='2019-2026')
    s.add_argument('--window', default='05-04:05-05', help='每年抓取的日期区间（名录通常在 5 月 4、5 日）')
    s.add_argument('--dates', help='直接指定日期，逗号分隔，如 2026-05-04,2026-05-05')
    s.add_argument('--include-vocational', action='store_true', help='同时保留中职名录')
    s.add_argument('--scan-all', action='store_true',
                   help='打开每天全部文章再判断（慢），默认只打开标题含“国家奖学金”的文章')
    s.add_argument('--dump-raw', help='把名录原文另存为 JSONL，便于核对条目切分')
    s.add_argument('--from-raw', help='不联网，用 --dump-raw 保存的原文重新切分条目')
    s.add_argument('--out', default=os.path.join(DATA, 'raw', 'rmrb.jsonl'))
    s.set_defaults(func=cmd_rmrb)

    s = sub.add_parser('search-sheet', help='为名录中的每人生成检索工作表')
    s.add_argument('--entries', default=os.path.join(DATA, 'raw', 'rmrb.jsonl'))
    s.add_argument('--out', default=os.path.join(DATA, 'search_sheet.csv'))
    s.set_defaults(func=cmd_search_sheet)

    s = sub.add_parser('articles', help='按 URL 清单或本地网页目录采集文章')
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument('--urls', help='CSV，至少含 url 列')
    g.add_argument('--local-dir', help='浏览器保存的网页所在目录')
    s.add_argument('--out', default=os.path.join(DATA, 'raw', 'articles.jsonl'))
    s.set_defaults(func=cmd_articles)

    s = sub.add_parser('nobel', help='采集诺贝尔奖获奖者自传、致辞、访谈、讲座')
    s.add_argument('--categories', default='phy,che,med')
    s.add_argument('--year-from', type=int)
    s.add_argument('--year-to', type=int)
    s.add_argument('--pages', default='biographical,speech,interview,lecture')
    s.add_argument('--out', default=os.path.join(DATA, 'raw', 'nobel.jsonl'))
    s.set_defaults(func=cmd_nobel)

    s = sub.add_parser('weibo', help='从 weibo_spider 结果中筛选人物事迹微博')
    s.add_argument('--weibo-dir', default='weibo')
    s.add_argument('--entries', help='名录 JSONL，用于按姓名关联人物')
    s.add_argument('--article-list', default=os.path.join(DATA, 'weibo_articles.csv'))
    s.add_argument('--out', default=os.path.join(DATA, 'raw', 'weibo.jsonl'))
    s.set_defaults(func=cmd_weibo)

    s = sub.add_parser('prepare', help='分句、标注事件句与口号句、合并语料')
    s.add_argument('inputs', nargs='*',
                   default=[os.path.join(DATA, 'raw', '*.jsonl')])
    s.add_argument('--min-sentences', type=int, default=3)
    s.add_argument('--out', default=os.path.join(DATA, 'prepared.jsonl'))
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser('classify', help='样本初步分类（创新型 / 非创新型）')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'prepared.jsonl'))
    s.add_argument('--out', default=os.path.join(DATA, 'persons.csv'))
    s.set_defaults(func=cmd_classify)

    s = sub.add_parser('lexical', help='词典辅助特征')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'prepared.jsonl'))
    s.add_argument('--out', default=os.path.join(DATA, 'lexical.csv'))
    s.set_defaults(func=cmd_lexical)

    s = sub.add_parser('code', help='用 Claude 编码（需 API 凭据）')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'prepared.jsonl'))
    s.add_argument('--out', default=os.path.join(DATA, 'codes.jsonl'))
    s.add_argument('--model', default='claude-opus-5-5')
    s.add_argument('--effort', default='medium',
                   choices=['low', 'medium', 'high', 'xhigh', 'max'])
    s.add_argument('--corpus', help='只编码这些语料组，逗号分隔')
    s.add_argument('--doc-ids', help='只编码文件中列出的 doc_id（每行一个）')
    s.add_argument('--limit', type=int, default=0, help='本次最多编码多少篇（试跑用）')
    s.add_argument('--events-only', action='store_true', help='不发送口号句，节省费用')
    s.add_argument('--batch-submit', action='store_true', help='提交批量任务（半价，异步）')
    s.add_argument('--batch-collect', metavar='BATCH_ID', help='收回批量任务结果')
    s.set_defaults(func=cmd_code)

    s = sub.add_parser('evidence', help='按证据编码手册 1.0 做 T01—T14 证据编码（需 API 凭据）')
    s.add_argument('inputs', nargs='*', default=EVIDENCE_INPUTS,
                   help='JSONL 文档，默认 data/self_narrative/analysis_set.jsonl')
    s.add_argument('--out', default=os.path.join(DATA, 'evidence', 'runs.jsonl'),
                   help='运行记录（只追加，保留每次原始输出）')
    s.add_argument('--prompt', default=None, help='提示词文件，默认 prompts/evidence_coding_v1.0.md')
    s.add_argument('--model', default='claude-opus-5-5')
    s.add_argument('--effort', default='high',
                   choices=['low', 'medium', 'high', 'xhigh', 'max'])
    s.add_argument('--max-tokens', type=int, default=32000)
    s.add_argument('--corpus', help='只编码这些语料组，逗号分隔，如 nobel,univ_interview')
    s.add_argument('--subset', help='只编码这些子集：nobel_autobiography,nobel_interview,cn_first_person')
    s.add_argument('--doc-ids', help='只编码文件中列出的 doc_id（每行一个）')
    s.add_argument('--limit', type=int, default=0, help='本次最多编码多少篇（试跑用）')
    s.add_argument('--include-narrator', action='store_true',
                   help='诺奖传记也编码第三人称（他人撰写）的版本')
    s.add_argument('--families', help='CSV（doc_id, source_family_id），同源材料归组')
    s.add_argument('--dry-run', metavar='FILE', help='只把请求写入 FILE，不调用 API')
    s.add_argument('--batch-submit', action='store_true', help='提交批量任务（半价，异步）')
    s.add_argument('--batch-collect', metavar='BATCH_ID', help='收回批量任务结果')
    s.set_defaults(func=cmd_evidence)

    s = sub.add_parser('evidence-export', help='把证据编码结果导出为 screening.csv、evidence.csv')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'evidence', 'runs.jsonl'))
    s.add_argument('--out-dir', default=os.path.join(DATA, 'evidence'))
    s.set_defaults(func=cmd_evidence_export)

    s = sub.add_parser('human-export', help='分层抽样并导出人工编码表')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'prepared.jsonl'))
    s.add_argument('--frac', type=float, default=0.2)
    s.add_argument('--seed', type=int, default=2026)
    s.add_argument('--out-dir', default=os.path.join(DATA, 'human'))
    s.set_defaults(func=cmd_human_export)

    s = sub.add_parser('human-import', help='导入人工编码结果')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'prepared.jsonl'))
    s.add_argument('--codes', required=True, help='填好的 codes_template.csv')
    s.add_argument('--coder', required=True, help='编码员标识，如 human:A')
    s.add_argument('--sample-ids', default=os.path.join(DATA, 'human', 'sample_ids.txt'))
    s.add_argument('--out', default=os.path.join(DATA, 'codes.jsonl'))
    s.set_defaults(func=cmd_human_import)

    s = sub.add_parser('analyze', help='计算画像、阶段显著性、组间比较与一致性')
    s.add_argument('--in', dest='inp', default=os.path.join(DATA, 'prepared.jsonl'))
    s.add_argument('--codes', default=os.path.join(DATA, 'codes.jsonl'))
    s.add_argument('--coder', help='使用哪位编码者的结果，默认取记录最多者')
    s.add_argument('--scale', default='anchor', choices=['anchor', 'percentile'])
    s.add_argument('--include-low', action='store_true', help='纳入可观测性为“低”的指标')
    s.add_argument('--stages', help='CSV（person_id, stage），覆盖默认阶段判定')
    s.add_argument('--reliability', metavar='CODER_A,CODER_B')
    s.add_argument('--out-dir', default=os.path.join(DATA, 'analysis'))
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser('codebook', help='把编码手册导出为 Markdown，供专家评审')
    s.add_argument('--out', default=os.path.join('docs', 'codebook.md'))
    s.set_defaults(func=cmd_codebook)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
