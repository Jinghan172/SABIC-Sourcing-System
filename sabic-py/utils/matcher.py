"""
搜索与匹配核心 v3.0
统一数据链路：本地缓存（MCP 采集的企查查数据）优先 → 企查查实时 API 兜底。
演示数据（suppliers.json/chemicals.json 虚拟企业）已全部移除。

筛选字段对照企查查字段：
  provinces     ← Province
  tiers         ← Province 推算
  status_active ← Status
  company_type  ← _role（经营范围分类）
  min_capital   ← registered_capital_wan（RegistCapi 解析）
  est_after     ← established（StartDate 解析）
  only_hazmat   ← _business_scope 含"危险化学品"（否定感知）
  scope_keyword ← _business_scope 文本匹配
  min_score     ← 计算后过滤
"""
from __future__ import annotations

from utils.scorer import DEFAULT_WEIGHTS, TIERS

# 最近一次搜索的元信息（数据来源、详情成功/失败数），供 UI 读取
# 注意：始终原地更新（不重新绑定），保证 `from utils.matcher import LAST_SEARCH_META`
# 拿到的引用在 match_suppliers() 之后仍然有效
LAST_SEARCH_META = {"detail_ok": 0, "detail_fail": 0, "total": 0, "source": ""}


def _set_meta(**kw):
    LAST_SEARCH_META.clear()
    LAST_SEARCH_META.update({"detail_ok": 0, "detail_fail": 0, "total": 0,
                             "source": ""})
    LAST_SEARCH_META.update(kw)

TIER1 = TIERS.get("tier1", {}).get("provinces", [])
TIER2 = TIERS.get("tier2", {}).get("provinces", [])


def _province_tier(province: str) -> int:
    if province in TIER1: return 1
    if province in TIER2: return 2
    return 3


def _apply_filters(supplier: dict, filters: dict, score: float = 0) -> bool:
    """返回 True 表示保留该供应商。所有条件取 AND。"""
    f = filters or {}
    province = supplier.get("province", "")

    # 省份筛选
    if f.get("provinces") and province not in f["provinces"]:
        return False

    # 圈层筛选（来自企查查 Province 推算）
    if f.get("tiers"):
        if _province_tier(province) not in f["tiers"]:
            return False

    # 经营状态（来自企查查 Status）
    if f.get("status_active"):
        status = supplier.get("reg_status", "存续") or "存续"
        if status not in ("存续", "在业", ""):
            return False

    # 企业类型（来自经营范围分类）
    ctype = f.get("company_type", "factory_first")
    role = supplier.get("_role", "unknown")
    if ctype == "manufacturer":
        if role not in ("manufacturer", "both"):
            return False
    elif ctype == "factory_first":
        if role == "agent":      # 默认排除纯中介
            return False
    # ctype == "all"：不过滤

    # 最低注册资本（来自企查查 RegistCapi）
    min_cap = f.get("min_capital", 0) or 0
    if min_cap > 0:
        cap = supplier.get("registered_capital_wan", 0) or 0
        if cap < min_cap:
            return False

    # 成立年份（来自企查查 StartDate）
    est_after = f.get("est_after", 1980) or 1980
    est = supplier.get("established", 0) or 0
    if est_after > 1980 and est > 0 and est < est_after:
        return False

    # 危化品资质（来自经营范围关键词）
    if f.get("only_hazmat"):
        lic = supplier.get("licenses", {})
        scope = supplier.get("_business_scope", "")
        if not (lic.get("hazardous_chemicals") or lic.get("hazmat_business")
                or "危险化学品" in scope):
            return False

    # 经营范围额外关键词（来自企查查 Scope 文本）
    kw = (f.get("scope_keyword") or "").strip()
    if kw:
        scope = supplier.get("_business_scope", "") or " ".join(supplier.get("products", []))
        if kw not in scope:
            return False

    # 最低评分门槛（计算后过滤）
    min_score = f.get("min_score", 0) or 0
    if min_score > 0 and score < min_score:
        return False

    return True


def match_suppliers(
    query: str = "",
    suppliers: list[dict] | None = None,   # 保留参数兼容旧调用方（不再使用）
    filters: dict | None = None,
    weights: dict | None = None,
    use_api: bool | None = None,           # 保留参数兼容旧调用方（始终走真实数据）
) -> tuple[None, list[dict]]:
    """
    主匹配入口（v3.0 仅真实数据）：
      1. 空查询 → 返回空列表（由 UI 展示搜索引导页，不再有演示数据）
      2. 本地缓存命中 → 直接返回（不调 API）
      3. 本地无缓存且配置了企查查 Key → 实时 API 搜索
    """
    query = (query or "").strip()
    if not query:
        _set_meta(source="empty")
        return None, []

    # ── ① 本地缓存优先（MCP 采集的企查查数据）─────────────────────────
    from utils.local_search import search_local, cache_status
    if cache_status()["count"] > 0:
        local_result = search_local(query=query, filters=filters, weights=weights)
        if not local_result.get("cache_missing"):
            _set_meta(
                total=local_result.get("total", 0),
                source="local_cache",
                cache_file=local_result.get("cache_file", ""),
                collected_at=local_result.get("collected_at", ""),
            )
            final = [s for s in local_result["suppliers"]
                     if _apply_filters(s, filters, s.get("score", 0))]
            return None, final

    # ── ② 本地没有 → 企查查实时 API ──────────────────────────────────
    from utils.qcc_client import is_configured
    if not is_configured():
        _set_meta(source="no_api")
        return None, []

    from utils.open_search import open_search
    result = open_search(query=query, filters=filters, weights=weights)
    _set_meta(
        detail_ok=result.get("detail_ok", 0),
        detail_fail=result.get("detail_fail", 0),
        total=result.get("total", 0),
        source="api",
    )
    final = [s for s in result["suppliers"] if _apply_filters(s, filters, s.get("score", 0))]
    return None, final
