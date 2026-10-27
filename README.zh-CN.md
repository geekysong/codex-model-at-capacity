# Selected model is at capacity — 30 分钟一轮的 SVG 监控

[English](README.md) | **中文**

## 背景

2026 年 10 月，这个 Codex 账号频繁遇到两个问题：

1. **"Selected model is at capacity."** 额度明明没怎么用，模型却反复用这个
   错误拒绝工作——没有预警、无处申诉，官方也不留任何可查的记录。
2. **怀疑模型「降智」。** 同一批模型，回答似乎明显不如从前——更慢、更笨，
   或者以前能做的任务突然失败——同样没有任何公告，也没有办法证明。

所以这个项目的目的，是给**这一个特定账号做持续、公开的体检**：它有没有被
capacity 拒绝，质量有没有在悄悄下滑。每次尝试都带时间戳公开发布。错误率
上升说明有容量问题；耗时、token 模式漂移、任务突然失败，就是降智的早期
信号。讽刺 SVG 只是探针，数据才是本体。

## 运行方式

树莓派上的定时任务每 30 分钟跑一轮，包含两个 benchmark——**鹈鹕**
（固定 prompt）和**每日挑战**（每天新生成一条共享 prompt）——每个被监控的
OpenAI Codex 模型对每个 benchmark 各画一张 SVG，**只尝试一次、不重试**。
模型串行执行，让一轮的形态接近账号的日常使用。

每次尝试都如实记录：

- 模型名
- 实际耗时（秒）
- `codex exec --json` 报告的 token 用量（`input`、`cached input`、`output`、`reasoning`、`total`）
- 确切的错误原文（如有，包括 capacity 拒绝）

结果发布在 GitHub Pages：**https://geekysong.github.io/codex-model-at-capacity/**

- `index.html` — 最新一轮的画廊（每轮重新生成）
- `history.html` — 完整历史表格（每轮重新生成）
- `stats.json` — 每次尝试的原始记录，只追加
- `runs/<round-id>-<variant>/<model>.svg` — 生成的 SVG 本身
- `run_round.py` — 整个流水线（Pi → codex exec → stats → 页面 → commit → push）

当前监控模型：`gpt-6-astra`、`gpt-6.1-sol`、`gpt-6.1-terra`、`gpt-6-luna`
（`codex-auto-review` 内部模型不纳入）。所有模型的 reasoning effort 统一
固定为 `low`，保证耗时可横向比较。

**Terra 升级（2026-10-27）：** 被监控的 Terra 模型由 `gpt-5.6-terra` 换成
`gpt-6.1-terra`，与 Codex 当前最新的 Terra 世代对齐（依据 Pi 上
`~/.codex/models_cache.json`，2026-10-27 抓取，并已用真实调用验证可用）。
`stats.json` 里更早的使用 `gpt-5.6-terra` 的轮次保持原样，作为历史数据。

网页上的跨厂商对照面板只比较下面四组配对，Claude 侧的产出由独立流程生成
（见下文「Claude 对照」）：

| Codex 模型 | Claude 对照 |
| --- | --- |
| `gpt-6-astra` | `claude-fable-5-1`（Fable 5.1） |
| `gpt-6.1-sol` | `claude-opus-5-5`（Opus 5.5） |
| `gpt-6.1-terra` | `claude-sonnet-5-5`（Sonnet 5.5） |
| `gpt-6-luna` | `claude-haiku-5-5`（Haiku 5.5） |

提交署名为 geekysong <geekysong@gmail.com>。

## 「降智」在这里指什么

这个项目刻意**不**把重要任务交给被怀疑降智的 Codex 去做。探针是一个小而
可逆的画图任务，只测可用性和少数可观测的成本信号，不拿真实交付物冒险。
所以 SVG 画成功不等于模型聪明，单次变慢也不等于发生了回归。

鹈鹕结果现在会接受独立的视觉评审：以一张固定的 Astra 参考图为基准，
评审者按鸟形、柔和度、骑车关系和整体可读性打分，0 分（可接受）到 4 分
（严重视觉失败），附原图、中文理由和版本化哈希。首页按新加坡时间的小时
绘图，展示每个模型在该小时内最差的评审分。没有评审和生成失败都不计分。
这是一个主观的画面质量序列，不代表模型的整体能力。数据结构、评审规则
和运行方法见 [QUALITY.md](QUALITY.md)。

## 数据格式

`stats.json` 是一个只追加的 JSON 数组，每条尝试包含这些字段：

| 字段 | 含义 |
| --- | --- |
| `round` | SGT 轮次标识，`YYYYMMDD-HHMMSS` |
| `time_sgt` | 这次模型尝试开始时的时间戳 |
| `model` | 传给 `codex exec` 的模型名 |
| `status` | 成功提取出完整 SVG 时为 `ok`，否则为 `error` |
| `duration_s` | 实际耗时（秒），包括失败和超时的尝试 |
| `input_tokens`、`cached_input_tokens`、`output_tokens`、`reasoning_tokens`、`total_tokens` | JSON 事件流报告的用量；取不到的值为 `null` |
| `error` | 截断后的错误文本（如有） |
| `svg` | 生成的 SVG 相对路径，或 `null` |

每轮每个 benchmark 还有一个 `runs/<round>-<variant>/meta.json`，包含该
benchmark 的四条记录。SVG 文件作为原始公开产物保留。

## 复现与运维

树莓派使用一条共享的每日 prompt。Codex 每 30 分钟跑一轮；Claude 每天跑
一次作为对照组：

```cron
0 0 * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/generate_daily_prompt.py >> /home/songyy/codex-model-at-capacity/claude_round.log 2>&1
*/30 * * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_round.py >> /home/songyy/codex-model-at-capacity/round.log 2>&1
5 0 * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_claude_round.py >> /home/songyy/codex-model-at-capacity/claude_round.log 2>&1
```

Codex runner 先获取 `.round.lock`，然后对每个 benchmark 串行调用四个监控
模型各一次，reasoning effort 为 `low`，单模型最多等待 600 秒；之后追加
结果、重建 `index.html` 和 `history.html`、写轮次元数据，再提交并推送
`main` 和 `main:gh-pages`。推送失败留给下一轮重试。不调用模型、只检查
runner 本身可以用：

```bash
python3 -m py_compile run_round.py
```

生成的页面刻意做成完全自包含：没有 CDN、没有构建步骤，GitHub Pages 可以
直接托管。`index.html` 是生成产物；要改页面 UI 请改 `run_round.py` 里的
`build_index()`，否则下一轮 cron 会把改动覆盖掉。

## Claude 对照

`compare_claude.py` 把完全相同的 SVG 探针直接发给 Anthropic 官方
Messages API。把 API key 单独放进被 `.gitignore` 忽略的
`.secrets/anthropic_api_key`（权限 `600`），然后运行：

```bash
python3 compare_claude.py
```

不改脚本也能选模型，例如 `CLAUDE_MODEL=claude-sonnet-5-5`。输出和非机密的
请求元数据写到 `comparisons/<timestamp>/`；key 永远不会被写进去或打印
出来。定时 Claude 对照会通过既有的 GitHub Pages 路径发布这些产物；单独
手动运行只写本地文件。

`daily_prompt_meta.json` 是当天题目的带日期权威来源，`daily_prompt.txt`
是它的可读镜像。两家厂商收到的是同一条 prompt；它的 SGT 日期和 SHA-256
前缀会记进每条结果，保证 Codex 的观测只和 Claude 同一天的对照比较。
定时生成器每天原子地产生一份快照。页面上保留更早的鹈鹕、替换、物理等
实验轮次作为历史。

### 当前 benchmark 与可见时间戳

现在每次定时 Codex 执行都串行跑鹈鹕和每日挑战两个 benchmark，每个
benchmark 四个模型。Claude 对照同样覆盖两个 benchmark。每个请求都带
自己的时间戳，并要求 SVG 里有一个可见的页脚，写明 Asia/Singapore
（SGT，UTC+08:00）的日期和时间。已有的历史图片不变。物理和替换保留为
归档，不再是单独的活跃 benchmark。

### 每日对照的可靠性

运行合同和回归检查清单在 [specs/claude-daily.md](specs/claude-daily.md)。
Pi 上的任务都按 Asia/Singapore 运行：prompt 生成在 00:00，Claude 在
00:05。Claude 最多等两小时获取与 Codex 共享的锁，每个挑战/模型只尝试
一次。带日期的 JSON prompt 快照是权威来源，`.txt` 文件只是镜像。网页上
的实时对照面板要求挑战日期和哈希一致。

```bash
python3 -m unittest -v test_claude_daily
python3 run_claude_round.py --dry-run
python3 run_claude_round.py --publish-only  # 不调用模型
```

失败或不确定的请求会留在被忽略的 `.claude-state/` 里供运维检查；重跑
每日任务不会重复发送。发布失败会以非零码退出并保留本地产物。API 产出
保留其真实的厂商和模型来源。
