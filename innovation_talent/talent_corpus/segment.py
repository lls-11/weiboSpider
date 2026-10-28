# -*- coding: UTF-8 -*-
"""把一篇写了多人的报道（答辩会、风采展）切分为每人一段。

依据实际抓到的版式整理出几种“人物开头行”：
    电子系—李智毅 / 胡耀文—物理系                   （答辩实录：院系—姓名，或倒序）
    伍绍文 人文学院                                 （姓名 院系）
    艾寒冰，1998年9月生，地球物理与空间……            （姓名，出生年月）
    公共卫生学院2019级……硕士研究生程北京              （院系年级 + 姓名）
    姓名：刘俊莹                                   （字段式）
    谈琪 / 计算机信息工程学院 人工智能专业 2025级……    （姓名单独一行，后两行内有院系、
                                                   单独的院系名或“男，汉族……”）
答辩会通讯稿没有人物开头行，改用图片说明里的名单（“依次为：丁恺睿、康吉赢……”），
把以院系加姓名开头的段落分给对应的人。
切分不出多人时返回 None，整篇保留为一份文档。
"""

import re

from . import corpus

_NAME = r'[一-龥]{2,4}'
_DEPT = r'[一-龥（）()]{1,14}(?:系|学院|书院|研究院|研究所|中心)'
_HEADERS = [
    ('dash_rev', re.compile(r'^(' + _NAME + r')\s*[—–-]{1,2}\s*' + _DEPT + r'$')),
    ('dash', re.compile(r'^[一-龥]{2,12}[—–-]{1,2}(' + _NAME + r')$')),
    ('name_dept', re.compile(r'^(' + _NAME + r')\s+' + _DEPT + r'$')),
    ('born', re.compile(r'^(' + _NAME + r')[，,]?\s?(?:19|20)\d{2}年\d{1,2}月生')),
    ('field', re.compile(r'^姓名[:：]\s*(' + _NAME + r')$')),
    ('dept_tail', re.compile(r'^.{4,40}?(?:\d{4}级).{0,20}?(?:研究生|本科生|博士生|硕士生)\s*(' +
                             _NAME + r')$')),
]
_DEPT_LINE = re.compile(r'(学院|书院|系|研究院|研究所).{0,30}(\d{4}级|本科生|研究生|博士生)')
_DEPT_ONLY = re.compile(r'^' + _DEPT + r'$')
_GENDER_LINE = re.compile(r'^[男女][，,]')
_NAME_LIST = re.compile(r'依次为[:：]([一-龥、，,\s]+)')
_STOP = {'个人简介', '答辩语录', '答辩风采', '成果展示', '科研心得', '发展规划', '答辩现场', '人物简介',
         '序号', '姓名', '院系'}
_NOT_NAME_TAIL = re.compile(r'(感悟|心得|规划|展示|简介|语录|经历|成果|评语|寄语|风采)$')
# 同一篇里可能混用“院系—姓名”和“姓名 院系”，这几种按一类计数
_FAMILY = {'dash_rev': 'name_and_dept', 'dash': 'name_and_dept', 'name_dept': 'name_and_dept'}


def _as_name(s):
    """单独成行的姓名：去掉中间空白（“刘 强”），允许少数民族姓名中的“·”。"""
    c = re.sub(r'\s+', '', s)
    if c in _STOP or _NOT_NAME_TAIL.search(c):
        return None
    if re.fullmatch(_NAME, c) or re.fullmatch(r'[一-龥]{2,8}·[一-龥]{2,8}', c):
        return c
    return None


def _person_follows(lines, i):
    """姓名行后两行内出现院系年级、单独的院系名或“男，汉族……”，视为人物开头。"""
    for j in (i + 1, i + 2):
        if j >= len(lines):
            return False
        nxt = lines[j].strip()
        if _DEPT_LINE.search(nxt) or _DEPT_ONLY.match(nxt) or _GENDER_LINE.match(nxt):
            return True
        if _as_name(nxt):          # 下一行又是姓名：这是名单，不是开头
            return False
    return False


def _headers(lines):
    """返回 [(行号, 姓名, 规则)]。"""
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        for rule, rx in _HEADERS:
            m = rx.match(s)
            if m and m.group(1) not in _STOP and not _NOT_NAME_TAIL.search(m.group(1)):
                out.append((i, m.group(1), rule))
                break
        else:
            name = _as_name(s)
            if name and _person_follows(lines, i):
                out.append((i, name, 'name_line'))
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
        fam = [_FAMILY.get(h[2], h[2]) for h in heads]
        best = max(set(fam), key=fam.count)
        heads = [h for h, f in zip(heads, fam) if f == best]
    if len(heads) >= min_people:
        best_part = {}
        for k, (i, name, rule) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            text = '\n'.join(lines[i:end])
            if name not in best_part or len(text) > len(best_part[name][1]):
                best_part[name] = (name, text, rule)
        # 文末结果表里一行一个姓名，只有姓名的段落不算
        out = [v for v in best_part.values() if len(v[1]) > len(v[0]) + 20]
        return out if len(out) >= min_people else None
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
