# -*- coding: utf-8 -*-
"""
统一首页导航 —— 把全站四大采购大类收敛成一致的『选大类 → 选品类 → 选厂区 → 决策报告』动线。

四大类（lane）：
  · core      核心原材料   —— 3 类外销沙特战略物料的专家评审（6 维，自带价格）
  · material  其他原材料   —— 生产性物料缓存品类（工商 3 维，按厂区独立地理评分）
  · mro       综合服务/MRO —— 15 类间接/服务采购（5 维专家 + 费率分析）
  · equipment 化工设备     —— 9 大设备（5 维专家 + 多源价格分析）

对外接口：
  LANES, HOME_CSS
  render_lane_selector()        首页四大类入口
  render_material_browse()      其他原材料：缓存品类分组浏览
  render_material_overview(q)   某原料品类的四大工厂总览地图 + 厂区选择
  unified_suggest(text)         跨四大类的搜索联想
  enter_item(item)              点击联想/卡片后的统一路由
"""
from __future__ import annotations
import json
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

from utils import sites
from utils.local_search import list_cache_categories, search_local
from utils.sabic_search import SABIC_SEARCH_STRATEGIES
from components.core_materials import load_core_materials
from components.services import load_services
from components.equipment import load_equipment

_BASE = Path(__file__).resolve().parent.parent / "data"
_CORE_HIDE_FILES = {"TiO2.json", "Pallet.json", "FlexPack.json"}   # 已升级为专家评审，从原料品类移除
_FONT = dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=14)

LANES = [
    {"key": "core", "cn": "核心原材料", "en": "Strategic Raw Materials", "icon": "⭐",
     "accent": "#0E8C3A",
     "tagline_en": "Saudi-export strategic materials · 6-dimension expert review + pricing",
     "tagline": "外销沙特战略物料 · 6 维专家评审 + 价格",
     "desc_en": "TiO₂ / FFS heavy-duty film / export pallets — in-depth due-diligence reports on the most critical materials.",
     "desc": "钛白粉 / FFS 重载膜 / 出口木托盘 —— 最核心物料的深度尽调报告。"},
    {"key": "material", "cn": "其他原材料", "en": "Production Materials", "icon": "🧪",
     "accent": "#2563eb",
     "tagline_en": "Production materials · 3-dimension business scoring · geography scored per plant",
     "tagline": "生产性物料 · 工商三维评分 · 按厂区独立计算地理分",
     "desc_en": "Resins / additives / pigments / flame retardants and more — pick a plant to recompute proximity scores.",
     "desc": "树脂 / 助剂 / 颜料 / 阻燃剂等缓存品类，选厂区即重算就近评分。"},
    {"key": "mro", "cn": "综合服务 / MRO", "en": "Services & MRO", "icon": "🏢",
     "accent": "#7c3aed",
     "tagline_en": "15 indirect / service categories · 5-dimension expert + rate analysis",
     "tagline": "15 类间接/服务采购 · 5 维专家 + 费率分析",
     "desc_en": "Local service procurement: staffing / events / IT / security / canteen / MRO / labs.",
     "desc": "人力 / 会务 / IT / 安保 / 食堂 / MRO / 实验室等属地服务采购。"},
    {"key": "equipment", "cn": "化工设备", "en": "Process Equipment", "icon": "🏭",
     "accent": "#dc2626",
     "tagline_en": "9 equipment classes · 5-dimension expert + multi-source price analysis",
     "tagline": "9 大设备 · 5 维专家 + 多源价格分析",
     "desc_en": "Heat exchangers / air coolers / columns / reactors / pumps / compressors / valves / cranes.",
     "desc": "换热器 / 空冷器 / 塔器 / 反应釜 / 泵 / 压缩机 / 阀门 / 起重机。"},
]
LANE_BY_KEY = {l["key"]: l for l in LANES}
_PLANT_COLOR = {"SH": "#0E8C3A", "NS": "#2563eb", "GL": "#f59e0b", "CQ": "#a855f7"}


# ── 各大类品类清单（统一结构，供卡片/联想/路由复用）────────────────────
def _core_items() -> list[dict]:
    out = []
    for m in load_core_materials().get("materials", []):
        out.append({"kind": "core", "key": m["key"], "cn": m.get("cn", m["key"]),
                    "en": m.get("en", m["key"]), "icon": m.get("icon", "⭐"),
                    "count": len(m.get("companies", []))})
    return out


def _material_items() -> list[dict]:
    out = []
    for c in list_cache_categories():
        if c["file"] in _CORE_HIDE_FILES:
            continue
        out.append({"kind": "material", "key": c["cn"], "query": c["cn"],
                    "cn": c["cn"], "en": c["en"], "icon": "🧪", "count": c["count"],
                    "file": c["file"],
                    "prio": SABIC_SEARCH_STRATEGIES.get(c["cn"], {}).get("priority", 2)})
    return out


def _mro_items() -> list[dict]:
    out = []
    for c in load_services().get("categories", []):
        n = sum(len(b.get("suppliers", [])) for b in c.get("bases", {}).values())
        out.append({"kind": "mro", "key": c["key"], "cn": c["cn"], "en": c.get("en", ""),
                    "icon": c.get("icon", "🏢"), "count": n})
    return out


def _equipment_items() -> list[dict]:
    out = []
    for c in load_equipment().get("categories", []):
        out.append({"kind": "equipment", "key": c["key"], "cn": c["cn"],
                    "en": c.get("en", ""), "icon": c.get("icon", "🏭"),
                    "count": c.get("ref_price_wan", "")})
    return out


def _all_items() -> list[dict]:
    return _core_items() + _material_items() + _mro_items() + _equipment_items()


def _equipment_supplier_total() -> int:
    """化工设备：各品类跨厂区去重后的供应商数合计。"""
    tot = 0
    for c in load_equipment().get("categories", []):
        names = set()
        for pv in c.get("plants", {}).values():
            for s in pv.get("suppliers", []):
                names.add(s.get("name") or id(s))
        tot += len(names)
    return tot


def global_stats() -> dict:
    """首页概览用的全站规模指标（未选品类时替代无意义的匹配数）。"""
    core, mat = _core_items(), _material_items()
    mro, eq = _mro_items(), _equipment_items()
    suppliers = (sum(c["count"] for c in core) + sum(c["count"] for c in mat)
                 + sum(c["count"] for c in mro) + _equipment_supplier_total())
    return {
        "lanes":      len(LANES),
        "categories": len(core) + len(mat) + len(mro) + len(eq),
        "suppliers":  suppliers,
        "plants":     len(sites.SITE_ORDER),
    }


# ── 统一路由：点击任意品类项后进入其报告 ────────────────────────────────
def enter_lane(lane_key: str) -> None:
    st.session_state.lane = lane_key
    st.session_state.query = ""
    st.rerun()


def enter_item(item: dict) -> None:
    """根据品类项 kind 跳转到对应报告，并清空其它路由键。"""
    for k in ("core_material", "service_cat", "equipment_cat"):
        st.session_state[k] = None
    st.session_state.query = ""
    st.session_state.selected_ids = []
    st.session_state.active_supplier = None
    kind = item["kind"]
    if kind == "core":
        st.session_state.lane = "core"
        st.session_state.core_material = item["key"]
    elif kind == "material":
        st.session_state.lane = "material"
        st.session_state.query = item.get("query") or item["cn"]
    elif kind == "mro":
        st.session_state.lane = "mro"
        st.session_state.service_cat = item["key"]
    elif kind == "equipment":
        st.session_state.lane = "equipment"
        st.session_state.equipment_cat = item["key"]
    st.rerun()


# ── 跨四大类搜索联想 ────────────────────────────────────────────────────
def unified_suggest(text: str, max_n: int = 10) -> list[dict]:
    q = (text or "").strip()
    if not q:
        return []
    ql = q.lower()
    ranked = []
    for it in _all_items():
        en_l, cn = (it.get("en") or "").lower(), it.get("cn") or ""
        rank = None
        if ql == en_l or q == cn:
            rank = 0
        elif en_l.startswith(ql) or cn.startswith(q):
            rank = 1
        elif (ql and ql in en_l) or (q and q in cn):
            rank = 2
        if rank is not None:
            # 同级内：核心/设备/服务优先于海量原料，原料里 P1 优先
            kind_w = {"core": 0, "equipment": 1, "mro": 1, "material": 2}.get(it["kind"], 3)
            prio = it.get("prio", 1)
            ranked.append((rank, kind_w, prio, it))
    ranked.sort(key=lambda x: x[:3])
    return [it for _, _, _, it in ranked[:max_n]]


# ═══════════════════════════════════════════════════════════════════════
# 首页：四大类入口
# ═══════════════════════════════════════════════════════════════════════
def render_lane_selector() -> None:
    counts = {"core": len(_core_items()), "material": len(_material_items()),
              "mro": len(_mro_items()), "equipment": len(_equipment_items())}
    st.markdown(
        "<div class='home-band'><div class='home-band-bar'></div><div>"
        "<div class='home-band-title'>Pick a procurement category first, then item & plant</div>"
        "<div class='home-band-title' style='font-size:16px;font-weight:700;color:#cfe0f0;margin-top:2px'>先选采购大类，再选品类与厂区</div>"
        "<div class='home-band-sub'>Unified flow across four categories: pick category → pick item → "
        "pick plant on the four-plant map → a detailed supplier comparison & decision report "
        "(services / equipment include price analysis).<br>"
        "四大类统一动线：选大类 → 选品类 → 四大工厂大地图选厂区 → "
        "一份细致的供应商对比与决策报告（服务 / 设备含价格分析）。</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, lane in enumerate(LANES):
        with cols[i % 2]:
            st.markdown(
                f"<div class='home-card' style='--accent:{lane['accent']}'>"
                f"<div class='home-card-top'><span class='home-ico'>{lane['icon']}</span>"
                f"<span class='home-tag'>{counts[lane['key']]} categories · 个品类</span></div>"
                f"<div class='home-name'>{lane['en']}</div>"
                f"<div class='home-name' style='font-size:18px;margin-top:0'>{lane['cn']}</div>"
                f"<div class='home-tagline'>{lane['tagline_en']}<br>{lane['tagline']}</div>"
                f"<div class='home-desc'>{lane['desc_en']}<br>{lane['desc']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button(f"Enter · 进入{lane['cn']} →", key=f"lane_{lane['key']}",
                         width="stretch", type="primary"):
                enter_lane(lane["key"])


# ═══════════════════════════════════════════════════════════════════════
# 其他原料：缓存品类分组浏览
# ═══════════════════════════════════════════════════════════════════════
def render_material_browse() -> None:
    items = _material_items()
    st.markdown(
        "<div style='color:#5a6780;font-size:14px;margin-bottom:8px'>"
        "Pick a production-material category, then choose a plant on the <b>four-plant map</b>; "
        "the system recomputes proximity scores per plant and ranks suppliers.<br>"
        "选择一个生产性物料品类，进入后用<b>四大工厂大地图</b>选厂区，"
        "系统按所选厂区独立计算就近评分并给出供应商排名。</div>",
        unsafe_allow_html=True,
    )
    for prio, title in [(1, "🔵 SABIC Core Procurement · 核心采购品类"),
                        (2, "⚪ Industry Extension · 行业扩展品类")]:
        grp = [c for c in items if c["prio"] == prio]
        if not grp:
            continue
        with st.expander(f"{title}（{len(grp)}）", expanded=(prio == 1)):
            cols = st.columns(4)
            for i, c in enumerate(grp):
                with cols[i % 4]:
                    if st.button(f"{c['en']} · {c['cn']}（{c['count']}）",
                                 key=f"matcat_{c['file']}", width="stretch"):
                        enter_item(c)


# ═══════════════════════════════════════════════════════════════════════
# 其他原料：某品类的四大工厂总览地图 + 厂区选择
# ═══════════════════════════════════════════════════════════════════════
def _material_plant_champions(query: str) -> dict:
    """各厂区该品类的榜首供应商（按厂区独立地理评分）。"""
    out = {}
    for sk in sites.SITE_ORDER:
        try:
            r = search_local(query, site_key=sk).get("suppliers", [])
        except Exception:
            r = []
        out[sk] = r[0] if r else None
    return out


def render_material_overview(query: str) -> None:
    champs = _material_plant_champions(query)
    geojson_path = _BASE / "china.json"
    if geojson_path.exists():
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
        cur = st.session_state.get("site", "SH")
        fig = go.Figure()
        fig.add_trace(go.Choropleth(
            geojson=geojson, locations=[], z=[], featureidkey="properties.name",
            showscale=False, marker_line_color="white", marker_line_width=0.6,
        ))
        for sk in sites.SITE_ORDER:
            site = sites.get_site(sk)
            col = _PLANT_COLOR.get(sk, "#0E8C3A")
            ch = champs.get(sk)
            is_cur = sk == cur
            nm = (ch.get("name", "")[:12] if ch else "—")
            sc = f"{ch.get('score', 0):.0f}" if ch else "—"
            hover = (f"<b>SABIC {site['cn']} Plant · 工厂</b><br>{site.get('feature','')}<br>"
                     f"🥇 Nearest pick · 就近首选：<b>{ch.get('name','—') if ch else '—'}</b>"
                     f" · <b>{sc} pts · 分</b>" if ch else f"<b>SABIC {site['cn']}</b>")
            fig.add_trace(go.Scattergeo(
                lat=[site["lat"]], lon=[site["lng"]], mode="markers+text",
                marker=dict(size=28 if is_cur else 15, color=col,
                            symbol="star" if is_cur else "diamond",
                            line=dict(color="white", width=2.4 if is_cur else 1.4),
                            opacity=1.0 if is_cur else 0.55),
                text=[f"★ {site['short']} · {sc}pts" if is_cur else f"◆ {site['short']}"],
                textposition="top center",
                textfont=dict(size=12.5 if is_cur else 10,
                              color="#0a1628" if is_cur else "#94a3b8"),
                hovertemplate=f"{hover}<extra></extra>",
                name=f"{'★ Current·当前' if is_cur else '◆'} {site['short']}", showlegend=True,
            ))
        fig.update_geos(
            visible=False, resolution=50, scope="asia",
            showland=True, landcolor="#f4f7fb", showocean=True, oceancolor="#e6f0fb",
            showcountries=True, countrycolor="#b6c2d2", countrywidth=0.5,
            showcoastlines=True, coastlinecolor="#b6c2d2", coastlinewidth=0.5,
            center=dict(lat=30, lon=110), projection_type="mercator",
            lonaxis=dict(range=[97, 125]), lataxis=dict(range=[18, 41]),
        )
        fig.update_layout(font=_FONT, paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=0, r=0, t=6, b=0), height=420,
                          legend=dict(orientation="h", x=0, y=-0.04, font=dict(size=12),
                                      bgcolor="rgba(255,255,255,.85)",
                                      bordercolor="#e2e8f0", borderwidth=1))
        st.plotly_chart(fig, width="stretch",
                        config={"displayModeBar": False, "scrollZoom": True},
                        key=f"mat_map_{query}")
        st.caption("★ Current plant · ◆ Other plants. Labels show each plant's nearest-pick "
                   "supplier overall score. Switch plant below to recompute distance & "
                   "proximity scores per plant.  \n"
                   "★ 当前采购厂区 · ◆ 其余厂区；标注为各厂就近首选供应商综合分。"
                   "切换下方厂区，距离与就近评分将以该厂独立重算。")

    # 厂区选择（与全局 site 绑定）
    st.radio(
        "Procurement plant · 采购厂区", sites.SITE_ORDER,
        format_func=lambda k: f"{sites.get_site(k)['en']} · {sites.get_site(k)['cn']}",
        horizontal=True, label_visibility="collapsed", key="site",
    )


# ═══════════════════════════════════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════════════════════════════════
HOME_CSS = """
<style>
.home-band{display:flex;align-items:center;gap:14px;margin:6px 0 16px;padding:16px 20px;
  background:linear-gradient(135deg,#071120 0%,#0d1d36 60%,#0a182c 100%);
  border-radius:16px;box-shadow:0 12px 34px -16px rgba(7,17,32,.55);}
.home-band-bar{width:6px;height:52px;border-radius:4px;background:linear-gradient(#5eead4,#0E8C3A);}
.home-band-title{font-size:20px;font-weight:800;color:#fff;letter-spacing:.3px;}
.home-band-sub{font-size:13px;color:#9fb3c8;margin-top:4px;max-width:1100px;line-height:1.6;}
.home-card{position:relative;background:#fff;border:1px solid #e6ebf2;border-top:5px solid var(--accent);
  border-radius:16px;padding:18px 20px 14px;margin-bottom:6px;
  box-shadow:0 10px 28px -18px rgba(10,22,40,.45);transition:transform .12s ease,box-shadow .12s ease;
  min-height:190px;}
.home-card:hover{transform:translateY(-2px);box-shadow:0 16px 34px -16px rgba(10,22,40,.5);}
.home-card-top{display:flex;align-items:center;justify-content:space-between;}
.home-ico{font-size:34px;}
.home-tag{font-size:12px;font-weight:700;color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,#fff);
  border:1px solid color-mix(in srgb,var(--accent) 22%,#fff);padding:3px 11px;border-radius:20px;}
.home-name{font-size:23px;font-weight:800;color:#0a1628;margin:10px 0 1px;}
.home-en{font-size:12px;color:#94a3b8;font-weight:600;letter-spacing:.02em;margin-bottom:7px;}
.home-tagline{font-size:13.5px;color:var(--accent);font-weight:700;line-height:1.5;margin-bottom:5px;}
.home-desc{font-size:13px;color:#5a6780;line-height:1.6;}
.home-back{font-size:13px;}
</style>
"""
