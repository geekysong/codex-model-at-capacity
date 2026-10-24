# Selected model is at capacity — 5 分钟 SVG 监控

## 背景

2026 年 10 月，这个 Codex 账号频繁遇到两个问题：额度明明没怎么用，却反复收到
“Selected model is at capacity”；同时怀疑模型回答质量悄悄下降。官方没有可查记录，
所以这个项目每 5 分钟用同一个低风险任务轮询模型，公开记录耗时、token、错误和生成的
讽刺 SVG。SVG 是探针，数据才是本体。

重要任务不会交给疑似降智的 Codex 去做。SVG 成功不等于模型聪明，单次变慢也不等于
发生回归。计划中的独立质量信号是：用固定 benchmark 让 Claude Code 按版本化 rubric
对 Codex 输出评分，记录 instruction following、事实准确性、推理、完整性和实用性，
每项 0–4 分。在真实评审数据产生前，网页不会展示虚构的质量分数。

## 运行方式

树莓派上的 cron 每 5 分钟错开执行两个 prompt round。每个 round 使用 4 个对应的 Codex
模型串行、每个只尝试一次，使用 `low` reasoning effort，单模型最多等待 600 秒。Claude
API 每 30 分钟对两个 round 各跑一次，结果追加进 `stats.json` 对应的 Codex 记录，页面由
`build_index()` 重建，然后提交并推送 `main` 和 `gh-pages`。

```cron
*/5 * * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_round.py >> /home/songyy/codex-model-at-capacity/round.log 2>&1
```

## 数据文件

- `stats.json`：追加式的每次尝试记录。
- `runs/<round>/<model>.svg`：Codex 生成的 SVG。
- `runs/<round>/meta.json`：该轮 8 条记录。
- `index.html`：由 `run_round.py` 自动生成的 GitHub Pages 页面。
- `compare_claude.py`：使用 Anthropic 官方 Messages API 生成对照 SVG。
- `comparisons/<timestamp>/`：Claude 对照结果，不进入 cron 健康序列。

`stats.json` 的记录包含轮次、SGT 时间、模型、状态、耗时、五种 token 数、错误文本和
SVG 路径。缺失值使用 `null`。页面展示了实际使用的完整 prompt，方便复现。

## Claude 对照

将 Anthropic API token 单独放进被 `.gitignore` 忽略的
`.secrets/anthropic_api_key`（权限 `600`），运行：

```bash
python3 compare_claude.py
```

当前网页只展示四组配对：`gpt-6-astra ↔ claude-fable-5-1`、
`gpt-6.1-sol ↔ claude-opus-5-5`、`gpt-6-luna ↔ claude-haiku-5-5`、
`gpt-5.6-terra ↔ claude-sonnet-5-5`。两边使用同一个 SVG prompt；Codex 走订阅登录，
Claude 走 Anthropic API。其它 Claude 模型不生成。
