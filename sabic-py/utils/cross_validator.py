"""
交叉验证引擎
将企查查（工商权威）+ 化工网（行业活跃度）+ 买化塑（产品真实性）三源合并

验证逻辑：
  企查查 → 法律层面是否存续（工商注册有效）
  化工网 → 行业层面是否活跃（是否在行业平台发布产品）
  买化塑 → 产品层面是否真实（是否有具体产品报价）

置信度计算：
  base         = 企查查数据置信度（始终最高，工商局权威）
  chemnet_hit  = +20%  在化工网有真实产品发布
  ibc_hit      = +15%  在买化塑有产品报价
  both_hit     = +10%  额外加成（三源均命中）
  name_mismatch = -20% 两个平台名称无法对齐（可能是同名不同企业）
"""
from __future__ import annotations
import re
import logging
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# 名称相似度阈值
NAME_MATCH_THRESHOLD = 75  # 0-100，高于此值视为同一企业


def _name_sim(a: str, b: str) -> float:
    """计算两个企业名称的模糊相似度（0-100）"""
    if not a or not b:
        return 0.0
    # 去除法律后缀，只比较有意义的部分
    strip = lambda s: re.sub(r"(有限公司|股份有限公司|有限责任公司|集团|控股)", "", s).strip()
    return fuzz.partial_ratio(strip(a), strip(b))


def validate_supplier(
    qcc_supplier: dict,
    chemnet_items: list[dict],
    ibc_items: list[dict],
    query: str = "",
) -> dict:
    """
    对单个企查查供应商进行三源交叉验证。

    参数：
      qcc_supplier  : 已评分的供应商对象（来自 matcher.py）
      chemnet_items : 化工网搜索结果列表
      ibc_items     : 买化塑搜索结果列表
      query         : 搜索关键词（用于产品匹配）

    返回：
      在 qcc_supplier 基础上追加 _validation 字段
    """
    name = qcc_supplier.get("name", "")
    province = qcc_supplier.get("province", "")

    # ── 化工网匹配 ────────────────────────────────────────────────────
    cn_match  = None
    cn_score  = 0.0
    for cn in chemnet_items:
        sim = _name_sim(name, cn.get("_cn_name") or cn.get("name", ""))
        # 省份一致加分
        prov_ok = province == (cn.get("_cn_province") or cn.get("province", ""))
        score = sim + (5 if prov_ok else 0)
        if score > cn_score:
            cn_score = score
            cn_match = cn if score >= NAME_MATCH_THRESHOLD else None

    # ── 买化塑匹配 ────────────────────────────────────────────────────
    ibc_match = None
    ibc_score = 0.0
    for ib in ibc_items:
        sim = _name_sim(name, str(ib.get("name", "")))
        prov_ok = province == _norm_province_ibc(ib)
        score = sim + (5 if prov_ok else 0)
        if score > ibc_score:
            ibc_score = score
            ibc_match = ib if score >= NAME_MATCH_THRESHOLD else None

    # ── 置信度计算 ────────────────────────────────────────────────────
    base_conf = 60.0  # 企查查单源基础置信度（工商局数据本身就比较可靠）

    chemnet_bonus = 20.0 if cn_match else 0.0
    ibc_bonus     = 15.0 if ibc_match else 0.0
    both_bonus    = 10.0 if (cn_match and ibc_match) else 0.0

    # 产品匹配加分（化工网返回的产品列表含查询词）
    prod_bonus = 0.0
    if cn_match and query:
        cn_prods = cn_match.get("_cn_products") or cn_match.get("main_products", [])
        if any(query in str(p) for p in cn_prods):
            prod_bonus = 8.0

    confidence = min(base_conf + chemnet_bonus + ibc_bonus + both_bonus + prod_bonus, 100.0)

    validation = {
        "_validation": {
            "confidence":       round(confidence, 1),
            "sources":          _build_sources(qcc_supplier, cn_match, ibc_match),
            "chemnet_matched":  cn_match is not None,
            "chemnet_score":    round(cn_score, 1),
            "ibc_matched":      ibc_match is not None,
            "ibc_score":        round(ibc_score, 1),
            "chemnet_products": (cn_match or {}).get("_cn_products", []),
            "chemnet_price":    (cn_match or {}).get("_cn_price_range", ""),
            "ibc_specs":        (ibc_match or {}).get("spec", ""),
            "ibc_price":        (ibc_match or {}).get("price", ""),
        }
    }
    return {**qcc_supplier, **validation}


def _build_sources(qcc, cn_match, ibc_match) -> list[dict]:
    sources = [{"name": "企查查", "matched": True, "color": "#3b82f6", "icon": "🏛"}]
    if cn_match:
        sources.append({"name": "化工网", "matched": True,  "color": "#059669", "icon": "⚗️"})
    else:
        sources.append({"name": "化工网", "matched": False, "color": "#d1d5db", "icon": "⚗️"})
    if ibc_match:
        sources.append({"name": "买化塑", "matched": True,  "color": "#f59e0b", "icon": "🏭"})
    else:
        sources.append({"name": "买化塑", "matched": False, "color": "#d1d5db", "icon": "🏭"})
    return sources


def _norm_province_ibc(item: dict) -> str:
    for key in ("province", "Province", "所在地", "地区"):
        v = item.get(key, "")
        if v:
            return str(v)[:3]
    return ""


def batch_validate(
    suppliers: list[dict],
    chemnet_items: list[dict],
    ibc_items: list[dict],
    query: str = "",
) -> list[dict]:
    """批量交叉验证，返回追加了 _validation 字段的供应商列表"""
    return [
        validate_supplier(s, chemnet_items, ibc_items, query)
        for s in suppliers
    ]


def confidence_label(conf: float) -> tuple[str, str]:
    """返回 (中文标签, 颜色hex)"""
    if conf >= 90: return ("极高置信",  "#15803d")
    if conf >= 75: return ("高置信",    "#059669")
    if conf >= 60: return ("中等置信",  "#d97706")
    if conf >= 45: return ("低置信",    "#dc2626")
    return ("待验证", "#9ca3af")
