"""
采购决策洞察 v1.0  —— 本系统区别于企查查的核心层。

企查查是「查一家公司」的工具；本模块把一组已评分的供应商，
浓缩成「该选谁 / 为什么 / 有哪些场景备选 / 整个供应版图长什么样」的
可执行采购结论。全部为纯函数，输入 = local_search/open_search 产出的
suppliers 列表（已含 score / dimensions / _role 等字段），无任何外部依赖。
"""
from __future__ import annotations
from datetime import datetime

from utils import sites

ROLE_LABEL = {
    "manufacturer": "工厂",
    "both":         "工厂兼贸易",
    "importer":     "进口商",
    "trader":       "经销商",
    "agent":        "中介",
    "unknown":      "类型待核",
}


def cap_text(wan) -> str:
    """注册资本（万元）→ 人类可读。"""
    wan = wan or 0
    if wan >= 10000:
        return f"注册资本 {wan / 10000:.1f} 亿"
    if wan > 0:
        return f"注册资本 {wan:.0f} 万"
    return "资本未披露"


def _age(s: dict) -> int:
    y = s.get("established", 0) or 0
    return max(0, datetime.now().year - y) if y else 0


def _has_hazmat(s: dict) -> bool:
    lic = s.get("licenses", {}) or {}
    return bool(lic.get("hazardous_chemicals") or lic.get("hazmat_business"))


def supplier_highlights(s: dict, max_n: int = 4, site_key: str = "SH") -> list[str]:
    """一家供应商最值得说的几个卖点标签（按优先级），用于卡片/推荐理由。"""
    tags: list[str] = []
    tier = s.get("_tier", 3)
    if tier in (1, 2):
        tags.append(sites.tier_label(tier, site_key))

    cap = s.get("registered_capital_wan", 0) or 0
    if cap >= 100000:
        tags.append("资本超 10 亿")
    elif cap >= 10000:
        tags.append(f"资本 {cap / 10000:.1f} 亿")

    role = s.get("_role", "unknown")
    if role in ("manufacturer", "both"):
        tags.append(ROLE_LABEL[role])

    if _has_hazmat(s):
        tags.append("危化品资质")

    if s.get("chemical_park"):
        tags.append("化工园区内")

    age = _age(s)
    if age >= 20:
        tags.append(f"深耕 {age} 年")

    dist = (s.get("logistics", {}).get("distance_km_to_site")
            or s.get("logistics", {}).get("distance_km_to_shanghai"))
    if isinstance(dist, (int, float)) and dist <= 300:
        tags.append(f"距{sites.get_site(site_key)['short']}约 {int(dist)} 公里")

    return tags[:max_n]


def _why(s: dict, site_key: str = "SH") -> str:
    """一句话推荐理由：取最突出的 3 个卖点串起来。"""
    hl = supplier_highlights(s, 3, site_key)
    return " · ".join(hl) if hl else "综合工商指标占优"


def decision_summary(results: list[dict], site_key: str = "SH") -> dict | None:
    """
    生成采购决策摘要：首选 + 领先幅度 + 三类场景之选。
    返回 None 表示无结果。
    """
    if not results:
        return None

    top = results[0]
    runner = results[1] if len(results) > 1 else None
    lead = round(top.get("score", 0) - runner.get("score", 0), 1) if runner else None

    def _best(dim_key):
        return max(results, key=lambda x: x.get("dimensions", {}).get(dim_key, 0))

    near      = _best("geography")
    strong    = _best("scale")
    compliant = _best("compliance")

    # 场景之选：仅当与首选不同 才有展示价值；同一企业不重复出现
    scenarios = []
    _seen = {top.get("id")}
    for label, icon, pick, dim in [
        ("就近交付", "🚚", near,      "geography"),
        ("实力优先", "🏆", strong,    "scale"),
        ("合规优先", "🛡️", compliant, "compliance"),
    ]:
        if pick.get("id") not in _seen:
            _seen.add(pick.get("id"))
            scenarios.append({
                "label": label, "icon": icon,
                "name":  pick.get("name"),
                "full":  pick.get("name"),
                "score": pick.get("dimensions", {}).get(dim, 0),
                "why":   _why(pick, site_key),
                "id":    pick.get("id"),
            })

    return {
        "top_name":  top.get("name"),
        "top_short": top.get("shortName") or top.get("name"),
        "top_score": top.get("score", 0),
        "top_why":   _why(top, site_key),
        "top_tags":  supplier_highlights(top, 4, site_key),
        "lead":      lead,
        "runner":    (runner.get("shortName") or runner.get("name")) if runner else None,
        "scenarios": scenarios,
        "id":        top.get("id"),
    }


DIM_LABEL = {"geography": "地理位置", "scale": "企业规模", "compliance": "合规资质"}
DIM_ICON  = {"geography": "📍", "scale": "🏢", "compliance": "✅"}
SCENARIO_BY_DIM = {"geography": "就近交付", "scale": "实力优先", "compliance": "合规优先"}
# 与 local_search 的排序优先级一致（数字越小越靠前）
_ROLE_RANK = {"manufacturer": 0, "both": 1, "importer": 2, "trader": 3, "unknown": 4, "agent": 5}


def why_not_top(active: dict, results: list[dict], weights: dict | None = None) -> dict | None:
    """
    解释「为什么这家不是首选」：与列表首位（首选推荐）逐维对比，
    指出主要差距维度、加权失分，以及它在哪个场景下反而更优。
    返回结构化结论，渲染交给 UI。active 即被点开查看的供应商。
    """
    if not results or not active:
        return None
    from utils.scorer import DEFAULT_WEIGHTS
    w = weights or DEFAULT_WEIGHTS

    top = results[0]
    a_id = active.get("id")
    is_top = a_id == top.get("id")
    rank = next((i + 1 for i, s in enumerate(results) if s.get("id") == a_id), None)

    a_dims = active.get("dimensions", {})
    t_dims = top.get("dimensions", {})
    a_score = round(active.get("score", 0), 1)
    t_score = round(top.get("score", 0), 1)
    gap = round(t_score - a_score, 1)

    # 该维度上 active 是否为全场最高（含并列）
    def _is_best(dim):
        mx = max(s.get("dimensions", {}).get(dim, 0) for s in results)
        return a_dims.get(dim, 0) >= mx

    best_in = [dim for dim in ("geography", "scale", "compliance") if _is_best(dim)]

    # 逐维差距：raw>0 表示 active 更强；weighted 为对总分的加权贡献差
    dim_gaps = []
    for k in ("geography", "scale", "compliance"):
        raw = round(a_dims.get(k, 0) - t_dims.get(k, 0), 1)
        dim_gaps.append({
            "key": k, "label": DIM_LABEL[k], "icon": DIM_ICON[k],
            "a": a_dims.get(k, 0), "t": t_dims.get(k, 0),
            "raw": raw, "weighted": round(raw * w.get(k, 0), 1),
        })
    losses = sorted([d for d in dim_gaps if d["raw"] < 0], key=lambda d: d["weighted"])
    wins   = sorted([d for d in dim_gaps if d["raw"] > 0], key=lambda d: -d["weighted"])

    # 场景之选：active 是全场某一维最高 → 在该场景下反而是更优选择
    scenario_fit = [
        {"key": d, "scenario": SCENARIO_BY_DIM[d], "icon": DIM_ICON[d],
         "score": a_dims.get(d, 0)}
        for d in best_in
    ]

    role_label = ROLE_LABEL.get(active.get("_role", "unknown"), "类型待核")
    top_role   = top.get("_role", "unknown")
    role_priority_reason = (
        a_score >= t_score and not is_top
        and _ROLE_RANK.get(active.get("_role", "unknown"), 4) > _ROLE_RANK.get(top_role, 4)
    )

    # 生成叙事
    if is_top:
        verdict = "✅ 它就是当前首选推荐"
        narrative = "在当前筛选与权重下，这家综合表现最优，无需对比。"
    elif role_priority_reason:
        verdict = f"综合分其实持平甚至更高，但寻源默认「工厂优先」"
        narrative = (f"它综合 {a_score} 分，并不低于首选「{top.get('shortName') or top.get('name')}」"
                     f"（{t_score} 分），但首选的经营角色是"
                     f"「{ROLE_LABEL.get(top_role, top_role)}」、本企业是「{role_label}」，"
                     f"排序按工厂 > 工厂兼贸易 > 进口商 > 经销商优先，故它排在后面。")
    else:
        verdict = f"综合 {a_score} 分，落后首选 {gap} 分"
        if losses:
            main = losses[0]
            parts = [f"主要差距在【{main['icon']} {main['label']}】"
                     f"（{main['a']:.0f} vs 首选 {main['t']:.0f}，加权拉开 {abs(main['weighted']):.1f} 分）"]
            if len(losses) > 1:
                second = losses[1]
                parts.append(f"其次是【{second['label']}】（{second['a']:.0f} vs {second['t']:.0f}）")
            narrative = "；".join(parts) + "。"
        else:
            narrative = "各维度与首选接近，差距来自综合加权的细微差异。"

    return {
        "is_top": is_top,
        "rank": rank,
        "verdict": verdict,
        "narrative": narrative,
        "gap": gap,
        "a_score": a_score,
        "t_score": t_score,
        "top_name": top.get("shortName") or top.get("name"),
        "dim_gaps": dim_gaps,
        "losses": losses,
        "wins": wins,
        "scenario_fit": scenario_fit,
        "role_priority_reason": role_priority_reason,
    }


def supply_landscape(results: list[dict], site_key: str = "SH") -> dict:
    """供应市场结构快照：体量 / 地理集中度 / 工厂占比 / 资质 / 资本龙头。"""
    n = len(results)
    if n == 0:
        return {"n": 0}

    cluster = sites.cluster_name(site_key)
    tier1 = sum(1 for s in results if s.get("_tier") == 1)
    tier2 = sum(1 for s in results if s.get("_tier") == 2)
    factories = sum(1 for s in results if s.get("_role") in ("manufacturer", "both"))
    hazmat = sum(1 for s in results if _has_hazmat(s))

    dists = [(s.get("logistics", {}).get("distance_km_to_site")
              or s.get("logistics", {}).get("distance_km_to_shanghai"))
             for s in results]
    dists = [d for d in dists if isinstance(d, (int, float))]
    avg_dist = round(sum(dists) / len(dists)) if dists else None

    # 省份分布（取前 3）
    prov_count: dict[str, int] = {}
    for s in results:
        p = s.get("province") or "未知"
        prov_count[p] = prov_count.get(p, 0) + 1
    top_provs = sorted(prov_count.items(), key=lambda x: -x[1])[:3]

    # 资本龙头
    leader = max(results, key=lambda x: x.get("registered_capital_wan", 0) or 0)

    # 地理集中度结论
    if n:
        share1 = tier1 / n
        if share1 >= 0.6:
            geo_note = f"供应高度集中在{cluster}，距厂区物流半径短、响应快"
        elif share1 >= 0.3:
            geo_note = f"{cluster}与外省各有分布，可在就近与实力间权衡"
        else:
            geo_note = "优质产能多在外省，需关注运距与交期"
    else:
        geo_note = ""

    return {
        "n": n,
        "tier1": tier1,
        "tier2": tier2,
        "tier1_share": round(tier1 / n * 100) if n else 0,
        "factories": factories,
        "factory_share": round(factories / n * 100) if n else 0,
        "hazmat": hazmat,
        "avg_dist": avg_dist,
        "top_provs": top_provs,
        "leader_name": leader.get("shortName") or leader.get("name"),
        "leader_cap": cap_text(leader.get("registered_capital_wan", 0)),
        "geo_note": geo_note,
    }
