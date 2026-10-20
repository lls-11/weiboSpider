# -*- coding: UTF-8 -*-
import json

import pytest

from talent_corpus import (analysis, classify, codable_indicators, corpus,
                           load_codebook, model_params, stats)
from talent_corpus.coding import human, lexical, llm
from talent_corpus.preprocess import Tagger, numbered_text, prepare, \
    split_sentences

ZH = ('张三从小喜欢拆收音机。高中时他自学电路，做了一台简易示波器。'
      '大二时他主动联系课题组，参与低功耗芯片设计。'
      '第一次流片失败后，他逐项对照仿真与测量数据，重新设计了三版电路。'
      '他心怀国之大者，以青春之我书写奋斗答卷。'
      '读博后，他提出把神经形态计算的思路用于传感器芯片，发表了2篇第一作者论文。')

EN = ('I was born in 1918 in New York. As a boy I built radios in my room. '
      'At MIT I read Dirac and tried to fix the theory myself. '
      'Dr. Wheeler suggested a different problem. '
      'In 1947 I realized the diagrams could be computed directly.')


def make_doc(text, corpus_name='univ_article', name='张三', pid='p_1',
             **extra):
    d = corpus.new_doc(corpus_name, 'news', 'u:' + text[:10], 't', text,
                       name=name, pid=pid, **extra)
    return prepare(d)


def test_split_sentences():
    assert len(split_sentences(ZH, 'zh')) == 6
    en = split_sentences(EN, 'en')
    assert len(en) == 5
    assert en[3].startswith('Dr. Wheeler')


def test_tagging_event_vs_rhetoric():
    d = make_doc(ZH)
    kinds = [s['kind'] for s in d['sentences']]
    assert kinds[4] == 'rhetoric'
    assert kinds[3] == 'event' and kinds[5] == 'event'
    assert d['stats']['n_rhetoric'] == 1


def test_life_period_sticky():
    d = make_doc(ZH)
    periods = [s['period'] for s in d['sentences']]
    assert periods[1] == 'P1' and periods[2] == 'P2'
    assert periods[3] == 'P2' and not d['sentences'][3]['period_explicit']
    assert periods[5] == 'P3'


def test_english_tagging():
    d = make_doc(EN, 'nobel', 'R. Feynman', 'nobel_1')
    assert d['language'] == 'en'
    assert d['sentences'][1]['attribution'] == 'self'
    assert d['sentences'][0]['period'] == 'P0'


def test_attribution_zh():
    t = Tagger()
    s = '导师说：“他是我见过最能坚持的学生。”'
    assert t.tag(s, 'zh')['attribution'] == 'other'
    assert t.tag('“我想弄清楚为什么会漏电。”他说。', 'zh')['attribution'] == 'self'


def test_classify_types():
    research = make_doc(ZH)
    r = classify.classify(research)
    assert r['innovation'] is True and r['primary'] == 'research'
    service = make_doc('她连续三年赴云南支教，累计志愿服务时长800小时。'
                       '她组织社会实践团调研乡村振兴，撰写调研报告。'
                       '她担任班长，综合测评专业第一。')
    r = classify.classify(service)
    assert r['innovation'] is False and r['primary'] == 'service'


def test_model_weights_match_reference():
    for t in (1, 1.5, 2, 3, 4):
        w = model_params.indicator_weights(t)
        assert abs(sum(v[1] for v in w.values()) - 1) < 1e-9
    shares = model_params.dim_shares(1)
    assert abs(shares[2] - 0.28) < 1e-9
    # C03 在阶段 1：A 级 1.0 × 相关度 1.0，类别 1 内原始分量合计
    # 0.3*.4 + .6*.6 + 1*1 + .6*.3 + .3*.2 = 1.72
    w1 = model_params.indicator_weights(1)
    assert abs(w1['C03'][0] - 1 / 1.72) < 1e-9


def test_evaluate_missing_not_zero():
    full = {i[0]: 60 for i in model_params.INDICATORS}
    part = dict(full, C01=None, C02=None)
    a = model_params.evaluate(full, 2)
    b = model_params.evaluate(part, 2)
    assert a['dims'][1]['score'] == pytest.approx(60)
    assert b['dims'][1]['score'] == pytest.approx(60)
    assert b['dims'][1]['coverage'] < 1


def test_codebook_consistent_with_model():
    cb = load_codebook()
    ids = [i['id'] for i in cb['indicators']]
    assert ids == [i[0] for i in model_params.INDICATORS]
    for ind in cb['indicators']:
        ref = model_params.IND_BY_ID[ind['id']]
        assert ind['dim'] == ref[1] and ind['name'] == ref[2]
        assert ind['grade'] == ref[3]
        assert set(ind['anchors']) == {'1', '2', '3', '4'}
    assert 'C12' not in codable_indicators(('高', '中', '低'))


def test_system_prompt_and_schema():
    prompt = llm.build_system_prompt()
    assert 'C33' in prompt and '潜伏抑制' not in prompt
    schema = llm.output_schema()
    enum = schema['properties']['codes']['items']['properties']['indicator']['enum']
    assert 'C12' not in enum and 'C09' in enum
    json.dumps(schema)


def test_verify_result():
    d = make_doc(ZH)
    result = {
        'codes': [
            {'indicator': 'C30', 'anchor_stage': 2, 'evidence_quality': 2,
             'evidence': [{'sentence_id': 'S001', 'quote': '重新设计了三版电路',
                           'life_period': 'P2', 'attribution': 'narrator'}],
             'rationale': ''},
            {'indicator': 'C18', 'anchor_stage': 3, 'evidence_quality': 3,
             'evidence': [{'sentence_id': 'S006', 'quote': '编造的引文',
                           'life_period': 'P3', 'attribution': 'narrator'}],
             'rationale': ''},
            {'indicator': 'C12', 'anchor_stage': 1, 'evidence_quality': 2,
             'evidence': [{'sentence_id': 'S001', 'quote': '收音机',
                           'life_period': 'P0', 'attribution': 'narrator'}],
             'rationale': ''},
        ],
        'local_codes': [{'code': 'L01', 'label': '', 'sentence_id': 'S005',
                         'quote': '国之大者'}],
        'rhetoric_sentence_ids': ['S005', 'S999'],
    }
    clean, st = llm.verify_result(result, d)
    assert [c['indicator'] for c in clean['codes']] == ['C30']
    assert clean['codes'][0]['evidence'][0]['sentence_id'] == 'S004'
    assert st['n_sid_fixed'] == 1 and st['n_dropped'] == 1
    assert st['n_codes_dropped'] == 2
    assert clean['rhetoric_sentence_ids'] == ['S005']
    assert 'S004' in llm.build_user_message(d)


def test_lexical_features():
    f = lexical.features(make_doc(ZH))
    assert f['C30_event'] >= 1 and f['rhetoric_ratio'] > 0


def _rec(doc, coder, codes):
    return {'doc_id': doc['doc_id'], 'person_id': doc['person_id'],
            'coder': coder, 'error': '', 'codes': codes,
            'local_codes': [{'code': 'L01', 'label': '', 'sentence_id': 'S001',
                             'quote': 'x'}],
            'rhetoric_sentence_ids': ['S001']}


def _code(iid, anchor, period, quality=2):
    return {'indicator': iid, 'anchor_stage': anchor,
            'evidence_quality': quality,
            'evidence': [{'sentence_id': 'S001', 'quote': 'x',
                          'life_period': period, 'attribution': 'self'}]}


@pytest.fixture
def toy():
    docs, records = [], []
    for k in range(6):
        d = make_doc(ZH, 'rmrb_scholarship', '学生%d' % k, 'p_s%d' % k,
                     level='undergraduate')
        docs.append(d)
        codes = [_code('C30', 2, 'P2'), _code('C10', 2, 'P2')]
        if k % 2:
            codes.append(_code('C28', 3, 'P3'))
        records.append(_rec(d, 'm', codes))
        records.append(_rec(d, 'human:A', codes[:2]))
    for k in range(4):
        d = make_doc(EN, 'nobel', 'L%d' % k, 'nobel_%d' % k)
        docs.append(d)
        # 好奇（C06）集中在童年，自主方向（C01）集中在独立研究期
        records.append(_rec(d, 'm', [_code('C06', 1, 'P0'),
                                     _code('C06', 2, 'P2'),
                                     _code('C01', 4, 'P5'),
                                     _code('C01', 3, 'P3'),
                                     _code('C25', 4, 'P5', quality=1)]))
    return docs, records


def test_analysis_pipeline(toy, tmp_path):
    docs, records = toy
    persons = analysis.build_persons(docs)
    assert persons['p_s0']['stage'] == 2.0 and persons['nobel_0']['stage'] == 4.0
    pc = analysis.person_codes(records, persons, 'm')
    assert 'C25' not in pc['nobel_0']  # 质量 1 的证据不计分
    table = analysis.score_table(pc, persons)
    assert table['p_s1']['C28'] == 75 and table['p_s0']['C28'] is None
    prof = analysis.profiles(table, persons)
    assert all(0 <= r['coverage'] <= 1 for r in prof)
    pct = analysis.score_table(pc, persons, scale='percentile')
    assert pct['nobel_0']['C01'] == 50.0

    rows, dim_rows, summary = analysis.stage_salience(records, persons,
                                                      coder='m')
    c06 = next(r for r in rows if r['indicator'] == 'C06')
    c01 = next(r for r in rows if r['indicator'] == 'C01')
    assert c06['prev_s1'] == 1.0 and c06['prev_s4'] == 0.0
    assert c06['direction_agree'] is True    # 先验：好奇随阶段下降
    assert c01['direction_agree'] is True    # 先验：目标清晰度随阶段上升
    assert summary['persons_per_stage'][1] == 4
    assert len(dim_rows) == 6

    cmp_rows = analysis.group_compare(prof, table, 'corpus', 'nobel',
                                      'rmrb_scholarship')
    assert any(r['measure'] == 'C06' and r['rate_a'] == 1.0 for r in cmp_rows)

    rel, rel_sum = analysis.reliability(records, 'm', 'human:A')
    assert rel_sum['n_docs'] == 6
    c30 = next(r for r in rel if r['indicator'] == 'C30')
    assert c30['agreement'] == 1.0
    c28 = next(r for r in rel if r['indicator'] == 'C28')
    assert c28['present_a'] == 3 and c28['present_b'] == 0

    local, _ = analysis.local_code_summary(records, persons, 'm')
    assert all(r['L01'] == 1.0 for r in local)
    rhet = analysis.rhetoric_summary(docs, records, 'm')
    assert {r['corpus'] for r in rhet} == {'nobel', 'rmrb_scholarship'}

    sheet, fields = analysis.score_sheet_rows(table, persons)
    assert len(sheet) == 34 and fields[:3] == ['编号', '类别编号', '指标']
    analysis.export(str(tmp_path), {'学生得分格式': (sheet, fields),
                                    '六维画像': (prof, None)})
    assert (tmp_path / '六维画像.csv').exists()


def test_stats():
    assert stats.cohen_kappa([0, 1, 1, 0], [0, 1, 1, 0]) == 1.0
    assert stats.cohen_kappa([1, 2, 3, 4], [1, 2, 3, 4], 'quadratic') == 1.0
    k = stats.cohen_kappa([0, 0, 1, 1], [0, 1, 0, 1])
    assert abs(k) < 1e-9
    u, p = stats.mann_whitney([1, 2, 3], [4, 5, 6])
    assert u == 0 and p < 0.1
    assert stats.cliffs_delta([4, 5], [1, 2]) == 1.0
    assert stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1)
    assert stats.slope([1, .8, .6, .6]) < 0
    assert stats.rankdata([3, 1, 3]) == [2.5, 1.0, 2.5]


def test_human_roundtrip(tmp_path, toy):
    docs, _ = toy
    sample = human.sample_docs(docs, frac=0.5, min_per_group=1)
    assert {d['corpus'] for d in sample} == {'nobel', 'rmrb_scholarship'}
    human.export_sheets(sample, str(tmp_path))
    codes = tmp_path / 'codes.csv'
    codes.write_text('doc_id,indicator,anchor_stage,evidence_quality,'
                     'sentence_ids,life_period,attribution,note\n'
                     '%s,c30,2,2,S004;S999,P2,narrator,\n' % sample[0]['doc_id'],
                     encoding='utf-8')
    recs = human.import_codes(str(codes), {d['doc_id']: d for d in sample},
                              'human:B')
    assert len(recs) == len(sample)
    first = next(r for r in recs if r['doc_id'] == sample[0]['doc_id'])
    assert first['codes'][0]['indicator'] == 'C30'
    assert len(first['codes'][0]['evidence']) == 1


def test_cli_codebook(tmp_path):
    from talent_corpus.__main__ import main
    out = tmp_path / 'cb.md'
    assert main(['codebook', '--out', str(out)]) == 0
    text = out.read_text(encoding='utf-8')
    assert '| C33 |' in text and '本土化候选编码' in text


def test_numbered_text_filter():
    d = make_doc(ZH)
    full = numbered_text(d)
    events = numbered_text(d, ('event', 'other'))
    assert '[S005]' in full and '[S005]' not in events
