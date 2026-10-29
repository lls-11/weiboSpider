# -*- coding: UTF-8 -*-
"""以人为单位的编码：去荣誉句、按人合并、引语核对、分析表。"""
import csv
import json

from talent_corpus.coding import person as pc

DOC = {'doc_id': 'd1', 'person_id': 'p_1', 'name': '张三', 'corpus': 'tsinghua_special',
       'source_type': 'news', 'language': 'zh', 'subset': 'cn_report', 'title': 't',
       'text': '张三，曾获国家奖学金、挑战杯特等奖，发表SCI论文5篇。\n'
               '第一次流片失败后，他逐项对照仿真与测量数据，重新设计了三版电路。'}


def test_blind_zh_keeps_process_sentences():
    text, removed = pc.blind_zh(DOC['text'])
    assert removed == 1 and '国家奖学金' not in text and '重新设计了三版电路' in text
    text, removed = pc.blind_zh('经过反复调试，最终论文发表在顶刊上。')
    assert removed == 0


def test_group_and_verify():
    people = pc.group_people([DOC, dict(DOC, doc_id='d2', text='他说，读文献就像喝咖啡。'),
                              dict(DOC, doc_id='d3', person_id='', name='')])
    assert len(people) == 1 and len(people[0]['docs']) == 2
    p = people[0]
    res = pc.verify(p, {'codes': [
        {'id': 'C30', 'level': 2, 'stage': '本科', 'quote': '重新设计了三版电路'},
        {'id': 'C30', 'level': 1, 'stage': '不详', 'quote': '他很坚持'},
        {'id': 'C10', 'level': 2, 'stage': '不详', 'quote': '查阅了大量文献'}]})
    codes = {c['id']: c for c in res['codes']}
    assert codes['C30']['level'] == 2 and codes['C30']['verified']
    assert not codes['C10']['verified']


def test_schema_and_table(tmp_path):
    json.dumps(pc.output_schema())
    p = pc.group_people([DOC])[0]
    rec = pc.make_record(p, 'm', {'text_type': '过程叙述', 'education': '本科', 'discipline': '工学',
                                  'gender': '男', 'n_events': 1, 'codes': [
                                      {'id': 'C30', 'level': 2, 'stage': '本科',
                                       'quote': '重新设计了三版电路'},
                                      {'id': 'C10', 'level': 2, 'stage': '本科', 'quote': '编造'}]})
    paths, n, coded = pc.build_table([p], [rec], str(tmp_path))
    with open(paths['persons'], encoding='utf-8-sig') as f:
        row = next(csv.DictReader(f))
    assert row['C30'] == '2' and row['C10'] == '0' and row['n_unverified'] == '1'
    assert row['award_level'] == '2' and row['D6_behavior'] == '1'
    assert row['crit_papers'] == '5'
