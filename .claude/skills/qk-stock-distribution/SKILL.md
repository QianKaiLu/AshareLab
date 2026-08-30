---
name: qk-stock-distribution
description: 识别 A 股个股/股票池是否出现主力出货形态（S1 天量巨阴 / S2 次高点巨量长阴 / S3 阶梯放量下跌 / S4 双头双放量巨阴 / S5 绿肥红瘦），输出「必走/至少走一半/稳一手」分级结论，用于排除持仓与候选股风险。触发场景：(1) 用户说「看看 XX 有没有出货」「XX 是不是主力在出货」「出货识别」「出货体检」(2) 用户给一批股票/B1 结果想排除有出货嫌疑的 (3) 用户问某只高位票还能不能拿 (4) 用户输入 /qk-stock-distribution。输入为股票名、6 位代码、代码列表、文件或指数池。
---

# 主力出货识别

量化探测器（S1~S5）负责穷举规则能框死的形态，你负责对边界情形做最终判读。
规则与案例标定见 [references/distribution_rules.md](references/distribution_rules.md)，
判读前先读它。

## 运行环境

必须切到 conda `stock` 环境；脚本已自行处理 `sys.path`，无需 `PYTHONPATH=.`。
`--live-stream` 必需，否则 `conda run` 缓冲输出到进程结束。

```bash
cd /Users/qianqian/stock/AshareLab
```

## 工作流

### 1. 批量扫描（给范围时）

```bash
conda run --live-stream -n stock python .claude/skills/qk-stock-distribution/scripts/distribution_scan.py --codes 600016,300251
conda run --live-stream -n stock python .claude/skills/qk-stock-distribution/scripts/distribution_scan.py --file b1_results/2026-08-28.md
conda run --live-stream -n stock python .claude/skills/qk-stock-distribution/scripts/distribution_scan.py --pool hs300
```

输出三档：**高危**（20 个交易日内有信号）/ **观察**（20~60 日）/ 无信号，
每股一行带形态、严重度、量化细节。`--to-date YYYYMMDD` 可回看历史时点。

分层解读：
- **高危 + 必走** → 直接排除，不必复核（除非个股有特殊逻辑）。
- **高危 + 至少走一半/稳一手**、**观察**档 → 进第 2 步逐只复核。
- **无信号** → 默认保留，但注意：复合式/温和式出货（尤其大盘股）量化会漏，
  若该票位置很高（距 60 日高点 <5%）且你心存疑虑，仍可进第 2 步。

### 2. 单股复核（给个股、或批量结果需要细看时）

```bash
conda run --live-stream -n stock python .claude/skills/qk-stock-distribution/scripts/distribution_review.py <股票名或代码> [日期]
```

输出：位置（距 60 日高点、白黄线）、量化信号列表（含每条阈值实测值）、
**顶部区逐根 K 线量价明细表**（开收高低、实体、归一化实体、量/20 日均量、
天量/缩量/巨阴/破线标记）。明细表就是给你判 AI 区情形的，读法见
references/distribution_rules.md 的「AI 判读步骤」。

### 3. 全市场扫描（很少用）

```bash
PYTHONPATH=. conda run --live-stream -n stock python -m hunters.z_distribution_hunter
```

注意：大盘见顶回落后全市场会有几百只同时命中（2026-08-19 大跌后次日扫描
命中 1715 只），这是市场状态的真实反映，不代表探测器失灵。全市场结果
适合做风险底稿，不适合直接当排除清单；排除决策落到具体池子再做。

## 判断纪律（继承文稿）

1. 只看量、价、位置。不叠 MACD/KDJ/背离。
2. 假阴真阳一律当阴线。
3. 宁可信其有。存疑的放到「需人工看图」，不要替用户决定「没事」。
4. 换庄失效：信号后出现更大量资金创新高接货，旧信号作废。

## 你的自由度边界

文稿作者明说「我的文章也可能片面」。你可以：

- **推翻量化结论**：量化命中但你从明细表看到换庄、或形态实为洗盘
  （如缩量回踩黄线不破、阴线量其实逐日递减），可以判「保留」，说明理由。
- **补量化漏报**：复合式/温和式出货、早期绿肥红瘦雏形，量化不报你可以报，
  但必须引用明细表中的具体日期和数值（哪几根 K 线、量和实体各是多少）。
- **调整严重度**：量化给「必走」你判「至少走一半」可以，反之亦然，
  同样要落到具体 K 线证据。

不接受：不引用具体数据的泛泛结论（「形态不太好」「量能有点异常」）。

## 输出格式

批量扫描后直接给结论表：

```
## 排除（高危+必走）：N 只
代码 名称 形态 最新信号日 一句话理由
## 复核后排除：N 只（含量化漏报、你补判的，注明）
## 保留：N 只
## 需人工看图：N 只（存疑，说清疑在哪根 K 线）
```

单股复核则按「结论 → 形态判定（量化/你补判）→ 关键证据（日期+数值）→
操作建议（回避/减仓/观察，附失效条件）」组织。
