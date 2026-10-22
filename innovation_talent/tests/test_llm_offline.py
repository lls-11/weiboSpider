# -*- coding: UTF-8 -*-
"""用本地桩服务器检查 LLMCoder 发出的请求与对响应的处理，不调用真实 API。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from talent_corpus import corpus
from talent_corpus.preprocess import prepare

anthropic = pytest.importorskip('anthropic')

TEXT = ('大二时他主动联系课题组，参与低功耗芯片设计。'
        '第一次流片失败后，他逐项对照仿真与测量数据，重新设计了三版电路。')


def _serve(reply, captured):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get('content-length', 0))
            captured.append({'path': self.path, 'headers': dict(self.headers),
                             'body': json.loads(self.rfile.read(n))})
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_coder_request_and_parse(monkeypatch):
    from talent_corpus.coding.llm import LLMCoder
    result = {
        'target_person': '张三',
        'sample_type': {'primary': 'research', 'innovation': True,
                        'rationale': ''},
        'codes': [{'indicator': 'C30', 'anchor_stage': 2,
                   'evidence_quality': 2, 'rationale': '',
                   'evidence': [{'sentence_id': 'S002',
                                 'quote': '重新设计了三版电路',
                                 'life_period': 'P2',
                                 'attribution': 'narrator'}]}],
        'local_codes': [], 'rhetoric_sentence_ids': [], 'notes': ''}
    reply = {'id': 'msg_1', 'type': 'message', 'role': 'assistant',
             'model': 'claude-opus-5-5', 'stop_reason': 'end_turn',
             'stop_sequence': None,
             'content': [{'type': 'text', 'text': json.dumps(result)}],
             'usage': {'input_tokens': 10, 'output_tokens': 5}}
    captured = []
    srv = _serve(reply, captured)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setenv('ANTHROPIC_BASE_URL',
                       'http://127.0.0.1:%d' % srv.server_address[1])
    try:
        doc = prepare(corpus.new_doc('univ_article', 'news', 'u', 't', TEXT,
                                     name='张三', pid='p_1'))
        rec = LLMCoder().code(doc)
    finally:
        srv.shutdown()
    req = captured[0]
    assert req['path'].startswith('/v1/messages')
    assert 'server-side-fallback-2026-07-01' in req['headers'].get(
        'anthropic-beta', '')
    body = req['body']
    assert body['model'] == 'claude-opus-5-5'
    assert body['fallbacks'] == 'default'
    assert body['output_config']['format']['type'] == 'json_schema'
    assert body['system'][0]['cache_control'] == {'type': 'ephemeral'}
    assert '[S002]' in body['messages'][0]['content']
    assert rec['error'] == '' and rec['coder'] == 'claude-opus-5-5'
    assert rec['codes'][0]['indicator'] == 'C30'
    assert rec['verification']['n_dropped'] == 0
