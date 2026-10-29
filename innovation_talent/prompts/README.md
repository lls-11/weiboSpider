# 证据编码提示词与脚本（手册 1.0）

| 文件 | 作用 |
|---|---|
| `evidence_coding_v1.0.md` | 依据《创造性人才指标文本证据编码手册》试用版 1.0 写成的系统提示。`<!-- 提示词正文 -->` 之后的内容会原样发给模型；开头的注释列出与手册不一致、需要课题组确认的地方。 |
| `../talent_corpus/coding/evidence.py` | 分段编号、调用模型、核对引文、导出表格 |

修改提示词时，同时把文件开头的 `prompt_version` 改掉（如 `evidence-1.0-p2`）。脚本按 `prompt_version` 和模型判断某篇是否已经编过，改了版本号，同一批文本就会重新编码，之前的结果仍保留在运行记录里，可以拿来对比。

## 运行（在 innovation_talent 目录下，PowerShell 一行一条）

```powershell
# 1. 试运行：不调用 API，只看会发什么、共多少篇
python -m talent_corpus evidence --limit 5 --dry-run talent_data/evidence/dry_run.jsonl

# 2. 设置 API 密钥（只在当前窗口有效）
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 3. 小样本试编：先编 5 篇，人工看过结果再决定是否扩大
python -m talent_corpus evidence --subset nobel_interview --limit 5

# 4. 导出表格
python -m talent_corpus evidence-export
```

默认输入是 `data/self_narrative/analysis_set.jsonl`（诺奖本人自传、诺奖深度访谈文字稿、国内第一人称专访与写到过程的报道，共 422 篇、约 710 万字符，筛选规则见该目录的 README）。用 `--subset` 只编其中几类，可选 nobel_autobiography、nobel_interview、cn_first_person、cn_report、cn_report_short；要编报道类文本，把文件路径作为参数传入。建议先用 `--limit` 小批量试编；正式批量运行时加 `--batch-submit`，价格减半，异步完成后再用 `--batch-collect <批次号>` 收回结果。

其他参数用 `python -m talent_corpus evidence -h` 查看，常用的有：
- `--doc-ids`：只编指定文档；
- `--effort`：推理强度，默认 high；
- `--families`：传入人工填写的 CSV（doc_id, source_family_id），把同源材料归为一组。

## 输出（talent_data/evidence/）

| 文件 | 内容 |
|---|---|
| `runs.jsonl` | 每次运行一行，只追加不覆盖：run 记录、模型原始输出、核对后的 screening 与 evidence、问题清单 |
| `screening.csv` | 每人 × T01—T14 一行，附空白人工复核列 |
| `evidence.csv` | 每条证据一行：引文、段号、字符偏移、各编码字段、indicator_details（JSON）、flags，附空白人工复核列 |

导出时，同一篇文档只取最近一次成功的运行。复核列为 reviewer_1、reviewer_2、original_codes、disagreements、final_codes、decision_reason、review_status，由编码员填写。

## 程序做的核对

- **引文**：
  - 在所引段落中逐字找到，标 `exact`；
  - 在别的段落找到，改正段号，标 `paragraph_id_corrected`；
  - 只有忽略空白或弯直引号的差异才能找到，标 `quote_normalized`；
  - 找不到，标 `quote_not_found`。

  字符偏移按固定文本（各段用换行连接）中的 Unicode 字符位置计算，起点包含、终点不包含。
- **覆盖**：每个目标人物在 screening 中必须有 14 行，缺少的写入 `problems`。screening 引用了不存在的证据编号，或者某条证据没有被任何 screening 行引用，都会打上标记。
- **字段**：检查子码与指标是否匹配，以及必提字段是否齐全（字段清单见 `evidence.py` 的 `DETAIL_FIELDS`）。

核对不通过的证据**不删除**，只在 `flags` 中注明原因，交人工复核。

---

# 以人为单位的指标编码（person_coding_v1.md）

每人一次调用，输出这个人体现了模型 C01—C33 中的哪些指标，最后整理成每人一行的分析表。与上面的证据编码（手册 1.0）相互独立，可以并行使用。

**控制成本的做法：**
- 系统提示约 1,900 字，开启了提示缓存，批量运行时重复部分只按缓存价计费；
- 输出只列出踩中的指标，没踩中的默认为 0；
- 文本量、获奖等级、论文专利奖项数、套话比例等能由程序计算的变量，都不交给模型；
- 默认推理强度为 medium。

```powershell
# 1. 试运行：不调用 API，看人数和正文字数
python -m talent_corpus person-code --dry-run talent_data/person/dry_run.jsonl

# 2. 先试 20 人（国内）
python -m talent_corpus person-code --subset cn_report,cn_first_person --limit 20

# 3. 生成分析表
python -m talent_corpus person-table
```

全量运行共 368 人（国内 143 人、诺奖 225 人），正文约 710 万字符，其中诺奖英文文本约占 98%。建议加 `--batch-submit` 提交批量任务，价格减半，完成后用 `--batch-collect <批次号>` 收回。

## 用 DeepSeek 运行

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek 密钥"

# 试运行（不调用 API）
python -m talent_corpus person-code --provider deepseek --limit 20 --dry-run talent_data/person/dry_run_ds.jsonl

# 试跑 20 人（国内）
python -m talent_corpus person-code --provider deepseek --subset cn_report,cn_first_person --limit 20

# 全量，4 路并发
python -m talent_corpus person-code --provider deepseek --workers 4
python -m talent_corpus person-table
```

- **模型名**：默认 `deepseek-chat`。要用其他型号（如 V4），用 `--model` 指定，名称以 DeepSeek 控制台和文档为准。
- **接口地址**：默认 `https://api.deepseek.com`。用第三方平台托管的 DeepSeek 时，用 `--base-url` 改成该平台的 OpenAI 兼容地址。
- **与 Claude 的区别**：
  - DeepSeek 的 JSON 模式只保证输出是合法 JSON，不检查字段取值。所以输出格式写进了系统提示，程序收到后再核对：越界的字段记“不详”，非法的指标判断丢弃，丢弃数记在 `n_dropped_invalid`。
  - 模型如果不支持 JSON 模式，程序会自动改为只靠提示词约束。
  - DeepSeek 自动缓存相同的系统提示，无须设置。它没有批量接口，用 `--workers` 并发提速。
  - 采样温度默认为 0，让同一份材料多次运行的结果尽量一致。
- **混用模型**：同一份运行记录里可以混有不同模型的结果，`person-table` 对每人取最近一次成功的结果。要比较两个模型，用 `--out` 写到不同文件，分别生成分析表。

## 输出：talent_data/person/persons.csv（每人一行）

| 变量 | 来源 | 说明 |
|---|---|---|
| group、language | 程序 | cn / nobel |
| subsets、corpora、source_types | 程序 | 材料子集、来源栏目、文本类型 |
| school、category、award_year、birth_year | 程序 | 学校；诺奖学科、获奖年、出生年 |
| n_texts、chars、log_chars | 程序 | 篇数、原文总字数及其自然对数（控制变量） |
| chars_sent、honor_sentences_removed | 程序 | 实际发给模型的字数；删去的荣誉罗列句数 |
| first_person_share | 程序 | 含第一人称的句子比例 |
| cliche_ratio | 程序 | 含套话的句子比例（宣传文本程度） |
| award_level、award_label | 程序 | 按来源判定的获奖等级：1 国家奖学金、2 校级最高荣誉、3 全国大学生年度人物、4 诺贝尔奖。清华特奖答辩材料中含未获奖的候选人 |
| in_rmrb_list | 程序 | 是否为人民日报国奖名录代表 |
| crit_* | 程序 | 仅国内：论文、第一作者论文、专利、主持项目、各级奖项数等（`criteria.py`，从原文提取） |
| text_type | 模型 | 过程叙述 / 荣誉罗列或通报 |
| education、discipline、gender、n_events | 模型 | 学历阶段、学科门类、性别、具体事件数 |
| C01—C33 | 模型 | 0 = 未体现，1 = 只有声明，2 = 有具体行为。C12、C13、C15、C17 不从文本编码，不出现 |
| D1_behavior—D6_behavior、D1_any—D6_any | 程序 | 6 个类别中，有行为证据的指标数、有任何证据的指标数 |
| n_behavior、n_statement、n_unverified | 程序 | 行为、声明指标总数；引语未通过核对的判断数 |

**引语核对**：默认只计入引语在原文中找得到的判断，加 `--include-unverified` 则全部计入。

## 输出：talent_data/person/codes.csv（每条判断一行）

person_id、name、group、indicator、dimension、level、stage（行为发生阶段）、verified、quote，用于抽查判断质量，或按阶段做分析。
