"""
SABIC 供应商全量化评分算法  v3.0
三个维度全部基于企查查工商数据的客观可量化指标。
（v3.0 移除"经营相关度"维度——本地缓存品类与企业一一对应，相关性由采集时
  recheck_relevance 保证；移除专利加分——企查查专利接口无数据，全为0无意义）

维度（默认权重）：
  ① 地理位置      geography   35%  — 省份圈层 + km 距离（纯数字）
  ② 企业规模      scale       35%  — 注册资本 + 成立年限（纯数字）
  ③ 合规与资质    compliance  30%  — 经营状态/角色/许可/园区/行业/进出口（全部可量化）

字段来源：全部来自企查查工商信息（status/scope/industry/address/RegistCapi/StartDate）
"""
from __future__ import annotations
import re
import json
from pathlib import Path
from datetime import datetime

from utils import sites

_DATA = Path(__file__).parent.parent / "data"
with open(_DATA / "regions.json", encoding="utf-8") as f:
    REGIONS = json.load(f)

TIERS          = REGIONS["tiers"]
PROVINCE_COORDS = REGIONS.get("provinceCoords", {})  # {省名: {lng,lat,distance_km}}

DEFAULT_WEIGHTS = {
    "geography":  0.35,
    "scale":      0.35,
    "compliance": 0.30,
}

# 同义词表：从 data/synonyms.json 动态加载（open_search.py 用于 API 搜索词扩展）
try:
    with open(_DATA / "synonyms.json", encoding="utf-8") as _sf:
        _SYNONYMS: dict[str, list[str]] = json.load(_sf)
except Exception:
    _SYNONYMS = {}  # 文件不存在时降级

# 互联网公开信息补充表：修正纯爬取经营范围导致的可靠企业合规低估
try:
    with open(_DATA / "web_reputation.json", encoding="utf-8") as _wf:
        WEB_REPUTATION: list[dict] = json.load(_wf).get("entries", [])
except Exception:
    WEB_REPUTATION = []


def reputation_for(name: str) -> dict | None:
    """按公司名包含匹配互联网公开信息条目（取 floor 最高者）。"""
    n = name or ""
    hits = [e for e in WEB_REPUTATION if e.get("match") and e["match"] in n]
    return max(hits, key=lambda e: e.get("floor", 0)) if hits else None


# ════════════════════════════════════════════════════════════════════
# ① 地理位置评分  (0-100)  ← 纯量化
# ════════════════════════════════════════════════════════════════════
# 距离-评分插值锚点（km, 分）：连续曲线，使同圈层内不同省份拉开差距
# 例：山东(680)≈68 vs 广东(1450)≈35，二级圈不再被压成同一分
_DIST_ANCHORS = [
    (0, 100.0), (180, 95.0), (280, 90.0), (470, 81.0), (680, 68.0),
    (850, 60.0), (920, 56.0), (1080, 49.0), (1230, 43.0), (1450, 35.0),
    (1670, 28.0), (1950, 19.0), (2400, 12.0), (3300, 8.0), (4000, 6.0),
]


def _distance_score(km: float) -> float:
    """按真实公里数做分段线性插值，得到连续的地理分（同圈层内有区分度）。"""
    if km <= _DIST_ANCHORS[0][0]:
        return _DIST_ANCHORS[0][1]
    for (k0, s0), (k1, s1) in zip(_DIST_ANCHORS, _DIST_ANCHORS[1:]):
        if km <= k1:
            return round(s0 + (s1 - s0) * (km - k0) / (k1 - k0), 1)
    return _DIST_ANCHORS[-1][1]


def score_geography(supplier: dict, site_key: str = sites.DEFAULT_SITE) -> float:
    """
    来源字段：province（企查查 Province 字段）+ 到所选厂区的真实公里数。
    多厂区改版：距离与属地圈层均以『当前所选厂区』为锚点独立计算——
    选上海就按距上海，选南沙/古雷/重庆就按距该厂区（utils/sites.py 统一口径）。
    厂区所在经济区一级圈再叠加少量"物流成熟度"加成。
    """
    province = supplier.get("province", "")

    distance = (
        supplier.get("logistics", {}).get("distance_km_to_site")
        or supplier.get("logistics", {}).get("distance_km_to_shanghai")
    )
    if distance is None:
        distance = sites.distance_to_site(province, site_key) if province else 1500

    base = _distance_score(distance)

    # 厂区一级圈物流成熟度加成（就近公路 1-2 天、合规资源成熟），其余圈层不加
    if sites.province_tier(province, site_key) == 1:
        base += 5.0
    return round(min(base, 100.0), 1)


# ════════════════════════════════════════════════════════════════════
# ② 企业规模评分  (0-100)  ← 纯量化
# ════════════════════════════════════════════════════════════════════
def score_scale(supplier: dict) -> float:
    """
    来源字段：
      registered_capital_wan — 企查查 RegistCapi 解析（万元）
      established            — 企查查 StartDate 解析（年份）
    计算方式：注册资本分 × 65% + 成立年限分 × 35%
    """
    cap  = supplier.get("registered_capital_wan", 0) or 0
    year = supplier.get("established", 0) or 0
    age  = max(0, datetime.now().year - year) if year else 0

    # 注册资本分（对数尺度）
    if cap >= 100_000:    # ≥10亿
        cap_score = 100.0
    elif cap >= 50_000:   # ≥5亿
        cap_score = 90.0
    elif cap >= 10_000:   # ≥1亿
        cap_score = 78.0
    elif cap >= 5_000:    # ≥5000万
        cap_score = 64.0
    elif cap >= 1_000:    # ≥1000万
        cap_score = 50.0
    elif cap >= 200:      # ≥200万
        cap_score = 36.0
    elif cap > 0:
        cap_score = 22.0
    else:
        cap_score = 30.0  # 未知 → 中性

    # 成立年限分
    if age >= 20:
        age_score = 100.0
    elif age >= 15:
        age_score = 85.0
    elif age >= 10:
        age_score = 70.0
    elif age >= 5:
        age_score = 50.0
    elif age >= 2:
        age_score = 30.0
    elif age > 0:
        age_score = 10.0
    else:
        age_score = 30.0  # 未知 → 中性

    return round(0.65 * cap_score + 0.35 * age_score, 1)


# ════════════════════════════════════════════════════════════════════
# ③ 合规与资质评分  (0-100)  ← 全部可量化指标，v3.0 重写提升区分度
# ════════════════════════════════════════════════════════════════════
# 危化品许可：正向关键词命中才给分，"不含/除危险化学品"等否定表述不给分
_HM_POS = ["危险化学品经营", "危险化学品生产", "危险化学品储存",
           "危险化学品批发", "危险化学品仓储", "危险化学品许可"]
_HM_NEG = ["不含危险化学品", "除危险化学品", "非危险化学品",
           "危险化学品除外", "危化品除外", "（危化品除外）"]

# 行业匹配：企查查 industry 字段属于化工/材料制造业
_IND_CHEM = ["化学原料", "化学制品", "化学纤维", "石油", "橡胶", "塑料",
             "化学农药", "涂料", "颜料", "合成材料", "专用化学"]
_IND_MFG  = ["制造", "材料", "矿物", "金属", "纺织", "造纸", "包装"]


def has_hazmat_license(scope: str) -> bool:
    """从经营范围判断危化品许可（否定表述感知）。"""
    s = scope or ""
    if any(k in s for k in _HM_POS):
        return True
    return "危险化学品" in s and not any(k in s for k in _HM_NEG)


def score_compliance(supplier: dict) -> float:
    """
    来源字段（全部来自企查查工商数据，可量化、可解释）：
      reg_status       — 企查查 Status（存续/注销/吊销）
      _role            — 经营范围文本分类（manufacturer/both/trader/...）
      _business_scope  — 企查查 Scope 全文
      industry         — 企查查行业分类
      address          — 注册地址
    得分构成（满分100）：
      经营状态 存续/在业        25 分
      企业角色 工厂20/兼贸易16/进口8/经销4/未知8/中介0
      危化品许可（否定感知）    20 分
      生产/安全许可证关键词     10 分
      化工园区10 / 工业园区5    （地址或经营范围）
      化工类行业10 / 制造类行业5（企查查行业字段）
      进出口经营资质             5 分
    """
    scope    = supplier.get("_business_scope", "") or ""
    industry = supplier.get("industry", "") or ""
    address  = supplier.get("address", "") or ""
    score = 0.0

    # 经营状态（25分）
    status = supplier.get("reg_status", "存续") or "存续"
    if status in ("存续", "在业", ""):
        score += 25

    # 企业角色分类（0-20分）—— 工厂优先，中介不得分
    role = supplier.get("_role", "unknown")
    role_map = {
        "manufacturer": 20,   # 工厂
        "both":         16,   # 工厂兼贸易
        "importer":      8,   # 进口商
        "trader":        4,   # 经销商
        "agent":         0,   # 纯中介
        "unknown":       8,
    }
    score += role_map.get(role, 8)

    # 危险化学品许可（20分）— 否定表述感知
    lic = supplier.get("licenses", {})
    if lic.get("hazardous_chemicals") or lic.get("hazmat_business") \
            or has_hazmat_license(scope):
        score += 20

    # 生产/安全许可证关键词（10分）
    if any(k in scope for k in ["生产许可", "安全生产许可", "生产经营许可",
                                "全国工业产品生产许可"]):
        score += 10

    # 化工园区（10分）/ 一般工业园区（5分）— 地址或经营范围
    loc_text = address + " " + scope
    if any(k in loc_text for k in ["化工园", "化工区", "化工园区", "化学工业园"]):
        score += 10
    elif any(k in loc_text for k in ["工业园", "工业区", "经济开发区", "高新区",
                                     "经济技术开发区"]):
        score += 5

    # 行业匹配（10/5分）— 企查查行业分类字段
    if any(k in industry for k in _IND_CHEM):
        score += 10
    elif any(k in industry for k in _IND_MFG):
        score += 5

    # 进出口经营资质（5分）
    if any(k in scope for k in ["进出口", "货物及技术进出口"]):
        score += 5

    # ISO/安全生产等资质（来自255资质接口，仅API模式可能有，封顶100）
    iso_certs = lic.get("iso_certs", []) or []
    if iso_certs:
        score += min(len(iso_certs) * 5, 10)
    if lic.get("safety_production") is True:
        score += 5

    # 规模信用（最高+8）— 长期存续的大型企业，资质大概率齐全，
    # 修正"爬不到许可关键词就低估可靠企业"的偏差（如甘肃东方钛业/中核钛白）
    cap  = supplier.get("registered_capital_wan", 0) or 0
    year = supplier.get("established", 0) or 0
    age  = max(0, datetime.now().year - year) if year else 0
    if cap >= 10_000 and age >= 15:
        score += 8
    elif cap >= 5_000 and age >= 10:
        score += 5
    elif cap >= 1_000 and age >= 8:
        score += 3

    # 互联网公开信息下限：上市/龙头/可靠企业不因爬取缺失而被打低分
    rep = reputation_for(supplier.get("name", ""))
    if rep:
        score = max(score, float(rep.get("floor", 0)))

    return min(score, 100.0)


# ════════════════════════════════════════════════════════════════════
# 总分计算
# ════════════════════════════════════════════════════════════════════
def score_supplier(
    supplier: dict,
    chemical: dict | None = None,  # 保留参数兼容旧调用方
    weights: dict | None = None,
    query: str = "",               # 保留参数兼容旧调用方
    site_key: str = sites.DEFAULT_SITE,
) -> dict:
    """
    计算供应商综合得分（三维：地理/规模/合规）。
    所有维度均为客观量化指标，公式透明可解释。
    geography 与圈层标签按 site_key 所选厂区独立计算。
    """
    w = weights or DEFAULT_WEIGHTS

    dims = {
        "geography":  score_geography(supplier, site_key),
        "scale":      score_scale(supplier),
        "compliance": score_compliance(supplier),
    }

    total = sum(dims[k] * w.get(k, 0) for k in ["geography", "scale", "compliance"])

    # 圈层标签（按所选厂区）
    province = supplier.get("province", "")
    tier  = sites.province_tier(province, site_key)

    out = {
        **supplier,
        "score":      round(total, 1),
        "dimensions": dims,
        "_tier":      tier,
        "_site":      site_key,
    }
    # 互联网公开信息核验（若命中）——供详情页展示，解释合规分为何被抬高
    rep = reputation_for(supplier.get("name", ""))
    if rep:
        out["_reputation"] = rep
    return out


def get_tier_label(province: str, site_key: str = sites.DEFAULT_SITE) -> str:
    return sites.tier_label(sites.province_tier(province, site_key), site_key)
