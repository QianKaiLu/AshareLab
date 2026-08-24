#!/usr/bin/env python
"""B1 买点体检：输出单只个股在指定日期的全部 B1 相关测量值。

只做客观测量与逐维度打标，不做整体结论——综合评价由 SKILL.md 的评分体系负责。

用法:
    python b1_review.py <股票名或代码> [日期]
    python b1_review.py 宁波韵升 20250806
    python b1_review.py 600366              # 日期默认最近交易日
    python b1_review.py 600366 --json       # 机器可读输出
"""
import argparse
import json
import sys
from typing import Optional

import pandas as pd

sys.path.insert(0, "/Users/qianqian/stock/AshareLab")

import hunters.z_b1_hunter as b1  # noqa: E402
from datas.query_stock import (  # noqa: E402
    get_stock_code_by_name,
    get_stock_info_by_code,
    query_bars_by_days,
)
from indicators.kdj import add_kdj_to_dataframe  # noqa: E402
from indicators.volume_ma import add_volume_ma_to_dataframe  # noqa: E402
from indicators.zxdkx import add_zxdkx_to_dataframe  # noqa: E402
from tools.stock_tools import latest_trade_day, to_std_code  # noqa: E402

BARS = 500

# 逐维度打标阈值。取自十个范本案例的实测区间，
# 不是全市场统计分布——用于「与范本比，这只算好还是勉强」的定性判断。
THRESHOLDS = {
    # 末日量 / 点火期均量。缩至启动阶段的 1/3 以下即「极致缩量」
    "shrink_excellent": 0.33,
    "shrink_ok": 0.60,
    # 末日量在近 60 日成交量中的分位，对应「地量」
    "floor_vol_excellent": 0.15,
    "floor_vol_ok": 0.35,
    # J 值：13 以下为标准形态，13~16 属「模糊认定买点」
    "kdj_excellent": 13.0,
    "kdj_ok": 16.0,
    # 点火后最大量 / 点火期最大量。>1.3 视为顶部放量（出货嫌疑）
    "top_vol_excellent": 0.8,
    "top_vol_ok": 1.3,
}


def resolve(name_or_code: str) -> tuple[Optional[str], str]:
    """把股票名或代码解析成 6 位标准码，返回 (code, 说明)。"""
    try:
        code = to_std_code(name_or_code)
        info = get_stock_info_by_code(code)
        if not info.empty:
            return code, "按代码匹配"
    except Exception:
        pass

    code = get_stock_code_by_name(name_or_code)
    if code:
        return code, f"按名称模糊匹配到 {code}"
    return None, f"无法解析「{name_or_code}」：股票池中查不到该名称或代码"


def label(value: float, excellent: float, ok: float, lower_is_better=True) -> str:
    if lower_is_better:
        if value <= excellent:
            return "优秀"
        return "合格" if value <= ok else "不足"
    if value >= excellent:
        return "优秀"
    return "合格" if value >= ok else "不足"


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    add_kdj_to_dataframe(d, inplace=True)
    add_zxdkx_to_dataframe(d, inplace=True)
    add_volume_ma_to_dataframe(d, periods=[b1.CONSOLIDATION_DAYS], inplace=True)
    d["_pct_change_oc"] = d["close"] / d["open"] - 1
    d["_is_up"] = d["close"] > d["open"]
    d["_is_down"] = d["close"] < d["open"]
    return d


def best_ignition(d: pd.DataFrame):
    """返回 (最佳点火段, 候选总数, 各候选卡在哪一阶段)。

    「最佳」= 第一个能通过阶段 E~G 的候选（由近及远）；
    若无候选全通过，退回最近的那个候选，用于说明形态差在哪。
    """
    key = f"volume_ma_{b1.CONSOLIDATION_DAYS}"
    cands = list(b1._find_ignitions(d, d["close"].values, key))
    if not cands:
        return None, 0, {}

    stage_stat: dict[str, int] = {}
    passed = None
    for fire in cands:
        post = d.iloc[fire.start_idx:]
        if b1._check_top_no_volume(d, fire) is None:
            stage_stat["顶部放量被拒"] = stage_stat.get("顶部放量被拒", 0) + 1
            continue
        if b1._check_pullback_volume(d, post, fire) is None:
            stage_stat["缩量回踩被拒"] = stage_stat.get("缩量回踩被拒", 0) + 1
            continue
        if b1._check_pullback_position(d, post, fire, b1.VARIANTS[0]) is None:
            stage_stat["区间位置被拒"] = stage_stat.get("区间位置被拒", 0) + 1
            continue
        stage_stat["全通过"] = stage_stat.get("全通过", 0) + 1
        if passed is None:
            passed = fire

    return (passed or cands[0]), len(cands), stage_stat


def review(name_or_code: str, date: Optional[str]) -> dict:
    code, resolve_note = resolve(name_or_code)
    if code is None:
        return {"error": resolve_note}

    to_date = date or latest_trade_day().strftime("%Y%m%d")
    df = query_bars_by_days(code, days=BARS, to_date=to_date)
    if df.empty:
        return {"error": f"{code} 在 {to_date} 之前无行情数据"}
    if len(df) < 120:
        return {"error": f"{code} 仅 {len(df)} 根 K 线，不足以评估（需 ≥120）"}

    info = get_stock_info_by_code(code)
    d = prepare(df)
    last, prev = d.iloc[-1], d.iloc[-2]

    out: dict = {
        "标的": {
            "code": code,
            "name": info["name"].values[0] if not info.empty else "",
            "行业": info["idn_name"].values[0] if not info.empty else "",
            "解析": resolve_note,
            "评估日": str(last["date"])[:10],
            "请求日": to_date,
            "K线根数": len(d),
        }
    }

    # ---------------- Tier 1 硬门槛
    chg = (last["close"] / prev["close"] - 1) * 100
    amp = float(last["amplitude"]) if pd.notna(last.get("amplitude")) else None
    close, white, yellow = float(last["close"]), float(last["z_white"]), float(last["z_yellow"])
    out["硬门槛"] = {
        "当日涨跌幅": {
            "值": round(chg, 2),
            "要求": "-2% ~ +1.8%",
            "通过": bool(-2.0 <= chg <= 1.8),
        },
        "当日振幅": {
            "值": round(amp, 2) if amp is not None else None,
            "要求": "≤ 7%",
            "通过": bool(amp is None or amp <= 7.5),
        },
        "白线>黄线": {
            "白线": round(white, 2),
            "黄线": round(yellow, 2),
            "白黄比": round(white / yellow, 4) if yellow else None,
            "通过": bool(yellow > 0 and white > yellow),
        },
    }

    # ---------------- 均线结构与黄线支撑
    recent = d.tail(20)
    broke_yellow = recent[recent["close"] < recent["z_yellow"]]
    out["均线结构"] = {
        "收盘价": round(close, 2),
        "收盘/黄线": round(close / yellow, 4) if yellow else None,
        "距黄线": f"{(close / yellow - 1) * 100:+.2f}%" if yellow else None,
        "位置": ("白线上方" if close >= white
                 else ("白黄之间" if close >= yellow else "黄线下方")),
        "近20日跌破黄线天数": len(broke_yellow),
        "跌破后已收回": bool(len(broke_yellow) > 0 and close >= yellow),
    }

    # ---------------- J 值
    j, pj = float(last["kdj_j"]), float(prev["kdj_j"])
    out["KDJ"] = {
        "J值": round(j, 2),
        "前值": round(pj, 2),
        "方向": "翘头" if j > pj else ("走平" if abs(j - pj) < 1 else "下行"),
        "评级": label(j, THRESHOLDS["kdj_excellent"], THRESHOLDS["kdj_ok"]),
        "说明": "13 以下为标准形态；13~16 属模糊认定买点",
    }

    # ---------------- 前期涨幅背景（决定洗盘深度预期）
    c60 = d["close"].iloc[-60:]
    run_up = (c60.max() / c60.min() - 1) * 100 if c60.min() > 0 else None
    out["位置背景"] = {
        "近60日涨幅": round(run_up, 1) if run_up is not None else None,
        "是否高位": bool(run_up is not None and run_up >= 100),
        "说明": "浮盈少→洗盘浅；前期涨幅高→洗盘时间长。高位票走完美四逻辑",
    }

    # ---------------- 点火段
    fire, n_cands, stage_stat = best_ignition(d)
    if fire is None:
        out["点火"] = {"找到": False,
                       "说明": "近 30 日内没有符合条件的放量启动段——缺少 B1 的前提"}
    else:
        post = d.iloc[fire.start_idx:]
        after = d.iloc[fire.start_idx + fire.days:]
        pullback_days = len(after)
        vol_ma_before = float(d.at[fire.start_idx - 1, f"volume_ma_{b1.CONSOLIDATION_DAYS}"])

        out["点火"] = {
            "找到": True,
            "点火日": str(fire.date)[:10],
            "持续天数": fire.days,
            "累计涨幅": round(fire.acc_pct * 100, 2),
            "放量倍数": round(fire.mean_volume / vol_ma_before, 2) if vol_ma_before else None,
            "点火首日最低价": round(float(fire.support_price), 2),
            "候选段总数": n_cands,
            "候选分布": stage_stat,
            "回调天数": pullback_days,
        }

        # 量能演化
        last_ratio = float(last["volume"]) / fire.max_volume
        prev_ratio = float(prev["volume"]) / fire.max_volume
        mean_ratio = float(last["volume"]) / fire.mean_volume
        top_ratio = (float(after["volume"].max()) / fire.max_volume
                     if not after.empty else None)
        vol60 = d["volume"].iloc[-60:]
        pctile = float((vol60 < last["volume"]).mean())

        out["量能"] = {
            "末日量/点火均量": round(mean_ratio, 3),
            "末日量/点火最大量": round(last_ratio, 3),
            "前一日量/点火最大量": round(prev_ratio, 3),
            "缩量评级": label(mean_ratio, THRESHOLDS["shrink_excellent"],
                              THRESHOLDS["shrink_ok"]),
            "末日量在近60日分位": round(pctile, 3),
            "地量评级": label(pctile, THRESHOLDS["floor_vol_excellent"],
                              THRESHOLDS["floor_vol_ok"]),
            "点火后最大量/点火最大量": round(top_ratio, 2) if top_ratio is not None else None,
            "顶部无量评级": (label(top_ratio, THRESHOLDS["top_vol_excellent"],
                                   THRESHOLDS["top_vol_ok"])
                             if top_ratio is not None else "无回调数据"),
        }

        # 洗盘形态
        post_max, post_min = float(post["high"].max()), float(post["low"].min())
        pos = ((close - post_min) / (post_max - post_min)) if post_max > post_min else None

        is_up = post["close"] > post["open"]
        is_down = post["close"] < post["open"]
        is_fake_down = is_down & (post["close"] > post["close"].shift(1))
        touch_high = post["high"] >= post["high"].max()
        adj_down = is_down & ((~is_fake_down) | touch_high)
        adj_up = is_up | (is_fake_down & ~touch_high)
        n = b1.TOP_VOL_BARS
        uv = float(post.loc[adj_up, "volume"].nlargest(n).sum())
        dv = float(post.loc[adj_down, "volume"].nlargest(n).sum())
        body = (post["close"] - post["open"]).abs()
        ub = float(body[adj_up].nlargest(n).sum())
        db = float(body[adj_down].nlargest(n).sum())

        pre_start = max(0, fire.start_idx - b1.CONSOLIDATION_DAYS)
        pre = d.iloc[pre_start:fire.start_idx]
        box = ((pre["close"].max() - pre["close"].min()) / pre["close"].min() * 100
               if not pre.empty and pre["close"].min() > 0 else None)

        drawdown = ((post_max - close) / post_max * 100) if post_max > 0 else None
        out["洗盘形态"] = {
            "点火后区间": [round(post_min, 2), round(post_max, 2)],
            "现价区间位置": round(pos, 2) if pos is not None else None,
            "自高点回撤": round(drawdown, 2) if drawdown is not None else None,
            "红肥绿瘦_量比": round(uv / dv, 2) if dv > 0 else None,
            "红肥绿瘦_实体比": round(ub / db, 2) if db > 0 else None,
            "点火前箱体振幅": round(box, 2) if box is not None else None,
            "说明": "区间位置 ≤0.5 为缩量回调型；接近高位且缩量属完美四的缩量上涨",
        }

        # 最近 K 线序列，供定性判断洗盘方式（圆弧/横盘/阶梯）
        tail = d.tail(min(pullback_days + fire.days, 15))
        out["近期K线"] = [
            {
                "日期": str(r["date"])[:10],
                "开": round(float(r["open"]), 2),
                "收": round(float(r["close"]), 2),
                "高": round(float(r["high"]), 2),
                "低": round(float(r["low"]), 2),
                "涨跌%": round(float(r["change_pct"]), 2) if pd.notna(r["change_pct"]) else None,
                "量/点火最大量": round(float(r["volume"]) / fire.max_volume, 2),
            }
            for _, r in tail.iterrows()
        ]

    # ---------------- 策略判定与止损
    try:
        hit = b1.hunt_b1(df.copy())
    except Exception as e:
        hit = None
        out["策略判定异常"] = f"{type(e).__name__}: {e}"

    out["策略判定"] = {
        "hunt_b1命中": bool(hit),
        "variant": hit.get("variant") if hit else None,
        "说明": "hunt_b1 是硬筛，未命中不代表没有参考价值；以各维度测量为准",
    }

    far = yellow > 0 and (close / yellow - 1) > b1.FAR_FROM_YELLOW_PCT
    stop_line, stop_price = ("白线", white) if far else ("黄线", yellow)
    out["止损"] = {
        "建议参考线": stop_line,
        "止损价": round(float(stop_price), 2),
        "距现价": f"{(stop_price / close - 1) * 100:+.2f}%",
        "点火首日低点": round(float(fire.support_price), 2) if fire else None,
        "说明": ("股价离黄线较远，改用白线止损，且需控制仓位"
                 if far else "股价贴近黄线，以跌破黄线为止损"),
    }

    return out


def render(r: dict) -> str:
    if "error" in r:
        return f"❌ {r['error']}"

    lines = []
    s = r["标的"]
    lines.append(f"# {s['name']}({s['code']})  {s['行业']}")
    lines.append(f"评估日 {s['评估日']}（请求 {s['请求日']}，{s['解析']}，{s['K线根数']} 根 K 线）")

    lines.append("\n## 硬门槛")
    for k, v in r["硬门槛"].items():
        mark = "✓" if v["通过"] else "✗"
        detail = ", ".join(f"{kk}={vv}" for kk, vv in v.items()
                           if kk not in ("通过", "要求"))
        req = f"（要求 {v['要求']}）" if "要求" in v else ""
        lines.append(f"  {mark} {k}: {detail}{req}")

    lines.append("\n## 均线结构")
    for k, v in r["均线结构"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\n## KDJ")
    for k, v in r["KDJ"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\n## 位置背景")
    for k, v in r["位置背景"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\n## 点火")
    for k, v in r["点火"].items():
        lines.append(f"  {k}: {v}")

    if "量能" in r:
        lines.append("\n## 量能")
        for k, v in r["量能"].items():
            lines.append(f"  {k}: {v}")

        lines.append("\n## 洗盘形态")
        for k, v in r["洗盘形态"].items():
            lines.append(f"  {k}: {v}")

        lines.append("\n## 近期 K 线（量比以点火期最大量为 1）")
        lines.append(f"  {'日期':<12}{'开':>8}{'收':>8}{'高':>8}{'低':>8}{'涨跌%':>8}{'量比':>7}")
        for b in r["近期K线"]:
            lines.append(f"  {b['日期']:<12}{b['开']:>8}{b['收']:>8}{b['高']:>8}"
                         f"{b['低']:>8}{str(b['涨跌%']):>8}{b['量/点火最大量']:>7}")

    lines.append("\n## 策略判定")
    for k, v in r["策略判定"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\n## 止损")
    for k, v in r["止损"].items():
        lines.append(f"  {k}: {v}")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="股票名或 6 位代码")
    ap.add_argument("date", nargs="?", default=None, help="评估日 YYYYMMDD，默认最近交易日")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    r = review(args.target, args.date)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(r))
    return 1 if "error" in r else 0


if __name__ == "__main__":
    sys.exit(main())
