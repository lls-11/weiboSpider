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


def test_honor_list_rule():
    assert pc.is_honor_list('曾获国家奖学金、“一二·九”奖学金、清华大学综合优秀奖学金等。')
    assert not pc.is_honor_list('谢廷玉曾用八个月时间梳理“塔克-伍德命题”四十余年的争论，以第二作者的身份发表文章。')
    assert not pc.is_honor_list('自中学时期起，戴言便对计算机产生了浓厚的兴趣，曾获得诸多信息学竞赛金牌；')
    assert not pc.is_honor_list('曾在清华马约翰杯比赛中获得100米蝶泳冠军，也是院里游泳俱乐部的创始人。')


def test_deepseek_backend_offline():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    answer = {'text_type': '过程叙述', 'education': '本科', 'discipline': '工科', 'gender': '男',
              'n_events': '2', 'codes': [
                  {'id': 'c30', 'level': 2, 'stage': '本科', 'quote': '重新设计了三版电路'},
                  {'id': 'C99', 'level': 2, 'stage': '本科', 'quote': 'x'},
                  {'id': 'C10', 'level': 3, 'stage': '本科', 'quote': 'x'}]}
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['content-length'])))
            seen.append((self.path, self.headers.get('Authorization'), body))
            if 'response_format' in body:      # 模拟不支持 JSON 模式的模型
                data, code = b'{"error": "response_format not supported"}', 400
            else:
                data, code = json.dumps({'model': 'deepseek-test', 'choices': [{
                    'finish_reason': 'stop', 'message': {
                        'content': '```json\n' + json.dumps(answer, ensure_ascii=False) + '\n```'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}).encode(), 200
            self.send_response(code)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        coder = pc.CompatCoder(base_url='http://127.0.0.1:%d' % srv.server_address[1], api_key='k')
        rec = coder.code(pc.group_people([DOC])[0])
    finally:
        srv.shutdown()
    path, auth, body = seen[-1]
    assert path == '/chat/completions' and auth == 'Bearer k'
    assert body['model'] == 'deepseek-chat' and body['temperature'] == 0.0
    assert '输出格式' in body['messages'][0]['content']
    assert len(seen) == 2 and 'response_format' not in body
    res = rec['result']
    assert rec['error'] == '' and rec['served_by'] == 'deepseek-test'
    assert res['discipline'] == '不详' and res['n_events'] == 2 and res['dropped_invalid'] == 2
    assert [c['id'] for c in res['codes']] == ['C30'] and res['codes'][0]['verified']
