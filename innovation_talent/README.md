# 创新人才识别模型 · 公开文本验证

本文件夹独立于 weiboSpider 的原有代码，用于为《创新人才识别模型（TAD 四阶段版）》采集、编码和分析公开文本数据。仓库根目录的微博爬虫保持原样，本文件夹只在需要微博数据时读取它的输出。

## 内容

| 路径 | 说明 |
|---|---|
| [docs/research_design.md](docs/research_design.md) | 研究方案：数据来源、编码方案、分析计划、操作步骤、局限与合规 |
| [docs/llm_coding_rubric.md](docs/llm_coding_rubric.md) | 大模型文本编码细则（待审核）：可提取的维度与指标、打分规则、实例 |
| [docs/scoring_plan.md](docs/scoring_plan.md) | 校标提取、可分析文本与打分方法的初步检验结果（含试编码） |
| [prompts/](prompts/README.md) | 证据编码手册 1.0 的大模型提示词与运行说明（T01—T14 证据档案，不打分） |
| [docs/codebook.md](docs/codebook.md) | 编码手册：33 项指标 × 4 个阶段的行为锚点、文本可观测性、本土化候选编码 |
| [data/](data/README.md) | 第一批公开数据：诺贝尔奖获得者信息表、国家奖学金名录与报道的地址清单 |
| `talent_corpus/` | 采集、预处理、编码与分析的 Python 模块 |
| `tests/` | 离线测试 |

## 快速开始

所有命令都在本文件夹内运行：

```bash
cd innovation_talent
pip install -r ../requirements.txt                  # lxml、requests
pip install -r talent_corpus/requirements.txt       # 可选：大模型编码、导出 Excel
python3 -m talent_corpus -h                         # 查看全部子命令
python3 -m pytest tests                             # 运行测试
```

采集结果默认写入本文件夹下的 `talent_data/`（已加入 .gitignore，不会提交）。完整流程见研究方案第六节。
