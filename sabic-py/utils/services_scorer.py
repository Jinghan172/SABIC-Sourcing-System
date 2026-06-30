# -*- coding: utf-8 -*-
"""
综合服务 / 属地采购 —— 服务类供应商评分引擎  v1.0

区别于主区的企查查工商评分（地理/规模/合规）与核心物料的 6 维专家评分：
服务类供应商（人力/会务/IT/安保/食堂/MRO…）没有注册资本、危化品许可这类
可爬取的工商量化字段，因此这里用一套『5 维加权专家模型』，所有维度均由每家
供应商的结构化标签（tier / nature / sector / quals / local / role）派生而来，
公式透明、可解释、可审计 —— 改一个标签就能复算分数，不是拍脑袋给数字。

五大维度（默认权重，可被各品类 weights 覆盖）：
  ① 资质合规  qual     30%  红线达标度 + 行业资质认证数（RBA/危运/NAID/消防备案/食安…）
  ② 行业适配  sector   22%  石化 / 炼化 / 外资化工经验匹配
  ③ 属地履约  local    20%  本地仓 / 驻点 / 园区官方 / 就近响应
  ④ 规模品牌  scale    16%  全国龙头 / 国企 / 外资背书
  ⑤ 服务保障  service  12%  首选兜底 / SLA / 长期合作稳定性

对外接口：
  DIM_KEYS, DIM_CN, DEFAULT_WEIGHTS
  score_service_supplier(sup, weights)   -> {**sup, "score", "dims"}
  rank_suppliers(suppliers, weights)     -> 按总分降序、写入 rank 的列表
  verdict_for(scored)                    -> 一句话评语（由最高维度自动生成）
"""
from __future__ import annotations

DIM_KEYS = ["qual", "sector", "local", "scale", "service"]
DIM_CN = {
    "qual":    "资质合规达标",
    "sector":  "石化行业适配",
    "local":   "属地履约响应",
    "scale":   "规模与品牌背书",
    "service": "服务保障与兜底",
}
DIM_EN = {
    "qual":    "Qualification & compliance",
    "sector":  "Petrochemical fit",
    "local":   "Local fulfillment",
    "scale":   "Scale & brand backing",
    "service": "Service assurance",
}
DEFAULT_WEIGHTS = {"qual": 30, "sector": 22, "local": 20, "scale": 16, "service": 12}

# ── 标签→分值映射（全部可解释）────────────────────────────────────────
_TIER_SCALE  = {"national_top": 92.0, "regional": 80.0, "local": 67.0}
_NATURE_BONUS = {"foreign": 6.0, "soe": 5.0, "joint": 4.0, "private": 0.0}
_SECTOR_FIT  = {"petrochem": 100.0, "chemical": 88.0, "industrial": 72.0, "general": 56.0}
_LOCAL_PTS   = {"park_official": 26.0, "onsite": 24.0, "warehouse": 22.0,
                "local_branch": 16.0, "regional_hub": 11.0}

_QUAL_BASE   = 56.0   # 基准合规分
_QUAL_PER    = 8.0    # 每多一项资质认证 +8（封顶 100）
_LOCAL_BASE  = 48.0


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def _dim_qual(sup: dict) -> float:
    n = len(sup.get("quals", []) or [])
    s = _QUAL_BASE + _QUAL_PER * n
    if sup.get("role") == "primary":
        s += 4.0   # 首选通常红线达标标杆
    return _clamp(s)


def _dim_sector(sup: dict) -> float:
    return _clamp(_SECTOR_FIT.get(sup.get("sector", "general"), 56.0))


def _dim_local(sup: dict) -> float:
    s = _LOCAL_BASE + sum(_LOCAL_PTS.get(f, 0.0) for f in sup.get("local", []) or [])
    return _clamp(s)


def _dim_scale(sup: dict) -> float:
    s = _TIER_SCALE.get(sup.get("tier", "local"), 67.0)
    s += _NATURE_BONUS.get(sup.get("nature", "private"), 0.0)
    return _clamp(s)


def _dim_service(sup: dict) -> float:
    s = 62.0
    if sup.get("role") == "primary":
        s += 18.0
    if sup.get("tier") == "national_top":
        s += 6.0   # 全国平台具备调拨兜底能力
    if any(f in ("onsite", "warehouse") for f in sup.get("local", []) or []):
        s += 6.0   # 驻场 / 本地仓 → 响应与兜底更强
    return _clamp(s)


def score_service_supplier(sup: dict, weights: dict | None = None) -> dict:
    """计算单个服务供应商的 5 维分与加权总分。"""
    w = weights or DEFAULT_WEIGHTS
    dims = {
        "qual":    _dim_qual(sup),
        "sector":  _dim_sector(sup),
        "local":   _dim_local(sup),
        "scale":   _dim_scale(sup),
        "service": _dim_service(sup),
    }
    wsum = sum(w.get(k, 0) for k in DIM_KEYS) or 1
    total = sum(dims[k] * w.get(k, 0) for k in DIM_KEYS) / wsum
    return {**sup, "dims": dims, "score": round(total, 1)}


def rank_suppliers(suppliers: list[dict], weights: dict | None = None) -> list[dict]:
    """对一个基地的供应商列表打分并按总分降序，写入 1..N 名次。"""
    scored = [score_service_supplier(s, weights) for s in (suppliers or [])]
    scored.sort(key=lambda x: -x["score"])
    for i, s in enumerate(scored, 1):
        s["rank"] = i
    return scored


def verdict_for(scored: dict) -> str:
    """由最高维度 + 角色自动生成一句话评语，避免逐家手写。"""
    dims = scored.get("dims", {})
    if not dims:
        return ""
    top = max(dims, key=dims.get)
    role = "Strategic top pick · 战略首选" if scored.get("role") == "primary" else "Backup · 备选补位"
    lead = {
        "qual":    "leads on red-line qualifications · 红线资质达标领先",
        "sector":  "best petrochemical fit · 石化行业适配最优",
        "local":   "strongest local response & proximity · 属地响应与就近履约最强",
        "scale":   "hardest scale & brand backing · 规模品牌背书最硬",
        "service": "fullest service assurance · 服务兜底保障最足",
    }.get(top, "balanced overall · 综合均衡")
    return f"{role} · {lead}"


# ════════════════════════════════════════════════════════════════════
# 评分可解释性 + 尽职利弊分析 —— 让每个分数有据可查，像咨询报告一样讲清取舍
# ════════════════════════════════════════════════════════════════════
_TIER_CN   = {"national_top": "National top platform · 全国头部平台", "regional": "Regional leader · 区域龙头", "local": "Local vendor · 属地厂商"}
_NATURE_CN = {"foreign": "Foreign-backed · 外资背书", "soe": "SOE-backed · 国企背书", "joint": "JV-backed · 合资背书", "private": "Private · 民营"}
_SECTOR_CN = {"petrochem": "Direct petrochem/refining experience · 石化/炼化直接经验", "chemical": "Chemical industry experience · 化工行业经验",
              "industrial": "General industrial experience · 一般工业制造经验", "general": "General service experience · 通用服务经验"}
_LOCAL_CN  = {"park_official": "Park official platform · 园区官方平台", "onsite": "On-site presence · 厂区驻点", "warehouse": "Local warehouse · 本地仓储",
              "local_branch": "Local branch · 本地分支机构", "regional_hub": "Regional hub · 区域枢纽辐射"}

# 各维度一句话方法论（展示在尽调卡里，说明分数怎么来）
DIM_METHOD = {
    "qual":    "Base 56; +8 per industry qualification/cert (top pick +4 more), capped at 100. · 合规基准 56 分起步，每具备一项行业资质/认证 +8 分（首选标杆再 +4），满分封顶 100。",
    "sector":  "Mapped directly from main-industry experience: petrochem 100 / chemical 88 / industrial 72 / general 56. · 按主营行业经验直接映射：石化 100 / 化工 88 / 一般工业 72 / 通用 56。",
    "local":   "On-site baseline 48, plus per local-fulfillment flag (park official/on-site/local warehouse/branch/hub). · 到场服务基线 48 分，叠加属地履约旗标（园区官方/驻点/本地仓/分支/枢纽）逐项加分。",
    "scale":   "Base by scale tier (national 92 / regional 80 / local 67), plus ownership bonus (foreign/SOE/JV). · 规模圈层定基（全国 92 / 区域 80 / 属地 67），再按企业性质（外资/国企/合资）加成。",
    "service": "Assurance baseline 62; top pick +18, national platform +6, on-site or local warehouse +6. · 服务保障基线 62 分，战略首选 +18、全国平台调拨 +6、驻场或本地仓 +6。",
}


def explain_supplier(sup: dict) -> dict:
    """返回每个维度的『得分构成明细』：[(标签, 说明, 贡献分), ...] + 最终分。
    与各 _dim_* 计算逐项对应，便于在界面上把分数拆开给采购看。"""
    quals = sup.get("quals", []) or []
    local = sup.get("local", []) or []
    is_primary = sup.get("role") == "primary"

    # qual
    qual_items = [("Compliance base · 合规基准分", "服务类供应商准入基线", _QUAL_BASE)]
    if quals:
        qual_items.append((f"{len(quals)} quals/certs · 项资质/认证", "、".join(quals), _QUAL_PER * len(quals)))
    if is_primary:
        qual_items.append(("Top-pick red-line · 首选红线标杆", "本基地战略首选，红线达标基准", 4.0))

    # sector
    sec = sup.get("sector", "general")
    sector_items = [(_SECTOR_CN.get(sec, "General service experience · 通用服务经验"), "主营行业经验直接映射",
                     _SECTOR_FIT.get(sec, 56.0))]

    # local
    local_items = [("On-site baseline · 到场服务基线", "具备基本属地服务能力", _LOCAL_BASE)]
    for f in local:
        local_items.append((_LOCAL_CN.get(f, f), "属地履约旗标", _LOCAL_PTS.get(f, 0.0)))

    # scale
    tier = sup.get("tier", "local")
    nature = sup.get("nature", "private")
    scale_items = [(_TIER_CN.get(tier, "Local vendor · 属地厂商"), "规模圈层定基", _TIER_SCALE.get(tier, 67.0))]
    if _NATURE_BONUS.get(nature, 0.0) > 0:
        scale_items.append((_NATURE_CN.get(nature, "Private · 民营"), "企业性质加成", _NATURE_BONUS[nature]))

    # service
    service_items = [("Service baseline · 服务保障基线", "常规 SLA 履约", 62.0)]
    if is_primary:
        service_items.append(("Top-pick assurance · 战略首选兜底", "长期稳定 + 优先响应", 18.0))
    if tier == "national_top":
        service_items.append(("National dispatch · 全国平台调拨", "跨区资源兜底能力", 6.0))
    if any(f in ("onsite", "warehouse") for f in local):
        service_items.append(("On-site/warehouse · 驻场/本地仓", "现场响应更快", 6.0))

    dims = sup.get("dims") or score_service_supplier(sup)["dims"]
    return {
        "qual":    {"score": dims["qual"],    "items": qual_items,    "method": DIM_METHOD["qual"]},
        "sector":  {"score": dims["sector"],  "items": sector_items,  "method": DIM_METHOD["sector"]},
        "local":   {"score": dims["local"],   "items": local_items,   "method": DIM_METHOD["local"]},
        "scale":   {"score": dims["scale"],   "items": scale_items,   "method": DIM_METHOD["scale"]},
        "service": {"score": dims["service"], "items": service_items, "method": DIM_METHOD["service"]},
    }


def analyze_supplier(scored: dict) -> dict:
    """咨询式尽调结论：优势 / 短板与风险 / 适用场景 / 慎用场景 / 一句话定调。
    全部由维度分与结构化标签推导，可解释、可复算。"""
    dims = scored.get("dims", {})
    quals = scored.get("quals", []) or []
    local = scored.get("local", []) or []
    tier = scored.get("tier", "local")
    nature = scored.get("nature", "private")
    sector = scored.get("sector", "general")
    is_primary = scored.get("role") == "primary"
    strong_local = [f for f in local if f in ("park_official", "onsite", "warehouse")]

    pros, cons, fit, caution = [], [], [], []

    # ── 优势 ───────────────────────────────────────────────
    if dims.get("qual", 0) >= 85:
        pros.append(f"Strong compliance: {len(quals)} industry quals/certs ({'、'.join(quals[:4])}), high red-line conformance · 资质合规领先：具备 {len(quals)} 项行业资质/认证，红线达标度高")
    if sector in ("petrochem", "chemical"):
        pros.append(f"Strong industry fit: {_SECTOR_CN[sector]}, familiar with petrochem/chemical site work & compliance · 行业适配强，熟悉石化/化工现场作业与合规要求")
    if strong_local:
        pros.append(f"Fast local fulfillment: { '、'.join(_LOCAL_CN[f] for f in strong_local) } — proximity response & emergency on-site assured · 属地履约快，就近响应、应急到场有保障")
    if tier == "national_top":
        pros.append("Scale & backup: national top platform, strong multi-base coordination & cross-region dispatch · 规模与兜底：全国头部平台，多基地协同、跨区资源调拨能力强")
    if nature in ("foreign", "soe"):
        pros.append(f"{_NATURE_CN[nature]}: mature compliance & audit systems, fits foreign-chemical governance · 合规与审计体系成熟，适配外资化工治理要求")
    if is_primary:
        pros.insert(0, "Strategic top pick at this base: highest overall, stable long-term cooperation & priority response · 本基地战略首选：综合评分居首，长期合作稳定、优先响应")

    # ── 短板与风险 ─────────────────────────────────────────
    if dims.get("qual", 0) < 72:
        cons.append("Few certifications: limited industry quals; add third-party verification & on-site audit before signing · 资质认证偏少：行业资质数量有限，签约前需补充第三方核验与现场审核")
    if sector in ("industrial", "general"):
        cons.append(f"Weaker industry experience: {_SECTOR_CN[sector]}, lacks direct petrochem cases; assess process & safety fit · 行业经验偏弱，缺乏石化/炼化直接案例，需评估工艺与安全适配")
    if not strong_local:
        cons.append("Remote-dependent local response: no on-site/local warehouse; emergency & high-frequency on-site response slower · 属地响应依赖远程：无厂区驻点/本地仓，应急与高频到场响应相对偏慢")
    if tier == "local":
        cons.append("Smaller scale: local vendor; limited coordination/backup for large volume, multi-base or sudden ramp-up · 规模偏小：属地厂商，大体量、多基地或突发扩容时协同与兜底能力有限")
    if dims.get("service", 0) < 75 and not is_primary:
        cons.append("Average backup: not the top pick and lacks dispatch capacity; use as backup, not sole supplier · 兜底保障一般：非首选、缺少调拨能力，建议作为备选而非独家供应")
    if not cons:
        cons.append("No clear weakness: balanced across dimensions; main risk is price & commercial terms, lock in at RFQ · 无显著短板：各维度均衡，主要风险点为价格与商务条款，需在询价阶段锁定")

    # ── 适用 / 慎用场景 ────────────────────────────────────
    top = max(dims, key=dims.get) if dims else None
    fit_map = {
        "qual":    "Primary for highly-regulated / high-compliance categories (hazmat, food safety, fire, data security) · 强监管 / 高合规要求品类（危化、食安、消防、数据安全）的主供",
        "sector":  "Petrochem/refining site work, process-related projects needing industry know-how · 石化炼化现场作业、工艺相关、需行业 know-how 的项目",
        "local":   "Daily fulfillment with high on-site frequency, emergency response & local presence needs · 高频到场、应急响应、属地驻点要求高的日常履约",
        "scale":   "Large frameworks, multi-base central buys, strategic ties needing brand backing & stable backup · 大体量框架、多基地统采、需品牌背书与稳定兜底的战略合作",
        "service": "Long-term sole/primary supply needing SLA & sustained stability · 长期独家 / 主供，需 SLA 与持续稳定保障的场景",
    }
    if top:
        fit.append(fit_map.get(top, "General fulfillment · 综合履约场景"))
    if is_primary:
        fit.append("Include as this base's primary / framework-agreement top pick · 作为本基地主供 / 框架协议首选纳入")
    else:
        fit.append("Use as backup / second source for benchmarking, split-orders & risk hedging · 作为备选 / 第二供应商，用于比价、分单与风险对冲")

    if tier == "local":
        caution.append("Not suitable to solely handle multi-base, large-volume or heavy ramp-up tasks · 不宜独家承担多基地、大体量或强扩容任务")
    if sector in ("industrial", "general"):
        caution.append("Not as sole supplier for core-process / high-hazard work · 涉及核心工艺 / 高危作业时不宜作为唯一供应")
    if not strong_local:
        caution.append("For ultra-time-critical emergencies, use cautiously or require on-site commitment · 对到场时效要求极高的应急场景需谨慎或要求驻点承诺")
    if not caution:
        caution.append("No clear no-go scenario; standard red-line verification per category suffices · 无明显禁用场景，按品类红线常规核验即可")

    # ── 一句话定调 ─────────────────────────────────────────
    if is_primary:
        verdict = "Best overall, usable as primary — but keep 1 backup to hedge single-point risk & pricing. · 综合最优、可作主供——但仍建议保留 1 家备选以对冲单点风险与议价。"
    elif scored.get("score", 0) >= 80:
        verdict = "Close to the top pick, better on specific dimensions — fits as a strong backup or split-order second source. · 实力接近首选、特定维度更优——适合作为强备选或分单第二供应。"
    else:
        verdict = "Has clear weaknesses — use only in its advantage scenarios, not as sole supplier. · 存在明显短板——建议仅在其优势场景下定向使用，不作独家。"

    return {"pros": pros, "cons": cons, "fit": fit, "caution": caution,
            "verdict": verdict, "top_dim": top}
