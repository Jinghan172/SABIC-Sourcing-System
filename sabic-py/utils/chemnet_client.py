"""
化工网 (ChemNet) 数据客户端
官网：https://china.chemnet.com/
开放平台：https://api.chemnet.com （需注册获取 API Key）

数据定位：
  - 化工行业专业 B2B 平台，专注化工产品和供应商
  - 可获取字段：实际经营产品、规格参数、报价区间、行业资质
  - 与企查查互补：企查查提供工商合规，化工网提供行业真实经营状态

认证方式：Bearer Token（注册后在控制台获取）
  Authorization: Bearer <api_key>

主要 API 接口：
  GET /v1/suppliers/search?keyword=聚乙烯&page=1&page_size=20
    → 返回化工行业供应商列表（已实际在平台发布产品的企业）
  GET /v1/products/search?keyword=聚乙烯&supplier_id=xxx
    → 返回某供应商的产品列表（含规格、价格、产地）
  GET /v1/supplier/{id}
    → 供应商详情（联系方式、主营产品、认证资质）

本地下载备选方案（无 API 时）：
  https://china.chemnet.com/ent/search.html?q=<关键词>
  → 手动筛选 → 导出为 Excel → 存入 data/chemnet/ 目录
"""
from __future__ import annotations
import os
import json
import time
import hashlib
import logging
from pathlib import Path
import requests
import diskcache

logger = logging.getLogger(__name__)

CHEMNET_BASE = "https://api.chemnet.com"
_CACHE_DIR   = Path(__file__).parent.parent / ".cache" / "chemnet"
_CACHE       = diskcache.Cache(str(_CACHE_DIR), size_limit=200_000_000)
_DATA_DIR    = Path(__file__).parent.parent / "data" / "chemnet"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL = {
    "search":  60 * 60 * 12,   # 供应商搜索缓存 12 小时
    "detail":  60 * 60 * 24 * 3,  # 供应商详情缓存 3 天
}


def _call(endpoint: str, params: dict, ttl_key="search") -> dict | None:
    api_key = os.environ.get("CHEMNET_API_KEY", "")
    if not api_key:
        return None  # 未配置，静默跳过

    ck = hashlib.md5(f"chemnet|{endpoint}|{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
    if ck in _CACHE:
        return _CACHE[ck]

    try:
        resp = requests.get(
            f"{CHEMNET_BASE}/{endpoint}",
            params=params,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 200 or data.get("status") == "ok":
            result = data.get("data") or data.get("result", {})
            _CACHE.set(ck, result, expire=CACHE_TTL[ttl_key])
            return result
    except Exception as e:
        logger.warning(f"化工网 API 调用失败: {e}")
    return None


def search_chem_suppliers(keyword: str, page: int = 1, page_size: int = 20) -> list[dict]:
    """
    按产品关键词搜索化工网注册供应商。
    返回：已在化工网实际发布产品的企业列表（比企查查更贴近实际经营状态）
    字段：name, province, main_products, price_range, certifications, contact
    """
    result = _call("v1/suppliers/search",
                   {"keyword": keyword, "page": page, "page_size": page_size})
    if result:
        return result.get("items", [])

    # ── 降级：从本地下载文件读取 ────────────────────────────────────
    return _load_local(keyword)


def get_supplier_detail(supplier_id: str) -> dict | None:
    """获取化工网供应商详情（产品规格、价格、资质证书）"""
    return _call(f"v1/supplier/{supplier_id}", {}, ttl_key="detail")


def _load_local(keyword: str) -> list[dict]:
    """
    从本地下载文件加载化工网供应商数据（API 不可用时的备选方案）。
    文件格式：data/chemnet/<keyword>.json 或 <keyword>.xlsx
    """
    # 尝试 JSON
    json_file = _DATA_DIR / f"{keyword}.json"
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("items", [])
        except Exception:
            pass

    # 尝试 Excel（需要 openpyxl）
    xlsx_file = _DATA_DIR / f"{keyword}.xlsx"
    if xlsx_file.exists():
        try:
            import pandas as pd
            df = pd.read_excel(xlsx_file)
            return df.to_dict("records")
        except Exception:
            pass
    return []


def chemnet_to_cross_fields(supplier: dict) -> dict:
    """
    把化工网返回字段映射成交叉验证标准格式。
    用于与企查查数据对比验证。
    """
    return {
        "_source_chemnet": True,
        "_cn_name":         supplier.get("name", ""),
        "_cn_province":     supplier.get("province", ""),
        "_cn_products":     supplier.get("main_products", []),
        "_cn_price_range":  supplier.get("price_range", ""),
        "_cn_certifications": supplier.get("certifications", []),
        "_cn_active":       supplier.get("status", "") in ("正常", "在业", ""),
    }


def is_configured() -> bool:
    return bool(os.environ.get("CHEMNET_API_KEY"))
