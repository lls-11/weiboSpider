# -*- coding: UTF-8 -*-
"""从国家奖学金事迹中提取可量化的成就指标，作为候选校标。

事迹是压缩后的成就清单，如：
    “发表SCI期刊论文6篇，其中3篇以第一作者在Nature Communications等期刊发表。”
    “获国家发明专利授权2项、国家实用新型专利授权2项。”
    “获“挑战杯”全国大学生课外学术科技作品竞赛特等奖、……三等奖。”
规则按分句（逗号、句号、分号）匹配，数字支持阿拉伯数字与中文数字。

注意：
- 列举后带“等”的（如“获……金奖等”），计数是下限，记在 truncated 中；
- 这些指标与指标编码来自同一段文本，用作校标时要避免把同一句话既算成就又算行为证据。
"""

import re

_CN = {'零': 0, '一': 1, '两': 2, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
       '七': 7, '八': 8, '九': 9, '十': 10}
NUM = r'(\d+|[一两二三四五六七八九十]{1,3})'
_CLAUSE = re.compile(r'[，。；;]')

_PAPER = re.compile(r'论文' + NUM + r'(余)?篇')
_PAPER_ALT = re.compile(NUM + r'(余)?篇[^，。；]{0,12}论文')
_FIRST_N = re.compile(NUM + r'(余)?篇')
_PATENT = re.compile(r'专利(?:授权)?' + NUM + r'(余)?(?:项|件)')
_SOFTWARE = re.compile(r'(?:软件著作权|软著)(?:授权|登记)?' + NUM + r'(余)?(?:项|件)')
_PROJECT = re.compile(r'主持[^，。；]{0,30}?项目' + NUM + r'(余)?项')
_PROJECT_ANY = re.compile(r'主持[^，。；]{0,30}?项目')
_HOURS = re.compile(r'(\d+(?:\.\d+)?)\s*(余)?\s*小时')
_SCHOLAR = re.compile(r'国家奖学金' + NUM + r'次')
_PRIZE = re.compile(r'(特等奖|一等奖|二等奖|三等奖|金奖|银奖|铜奖|冠军|亚军|季军|'
                    r'金牌|银牌|铜牌|优胜奖|特等奖提名|一等奖提名)')
_TOP_JOURNAL = re.compile(
    r'Nature|Science|Cell|PNAS|Lancet|JACS|Angew|Advanced Materials|'
    r'NEJM|JAMA|BMJ|Physical Review Letters|IEEE Trans', re.I)
_HONOR = re.compile(r'(三好学生|优秀学生干部|优秀共青团员|优秀共产党员|自强之星|'
                    r'年度人物|科技新星|优秀学生标兵|十佳|标兵)')
_VENTURE = re.compile(r'(创立|创办|联合创办|注册成立|成立)[^，。；]{0,20}(公司|企业)')

PRIZE_GRADE = {'特等奖': 1, '金奖': 1, '冠军': 1, '金牌': 1, '一等奖': 2,
               '银奖': 2, '亚军': 2, '银牌': 2, '特等奖提名': 2, '二等奖': 3,
               '铜奖': 3, '季军': 3, '铜牌': 3, '一等奖提名': 3, '三等奖': 4,
               '优胜奖': 4}
LEVELS = ('international', 'national', 'provincial', 'other')


def cn_int(s):
    if s.isdigit():
        return int(s)
    if s == '十':
        return 10
    if s.startswith('十'):
        return 10 + _CN.get(s[1:], 0)
    if '十' in s:
        a, b = s.split('十', 1)
        return _CN[a] * 10 + (_CN.get(b, 0) if b else 0)
    return _CN.get(s, 0)


_PROVINCES = ('北京|天津|上海|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|'
              '山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|内蒙古|广西|'
              '西藏|宁夏|新疆|首都')


def prize_level(phrase):
    # “中国国际大学生创新大赛”“中国国际‘互联网+’大赛”是国内赛事
    phrase = phrase.replace('中国国际', '中国')
    if re.search(r'国际|世界|全球|美国|亚洲|亚太|ICPC|iGEM|Kaggle', phrase):
        return 'international'
    if re.search(r'全国|国家级|中国|“挑战杯”|挑战杯|互联网\+|创青春', phrase) and \
            not re.search(r'省级|赛区|省赛|分赛区', phrase):
        return 'national'
    if re.search(r'省|自治区|市|赛区|区域|' + _PROVINCES, phrase):
        return 'provincial'
    return 'other'


def awards(text):
    """返回 [(级别, 等级, 原文片段)]。一个顿号分隔的片段可能含一个奖项。"""
    out = []
    for clause in _CLAUSE.split(text):
        if not _PRIZE.search(clause):
            continue
        last = None
        for piece in re.split(r'[、]', clause):
            # “美国大学生数学建模竞赛一等奖（2023年）、二等奖（2022年）”：
            # 只有奖级的片段沿用前一个赛事的级别
            bare = re.sub(r'[（(][^）)]*[）)]', '', piece).strip()
            for m in _PRIZE.finditer(piece):
                lv = prize_level(piece)
                if lv == 'other' and last and len(bare) <= 8:
                    lv = last
                out.append((lv, PRIZE_GRADE[m.group(1)], piece.strip()))
                last = lv
    return out


def extract(text):
    # 保留分隔符，以便知道“其中……”从哪里开始、在句号处结束
    parts = re.split(r'([，。；;])', text)
    clauses, subset_flags, in_subset = [], [], False
    for i in range(0, len(parts), 2):
        c = parts[i]
        if c.lstrip().startswith('其中'):
            in_subset = True
        if c:
            clauses.append(c)
            subset_flags.append(in_subset)
        if i + 1 < len(parts) and parts[i + 1] in '。；;':
            in_subset = False
    papers = first = patents = granted = software = projects = 0
    hours = 0.0
    truncated = []
    for c, subset in zip(clauses, subset_flags):
        found = _PAPER.findall(c) or _PAPER_ALT.findall(c)
        n = sum(cn_int(x[0]) for x in found)
        # “其中……”到句末的分句是总数的子集，不再计入总数
        if subset:
            n = 0
        if '第一作者' in c or '一作' in c:
            nums = [cn_int(x[0]) for x in _FIRST_N.findall(c)]
            # “发表论文6篇，其中第一作者2篇”在同一分句时取最后一个数
            first += nums[-1] if nums else 0
        papers += n
        for x in _PATENT.findall(c):
            k = cn_int(x[0])
            patents += k
            if '授权' in c:
                granted += k
        for x in _SOFTWARE.findall(c):
            software += cn_int(x[0])
        if _PROJECT_ANY.search(c):
            m = _PROJECT.search(c)
            projects += cn_int(m.group(1)) if m else 1
        if re.search(r'志愿|服务|支教', c):
            for h, _ in _HOURS.findall(c):
                hours += float(h)
        if c.rstrip().endswith('等') and (_PRIZE.search(c) or '论文' in c):
            truncated.append(c.strip()[-20:])
    # 只写“以第一作者发表论文”而未写篇数时，第一作者论文至少 1 篇
    if first == 0 and re.search(r'第一作者[^，。；]{0,12}(发表|论文)', text):
        first = 1
    aw = awards(text)
    best = min((g for _, g, _ in aw), default=None)
    lvl_counts = {lv: sum(1 for x in aw if x[0] == lv) for lv in LEVELS}
    top_level = next((lv for lv in LEVELS if lvl_counts[lv]), '')
    sch = _SCHOLAR.search(text)
    return {
        'papers': papers,
        'papers_first_author': min(first, papers) if papers else first,
        'top_journal_mention': bool(_TOP_JOURNAL.search(text)),
        'patents': patents,
        'patents_granted': granted,
        'software_copyrights': software,
        'projects_led': projects,
        'awards': len(aw),
        'awards_international': lvl_counts['international'],
        'awards_national': lvl_counts['national'],
        'awards_provincial': lvl_counts['provincial'],
        'award_top_level': top_level,
        'award_best_grade': best,
        'honors': len(set(_HONOR.findall(text))),
        'volunteer_hours': hours,
        'national_scholarship_times': cn_int(sch.group(1)) if sch else None,
        'venture': bool(_VENTURE.search(text)),
        'truncated': '；'.join(truncated),
    }


_ENG = ('工程|计算机|软件|电子|电气|通信|机械|自动化|材料|土木|建筑|化工|能源|航空|航天|'
        '交通|测绘|信息|人工智能|智能|集成电路|网络|控制|车辆|船舶|矿|地质工程|石油|环境|'
        '安全|仪器|光电|微电子|制造|技术')
_HUM = ('文学|语言|汉语|外语|英语|新闻|传播|历史|哲学|教育|艺术|设计|音乐|美术|舞蹈|戏剧|'
        '影视|体育|马克思|思想政治')
FIELD_RULES = [
    ('医学', '医|药|护理|口腔|临床|中医|公共卫生'),
    ('农林', '农|林|园艺|畜牧|水产|兽医|植物|动物科学|草业|食品'),
    ('工学', _ENG),
    ('理学', '数学|物理|化学|生物|天文|地理|地质|大气|海洋|统计|心理|生态|力学'),
    ('经管法', '经济|金融|管理|会计|财|商|法学|法律|政治|国际关系|社会|公共'),
    ('人文艺术', _HUM),
]


def field_of(program, school=''):
    """按院系专业名称粗分学科门类，用于学科内比较。"""
    if re.search(r'职业|职业技术|专科', school):
        return '高职'
    for name, pat in FIELD_RULES:
        if re.search(pat, program):
            return name
    return '其他'
