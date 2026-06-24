"""
开放产品搜索引擎（企查查版）
突破 chemicals.json 的 15 种化学品限制，支持任意产品关键词
"""
from __future__ import annotations

import re
import time
import json
import logging
from pathlib import Path

from utils.qcc_client import (
    search_companies, get_company_detail,
    classify_role, is_relevant, is_configured,
)
from utils.scorer import score_supplier, DEFAULT_WEIGHTS
from utils.sabic_search import get_search_plan, get_qcc_filters

logger = logging.getLogger(__name__)

_DATA = Path(__file__).parent.parent / "data"
with open(_DATA / "regions.json", encoding="utf-8") as f:
    _REGIONS = json.load(f)

# 省份距离表
_DIST = {
    name: info.get("distance_km", 600)
    for name, info in _REGIONS.get("provinceCoords", {}).items()
    if isinstance(info, dict)
}

# 企查查省份字段已是全称（如"上海"），直接用
_PROVINCE_FULL = {
    "京":"北京","津":"天津","沪":"上海","渝":"重庆",
    "冀":"河北","豫":"河南","云":"云南","辽":"辽宁",
    "黑":"黑龙江","湘":"湖南","皖":"安徽","鲁":"山东",
    "新":"新疆","苏":"江苏","浙":"浙江","赣":"江西",
    "鄂":"湖北","桂":"广西","甘":"甘肃","晋":"山西",
    "蒙":"内蒙古","陕":"陕西","吉":"吉林","闽":"福建",
    "贵":"贵州","粤":"广东","川":"四川","青":"青海",
    "琼":"海南","宁":"宁夏","藏":"西藏",
}


# 主要工业城市 → 省份映射（企查查 Province 字段有时返回城市名）
_CITY_TO_PROVINCE = {
    "无锡":"江苏","苏州":"江苏","南京":"江苏","常州":"江苏","南通":"江苏",
    "扬州":"江苏","泰州":"江苏","盐城":"江苏","徐州":"江苏","镇江":"江苏","连云港":"江苏","江阴":"江苏","宜兴":"江苏","张家港":"江苏","昆山":"江苏","常熟":"江苏","太仓":"江苏",
    "宁波":"浙江","杭州":"浙江","温州":"浙江","绍兴":"浙江","嘉兴":"浙江",
    "台州":"浙江","金华":"浙江","湖州":"浙江","衢州":"浙江","舟山":"浙江","义乌":"浙江","余姚":"浙江","慈溪":"浙江","上虞":"浙江",
    "合肥":"安徽","芜湖":"安徽","蚌埠":"安徽","马鞍山":"安徽","安庆":"安徽",
    "青岛":"山东","济南":"山东","烟台":"山东","潍坊":"山东","淄博":"山东","东营":"山东","威海":"山东",
    "广州":"广东","深圳":"广东","东莞":"广东","佛山":"广东","珠海":"广东","中山":"广东","惠州":"广东",
    "武汉":"湖北","宜昌":"湖北","襄阳":"湖北","黄石":"湖北",
    "郑州":"河南","洛阳":"河南","南阳":"河南","新乡":"河南",
    "成都":"四川","绵阳":"四川","德阳":"四川","宜宾":"四川",
    "厦门":"福建","福州":"福建","泉州":"福建","漳州":"福建",
    "大连":"辽宁","沈阳":"辽宁","盘锦":"辽宁",
    "西安":"陕西","咸阳":"陕西","榆林":"陕西",
    "长沙":"湖南","岳阳":"湖南","株洲":"湖南",
    "天津":"天津","北京":"北京","上海":"上海","重庆":"重庆",
    "石家庄":"河北","唐山":"河北","沧州":"河北","邯郸":"河北",
    "太原":"山西","大同":"山西","南昌":"江西","九江":"江西",
    "昆明":"云南","贵阳":"贵州","南宁":"广西","柳州":"广西",
    "兰州":"甘肃","乌鲁木齐":"新疆","呼和浩特":"内蒙古","包头":"内蒙古",
    "海口":"海南","银川":"宁夏","西宁":"青海","拉萨":"西藏","哈尔滨":"黑龙江","长春":"吉林",
}
_VALID_PROVINCES = {
    "北京","天津","上海","重庆","河北","山西","内蒙古","辽宁","吉林","黑龙江",
    "江苏","浙江","安徽","福建","江西","山东","河南","湖北","湖南","广东",
    "广西","海南","四川","贵州","云南","西藏","陕西","甘肃","青海","宁夏","新疆",
}

def _norm_province(raw: str) -> str:
    """把企查查返回的省份/城市字段统一成坐标表里的省份全称。"""
    if not raw:
        return ""
    raw = str(raw).strip()
    # 1. 去掉行政后缀
    cleaned = (raw.replace("省","").replace("市","").replace("自治区","")
                  .replace("特别行政区","").replace("壮族","").replace("回族","")
                  .replace("维吾尔","").strip())
    # 2. 直接是有效省份
    if cleaned in _VALID_PROVINCES:
        return cleaned
    # 3. 是城市 → 映射到省份
    if cleaned in _CITY_TO_PROVINCE:
        return _CITY_TO_PROVINCE[cleaned]
    # 4. 前两字匹配省份（如"内蒙古XX"）
    for p in _VALID_PROVINCES:
        if cleaned.startswith(p) or raw.startswith(p):
            return p
    # 5. 单字简称（沪苏浙）
    if len(raw) >= 1:
        return _PROVINCE_FULL.get(raw[:1], cleaned)
    return cleaned


def _province_from_text(*texts: str) -> str:
    """
    从地址、企业名等文本里提取省份。中国地址必以省/直辖市开头，
    企业名常以城市开头（如"义乌市第二石油化"），用这两条强力兜底。
    返回标准省份全称，提取失败返回 ""。
    """
    for text in texts:
        if not text:
            continue
        t = str(text)
        # 5a. 直接含省份全称
        for p in _VALID_PROVINCES:
            if p in t[:12]:        # 只看前 12 字，避免误匹配经营范围里的省名
                return p
        # 5b. 含城市名 → 映射省份
        for city, prov in _CITY_TO_PROVINCE.items():
            if city in t[:8]:
                return prov
        # 5c. 单字简称在开头
        if t and t[0] in _PROVINCE_FULL:
            return _PROVINCE_FULL[t[0]]
    return ""


# ── 行业相关性判断（解决宠物公司/简称误匹配）─────────────────────────
# 明显非化工行业的企业名关键词 → 直接排除
_NEGATIVE_NAME_KW = [
    "宠物","餐饮","食品","服装","服饰","教育","培训","房地产","地产","物业",
    "旅游","酒店","餐厅","美容","美发","婚庆","传媒","广告","影视","文化",
    "娱乐","游戏","健身","母婴","玩具","珠宝","眼镜","汽车销售","汽车维修",
    "驾校","花卉","园林绿化","农业","养殖","种植","水产","茶叶","烟酒",
    "建材销售","装饰装修","家具","家居","超市","便利店","百货","电子商务",
]
# 化工/材料行业正向词 → 出现则一定保留
_CHEM_POSITIVE_KW = [
    "化工","化学","新材料","树脂","塑料","橡胶","聚","高分子","助剂","添加剂",
    "颜料","染料","涂料","试剂","材料科技","精细化","石化","化纤","纤维",
    "母粒","改性","阻燃","稳定剂","抗氧","硬脂","填料","炭黑","钛白",
]

def _industry_relevant(name: str, scope: str, query: str, terms: set) -> bool:
    """
    判断企业是否与化工采购相关，用于过滤宠物公司这类误匹配。
    返回 True=保留，False=过滤。
    """
    text = f"{name} {scope}"
    # 1. 命中搜索词或同义词 → 一定相关
    if any(t in text for t in terms if t):
        return True
    # 2. 名称/范围含化工正向词 → 相关
    if any(k in text for k in _CHEM_POSITIVE_KW):
        return True
    # 3. 名称含明显非化工行业词 且 不含任何化工线索 → 过滤
    if any(k in name for k in _NEGATIVE_NAME_KW):
        return False
    # 4. 有经营范围但完全不含化工线索 → 过滤
    if scope and len(scope) > 15:
        return False
    # 5. 信息不足（无范围）→ 保留（避免误杀，但会被低分排后）
    return True


def resolve_province(detail: dict) -> str:
    """
    综合提取企业省份：Province 字段 → 注册地址 → 企业名称，逐级兜底。
    这是修复"省份识别失败导致地理分崩溃/地图不显示"的核心。
    """
    # 1. 优先用 Province 字段
    prov = _norm_province(detail.get("Province", ""))
    if prov in _VALID_PROVINCES or prov in ("上海","北京","天津","重庆"):
        return prov
    # 2. 从地址提取
    prov = _province_from_text(detail.get("Address", ""),
                               detail.get("OperName", ""),
                               detail.get("Name", ""))
    return prov


def _parse_capital(s: str) -> float:
    if not s:
        return 0.0
    m = re.search(r"([\d.]+)\s*([万亿]?)", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    return val * 10000 if m.group(2) == "亿" else val


def _parse_year(date_str: str) -> int:
    """'2010-01-01' -> 2010"""
    if not date_str:
        return 2010
    try:
        return int(str(date_str)[:4])
    except Exception:
        return 2010


# ══════════════════════════════════════════════════════════════════════
# 企查查字段 → 系统 Supplier 格式
# ══════════════════════════════════════════════════════════════════════

def qcc_to_supplier(detail: dict, query: str = "") -> dict:
    """
    企查查 ECIV4/GetBasicDetailsByName 或 FuzzySearch/GetList 返回字段
    映射成系统 Supplier 对象，可直接传入 score_supplier()。

    企查查关键字段：
      Name          企业全称
      OperName      法定代表人
      Status        经营状态（存续/注销等）
      Province      所在省份
      Address       注册地址
      StartDate     成立日期  "2010-01-01"
      RegistCapi    注册资本  "1000万人民币"
      No / CreditCode  统一社会信用代码
      Scope         经营范围（详情接口）
      BusinessScope 经营范围（搜索结果字段，部分版本）
    """
    # 多字段名兜底取值（企查查不同接口/版本字段名有差异）
    def _g(*keys, default=""):
        for k in keys:
            v = detail.get(k)
            if v not in (None, "", []):
                return v
        return default

    scope    = _g("Scope", "BusinessScope", "OperScope", "经营范围")
    province = resolve_province(detail)
    role     = classify_role(scope)
    products = _extract_products(scope, query)

    _capital = _parse_capital(_g("RegistCapi", "RegCapital", "RegistCapital", "注册资本"))
    _year    = _parse_year(_g("StartDate", "EstablishDate", "EstiblishTime", "FromTime", "成立日期"))

    return {
        "id":          f"QCC-{_g('KeyNo','No','CreditCode',default=str(time.time()))}",
        "name":        _g("Name", "企业名称"),
        "shortName":   _g("Name", "企业名称")[:8],
        "creditCode":  _g("CreditCode", "No", "统一社会信用代码"),
        "legalPerson": _g("OperName", "LegalPerson", "FRDB", "法定代表人"),
        "industry":    _g("Industry", "IndustryV3", "IndustryName", "行业", default="—"),
        "province":    province,
        "city":        _g("City", "城市"),
        "address":     _g("Address", "RegLocation", "注册地址"),
        "established": _year,
        "employees":   None,   # 企查查基础接口不返回
        "reg_status":  _g("Status", "经营状态", default="存续"),

        # 供应能力：企查查不提供的字段一律 None（UI 显示"企查查未提供"，绝不编造）
        "products":            products,
        "main_categories":     [query] if query else [],
        "annual_capacity_ton": None,    # 企查查无此数据
        "min_order_ton":       None,    # 企查查无此数据
        "price_range_per_ton": None,    # 企查查无此数据
        "chemical_park":       ("化工园" in (_g("Address","RegLocation") or "")
                                or "化工区" in (_g("Address","RegLocation") or "")),

        "registered_capital_wan": _capital,

        # 资质：只标注「从经营范围可推断」的，不能确认的一律 None（不瞎猜）
        "licenses": {
            # 经营范围明确含危化品字样 → True；否则 None（未知，不是 False）
            "hazardous_chemicals": True if ("危险化学品" in scope or "危化品" in scope) else None,
            "safety_production":   None,   # 需 255 资质接口核验
            "vat_general":         None,   # 企查查基础接口不返回，不再默认 True
            "gb_certified":        None,   # 需 255 资质接口核验
            "iso_certs":           [],     # 由 255 资质接口填充
        },

        "logistics": {
            "distance_km_to_shanghai": _DIST.get(province, 600),
            "own_fleet":        False,
            "hazmat_transport": False,
        },

        # 元数据
        "_source":         "qichacha",
        "_role":           role,
        "_business_scope": scope,
        "_fetched_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _extract_products(scope: str, query: str) -> list[str]:
    """从经营范围简单提取产品列表"""
    if not scope:
        return [query] if query else []
    parts = re.split(r"[；;，,。\n]", scope)
    result = []
    for p in parts:
        p = p.strip()
        if 2 <= len(p) <= 20 and not any(p.startswith(w) for w in ["销售","经营","从事","提供"]):
            result.append(p)
    out = result[:6]
    if query and query not in out:
        out.insert(0, query)
    return out


# ══════════════════════════════════════════════════════════════════════
# 开放搜索主入口
# ══════════════════════════════════════════════════════════════════════

def open_search(
    query: str,
    filters: dict | None = None,
    weights: dict | None = None,
    page: int = 1,
    include_traders: bool = False,
) -> dict:
    """
    开放产品搜索：输入任意产品关键词，返回评分排序的供应商列表。

    返回：
    {
        "total":     int,    企查查总命中数
        "displayed": int,    本次实际返回数量
        "suppliers": list,   已评分排序的供应商
        "source":    str,    "qichacha"
    }
    """
    if not query:
        return {"total": 0, "displayed": 0, "suppliers": [], "source": "demo"}

    f = filters or {}
    w = weights or DEFAULT_WEIGHTS

    # ── SABIC 专项搜索：所有关键词全部执行 + 多页累积 ─────────────────
    # 目标：累计收集至少 MAX_COLLECT 家候选企业（去重后）
    # CAS 号输入自动转换为中文名（企查查按中文名搜索效果更好）
    from pathlib import Path as _P
    import json as _j
    _cas_path = _P(__file__).parent.parent / "data" / "cas_db.json"
    try:
        _cas_db = _j.loads(_cas_path.read_text(encoding="utf-8"))
        if query in _cas_db:
            cn, en, abbr = _cas_db[query]
            query = cn           # 用中文名代替 CAS 号进入后续搜索
        else:
            # 也支持简称输入（如 BPA → 双酚A）
            for _cas, (cn, en, abbr) in _cas_db.items():
                if query.upper() == abbr.upper() or query.lower() == en.lower():
                    query = cn
                    break
    except Exception:
        pass

    MAX_COLLECT = 30          # 目标候选数（尽量多）
    MAX_PAGES   = 4           # 每个关键词最多翻页数（避免过度消耗额度）
    PAGE_SIZE   = 5           # 企查查单次最多返回 5 条

    # 关键词清单：专项策略词 + 原始词 + 同义词 + 常见变体（尽量多收集候选）
    from utils.scorer import _SYNONYMS as _SYN_ALL
    keywords = list(get_search_plan(query))
    # 加原始词本身
    if query not in keywords:
        keywords.append(query)
    # 加同义词（如 马来酸酐→顺酐、双酚A→BPA）
    for syn in _SYN_ALL.get(query, []):
        if syn and syn not in keywords and len(syn) >= 2 and not syn.isascii():
            keywords.append(syn)        # 只加中文同义词（英文简称搜企业名无意义）
    # 加常见制造业变体（裸词 + 化工后缀），扩大召回
    for suffix in ("生产", "制造", "化工", "新材料", "科技"):
        kw = f"{query}{suffix}"
        if kw not in keywords:
            keywords.append(kw)
    seen_names: set[str] = set()
    all_items: list[dict] = []
    grand_total = 0

    def _collect(kw):
        """搜一个关键词，多页累积去重到 all_items"""
        nonlocal grand_total
        for pg in range(1, MAX_PAGES + 1):
            if len(all_items) >= MAX_COLLECT:
                return
            raw = search_companies(kw, page=pg, page_size=PAGE_SIZE)
            items = raw.get("items", [])
            if not items:
                return
            grand_total = max(grand_total, raw.get("total", 0))
            for item in items:
                name = item.get("Name") or item.get("name", "")
                if name and name not in seen_names:
                    seen_names.add(name)
                    all_items.append(item)
            if len(items) < PAGE_SIZE:
                return

    for kw in keywords:
        if len(all_items) >= MAX_COLLECT:
            break
        _collect(kw)

    # 候选仍偏少（<12家）→ 已在 keywords 里包含裸词和同义词，无需额外兜底

    # 注：不再自动套用 SABIC 策略的 min_capital（避免隐藏过滤），
    #     最低资本完全由用户在侧边栏控制。专项策略只用于优化搜索关键词。
    total      = grand_total
    candidates = all_items

    # ── 阶段一：便宜的预筛选（仅用搜索结果字段，不消耗详情额度）────────
    # 用 Status / Province / RegistCapi / StartDate 等搜索结果就有的字段
    from utils.scorer import _SYNONYMS
    import datetime as _dt
    _cur_year = _dt.datetime.now().year

    pre_filtered = []
    for c in candidates:
        # 经营状态（搜索结果含 Status）
        status = c.get("Status", "")
        if f.get("status_active", True) and status and status not in ("存续", "在业", ""):
            continue
        # 省份（搜索结果含 Province）
        if f.get("provinces"):
            prov = _norm_province(c.get("Province", ""))
            if prov not in f["provinces"]:
                continue
        # 最低注册资本（搜索结果含 RegistCapi）
        min_cap = f.get("min_capital_wan", 0) or f.get("min_capital", 0) or 0
        if min_cap > 0:
            cap = _parse_capital(c.get("RegistCapi", ""))
            if cap > 0 and cap < min_cap:   # cap=0 表示未知，不过滤
                continue
        pre_filtered.append(c)

    if not pre_filtered:
        return {"total": total, "displayed": 0, "suppliers": [], "source": "qichacha"}

    # ── 阶段二：拉详情拿到经营范围 Scope ──────────────────────────────
    suppliers = []
    syns = _SYNONYMS.get(query, [])
    ctype = f.get("company_type", "all")

    detail_ok   = 0   # 成功拿到详情（有经营范围）的家数
    detail_fail = 0   # 详情拉取失败（额度耗尽/异常）的家数

    # 相关性判断用的关键词集合：搜索词 + 同义词 + 单字成分（化学品名常见）
    relevance_terms = set([query] + syns)
    # 把搜索词里的关键 2-3 字片段也加入（如"季戊四醇"→"季戊"、"戊四醇"）
    if len(query) >= 4:
        relevance_terms.add(query[:3])
        relevance_terms.add(query[-3:])

    for c in pre_filtered[:MAX_COLLECT]:
        name   = c.get("Name", "")
        detail = get_company_detail(name) if name else None
        has_detail = bool(detail)
        if not detail:
            detail = c   # 详情拉取失败，降级用搜索字段
        sup = qcc_to_supplier(detail, query)
        scope = sup.get("_business_scope", "")

        if has_detail and scope:
            detail_ok += 1
        else:
            detail_fail += 1

        # ── 行业相关性过滤（解决宠物公司/简称误匹配）──────────────────
        # 综合企业名 + 经营范围 + 化工正/负向词判断，即使没拿到经营范围
        # 也能靠企业名过滤掉明显无关的（宠物/餐饮/服装等）
        if not _industry_relevant(name, scope, query, relevance_terms):
            continue

        # 企业类型过滤
        role = sup.get("_role", "unknown")
        if ctype == "manufacturer":
            # 只看工厂：仅保留 manufacturer / both
            if role not in ("manufacturer", "both"):
                continue
        elif ctype == "factory_first":
            # 工厂优先（默认）：排除纯中介，其余保留（后续按角色排序，工厂排前）
            if role == "agent":
                continue
        # ctype == "all"：全部保留（含中介）

        suppliers.append(sup)

    if not suppliers:
        return {"total": total, "displayed": 0, "suppliers": [],
                "source": "qichacha", "detail_fail": detail_fail, "detail_ok": detail_ok}

    # ── 阶段四：初步评分 ──────────────────────────────────────────────
    virtual_chem = {"id": query, "category": query, "primaryName": query}
    scored = []
    for s in suppliers:
        s["main_categories"] = list(set(s.get("main_categories", []) + [query]))
        scored.append(score_supplier(s, virtual_chem, w, query=query))

    # ── 阶段五：综合评分降序（同分时工厂 > 工厂兼贸易 > 进口商 > 经销商 > 中介）──
    # 主排序键为综合分，确保列表严格按评分从高到低；角色仅作同分时的次级排序。
    _role_rank = {"manufacturer":0, "both":1, "importer":2, "trader":3, "unknown":4, "agent":5}
    scored.sort(key=lambda x: (-x["score"],
                               _role_rank.get(x.get("_role","unknown"), 4)))

    # ── 阶段六：用 255 资质证书核验 Top 候选（验证真工厂+质量）──────────
    # 仅对排序后前 N 家调用（控制成本），用资质数据回填并微调分数
    from utils.qcc_client import get_qualifications, is_qual_enabled
    qual_checked = 0
    if is_qual_enabled():
        VERIFY_TOP_N = 12   # 只核验前12家，每家0.3元
        for s in scored[:VERIFY_TOP_N]:
            quals = get_qualifications(s.get("name", ""))
            if quals and quals.get("items"):
                items = quals["items"]
                names = " ".join(i.get("name","") for i in items)
                lic = s.setdefault("licenses", {})
                lic["iso_certs"] = [i.get("name","") for i in items
                                    if "ISO" in i.get("name","") or "体系认证" in i.get("name","")]
                lic["production_license"] = ("生产许可" in names)
                lic["safety_production"]  = ("安全生产许可" in names)
                if "危险化学品" in names:
                    lic["hazardous_chemicals"] = True
                s["_qualifications"] = items
                s["_qual_verified"] = True
                # 资质齐全的真工厂：重新评分（资质分会提升 compliance）
                rescored = score_supplier(s, virtual_chem, w, query=query)
                s["score"] = rescored["score"]
                s["dimensions"] = rescored["dimensions"]
                qual_checked += 1
            else:
                s["_qual_verified"] = False
        # 资质回填后重排（综合评分降序，同分工厂优先）
        scored.sort(key=lambda x: (-x["score"],
                                   _role_rank.get(x.get("_role","unknown"), 4)))

    return {
        "total":        total,
        "displayed":    len(scored),
        "suppliers":    scored,
        "source":       "qichacha",
        "detail_ok":    detail_ok,
        "detail_fail":  detail_fail,
        "qual_checked": qual_checked,
    }
