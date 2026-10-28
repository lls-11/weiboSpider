# -*- coding: UTF-8 -*-
"""证据编码（手册 1.0）：提示词读取、分段、核对与导出；最后一项用本地桩服务器检查请求。"""
import csv
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from talent_corpus.coding import evidence as ev

TEXT = ('张三，清华大学电子系本科生。\n'
        '大二时他主动联系课题组，参与低功耗芯片设计。\n'
        '第一次流片失败后，他逐项对照仿真与测量数据，重新设计了三版电路。')
DOC = {'doc_id': 'd1', 'person_id': 'p_1', 'name': '张三',
       'corpus': 'tsinghua_special', 'source_type': 'news', 'url': 'u',
       'title': 't', 'text': TEXT}


def _unit():
    _, meta = ev.load_prompt()
    return ev.prepare_doc(DOC, meta)


def _evidence(**kw):
    e = {'evidence_id': 'E001', 'person_id': 'p_1', 'event_id': 'EV001',
         'indicator_id': 'T07', 'subcode': 'T07b',
         'quotes': [{'paragraph_id': 'L3', 'quote': '重新设计了三版电路'}],
         'form': '行为', 'direction': '支持', 'creative_context': '可能',
         'process_link': 'P3', 'attribution': '记者或传记作者',
         'creative_phase': ['求解'], 'voice': '记者或作者',
         'event_time': None, 'age_at_event': None, 'age_basis': None,
         'education_stage': '本科', 'domain': '电子', 'elicitation': '未知',
         'context_support': ['课题组'],
         'indicator_details': [{'field': f, 'value': 'x'} for f in
                               ev.DETAIL_FIELDS['T07b']],
         'interpretation': '', 'limitation': '记者叙述'}
    e.update(kw)
    return e


def _result(evidence):
    rows = [{'person_id': 'p_1', 'indicator_id': t, 'status': 'completed',
             'reason': '已核读全文', 'evidence_ids': []}
            for t in ev.INDICATORS]
    for e in evidence:
        for r in rows:
            if r['indicator_id'] == e['indicator_id']:
                r['evidence_ids'].append(e['evidence_id'])
    return {'screening': rows, 'evidence': evidence}


def test_load_prompt():
    system, meta = ev.load_prompt()
    assert meta['prompt_version'] == 'evidence-1.0-p1'
    assert meta['codebook_version'] == '1.0'
    assert system.startswith('# 角色与任务')
    assert '文件说明' not in system
    for t in ev.INDICATORS:
        assert '## %s ' % t in system


def test_paragraphs_and_chunks():
    paras, fixed = ev.paragraphs(TEXT)
    assert [p[0] for p in paras] == ['L1', 'L2', 'L3']
    for _, text, pos in paras:
        assert fixed[pos:pos + len(text)] == text
    long = '这是一句话。' * 400
    chunks = ev._chunks(long, 1200)
    assert ''.join(chunks) == long and max(map(len, chunks)) <= 1200


def test_schema_and_user_message():
    json.dumps(ev.output_schema())
    msg = ev.build_user_message(_unit())
    assert '[L3] 第一次流片失败后' in msg and 'p_1' in msg


def test_validate_offsets_and_flags():
    u = _unit()
    clean, problems = ev.validate(u, _result([
        _evidence(),
        _evidence(evidence_id='E002', indicator_id='T05', subcode=None,
                  quotes=[{'paragraph_id': 'L3', 'quote': '主动联系课题组'}],
                  indicator_details=[]),
        _evidence(evidence_id='E003', indicator_id='T03', subcode=None,
                  quotes=[{'paragraph_id': 'L2', 'quote': '查阅了大量文献'}],
                  indicator_details=[{'field': f, 'value': None} for f in
                                     ev.DETAIL_FIELDS['T03']]),
    ]))
    e1, e2, e3 = clean['evidence']
    q = e1['quotes'][0]
    assert q['match'] == 'exact' and e1['flags'] == []
    assert u['fixed_text'][q['char_start']:q['char_end']] == '重新设计了三版电路'
    assert e2['quotes'][0]['paragraph_id'] == 'L2'
    assert 'paragraph_id_corrected' in e2['flags']
    assert any(f.startswith('details_missing') for f in e2['flags'])
    assert 'quote_not_found' in e3['flags']
    assert isinstance(e1['indicator_details'], dict)
    assert problems == ['2 条证据需要复核']


def test_validate_coverage_and_links():
    res = _result([_evidence()])
    res['screening'] = res['screening'][:10]
    res['screening'][0]['evidence_ids'] = ['E009']
    res['screening'][6]['evidence_ids'] = []
    clean, problems = ev.validate(_unit(), res)
    assert any('T11,T12,T13,T14' in p for p in problems)
    assert clean['screening'][0]['flags'] == ['evidence_id_not_found:E009']
    assert 'not_in_screening' in clean['evidence'][0]['flags']


def test_normalized_quote():
    u = ev.prepare_doc(dict(DOC, text='他说：“先做 再说”。'), {})
    pid, s, e, how = ev.locate_quote(u, 'L1', '"先做再说"')
    assert how == 'normalized' and u['fixed_text'][s:e] == '“先做 再说”'


def test_select_docs():
    docs = [DOC, dict(DOC, doc_id='d2', name=''),
            dict(DOC, doc_id='d3', source_type='biographical',
                 narrative_voice='narrator')]
    assert [d['doc_id'] for d in ev.select_docs(docs)] == ['d1']


def test_export(tmp_path):
    u = _unit()
    rec = ev.make_record(u, _result([_evidence()]))
    paths = ev.export_tables([rec], str(tmp_path))
    with open(paths['evidence'], encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['quote_text'] == '重新设计了三版电路'
    assert rows[0]['run_id'] == u['run']['run_id']
    assert 'final_codes' in rows[0]
    with open(paths['screening'], encoding='utf-8-sig') as f:
        assert len(list(csv.DictReader(f))) == 14


def _sse(text):
    msg = {'id': 'msg_1', 'type': 'message', 'role': 'assistant',
           'model': 'claude-opus-5-5', 'content': [], 'stop_reason': None,
           'stop_sequence': None,
           'usage': {'input_tokens': 10, 'output_tokens': 0}}
    events = [
        ('message_start', {'type': 'message_start', 'message': msg}),
        ('content_block_start', {'type': 'content_block_start', 'index': 0,
                                 'content_block': {'type': 'text',
                                                   'text': ''}}),
        ('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                 'delta': {'type': 'text_delta',
                                           'text': text}}),
        ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
        ('message_delta', {'type': 'message_delta',
                           'delta': {'stop_reason': 'end_turn',
                                     'stop_sequence': None},
                           'usage': {'output_tokens': 5}}),
        ('message_stop', {'type': 'message_stop'}),
    ]
    return ''.join('event: %s\ndata: %s\n\n' % (k, json.dumps(v))
                   for k, v in events).encode()


def test_coder_request_offline(monkeypatch):
    pytest.importorskip('anthropic')
    body = _sse(json.dumps(_result([_evidence()]), ensure_ascii=False))
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get('content-length', 0))
            captured.append({'headers': dict(self.headers),
                             'body': json.loads(self.rfile.read(n))})
            self.send_response(200)
            self.send_header('content-type', 'text/event-stream')
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setenv('ANTHROPIC_BASE_URL',
                       'http://127.0.0.1:%d' % srv.server_address[1])
    try:
        coder = ev.EvidenceCoder()
        rec = coder.code(coder.unit(DOC))
    finally:
        srv.shutdown()
    req = captured[0]
    assert 'server-side-fallback-2026-07-01' in req['headers'].get(
        'anthropic-beta', '')
    b = req['body']
    assert b['model'] == 'claude-opus-5-5' and b['fallbacks'] == 'default'
    assert b['stream'] is True
    assert b['output_config']['effort'] == 'high'
    assert b['output_config']['format']['type'] == 'json_schema'
    assert b['system'][0]['cache_control'] == {'type': 'ephemeral'}
    assert rec['error'] == '' and rec['served_by'] == 'claude-opus-5-5'
    assert rec['evidence'][0]['flags'] == [] and rec['problems'] == []
