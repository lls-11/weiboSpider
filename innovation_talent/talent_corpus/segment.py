# -*- coding: UTF-8 -*-
"""把一篇写了多人的报道（答辩会、风采展）切分为每人一段。

依据实际抓到的版式整理出几种“人物开头行”：
    电子系—李智毅                                  （答辩实录：院系—姓名）
    艾寒冰，1998年9月生，地球物理与空间……            （姓名，出生年月）
    公共卫生学院2019级……硕士研究生程北京              （院系年级 + 姓名）
    姓名：刘俊莹                                   （字段式）
    谈琪 / 计算机信息工程学院 人工智能专业 2025级……    （姓名单独一行，下一行是院系）
答辩会通讯稿没有人物开头行，改用图片说明里的名单（“依次为：丁恺睿、康吉赢……”），
把以院系加姓名开头的段落分给对应的人。
切分不出多人时返回 None，整篇保留为一份文档。
"""

import re

from . import corpus

_NAME = r'[一-龥]{2,4}'
_HEADERS = [
    ('dash', re.compile(r'^[一-龥]{2,12}[—–-]{1,2}(' + _NAME + r')$')),
    ('born', re.compile(r'^(' + _NAME + r')[，,]?\s?(?:19|20)\d{2}年\d{1,2}月生')),
    ('field', re.compile(r'^姓名[:：]\s*(' + _NAME + r')$')),
    ('dept_tail', re.compile(r'^.{4,40}?(?:\d{4}级).{0,20}?(?:研究生|本科生|博士生|硕士生)\s*(' +
                             _NAME + r')$')),
]
_DEPT_LINE = re.compile(r'(学院|书院|系|研究院|研究所).{0,30}(\d{4}级|本科生|研究生)')
_NAME_LIST = re.compile(r'依次为[:：]([一-龥、，,\s]+)')
_STOP = {'个人简介', '答辩语录', '答辩风采', '成果展示', '科研心得', '发展规划'}


def _headers(lines):
    """返回 [(行号, 姓名, 规则)]。"""
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        for rule, rx in _HEADERS:
            m = rx.match(s)
            if m and m.group(1) not in _STOP:
                out.append((i, m.group(1), rule))
                break
        else:
            # 姓名单独一行、下一行是院系年级
            if re.fullmatch(_NAME, s) and i + 1 < len(lines) and \
                    _DEPT_LINE.search(lines[i + 1]) and s not in _STOP:
                out.append((i, s, 'name_line'))
    return out


def _by_name_list(lines):
    names = []
    for line in lines:
        for m in _NAME_LIST.finditer(line):
            names += [n for n in re.split(r'[、，,\s]+', m.group(1)) if 2 <= len(n) <= 4]
    if len(names) < 2:
        return None
    parts = {}
    for line in lines:
        head = line[:24]
        hit = [n for n in names if n in head]
        if len(hit) == 1 and len(line) > 40:
            parts.setdefault(hit[0], []).append(line)
    return [(n, '\n'.join(ls), 'name_list') for n, ls in parts.items()] or None


def split_people(text, min_people=2):
    lines = [ln for ln in text.split('\n') if ln.strip()]
    heads = _headers(lines)
    # 同一规则至少出现 min_people 次才认为是多人版式，避免误切
    if heads:
        best = max(set(h[2] for h in heads), key=lambda r: sum(h[2] == r for h in heads))
        heads = [h for h in heads if h[2] == best]
    if len(heads) >= min_people:
        out = []
        for k, (i, name, rule) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            out.append((name, '\n'.join(lines[i:end]), rule))
        return out
    return _by_name_list(lines)


_TITLE_NAME = [re.compile(r'[|｜]\s*(' + _NAME + r')[：:]'),
               re.compile(r'获得者(?:之)?\s*(' + _NAME + r')[：:，,]'),
               re.compile(r'——\s*(' + _NAME + r')\s*$'),
               re.compile(r'(?:^|[！!，,\s])(' + _NAME + r')[：:]'),
               re.compile(r'(?:本科生|研究生|博士生)(' + _NAME + r')获得')]


def name_from_title(title):
    t = title.split('-')[0].strip()
    for rx in _TITLE_NAME:
        m = rx.search(t)
        if m:
            return m.group(1)
    return ''


def segment_docs(docs, min_chars=80):
    """把多人文章拆成每人一份文档；单人文章原样保留并标记 segment='whole'。"""
    out = []
    for d in docs:
        parts = split_people(d['text'])
        if not parts:
            name = d.get('name') or name_from_title(d['title'])
            out.append(dict(d, name=name, segment='whole'))
            continue
        for name, text, rule in parts:
            if len(text) < min_chars:
                continue
            out.append(corpus.new_doc(
                d['corpus'], d['source_type'], d['url'], d['title'], text,
                name=name, school=d.get('school', ''), publish_time=d.get('publish_time', ''),
                parent_doc_id=d['doc_id'], segment=rule))
    return out
