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

# 3. 小样本试编：先编 5 篇国内文本，人工看结果再决定是否扩大
python -m talent_corpus evidence --corpus tsinghua_special --limit 5

# 4. 导出表格
python -m talent_corpus evidence-export
```

默认输入是三份文件：`data/long_texts/analysis_set.jsonl`（国内叙事文本），以及诺奖的 `biographical.jsonl` 和 `interview.jsonl`。传记只取本人撰写的版本，加上 `--include-narrator` 才会同时编他人撰写的版本。没有目标人物的多人合辑会自动跳过。全部材料共 706 篇、约 960 万字符，其中大部分是诺奖访谈和自传。建议先用 `--limit` 和 `--corpus` 小批量试编；正式批量运行时加 `--batch-submit`，价格减半，异步完成后再用 `--batch-collect <批次号>` 收回结果。

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
