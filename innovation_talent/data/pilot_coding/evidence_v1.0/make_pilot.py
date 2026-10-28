# -*- coding: UTF-8 -*-
"""手册 1.0 证据编码试编（5 篇）。

编码者是 Claude，在研究会话中按 prompts/evidence_coding_v1.0.md 逐篇阅读编码，没有通过 API 调用；
结果经 talent_corpus.coding.evidence 的同一套程序核对并导出，用来检查提示词、输出格式
和核对规则是否可用。只有一名编码者，未经信度检验，不作为正式数据。

运行（innovation_talent 目录下）：python data/pilot_coding/evidence_v1.0/make_pilot.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

from talent_corpus import corpus  # noqa: E402
from talent_corpus.coding import evidence as ev  # noqa: E402

CODER = 'claude-session-pilot'
SOURCES = [os.path.join(ROOT, 'data', 'long_texts', 'analysis_set.jsonl'),
           os.path.join(ROOT, 'data', 'nobel', 'texts', 'biographical.jsonl'),
           os.path.join(ROOT, 'data', 'nobel', 'texts', 'interview.jsonl')]

BASE = {'creative_phase': ['未明确'], 'event_time': None, 'age_at_event': None,
        'age_basis': None, 'education_stage': None, 'domain': None,
        'elicitation': '未知', 'context_support': []}


def E(pid, eid, ev_id, ind, sub, quotes, form, direction, ctx, link, attr,
      voice, details, interp, limit, **kw):
    e = dict(BASE, evidence_id=eid, person_id=pid, event_id=ev_id,
             indicator_id=ind, subcode=sub,
             quotes=[{'paragraph_id': p, 'quote': q} for p, q in quotes],
             form=form, direction=direction, creative_context=ctx,
             process_link=link, attribution=attr, voice=voice,
             indicator_details=[{'field': k, 'value': v}
                                for k, v in details.items()],
             interpretation=interp, limitation=limit)
    e.update(kw)
    return e


def screening(pid, evidence, reasons, default):
    rows = []
    for t in ev.INDICATORS:
        ids = [e['evidence_id'] for e in evidence if e['indicator_id'] == t]
        rows.append({'person_id': pid, 'indicator_id': t,
                     'status': 'completed',
                     'reason': reasons.get(t, default),
                     'evidence_ids': ids})
    return rows


# ---------------------------------------------------------------- 邓禹
P = 'p_2efae55fe306'
deng = [
    E(P, 'E001', 'EV001', 'T06', 'T06c',
      [('L23', '刚开始接触科研时，还没有从本科的学习思路转变过来，很多时候觉得无所适从，效率较为低下'),
       ('L23', '后来通过和导师的交谈，学习前辈们的科研方式，逐渐明白了做科研要以解决问题为导向，围绕一个特定的问题，去搜索相关文献资料，从中找到自己需要的内容，为解决问题而服务')],
      '行为', '支持', '未建立', 'P2', '本人', '本人',
      {'before': '沿用本科学习思路，无所适从、效率低', 'after': '围绕特定问题检索文献、为解决问题服务'},
      '有学习需要（效率低、无所适从）与学习方式改变前后两端，符合 T06c“基于需要或反馈的学习方式改变”；文中说明新方式服务于解决问题，记 P2。',
      '“逐渐明白了”偏认识变化，未交代某一具体问题上的检索行为与后续结果；导师与前辈是改变的直接来源。',
      creative_phase=['学习准备'], education_stage='研究生（刚开始接触科研时）',
      domain='半导体激光', elicitation='一般经历提问',
      context_support=['导师交谈', '前辈的科研方式']),
    E(P, 'E002', 'EV002', 'T07', 'T07a',
      [('L24', '在实验早期的两三个月内，我一直没有观测到我们所预期的混沌现象，甚至都开始怀疑设想是否正确'),
       ('L24', '我又调整好了心态，耐下心来仔细观测，终于功夫不负有心人，经过对整个实验装置的反复优化调试，最后实验结果很理想')],
      '行为', '支持', '明确', 'P3', '本人', '本人',
      {'obstacle': '两三个月未观测到预期混沌现象', 'subsequent_action': '继续仔细观测，反复优化调试实验装置',
       'support': '导师鼓励并以理论分析说明有成功预期'},
      '明确困难（长期未观测到预期现象）与其后的继续行动，符合 T07a；同一事件交代了问题、行动和后续结果（开发出超混沌激光源），记 P3。成果有发表评价，创造情境记明确。',
      '继续投入紧接导师的鼓励与理论判断，不能全部归于本人；“反复优化调试”未交代调整前后的具体策略，故不记 T07b。',
      creative_phase=['求解', '实施迭代'], education_stage='博士研究生',
      domain='中红外激光', elicitation='一般经历提问',
      context_support=['导师王成教授的鼓励与理论分析']),
    E(P, 'E003', 'EV002', 'T14', None,
      [('L24', '甚至都开始怀疑设想是否正确'),
       ('L24', '我的导师王成教授却一直鼓励我再多尝试一番，并以理论知识分析说明实验是有成功预期的')],
      '行为', '不确定', '明确', 'P1', '本人', '本人',
      {'uncertainty': '设想是否正确尚不清楚', 'response': '导师给出理论判断后继续实验',
       'support': '导师的理论分析与鼓励'},
      '文本写出了对设想正确性的未知，但对未知的处理主要是导师给出判断，本人随后继续实验，接近排除条件“老师给出结论后照做但未处理未知”。',
      '未见本人针对“设想是否正确”的探查、比较或暂缓结论；按手册试编码例子保留为待核，不判支持。',
      creative_phase=['求解'], education_stage='博士研究生', domain='中红外激光',
      elicitation='一般经历提问', context_support=['导师王成教授']),
    E(P, 'E004', 'EV002', 'T13', None,
      [('L24', '实验最佳条件都需要手动去调谐光路中的每个元件并一点点寻找'),
       ('L24', '经过对整个实验装置的反复优化调试')],
      '材料不足', '不确定', '明确', 'P1', '本人', '本人',
      {'check_target': '光路元件与实验条件', 'dimensions_or_comparison': None,
       'action': '逐个调谐元件、反复优化调试', 'observation': None},
      '有检查对象（光路各元件），但未交代检查维度或对照关系。',
      '按手册，“反复调试”未交代检查维度只能作线索。',
      creative_phase=['实施迭代'], education_stage='博士研究生', domain='中红外激光',
      elicitation='一般经历提问'),
    E(P, 'E005', 'EV003', 'T06', 'T06a',
      [('L28', '我是规定自己少休息半小时或一小时，努力用最短、最有效的时间去完成学生干部的工作')],
      '行为', '支持', '未建立', 'P0', '本人', '本人',
      {'plan_content': '每天少休息半小时到一小时处理学生干部工作，不挤占科研时间'},
      '有具体时间安排及其目的（不挤占学习科研时间），作为习惯事件记 T06a。',
      '安排对象是学生工作时间，与学习或研究过程本身的联系弱；回答由“如何平衡”的问题引出。',
      education_stage='博士研究生', elicitation='直接特征提问'),
    E(P, 'E006', 'EV004', 'T06', 'T06b',
      [('L31', '我会在课下进行相应的复习并查漏补缺')],
      '声明', '不确定', '未建立', 'P0', '本人', '本人',
      {'monitor_basis': '课后复习、查漏补缺'},
      '自述有理解检查的习惯，但没有具体事件或检查依据。',
      '泛化的学习习惯，回答由“如何自主学习”的问题引出。',
      education_stage='研究生', elicitation='直接特征提问'),
    E(P, 'E007', 'EV005', 'T02', None,
      [('L34', '我的科研动力是喜欢探索和解决新的问题所带来的喜悦感和获得感，更多要依靠自我的内驱动力')],
      '声明', '不确定', '未建立', 'P0', '本人', '本人',
      {'choice': None, 'endorsed_reason': '喜欢探索和解决新问题带来的喜悦感', 'external_requirement': None},
      '有本人表达的认可理由，但没有对应的具体选择或持续行动，记声明。',
      '回答由“你的科研动力是什么”直接引出。',
      elicitation='直接特征提问'),
]
deng_reasons = {
    'T03': '已核读全文。L23 的文献检索是一般学习方式，未指向某一未知问题，已记入 T06c；未找到独立的 T03 证据。',
    'T04': '已核读全文。只有兴趣表述（L34、L43），没有跨时点参与的材料。',
    'T07': '已核读全文。EV002 记 T07a；未交代调整前后策略，未记 T07b。',
    'T11': '已核读全文。L40“记录下来然后暂时放下”是情绪调节，不是证据驱动的修订。',
}
deng_default = '已核读全文（L1–L7 为学院导语，不属本人），未找到符合纳入条件的材料。'

# ---------------------------------------------------------------- 张如范
P = 'p_92373c52e419'
zhang = [
    E(P, 'E001', 'EV001', 'T02', None,
      [('L11', '在家长和老师的建议下，“心不甘情不愿”地去了第二志愿的院校'),
       ('L12', '他还是毅然决然地做出一个旁人看来近乎“疯狂”的决定——退学'),
       ('L13', '回忆起当时的决定，张如范说自己想得很简单，“就是不想让自己后悔。”')],
      '行为', '支持', '未建立', 'P0', '多人', '本人',
      {'choice': '退学复读', 'endorsed_reason': '不想让自己后悔；追求学术梦想',
       'external_requirement': '此前按家长和老师建议入读第二志愿'},
      '有具体选择（退学）和本人表达的认可理由，并与先前的外部建议形成对照，符合 T02。',
      '理由由记者转述的直接引语给出；“学术梦想”内容不具体，不支持 T01。',
      event_time='2004—2005年', education_stage='本科一年级至复读',
      domain=None, creative_phase=['方向选择']),
    E(P, 'E002', 'EV002', 'T07', 'T07a',
      [('L16', '催化剂就是无法挂载到碳纳米管上，更别提研究反应机理'),
       ('L16', '但天生乐观的他并没有因此放弃，而是继续在这个课题上努力')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'obstacle': '催化剂无法挂载到碳纳米管上', 'subsequent_action': '继续在课题上努力',
       'strategy_before': None, 'strategy_after': None, 'support': '魏飞教授课题组'},
      '明确阻碍与其后的继续行动，符合 T07a；后续 L17 有结果变化，记 P3。',
      '“天生乐观”是记者归因；继续行动的具体内容见 E003（T07b）。',
      event_time='2009年春', education_stage='本科毕业设计', domain='碳纳米材料',
      creative_phase=['求解'], context_support=['魏飞教授课题组']),
    E(P, 'E003', 'EV002', 'T07', 'T07b',
      [('L16', '催化剂就是无法挂载到碳纳米管上'),
       ('L17', '他决定先尝试在碳纳米管上挂载别的颗粒，摸清其中的原理，再来做魏飞老师安排的课题')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'obstacle': '催化剂无法挂载', 'subsequent_action': '先挂载其他颗粒摸清原理',
       'strategy_before': '直接挂载指定催化剂', 'strategy_after': '先用其他颗粒探明挂载原理，再回到原课题',
       'support': '魏飞教授课题组'},
      '有困难、改变前后的策略（直接挂载 → 先用其他颗粒摸原理）以及回到原课题的推进意图，符合 T07b。',
      '策略改变由记者叙述，本人回忆只涉及试验数量。',
      event_time='2009年春', education_stage='本科毕业设计', domain='碳纳米材料',
      creative_phase=['求解']),
    E(P, 'E004', 'EV002', 'T05', None,
      [('L16', '魏飞教授最初给张如范制定的“练手”课题是利用碳纳米管挂载某种催化剂，研究其反应机理'),
       ('L17', '他决定先尝试在碳纳米管上挂载别的颗粒')],
      '行为', '支持', '可能', 'P2', '记者或传记作者', '记者或作者',
      {'initiative_scope': '子问题：用其他颗粒摸清挂载原理', 'proposer': '本人',
       'first_action': '试验几十种材料', 'co_initiators': None},
      '总任务由导师制定，本人提出并启动子问题，符合“教师提出总任务但学生自主提出子问题时，只编码该子问题的发起”。',
      '“他决定”是记者叙述，导师是否参与子问题的提出未交代。',
      event_time='2009年春', education_stage='本科毕业设计', domain='碳纳米材料',
      creative_phase=['问题发现'], context_support=['导师制定总课题']),
    E(P, 'E005', 'EV002', 'T03', None,
      [('L17', '摸清其中的原理'),
       ('L17', '他大概累计试验了几十种材料，每一种从设计到准备再到操作，都要花费几天的时间')],
      '行为', '支持', '明确', 'P3', '多人', '本人',
      {'unknown_question': '颗粒挂载到碳纳米管上的原理', 'search_action': '累计试验几十种材料',
       'prompted_by_other': '否（总课题由导师给出）', 'finding': 'TiO2 颗粒散射可见光，可在光学显微镜下观察单根碳纳米管'},
      '有知识缺口（挂载原理）和为弄清它进行的试验，符合 T03；有探索所得，记 P3。',
      '试验数量来自本人回忆，目的由记者叙述。',
      event_time='2009年春', education_stage='本科毕业设计', domain='碳纳米材料',
      creative_phase=['问题发现', '求解']),
    E(P, 'E006', 'EV002', 'T12', None,
      [('L17', '先尝试在碳纳米管上挂载别的颗粒，摸清其中的原理，再来做魏飞老师安排的课题'),
       ('L17', '他发现挂载Ti02颗粒的碳纳米管，由于颗粒对可见光有很强的散射能力，从而实现了光学显微镜下单根碳纳米管的可视化观察'),
       ('L17', '他敏感地意识到这一偶然发现背后的意义，很快便利用这种现象设计出一种简单但有效的测量单根碳纳米管力学性质的方法')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'representation_before': '颗粒挂载是为原催化剂课题摸清原理的预备步骤',
       'representation_after': '颗粒散射成为观察和测量单根碳纳米管的手段',
       'changed_element': '对象关系与用途（副现象转为测量手段）',
       'path_change': '设计单根碳纳米管力学性质测量方法'},
      '改变前后对颗粒挂载作用的理解均可定位，并导致新的求解方向，与手册中 Mullis“副效应转为新用途”的重表征线索同类。',
      '“意识到意义”是记者概括，未写本人如何理解；也可解释为 T11b（新观察引起行动改变），需人工裁定。',
      event_time='2009年春', education_stage='本科毕业设计', domain='碳纳米材料',
      creative_phase=['问题发现', '想法生成']),
    E(P, 'E007', 'EV003', 'T06', 'T06b',
      [('L19', '他平均每十天半个月，便要总结反思自己这段时间的科研成果，对于自己的错误、懒惰、懈怠，认真地进行自我批判')],
      '行为', '支持', '未建立', 'P1', '多人', '记者或作者',
      {'monitor_basis': '每十天半个月总结反思科研进展与错误'},
      '有频率的进展检查习惯，符合 T06b 的习惯事件。',
      '与成果的联系（“成果的基石”）是记者断言，记 P1。',
      education_stage='博士研究生', domain='碳纳米材料'),
    E(P, 'E008', 'EV004', 'T07', 'T07a',
      [('L21', '在从事超长碳纳米管制备的过程中，他经常会遇到碳纳米管停止生长的情况。多次失败后，他常常习惯于把以往所有的实验数据进行整理和分析，努力从中寻找蛛丝马迹')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'obstacle': '碳纳米管停止生长，多次失败', 'subsequent_action': '整理分析以往全部实验数据',
       'strategy_before': None, 'strategy_after': None, 'support': None},
      '明确阻碍与其后的继续行动，后续建立模型并制备出半米长碳管，记 P3。',
      '“习惯于”表示反复发生，具体哪一次失败未交代。',
      education_stage='博士研究生', domain='碳纳米材料', creative_phase=['求解']),
    E(P, 'E009', 'EV004', 'T03', None,
      [('L21', '把以往所有的实验数据进行整理和分析，努力从中寻找蛛丝马迹'),
       ('L22', '他从那些看似杂乱无章的数据中发现了相互间的联系，并由此建立一种能成功描述超长碳纳米管生长的模型')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'unknown_question': '碳纳米管为何停止生长', 'search_action': '整理分析以往全部数据',
       'prompted_by_other': None, 'finding': '数据间的联系与生长模型'},
      '面对未解释的停止生长，以数据分析寻求解释并有所得，符合 T03。',
      '未知问题由记者概括；分析方法未交代，不记 T13。',
      education_stage='博士研究生', domain='碳纳米材料',
      creative_phase=['问题发现', '想法生成']),
    E(P, 'E010', 'EV004', 'T11', 'T11a',
      [('L22', '在此理论模型下，以前所有的数据，哪怕是曾经认为的“垃圾数据”都能得到合理的解释'),
       ('L22', '依据这种机理模型的指导，张如范历经3年钻研，终于成功制备出单根长度达到半米的碳纳米管')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'before': '部分数据被认为是“垃圾数据”', 'new_evidence': '数据间的联系与生长模型',
       'after': '这些数据得到合理解释，并以模型指导制备'},
      '原判断（垃圾数据）、新证据（数据联系）与判断修订三要素齐备，符合 T11a。',
      '“曾经认为”的主体未明确是本人还是团队；判断变化由记者叙述。',
      education_stage='博士研究生', domain='碳纳米材料',
      creative_phase=['想法生成', '评价验证']),
    E(P, 'E011', 'EV005', 'T07', 'T07b',
      [('L26', '常规的做法是单根碳纳米管固定在专门的力学仪器上进行测量。这种测量一般需要精度达到纳米级的专业设备。可是张如范所在的实验室并没有这类设备，怎么办？'),
       ('L27', '张如范创新性地提出，利用一根毛细管从悬空碳纳米管侧面“吹气”，使其发生弯曲')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'obstacle': '实验室没有纳米级力学测量设备', 'subsequent_action': '提出吹气弯曲测量法',
       'strategy_before': '常规做法：固定在专门力学仪器上测量', 'strategy_after': '毛细管吹气使碳管弯曲并据此计算受力',
       'support': '可到外单位合作（L25）'},
      '有阻碍、改变前后的方法和继续推进，符合 T07b；后续做出沟槽并发表，记 P3。',
      '“创新性地”是记者评价；方法改变是否由本人独立提出未见本人陈述。',
      education_stage='博士研究生', domain='碳纳米材料', creative_phase=['想法生成', '求解']),
    E(P, 'E012', 'EV005', 'T05', None,
      [('L27', '张如范创新性地提出，利用一根毛细管从悬空碳纳米管侧面“吹气”'),
       ('L27', '首先需要使碳纳米管生长在具有一定沟槽的硅片基底上')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'initiative_scope': '吹气法测量碳纳米管力学性质', 'proposer': '本人',
       'first_action': '设法制作带沟槽的硅片基底', 'co_initiators': None},
      '提出者可辨认（本人），并有首步行动（制作沟槽），符合 T05。',
      '与导师、团队的分工未交代。',
      education_stage='博士研究生', domain='碳纳米材料', creative_phase=['想法生成']),
    E(P, 'E013', 'EV005', 'T09', None,
      [('L27', '而在硅片上刻槽的传统方法是微加工工艺，成本很高，制作一个符合实验要求的沟槽，成本接近万元'),
       ('L27', '既然微加工方法如此之贵，何不将三块硅片上下拼接在一起，形成一个沟槽？')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'shared_problem': '制作符合实验要求的沟槽', 'perspective_1': '微加工刻槽（成本近万元）',
       'perspective_2': '三块硅片拼接成槽', 'consideration_action': '以成本比较后转向拼接方案'},
      '同一问题下有两个实质不同的方案，并以成本为依据作取舍，符合 T09。',
      '比较维度只有成本一项，由记者叙述。',
      education_stage='博士研究生', domain='碳纳米材料', creative_phase=['想法生成']),
    E(P, 'E014', 'EV005', 'T07', 'T07b',
      [('L27', '没有能够耐受1000摄氏度实验高温且不挥发不影响碳纳米管生长的粘合剂。张如范尝试了大料有机和无机材料，都没有成功'),
       ('L27', '何不用金属箔片作为粘合剂呢？他将小片铝箔放在硅片之间，然后在高温下将铝箔熔化')],
      '行为', '支持', '明确', 'P3', '记者或传记作者', '记者或作者',
      {'obstacle': '没有耐高温且不影响生长的粘合剂', 'subsequent_action': '改用铝箔熔化粘接',
       'strategy_before': '尝试各种有机、无机粘合材料', 'strategy_after': '用金属箔片熔化后凝固粘接',
       'support': '与师姐聊天时得到启发'},
      '困难、策略前后与继续推进齐备，符合 T07b；做出沟槽，记 P3。',
      '新想法出现在与师姐的聊天中，启发来源与本人贡献的比例不清；原文“大料”疑为“大量”的错字，引文照录。',
      education_stage='博士研究生', domain='碳纳米材料', creative_phase=['求解'],
      context_support=['师姐']),
    E(P, 'E015', 'EV006', 'T10', None,
      [('L5', '4年前，他从石油化工领域，转行到陌生的碳纳米材料领域'),
       ('L16', '这个课题对于之前从未接触碳纳米管相关知识的张如范而言简直难于登天')],
      '材料不足', '不确定', '可能', 'P0', '记者或传记作者', '记者或作者',
      {'prior_experience': '石油化工本科', 'new_demand': '陌生的碳纳米材料领域',
       'choice': None, 'action': '进入魏飞课题组做毕业设计'},
      '原有经验与新要求均有文本依据，但未交代转行是否出于本人选择。',
      '缺少选择主动性的证据，不能判 T10。',
      event_time='2009年', education_stage='本科毕业至直博', domain='碳纳米材料',
      creative_phase=['方向选择']),
]
zhang_reasons = {
    'T01': '已核读全文。“学术梦想”“一番事业”（L12、L13）没有具体方向或问题，不记目标证据。',
    'T04': '已核读全文。有3—4年的持续研究（L21—L23），但只有“坚持”“付出”的表述，没有兴趣依据。',
    'T08': '已核读全文。L25 提到碳纳米管跨多个学科，但未见来源知识与目标问题的映射。',
    'T13': '已核读全文。数据分析（L21）与吹气测量（L27）均未交代检查维度或对照。',
    'T14': '已核读全文。困难多有交代，但没有对未知本身的处理（如暂缓结论、比较解释）。',
}
zhang_default = '已核读全文，未找到符合纳入条件的材料。'

# ---------------------------------------------------------------- 高焕昂
P = 'p_ca4629a5cf97'
gao = [
    E(P, 'E001', 'EV001', 'T01', None,
      [('L8', '并将计算机视觉如何应用于机器人场景作为自己的未来研究方向')],
      '声明', '支持', '未建立', 'P0', '记者或传记作者', '记者或作者',
      {'goal_content': '计算机视觉在机器人场景中的应用', 'goal_background': None,
       'related_choice': None, 'goal_change': '未知'},
      '有具体研究方向，但无对应的选择或行动，按规则记目标声明。',
      'L4 导师所说“早早地确立了学术理想”是他人评价，未作证据。',
      education_stage='本科', domain='计算机视觉', creative_phase=['方向选择']),
    E(P, 'E002', 'EV002', 'T02', None,
      [('L6', '在参加“龙芯杯”时，高焕昂本可以选用国外研发、已成为事实标准的架构作为工作基础。但他并没有，因为高焕昂坚信未来的中国芯上应该运行中国自主可控的架构。'),
       ('L6', '“如果这条路上鲜有前人的工作，那么我就立志建设它！”')],
      '行为', '支持', '可能', 'P1', '多人', '本人',
      {'choice': '参赛时不采用事实标准的国外架构', 'endorsed_reason': '认为中国芯应运行自主可控架构',
       'external_requirement': '竞赛'},
      '有具体选择和本人认可的价值理由，符合 T02。',
      '理由主要由记者转述；新架构工作的内容、难度与结果关系未交代，创造情境只记可能。',
      education_stage='本科', domain='计算机系统', creative_phase=['方向选择']),
    E(P, 'E003', 'EV002', 'T10', None,
      [('L6', '高焕昂本可以选用国外研发、已成为事实标准的架构作为工作基础。但他并没有'),
       ('L6', '如果这条路上鲜有前人的工作，那么我就立志建设它！')],
      '材料不足', '不确定', '可能', 'P1', '多人', '本人',
      {'prior_experience': None, 'new_demand': '鲜有前人工作的架构', 'choice': '放弃事实标准架构',
       'action': None},
      '有可选择范围与主动选择，但没有相对其原有经验的新要求依据，也未写实际工作内容。',
      '不能凭“鲜有前人工作”推断对本人更难。',
      education_stage='本科', domain='计算机系统'),
    E(P, 'E004', 'EV003', 'T05', None,
      [('L7', '高焕昂还牵头建构了计算机系科协的系统性培训体系，也在同学们对作业框架感受不佳时组织调研、促进课程改革')],
      '行为', '不确定', '可能', 'P1', '记者或传记作者', '记者或作者',
      {'initiative_scope': '科协培训体系；作业框架调研与课程改革', 'proposer': None,
       'first_action': '组织调研', 'co_initiators': None},
      '有问题线索（同学对作业框架感受不佳）和首步行动（组织调研），但“牵头”可能只是科协主席职务。',
      '提出者未交代，接近排除条件“承担负责人职务”。',
      education_stage='本科', domain='教学改进', creative_phase=['问题发现']),
    E(P, 'E005', 'EV004', 'T04', None,
      [('L10', '回望过去三年的本科生活，让我最幸福的不是取得的那些成果，而是学习知识、传播知识和尝试发现新知识的每时每刻。')],
      '声明', '不确定', '未建立', 'P0', '本人', '本人',
      {'interest_domain': '学习、传播和发现知识', 'time_basis': '本科三年',
       'participation': None, 'interest_expression': '最幸福的是学习知识……的每时每刻'},
      '有兴趣表达和时段，但对象宽泛，没有可区分时点的参与材料。',
      '答辩语录，属于自我呈现场合。',
      education_stage='本科', elicitation='自发叙述'),
]
gao_reasons = {
    'T03': '已核读全文。L8“尝试发现新知识”是概括，无具体探查。',
}
gao_default = '已核读全文，未找到符合纳入条件的材料。'

# ---------------------------------------------------------------- Boyle
P = 'nobel_839'
boyle = [
    E(P, 'E001', 'EV001', 'T03', None,
      [('L1', 'She was a curious woman, and through her teaching I developed a strong curiosity as well.')],
      '声明', '不确定', '未建立', 'P0', '本人', '本人',
      {'unknown_question': None, 'search_action': None, 'prompted_by_other': '母亲的苏格拉底式提问',
       'finding': None}, '本人自述好奇心的来源，没有具体探查经历。',
      '按排除条件“从小好奇而无经历”，只记声明。',
      education_stage='家庭教育（14岁前）', context_support=['母亲的家庭教学'],
      elicitation='自发叙述'),
    E(P, 'E002', 'EV002', 'T07', 'T07a',
      [('L2', 'The transition back to class was not easy, but I found it very helpful that my best friend from the Navy was also at McGill and we were able to work together to adapt back to our old lives.')],
      '行为', '支持', '未建立', 'P1', '本人', '本人',
      {'obstacle': '战后重返课堂不容易', 'subsequent_action': '与海军时的朋友一起适应学习生活',
       'strategy_before': None, 'strategy_after': None, 'support': '同在 McGill 的海军好友'},
      '有明确阻碍和其后的继续行动，符合 T07a。',
      '只涉及恢复学业，未见与学习或创造过程的具体联系；朋友支持是主要条件。',
      event_time='二战结束时', education_stage='本科（McGill）', domain='物理',
      creative_phase=['学习准备'], context_support=['海军好友'], elicitation='自发叙述'),
    E(P, 'E003', 'EV003', 'T02', None,
      [('L3', 'In 1953, after careful consideration, I decided the academic community available through Bell Labs would become my new home.')],
      '行为', '支持', '未建立', 'P0', '本人', '本人',
      {'choice': '在几个工作机会中选择贝尔实验室',
       'endorsed_reason': '贝尔实验室的学术共同体', 'external_requirement': None},
      '有具体选择和本人给出的理由，符合 T02。',
      '理由较简略，未说明为何看重学术共同体。',
      event_time='1953年', age_at_event='28—29岁',
      age_basis='生于1924年8月19日，事件只写年份1953年',
      education_stage='博士后/职业早期', domain='物理', creative_phase=['方向选择'],
      elicitation='自发叙述'),
    E(P, 'E004', 'EV004', 'T05', None,
      [('L4', 'Then in 1969, during a brainstorming session with George Smith, we created the charged-coupled device.')],
      '材料不足', '不确定', '可能', 'P1', '本人', '本人',
      {'initiative_scope': '电荷耦合器件（CCD）', 'proposer': None,
       'first_action': 'brainstorming session', 'co_initiators': 'George Smith'},
      '有共同发起的线索（与 Smith 头脑风暴），但未交代谁提出问题、首步行动是什么。',
      '共同发起不得归为独立发起；创造过程几乎没有展开。',
      event_time='1969年', age_at_event='44—45岁',
      age_basis='生于1924年8月19日，事件只写年份1969年',
      education_stage='职业中期', domain='物理/器件', creative_phase=['想法生成'],
      context_support=['George Smith'], elicitation='自发叙述'),
]
boyle_reasons = {
    'T04': '已核读全文。L2“continued to pursue my scientific interests”只伴随就读年限，属排除条件“只列多年就读”。',
    'T10': '已核读全文。L4“always challenging”是概括，未见主动选择的具体任务。',
}
boyle_default = '已核读全文，未找到符合纳入条件的材料。L6—L14 为奖项列表，L15 为出处。'

# ---------------------------------------------------------------- Marshall
P = 'nobel_789'
marshall = [
    E(P, 'E001', 'EV001', 'T13', None,
      [('L3', 'Barry Marshall proved that peptic ulcers are caused by Helicobacter pylori by actually drinking down a dose of the bacteria himself')],
      '材料不足', '不确定', '明确', 'P1', '记者或传记作者', '记者或作者',
      {'check_target': '幽门螺杆菌致溃疡的假设', 'dimensions_or_comparison': None,
       'action': '自己喝下细菌', 'observation': None},
      '网站编者对自体实验的一句概括，有检查对象与行动，但无检查维度和观察。',
      '对应的视频访谈未转录，现有文本中没有本人叙述。',
      domain='医学', creative_phase=['评价验证']),
    E(P, 'E002', 'EV002', 'T04', None,
      [('L23', 'That’s where my interest is at the moment; I love doing this work.')],
      '声明', '不确定', '未建立', 'P0', '本人', '本人',
      {'interest_domain': '目前的研究项目', 'time_basis': None,
       'participation': None, 'interest_expression': 'I love doing this work'},
      '只有当下的兴趣表达，没有时间跨度。',
      '回答获奖后工作安排的问题，属一般性表态。',
      domain='医学', elicitation='一般经历提问'),
]
marshall_reasons = {
    'T07': '已核读全文。L24—L25 提到最初无人相信，但回答转向公众认知，未写本人困难后的行动。',
}
marshall_default = ('已核读全文。可用正文只有获奖当天的电话访谈（L13—L36），内容是获奖反应；'
                    'L3、L7、L9 是视频简介，视频访谈未转录。未找到符合纳入条件的材料。')

CASES = [
    ('univ_interview_6a429a43fbba', deng, deng_reasons, deng_default),
    ('tsinghua_special_e6c8ab123a0c', zhang, zhang_reasons, zhang_default),
    ('tsinghua_special_3247ea0c1d9a', gao, gao_reasons, gao_default),
    ('nobel_e56eceb5d699', boyle, boyle_reasons, boyle_default),
    ('nobel_603039526f99', marshall, marshall_reasons, marshall_default),
]


def main():
    docs = {d['doc_id']: d for p in SOURCES for d in corpus.read_jsonl(p)}
    _, meta = ev.load_prompt()
    records = []
    for doc_id, evidence, reasons, default in CASES:
        doc = docs[doc_id]
        unit = ev.prepare_doc(doc, meta, model=CODER)
        result = {'screening': screening(doc['person_id'], evidence, reasons,
                                         default),
                  'evidence': evidence}
        rec = ev.make_record(unit, result, served_by=CODER,
                             stop_reason='manual')
        rec['raw_output'] = ''
        records.append(rec)
        print(doc_id, doc['name'], '证据', len(evidence), '问题',
              rec['problems'] or '无')
    corpus.write_jsonl(os.path.join(HERE, 'runs.jsonl'), records)
    print(ev.export_tables(records, HERE))
    print(ev.summarize(records))


if __name__ == '__main__':
    main()
