"""
企查查 MCP 本地数据采集  v5
用法：
  python collect_local.py --debug 中国石化      # 看原始返回格式
  python collect_local.py --list-tools          # 查看工具清单
  python collect_local.py --category 双酚A      # 采集单个品类
  python collect_local.py                        # 全部 50 个品类
"""
import argparse, json, re, time
from pathlib import Path
import requests

TOKEN = "MdJnJbc7hDkUqN2tSJNIiZOGm3ESuGUzN1PgYCwRAylX3sb8"
HEADERS = {"Authorization": f"Bearer {TOKEN}",
           "Content-Type": "application/json", "Accept": "application/json"}
SERVERS = {
    "company":   "https://agent.qcc.com/mcp/company/stream",
    "ipr":       "https://agent.qcc.com/mcp/ipr/stream",
    "operation": "https://agent.qcc.com/mcp/operation/stream",
    "risk":      "https://agent.qcc.com/mcp/risk/stream",
}
OUTPUT_DIR = Path(__file__).parent / "sabic-py" / "data" / "local_cache"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_req_id = 0
_inited: set = set()
_tcache: dict = {}

# ── 核心 HTTP 调用 ────────────────────────────────────────────────────────
def mcp_post(url, method, params={}, timeout=30):
    global _req_id
    _req_id += 1
    payload = {"jsonrpc":"2.0","method":method,"params":params,"id":_req_id}
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=timeout)
        if r.status_code != 200:
            print(f"    HTTP {r.status_code}")
            return None
        body = r.content.decode("utf-8", errors="replace")
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                s = line[5:].strip()
                if not s or s == "[DONE]": continue
                try:
                    msg = json.loads(s)
                    if "result" in msg or "error" in msg:
                        return msg
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"    error: {e}")
    return None

def ensure_init(url):
    if url in _inited: return True
    r = mcp_post(url, "initialize", {
        "protocolVersion":"2024-11-05","capabilities":{},
        "clientInfo":{"name":"sabic-collector","version":"5.0"}})
    if r and "result" in r:
        _inited.add(url)
        mcp_post(url, "notifications/initialized", {})
        return True
    return False

def get_tools(server):
    url = SERVERS.get(server,"")
    if not url or not ensure_init(url): return []
    if url not in _tcache:
        r = mcp_post(url, "tools/list", {})
        _tcache[url] = (r or {}).get("result",{}).get("tools",[]) if r else []
    return _tcache[url]

def call_tool(server, tool_name, args, timeout=30):
    url = SERVERS.get(server,"")
    if not url or not ensure_init(url): return None
    r = mcp_post(url,"tools/call",{"name":tool_name,"arguments":args},timeout)
    if not r or "result" not in r: return None
    for c in (r["result"].get("content") or []):
        if c.get("type") == "text": return c["text"]
    res = r["result"]
    return json.dumps(res, ensure_ascii=False) if isinstance(res, dict) else None

def find_tool(server, *kws):
    for t in get_tools(server):
        for kw in kws:
            if kw.lower() in t["name"].lower(): return t["name"]
    return None

# ── 调试：看原始响应 ─────────────────────────────────────────────────────
def cmd_debug(keyword):
    print(f"\n=== get_company_by_query searchKey={keyword!r} ===")
    ensure_init(SERVERS["company"])
    resp = mcp_post(SERVERS["company"],"tools/call",
                    {"name":"get_company_by_query","arguments":{"searchKey":keyword}},30)
    if not resp:
        print("✗ 无响应"); return
    for c in (resp.get("result") or {}).get("content") or []:
        if c.get("type") == "text":
            text = c["text"]
            print(f"长度: {len(text)} 字节\n前1500字:\n{text[:1500]}")
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "企业信息" in data:
                    companies = data["企业信息"]
                    print(f"\n企业信息列表: {len(companies)} 家")
                    if companies:
                        first_name = companies[0].get("企业名称","")
                        print(f"\n=== 对第一家 '{first_name}' 调用 get_company_profile ===")
                        r2 = mcp_post(SERVERS["company"],"tools/call",
                                      {"name":"get_company_profile","arguments":{"searchKey":first_name}},30)
                        if r2:
                            for c2 in (r2.get("result") or {}).get("content") or []:
                                if c2.get("type") == "text":
                                    t2 = c2["text"]
                                    print(f"长度: {len(t2)} 字节\n前2000字:\n{t2[:2000]}")
                                    try:
                                        d2 = json.loads(t2)
                                        print(f"\n顶层键: {list(d2.keys()) if isinstance(d2,dict) else type(d2)}")
                                        if isinstance(d2, dict):
                                            for k,v in list(d2.items())[:15]:
                                                print(f"  {k}: {str(v)[:120]}")
                                    except Exception: pass
            except Exception: pass

# ── 业务函数 ─────────────────────────────────────────────────────────────
NEGATIVE = ["宠物","餐饮","食品","服装","教育","房地产","旅游","婚庆","娱乐","汽车","装修",
            "地毯","光电","纺织","印刷","家具","家纺","建筑装饰","物业","酒店"]
POSITIVE = ["化工","新材料","树脂","塑料","助剂","颜料","稳定剂","炭黑","纤维","橡胶","改性","聚合"]

# 品类必含词：企业 名称+经营范围 必须命中其中之一才保留。
# 用于材质/形态有严格限定的品类，防止泛化关键词混入近似品（如塑料托盘混进木托盘）
CATEGORY_REQUIRE = {
    "Pallet": ["木托盘", "木制托盘", "木质托盘"],
}

def meets_require(en, c):
    req = CATEGORY_REQUIRE.get(en)
    if not req:
        return True
    t = c.get("name", "") + c.get("scope", "")
    return any(k in t for k in req)

def is_relevant(name, scope=""):
    t = name + scope
    if any(k in t for k in POSITIVE): return True
    if any(k in name for k in NEGATIVE): return False
    return True

def recheck_relevance(c, cn, en=""):
    """补全 scope 后二次核验：scope 已知但与正面关键词及品类名都不沾边时剔除。
    负面词只对企业名称生效（如纸箱厂经营范围常含"印刷"，不应被当作无关业务剔除）"""
    name, scope = c.get("name",""), c.get("scope","")
    if any(k in name for k in NEGATIVE): return False
    if not meets_require(en, c): return False
    if not scope:
        return True  # scope 仍未知，保留（避免误删）
    t = name + scope
    if any(k in t for k in POSITIVE): return True
    if cn and cn in t: return True
    if en and en.lower() in t.lower(): return True
    return False

def search_companies(keyword):
    tool = find_tool("company","query","search","fuzzy","find","list")
    if not tool and get_tools("company"):
        tool = get_tools("company")[0]["name"]
    if not tool: return []
    raw = call_tool("company", tool, {"searchKey": keyword})
    return _parse_list(raw, keyword) if raw else []

def get_detail(name):
    raw = call_tool("company", "get_company_registration_info", {"searchKey": name})
    d = _parse_registration(raw) if raw else {}
    if d.get("scope"):
        return d
    tool = find_tool("company","profile","detail")
    raw2 = call_tool("company", tool, {"searchKey": name}) if tool else None
    d2 = _parse_single(raw2) if raw2 else {}
    merged = {**d2, **{k:v for k,v in d.items() if v}}
    return merged

def get_patents(name):
    tool = find_tool("ipr","patent","invention","utility")
    if not tool: return []
    raw = call_tool("ipr", tool, {"searchKey": name})
    return _parse_patents(raw) if raw else []

# ── 数据解析 ─────────────────────────────────────────────────────────────
def _g(d, *keys):
    for k in keys:
        for key in (k, k.lower(), k[0].lower()+k[1:] if len(k)>1 else k):
            v = d.get(key)
            if v: return str(v)
    return ""

PROVINCES = ["上海","江苏","浙江","安徽","山东","广东","湖北","河南","福建","河北",
             "四川","辽宁","天津","北京","重庆","湖南","江西","陕西","云南","贵州",
             "广西","黑龙江","吉林","内蒙古","甘肃","新疆","山西","海南"]
CITY_PROV = {"寿光":"山东","东营":"山东","淄博":"山东","潍坊":"山东","青岛":"山东",
             "扬州":"江苏","南通":"江苏","无锡":"江苏","苏州":"江苏","常州":"江苏",
             "宁波":"浙江","绍兴":"浙江","台州":"浙江","温州":"浙江",
             "惠州":"广东","东莞":"广东","佛山":"广东","深圳":"广东","广州":"广东",
             "郑州":"河南","洛阳":"河南","武汉":"湖北","成都":"四川","西安":"陕西"}

def _province_from_text(text: str) -> str:
    for p in PROVINCES:
        if p in text:
            return p
    for city, prov in CITY_PROV.items():
        if city in text:
            return prov
    return ""

def _normalize_registration(item: dict) -> dict:
    """处理 get_company_registration_info 返回的结构化字段"""
    name = item.get("企业名称","")
    if not name or len(name) < 3: return None
    status_raw = item.get("登记状态","")
    status = "存续" if any(k in status_raw for k in ["存续","在业","在营","开业"]) else status_raw
    region = item.get("所属地区","")
    address = item.get("注册地址","") or region
    return {
        "name":         name,
        "credit_code":  item.get("统一社会信用代码",""),
        "legal_person": str(item.get("法定代表人","")),
        "reg_capital":  item.get("注册资本",""),
        "established":  item.get("成立日期",""),
        "status":       status,
        "scope":        item.get("经营范围",""),
        "province":     _province_from_text(region) or _province_from_text(address),
        "city":         "",
        "address":      address,
        "industry":     item.get("国标行业",""),
        "_qcc_industry":item.get("国标行业",""),
    }

def _parse_registration(raw):
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            if "企业名称" in data:
                return _normalize_registration(data) or {}
            info = data.get("企业信息")
            if isinstance(info, dict):
                return _normalize_registration(info) or {}
            if isinstance(info, list) and info:
                return _normalize_registration(info[0]) or {}
    except Exception: pass
    return {}

def _extract_from_jianjie(jianjie: str, base: dict) -> dict:
    """从 get_company_profile 返回的简介文本里提取结构化字段"""
    import re
    j = jianjie

    def find(pattern, default=""):
        m = re.search(pattern, j)
        return m.group(1).strip() if m else default

    capital   = find(r"注册资本为([^\s，。,]+)")
    address   = find(r"注册地址(?:位于|为|：)(.+?)(?:，|。|$)")
    industry  = find(r"所属行业为(.+?)(?:，|。|经营)")
    # 经营范围：从"经营范围包含："到"企业当前"或末尾
    scope_m   = re.search(r"经营范围(?:包含：|为：?|：)(.+?)(?:企业当前|当前经营状态|$)", j, re.DOTALL)
    scope     = scope_m.group(1).strip().rstrip("*。，") if scope_m else ""
    est_m     = re.search(r"成立于(\d{4}-\d{2}-\d{2})", j)
    established = est_m.group(1) if est_m else base.get("established","")
    legal_m   = re.search(r"法定代表人为(\S+?)，", j)
    legal     = legal_m.group(1) if legal_m else base.get("legal_person","")
    cap_m_alt = re.search(r"信用代码为(\w+)", j)
    credit    = cap_m_alt.group(1) if cap_m_alt else base.get("credit_code","")

    province = _province_from_text(address) or _province_from_text(j[:80])

    return {
        **base,
        "reg_capital":  capital  or base.get("reg_capital",""),
        "established":  established,
        "legal_person": legal    or base.get("legal_person",""),
        "credit_code":  credit   or base.get("credit_code",""),
        "scope":        scope    or base.get("scope",""),
        "province":     province or base.get("province",""),
        "address":      address  or base.get("address",""),
        "industry":     base.get("_qcc_industry","") or industry or base.get("industry",""),
    }


def _normalize_cn(item):
    """处理企查查 MCP 中文字段名"""
    name = item.get("企业名称","")
    if not name or len(name) < 3: return None
    legal = item.get("法定代表人名称","")
    if isinstance(legal, list): legal = "、".join(legal)
    base = {
        "name":         name,
        "credit_code":  item.get("统一社会信用代码",""),
        "legal_person": str(legal),
        "reg_capital":  item.get("注册资本",""),
        "established":  item.get("成立日期",""),
        "status":       item.get("状态",""),
        "scope":        item.get("经营范围",""),
        "province":     item.get("省份",""),
        "city":         item.get("城市",""),
        "address":      item.get("注册地址",""),
        "industry":     item.get("行业","") or item.get("企查查行业",""),
        "_qcc_industry": item.get("企查查行业",""),
    }
    # 如果有简介文本，用它补充所有字段
    jianjie = item.get("简介","")
    if jianjie and len(jianjie) > 20:
        base = _extract_from_jianjie(jianjie, base)
    return base

def _normalize(item):
    name = _g(item,"Name","name","企业名称","companyName","entName","company_name")
    if not name or len(name) < 3: return None
    return {"name":name,
            "credit_code": _g(item,"CreditCode","creditCode","No","no"),
            "legal_person":_g(item,"OperName","legalPerson","法定代表人"),
            "reg_capital": _g(item,"RegistCapi","regCapital","registeredCapital","注册资本"),
            "established": _g(item,"StartDate","startDate","establishDate","成立日期"),
            "status":      _g(item,"Status","status","经营状态"),
            "scope":       _g(item,"Scope","scope","businessScope","经营范围"),
            "province":    _g(item,"Province","province","省份"),
            "city":        _g(item,"City","city"),
            "address":     _g(item,"Address","address","注册地址"),
            "industry":    _g(item,"Industry","industry","行业")}

def _parse_list(raw, keyword):
    companies = []
    # 接口明确返回"未匹配"时直接判空，防止下方正则兜底把提示 JSON 误解析成公司名
    if raw and "未匹配" in raw[:100]:
        return []
    try:
        data = json.loads(raw)
        # 企查查 MCP 实际返回格式：{"企业信息": [{...}, ...]}
        if isinstance(data, dict) and "企业信息" in data:
            for item in data["企业信息"]:
                if isinstance(item, dict):
                    c = _normalize_cn(item)
                    if c and is_relevant(c["name"], c.get("scope","")):
                        companies.append(c)
            return companies
        # 兼容其他路径
        for path in (["data","list"],["data","items"],["result","list"],
                     ["data"],["result"],["list"],["items"],[]):
            cur = data
            for key in path:
                cur = cur.get(key) if isinstance(cur,dict) else None
                if cur is None: break
            if isinstance(cur, list):
                for item in cur:
                    if isinstance(item,dict):
                        c = _normalize(item) or _normalize_cn(item)
                        if c and is_relevant(c["name"],c.get("scope","")): companies.append(c)
                if companies: return companies
        if isinstance(data, dict):
            c = _normalize(data) or _normalize_cn(data)
            if c and is_relevant(c["name"],c.get("scope","")): return [c]
    except Exception: pass
    for line in raw.split("\n"):
        m = re.search(r"([^\s\d\[\]「」【】]{3,20}(?:有限公司|股份|集团))", line)
        if m:
            n = m.group(1).strip()
            if is_relevant(n): companies.append({"name":n})
    return companies

def _parse_single(raw):
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            # get_company_profile 格式：{企业名称, 简介, 企查查行业}
            if "简介" in data:
                c = _normalize_cn(data); return c or {}
            if "企业信息" in data and data["企业信息"]:
                c = _normalize_cn(data["企业信息"][0]); return c or {}
            if "企业名称" in data:
                c = _normalize_cn(data); return c or {}
        node = data.get("data") or data.get("result") or data if isinstance(data,dict) else data
        if isinstance(node,dict):
            c = _normalize(node) or _normalize_cn(node); return c or {}
    except Exception: pass
    return {}

def _parse_patents(raw):
    try:
        data = json.loads(raw)
        items = data.get("data") or data.get("result") or (data if isinstance(data,list) else [])
        if isinstance(items,dict): items = items.get("list") or items.get("items") or []
        return [{"title":str(i.get("title") or i.get("patentName") or ""),
                 "type": str(i.get("type") or i.get("patentType") or "")}
                for i in items if isinstance(i,dict)]
    except Exception: return []

# ── 品类表 ────────────────────────────────────────────────────────────────
CATEGORIES = {
    "原材料": [
        ("ABS","ABS树脂",["ABS树脂生产","ABS工程塑料制造","丙烯腈丁二烯苯乙烯生产"]),
        ("PP","聚丙烯",["聚丙烯生产","聚丙烯树脂制造","PP树脂销售"]),
        ("PC","聚碳酸酯",["聚碳酸酯生产","聚碳酸酯树脂制造","PC树脂生产"]),
        ("PET","PET聚酯",["聚酯切片生产","涤纶切片生产","聚对苯二甲酸乙二醇酯生产"]),
        ("PBT","PBT聚酯",["聚对苯二甲酸丁二醇酯生产","PBT树脂生产","PBT聚酯制造"]),
        ("PMMA","聚甲基丙烯酸甲酯",["聚甲基丙烯酸甲酯生产","有机玻璃制造","亚克力板生产"]),
        ("PPO","聚苯醚",["聚苯醚生产","改性聚苯醚制造","PPO树脂生产"]),
        ("PS","聚苯乙烯",["聚苯乙烯生产","PS树脂制造","高抗冲聚苯乙烯生产"]),
        ("BPA","双酚A",["双酚A生产","双酚A制造","双酚生产"]),
        ("BDO","丁二醇",["1,4-丁二醇生产","丁二醇生产","BDO制造"]),
        ("AcN","丙烯腈",["丙烯腈生产","丙烯腈制造"]),
        ("MA","马来酸酐",["马来酸酐生产","顺酐制造","顺丁烯二酸酐生产"]),
        ("PA","苯酐",["苯酐生产","邻苯二甲酸酐生产","苯酐制造"]),
        ("IPA","间苯二甲酸",["间苯二甲酸生产","间苯二甲酸制造"]),
        ("Hexane","正己烷",["正己烷生产","己烷生产","溶剂油生产"]),
        ("Castor","蓖麻油",["蓖麻油生产","蓖麻油制造","蓖麻加工"]),
        ("AlPow","铝粉",["铝粉生产","铝银浆制造","球形铝粉生产"]),
        ("BDDMA","BDDMA单体",["1,4-丁二醇二甲基丙烯酸酯生产","BDDMA制造"]),
        ("Hex1","1-己烯",["1-己烯生产","己烯共聚单体制造"]),
        ("Isobutane","异丁烷",["异丁烷生产","液化异丁烷制造"]),
        ("Isohexane","异己烷",["异己烷生产","异己烷制造"]),
        ("nHeptane","正庚烷",["正庚烷生产","正庚烷制造"]),
        ("PBR","聚丁二烯橡胶",["聚丁二烯橡胶生产","顺丁橡胶制造","BR橡胶生产"]),
        ("PCCD","PCCD聚酯",["PCCD生产","聚环己烷二甲醇碳酸酯"]),
        ("PCT","PCT/PCTG聚酯",["PCTG生产","PCT聚酯制造","改性聚酯生产"]),
        ("SAN","SAN树脂",["SAN树脂生产","苯乙烯丙烯腈共聚物制造"]),
        ("THPE","三羟基苯乙酮",["三羟基苯乙酮生产","THPE制造","苯乙酮衍生物"]),
        ("3MPA","3-巯基丙酸",["3-巯基丙酸生产","有机硫化物制造"]),
        ("PA6","尼龙6",["聚酰胺6生产","PA6切片制造","尼龙6工程塑料"]),
        ("PA66","尼龙66",["聚酰胺66生产","PA66工程塑料","尼龙66制造"]),
        ("PA12","尼龙12",["聚酰胺12生产","PA12制造"]),
        ("TPU","热塑性聚氨酯",["TPU弹性体生产","热塑性聚氨酯制造"]),
        ("POM","聚甲醛",["聚甲醛生产","POM工程塑料制造"]),
        ("PPS","聚苯硫醚",["聚苯硫醚生产","PPS工程塑料制造"]),
        ("PEEK","聚醚醚酮",["PEEK生产","聚醚醚酮制造"]),
        ("LCP","液晶聚合物",["液晶聚合物生产","LCP树脂制造"]),
        ("TPE","热塑性弹性体",["TPE弹性体生产","热塑性橡胶制造"]),
        ("EVA","乙烯醋酸乙烯共聚物",["EVA生产","乙烯醋酸乙烯共聚物制造"]),
        ("HDPE","高密度聚乙烯",["HDPE生产","高密度聚乙烯制造"]),
        ("LLDPE","线性低密度聚乙烯",["LLDPE生产","线性低密度聚乙烯制造"]),
        ("PVC","聚氯乙烯",["PVC生产","聚氯乙烯制造"]),
        ("PVB","聚乙烯醇缩丁醛",["PVB生产","聚乙烯醇缩丁醛制造"]),
        ("PSU","聚砜",["聚砜生产","PSU工程塑料制造"]),
        ("Styrene","苯乙烯",["苯乙烯生产","苯乙烯单体制造"]),
        ("Caprolactam","己内酰胺",["己内酰胺生产","尼龙6原料制造"]),
        ("Adipic Acid","己二酸",["己二酸生产","尼龙66原料制造"]),
        ("MDI","二苯甲烷二异氰酸酯",["MDI生产","异氰酸酯制造"]),
        ("TDI","甲苯二异氰酸酯",["TDI生产","甲苯二异氰酸酯制造"]),
        ("ECH","环氧氯丙烷",["环氧氯丙烷生产","ECH制造"]),
        ("DMC","碳酸二甲酯",["碳酸二甲酯生产","DMC制造"]),
        ("EG","乙二醇",["乙二醇生产","MEG制造"]),
        ("Phenol","苯酚",["苯酚生产","纯苯酚制造"]),
        ("Acetone","丙酮",["丙酮生产","丙酮制造"]),
        ("Acrylic Acid","丙烯酸",["丙烯酸生产","丙烯酸制造"]),
        ("Butanol","正丁醇",["正丁醇生产","丁醇制造"]),
        ("EtOAc","乙酸乙酯",["乙酸乙酯生产","醋酸乙酯制造"]),
    ],
    "阻燃剂": [
        ("BrFR","溴系阻燃剂",["溴系阻燃剂生产","溴代阻燃剂制造","阻燃剂生产"]),
        ("TBBPA","四溴双酚A",["四溴双酚A生产","TBBPA制造","溴化阻燃剂生产"]),
        ("RDP","RDP阻燃剂",["磷酸酯阻燃剂生产","间苯二酚双磷酸酯生产","磷系阻燃剂制造"]),
        ("TPP","磷酸三苯酯",["磷酸三苯酯生产","磷酸酯制造","TPP生产"]),
        ("ATO","三氧化二锑",["三氧化二锑生产","氧化锑生产","锑化合物制造"]),
        ("MPP","聚磷酸蜜胺",["聚磷酸蜜胺生产","蜜胺磷酸盐制造","无卤阻燃剂生产"]),
        ("AlPhos","次膦酸铝",["次膦酸铝生产","有机磷阻燃剂制造","磷铝化合物生产"]),
        ("BDP","双酚A双磷酸酯",["BDP阻燃剂","双酚A双磷酸酯"]),
        ("ATO-MB","ATO母粒",["三氧化二锑母粒生产","ATO阻燃母粒制造"]),
        ("BrAcr","溴化丙烯酸酯",["溴化丙烯酸酯生产","溴系丙烯酸酯阻燃剂"]),
        ("BrEpoxy","溴化环氧树脂",["溴化环氧树脂生产","溴化环氧阻燃剂制造"]),
        ("Bromine","溴素",["溴素生产","液溴制造","溴化工生产"]),
        ("BrPS","溴化聚苯乙烯",["溴化聚苯乙烯生产","BrPS阻燃剂制造"]),
        ("TBBPA-DGE","TBBPA二缩水甘油醚",["TBBPA二缩水甘油醚生产","溴化环氧活性阻燃剂"]),
        ("TBBPA-MPE","TBBPA甲基苯基醚",["TBBPA甲基苯基醚生产","溴化阻燃剂制造"]),
        ("BrCO","溴化碳酸酯低聚物",["溴化碳酸酯低聚物生产","溴化PC低聚物"]),
        ("BPA-DP","双酚A磷酸二苯酯",["双酚A双磷酸酯生产","BDP阻燃剂制造"]),
        ("IntP","膨胀型磷系阻燃剂",["膨胀型阻燃剂生产","IFR阻燃体系制造"]),
        ("KSS","全氟丁基磺酸钾",["磺酸钾盐阻燃剂生产","KSS制造"]),
        ("NATS","芳香族磺酸钠",["芳香族磺酸钠生产","磺酸盐阻燃剂制造"]),
        ("Phosphazene","苯氧基磷腈",["环状磷腈阻燃剂生产","苯氧基磷腈制造"]),
        ("Resorcinol","间苯二酚",["间苯二酚生产","间苯二酚制造"]),
        ("Rimar","全氟乙基磺酸钾",["全氟乙基磺酸钾生产","Rimar盐制造"]),
        ("SolDP","Sol-DP磷酸酯",["Sol-DP磷酸酯生产","脂肪族磷酸二苯酯"]),
        ("SpecTalc","特种滑石粉",["特种滑石粉生产","阻燃级滑石粉制造"]),
        ("STB","STB磺酸盐",["芳香族磺酸盐生产","STB阻燃剂制造"]),
        ("TAP","磷酸三烯丙酯",["磷酸三烯丙酯生产","TAP制造"]),
        ("ATH","氢氧化铝",["氢氧化铝阻燃剂生产","ATH制造"]),
        ("MDH","氢氧化镁",["氢氧化镁阻燃剂生产","MDH制造"]),
        ("Zinc Borate","硼酸锌",["硼酸锌生产","阻燃硼酸锌制造"]),
        ("Red Phosphorus","红磷",["红磷阻燃剂生产","包覆红磷制造"]),
        ("Melamine","三聚氰胺",["三聚氰胺生产","蜜胺制造"]),
        ("DOPO","DOPO磷阻燃剂",["DOPO生产","有机磷阻燃剂制造"]),
        ("Anti-drip","防滴落剂",["防滴落剂生产","抗熔滴剂制造"]),
    ],
    "改性剂": [
        ("SEBS","SEBS弹性体",["SEBS生产","热塑性弹性体制造","氢化苯乙烯嵌段共聚物生产"]),
        ("SBS","SBS弹性体",["SBS生产","苯乙烯丁二烯嵌段共聚物生产","热塑弹性体制造"]),
        ("POE","POE弹性体",["POE生产","乙烯辛烯共聚物生产","聚烯烃弹性体制造"]),
        ("MBS","MBS树脂",["MBS树脂生产","抗冲改性剂生产","冲击改性剂制造"]),
        ("PEMA","马来酸酐接枝PE",["马来酸酐接枝生产","相容剂生产","接枝改性聚烯烃制造"]),
        ("Silicon-IM","有机硅抗冲剂",["有机硅母粒生产","硅酮母粒制造"]),
        ("AIM","丙烯酸酯抗冲改性剂",["ACR抗冲改性剂生产","丙烯酸酯抗冲剂制造","丙烯酸酯核壳结构改性剂"]),
        ("TSAN","PTFE包覆SAN",["PTFE包覆SAN生产","TSAN防滴落剂制造"]),
        ("SEP","SEP嵌段共聚物",["SEP生产","苯乙烯乙烯丙烯嵌段共聚物"]),
        ("PP-MA","马来酸酐接枝PP",["马来酸酐接枝聚丙烯生产","PP-g-MA制造"]),
        ("Compatibilizer","相容剂",["相容剂生产","增容剂制造"]),
    ],
    "氟塑料": [
        ("ETFE","ETFE氟塑料",["ETFE生产","乙烯四氟乙烯共聚物制造"]),
        ("PTFE-D","PTFE分散液",["PTFE乳液生产","聚四氟乙烯分散液制造"]),
        ("PTFE-P","PTFE粉",["聚四氟乙烯粉生产","PTFE模压粉制造"]),
        ("PVDF","聚偏氟乙烯",["PVDF生产","聚偏氟乙烯制造","偏氟乙烯树脂"]),
    ],
    "稳定剂": [
        ("AO","抗氧剂",["抗氧剂生产","受阻酚抗氧剂制造","酚类抗氧剂生产"]),
        ("HALS","受阻胺光稳定剂",["受阻胺光稳定剂生产","光稳定剂制造","HALS生产"]),
        ("UV","紫外线吸收剂",["紫外线吸收剂生产","苯并三唑制造","UV吸收剂生产"]),
        ("HeatStab","热稳定剂",["热稳定剂生产","钙锌稳定剂制造","有机锡稳定剂生产"]),
        ("MetSt","金属硬脂酸盐",["硬脂酸锌生产","硬脂酸钙制造","金属皂生产"]),
        ("PETS","季戊四醇硬脂酸酯",["季戊四醇硬脂酸酯生产","硬脂酸酯生产","塑料助剂生产"]),
        ("Nucleating Agent","成核剂",["成核剂生产","塑料成核剂制造"]),
        ("Plasticizer","增塑剂",["增塑剂生产","DINP制造","DOP生产"]),
        ("Montan-Wax","蒙旦蜡",["蒙旦蜡生产","褐煤蜡制造"]),
        ("Anti-static","抗静电剂",["抗静电剂生产","抗静电剂制造"]),
        ("GMS90","甘油单硬脂酸酯",["甘油单硬脂酸酯生产","GMS制造","单甘酯生产"]),
        ("Slip","滑爽剂",["滑爽剂生产","油酸酰胺制造","爽滑剂生产"]),
        ("Preblends","复合稳定剂预混料",["复合稳定剂生产","预混稳定剂制造","一体化助剂包"]),
        ("Mold Release","脱模剂",["脱模剂生产","塑料脱模剂制造"]),
        ("Silicone Oil","硅油",["硅油生产","聚二甲基硅氧烷制造"]),
    ],
    "色料增强": [
        ("CB","炭黑",["炭黑生产","导电炭黑制造","橡胶用炭黑生产"]),
        ("TiO2","钛白粉",["钛白粉生产","二氧化钛制造","氯化法钛白生产"]),
        ("GF","玻璃纤维",["玻璃纤维生产","玻纤制造","无碱玻璃纤维生产"]),
        ("CF","碳纤维",["碳纤维生产","碳素纤维制造","聚丙烯腈基碳纤维生产"]),
        ("Talc","滑石粉",["滑石粉生产","超细滑石粉制造","滑石制造"]),
        ("CMB","色母粒",["色母粒生产","功能母粒制造","塑料色母制造"]),
        ("OrgPig","有机颜料",["有机颜料生产","颜料制造","偶氮颜料生产"]),
        ("InoPig","无机颜料",["无机颜料生产","氧化铁颜料制造","铁红生产"]),
        ("CNT","碳纳米管",["碳纳米管生产","多壁碳纳米管制造"]),
        ("ConductCB","导电炭黑",["导电炭黑生产","导电碳黑制造"]),
        ("Dyes","染料",["分散染料生产","工业染料制造","活性染料生产"]),
        ("RCF","再生碳纤维",["再生碳纤维生产","回收碳纤维制造"]),
        ("Siloxane","有机硅烷",["硅烷偶联剂生产","有机硅烷制造"]),
        ("WAX","聚乙烯蜡",["聚乙烯蜡生产","PE蜡制造","氧化聚乙烯蜡"]),
        ("ZnS","硫化锌",["硫化锌生产","硫化锌制造"]),
        ("CBMB","炭黑母粒",["炭黑母粒生产","黑色母粒制造","炭黑色母制造"]),
        ("CaCO3","重质碳酸钙",["重质碳酸钙生产","碳酸钙填料制造"]),
        ("Mica","云母粉",["云母粉生产","绢云母制造"]),
        ("BaSO4","硫酸钡",["硫酸钡生产","超细硫酸钡制造"]),
        ("Wollastonite","硅灰石",["硅灰石生产","针状硅灰石制造"]),
        ("Kaolin","高岭土",["煅烧高岭土生产","高岭土填料制造"]),
        ("Silane","硅烷偶联剂",["硅烷偶联剂生产","有机硅烷制造"]),
    ],
    "包装": [
        ("Pallet","木托盘",["木托盘生产","木质托盘制造","木制托盘制造"]),
        ("FIBC","集装袋",["集装袋生产","吨袋制造","柔性集装袋生产"]),
        ("Liner","散装内衬袋",["包装袋生产","塑料薄膜袋生产","编织袋生产"]),
        ("Box","瓦楞纸箱",["瓦楞纸箱生产","纸箱制造","瓦楞纸板箱制造"]),
        ("FlexPack","软包装",["工业软包装生产","塑料编织袋制造","复合软包装生产"]),
    ],
}

def collect_one(en, cn, keywords, refresh=False):
    out = OUTPUT_DIR / f"{en}.json"
    if out.exists() and not refresh:
        d = json.loads(out.read_text(encoding="utf-8"))
        print(f"  {en:10s} 已有({d.get('count',0)}家)，跳过"); return
    print(f"  ── {en} · {cn}")
    seen: dict = {}
    for kw in keywords:
        results = search_companies(kw)
        new = [c for c in results if c.get("name") not in seen]
        for c in new: seen[c["name"]] = c
        print(f"    「{kw}」→ {len(results)}家（新{len(new)}，累计{len(seen)}）")
        time.sleep(0.5)
        if len(seen) >= 30: break
    companies = list(seen.values())
    for c in companies:
        if not c.get("scope"):
            d = get_detail(c["name"])
            c.update({k:v for k,v in d.items() if v and not c.get(k)})
            time.sleep(0.3)
    companies = [c for c in companies if meets_require(en, c)]
    for c in companies[:10]:
        pts = get_patents(c["name"])
        c["patent_count"] = len(pts)
        c["has_chem_patent"] = any(any(kw in p.get("title","") for kw in [cn,en,"化工","合成"]) for p in pts)
        time.sleep(0.2)
    out.write_text(json.dumps({"en":en,"cn":cn,
        "collected_at":time.strftime("%Y-%m-%d %H:%M"),
        "count":len(companies),"companies":companies},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    ✓ {len(companies)} 家 → {out.name}")

def cmd_fill_missing(only=None, limit=None):
    """补全已采集数据中 scope/reg_capital/province 缺失的企业，并二次核验相关性"""
    print("\n补全缺失字段\n" + "="*60)
    if not ensure_init(SERVERS["company"]): print("✗ 连接失败"); return
    flat = [(en, cn) for items in CATEGORIES.values() for en, cn, _ in items]
    n_calls = 0
    for en, cn in flat:
        if only and cn != only and en.lower() != only.lower(): continue
        out = OUTPUT_DIR / f"{en}.json"
        if not out.exists(): continue
        d = json.loads(out.read_text(encoding="utf-8"))
        companies = d.get("companies", [])
        incomplete = [c for c in companies if not c.get("scope") or not c.get("reg_capital") or not c.get("province")]
        if not incomplete: continue
        print(f"  ── {en} · {cn}：{len(incomplete)} 家待补全")
        changed = False
        for c in incomplete:
            if limit and n_calls >= limit:
                print(f"    达到调用上限 {limit}，停止"); break
            det = get_detail(c["name"])
            n_calls += 1
            if det:
                for k, v in det.items():
                    if v and not c.get(k):
                        c[k] = v
                changed = True
            time.sleep(0.3)
        if limit and n_calls >= limit:
            if changed:
                before = len(companies)
                companies = [c for c in companies if recheck_relevance(c, cn, en)]
                d["companies"], d["count"] = companies, len(companies)
                out.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"    ✓ 已保存（{before}→{len(companies)}家）")
            print(f"    达到调用上限 {limit}，整体停止")
            break
        if changed:
            before = len(companies)
            companies = [c for c in companies if recheck_relevance(c, cn, en)]
            d["companies"], d["count"] = companies, len(companies)
            out.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"    ✓ 已保存（{before}→{len(companies)}家）")
    print(f"\n完成，共调用 get_company_registration_info {n_calls} 次")

def cmd_list_tools():
    print("\n企查查 MCP 工具清单\n" + "="*60)
    for name in SERVERS:
        tools = get_tools(name)
        if not tools: print(f"\n{name}: ✗"); continue
        print(f"\n{name}: {len(tools)} 个工具")
        for t in tools:
            props = list((t.get("inputSchema") or {}).get("properties",{}).keys())
            print(f"  {t['name']:40s} {props}")

def cmd_collect(only=None, refresh=False):
    print("\n企查查 MCP 本地数据采集  v5\n" + "="*60)
    print("连接测试...", end="", flush=True)
    if not ensure_init(SERVERS["company"]): print("\n✗ 失败"); return
    tools = get_tools("company")
    print(f" ✓  company 工具: {[t['name'] for t in tools[:4]]}...")
    done = 0
    for group, items in CATEGORIES.items():
        print(f"\n[{group}]")
        for en, cn, keywords in items:
            if only and cn != only and en.lower() != only.lower(): continue
            collect_one(en, cn, keywords, refresh=refresh)
            done += 1
    print(f"\n完成 {done} 个品类 → {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", help="只采集指定品类")
    ap.add_argument("--refresh",  action="store_true")
    ap.add_argument("--list-tools", action="store_true")
    ap.add_argument("--debug", metavar="KEYWORD", help="调试：打印原始响应")
    ap.add_argument("--fill-missing", action="store_true", help="补全 scope/资本/省份缺失的企业")
    ap.add_argument("--limit", type=int, help="--fill-missing 时最多调用次数")
    args = ap.parse_args()
    if args.list_tools:
        cmd_list_tools()
    elif args.debug:
        cmd_debug(args.debug)
    elif args.fill_missing:
        cmd_fill_missing(only=args.category, limit=args.limit)
    else:
        cmd_collect(only=args.category, refresh=args.refresh)