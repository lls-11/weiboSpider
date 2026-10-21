# -*- coding: UTF-8 -*-
from datetime import date

from talent_corpus import extract
from talent_corpus.sources import articles, nobel, rmrb

RMRB_LAYOUT_NEW = '''<html><body>
<div class="swiper-container">
  <a href="node_01.html">01版：要闻</a>
  <a href="node_05.html">05版：国家奖学金</a>
  <a href="node_06.html">06版：国家奖学金</a>
  <a href="../../03/node_01.html">上一期</a>
</div>
<ul class="news-list">
  <li><a href="../../../content/202605/04/content_30154802.html">名录</a></li>
  <li><a href="../../../content/202605/04/content_30154802.html">名录</a></li>
</ul>
</body></html>'''

RMRB_LAYOUT_OLD = '''<html><body>
<a href="nbs.D110000renmrb_01.htm">01</a>
<a href="nbs.D110000renmrb_06.htm">06</a>
<a href="nw.D110000renmrb_20240504_1-06.htm">名录</a>
<a href="../03/nw.D110000renmrb_20240503_1-01.htm">前一天</a>
</body></html>'''

RMRB_ARTICLE = '''<html><body><div class="article">
<h1>2024—2025学年度本专科生国家奖学金获奖学生代表名录</h1>
<div id="ozoom">
<p>全国共有12万名本专科学生荣获2024—2025学年度本专科生国家奖学金，以下100名学生是他们中的优秀代表。</p>
<p><strong>张三</strong>　清华大学电子工程系2021级本科生。大二时主动联系课题组，参与低功耗芯片设计。</p>
<p>此外，清华大学为他提供了实验平台。</p>
<p><strong>李四</strong>　浙江大学机械工程学院2020级本科生。三次参加机器人竞赛，前两次失败后重新设计底盘。</p>
<p>王五，复旦大学数学科学学院2021级本科生，自学拓扑学并在讨论班报告。</p>
</div></div></body></html>'''


def test_rmrb_new_layout_links():
    base = 'https://paper.people.com.cn/rmrb/pc/layout/202605/04/node_01.html'
    pages = rmrb.page_urls(RMRB_LAYOUT_NEW, base, 'new')
    assert pages[0] == base and len(pages) == 3
    assert pages[-1].endswith('/pc/layout/202605/04/node_06.html')
    arts = rmrb.article_urls(RMRB_LAYOUT_NEW, base, 'new')
    assert arts == ['https://paper.people.com.cn/rmrb/pc/content/202605/04/'
                    'content_30154802.html']


def test_rmrb_old_layout_links():
    base = 'https://paper.people.com.cn/rmrb/html/2024-05/04/nbs.D110000renmrb_01.htm'
    assert len(rmrb.page_urls(RMRB_LAYOUT_OLD, base, 'old')) == 2
    arts = rmrb.article_urls(RMRB_LAYOUT_OLD, base, 'old')
    assert len(arts) == 1
    assert arts[0].endswith('2024-05/04/nw.D110000renmrb_20240504_1-06.htm')


def test_rmrb_page_one_urls():
    fmt_urls = rmrb.page_one_urls(date(2024, 5, 4))
    assert fmt_urls[0][1].endswith('html/2024-05/04/nbs.D110000renmrb_01.htm')
    assert fmt_urls[1][1].endswith('pc/layout/202405/04/node_01.html')
    assert rmrb.page_one_urls(date(2026, 5, 4))[0][0] == 'new'


def test_rmrb_parse_entries():
    entries = rmrb.parse_entries(rmrb.article_paragraphs(RMRB_ARTICLE))
    assert [e['name'] for e in entries] == ['张三', '李四', '王五']
    zs = entries[0]
    assert zs['school'] == '清华大学'
    assert '2021级本科生' in zs['program']
    # “此外，清华大学……”不能被当作新条目，应并入张三
    assert '实验平台' in zs['text']
    assert entries[0]['parse_method'] == 'bold'
    assert entries[2]['parse_method'] == 'regex'


def test_rmrb_to_docs_and_meta():
    art = {'date': '2026-05-04', 'page': 5, 'url': 'u',
           'title': '2024—2025学年度本专科生国家奖学金获奖学生代表名录',
           'paragraphs': rmrb.article_paragraphs(RMRB_ARTICLE)}
    docs = rmrb.to_docs(art)
    assert len(docs) == 3
    assert docs[0]['level'] == 'undergraduate'
    assert docs[0]['award_year'] == '2024-2025'
    assert docs[0]['person_id'] != docs[1]['person_id']
    assert rmrb.list_level('2025年研究生国家奖学金获奖学生代表名录') == 'graduate'
    assert rmrb.to_docs(dict(art, title='中等职业教育国家奖学金获奖学生代表名录')) == []


WECHAT = '''<html><head><meta charset="utf-8"></head><body>
<h1 id="activity-name"> 国奖学子｜张三：在芯片里找答案 </h1>
<div id="js_content"><section><p>大二那年，张三第一次走进实验室。</p>
<p>他把仿真结果和测量数据逐项对照，发现了一个被忽略的漏电问题。</p>
<p>此后半年，他重新设计了三版电路，功耗降低了40%。</p></section></div>
<script>var ct = "1714800000";</script></body></html>'''

VSB = '''<html><head><meta charset="gb2312"><title>学校新闻网</title></head><body>
<div class="nav">首页 新闻</div><h1>李四：三战机器人大赛</h1>
<div class="info">发布时间：2025-05-06</div>
<div class="v_news_content"><p>李四所在团队连续三年参加全国大学生机器人大赛。</p>
<p>第一次比赛，底盘在决赛中断裂，团队止步八强。</p>
<p>赛后他逐帧回看录像，把底盘从铝合金改为碳纤维，并重写了控制算法。</p></div>
</body></html>'''


def test_extract_wechat():
    r = extract.extract(WECHAT, 'https://mp.weixin.qq.com/s/abc')
    assert r['extractor'] == 'wechat'
    assert r['title'].startswith('国奖学子')
    assert r['text'].count('\n') == 2
    assert r['publish_time'].startswith('2024-05')


def test_extract_wechat_blocked():
    page = '<html><body><p>环境异常</p><p>完成验证后即可继续访问</p></body></html>'
    r = extract.extract(page, 'https://mp.weixin.qq.com/s/abc')
    assert r['blocked'] is True


def test_extract_vsb_and_gbk_decoding():
    from talent_corpus.fetch import decode_html
    html_text = decode_html(VSB.encode('gb18030'))
    r = extract.extract(html_text, 'https://news.example.edu.cn/info/1.htm')
    assert r['extractor'] == 'visualsitebuilder'
    assert r['title'] == '李四：三战机器人大赛'
    assert r['publish_time'] == '2025-05-06'
    assert '碳纤维' in r['text'] and '首页' not in r['text']


def test_extract_density_fallback():
    page = ('<html><body><div><p>导航</p></div><div class="x">' +
            ''.join('<p>这是一段足够长的正文内容，用来测试按段落密度选择正文容器。</p>'
                    for _ in range(5)) + '</div></body></html>')
    r = extract.extract(page)
    assert r['extractor'] == 'density' and '导航' not in r['text']


def test_search_sheet(tmp_path):
    out = tmp_path / 's.csv'
    n = articles.make_search_sheet([{'name': '张三', 'school': '清华大学',
                                     'person_id': 'p_1'}], str(out))
    assert n == 1
    text = out.read_text(encoding='utf-8-sig')
    assert 'weixin.sogou.com' in text and 'p_1' in text


NOBEL_LAUREATE = {
    'id': '218', 'knownName': {'en': 'Richard P. Feynman'}, 'gender': 'male',
    'birth': {'date': '1918-05-11'},
    'nobelPrizes': [{'awardYear': '1965', 'category': {'en': 'Physics'},
                     'motivation': {'en': 'for their fundamental work'},
                     'links': [{'rel': 'external', 'href':
                                'https://www.nobelprize.org/prizes/physics/1965/summary/'}]}],
    'links': [{'rel': 'external', 'href':
               'https://www.nobelprize.org/prizes/physics/1965/feynman/facts/'}],
}


def test_nobel_record():
    r = nobel._laureate_record(NOBEL_LAUREATE, 'phy')
    assert r['bases'] == ['https://www.nobelprize.org/prizes/physics/1965/feynman/']
    assert r['birth_year'] == '1918' and r['prizes'][0]['year'] == '1965'


def test_nobel_voice():
    auto = 'I was born in 1918. My father taught me to notice things. ' * 20
    bio = 'He was born in 1918. His father worked in uniforms. ' * 20
    assert nobel.narrative_voice(auto) == 'self'
    assert nobel.narrative_voice(bio) == 'narrator'
