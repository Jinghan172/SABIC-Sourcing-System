"""
企查查 API 客户端
官网：https://openapi.qcc.com/

认证方式（与天眼查不同）：
  Token = MD5(AppKey + Timespan + SecretKey).toUpperCase()
  每次请求都要重新生成 Token（Timespan 是当前秒级时间戳）

本地运行时：Python 直接调用 api.qichacha.com，无需任何代理
生产部署时：建议同样通过服务端环境变量注入 Key，不暴露给前端

需要配置的环境变量（写在 .env.local）：
  QCC_APP_KEY=你的 AppKey
  QCC_SECRET_KEY=你的 SecretKey
"""
from __future__ import annotations

import os
import re
import hashlib
import time
import json
import logging
import threading
from pathlib import Path
import requests
import diskcache

logger = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────────────────────
QCC_BASE    = "https://api.qichacha.com"
CACHE_DIR   = Path(__file__).parent.parent / ".cache" / "qcc"
CACHE_TTL   = {
    "search": 60 * 60 * 6,       # 搜索结果缓存 6 小时
    "detail": 60 * 60 * 24 * 7,  # 企业详情缓存 7 天
}

_CACHE = diskcache.Cache(str(CACHE_DIR), size_limit=300_000_000)


# ── MD5 签名 ─────────────────────────────────────────────────────────
def _make_token(app_key: str, secret_key: str) -> tuple[str, str]:
    """返回 (token, timespan)，每次调用前实时生成，不可复用。"""
    timespan = str(int(time.time()))
    raw = f"{app_key}{timespan}{secret_key}"
    token = hashlib.md5(raw.encode("utf-8")).hexdigest().upper()
    return token, timespan


# ── 令牌桶速率限制 ────────────────────────────────────────────────────
class _TokenBucket:
    def __init__(self, rate=1.5, burst=5):
        self._rate   = rate
        self._burst  = burst
        self._tokens = float(burst)
        self._last   = time.monotonic()
        self._lock   = threading.Lock()

    def acquire(self, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return True
            time.sleep(0.12)
        return False


_LIMITER = _TokenBucket(rate=1.5, burst=4)


# ── 核心请求函数 ──────────────────────────────────────────────────────
def _qcc_get(endpoint: str, params: dict, ttl_key="search") -> dict | None:
    """
    发起一次企查查 GET 请求。
    - 先查磁盘缓存，命中则直接返回
    - 速率限制：平均 1.5 次/秒
    - 失败自动重试 3 次（指数退避）
    """
    app_key    = os.environ.get("QCC_APP_KEY", "")
    secret_key = os.environ.get("QCC_SECRET_KEY", "")

    if not app_key or not secret_key:
        logger.debug("QCC_APP_KEY / QCC_SECRET_KEY 未配置，跳过 API 调用")
        return None

    # 缓存键（不含 timespan，因为 timespan 每次不同）
    import hashlib as _h
    ck = _h.md5(f"qcc|{endpoint}|{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
    if ck in _CACHE:
        return _CACHE[ck]

    if not _LIMITER.acquire():
        logger.warning("企查查速率限制等待超时")
        return None

    params["key"] = app_key  # AppKey 放 URL 参数

    for attempt in range(3):
        token, timespan = _make_token(app_key, secret_key)
        try:
            resp = requests.get(
                f"{QCC_BASE}/{endpoint}",
                params=params,
                headers={
                    "Token":   token,
                    "Timespan": timespan,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            # 企查查成功标志：Status == "200"
            if str(data.get("Status")) == "200":
                result = data.get("Data") or data.get("Result")
                _CACHE.set(ck, result, expire=CACHE_TTL[ttl_key])
                return result
            else:
                logger.warning(f"企查查业务错误: Status={data.get('Status')} Msg={data.get('Message')}")
                return None

        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"企查查请求失败（第{attempt+1}次）: {e}，{wait}s 后重试")
            time.sleep(wait)

    return None


# ══════════════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════════════

def search_companies(keyword: str, page: int = 1, page_size: int = 5) -> dict:
    """
    企业模糊搜索。
    endpoint: FuzzySearch/GetList
    支持：企业名、产品名、经营范围关键词、人名、地址等

    返回 {"total": int, "items": [...]}
    每页最多 5 条（企查查限制）。
    """
    raw = _qcc_get(
        "FuzzySearch/GetList",
        {"searchKey": keyword, "pageIndex": page, "pageSize": page_size},
        ttl_key="search",
    )
    if raw is None:
        return {"total": 0, "items": []}

    # raw 可能是 list 或 dict
    if isinstance(raw, list):
        return {"total": len(raw), "items": raw}

    items = raw.get("Items") or raw.get("Result") or raw if isinstance(raw, list) else []
    total = raw.get("Paging", {}).get("TotalRecords", len(items)) if isinstance(raw, dict) else len(items)
    return {"total": int(total), "items": items}


def get_company_detail(company_name: str) -> dict | None:
    """
    企业工商基本信息详情。
    endpoint: ECIV4/GetBasicDetailsByName
    返回完整工商信息，含经营范围（Scope 字段）。

    调试：设环境变量 QCC_DEBUG=1 时，会把原始返回的字段名打印到控制台，
          方便核对实际字段名是否与代码映射一致。
    """
    result = _qcc_get(
        "ECIV4/GetBasicDetailsByName",
        {"keyword": company_name},
        ttl_key="detail",
    )
    if os.environ.get("QCC_DEBUG") == "1" and result:
        import sys
        if isinstance(result, dict):
            print(f"[QCC_DEBUG] {company_name} 详情字段: {list(result.keys())}", file=sys.stderr)
            # 打印关键字段的值，确认是否有数据
            for k in ("Name","OperName","RegistCapi","StartDate","Status","Scope","Province","Address","CreditCode","No"):
                if k in result:
                    v = str(result[k])[:40]
                    print(f"           {k} = {v}", file=sys.stderr)
    return result


# ══════════════════════════════════════════════════════════════════════
# 企业角色分析（与 tyc_client.py 逻辑完全一致，可复用）
# ══════════════════════════════════════════════════════════════════════

_MFG_WORDS    = ["制造","生产","研发","加工","生产加工","制备","合成","提炼","铸造","配制","聚合","炼制"]
_TRADE_WORDS  = ["销售","经销","批发","零售","贸易","供应"]
_IMPORT_WORDS = ["进出口","进口","出口","报关"]
# 纯中介信号：以代理/居间/咨询为主业，无生产
_AGENT_WORDS  = ["代理","居间","中介","信息咨询","商务咨询","经纪","代购"]

def classify_role(scope: str) -> str:
    """
    从经营范围判断企业角色，用于排序优先级：
      manufacturer 工厂（有生产/制造）         —— 最优先
      both         工厂兼贸易                   —— 次优先
      importer     进口商（有进出口，无生产）   —— 再次
      trader       经销商（纯销售，无生产）     —— 较后
      agent        纯中介（代理/居间为主）      —— 排除/最后
      unknown      信息不足
    """
    if not scope:
        return "unknown"
    has_mfg    = any(w in scope for w in _MFG_WORDS)
    has_trade  = any(w in scope for w in _TRADE_WORDS)
    has_import = any(w in scope for w in _IMPORT_WORDS)
    has_agent  = any(w in scope for w in _AGENT_WORDS)

    if has_mfg and (has_trade or has_import):
        return "both"
    if has_mfg:
        return "manufacturer"
    # 无生产：看是不是纯中介
    if has_agent and not has_trade and not has_import:
        return "agent"
    if has_import:
        return "importer"
    if has_trade:
        return "trader"
    if has_agent:
        return "agent"
    return "unknown"


def is_relevant(scope: str, query: str) -> bool:
    """经营范围是否真正涉及查询产品（宽松判断）。"""
    if not scope or not query:
        return False
    return query in scope


def is_configured() -> bool:
    """检查企查查 Key 是否已配置。"""
    return bool(os.environ.get("QCC_APP_KEY") and os.environ.get("QCC_SECRET_KEY"))


def get_cache_stats() -> dict:
    return {
        "count":   len(_CACHE),
        "size_mb": round(_CACHE.volume() / 1024 / 1024, 1),
        "dir":     str(CACHE_DIR),
    }


def clear_cache():
    _CACHE.clear()
