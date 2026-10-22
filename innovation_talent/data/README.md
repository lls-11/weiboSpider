# 公开数据（第一批）

本目录存放为《创新人才识别模型》初步验证收集的公开数据。采集时间为 2026 年 10 月 20–21 日。

## 先说明：这一批没有正文文本

采集所用的云端环境只允许访问 GitHub 和 PyPI。人民日报电子版、人民网、教育部网站、高校新闻网、微信公众号、诺贝尔奖官网、微博全部被网络策略拦截，因此**名录条目、学生事迹、诺奖自传等叙事文本一篇都没有取得**。本目录只收了两类能拿到的数据：

1. **诺贝尔奖获得者的结构化信息**：来自 GitHub 上两个公开数据集，整理成科学类获奖者的采样框；
2. **名录与报道的地址清单**：通过网页检索确认的人民日报名录页面及转载、高校报道地址。这些是下一步抓取的入口，内容本身尚未抓取。

在能访问上述网站的电脑上运行 `talent_corpus` 的命令（见 [docs/research_design.md](../docs/research_design.md)），即可在这些清单的基础上取得正文。

## 目录结构

```
data/
├── README.md                       本说明
├── build_nobel.py                  由原始数据集生成 nobel/ 下各表的脚本
├── nobel/
│   ├── laureates_all.csv           全部奖项 1901–2024，1006 条（一人多次获奖为多条）
│   ├── laureates_stem.csv          物理、化学、生理学或医学的个人获奖记录，649 条
│   ├── crawl_frame_stem.csv        科学类获奖者采样框：获奖年份页面与 API 地址，抓取状态
│   └── stats.json                  描述统计
└── rmrb_scholarship/
    ├── list_sources.csv            2024–2026 年名录的电子版页面与转载地址，19 条
    └── school_report_leads.csv     高校与媒体的相关报道地址，12 条
```

## 诺贝尔奖数据（nobel/）

### 来源

| 数据集 | 内容 | 版本 |
|---|---|---|
| [JeffersonConza/The_Nobel_Laureates](https://github.com/JeffersonConza/The_Nobel_Laureates) | 1901–2024 年获奖记录：类别、获奖理由、出生日期与地点、性别、获奖时所在机构（源自诺贝尔奖官方 API） | 提交 `ee418fe` |
| [frishberg/Nobel-Prizes-by-Academic-Affiliations](https://github.com/frishberg/Nobel-Prizes-by-Academic-Affiliations) | 获奖者的就读院校（alma mater）与任职机构，取自维基百科信息框 | 提交 `8688999` |

两个仓库都没有附许可证文件。这里只保留事实性字段并注明出处，仅供研究使用。

### 处理

- 同一奖项因多个所属机构而重复的行合并为一条，机构合并到 `award_organizations`；
- “Physiology or Medicine” 统一记为 Medicine；
- `age_at_award` = 获奖年份 − 出生年份；
- 院校信息按姓名 + 年份 + 类别与第二个数据集匹配，匹配不上时按姓氏 + 年份 + 类别找唯一候选。全部奖项匹配率 92.4%，科学类 649 条中 38 条未匹配（多为“Sir”“née”等名称写法不同，如 Marie Curie、John Bardeen），这些行的 `alma_maters`、`institutions` 为空。

### 字段（laureates_all.csv / laureates_stem.csv）

`laureate_id`（官方编号，可直接用于 API）、`year`、`category`、`laureate_type`、`full_name`、`sex`、`birth_year`、`birth_date`、`birth_city`、`birth_country`、`death_date`、`age_at_award`、`prize_share`、`motivation`、`award_organizations`、`wiki_name`、`wiki_url`、`alma_maters`、`institutions`。多值字段用“; ”分隔。

### 描述统计（stats.json）

- 科学类个人获奖 649 次：物理 226、化学 195、生理学或医学 228；女性占 4.0%；
- 获奖年龄中位数 57 岁，并随年代明显推后：1930 年代 46.5 岁，1980 年代 58 岁，2010 年代 70.5 岁；
- 有完整院校信息的 490 条中，37.6% 曾在自己的母校任职；
- 就读院校前五：剑桥大学 57、哈佛大学 55、哥伦比亚大学 34、加州大学伯克利分校 27、麻省理工学院 26（按获奖次数计）。

和模型的关系：获奖年龄说明“原创贡献拓展”阶段的成果被认可往往比成果本身晚几十年。用诺奖自传做阶段分析时，阶段 4 的证据要按做出成果的时间判定，不能用获奖时间。

### 用法

`crawl_frame_stem.csv` 中每行对应一位科学类获奖者，`api_query` 为官方 API 的单人查询地址。在能访问诺奖官网的电脑上运行：

```bash
python3 -m talent_corpus nobel --categories phy,che,med
```

即可抓取这些获奖者的自传、致辞、访谈和讲座页面。

## 国家奖学金名录（rmrb_scholarship/）

### list_sources.csv

每份名录的电子版页面及转载地址。`list_id` 标识同一份名录（如 `2026_ug` 为 2026 年 5 月 4 日刊登的 2024—2025 学年度本专科生名录），`url_format` 为 `new`（2024 年 12 月 1 日起的 `pc/content/...`）、`old`（`html/.../nw.D110000renmrb_...htm`）或 `reprint`（转载）。所有地址都来自 2026 年 10 月 20–21 日的网页检索结果，页面内容未经本地抓取核对。

已确认的名录：

| 刊登日期 | 名录 | 电子版页面 |
|---|---|---|
| 2026-05-04 | 2024—2025 学年度本专科生 | 第 05、06 版 |
| 2026-05-05 | 2025 年研究生 | 第 06 版 |
| 2026-05-04 | 2024—2025 学年度中等职业教育 | 第 08 版（默认不纳入分析） |
| 2025-05-04 | 2023—2024 学年度本专科生 | 已找到电子版页面 |
| 2025-05-05 | 2024 年研究生 | 只找到人民网与客户端转载 |
| 2024-05-04 | 2022—2023 学年度本专科生 | 第 05、06 版（旧版地址） |

2024 年的研究生名录和 2019–2023 年各年名录尚未找到地址；`talent_corpus rmrb --years 2019-2026` 会按日期直接遍历电子版版面，不依赖这张表。

### school_report_leads.csv

各校新闻网、地方媒体对本校学生入选名录的报道。`title_or_summary` 一栏部分来自检索结果的摘要（如学生姓名、院系），尚未与原文核对，使用前须打开原文确认。

## 下一步

1. 在可访问外网的电脑上运行 `talent_corpus rmrb`，按 `list_sources.csv` 核对每份名录约 100 条；
2. 运行 `search-sheet` 生成每人的检索表，把 `school_report_leads.csv` 中已有的地址填进去；
3. 运行 `nobel`，按 `crawl_frame_stem.csv` 检查抓取覆盖率；
4. 正文取得后，按 docs/research_design.md 的步骤预处理、编码与分析。

若希望在云端环境里直接抓取，需要在环境设置的 Network access 中放行 paper.people.com.cn、edu.people.com.cn、www.moe.gov.cn、api.nobelprize.org、www.nobelprize.org 等域名。
