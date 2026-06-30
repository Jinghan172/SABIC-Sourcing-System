# -*- coding: utf-8 -*-
"""
三类核心物料专家评审模块 —— SABIC 上海基地最核心采购物料。
区别于主区的纯企查查工商评分：这里用 6 大差异化加权维度的人工专家评分，
技术匹配度为核心，因此能识别出中信钛业/海湾石化/华臣木业这类"真正好企业"。

数据：data/core_materials.json（由 _build_core_materials.py 生成）。
对外接口：
  load_core_materials()            -> dict
  render_core_cards()              -> 在落地页渲染三张核心物料入口卡
  render_core_report(material_key) -> 渲染某一物料的详尽对比报告
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from utils.scorer import reputation_for
from components.comparison import render_comparison

_BASE = Path(__file__).resolve().parent.parent / "data"
_DATA_PATH = _BASE / "core_materials.json"
_CACHE_DIR = _BASE / "local_cache"
# 放大基础字号，告别"看不清"
_FONT = dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=14)
_BG = "rgba(0,0,0,0)"
_SABIC_GREEN = "#0E8C3A"
_SABIC_DARK = "#0a1628"

# 物料类型 → 颜色（散点/图例配色）
_TYPE_COLOR = {
    # TiO2
    "氯化法龙头": "#0E8C3A", "氯化双线": "#16a34a", "氯化法大厂": "#22c55e",
    "氯化法产线": "#4ade80", "上海一级代理": "#3b82f6", "上海贸易商": "#60a5fa",
    "硫酸法大厂": "#f59e0b", "硫酸法工厂": "#f97316",
    # FFS
    "上海自产龙头": "#2563eb", "上市子公司": "#3b82f6", "上海新三板厂": "#0ea5e9",
    "异地大厂": "#f59e0b", "上海加工厂": "#06b6d4", "异地中小": "#f97316",
    # Pallet
    "上海IPPC龙头": "#b45309", "上海出口托盘厂": "#d97706", "上海物流一体": "#0891b2",
    "长三角配套": "#8b5cf6", "异地中型厂": "#f59e0b",
    # v5 新增
    "氯化法新锐": "#15803d", "广州FFS出口厂·近南沙": "#2563eb",
    "广州出口托盘厂·近南沙": "#d97706",
    "全球氯化法龙头·进口": "#7c3aed", "垂直一体化氯化法·进口": "#7c3aed",
    "氯化法鼻祖·进口": "#7c3aed",
    # v6 新增：补齐南沙/古雷/重庆三基地就近托盘候选
    "华南出口托盘厂·近南沙": "#2563eb",
    "海西出口托盘厂·近古雷": "#d97706",
    "西南出口托盘厂·近重庆": "#a855f7",
}

# 四大基地配色（地图标注 + 就近基地标签）
_BASE_COLOR = {
    "SH": "#0E8C3A", "NS": "#2563eb", "GL": "#f59e0b", "CQ": "#a855f7",
    "ALL": "#7c3aed",
}

# 6 维英文名（与 JSON dim_cn 一一对应），用于双语展示
_DIM_EN = {
    "tech": "Product / tech fit",
    "location": "Proximity & delivery",
    "cost": "Total cost",
    "ehss": "EHSS & compliance",
    "scale": "Capacity & resilience",
    "service": "Service & partnership",
}


def _dim_bi(k: str, dim_cn: dict, sep: str = " · ") -> str:
    """维度双语标签：英文在前、中文在后。"""
    return f"{_DIM_EN.get(k, k)}{sep}{dim_cn.get(k, k)}"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点球面直线距离（km），与 regions/数据里既有 distance_km 口径一致。"""
    R = 6371.0
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


# 木托盘『就近基地区位』维度：纯按到最近基地的直线距离打分。
# 木托盘又重又笨、低货值、需在基地就地装箱，就近交付是硬指标；该曲线对四个
# 基地完全对称（近南沙/古雷/重庆与近上海同分），消除原『上海 vs 异地』偏置。
_PALLET_LOC_CURVE = [
    (50, 98), (75, 95), (100, 92), (150, 86),
    (250, 78), (450, 68), (700, 58), (1100, 48),
]


def _location_score_from_km(km: float) -> float:
    """到最近基地的直线距离 → 0-100 就近基地区位分（越近越高，四基地对称）。"""
    for thresh, score in _PALLET_LOC_CURVE:
        if km <= thresh:
            return float(score)
    return 40.0


def _recompute_base_km(data: dict) -> None:
    """按企业工厂坐标到『所属基地』的真实直线距离重算 base_km，避免手填值与
    地图气泡位置矛盾（如中信钛业工厂在辽宁锦州、却被标成『近上海 ~40km』）。
    并对木托盘按该距离自动重算『就近基地区位』维度分，使四个基地完全对称，
    新增任何基地附近的供应商都自动公平评分（不再受『上海 vs 异地』模板偏置）。
    进口企业（无坐标 / is_import）保持原状。就近基地按四基地中最近者兜底。"""
    bases = {b["key"]: b for b in data.get("bases", [])}
    if not bases:
        return
    for m in data.get("materials", []):
        is_pallet = m.get("key") == "Pallet"
        for c in m.get("companies", []):
            co = c.get("coords")
            if not co or c.get("is_import"):
                continue
            # 优先用已指定基地；缺失则取四基地中最近的一个
            b = bases.get(c.get("base"))
            if b is None:
                b = min(bases.values(),
                        key=lambda x: _haversine_km(co["lat"], co["lng"], x["lat"], x["lng"]))
                c["base"] = b["key"]
                c["base_cn"] = b["cn"]
            c["base_km"] = round(_haversine_km(co["lat"], co["lng"], b["lat"], b["lng"]))
            # 木托盘：区位维度改为按就近基地距离自动打分
            if is_pallet and "dims" in c:
                c["dims"]["location"] = _location_score_from_km(c["base_km"])


def _bases() -> list[dict]:
    return load_core_materials().get("bases", [])


def _base_color(c: dict) -> str:
    return _BASE_COLOR.get(c.get("base", "SH"), "#64748b")


def _base_label(c: dict) -> str:
    """就近基地短标签，如 '近南沙 ~45km'；进口企业显示覆盖说明。"""
    if c.get("is_import"):
        return c.get("base_cn", "Import · 进口·覆盖四基地")
    km = c.get("base_km")
    cn = c.get("base_cn", "")
    if km is None:
        return f"near · 近{cn}" if cn else ""
    return f"near · 近{cn} ~{km}km"


def _near_base(c: dict, thresh: int = 120) -> bool:
    """是否紧邻某一基地（≤thresh km），用于'本地就近'计数。"""
    km = c.get("base_km")
    return km is not None and km <= thresh


def _norm(s: str) -> str:
    for t in ("股份", "有限", "责任", "公司", "集团", "（", "）", "(", ")", " "):
        s = s.replace(t, "")
    return s


def _match_qcc(name: str, qcc_companies: list[dict]) -> dict | None:
    """把专家名录里的企业与企查查缓存按名称模糊对齐。"""
    a = _norm(name)
    for q in qcc_companies:
        b = _norm(q.get("name", ""))
        if not b:
            continue
        if a in b or b in a or (len(a) >= 4 and len(b) >= 4 and a[:5] == b[:5]):
            return q
    return None


@st.cache_data(show_spinner=False)
def load_core_materials() -> dict:
    try:
        data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"materials": [], "dim_keys": [], "dim_cn": {}}

    # 按真实工厂坐标重算就近基地距离，纠正手填的 base_km 错误
    _recompute_base_km(data)

    # 并入企查查工商数据（按名称匹配）+ 互联网公开信息核验
    for m in data.get("materials", []):
        qcc = []
        try:
            cache = json.loads((_CACHE_DIR / m["cache_file"]).read_text(encoding="utf-8"))
            qcc = cache.get("companies", [])
        except Exception:
            qcc = []
        for c in m["companies"]:
            q = _match_qcc(c["name"], qcc)
            if q:
                c["_qcc"] = {
                    "credit_code":  q.get("credit_code", ""),
                    "legal_person": q.get("legal_person", ""),
                    "reg_capital":  q.get("reg_capital", ""),
                    "established":  q.get("established", ""),
                    "status":       q.get("status", ""),
                    "province":     q.get("province", ""),
                    "address":      q.get("address", ""),
                    "industry":     q.get("industry", ""),
                    "qcc_name":     q.get("name", ""),
                    "legal_name":   q.get("legal_name", "") or q.get("name", ""),
                    "insured":      q.get("insured", ""),
                }
            rep = reputation_for(c["name"])
            if rep:
                c["_web"] = rep
            # 核验等级：2=企查查工商, 1=互联网公开信息, 0=待核验
            c["_verify"] = 2 if q else (1 if rep else 0)
    return data


def _materials() -> list[dict]:
    return load_core_materials().get("materials", [])


def get_material(key: str) -> dict | None:
    return next((m for m in _materials() if m["key"] == key), None)


def _is_local(loc: str) -> bool:
    return "上海" in (loc or "")


# ═══════════════════════════════════════════════════════════════════════
# 落地页：三张核心物料入口卡
# ═══════════════════════════════════════════════════════════════════════
def render_core_cards() -> None:
    mats = _materials()
    if not mats:
        return

    st.markdown("""
<div class="core-band">
  <div class="core-band-bar"></div>
  <div>
    <div class="core-band-title">⭐ Most Critical Materials · Expert Supplier Review · 最核心物料 · 专家级供应商评审</div>
    <div class="core-band-sub">Three strategic materials exported to Saudi Arabia — beyond pure QCC business scoring, graded by a 6-dimension weighted expert model. Click to open the full comparison report.<br>三类外销沙特的战略物料 —— 已脱离纯企查查工商评分，采用 6 维差异化加权专家评分，点击进入详尽对比报告</div>
  </div>
</div>
""", unsafe_allow_html=True)

    cols = st.columns(3)
    for col, m in zip(cols, mats):
        champ = next((c for c in m["companies"] if c["name"] == m["champion"]), m["companies"][0])
        local_n = sum(1 for c in m["companies"] if _near_base(c))
        with col:
            st.markdown(f"""
<div class="core-card" style="--accent:{m['accent']}">
  <div class="core-card-top">
    <span class="core-ico">{m['icon']}</span>
    <span class="core-tag">{len(m['companies'])} candidates · 家候选</span>
  </div>
  <div class="core-name">{m.get('en', m['cn'])}</div>
  <div class="core-name" style="font-size:15px;margin-top:0;color:#5a6780">{m['cn']}</div>
  <div class="core-tagline">{m['tagline']}</div>
  <div class="core-champ">
    <span class="core-champ-medal">🥇</span>
    <div>
      <div class="core-champ-name">{champ['name']}</div>
      <div class="core-champ-lbl">Strategic pick · 战略首选 · {champ['score']}</div>
    </div>
  </div>
  <div class="core-mini">
    <span>📍 Near base · 紧邻基地 <b>{local_n}</b></span>
    <span>🎯 Lead · 首选领先 <b>{round(champ['score'] - m['companies'][1]['score'], 1)}</b></span>
  </div>
</div>
""", unsafe_allow_html=True)
            if st.button(f"View {m['short']} full review report · 查看详尽评审报告 →", key=f"core_enter_{m['key']}",
                         width="stretch", type="primary"):
                st.session_state.core_material = m["key"]
                st.session_state.query = ""
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 地理：从 location 文本解析省份 + 省会坐标
# ═══════════════════════════════════════════════════════════════════════
_PROV_COORDS: dict | None = None


def _province_coords() -> dict:
    global _PROV_COORDS
    if _PROV_COORDS is None:
        try:
            _PROV_COORDS = json.loads(
                (_BASE / "regions.json").read_text(encoding="utf-8")
            ).get("provinceCoords", {})
        except Exception:
            _PROV_COORDS = {}
    return _PROV_COORDS


def _province_of(loc: str) -> str | None:
    """从 '辽宁锦州（上海天亿…）' 这类文本里取出真实工厂所在省份。"""
    coords = _province_coords()
    loc = (loc or "").strip()
    for p in coords:
        if loc.startswith(p):
            return p
    return None


# ═══════════════════════════════════════════════════════════════════════
# 图表（全部交互式 · 字号放大）
# ═══════════════════════════════════════════════════════════════════════
def _supplier_map(m: dict):
    """供应商区位地图：省份热力底图 + 企业气泡（落在工厂真实城市坐标，大小=综合分，
    冠军金色高亮，气泡描边=就近基地配色）+ SABIC 四大基地（上海/南沙/古雷/重庆）菱形标注。"""
    geojson_path = _BASE / "china.json"
    if not geojson_path.exists():
        return None
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))

    # 省份计数（底图深浅）
    pc: dict[str, int] = {}
    for c in m["companies"]:
        p = _province_of(c["location"])
        if p:
            pc[p] = pc.get(p, 0) + 1
    df = pd.DataFrame([{"province": p, "count": n} for p, n in pc.items()])

    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        geojson=geojson,
        locations=df["province"] if not df.empty else [],
        z=df["count"] if not df.empty else [],
        featureidkey="properties.name",
        colorscale=[[0, "#eef3f8"], [1, m["accent"]]],
        zmin=0, zmax=max(df["count"].max() if not df.empty else 1, 1),
        showscale=False, marker_line_color="white", marker_line_width=0.6,
        hovertemplate="%{location}: %{z} candidates · 家候选<extra></extra>",
    ))

    import random
    # 普通企业（按分数渐变）与冠军分两批画，冠军永远在最上层
    n_lat, n_lon, n_txt, n_size, n_color, n_line = [], [], [], [], [], []
    c_lat = c_lon = c_txt = c_size = None
    for c in m["companies"]:
        co = c.get("coords")
        if not co:
            continue
        # 同城多家做微抖动避免完全重叠
        rnd = random.Random(hash(c["name"]) % 9973)
        lat = co["lat"] + rnd.uniform(-0.18, 0.18)
        lon = co["lng"] + rnd.uniform(-0.20, 0.20)
        sc = c["score"]
        hover = (f"<b>{c['name']}</b><br>{c['type']} · {c['location']}<br>"
                 f"🎯 Nearest base · 就近基地：<b>{_base_label(c)}</b><br>"
                 f"Overall · 综合 {sc:.1f} · Tech · 技术 {c['dims']['tech']:.0f} · Loc · 区位 {c['dims']['location']:.0f}")
        if c["name"] == m["champion"]:
            c_lat, c_lon, c_txt, c_size = lat, lon, hover, max(26, sc * 0.34)
        else:
            n_lat.append(lat); n_lon.append(lon); n_txt.append(hover)
            n_size.append(max(11, sc * 0.26)); n_color.append(sc)
            n_line.append(_base_color(c))

    if n_lat:
        fig.add_trace(go.Scattergeo(
            lat=n_lat, lon=n_lon, text=n_txt, mode="markers",
            marker=dict(size=n_size, color=n_color,
                        colorscale=[[0, "#f59e0b"], [0.5, "#3b82f6"], [1, _SABIC_GREEN]],
                        cmin=55, cmax=95, line=dict(color=n_line, width=2.2), opacity=.92),
            hovertemplate="%{text}<extra></extra>", name="Candidates · 候选供应商",
        ))
    if c_lat is not None:
        fig.add_trace(go.Scattergeo(
            lat=[c_lat], lon=[c_lon], text=[c_txt], mode="markers+text",
            marker=dict(size=c_size, color="#facc15", symbol="star",
                        line=dict(color="#b45309", width=1.6)),
            textfont=dict(size=12, color=_SABIC_DARK),
            hovertemplate="🥇 Strategic pick · 战略首选<br>%{text}<extra></extra>", name="🥇 Strategic pick · 战略首选",
        ))
    # SABIC 四大基地（上海 / 广州南沙 / 福建漳州古雷 / 重庆）
    for bs in _bases():
        col = _BASE_COLOR.get(bs["key"], _SABIC_GREEN)
        fig.add_trace(go.Scattergeo(
            lat=[bs["lat"]], lon=[bs["lng"]], mode="markers+text",
            marker=dict(size=19, color=col, symbol="diamond",
                        line=dict(color="white", width=2)),
            text=[f"◆ SABIC {bs['short']}"], textposition="top center",
            textfont=dict(size=12.5, color=_SABIC_DARK, family="PingFang SC"),
            hovertemplate=f"SABIC {bs['cn']} base · 基地<br>Nearest export port · 就近出口口岸：{bs['port']}<extra></extra>",
            name=f"◆ {bs['short']}", showlegend=True,
        ))

    fig.update_geos(
        visible=False, resolution=50, scope="asia",
        showland=True, landcolor="#f4f7fb",
        showocean=True, oceancolor="#e6f0fb",
        showcountries=True, countrycolor="#b6c2d2", countrywidth=0.5,
        showcoastlines=True, coastlinecolor="#b6c2d2", coastlinewidth=0.5,
        center=dict(lat=34, lon=110), projection_type="mercator",
        lonaxis=dict(range=[78, 132]), lataxis=dict(range=[18, 50]),
    )
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, margin=dict(l=0, r=0, t=8, b=0), height=470,
        legend=dict(orientation="h", x=0, y=-0.04, font=dict(size=12),
                    bgcolor="rgba(255,255,255,.85)", bordercolor="#e2e8f0", borderwidth=1),
    )
    return fig


def _radar_top(m: dict, top_n: int = 5) -> go.Figure:
    dim_keys = load_core_materials()["dim_keys"]
    dim_cn = load_core_materials()["dim_cn"]
    cats = [f"{_DIM_EN.get(k,k)}<br>{dim_cn[k]}" for k in dim_keys]
    cats_closed = cats + [cats[0]]
    palette = ["#0E8C3A", "#3b82f6", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"]
    fig = go.Figure()
    for i, c in enumerate(m["companies"][:top_n]):
        vals = [c["dims"][k] for k in dim_keys]
        vals_closed = vals + [vals[0]]
        col = m["accent"] if c["name"] == m["champion"] else palette[i % len(palette)]
        fig.add_trace(go.Scatterpolar(
            r=vals_closed, theta=cats_closed, fill="toself",
            fillcolor="rgba(0,0,0,0)" if c["name"] != m["champion"] else None,
            line=dict(color=col, width=3.4 if c["name"] == m["champion"] else 1.8),
            name=f"{c['name'][:10]} ({c['score']:.1f})",
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[40, 100], gridcolor="#e2e8f0",
                                   tickfont=dict(size=11)),
                   angularaxis=dict(tickfont=dict(size=13))),
        height=460, margin=dict(l=50, r=50, t=34, b=40),
        paper_bgcolor=_BG, font=_FONT,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, x=0, font=dict(size=12)),
    )
    return fig


def _scatter_tech_loc(m: dict) -> go.Figure:
    dim_cn = load_core_materials()["dim_cn"]
    fig = go.Figure()
    seen = set()
    for c in m["companies"]:
        col = _TYPE_COLOR.get(c["type"], "#94a3b8")
        show_legend = c["type"] not in seen
        seen.add(c["type"])
        fig.add_trace(go.Scatter(
            x=[c["dims"]["tech"]], y=[c["dims"]["location"]],
            mode="markers+text",
            marker=dict(size=14 + (c["score"] - 55) * 0.95, color=col,
                        line=dict(width=2.4 if c["name"] == m["champion"] else 0.6,
                                  color="#0a1628")),
            text=[c["name"][:6]] if c["score"] >= 78 else [""],
            textposition="top center", textfont=dict(size=11),
            name=c["type"], legendgroup=c["type"], showlegend=show_legend,
            hovertemplate=f"{c['name']}<br>{_dim_bi('tech', dim_cn)} %{{x:.1f}}<br>"
                          f"{_dim_bi('location', dim_cn)} %{{y:.1f}}<br>Overall · 综合 {c['score']:.1f}<extra></extra>",
        ))
    fig.update_layout(
        height=470, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor=_BG, plot_bgcolor=_BG, font=_FONT,
        xaxis=dict(title=_dim_bi("tech", dim_cn), gridcolor="#e2e8f0", range=[40, 100],
                   tickfont=dict(size=12)),
        yaxis=dict(title=_dim_bi("location", dim_cn), gridcolor="#e2e8f0", range=[40, 100],
                   tickfont=dict(size=12)),
        legend=dict(font=dict(size=12)),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# 详尽报告
# ═══════════════════════════════════════════════════════════════════════
def _dim_weight_bars(m: dict) -> str:
    dim_keys = load_core_materials()["dim_keys"]
    dim_cn = load_core_materials()["dim_cn"]
    w = m["weights"]
    rows = ""
    for k in dim_keys:
        pct = w[k]
        rows += (
            f"<div class='cm-wrow'>"
            f"<span class='cm-wlbl'>{_dim_bi(k, dim_cn)}</span>"
            f"<div class='cm-wbar'><div class='cm-wfill' style='width:{pct*2}%;background:{m['accent']}'></div></div>"
            f"<span class='cm-wval'>{pct}%</span>"
            f"</div>"
        )
    return rows


def _podium_html(m: dict) -> str:
    """前三名领奖台：金（冠军居中最高）/ 银 / 铜，一眼定胜负。"""
    top = sorted(m["companies"], key=lambda c: -c["score"])[:3]
    if len(top) < 3:
        return ""
    order = [(top[1], "silver", "🥈", "2"), (top[0], "gold", "🥇", "1"),
             (top[2], "bronze", "🥉", "3")]
    cells = ""
    for c, cls, medal, rk in order:
        type_col = _TYPE_COLOR.get(c["type"], "#94a3b8")
        bcol = _base_color(c)
        local = (f"<span class='cm-pod-loc-chip' style='background:{bcol}1a;color:{bcol};"
                 f"border-color:{bcol}40'>📍{_base_label(c)}</span>")
        cells += (
            f"<div class='cm-pod {cls}'>"
            f"<div class='cm-pod-medal'>{medal}</div>"
            f"<div class='cm-pod-name'>{c['name']}</div>"
            f"<div class='cm-pod-type' style='color:{type_col}'>● {c['type']}{local}</div>"
            f"<div class='cm-pod-score'>{c['score']}<span>pts·分</span></div>"
            f"<div class='cm-pod-bar'></div>"
            f"</div>"
        )
    return f"<div class='cm-podium' style='--accent:{m['accent']}'>{cells}</div>"


def _render_company_body(m: dict, c: dict, dim_keys, dim_cn) -> None:
    """单家企业详情卡内容（6 维条 + 优劣势 + 企查查工商 + 互联网核验）。
    供「交互聚焦」与「完整榜单」复用。"""
    sc = c["score"]
    sc_col = "#0E8C3A" if sc >= 80 else ("#f59e0b" if sc >= 70 else "#94a3b8")
    type_col = _TYPE_COLOR.get(c["type"], "#94a3b8")
    is_champ = c["name"] == m["champion"]
    _bcol = _base_color(c)
    local_chip = (f"<span class='cm-loc-chip' style='background:{_bcol};color:#fff;"
                  f"border-color:{_bcol};'>📍 {_base_label(c)}</span>")
    _vf = c.get("_verify", 0)
    _vchip = (
        "<span class='cm-vf cm-vf2'>🏢 QCC-verified · 企查查工商已核验</span>" if _vf == 2 else
        "<span class='cm-vf cm-vf1'>🌐 Web-info verified · 互联网公开信息核验</span>" if _vf == 1 else
        "<span class='cm-vf cm-vf0'>⚪ Manual check pending · 工商待人工核验</span>"
    )
    st.markdown(
        f"<div class='cm-row-head'>"
        f"<span class='cm-type-chip' style='background:{type_col}'>{c['type']}</span>"
        f"{'<span class=\"cm-champ-pill\">⭐ Strategic pick · 战略首选</span>' if is_champ else ''}"
        f"{local_chip}{_vchip}"
        f"<span class='cm-row-loc'>📍 {c['location']}</span>"
        f"<span class='cm-row-score' style='color:{sc_col}'>{sc} pts·分</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='cm-row-note'>{c['note']}</div>", unsafe_allow_html=True)
    if c.get("gs"):
        _gs = c["gs"]
        _gscol = ("#dc2626" if _gs.startswith("❌") else
                  "#d97706" if _gs.startswith("⚠️") else "#0E8C3A")
        st.markdown(
            f"<div style='margin:2px 0 6px;padding:6px 10px;border-radius:8px;"
            f"background:rgba(2,6,23,.03);border-left:3px solid {_gscol};"
            f"font-size:13px;color:#334155'>🏢 <b>Business cross-check · 工商交叉核验</b>：{_gs}</div>",
            unsafe_allow_html=True,
        )
    # 6 维迷你条
    bars = ""
    for k in dim_keys:
        v = c["dims"][k]
        bcol = "#0E8C3A" if v >= 75 else ("#f59e0b" if v >= 55 else "#ef4444")
        bars += (
            f"<div class='cm-dim'>"
            f"<div class='cm-dim-lbl'>{_dim_bi(k, dim_cn)}<b style='color:{bcol}'> {v:.0f}</b></div>"
            f"<div class='cm-dim-bar'><div style='width:{v:.0f}%;background:{bcol}'></div></div>"
            f"</div>"
        )
    st.markdown(f"<div class='cm-dims'>{bars}</div>", unsafe_allow_html=True)
    pcol, ccol = st.columns(2)
    with pcol:
        if c.get("pros"):
            st.markdown("**✅ Strengths · 优势**")
            st.markdown("".join(f"<div class='cm-pro'>＋ {p}</div>" for p in c["pros"]),
                        unsafe_allow_html=True)
        else:
            st.markdown(f"**✅ Positioning · 适配定位**\n\n<div class='cm-pro'>＋ {c['note']}</div>",
                        unsafe_allow_html=True)
    with ccol:
        if c.get("cons"):
            st.markdown("**⚠️ Weaknesses · 短板**")
            st.markdown("".join(f"<div class='cm-con'>－ {p}</div>" for p in c["cons"]),
                        unsafe_allow_html=True)

    # ── 企查查工商信息 + 互联网公开信息核验 ──────────────
    q = c.get("_qcc")
    web = c.get("_web")
    if q or web:
        rows = ""
        if q:
            fields = [
                ("Full name · 企业全称", q.get("legal_name", "") or q.get("qcc_name", "")),
                ("Credit code · 统一信用代码", q.get("credit_code", "")),
                ("Legal rep. · 法定代表人", q.get("legal_person", "")),
                ("Reg. capital · 注册资本", q.get("reg_capital", "")),
                ("Founded · 成立日期", q.get("established", "")),
                ("Status · 经营状态", q.get("status", "")),
                ("Insured (pension) · 参保人数(养老保险)", q.get("insured", "")),
                ("Industry · 所属行业", q.get("industry", "")),
                ("Address · 注册地址", q.get("address", "")),
            ]
            rows = "".join(
                f"<div class='cm-qcc-row'><span>{k}</span><b>{v or '—'}</b></div>"
                for k, v in fields
            )
        src = ("🏢 QCC business data (aligned to the expert list) · 企查查工商数据（已与专家名录对齐）" if q
               else "🌐 Public web info (not in QCC cache; for manual reference) · 互联网公开信息（企查查缓存未直接收录，供人工核验参考）")
        web_html = ""
        if web:
            tk = web.get("tag", "")
            tic = f"｜Ticker · 股票代码 {web['ticker']}" if web.get("ticker") else ""
            aka = f"｜aka · 亦称 {web['aka']}" if web.get("aka") else ""
            web_html = (
                f"<div class='cm-web'>🌐 <b>Public web info · 互联网公开信息</b> "
                f"<span class='cm-web-tag'>{tk}</span>{tic}{aka}<br>"
                f"<span style='color:#334155'>{web.get('note','')}</span></div>"
            )
        st.markdown(
            f"<div class='cm-qcc'><div class='cm-qcc-h'>{src}</div>"
            f"<div class='cm-qcc-grid'>{rows}</div>{web_html}</div>",
            unsafe_allow_html=True,
        )


_PRICE_TAG = {
    "verified": ("Public quote · 公开行情", "tag-verified"),
    "estimate": ("Estimate · 测算参考", "tag-estimate"),
    "rfq":      ("RFQ · 需询价", "tag-rfq"),
}


def _num(x) -> str:
    """数值格式化：整数加千分位（17600→17,600），小数原样（1.5→1.5）。"""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{int(x):,}" if x == int(x) else f"{x:g}"


def _price_text(it: dict) -> tuple[str, str]:
    """返回 (主体数值文本, 单位)。low/high 均为 0 视为文本型（如『需询价』），
    此时主体取 unit 文本、单位留空。"""
    low, high = it.get("low", 0), it.get("high", 0)
    unit = it.get("unit", "")
    if not low and not high:
        return unit, ""
    body = _num(low) if low == high else f"{_num(low)}–{_num(high)}"
    return body, unit


def _render_pricing(m: dict) -> None:
    """市场报价模块：给采购看『市场官方行情价』+『各厂商报价对标』。
    数据来自 data/core_materials.json 各物料的 pricing 块（公开信息测算）。"""
    p = m.get("pricing")
    if not p:
        return
    st.markdown("#### 💰 Market Pricing & Vendor Benchmark · 市场报价与厂商对标 · 给采购的参考价")
    st.markdown(
        f"<div class='cm-price-hero' style='--accent:{m['accent']}'>"
        f"<div class='cm-price-h'>📈 Market snapshot · 行情速览 · updated · 数据更新 {p.get('updated','')}</div>"
        f"<div class='cm-price-sub'>{p.get('headline','')}</div></div>",
        unsafe_allow_html=True,
    )

    off = p.get("official", {})
    items = off.get("items", [])
    if items:
        st.markdown(f"**{off.get('title','Official market price · 市场官方行情价')}**")
        cards = ""
        for it in items:
            body, unit = _price_text(it)
            tcn, tcls = _PRICE_TAG.get(it.get("tag", "estimate"), _PRICE_TAG["estimate"])
            cards += (
                f"<div class='cm-price-card' style='--accent:{m['accent']}'>"
                f"<div class='cm-price-name'>{it['name']}</div>"
                f"<div class='cm-price-val'>{body}<span class='u'>{unit}</span></div>"
                f"<span class='cm-price-tag {tcls}'>{tcn}</span></div>"
            )
        st.markdown(f"<div class='cm-price-grid'>{cards}</div>", unsafe_allow_html=True)
        srcs = ""
        for s in off.get("sources", []):
            if isinstance(s, dict):
                srcs += (f"<a class='cm-price-src cm-price-src-a' "
                         f"href='{s.get('url','#')}' target='_blank' rel='noopener'>"
                         f"📊 {s.get('name','')} ↗</a>")
            else:
                srcs += f"<span class='cm-price-src'>📊 {s}</span>"
        if srcs:
            st.markdown(
                f"<div class='cm-price-srcs'>"
                f"<b style='font-size:12px;color:#334155'>Sources · 数据来源：</b>{srcs}</div>",
                unsafe_allow_html=True,
            )

    vendors = p.get("vendors", [])
    if vendors:
        st.markdown("**🏭 Major Vendor Quote Benchmark · 主要厂商报价对标**")
        vcards = ""
        for v in vendors:
            body, unit = _price_text(v)
            tcn, tcls = _PRICE_TAG.get(v.get("conf", "estimate"), _PRICE_TAG["estimate"])
            vcards += (
                f"<div class='cm-vendor' style='--accent:{m['accent']}'>"
                f"<div class='cm-vendor-top'>"
                f"<div><div class='cm-vendor-name'>{v['name']}</div>"
                f"<div class='cm-vendor-type'>● {v.get('tag_cn','')}</div></div>"
                f"<div class='cm-vendor-price'>{body}<span class='u'> {unit}</span></div>"
                f"</div>"
                f"<div class='cm-vendor-basis'>{v.get('basis','')} "
                f"<span class='cm-price-tag {tcls}'>{tcn}</span></div>"
                f"</div>"
            )
        st.markdown(f"<div class='cm-vendor-grid'>{vcards}</div>", unsafe_allow_html=True)

    if p.get("disclaimer"):
        st.markdown(
            f"<div class='cm-price-disc'>⚠️ {p['disclaimer']}</div>",
            unsafe_allow_html=True,
        )


def render_core_report(material_key: str) -> None:
    m = get_material(material_key)
    if not m:
        st.error("Core-material data not found. · 未找到该核心物料数据。")
        return
    dim_keys = load_core_materials()["dim_keys"]
    dim_cn = load_core_materials()["dim_cn"]
    comps = m["companies"]
    imports = m.get("import_companies", [])
    champ = next((c for c in comps if c["name"] == m["champion"]), comps[0])
    local_n = sum(1 for c in comps if _near_base(c))
    avg = round(sum(c["score"] for c in comps) / len(comps), 1)

    # 返回
    if st.button("← Back to core materials / all categories · 返回核心物料 / 全部品类", key="cm_back"):
        st.session_state.core_material = None
        st.rerun()

    # ── 头部 ────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="cm-hero" style="--accent:{m['accent']}">
  <div class="cm-hero-l">
    <div class="cm-hero-ico">{m['icon']}</div>
    <div>
      <div class="cm-hero-kicker">⭐ SABIC Most Critical Material · Expert Supplier Review · 最核心物料 · 专家级供应商评审报告</div>
      <div class="cm-hero-title">{m.get('en', m['cn'])}</div>
      <div class="cm-hero-title" style="font-size:20px;color:#c0cfe0;font-weight:700;margin-top:0">{m['cn']}</div>
      <div class="cm-hero-tagline">{m['tagline']}</div>
    </div>
  </div>
  <div class="cm-hero-need">📌 {m['need']}</div>
</div>
""", unsafe_allow_html=True)

    # ── KPI 条 ──────────────────────────────────────────────────────
    qcc_n = sum(1 for c in comps if c.get("_verify") == 2)
    web_n = sum(1 for c in comps if c.get("_verify") == 1)
    k1, k2, k3, k4 = st.columns(4)
    _imp_suffix = f" +{len(imports)} import·进口" if imports else ""
    k1.metric("Candidates · 候选供应商", f"{len(comps)}{_imp_suffix}")
    k2.metric("Near base (≤120km) · 紧邻基地", f"{local_n}")
    k3.metric("Top pick score · 战略首选分", f"{champ['score']}")
    k4.metric("Tier avg · 梯队平均分", f"{avg}")

    # 数据来源/核验覆盖条 —— 专家评分 ＋ 企查查工商 ＋ 互联网公开信息三源
    st.markdown(
        f"<div class='cm-srcbar'>"
        f"<span class='cm-src-lbl'>🔁 Three-source cross-check · 三源交叉核验</span>"
        f"<span class='cm-src-chip exp'>👤 Expert scoring · 专家差异化评分 {len(comps)}</span>"
        f"<span class='cm-src-chip qcc'>🏢 QCC-verified · 企查查工商核验 {qcc_n}</span>"
        f"<span class='cm-src-chip web'>🌐 Public web info · 互联网公开信息 {web_n}</span>"
        f"<span class='cm-src-note'>Overall score comes from the 6-dimension expert model; business/web info cross-checks and corrects QCC single-source underestimation. · "
        f"综合分由 6 维专家评分得出；工商/互联网信息用于交叉印证与修正企查查单一来源的低估。</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 冠军聚焦 ────────────────────────────────────────────────────
    pros_html = "".join(f"<li>{p}</li>" for p in champ.get("pros", []))
    st.markdown(f"""
<div class="cm-champ" style="--accent:{m['accent']}">
  <div class="cm-champ-head">
    <span class="cm-champ-medal">🥇</span>
    <div style="flex:1">
      <div class="cm-champ-name">{champ['name']}</div>
      <div class="cm-champ-verdict">{champ.get('verdict','Strategic pick · 战略首选')} · {champ['location']}</div>
    </div>
    <div class="cm-champ-score"><b>{champ['score']}</b><span>Overall · 综合评分</span></div>
  </div>
  <ul class="cm-champ-pros">{pros_html}</ul>
</div>
""", unsafe_allow_html=True)

    # ── 为什么企查查评分选不出它 ─────────────────────────────────
    st.markdown(f"""
<div class="cm-why">
  <div class="cm-why-title">🧭 Why pure QCC scoring can't pick it · 为什么纯企查查评分选不出它？</div>
  <div class="cm-why-body">{m['why_qcc_misses']}</div>
</div>
""", unsafe_allow_html=True)

    # ── 市场报价模块（公开信息）────────────────────────────────────
    _render_pricing(m)

    # ── 评分框架 ────────────────────────────────────────────────────
    with st.expander("📐 Scoring framework: 6-dim weighting + bonus rules · 评分框架：6 维差异化加权 + 专项加分规则", expanded=False):
        cfl, cfr = st.columns([1, 1])
        with cfl:
            st.markdown("**Primary dimension weights (material-specific) · 一级维度权重（本物料专属）**")
            st.markdown(f"<div class='cm-wbox'>{_dim_weight_bars(m)}</div>", unsafe_allow_html=True)
        with cfr:
            st.markdown("**Bonus rules (key to spotting truly good firms) · 专项加分规则（识别真正好企业的关键）**")
            st.markdown(
                "<div class='cm-bonus'>"
                + "".join(f"<div class='cm-bonus-item'>✚ {r}</div>" for r in m["bonus_rules"])
                + "</div>", unsafe_allow_html=True)

    # ── 可视化（交互式 · 地图优先）──────────────────────────────────
    st.markdown("#### 🗺️ Supplier Location Map · 供应商区位地图 · 四大基地就近交付，谁离哪个厂近、谁分更高，一图看清")
    _map = _supplier_map(m)
    if _map is not None:
        st.plotly_chart(_map, width="stretch",
                        config={"displayModeBar": False, "scrollZoom": True},
                        key=f"cm_map_{m['key']}")
        st.caption("◆ SABIC four bases: Shanghai (green) · Guangzhou Nansha (blue) · Fujian Gulei (orange) · "
                   "Chongqing (purple). Bubble border = nearest base · ⭐ gold star = strategic pick · "
                   "bigger bubble = higher score · hover for 'nearest base + distance' · scroll to zoom/drag.  \n"
                   "◆ SABIC 四大基地：上海(绿) · 广州南沙(蓝) · 福建漳州古雷(橙) · 重庆(紫) —— "
                   "气泡描边颜色＝该企业就近基地 · ⭐金色大星为战略首选 · 气泡越大综合分越高 · "
                   "鼠标悬停看『就近基地 + 距离』 · 可滚轮缩放拖拽。")
    else:
        st.info("china.json base map missing — skipping location map. · china.json 地图底图缺失，跳过区位地图。")

    # ── 进口供应商区（按物料专属文案；标题/说明来自 import_meta，数量动态）────
    if imports:
        _n_imp = len(imports)
        _imeta = m.get("import_meta", {})
        _imp_title = _imeta.get(
            "title", f"🌐 {m.get('en', m['cn'])} · Import / International Suppliers · 进口 / 国际供应商区")
        _imp_caption = _imeta.get(
            "caption",
            f"The {_n_imp} international suppliers below serve as import benchmarks and backups, "
            "covering the four bases via 'import + nearest port': Shanghai→Shanghai/Yangshan, "
            "Nansha→Nansha, Gulei→Gulei/Xiamen, Chongqing→Guoyuan transshipment. · "
            f"下列 {_n_imp} 家国际供应商作为进口对标基准与备选，"
            "按『进口 + 就近港口』模式覆盖四大基地：上海→上海港/洋山、"
            "南沙→南沙港、古雷→古雷/厦门港、重庆→果园港转水。")
        st.markdown(f"#### {_imp_title}")
        st.caption(_imp_caption)
        icols = st.columns(len(imports))
        for col, c in zip(icols, imports):
            with col:
                tcol = _TYPE_COLOR.get(c["type"], "#7c3aed")
                st.markdown(
                    f"<div class='cm-imp'>"
                    f"<div class='cm-imp-h'>{c['name']}</div>"
                    f"<div class='cm-imp-type' style='color:{tcol}'>● {c['type']}</div>"
                    f"<div class='cm-imp-score'>{c['score']}<span>pts·分</span>"
                    f"<span class='cm-imp-origin'>Origin · 产地 {c.get('import_origin','—')}</span></div>"
                    f"<div class='cm-imp-note'>{c['note']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        with st.expander(f"Expand {_n_imp} imports — detailed pros/cons · 展开进口详细优劣势对比", expanded=False):
            for c in imports:
                with st.expander(f"🌐 {c['name']} — {c['score']} pts·分（{c.get('import_origin','')}）",
                                 expanded=False):
                    _render_company_body(m, c, dim_keys, dim_cn)

    with st.expander("📡 Radar / 🎯 Tech × Location quadrant (two interactive charts) · 多维雷达 / 技术 × 区位象限", expanded=False):
        vt1, vt2 = st.tabs(["📡 Top radar · 头部雷达对比", "🎯 Tech × Location · 技术 × 区位象限"])
        with vt1:
            st.plotly_chart(_radar_top(m), width="stretch",
                            config={"displayModeBar": False}, key=f"cm_radar_{m['key']}")
            st.caption("Bold accent line = strategic pick — its tech/location/compliance polygon is the fullest.  \n"
                       "加粗主色为战略首选 —— 其『技术匹配 / 区位交付 / 合规』围出的多边形最饱满。")
        with vt2:
            st.plotly_chart(_scatter_tech_loc(m), width="stretch",
                            config={"displayModeBar": False}, key=f"cm_scatter_{m['key']}")
            st.caption("Top-right quadrant = high tech fit + best proximity (nearest of the four bases) — the ideal "
                       "Saudi-export supplier zone. Bubble size = overall score.  \n"
                       "右上象限 = 技术匹配高 + 就近基地区位优（四基地中最近一个），是出口沙特的理想供应商区。气泡大小=综合分。")

    # ── 前三名领奖台 ────────────────────────────────────────────────
    st.markdown("#### 🏆 Top-3 Strategic Tier · 前三名战略梯队")
    st.markdown(_podium_html(m), unsafe_allow_html=True)

    # ── 厂家逐一对比（图示之外的文字版结论）────────────────────────
    render_comparison(
        comps, dim_keys, {k: _dim_bi(k, dim_cn) for k in dim_keys},
        m["weights"], accent=m["accent"], key=m["key"],
        intro=("Below, each supplier's scoring rationale in words: where the strategic pick is strong and by how "
               "much it leads; each other firm's key weak dimension and weighted drag, and the scenarios where it "
               "is actually the better choice. · "
               "下面用文字逐家说清评分依据：战略首选强在哪几维、领先多少；其余各家"
               "的核心短板是哪一维、加权拖累多少分，以及它们在什么场景下反而更值得选。"),
    )

    # ── 交互聚焦：选一家看穿到底（替代一长串列表）────────────────────
    st.markdown("#### 🔍 Focus on One · 6-dim strengths + QCC info · 聚焦单家 · 选择企业看 6 维强弱 + 企查查工商信息")
    _opts = [f"{c['rank']}. {c['name']}（{c['score']}）"
             + ("　⭐ pick·首选" if c["name"] == m["champion"] else "")
             for c in comps]
    _sel = st.selectbox("Select a company to inspect · 选择要深入查看的企业", _opts, index=0,
                        key=f"cm_focus_{m['key']}", label_visibility="collapsed")
    _idx = _opts.index(_sel)
    st.markdown(f"<div class='cm-focus' style='--accent:{m['accent']}'>", unsafe_allow_html=True)
    _render_company_body(m, comps[_idx], dim_keys, dim_cn)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── 完整榜单（默认折叠，给想逐家核对的人）────────────────────────
    with st.expander(f"📋 Expand full ranking of {len(comps)} · 展开完整榜单 · 逐家优劣对比", expanded=False):
        for c in comps:
            rank = c["rank"]
            medal = ["🥇", "🥈", "🥉"][rank - 1] if rank <= 3 else f"{rank}"
            is_champ = c["name"] == m["champion"]
            title = (f"{medal}　{c['name']}　— {c['score']} pts·分"
                     f"{'　⭐ 战略首选' if is_champ else ''}")
            with st.expander(title, expanded=False):
                _render_company_body(m, c, dim_keys, dim_cn)

    # ── 评审结论 ────────────────────────────────────────────────────
    st.markdown("#### 🧾 Review Conclusion & Procurement Advice · 评审结论与采购建议")
    cc = m["conclusion"]
    st.markdown(f"""
<div class="cm-concl">
  <div class="cm-concl-card strat"><div class="cm-concl-h">🥇 Strategic supply · 战略主供</div><div>{cc['strategic']}</div></div>
  <div class="cm-concl-card back"><div class="cm-concl-h">🔁 Backup tier · 备选梯队</div><div>{cc['backup']}</div></div>
  <div class="cm-concl-card risk"><div class="cm-concl-h">⛔ Risk note · 风险提示</div><div>{cc['risk']}</div></div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════════════════════════════════
CORE_CSS = """
<style>
/* 返回按钮：避免被 Streamlit 顶部 header 遮住一半 */
.st-key-cm_back{margin-top:2.6rem;}
/* 核心物料分区横幅 */
.core-band{display:flex;align-items:center;gap:14px;margin:6px 0 14px;padding:14px 18px;
  background:linear-gradient(135deg,#0b1f17 0%,#0d2a1c 55%,#0a1628 100%);
  border-radius:14px;box-shadow:0 10px 30px -14px rgba(7,17,32,.5);}
.core-band-bar{width:5px;height:46px;border-radius:4px;background:linear-gradient(#34d399,#0E8C3A);}
.core-band-title{font-size:18px;font-weight:800;color:#fff;letter-spacing:.3px;}
.core-band-sub{font-size:12.5px;color:#9fb3c8;margin-top:3px;max-width:980px;line-height:1.5;}
/* 核心物料入口卡 */
.core-card{position:relative;background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--accent);
  border-radius:14px;padding:16px 16px 14px;box-shadow:0 8px 24px -16px rgba(10,22,40,.45);
  transition:transform .12s ease,box-shadow .12s ease;min-height:236px;}
.core-card:hover{transform:translateY(-2px);box-shadow:0 14px 30px -16px rgba(10,22,40,.5);}
.core-card-top{display:flex;align-items:center;justify-content:space-between;}
.core-ico{font-size:30px;}
.core-tag{font-size:11px;font-weight:700;color:var(--accent);background:rgba(14,140,58,.08);
  border:1px solid rgba(14,140,58,.18);padding:2px 9px;border-radius:20px;}
.core-name{font-size:20px;font-weight:800;color:#0a1628;margin:10px 0 2px;}
.core-tagline{font-size:12px;color:#5a6780;line-height:1.5;min-height:34px;}
.core-champ{display:flex;align-items:center;gap:9px;margin:10px 0 8px;padding:9px 11px;
  background:#f6faf7;border:1px solid #e1efe6;border-radius:10px;}
.core-champ-medal{font-size:20px;}
.core-champ-name{font-size:13.5px;font-weight:700;color:#0a1628;line-height:1.25;}
.core-champ-lbl{font-size:11px;color:var(--accent);font-weight:600;margin-top:1px;}
.core-mini{display:flex;justify-content:space-between;font-size:11.5px;color:#5a6780;padding:0 2px;}
.core-mini b{color:#0a1628;}
/* 报告 hero */
.cm-hero{background:linear-gradient(135deg,#071120 0%,#0d1d36 60%,#0a182c 100%);
  border-radius:16px;padding:22px 26px;margin:8px 0 14px;position:relative;overflow:hidden;
  box-shadow:0 16px 40px -18px rgba(7,17,32,.55);}
.cm-hero::after{content:'';position:absolute;top:-80px;right:-50px;width:300px;height:300px;
  border-radius:50%;background:radial-gradient(circle,var(--accent),transparent 68%);opacity:.25;filter:blur(10px);}
.cm-hero-l{display:flex;align-items:center;gap:16px;position:relative;z-index:1;}
.cm-hero-ico{font-size:44px;line-height:1;}
.cm-hero-kicker{font-size:12.5px;font-weight:700;letter-spacing:.14em;color:#5eead4;text-transform:uppercase;}
.cm-hero-title{font-size:34px;font-weight:800;color:#fff;margin:4px 0;}
.cm-hero-tagline{font-size:15.5px;color:#c0cfe0;}
.cm-hero-need{position:relative;z-index:1;margin-top:14px;font-size:14.5px;color:#d6e0ec;line-height:1.75;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:11px 14px;}
/* 冠军卡 */
.cm-champ{background:#fff;border:1px solid #e6ebf2;border-left:5px solid var(--accent);
  border-radius:14px;padding:16px 18px;margin:12px 0;box-shadow:0 8px 24px -18px rgba(10,22,40,.4);}
.cm-champ-head{display:flex;align-items:center;gap:14px;}
.cm-champ-medal{font-size:34px;}
.cm-champ-name{font-size:21px;font-weight:800;color:#0a1628;}
.cm-champ-verdict{font-size:13.5px;color:var(--accent);font-weight:600;margin-top:2px;}
.cm-champ-score{text-align:center;}
.cm-champ-score b{font-size:36px;color:var(--accent);font-weight:800;display:block;line-height:1;}
.cm-champ-score span{font-size:12px;color:#9ba8bb;}
.cm-champ-pros{margin:12px 0 0;padding-left:20px;}
.cm-champ-pros li{font-size:14.5px;color:#2b3a4f;line-height:1.8;margin-bottom:3px;}
/* 为什么企查查选不出 */
.cm-why{background:#fffaf0;border:1px solid #fde9c8;border-radius:12px;padding:14px 18px;margin:4px 0 14px;}
.cm-why-title{font-size:16px;font-weight:800;color:#b45309;margin-bottom:6px;}
.cm-why-body{font-size:14.5px;color:#7c5310;line-height:1.8;}
/* 权重条 */
.cm-wbox{background:#f8fafc;border:1px solid #e6ebf2;border-radius:10px;padding:10px 12px;}
.cm-wrow{display:flex;align-items:center;gap:8px;margin:5px 0;}
.cm-wlbl{width:230px;font-size:12px;color:#2b3a4f;line-height:1.35;}
.cm-wbar{flex:1;height:9px;background:#e8edf3;border-radius:5px;overflow:hidden;}
.cm-wfill{height:100%;border-radius:5px;}
.cm-wval{width:38px;text-align:right;font-size:12px;font-weight:700;color:#0a1628;}
.cm-bonus{display:flex;flex-direction:column;gap:6px;}
.cm-bonus-item{font-size:12.3px;color:#2b3a4f;background:#f6faf7;border:1px solid #e1efe6;
  border-radius:8px;padding:6px 10px;line-height:1.5;}
/* 榜单行 */
.cm-row-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:6px;}
.cm-type-chip{color:#fff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;}
.cm-loc-chip{font-size:11px;font-weight:700;color:#0E8C3A;background:rgba(14,140,58,.1);
  border:1px solid rgba(14,140,58,.2);padding:2px 8px;border-radius:20px;}
.cm-row-loc{font-size:13.5px;color:#5a6780;}
.cm-row-score{margin-left:auto;font-size:20px;font-weight:800;}
.cm-row-note{font-size:14px;color:#3a4a5f;line-height:1.7;margin-bottom:10px;}
.cm-champ-pill{font-size:11.5px;font-weight:700;color:#b45309;background:#fef3c7;
  border:1px solid #fcd34d;padding:2px 9px;border-radius:20px;}
.cm-dims{display:grid;grid-template-columns:repeat(3,1fr);gap:9px 18px;margin-bottom:12px;}
.cm-dim-lbl{font-size:13px;color:#5a6780;margin-bottom:3px;}
.cm-dim-bar{height:8px;background:#e8edf3;border-radius:4px;overflow:hidden;}
.cm-dim-bar>div{height:100%;border-radius:4px;}
.cm-pro{font-size:13.8px;color:#15603a;line-height:1.7;margin:2px 0;}
.cm-con{font-size:13.8px;color:#9a3412;line-height:1.7;margin:2px 0;}
/* 三源核验条 */
.cm-srcbar{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:10px 0 4px;padding:9px 13px;
  background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;}
.cm-src-lbl{font-size:14px;font-weight:800;color:#0a1628;}
.cm-src-chip{font-size:13px;font-weight:700;padding:3px 11px;border-radius:20px;}
.cm-src-chip.exp{color:#0E8C3A;background:rgba(14,140,58,.1);border:1px solid rgba(14,140,58,.2);}
.cm-src-chip.qcc{color:#2563eb;background:rgba(37,99,235,.1);border:1px solid rgba(37,99,235,.2);}
.cm-src-chip.web{color:#b45309;background:rgba(180,83,9,.1);border:1px solid rgba(180,83,9,.2);}
.cm-src-note{font-size:12.5px;color:#64748b;margin-left:auto;max-width:560px;line-height:1.55;}
/* 核验徽标 */
.cm-vf{font-size:10.5px;font-weight:700;padding:1px 8px;border-radius:20px;}
.cm-vf2{color:#2563eb;background:rgba(37,99,235,.1);border:1px solid rgba(37,99,235,.22);}
.cm-vf1{color:#b45309;background:rgba(180,83,9,.1);border:1px solid rgba(180,83,9,.22);}
.cm-vf0{color:#94a3b8;background:#f1f5f9;border:1px solid #e2e8f0;}
/* 企查查/互联网信息块 */
.cm-qcc{margin-top:12px;background:#f8fafc;border:1px solid #e6ebf2;border-radius:10px;padding:12px 14px;}
.cm-qcc-h{font-size:13.5px;font-weight:700;color:#334155;margin-bottom:8px;}
.cm-qcc-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 20px;}
.cm-qcc-row{display:flex;justify-content:space-between;gap:10px;font-size:13.5px;border-bottom:1px dashed #eef1f5;padding:3px 0;}
.cm-qcc-row span{color:#64748b;white-space:nowrap;}
.cm-qcc-row b{color:#1e293b;text-align:right;font-weight:600;}
.cm-web{margin-top:10px;font-size:13.5px;color:#1e3a8a;background:#eff6ff;border:1px solid #bfdbfe;
  border-radius:8px;padding:9px 12px;line-height:1.7;}
.cm-web-tag{background:#dbeafe;border-radius:6px;padding:0 6px;font-size:12px;}
/* 前三名领奖台 */
.cm-podium{display:flex;align-items:flex-end;justify-content:center;gap:14px;margin:4px 0 16px;}
.cm-pod{flex:1;max-width:300px;border-radius:14px 14px 0 0;padding:16px 16px 0;text-align:center;
  border:1px solid #e6ebf2;border-bottom:none;background:#fff;box-shadow:0 8px 24px -16px rgba(10,22,40,.4);}
.cm-pod-medal{font-size:30px;line-height:1;}
.cm-pod-name{font-size:15px;font-weight:800;color:#0a1628;margin:6px 0 2px;line-height:1.3;}
.cm-pod-type{font-size:12px;font-weight:600;margin-bottom:6px;}
.cm-pod-loc-chip{margin-left:6px;font-size:10.5px;font-weight:700;color:#0E8C3A;
  background:rgba(14,140,58,.1);border:1px solid rgba(14,140,58,.2);padding:1px 6px;border-radius:10px;}
.cm-pod-score{font-size:28px;font-weight:800;color:#0a1628;line-height:1;}
.cm-pod-score span{font-size:13px;font-weight:600;color:#9ba8bb;margin-left:2px;}
.cm-pod-bar{margin-top:12px;border-radius:6px 6px 0 0;}
.cm-pod.gold{transform:translateY(-12px);border-color:#fcd34d;background:linear-gradient(180deg,#fffbeb,#fff);}
.cm-pod.gold .cm-pod-bar{height:66px;background:linear-gradient(180deg,#facc15,#f59e0b);}
.cm-pod.gold .cm-pod-name{font-size:17px;}
.cm-pod.gold .cm-pod-score{font-size:34px;color:#b45309;}
.cm-pod.silver .cm-pod-bar{height:44px;background:linear-gradient(180deg,#cbd5e1,#94a3b8);}
.cm-pod.bronze .cm-pod-bar{height:32px;background:linear-gradient(180deg,#fcd9b6,#d9a066);}
/* 交互聚焦卡 */
.cm-focus{background:#fff;border:1px solid #e6ebf2;border-left:5px solid var(--accent);
  border-radius:0 14px 14px 0;padding:16px 18px 6px;margin:2px 0 12px;
  box-shadow:0 8px 24px -18px rgba(10,22,40,.4);}
/* 结论 */
.cm-concl{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:6px 0 18px;}
.cm-concl-card{border-radius:12px;padding:14px 16px;font-size:14px;line-height:1.75;color:#2b3a4f;}
.cm-concl-card.strat{background:#f0faf4;border:1px solid #bfe6cd;}
.cm-concl-card.back{background:#eff6ff;border:1px solid #c7ddfb;}
.cm-concl-card.risk{background:#fef2f2;border:1px solid #fbd0d0;}
.cm-concl-h{font-size:15px;font-weight:800;margin-bottom:6px;color:#0a1628;}
@media (max-width:900px){.cm-concl,.cm-dims,.cm-podium{grid-template-columns:1fr;}.cm-podium{flex-direction:column;align-items:stretch;}.cm-pod.gold{transform:none;}}
/* 进口供应商区 */
.cm-imp{background:linear-gradient(180deg,#faf5ff,#fff);border:1px solid #e9d5ff;
  border-top:4px solid #7c3aed;border-radius:13px;padding:14px 15px;height:100%;
  box-shadow:0 8px 22px -16px rgba(124,58,237,.5);}
.cm-imp-h{font-size:16px;font-weight:800;color:#0a1628;line-height:1.35;}
.cm-imp-type{font-size:12px;font-weight:700;margin:5px 0 8px;}
.cm-imp-score{font-size:26px;font-weight:800;color:#7c3aed;line-height:1;}
.cm-imp-score span{font-size:12px;color:#7c3aed;margin-left:2px;}
.cm-imp-origin{font-size:11.5px;font-weight:700;color:#6b7280;background:#f3e8ff;
  border:1px solid #e9d5ff;padding:2px 8px;border-radius:20px;margin-left:8px;vertical-align:middle;}
.cm-imp-note{font-size:12.5px;color:#3a4a5f;line-height:1.65;margin-top:9px;}
@media (max-width:900px){.cm-imp{margin-bottom:10px;}}
/* 市场报价模块 */
.cm-price-hero{background:linear-gradient(135deg,#0a1f17 0%,#0d2a1c 60%,#0a1628 100%);
  border-radius:13px;padding:14px 18px;margin:6px 0 14px;
  box-shadow:0 10px 28px -16px rgba(7,17,32,.5);}
.cm-price-h{font-size:15px;font-weight:800;color:#fff;margin-bottom:4px;}
.cm-price-sub{font-size:13px;color:#9fb3c8;line-height:1.65;}
.cm-price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:8px 0 6px;}
.cm-price-card{background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--accent);
  border-radius:12px;padding:14px 16px;box-shadow:0 8px 22px -16px rgba(10,22,40,.4);}
.cm-price-name{font-size:13px;color:#5a6780;font-weight:600;line-height:1.45;min-height:38px;}
.cm-price-val{font-size:27px;font-weight:800;color:#0a1628;line-height:1.1;margin:5px 0 6px;}
.cm-price-val .u{font-size:13px;font-weight:600;color:#9ba8bb;margin-left:4px;}
.cm-price-tag{font-size:10.5px;font-weight:700;padding:2px 9px;border-radius:20px;white-space:nowrap;}
.tag-verified{color:#0E8C3A;background:rgba(14,140,58,.1);border:1px solid rgba(14,140,58,.22);}
.tag-estimate{color:#b45309;background:rgba(180,83,9,.1);border:1px solid rgba(180,83,9,.22);}
.tag-rfq{color:#64748b;background:#f1f5f9;border:1px solid #e2e8f0;}
.cm-price-srcs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0 14px;}
.cm-price-src{font-size:11.5px;color:#475569;background:#f8fafc;border:1px solid #e2e8f0;
  border-radius:20px;padding:2px 10px;}
.cm-price-src-a{text-decoration:none;cursor:pointer;transition:all .12s ease;}
.cm-price-src-a:hover{color:#0E8C3A;background:rgba(14,140,58,.08);
  border-color:rgba(14,140,58,.3);}
.cm-vendor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:6px 0 2px;}
.cm-vendor{background:#fff;border:1px solid #e6ebf2;border-left:4px solid var(--accent);
  border-radius:11px;padding:12px 14px;box-shadow:0 6px 18px -16px rgba(10,22,40,.4);}
.cm-vendor-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;}
.cm-vendor-name{font-size:15px;font-weight:800;color:#0a1628;line-height:1.25;}
.cm-vendor-type{font-size:11.5px;color:#5a6780;font-weight:600;margin-top:2px;}
.cm-vendor-price{font-size:20px;font-weight:800;color:var(--accent);white-space:nowrap;text-align:right;}
.cm-vendor-price .u{font-size:11px;color:#9ba8bb;font-weight:600;}
.cm-vendor-basis{font-size:12.3px;color:#5a6780;line-height:1.6;margin-top:8px;}
.cm-price-disc{font-size:11.5px;color:#94a3b8;line-height:1.65;margin-top:12px;font-style:italic;}
@media (max-width:900px){.cm-price-grid{grid-template-columns:1fr;}}
</style>
"""
