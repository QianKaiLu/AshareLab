# 波段持仓监控与复盘

交易系统中「波段操作」分支的日常流程文档库（区别于「长期价值投资」分支）。

## 文档索引

| 文档 | 内容 |
|---|---|
| [需求文档.md](需求文档.md) | 当前版本的完整设计：数据模型、分析场景、skill 分工 |
| [TODO.md](TODO.md) | 待迭代项，含推后的决策与原因 |
| [CHANGELOG.md](CHANGELOG.md) | 迭代历史，每次设计变更记一条 |

## 交易系统本体

规则来源在另一个仓库，本流程只做实现，不在这里重复定义规则：

- `~/stock/life_kernel/trading_system/` — 核心原则、B1、双线系统、卖点、macd、kdj、对称交易、活跃市值
- `~/stock/life_kernel/trading_system/reference_articles/modoo/` — modoo 体系文章

## 当前状态

需求文档第 6 节的六步落地顺序**已全部完成**（2026-09-05）：存储层 → 周线 KDJ → 测量快照 → 每日日报 → 单票复盘 → 记账 skill。

三个 skill 与共享的 py 包：

| 入口 | 用途 |
|---|---|
| `/qk-stock-swing-trade` | 记一笔（买卖 + 理由 + 止损计划 + 便签验证） |
| `/qk-stock-swing-daily` | 每日持仓日报，按「今天要不要动手」分档 |
| `/qk-stock-swing-review` | 单笔买入复盘（买点 + 成交价偏离 + 理由 + 事后走势） |
| `portfolio/` | 三者共享：store / position / snapshot / monitor / review / archive / cli |

账本还是空的，用 `python -m portfolio.cli buy ...` 录第一笔，或 `python -m portfolio.monitor --codes <代码>` 先试跑。

用法速查见 [../工具与工作流.md](../工具与工作流.md)。
