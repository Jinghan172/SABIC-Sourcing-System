"""
本地数据搜索模块 v3.0
读取 MCP 采集的 local_cache JSON，评分逻辑统一调用 utils/scorer.py（三维评分）。
- 不修改 JSON 原始数据（企查查导入数据只读）；province/city 缺失时从 address 推导（仅展示用）
- 移除相关性评分与专利加分（v3.0）
"""
import json
import re
from pathlib import Path

from utils.scorer import score_supplier, DEFAULT_WEIGHTS, has_hazmat_license
from utils import sites

CACHE_DIR = Path(__file__).parent.parent / "data" / "local_cache"

# 城市→省份映射，用于从地址推导省份/城市（不写回 JSON）
_CITY_PROV = {
    "聊城":"山东","东营":"山东","淄博":"山东","潍坊":"山东","青岛":"山东",
    "烟台":"山东","济南":"山东","威海":"山东","临沂":"山东","济宁":"山东",
    "泰安":"山东","菏泽":"山东","寿光":"山东","德州":"山东","枣庄":"山东",
    "扬州":"江苏","南通":"江苏","无锡":"江苏","苏州":"江苏","常州":"江苏",
    "徐州":"江苏","南京":"江苏","连云港":"江苏","泰州":"江苏","盐城":"江苏",
    "镇江":"江苏","宿迁":"江苏","淮安":"江苏","泰兴":"江苏","如皋":"江苏",
    "张家港":"江苏","常熟":"江苏","仪征":"江苏","海门":"江苏","靖江":"江苏",
    "宁波":"浙江","绍兴":"浙江","台州":"浙江","温州":"浙江","嘉兴":"浙江",
    "湖州":"浙江","杭州":"浙江","金华":"浙江","丽水":"浙江","衢州":"浙江",
    "慈溪":"浙江","余姚":"浙江","诸暨":"浙江","桐乡":"浙江","海宁":"浙江",
    "惠州":"广东","东莞":"广东","佛山":"广东","深圳":"广东","广州":"广东",
    "珠海":"广东","中山":"广东","汕头":"广东","湛江":"广东","茂名":"广东",
    "郑州":"河南","洛阳":"河南","新乡":"河南","许昌":"河南","安阳":"河南",
    "武汉":"湖北","宜昌":"湖北","荆门":"湖北","黄石":"湖北","鄂州":"湖北",
    "成都":"四川","泸州":"四川","乐山":"四川","自贡":"四川","绵阳":"四川",
    "西安":"陕西","咸阳":"陕西","榆林":"陕西",
    "太原":"山西","大同":"山西","临汾":"山西","晋中":"山西","运城":"山西",
    "合肥":"安徽","芜湖":"安徽","马鞍山":"安徽","铜陵":"安徽","蚌埠":"安徽",
    "南昌":"江西","九江":"江西","吉安":"江西","景德镇":"江西",
    "长沙":"湖南","株洲":"湖南","岳阳":"湖南","衡阳":"湖南",
    "福州":"福建","厦门":"福建","泉州":"福建","漳州":"福建",
    "昆明":"云南","曲靖":"云南","贵阳":"贵州","遵义":"贵州",
    "南宁":"广西","柳州":"广西","桂林":"广西",
    "沈阳":"辽宁","大连":"辽宁","抚顺":"辽宁","鞍山":"辽宁","盘锦":"辽宁",
    "长春":"吉林","四平":"吉林",
    "哈尔滨":"黑龙江","大庆":"黑龙江","齐齐哈尔":"黑龙江",
    "石家庄":"河北","唐山":"河北","沧州":"河北","保定":"河北","邯郸":"河北",
    "兰州":"甘肃","白银":"甘肃",
    "乌鲁木齐":"新疆","克拉玛依":"新疆","库尔勒":"新疆",
    "呼和浩特":"内蒙古","包头":"内蒙古","鄂尔多斯":"内蒙古",
}

_MUNICIPALITIES = {"上海", "北京", "天津", "重庆"}


def _classify_role(scope: str) -> str:
    if not scope: return "unknown"
    # "合成" 不算制造信号：常出现在"合成树脂销售"等纯贸易经营范围中
    mfg   = any(w in scope for w in ["制造","生产","研发","加工"])
    trade = any(w in scope for w in ["销售","经销","批发","贸易"])
    imp   = any(w in scope for w in ["进出口","进口"])
    # "咨询" 太通用（很多公司经营范围里捎带"技术咨询/管理咨询"），不作为中介信号
    agent = any(w in scope for w in ["代理","居间","经纪"])
    if mfg and (trade or imp): return "both"
    if mfg: return "manufacturer"
    if agent and not trade: return "agent"
    if imp: return "importer"
    if trade: return "trader"
    return "unknown"


def _province_from_address(address: str, name: str = "") -> str:
    provinces = ["上海","江苏","浙江","安徽","山东","广东","福建","湖北","河南",
                 "河北","四川","辽宁","吉林","黑龙江","湖南","江西","重庆",
                 "北京","天津","陕西","甘肃","云南","贵州","广西","新疆","内蒙古",
                 "山西","海南","宁夏","青海","西藏"]
    text = (address or "") + (name or "")
    for p in provinces:
        if p in text:
            return p
    for city, prov in _CITY_PROV.items():
        if city in text:
            return prov
    return ""


def _city_from_address(address: str, province: str = "") -> str:
    """从地址推导城市（仅展示用，不写回 JSON）。直辖市直接返回市名。"""
    if province in _MUNICIPALITIES:
        return province
    text = address or ""
    # 已知城市名直接命中（含县级市如张家港、寿光）
    for city in _CITY_PROV:
        if city in text:
            return city
    # 通用 "XX市" 模式（去掉省份前缀后取第一个市）
    m = re.search(r"(?:省|区)?([一-龥]{2,4})市", text)
    if m:
        c = m.group(1)
        # 去掉可能粘连的省名（如"山东省淄博" → 淄博）
        for p in ("黑龙江","内蒙古","山东","江苏","浙江","安徽","广东","河南",
                  "湖北","湖南","河北","福建","江西","四川","陕西","山西",
                  "辽宁","吉林","云南","贵州","广西","甘肃","新疆","海南"):
            if c.startswith(p):
                c = c[len(p):]
        return c
    return ""


def search_local(query: str, filters: dict = None, weights: dict = None,
                 top_n: int = 20, site_key: str = sites.DEFAULT_SITE) -> dict:
    """
    从本地 JSON 缓存搜索供应商，返回评分排序结果（三维评分，调 scorer.py）。
    geography 按 site_key 所选厂区独立计算。格式与 open_search() 完全兼容。
    """
    filters = filters or {}
    weights = weights or dict(DEFAULT_WEIGHTS)

    cache_file = _find_cache(query)
    if not cache_file:
        return {"total": 0, "displayed": 0, "suppliers": [],
                "source": "local", "cache_missing": True}

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    cn   = data.get("cn", query)
    raw  = data.get("companies", [])

    suppliers = []
    for c in raw:
        name     = c.get("name", "")
        scope    = c.get("scope", "")
        address  = c.get("address", "")
        province = (c.get("province") or
                    _province_from_address(address, name))
        city     = c.get("city") or _city_from_address(address, province)
        role     = _classify_role(scope)

        # 行业相关性过滤：负面词只对企业名称生效，避免经营范围里捎带的无关业务
        # （如纸箱厂常含"印刷"、木托盘厂常含"家具"）误伤真正相关的企业
        neg = ["宠物","餐饮","服装","教育","房地产","旅游","婚庆",
               "地毯","光电","纺织","印刷","家具","家纺","建筑装饰","物业","酒店"]
        pos = ["化工","新材料","树脂","助剂","颜料","稳定剂","炭黑","纤维"]
        if any(k in name for k in neg) and not any(k in (name+scope) for k in pos):
            continue

        # 企业类型过滤
        ctype = filters.get("company_type", "factory_first")
        if ctype == "manufacturer" and role not in ("manufacturer","both"):
            continue
        if ctype == "factory_first" and role == "agent":
            continue

        # 省份过滤
        if filters.get("provinces") and province not in filters["provinces"]:
            continue

        base = {
            "id":           f"LOCAL-{name[:8]}",
            "name":         name,
            "shortName":    name[:8],
            "creditCode":   c.get("credit_code",""),
            "legalPerson":  c.get("legal_person",""),
            "province":     province,
            "city":         city,
            "address":      address,
            "established":  _extract_year(c.get("established","")),
            "reg_status":   c.get("status","存续"),
            "registered_capital_wan": _parse_capital(c.get("reg_capital","")),
            "industry":     c.get("industry",""),
            "_business_scope": scope,
            "_role":        role,
            "licenses":     {"hazardous_chemicals": has_hazmat_license(scope)},
            "chemical_park": any(k in (address + " " + scope) for k in
                                 ["化工园", "化工区", "化工园区", "化学工业园"]),
            "logistics":    {"distance_km_to_site": sites.distance_to_site(province, site_key)},
            "_tier":        sites.province_tier(province, site_key),
            "_source":      "local_cache",
            "products":     [],
            "main_categories": [cn],
        }
        suppliers.append(score_supplier(base, weights=weights, site_key=site_key))

    # 综合评分降序（同分时工厂优先）
    role_rank = {"manufacturer":0,"both":1,"importer":2,"trader":3,"unknown":4,"agent":5}
    suppliers.sort(key=lambda x: (-x["score"], role_rank.get(x["_role"],4)))

    return {
        "total":     len(suppliers),
        "displayed": len(suppliers[:top_n]),
        "suppliers": suppliers[:top_n],
        "source":    "local_cache",
        "cache_file": cache_file.name,
        "collected_at": data.get("collected_at",""),
    }


def _find_cache(query: str) -> Path | None:
    if not CACHE_DIR.exists():
        return None
    q = (query or "").strip()
    if not q:
        return None
    # 精确匹配文件名
    for candidate in [q, q.replace("/","_"), q.replace(" ","_")]:
        f = CACHE_DIR / f"{candidate}.json"
        if f.exists(): return f
    # 模糊：在所有文件的 cn/en 字段里找
    for f in CACHE_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("cn") == q or d.get("en","").lower() == q.lower():
                return f
        except Exception:
            pass
    return None

def _extract_year(s: str) -> int:
    if not s: return 0
    m = re.search(r"(\d{4})", str(s))
    return int(m.group(1)) if m else 0

def _parse_capital(s: str) -> float:
    if not s: return 0.0
    m = re.search(r"([\d.]+)\s*([万亿]?)", str(s))
    if not m: return 0.0
    v = float(m.group(1))
    return v * 10000 if m.group(2) == "亿" else v

def cache_status() -> dict:
    """返回本地缓存状态"""
    if not CACHE_DIR.exists():
        return {"exists": False, "count": 0, "files": []}
    files = list(CACHE_DIR.glob("*.json"))
    return {
        "exists": True,
        "count": len(files),
        "files": [f.stem for f in files],
        "dir": str(CACHE_DIR),
    }


_CATEGORY_CACHE: list | None = None

def list_cache_categories(refresh: bool = False) -> list[dict]:
    """
    扫描 local_cache 目录，返回与 JSON 文件一一对应的品类清单：
      [{"en": "PC", "cn": "聚碳酸酯", "file": "PC.json", "count": 7}, ...]
    供搜索联想使用——每个联想项严格对应一个缓存文件。
    """
    global _CATEGORY_CACHE
    if _CATEGORY_CACHE is not None and not refresh:
        return _CATEGORY_CACHE
    cats = []
    if CACHE_DIR.exists():
        for f in sorted(CACHE_DIR.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                cats.append({
                    "en":    d.get("en", f.stem),
                    "cn":    d.get("cn", f.stem),
                    "file":  f.name,
                    "count": len(d.get("companies", [])),
                })
            except Exception:
                continue
    _CATEGORY_CACHE = cats
    return cats
