# -*- coding: utf-8 -*-
"""
石化设备供应商评分引擎  v1.0

区别于主区企查查工商评分（地理/规模/合规）与综合服务 5 维专家模型：设备类供应商
的核心采购决策围绕『到厂总成本 + 履约确定性 + 资质合规』展开，因此用一套面向
寻源场景的 5 维加权专家模型。每一维都由 build_equipment.py 写入的结构化字段
（price_level / lead_time_days / distance_km / is_local / qualification / tier）
派生而来，公式透明、可解释、可复算 —— 改一个字段即可复现分数，不是拍脑袋打分。

五大维度（默认权重，可被各品类 weights 覆盖）：
  ① 价格竞争力  price     32%  到厂价格系数（越低越优，行业均价=1.00 为锚）
  ② 交期保障    delivery  22%  交付周期（越短越优）
  ③ 属地履约    local     18%  属地供应商 + 距离就近响应
  ④ 资质等级    qual      16%  A1/API Q1/特种A级 等资质权威度
  ⑤ 规模品牌    scale     12%  全国龙头 / 区域头部 / 属地厂商

对外接口：
  DIM_KEYS, DIM_CN, DEFAULT_WEIGHTS
  score_supplier(sup, weights)        -> {**sup, "score", "dims"}
  rank_suppliers(suppliers, weights)  -> 按总分降序、写入 rank 的列表
  verdict_for(scored)                 -> 一句话评语（由最高维度自动生成）
"""
from __future__ import annotations

DIM_KEYS = ["price", "delivery", "local", "qual", "scale"]
DIM_CN = {
    "price":    "价格竞争力",
    "delivery": "交期保障",
    "local":    "属地履约响应",
    "qual":     "资质合规等级",
    "scale":    "规模与品牌背书",
}
DEFAULT_WEIGHTS = {"price": 32, "delivery": 22, "local": 18, "qual": 16, "scale": 12}

# 资质权威度 → 分值
_QUAL_PTS = {
    "A1": 96.0, "A2": 84.0,
    "API Q1": 94.0, "ISO 9001": 82.0, "CE": 86.0,
    "特种设备制造许可证（A级）": 95.0,
}
_TIER_SCALE = {"national_top": 94.0, "regional": 80.0, "local": 66.0}


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def _dim_price(sup: dict) -> float:
    # price_level 0.85→~100，1.00→~85，1.15→~62（线性偏陡，凸显价格优势）
    pl = sup.get("price_level", 1.0)
    return _clamp(100.0 - (pl - 0.85) * 130.0)


def _dim_delivery(sup: dict) -> float:
    # 30 天≈96，60 天≈78，120 天≈42，180 天≈24
    d = sup.get("lead_time_days", 60)
    return _clamp(108.0 - d * 0.46)


def _dim_local(sup: dict) -> float:
    s = 58.0
    if sup.get("is_local"):
        s += 24.0
    dist = sup.get("distance_km", 600)
    s += max(0.0, 18.0 - dist / 80.0)   # 越近加分，0km≈+18，1440km≈0
    return _clamp(s)


def _dim_qual(sup: dict) -> float:
    return _clamp(_QUAL_PTS.get(sup.get("qualification", ""), 78.0))


def _dim_scale(sup: dict) -> float:
    return _clamp(_TIER_SCALE.get(sup.get("tier", "regional"), 80.0))


def score_supplier(sup: dict, weights: dict | None = None) -> dict:
    w = weights or DEFAULT_WEIGHTS
    dims = {
        "price":    _dim_price(sup),
        "delivery": _dim_delivery(sup),
        "local":    _dim_local(sup),
        "qual":     _dim_qual(sup),
        "scale":    _dim_scale(sup),
    }
    wsum = sum(w.get(k, 0) for k in DIM_KEYS) or 1
    total = sum(dims[k] * w.get(k, 0) for k in DIM_KEYS) / wsum
    return {**sup, "dims": dims, "score": round(total, 1)}


def rank_suppliers(suppliers: list[dict], weights: dict | None = None) -> list[dict]:
    scored = [score_supplier(s, weights) for s in (suppliers or [])]
    # 同分时本地优先、价格低者优先，结果稳定
    scored.sort(key=lambda x: (-x["score"], not x.get("is_local"), x.get("price_level", 1.0)))
    for i, s in enumerate(scored, 1):
        s["rank"] = i
    return scored


def verdict_for(scored: dict) -> str:
    dims = scored.get("dims", {})
    if not dims:
        return ""
    top = max(dims, key=dims.get)
    lead = {
        "price":    "到厂价格最具竞争力",
        "delivery": "交期最短、履约最快",
        "local":    "属地就近响应最强",
        "qual":     "资质等级最权威",
        "scale":    "规模品牌背书最硬",
    }.get(top, "综合均衡")
    role = "🥇 入围首选" if scored.get("rank") == 1 else "入围候选"
    return f"{role} · {lead}"
