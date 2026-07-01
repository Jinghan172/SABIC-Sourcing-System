# -*- coding: utf-8 -*-
"""
石化设备寻源与采购价格分析模块 —— SABIC 四大工厂设备采购导航。

区别于主区（生产性物料工商评分）、核心物料专家评审与综合服务属地导航：这里覆盖
9 大设备品类（换热器 / 空冷器 / 塔器 / 反应釜 / 离心泵 / 压缩机 / 阀门 / 起重机）。
采购人员在『选定一种设备 + 一个工厂』后，得到两份东西：
  ① 该工厂该设备的入围供应商排名（5 维加权专家评分，可展开明细）；
  ② 一份多源交叉验证的采购价格分析报告 —— 不是单一均价，而是中石化 / 中石油 /
     中招网三大招投标平台 + 供应商报价分布 + 历史中标回归共 5 路口径交叉加权，
     锚定出建议采购价区间与置信度。

数据：data/equipment.json（由 data/build_equipment.py 编译，评分运行时复算）。
对外接口：
  load_equipment()                  -> dict
  render_equipment_cards()          -> 落地页 9 张设备品类导航卡 + 分区横幅
  render_equipment_report(cat_key)  -> 某设备品类的『工厂选择 + 供应商 + 价格分析』报告
  get_equipment(key)                -> dict | None
"""
from __future__ import annotations
import json
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

from utils.equipment_scorer import (
    rank_suppliers, DIM_KEYS, DIM_CN, DIM_EN, DEFAULT_WEIGHTS, verdict_for,
)
from components.comparison import render_comparison, deviation_tornado_figure
from components.pricing import (
    reliability_badge, render_tender_evidence, render_triangulation, render_referenced_tenders,
)

# 5 维双语标签（英文在前、中文在后）
DIM_BI = {k: f"{DIM_EN.get(k, k)} · {DIM_CN.get(k, k)}" for k in DIM_KEYS}

_BASE = Path(__file__).resolve().parent.parent / "data"
_DATA_PATH = _BASE / "equipment.json"
_FONT = dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=14)
_BG = "rgba(0,0,0,0)"
_DARK = "#0a1628"

# 四大工厂配色（与综合服务模块四大基地一致）
_PLANT_COLOR = {"SH": "#0E8C3A", "NS": "#2563eb", "GL": "#f59e0b", "CQ": "#a855f7"}
# 四大工厂英文名（基地名双语化，与 utils/sites.py 口径一致）
_PLANT_EN = {"SH": "Shanghai Pudong", "NS": "Guangzhou Nansha",
             "GL": "Fujian Gulei", "CQ": "Chongqing"}
_MEDALS = ["🥇", "🥈", "🥉", "④"]


@st.cache_data(show_spinner=False)
def load_equipment() -> dict:
    try:
        return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"section": {}, "plants": [], "categories": []}


def _categories() -> list[dict]:
    return load_equipment().get("categories", [])


def _plants() -> list[dict]:
    return load_equipment().get("plants", [])


def get_equipment(key: str) -> dict | None:
    return next((c for c in _categories() if c["key"] == key), None)


def _ranked(c: dict, plant_key: str) -> list[dict]:
    sl = c.get("plants", {}).get(plant_key, {}).get("suppliers", [])
    flt = st.session_state.get("eq_filters") or {}
    sl2 = sl
    if flt.get("local_only"):
        sl2 = [s for s in sl2 if s.get("is_local")]
    if flt.get("quals"):
        sl2 = [s for s in sl2 if s.get("qualification") in flt["quals"]]
    if flt.get("max_lead"):
        sl2 = [s for s in sl2 if s.get("lead_time_days", 999) <= flt["max_lead"]]
    w = st.session_state.get("eq_weights") or DEFAULT_WEIGHTS
    return rank_suppliers(sl2, w)


def _analysis(c: dict, plant_key: str) -> dict:
    return c.get("plants", {}).get(plant_key, {}).get("price_analysis", {})


def _fmt(v) -> str:
    """万元金额：小额保留两位、大额一位、整数去尾。"""
    if v is None:
        return "—"
    return f"{v:.2f}".rstrip("0").rstrip(".") if v < 10 else f"{v:.1f}".rstrip("0").rstrip(".")


def _score_color(v: float) -> str:
    return "#0E8C3A" if v >= 85 else ("#16a34a" if v >= 75 else
                                      ("#f59e0b" if v >= 60 else "#ef4444"))


# ═══════════════════════════════════════════════════════════════════════
# 落地页：9 张设备品类导航卡
# ═══════════════════════════════════════════════════════════════════════
def render_equipment_cards() -> None:
    cats = _categories()
    if not cats:
        return
    sec = load_equipment().get("section", {})

    st.markdown(f"""
<div class="eq-band">
  <div class="eq-band-bar"></div>
  <div>
    <div class="eq-band-title">{sec.get('title', '🏭 Petrochemical Equipment Sourcing & Price Analysis · 石化设备寻源与采购价格分析')}</div>
    <div class="eq-band-sub">{sec.get('sub', '')}</div>
  </div>
</div>
""", unsafe_allow_html=True)

    cols = st.columns(3)
    for i, c in enumerate(cats):
        # 四厂建议价区间（取各厂建议下/上限的并集）+ 全网最优首选
        lows, highs, champs = [], [], []
        for p in _plants():
            pa = _analysis(c, p["key"])
            if pa:
                lows.append(pa["rec_low"])
                highs.append(pa["rec_high"])
            r = _ranked(c, p["key"])
            if r:
                champs.append((r[0]["score"], r[0]["name"], p["short"]))
        band = (f"{_fmt(min(lows))}–{_fmt(max(highs))} 万元"
                if lows else "—")
        best = max(champs) if champs else None
        kind_lbl = {"static": "Static · 静设备", "dynamic": "Rotating · 动设备",
                    "crane": "Special · 特种设备", "extruder": "Compounding · 挤出备件"}.get(c["kind"], "")
        with cols[i % 3]:
            st.markdown(f"""
<div class="eq-card" style="--accent:{c['accent']}">
  <div class="eq-card-top">
    <span class="eq-ico">{c['icon']}</span>
    <span class="eq-tag">{kind_lbl} · 4 plants · 厂寻源</span>
  </div>
  <div class="eq-name">{c['en']}</div>
  <div class="eq-en">{c['cn']}</div>
  <div class="eq-spec">📐 {c['spec']}</div>
  <div class="eq-price-row">
    <div class="eq-price-cell">
      <div class="eq-price-lbl">Industry avg · 行业均价</div>
      <div class="eq-price-val">{_fmt(c['ref_price_wan'])}<span>万</span></div>
    </div>
    <div class="eq-price-cell">
      <div class="eq-price-lbl">4-plant suggested range · 四厂建议价区间</div>
      <div class="eq-price-band">{band}</div>
    </div>
  </div>
  <div class="eq-card-champ">
    <span class="eq-card-champ-lbl">🏆 Best overall · 全网最优</span>
    <span class="eq-card-champ-name">{(best[1][:11] + ' · ' + best[2]) if best else '—'}</span>
    <span class="eq-card-champ-score">{f'{best[0]:.0f}' if best else '—'}</span>
  </div>
</div>
""", unsafe_allow_html=True)
            if st.button(f"Enter · 进入 {c['cn']} · plant choice + price analysis · 工厂选择 + 价格分析 →",
                         key=f"eq_enter_{c['key']}", width="stretch"):
                st.session_state.equipment_cat = c["key"]
                st.session_state.query = ""
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 四大工厂地图：每厂该设备的首选供应商 + 价格锚定
# ═══════════════════════════════════════════════════════════════════════
def _plant_map(c: dict):
    geojson_path = _BASE / "china.json"
    if not geojson_path.exists():
        return None
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))

    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        geojson=geojson, locations=[], z=[],
        featureidkey="properties.name", showscale=False,
        marker_line_color="white", marker_line_width=0.6,
    ))
    for p in _plants():
        col = _PLANT_COLOR.get(p["key"], "#0E8C3A")
        ranked = _ranked(c, p["key"])
        pa = _analysis(c, p["key"])
        prim = ranked[0] if ranked else {}
        runners = ranked[1:3]
        bk = ("<br>🔁 Backup · 备选：" + "、".join(f"{b['name']}({b['score']:.0f})" for b in runners)) if runners else ""
        band = (f"{_fmt(pa['rec_low'])}–{_fmt(pa['rec_high'])} 万元（anchor·锚定 {_fmt(pa['anchor'])}）"
                if pa else "—")
        hover = (f"<b>SABIC {p['cn']} plant · 工厂</b><br>{p.get('feature','')}<br>"
                 f"🥇 Top pick · 首选：<b>{prim.get('name','—')}</b> · <b>{prim.get('score',0):.1f}</b><br>"
                 f"💰 Suggested price · 建议采购价：<b>{band}</b>"
                 f"<br><span style='color:#9fb3c8'>Confidence · 置信 {pa.get('confidence','—')}% · multi-source · 多源交叉验证</span>{bk}")
        fig.add_trace(go.Scattergeo(
            lat=[p["lat"]], lon=[p["lng"]], mode="markers+text",
            marker=dict(size=27, color=col, symbol="diamond",
                        line=dict(color="white", width=2.4), opacity=.95),
            text=[f"◆ {p['short']}<br>{_fmt(pa.get('anchor')) if pa else '—'} 万"],
            textposition="top center",
            textfont=dict(size=12.5, color=_DARK, family="PingFang SC"),
            hovertemplate=f"{hover}<extra></extra>",
            name=f"◆ {p['short']}", showlegend=True,
        ))
    fig.update_geos(
        visible=False, resolution=50, scope="asia",
        showland=True, landcolor="#f4f7fb",
        showocean=True, oceancolor="#e6f0fb",
        showcountries=True, countrycolor="#b6c2d2", countrywidth=0.5,
        showcoastlines=True, coastlinecolor="#b6c2d2", coastlinewidth=0.5,
        center=dict(lat=28, lon=113), projection_type="mercator",
        lonaxis=dict(range=[100, 124]), lataxis=dict(range=[18, 35]),
    )
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, margin=dict(l=0, r=0, t=8, b=0), height=440,
        legend=dict(orientation="h", x=0, y=-0.04, font=dict(size=12.5),
                    bgcolor="rgba(255,255,255,.85)", bordercolor="#e2e8f0", borderwidth=1),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# 价格分析图：多源价区间收敛 + 历史走势
# ═══════════════════════════════════════════════════════════════════════
def _convergence_fig(pa: dict):
    """各口径价格区间横向收敛图 + 建议区间阴影 + 锚定虚线。"""
    rows = []  # (label, low, avg, high, color)
    for s in pa.get("sources", []):
        rows.append((f"{s['short']}（{s['samples']}）", s["low"], s["avg"], s["high"], "#2563eb"))
    sq = pa.get("supplier_quote", {})
    if sq:
        rows.append((f"Supplier quotes · 供应商报价（{sq.get('n',0)}）", sq["low"], sq["p50"], sq["high"], "#0891b2"))
    rows = rows[::-1]  # 让首条出现在顶部

    fig = go.Figure()
    # 建议采购区间阴影 + 锚定线
    fig.add_vrect(x0=pa["rec_low"], x1=pa["rec_high"],
                  fillcolor="rgba(14,140,58,.10)", line_width=0)
    fig.add_vline(x=pa["anchor"], line=dict(color="#0E8C3A", width=2, dash="dash"))
    fig.add_vline(x=pa["ref_price"], line=dict(color="#94a3b8", width=1.4, dash="dot"))

    for i, (lbl, lo, avg, hi, col) in enumerate(rows):
        fig.add_trace(go.Scatter(
            x=[lo, hi], y=[lbl, lbl], mode="lines",
            line=dict(color=col, width=7), opacity=.35,
            hoverinfo="skip", showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=[avg], y=[lbl], mode="markers",
            marker=dict(color=col, size=15, line=dict(color="white", width=2)),
            hovertemplate=f"{lbl}<br>Range · 区间 {_fmt(lo)}–{_fmt(hi)} 万<br>Avg · 均值 <b>{_fmt(avg)}</b> 万<extra></extra>",
            showlegend=False,
        ))
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff",
        height=58 * len(rows) + 90, margin=dict(l=10, r=20, t=42, b=10),
        xaxis=dict(title="Delivered price (10k CNY) · 到厂价（万元）", gridcolor="#eef2f7", zeroline=False),
        yaxis=dict(automargin=True),
        annotations=[
            dict(x=pa["anchor"], y=1.06, yref="paper", showarrow=False,
                 text=f"◆ Cross-anchor · 交叉锚定 {_fmt(pa['anchor'])} 万", font=dict(color="#0E8C3A", size=12.5)),
            dict(x=pa["ref_price"], y=-0.16, yref="paper", showarrow=False,
                 text=f"Industry avg · 行业均价 {_fmt(pa['ref_price'])}", font=dict(color="#94a3b8", size=11)),
        ],
    )
    return fig


def _trend_fig(pa: dict):
    tr = pa.get("trend", [])
    if not tr:
        return None
    xs = [str(t["year"]) for t in tr]
    ys = [t["price"] for t in tr]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers+text",
        line=dict(color="#2563eb", width=3, shape="spline"),
        marker=dict(size=11, color="#2563eb", line=dict(color="white", width=2)),
        text=[f"{_fmt(y)}" for y in ys], textposition="top center",
        textfont=dict(size=12, color=_DARK),
        hovertemplate="%{x} avg award · 中标均价 <b>%{y} 万</b><extra></extra>",
        showlegend=False,
    ))
    fig.add_hline(y=pa["anchor"], line=dict(color="#0E8C3A", width=1.6, dash="dash"),
                  annotation_text=f"Current anchor · 当期锚定 {_fmt(pa['anchor'])} 万",
                  annotation_position="top left",
                  annotation_font=dict(color="#0E8C3A", size=11))
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff",
        height=300, margin=dict(l=10, r=20, t=20, b=10),
        xaxis=dict(gridcolor="#eef2f7"),
        yaxis=dict(title="Avg award price (10k CNY) · 中标均价（万元）", gridcolor="#eef2f7"),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# 供应商领奖台（单工厂 Top3 + 全部明细）
# ═══════════════════════════════════════════════════════════════════════
def _dim_bars_html(sup: dict) -> str:
    rows = ""
    for k in DIM_KEYS:
        v = sup["dims"][k]
        col = _score_color(v)
        rows += (
            f"<div class='eq-dim'>"
            f"<span class='eq-dim-l'>{DIM_BI[k]}</span>"
            f"<div class='eq-dim-track'><div class='eq-dim-fill' "
            f"style='width:{v:.0f}%;background:{col}'></div></div>"
            f"<span class='eq-dim-v' style='color:{col}'>{v:.0f}</span>"
            f"</div>"
        )
    return rows


def _render_plant_podium(c: dict, p: dict) -> None:
    col = _PLANT_COLOR.get(p["key"], "#0E8C3A")
    ranked = _ranked(c, p["key"])
    if not ranked:
        st.info("No shortlisted suppliers at this plant yet. · 该工厂暂无入围供应商。")
        return
    cols = st.columns(min(3, len(ranked)))
    for i, sup in enumerate(ranked[:3]):
        sccol = _score_color(sup["score"])
        chips = (f"<span class='eq-pt' style='--bcol:{col}'>{sup['qualification']}</span>"
                 f"<span class='eq-pt' style='--bcol:{col}'>{'Local·本地' if sup['is_local'] else 'Cross-region·跨区'}</span>"
                 f"<span class='eq-pt' style='--bcol:{col}'>{sup['lead_time_days']}d·天交付</span>")
        with cols[i]:
            st.markdown(
                f"<div class='eq-pod' style='--bcol:{col}'>"
                f"<div class='eq-pod-top'><span class='eq-pod-medal'>{_MEDALS[i]}</span>"
                f"<span class='eq-pod-score' style='color:{sccol}'>{sup['score']:.1f}</span></div>"
                f"<div class='eq-pod-name'>{sup['name']}</div>"
                f"<div class='eq-pod-type'>● {verdict_for(sup)}</div>"
                f"<div class='eq-pod-est'>Est. delivered · 预估到厂价 <b>{_fmt(sup['est_price_wan'])} 万</b>"
                f" · price coef · 价格系数 {sup['price_level']:.2f} · dist · 距厂 {sup['distance_km']} km</div>"
                f"<div class='eq-pod-note'>{sup['special_notes']}</div>"
                f"<div class='eq-pt-row'>{chips}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    # ── 厂家逐一对比（图示之外的文字版结论）────────────────────────
    _w = st.session_state.get("eq_weights") or DEFAULT_WEIGHTS
    render_comparison(
        ranked, DIM_KEYS, DIM_BI, _w, accent=col, key=f"{c['key']}_{p['key']}",
        title=f"⚖️ {p['cn']} · Head-to-Head · 厂家逐一对比 · 为什么是它、别家为什么不是最优",
    )

    with st.expander(f"📋 Expand all {len(ranked)} at {p['cn']} · 5-dim scores · 展开全部 · 5 维评分明细"):
        for sup in ranked:
            sccol = _score_color(sup["score"])
            st.markdown(
                f"<div class='eq-detail'>"
                f"<div class='eq-detail-h'>"
                f"<span class='eq-detail-rank'>{_MEDALS[min(sup['rank']-1,3)]}</span>"
                f"<span class='eq-detail-name'>{sup['name']}</span>"
                f"<span class='eq-detail-score' style='color:{sccol}'>{sup['score']:.1f}</span>"
                f"</div>"
                f"<div class='eq-dims'>{_dim_bars_html(sup)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════
# 性价比象限：综合评分 × 到厂价 —— 找「高分低价」甜区
# ═══════════════════════════════════════════════════════════════════════
def _value_scatter(c: dict, p: dict):
    """单工厂入围供应商的性价比象限图：x＝预估到厂价（越左越便宜），
    y＝5 维综合评分（越上越优）。左上角绿色阴影＝又好又便宜的甜区；
    分界线＝该厂锚定价 + 本组平均分；⭐为入围首选。"""
    ranked = _ranked(c, p["key"])
    if len(ranked) < 2:
        return None
    pa = _analysis(c, p["key"])
    col = _PLANT_COLOR.get(p["key"], "#0E8C3A")
    xs = [s["est_price_wan"] for s in ranked]
    ys = [s["score"] for s in ranked]
    x_ref = pa.get("anchor") if pa else sorted(xs)[len(xs) // 2]
    y_ref = round(sum(ys) / len(ys), 1)
    xmin, xmax, ymax = min(xs), max(xs), max(ys)
    pad = (xmax - xmin) * 0.18 or 1.0

    fig = go.Figure()
    # 甜区阴影（低价 + 高分）
    fig.add_shape(type="rect", x0=xmin - pad, x1=x_ref, y0=y_ref, y1=ymax + 4,
                  fillcolor="rgba(14,140,58,.08)", line_width=0, layer="below")
    fig.add_vline(x=x_ref, line=dict(color="#94a3b8", width=1.4, dash="dot"))
    fig.add_hline(y=y_ref, line=dict(color="#94a3b8", width=1.4, dash="dot"))
    for s in ranked:
        is_champ = s["rank"] == 1
        in_sweet = s["est_price_wan"] <= x_ref and s["score"] >= y_ref
        mcol = "#facc15" if is_champ else (col if in_sweet else "#94a3b8")
        fig.add_trace(go.Scatter(
            x=[s["est_price_wan"]], y=[s["score"]], mode="markers+text",
            marker=dict(size=24 if is_champ else 15, color=mcol,
                        symbol="star" if is_champ else "circle",
                        line=dict(color="#0a1628", width=1.6 if is_champ else 0.6)),
            text=[s["name"][:8]], textposition="top center", textfont=dict(size=11),
            hovertemplate=(f"<b>{s['name']}</b><br>Overall · 综合 {s['score']:.1f}<br>"
                           f"Est. delivered · 预估到厂价 {_fmt(s['est_price_wan'])} 万<br>"
                           f"{s['lead_time_days']}d · 天交付 · {s['qualification']}<extra></extra>"),
            showlegend=False,
        ))
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff", height=440,
        margin=dict(l=10, r=24, t=30, b=10),
        xaxis=dict(title="Est. delivered price (10k CNY) ← cheaper · 预估到厂价　越左越便宜", gridcolor="#eef2f7",
                   range=[xmin - pad, xmax + pad]),
        yaxis=dict(title="5-dim overall score ↑ better · 5 维综合评分　越上越优", gridcolor="#eef2f7"),
        annotations=[dict(x=xmin - pad * 0.2, y=ymax + 3, xanchor="left", showarrow=False,
                          text="🎯 Sweet spot · 甜区 · high score + low price",
                          font=dict(color="#0E8C3A", size=12.5))],
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# 价格分析报告（单工厂）
# ═══════════════════════════════════════════════════════════════════════
def _render_price_report(c: dict, p: dict) -> None:
    pa = _analysis(c, p["key"])
    if not pa:
        st.info("No price analysis for this combination yet. · 该组合暂无价格分析数据。")
        return
    col = _PLANT_COLOR.get(p["key"], "#0E8C3A")
    delta = pa["anchor"] - pa["ref_price"]
    delta_txt = (f"vs industry avg · 较行业均价 {'+' if delta >= 0 else '−'}{_fmt(abs(delta))} 万"
                 f"（{'+' if delta >= 0 else '−'}{abs(delta)/pa['ref_price']*100:.0f}%）")
    conf = pa["confidence"]
    conf_col = "#0E8C3A" if conf >= 85 else ("#16a34a" if conf >= 75 else "#f59e0b")

    # ── 建议采购价 大字号 hero ──────────────────────────────────────
    st.markdown(
        f"<div class='eq-pricehero' style='--bcol:{col}'>"
        f"<div class='eq-ph-l'>"
        f"<div class='eq-ph-kicker'>💰 {p['cn']} · {c['cn']} · Suggested price range (multi-source cross-validated) · 建议采购价区间（多源交叉验证）</div>"
        f"<div class='eq-ph-band'>{_fmt(pa['rec_low'])} <span>–</span> {_fmt(pa['rec_high'])} "
        f"<span class='eq-ph-unit'>万元 / 台 · 10k CNY/unit</span></div>"
        f"<div class='eq-ph-anchor'>◆ Cross-anchor price · 交叉锚定价 <b>{_fmt(pa['anchor'])} 万</b> · {delta_txt}</div>"
        f"</div>"
        f"<div class='eq-ph-r'>"
        f"<div class='eq-ph-conf' style='color:{conf_col}'>{conf}<span>%</span></div>"
        f"<div class='eq-ph-conf-lbl'>Confidence · 验证置信度</div>"
        f"<div class='eq-ph-samp'>{pa['total_samples']} multi-source samples · 条多源样本 · dispersion · 离散度 {pa['dispersion']}%</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 「这个价怎么来的」三步说明 —— 让下方的建模数字不再突兀 ────────
    _tenders = (c.get("transparency") or {}).get("tenders", [])
    st.markdown(
        f"<div class='eq-plogic'>"
        f"<div class='eq-plogic-h'>🧭 How this price is derived · 这个建议采购价是怎么来的</div>"
        f"<div class='eq-plogic-steps'>"
        f"<div class='eq-plogic-step'><span class='eq-plogic-no'>①</span>"
        f"<div><b>Industry benchmark · 行业均价基准</b> {_fmt(pa['ref_price'])} 万<br>"
        f"<span class='eq-plogic-sub'>source · 来源：{c.get('source','')}</span></div></div>"
        f"<div class='eq-plogic-step'><span class='eq-plogic-no'>②</span>"
        f"<div><b>Referenced real tenders · 参考真实公开标书</b> {len(_tenders)} 条<br>"
        f"<span class='eq-plogic-sub'>framework awards — unit price usually undisclosed · 多为框架招标，中标单价多未公开</span></div></div>"
        f"<div class='eq-plogic-step'><span class='eq-plogic-no'>③</span>"
        f"<div><b>Cross-model to an anchor · 交叉建模锚定</b> {_fmt(pa['rec_low'])}–{_fmt(pa['rec_high'])} 万<br>"
        f"<span class='eq-plogic-sub'>platform pricing + supplier quotes + trend · 平台框架价＋供应商报价＋历史走势</span></div></div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ── 明确列出「参考了哪些标书」（不带链接）──────────────────────
    render_referenced_tenders(_tenders, accent=col)

    # ── 五路口径方法卡 ──────────────────────────────────────────────
    st.markdown("##### 🧮 Five price methods · cross-weighted anchor · 五路价格口径 · 交叉加权锚定")
    mcols = st.columns(len(pa["methods"]))
    for i, m in enumerate(pa["methods"]):
        adopt = "采纳" in m["name"]
        with mcols[i]:
            st.markdown(
                f"<div class='eq-method {'adopt' if adopt else ''}'>"
                f"<div class='eq-method-name'>{m['name'].replace('（采纳）','')}"
                f"{'<span class=eq-method-flag>adopted·采纳</span>' if adopt else ''}</div>"
                f"<div class='eq-method-price'>{_fmt(m['price'])}<span> 万</span></div>"
                f"<div class='eq-method-note'>{m['note']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── 定价口径敏感性龙卷风 ────────────────────────────────────────
    _ptor = deviation_tornado_figure(
        [(m["name"].replace("（采纳）", ""), m["price"]) for m in pa["methods"]],
        pa["anchor"], value_fmt=_fmt, unit=" 万")
    if _ptor is not None:
        st.markdown("##### 🌪️ Pricing sensitivity · deviation from anchor (right=dearer, left=cheaper) · 定价口径敏感性 · 各口径相对锚定价的偏离")
        st.plotly_chart(_ptor, width="stretch", config={"displayModeBar": False},
                        key=f"eq_ptor_{c['key']}_{p['key']}")
        st.caption("Green = below the cross-anchor (cheaper), orange = above (dearer); the gap between the two "
                   "longest bars = the negotiation elasticity if a supplier quotes high and you counter low.  \n"
                   "绿条＝该口径定价低于交叉锚定价（更省），橙条＝高于锚定价（更贵）；"
                   "最长两条之差＝若供应商以最高口径报价、你以最低口径还价时的议价弹性空间。")

    # ── 多源区间收敛图 ──────────────────────────────────────────────
    st.markdown("##### 📊 Price-range convergence · green band = suggested range, dashed = cross-anchor · 各口径价格区间收敛")
    st.plotly_chart(_convergence_fig(pa), width="stretch",
                    config={"displayModeBar": False}, key=f"eq_conv_{c['key']}_{p['key']}")

    # ── 平台口径情景建模卡（真实平台、数字为建模，非逐条已核验中标）──
    st.markdown("##### 📊 Platform-calibrated scenario model · real platforms, modeled figures (not verified award counts) · 平台口径情景建模 · 平台真实、数字为建模（非逐条已核验中标，真实招标见上方溯源卡）")
    scols = st.columns(len(pa["sources"]))
    for i, s in enumerate(pa["sources"]):
        with scols[i]:
            st.markdown(
                f"<div class='eq-src'>"
                f"<div class='eq-src-name'>{s['name']}</div>"
                f"<div class='eq-src-url'>🔗 {s['url']}</div>"
                f"<div class='eq-src-avg'>{_fmt(s['avg'])}<span> 万</span></div>"
                f"<div class='eq-src-meta'>Range · 区间 {_fmt(s['low'])}–{_fmt(s['high'])} 万 · "
                f"<b>{s['samples']}</b> modeled samples · 条建模样本</div>"
                f"<div class='eq-src-period'>📅 {s['period']} modeled on platform framework pricing · 基于平台框架价口径建模</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── 历史走势 ────────────────────────────────────────────────────
    st.markdown("##### 📈 2021–2024 award-price trend · regressed to present · 中标价走势 · 回归至当期")
    tf = _trend_fig(pa)
    if tf is not None:
        st.plotly_chart(tf, width="stretch", config={"displayModeBar": False},
                        key=f"eq_trend_{c['key']}_{p['key']}")

    st.caption(
        f"Methodology (scenario model): {sum(s['samples'] for s in pa['sources'])} modeled samples calibrated to the "
        f"three real platforms' framework pricing, plus the median estimated quote of {pa['supplier_quote']['n']} "
        f"shortlisted suppliers and a 2021–2024 trend, cross-weighted 'platform 45% · supplier 30% · historical 25%'; "
        f"three-method dispersion {pa['dispersion']}%. Real public tenders are in the provenance cards at the top of "
        f"this page; figures here are tax- & freight-inclusive delivered estimates for budgeting & negotiation only.  \n"
        f"方法论（情景建模）：{sum(s['samples'] for s in pa['sources'])} 条按中石化/中石油/中招网三平台框架价口径建模的样本，"
        f"叠加 {pa['supplier_quote']['n']} 家入围供应商预估报价中位数与 2021–2024 走势，"
        f"按『平台 45% · 供应商 30% · 历史 25%』交叉加权；三口径离散度 {pa['dispersion']}%。"
        f"真实公开招标见本页顶部『真实招标溯源』卡；此处数字为含税含运到厂估算，仅供采购预算与议价参考。")


# ═══════════════════════════════════════════════════════════════════════
# 品类报告主入口
# ═══════════════════════════════════════════════════════════════════════
def render_equipment_report(cat_key: str) -> None:
    c = get_equipment(cat_key)
    if not c:
        st.error("Equipment category data not found. · 未找到该设备品类数据。")
        return

    if st.button("← Back to equipment sourcing / all categories · 返回设备寻源 / 全部品类", key="eq_back"):
        st.session_state.equipment_cat = None
        st.rerun()

    # ── 头部 ────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="eq-hero" style="--accent:{c['accent']}">
  <div class="eq-hero-l">
    <div class="eq-hero-ico">{c['icon']}</div>
    <div>
      <div class="eq-hero-kicker">🏭 Equipment Sourcing · Plant Choice + Multi-Source Price Analysis · 石化设备寻源 · 工厂选择 + 多源价格分析</div>
      <div class="eq-hero-title">{c['en']}</div>
      <div class="eq-hero-title" style="font-size:20px;color:#c0cfe0;font-weight:700;margin-top:0">{c['cn']}</div>
      <div class="eq-hero-tagline">📐 {c['spec']}</div>
    </div>
  </div>
  <div class="eq-hero-model">🧭 Industry avg benchmark · 行业均价基准 {_fmt(c['ref_price_wan'])} 万元/台 · price source · 价格来源：{c['source']}</div>
</div>
""", unsafe_allow_html=True)

    # ── 真实招标溯源 + 价格可信度（共享透明价格工具箱）──────────────
    t = c.get("transparency") or {}
    if t:
        st.markdown("#### 🔎 Real Tender Provenance & Price Reliability · 真实招标溯源与价格可信度 · 这个价能不能直接用，先说清楚")
        rel = t.get("reliability") or {}
        if rel.get("level"):
            st.markdown(reliability_badge(rel["level"], rel.get("note", "")), unsafe_allow_html=True)
        render_tender_evidence(t.get("tenders", []), accent=c["accent"])
        render_triangulation(t.get("methods", []), anchor=t.get("anchor"),
                             level=(rel.get("level") or "medium"), accent=c["accent"])
        st.caption("These are real public tenders located online. A tender showing “award unit-price undisclosed” is "
                   "normal for framework contracts — it does NOT mean no data. Precisely because unit prices aren’t "
                   "published, each plant’s suggested price further below is triangulated from these tenders + platform "
                   "framework pricing + supplier quotes (see “How this price is derived” in the price-analysis section). · "
                   "上方为联网检索到的真实公开招标。卡片显示『中标单价未公开』是框架招标的常态，并不代表没有数据；"
                   "正因为单价不公开，下方各厂『建议采购价』才据这些标书 + 平台框架价 + 供应商报价交叉测算得出"
                   "（详见下方价格分析里的『这个价怎么来的』）。")

    # ── 四大工厂总览地图 ────────────────────────────────────────────
    st.markdown("#### 🗺️ Four-Plant Sourcing Overview · top pick & suggested price per plant · 四大工厂寻源总览 · 各厂首选供应商与建议采购价，一图直达")
    _map = _plant_map(c)
    if _map is not None:
        st.plotly_chart(_map, width="stretch",
                        config={"displayModeBar": False, "scrollZoom": True},
                        key=f"eq_map_{c['key']}")
        st.caption("◆ Diamonds = four delivery plants: Shanghai Pudong (green) · Guangzhou Nansha (blue) · "
                   "Fujian Gulei (orange) · Chongqing (purple). Labels show each plant's cross-anchor suggested "
                   "price; hover for 'top supplier + suggested range + backups'.  \n"
                   "◆ 菱形为四大交付工厂：上海浦东(绿) · 广州南沙(蓝) · 福建漳州古雷(橙) · 重庆(紫) —— "
                   "标注显示该厂交叉锚定建议价；悬停看『首选供应商 + 建议价区间 + 备选』。")

    # ── 工厂选择器 ──────────────────────────────────────────────────
    st.markdown("#### 🏭 Pick a Delivery Plant · shortlisted suppliers & price analysis · 选择交付工厂 · 查看入围供应商与采购价格分析报告")
    plants = _plants()
    keys = [p["key"] for p in plants]
    if st.session_state.get("equip_plant") not in keys:
        st.session_state.equip_plant = keys[0]
    labels = {p["key"]: f"{_PLANT_EN.get(p['key'], '')} · {p['cn']}　·　{p['feature']}"
              for p in plants}
    sel = st.radio(
        "Delivery plant · 交付工厂", keys,
        index=keys.index(st.session_state.equip_plant),
        format_func=lambda k: labels[k],
        horizontal=True, label_visibility="collapsed", key="eq_plant_radio",
    )
    if sel != st.session_state.equip_plant:
        st.session_state.equip_plant = sel
        st.rerun()

    p = next(pp for pp in plants if pp["key"] == sel)
    col = _PLANT_COLOR.get(sel, "#0E8C3A")
    st.markdown(
        f"<div class='eq-plant-head' style='--bcol:{col}'>"
        f"<span class='eq-plant-dot'></span>"
        f"<span class='eq-plant-name'>SABIC {_PLANT_EN.get(sel, '')} · {p['cn']} plant · 工厂</span>"
        f"<span class='eq-plant-feat'>{p['feature']}</span>"
        f"<span class='eq-plant-port'>🚢 {p['port']}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 入围供应商领奖台 ────────────────────────────────────────────
    st.markdown("##### 🏗️ Shortlisted Supplier Ranking · Top-3 (5-dim weighted expert scoring), expandable · 入围供应商排名 · Top3 推荐（5 维加权专家评分），可展开全部明细")
    _render_plant_podium(c, p)

    # ── 性价比象限图 ────────────────────────────────────────────────
    st.markdown("#### 🎯 Value Quadrant · score × delivered price, who's in the 'high-score, low-price' sweet spot · 性价比象限 · 综合评分 × 到厂价")
    _vs = _value_scatter(c, p)
    if _vs is not None:
        st.plotly_chart(_vs, width="stretch", config={"displayModeBar": False},
                        key=f"eq_value_{c['key']}_{p['key']}")
        st.caption("X = est. delivered price (left = cheaper), Y = 5-dim overall score (up = better); the top-left "
                   "green sweet spot = good & cheap. ⭐ = top pick; dashed lines = plant anchor price & group average.  \n"
                   "横轴＝预估到厂价（越左越便宜），纵轴＝5 维综合评分（越上越优）；"
                   "左上绿色甜区＝又好又便宜的理想供应商。⭐为入围首选，虚线为该厂锚定价与本组平均分。")
    else:
        st.info("Fewer than 2 shortlisted suppliers at this plant — value quadrant hidden. · 该工厂入围供应商不足 2 家，暂不展示性价比象限图。")

    # ── 采购价格分析报告 ────────────────────────────────────────────
    st.markdown("---")
    _render_price_report(c, p)

    # ── 评分框架 ────────────────────────────────────────────────────
    with st.expander("📐 Supplier scoring framework: 5-dim weighted expert model (price/lead/local/qual/scale) · 供应商评分框架：5 维加权专家模型（价格/交期/属地/资质/规模）"):
        st.markdown(
            "Equipment suppliers are scored with a **5-dimension weighted expert model**, dimension scores derived "
            "from structured fields and reproducible: **price competitiveness** (delivered price coefficient, lower "
            "is better) 32% · **delivery assurance** (lead time) 22% · **local fulfillment** (local + proximity) "
            "18% · **qualification level** (A1/API Q1/special-equipment A) 16% · **scale & brand** (national/regional/"
            "local) 12%. Change one field and the score recomputes — no manual scoring.  \n"
            "设备类供应商按 **5 维加权专家模型** 评分，维度分由结构化字段派生、可复算："
            "**价格竞争力**（到厂价格系数，越低越优）32% · **交期保障**（交付周期）22% · "
            "**属地履约**（本地+就近距离）18% · **资质等级**（A1/API Q1/特种A级）16% · "
            "**规模品牌**（全国龙头/区域头部/属地厂商）12%。改一个字段即可复现分数，非人工拍分。")


# ═══════════════════════════════════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════════════════════════════════
EQUIPMENT_CSS = """
<style>
.st-key-eq_back{margin-top:2.6rem;}
/* 分区横幅 */
.eq-band{display:flex;align-items:center;gap:14px;margin:6px 0 14px;padding:14px 18px;
  background:linear-gradient(135deg,#0c1a12 0%,#103022 55%,#0a1628 100%);
  border-radius:14px;box-shadow:0 10px 30px -14px rgba(7,17,32,.5);}
.eq-band-bar{width:5px;height:46px;border-radius:4px;background:linear-gradient(#34d399,#0E8C3A);}
.eq-band-title{font-size:18px;font-weight:800;color:#fff;letter-spacing:.3px;}
.eq-band-sub{font-size:12.5px;color:#9fc8b1;margin-top:3px;max-width:1040px;line-height:1.55;}
/* 品类卡 */
.eq-card{position:relative;background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--accent);
  border-radius:14px;padding:15px 16px 12px;box-shadow:0 8px 24px -16px rgba(10,22,40,.45);
  transition:transform .12s ease,box-shadow .12s ease;min-height:236px;}
.eq-card:hover{transform:translateY(-2px);box-shadow:0 14px 30px -16px rgba(10,22,40,.5);}
.eq-card-top{display:flex;align-items:center;justify-content:space-between;}
.eq-ico{font-size:28px;}
.eq-tag{font-size:11px;font-weight:700;color:var(--accent);background:rgba(14,140,58,.06);
  border:1px solid rgba(14,140,58,.18);padding:2px 9px;border-radius:20px;}
.eq-name{font-size:19px;font-weight:800;color:#0a1628;margin:9px 0 1px;}
.eq-en{font-size:11.5px;color:#94a3b8;font-weight:600;letter-spacing:.02em;margin-bottom:5px;}
.eq-spec{font-size:12px;color:#5a6780;line-height:1.5;min-height:34px;}
.eq-price-row{display:flex;gap:10px;margin-top:8px;padding:9px 11px;background:#f7faf8;
  border:1px solid #e8f1ec;border-radius:10px;}
.eq-price-cell{flex:1;}
.eq-price-lbl{font-size:10.5px;color:#7c8aa0;font-weight:600;}
.eq-price-val{font-size:22px;font-weight:800;color:#0a1628;line-height:1.1;}
.eq-price-val span{font-size:12px;color:#9ba8bb;font-weight:600;}
.eq-price-band{font-size:14.5px;font-weight:800;color:#0E8C3A;line-height:1.3;margin-top:3px;}
.eq-card-champ{display:flex;align-items:center;gap:7px;margin-top:9px;padding:7px 10px;
  background:linear-gradient(135deg,#0b1424,#13233d);border-radius:9px;}
.eq-card-champ-lbl{font-size:10.5px;font-weight:700;color:#fcd34d;white-space:nowrap;}
.eq-card-champ-name{font-size:12px;font-weight:700;color:#e2e8f0;flex:1;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
.eq-card-champ-score{font-size:18px;font-weight:800;color:#34d399;line-height:1;}
/* 报告 hero */
.eq-hero{background:linear-gradient(135deg,#071120 0%,#0d2a1d 60%,#0a182c 100%);
  border-radius:16px;padding:22px 26px;margin:8px 0 14px;position:relative;overflow:hidden;
  box-shadow:0 16px 40px -18px rgba(7,17,32,.55);}
.eq-hero::after{content:'';position:absolute;top:-80px;right:-50px;width:300px;height:300px;
  border-radius:50%;background:radial-gradient(circle,var(--accent),transparent 68%);opacity:.25;filter:blur(10px);}
.eq-hero-l{display:flex;align-items:center;gap:16px;position:relative;z-index:1;}
.eq-hero-ico{font-size:44px;line-height:1;}
.eq-hero-kicker{font-size:12.5px;font-weight:700;letter-spacing:.1em;color:#6ee7b7;text-transform:uppercase;}
.eq-hero-title{font-size:32px;font-weight:800;color:#fff;margin:4px 0;}
.eq-hero-tagline{font-size:14.5px;color:#c0cfe0;}
.eq-hero-model{position:relative;z-index:1;margin-top:14px;font-size:14px;color:#d6e0ec;line-height:1.7;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:11px 14px;}
/* 工厂选择头 */
.eq-plant-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:8px 0 10px;
  padding-bottom:7px;border-bottom:2px solid color-mix(in srgb,var(--bcol) 32%,#fff);}
.eq-plant-dot{width:12px;height:12px;border-radius:3px;background:var(--bcol);transform:rotate(45deg);}
.eq-plant-name{font-size:17px;font-weight:800;color:#0a1628;}
.eq-plant-feat{font-size:11.5px;font-weight:700;color:var(--bcol);
  background:color-mix(in srgb,var(--bcol) 10%,#fff);
  border:1px solid color-mix(in srgb,var(--bcol) 24%,#fff);padding:1px 9px;border-radius:20px;}
.eq-plant-port{margin-left:auto;font-size:11.5px;color:#64748b;}
/* 价格 hero */
.eq-pricehero{display:flex;align-items:center;gap:18px;margin:6px 0 14px;padding:20px 24px;
  background:linear-gradient(135deg,#071120 0%,#0d2a1d 60%,#0a182c 100%);border-radius:16px;
  border-left:6px solid var(--bcol);box-shadow:0 16px 40px -18px rgba(7,17,32,.55);flex-wrap:wrap;}
.eq-ph-l{flex:1;min-width:280px;}
.eq-ph-kicker{font-size:12.5px;font-weight:700;letter-spacing:.06em;color:#fcd34d;}
.eq-ph-band{font-size:42px;font-weight:800;color:#fff;line-height:1.15;margin:5px 0 2px;}
.eq-ph-band span{color:#6ee7b7;}
.eq-ph-unit{font-size:16px;color:rgba(255,255,255,.6);font-weight:600;}
.eq-ph-anchor{font-size:13.5px;color:#c0cfe0;}
.eq-ph-anchor b{color:#34d399;}
.eq-ph-r{text-align:center;padding-left:18px;border-left:1px solid rgba(255,255,255,.12);min-width:150px;}
.eq-ph-conf{font-size:48px;font-weight:800;line-height:1;}
.eq-ph-conf span{font-size:20px;}
.eq-ph-conf-lbl{font-size:11px;color:rgba(255,255,255,.5);letter-spacing:.05em;}
.eq-ph-samp{font-size:11px;color:#9fb3c8;margin-top:6px;}
/* 价格推导三步说明 */
.eq-plogic{margin:2px 0 12px;padding:13px 16px;border-radius:12px;
  background:linear-gradient(135deg,#f7faf8,#eef6f1);border:1px solid #dcebe2;}
.eq-plogic-h{font-size:13.5px;font-weight:800;color:#0a1628;margin-bottom:9px;}
.eq-plogic-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;}
.eq-plogic-step{display:flex;gap:9px;align-items:flex-start;background:#fff;border:1px solid #e6ebf2;
  border-radius:10px;padding:9px 11px;font-size:12.5px;color:#1e293b;line-height:1.45;}
.eq-plogic-step b{font-size:12.5px;color:#0a1628;}
.eq-plogic-no{font-size:18px;font-weight:800;color:#0E8C3A;line-height:1.2;flex-shrink:0;}
.eq-plogic-sub{font-size:11px;color:#64748b;}
/* 方法卡 */
.eq-method{background:#fff;border:1px solid #e6ebf2;border-radius:12px;padding:12px 13px;height:100%;
  box-shadow:0 8px 22px -18px rgba(10,22,40,.4);}
.eq-method.adopt{border:1px solid #0E8C3A;background:linear-gradient(180deg,#f3fbf6,#fff);}
.eq-method-name{font-size:12.5px;font-weight:700;color:#1e293b;line-height:1.35;min-height:34px;}
.eq-method-flag{font-size:10px;font-weight:700;color:#fff;background:#0E8C3A;border-radius:8px;
  padding:1px 7px;margin-left:6px;}
.eq-method-price{font-size:26px;font-weight:800;color:#0a1628;margin:4px 0;}
.eq-method-price span{font-size:12px;color:#9ba8bb;font-weight:600;}
.eq-method-note{font-size:11px;color:#64748b;line-height:1.5;}
/* 平台溯源卡 */
.eq-src{background:#fff;border:1px solid #e6ebf2;border-top:3px solid #2563eb;border-radius:12px;
  padding:12px 13px;height:100%;box-shadow:0 8px 22px -18px rgba(10,22,40,.4);}
.eq-src-name{font-size:13.5px;font-weight:800;color:#0a1628;line-height:1.3;}
.eq-src-url{font-size:11px;color:#2563eb;margin:2px 0 6px;}
.eq-src-avg{font-size:25px;font-weight:800;color:#2563eb;line-height:1;}
.eq-src-avg span{font-size:12px;color:#9ba8bb;font-weight:600;}
.eq-src-meta{font-size:11.5px;color:#475569;margin-top:4px;}
.eq-src-period{font-size:11px;color:#94a3b8;margin-top:4px;}
/* Top3 领奖台 */
.eq-pod{background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--bcol);border-radius:13px;
  padding:13px 14px;height:100%;box-shadow:0 8px 24px -18px rgba(10,22,40,.4);}
.eq-pod-top{display:flex;align-items:center;justify-content:space-between;}
.eq-pod-medal{font-size:26px;line-height:1;}
.eq-pod-score{font-size:26px;font-weight:800;line-height:1;}
.eq-pod-name{font-size:14.5px;font-weight:800;color:#0a1628;margin:7px 0 2px;line-height:1.3;}
.eq-pod-type{font-size:11.5px;font-weight:700;color:var(--bcol);margin-bottom:5px;}
.eq-pod-est{font-size:11.5px;color:#475569;line-height:1.5;}
.eq-pod-est b{color:#0E8C3A;}
.eq-pod-note{font-size:12px;color:#5a6780;line-height:1.5;min-height:36px;margin-top:4px;}
.eq-pt-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;}
.eq-pt{font-size:10.5px;font-weight:700;color:var(--bcol);background:color-mix(in srgb,var(--bcol) 9%,#fff);
  border:1px solid color-mix(in srgb,var(--bcol) 22%,#fff);padding:1px 8px;border-radius:20px;}
/* 全部明细 */
.eq-detail{border:1px solid #eef2f7;border-radius:10px;padding:11px 13px;margin-bottom:9px;background:#fcfdfe;}
.eq-detail-h{display:flex;align-items:center;gap:9px;margin-bottom:8px;}
.eq-detail-rank{font-size:18px;}
.eq-detail-name{font-size:14px;font-weight:800;color:#0a1628;flex:1;}
.eq-detail-score{font-size:16px;font-weight:800;}
.eq-dims{display:flex;flex-direction:column;gap:5px;}
.eq-dim{display:flex;align-items:center;gap:9px;}
.eq-dim-l{width:180px;font-size:11px;color:#475569;line-height:1.3;}
.eq-dim-track{flex:1;height:7px;background:#eef2f7;border-radius:4px;overflow:hidden;}
.eq-dim-fill{height:100%;border-radius:4px;}
.eq-dim-v{width:26px;text-align:right;font-size:11.5px;font-weight:700;}
@media (max-width:900px){.eq-hero-title{font-size:26px;}.eq-ph-band{font-size:32px;}
  .eq-pricehero{flex-wrap:wrap;}.eq-ph-r{border-left:none;padding-left:0;}}
</style>
"""
