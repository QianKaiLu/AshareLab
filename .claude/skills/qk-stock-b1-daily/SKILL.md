---
name: qk-stock-b1-daily
description: A 股 B1 买点日更全流程——更新最新行情 → 全市场 B1 扫描 → 分级评价。触发场景:(1) 用户说「跑一下 B1」「B1 选股」「今天有哪些 B1 买点」「扫一下 B1」(2) 用户要行情更新 + B1 选股一次性完成(3) 用户问「今天的 B1 结果怎么样」「B1 复盘」(4) 用户输入 /qk-stock-b1-daily。
---

# B1 买点日更

三步流水线，按序执行：

```
1. 行情日更（workflow/daily_update.py）
   ↓
2. 全市场 B1 扫描（hunters/z_b1_hunter.py，输出含每只命中股的完整指标）
   ↓
3. 分级评价（按量能链规则 + 既定输出格式）
   ↓
4. 存档（b1_results/YYYY-MM-DD.md，供回测回溯）
```

## 运行环境（必读）

- 所有命令切 conda `stock` 环境：`PYTHONPATH=. conda run --live-stream -n stock python ...`，缺 `--live-stream` 会缓冲输出到进程结束，看起来像卡死
- 耗时：日更约 35 秒~20 分钟（视落后天数）、扫描约 3 分钟，**两步都必须后台跑**（Bash 工具 `run_in_background: true`），收到完成通知后再进下一步
- 若当日行情已更新过（上一轮刚跑完），可直接跳过步骤 1

## 步骤 1：行情日更

```bash
PYTHONPATH=. conda run --live-stream -n stock python workflow/daily_update.py > logs/daily_$(date +%Y%m%d).log 2>&1
```

- 读日志尾部「=== 校验 ===」段，向用户报告：最新交易日、落后股票数、OHLC/涨跌幅/换手率异常数
- 出现 `⚠ 数据质量异常` 先处理（repair_negative_prices.py --dry-run），再继续
- 落后几只（停牌股）属正常，不影响扫描

## 步骤 2：全市场 B1 扫描

```bash
PYTHONPATH=. conda run --live-stream -n stock python -m hunters.z_b1_hunter > logs/b1_hunt_$(date +%Y%m%d).log 2>&1
```

- 日志中每只命中输出两行：名称行 + 指标行，指标行字段：`variant, kdj_j, price_change_pct, amplitude_pct, fire_date, fire_days, fire_pct, top_vol_ratio, last_day_volume_ratio, prev_day_volume_ratio, three_vol_ratio, three_body_ratio, pos_in_breakout_range, is_high_position, stop_loss_line, stop_loss_price, support_price`
- 命中 40~80 只属正常范围；先给用户命中总数，再进步骤 3

## 步骤 3：分级评价

评价基准：**量能链优先**——点火放量 → 顶部无量 → 缩至地量 → 小阴小阳企稳。阈值标定与十范本案例见 `qk-stock-b1-review` 的 `references/b1_rules.md`（路径 `.claude/skills/qk-stock-b1-review/references/b1_rules.md`，必读）。

### 关键阈值

| 维度 | 字段 | 优秀 | 勉强 |
|---|---|---|---|
| 顶部无量 | top_vol_ratio | ≤0.8 | 0.8~1.3 |
| 末日缩量 | last_day_volume_ratio | ≤0.25（极致，范本参照 0.253） | 0.25~0.45 |
| 回调位置 | pos_in_breakout_range | ≤0.35（越低越充分） | 0.35~0.5 |
| J 值 | kdj_j | ≤13 完美一；13~16 完美二模糊 | >16 归完美四分支 |
| 红肥绿瘦 | three_vol_ratio / three_body_ratio | ≥1.2（任一） | <1.2 |

纪律：J 值只是过滤不是质量指标；量能优先于绝对指标；顶部无量 >1.3 或末日量 >0.45 属量能链残缺 → 第三梯队。

### 分级规则

- **第一梯队 · 优秀范本**：量能链完整（顶部无量 ≤0.8 且末日缩量 ≤0.25）+ 回调充分（位置 ≤0.35），J 深勾或红肥绿瘦突出。选 5~8 只
- **第二梯队 · 合格可试错**：主链成立，个别环节偏弱（缩量 0.25~0.35、位置 0.35~0.5、红肥绿瘦单边）
- **第三梯队 · 勉强、需等待**：顶部无量 >0.8（点火后出现过放量）、末日量 >0.45（没缩下来）、或位置 >0.5（未回调）
- **完美四组**：区分「真高位」（is_high_position=True，止损用白线、仓位压缩）与「位置超限被归入」（股价贴区间上沿，未回调到位）。真高位单独列出，其余并入第三梯队或备注

### 输出格式

- **第一梯队：表格**（列：股票 / 归类 / J值 / 顶部无量 / 末日缩量 / 区间位置 / 亮点），亮点带具体数字
- **第二、三梯队及完美四：竖排列表**，每行 `代码 名称 — 一句话评价`，方便复制/导入 Excel、备忘录：
  ```
  002612 朗姿股份 — 红肥绿瘦最强(2.4/2.87)，缩量到位
  605339 南侨食品 — 量比 2.66，回调至 0.20
  ```
- **每一节末尾附股票代码列表字符串**（逗号分隔、6 位代码、无空格），供直接粘贴到行情软件/自选股导入：
  ```
  股票列表：000596,300119,601108,603368,002348,002612,300441,300333
  ```
- 结尾列「需要人工确认」：ST/带帽股、基本面消息面不可见项
- 评级用词：`优秀范本` / `合格可试错` / `勉强、需等待` / `不构成 B1`

## 步骤 4：存档（回测回溯用）

把步骤 3 的完整分析写入 `b1_results/<当日日期>.md`（如 `b1_results/2026-08-25.md`），文件结构固定：

```markdown
# B1 买点分析 <日期>

- 数据源：ashare_data.db 前复权日线，最新交易日 <日期>
- 扫描范围：全市场 N 只（min_bars=500）
- 命中：N 只

## 第一梯队 · 优秀范本
（表格，同步骤 3）

股票列表：000596,300119,601108,603368,002348,002612,300441,300333

## 第二梯队 · 合格可试错
（竖排列表）

股票列表：000752,000977,002582,...

## 第三梯队 · 勉强、需等待
（竖排列表）

股票列表：300307,300871,300937,...

## 完美四 · 激进试错（仓位压缩）
（竖排列表）

股票列表：600664,001223,002199,...

## 完整指标（回测对齐用，CSV）
```csv
code,name,variant,kdj_j,chg,amp,fire,fire_days,fire_pct,top_vol_ratio,last_vol_ratio,prev_vol_ratio,vol_ratio,body_ratio,pos,high_pos,stop,stop_price,support
...
```
```

- 用 Write 工具写入；同一天重复运行时覆盖同名文件
- 「完整指标」段为全量 CSV（一行一股），从扫描日志的指标行提取，供后续回测脚本直接读入对齐
- 参考已有档案的格式：`b1_results/2026-08-25.md`

## 纪律

- 不做收益预测；数据只到评估日
- 图形类型不预示收益；完美四仓位必须压缩
- 单只股票想细看 → 建议用户跑 `/qk-stock-b1-review` 逐个体检

## 相关

- `workflow/daily_update.py` — 行情日更流水线（详见 `/qk-stock-daily-update`）
- `hunters/z_b1_hunter.py` — B1 全市场硬筛，`main()` 输出指标行
- `qk-stock-b1-review/references/b1_rules.md` — 评价标定基准
- `b1_results/` — 每日分析存档，`YYYY-MM-DD.md` 含分级 + 全量指标 CSV
