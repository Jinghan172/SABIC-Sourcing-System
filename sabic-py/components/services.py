# -*- coding: utf-8 -*-
"""
综合服务与属地采购模块 —— SABIC 四大基地间接 / 服务采购导航。

区别于主区（生产性物料的工商评分）与核心物料专家评审：这里覆盖人力、会务、
广告、办公、IT、咨询、通勤、安保、食堂、保险、MRO、实验室等 15 类间接/服务
采购。每个品类按『全国头部平台 + 属地兜底』双轨在四大基地（上海·南沙·古雷·
重庆）落地，用一张交互地图指引采购人员：哪个基地就找哪家首选服务商。

数据：data/services.json（静态缓存名录，可持续维护）。
对外接口：
  load_services()                 -> dict
  render_service_cards()          -> 落地页渲染 15 张品类导航卡 + 分区横幅
  render_service_report(cat_key)  -> 渲染某一品类的四大基地地图导航报告
  get_service(key)                -> dict | None
"""
from __future__ import annotations
import json
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

from utils.services_scorer import (
    rank_suppliers, DIM_KEYS, DIM_CN, DIM_EN, DEFAULT_WEIGHTS, verdict_for,
    explain_supplier, analyze_supplier,
)
from components.comparison import render_comparison, deviation_tornado_figure

# 5 维双语标签（英文在前、中文在后）
DIM_BI = {k: f"{DIM_EN.get(k, k)} · {DIM_CN.get(k, k)}" for k in DIM_KEYS}

_BASE = Path(__file__).resolve().parent.parent / "data"
_DATA_PATH = _BASE / "services.json"
_FONT = dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=14)
_BG = "rgba(0,0,0,0)"
_SABIC_DARK = "#0a1628"

# 四大基地配色（与核心物料地图一致）
_BASE_COLOR = {"SH": "#0E8C3A", "NS": "#2563eb", "GL": "#f59e0b", "CQ": "#a855f7"}


@st.cache_data(show_spinner=False)
def load_services() -> dict:
    try:
        return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"section": {}, "bases": [], "categories": []}


@st.cache_data(show_spinner=False)
def load_service_rates() -> dict:
    try:
        return json.loads((_BASE / "service_rates.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _categories() -> list[dict]:
    return load_services().get("categories", [])


def _bases() -> list[dict]:
    return load_services().get("bases", [])


def get_service(key: str) -> dict | None:
    return next((c for c in _categories() if c["key"] == key), None)


# ── 评分辅助：把每基地的供应商名录按 5 维加权评分排序 ────────────────
def _weights(c: dict) -> dict:
    # 侧栏「服务评分权重」滑块（svc_weights）优先；否则用该品类设计默认权重
    return st.session_state.get("svc_weights") or c.get("weights", DEFAULT_WEIGHTS)


def _ranked(c: dict, base_key: str) -> list[dict]:
    sl = c.get("bases", {}).get(base_key, {}).get("suppliers", [])
    flt = st.session_state.get("svc_filters") or {}
    if flt.get("tiers"):
        sl = [s for s in sl if s.get("tier") in flt["tiers"]]
    if flt.get("primary_only"):
        sl = [s for s in sl if s.get("role") == "primary"]
    return rank_suppliers(sl, _weights(c))


def _base_champions(c: dict) -> list[tuple[dict, dict]]:
    """返回 [(base_meta, 该基地榜首供应商), ...]，按四大基地顺序。"""
    out = []
    for bs in _bases():
        r = _ranked(c, bs["key"])
        if r:
            out.append((bs, r[0]))
    return out


def _strategic_champion(c: dict) -> tuple[dict, dict] | None:
    """四大基地榜首中综合分最高者 —— 跨基地战略首选。"""
    champs = _base_champions(c)
    return max(champs, key=lambda t: t[1]["score"]) if champs else None


def _score_color(v: float) -> str:
    return "#0E8C3A" if v >= 85 else ("#16a34a" if v >= 75 else
                                      ("#f59e0b" if v >= 60 else "#ef4444"))


# ═══════════════════════════════════════════════════════════════════════
# 落地页：15 张品类导航卡
# ═══════════════════════════════════════════════════════════════════════
def render_service_cards() -> None:
    cats = _categories()
    if not cats:
        return
    sec = load_services().get("section", {})

    st.markdown(f"""
<div class="sv-band">
  <div class="sv-band-bar"></div>
  <div>
    <div class="sv-band-title">{sec.get('title', '🏢 Services & Local Procurement · 综合服务与属地采购')}</div>
    <div class="sv-band-sub">{sec.get('sub', '')}</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # 三列网格，逐行铺满
    cols = st.columns(3)
    for i, c in enumerate(cats):
        bcnt = len(c.get("bases", {}))
        scnt = sum(len(b.get("suppliers", [])) for b in c.get("bases", {}).values())
        sc = _strategic_champion(c)
        champ_name = sc[1]["name"] if sc else "—"
        champ_score = f"{sc[1]['score']:.1f}" if sc else "—"
        with cols[i % 3]:
            st.markdown(f"""
<div class="sv-card" style="--accent:{c['accent']}">
  <div class="sv-card-top">
    <span class="sv-ico">{c['icon']}</span>
    <span class="sv-tag">{bcnt} bases · 基地 · {scnt} firms · 家入围</span>
  </div>
  <div class="sv-name">{c['en']}</div>
  <div class="sv-en">{c['cn']}</div>
  <div class="sv-tagline">{c['tagline']}</div>
  <div class="sv-card-champ">
    <span class="sv-card-champ-lbl">🏆 Top pick · 战略首选</span>
    <span class="sv-card-champ-name">{champ_name[:12]}</span>
    <span class="sv-card-champ-score">{champ_score}</span>
  </div>
</div>
""", unsafe_allow_html=True)
            if st.button(f"Enter · 进入 {c['cn']} · 四大基地导航 →", key=f"sv_enter_{c['key']}",
                         width="stretch"):
                st.session_state.service_cat = c["key"]
                st.session_state.query = ""
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 地图：四大基地 + 各基地该品类首选服务商
# ═══════════════════════════════════════════════════════════════════════
def _base_map(c: dict):
    geojson_path = _BASE / "china.json"
    if not geojson_path.exists():
        return None
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))

    fig = go.Figure()
    # 底图（无填充，仅描边）
    fig.add_trace(go.Choropleth(
        geojson=geojson, locations=[], z=[],
        featureidkey="properties.name", showscale=False,
        marker_line_color="white", marker_line_width=0.6,
    ))

    for bs in _bases():
        col = _BASE_COLOR.get(bs["key"], "#0E8C3A")
        ranked = _ranked(c, bs["key"])
        prim = ranked[0] if ranked else {}
        runners = ranked[1:3]
        bk_txt = ("<br>🔁 Backup · 备选：" + "、".join(f"{b['name']}({b['score']:.0f})" for b in runners)) if runners else ""
        hover = (f"<b>SABIC {bs['cn']} base · 基地</b><br>{bs.get('feature','')}<br>"
                 f"🥇 Top pick · 首选：<b>{prim.get('name','—')}</b> · <b>{prim.get('score',0):.1f}</b><br>"
                 f"<span style='color:#9fb3c8'>{prim.get('type','')}</span>{bk_txt}")
        fig.add_trace(go.Scattergeo(
            lat=[bs["lat"]], lon=[bs["lng"]], mode="markers+text",
            marker=dict(size=26, color=col, symbol="diamond",
                        line=dict(color="white", width=2.4), opacity=.95),
            text=[f"◆ {bs['short']} · {prim.get('score',0):.0f}<br>{prim.get('name','')[:10]}"],
            textposition="top center",
            textfont=dict(size=12.5, color=_SABIC_DARK, family="PingFang SC"),
            hovertemplate=f"{hover}<extra></extra>",
            name=f"◆ {bs['short']}", showlegend=True,
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
        font=_FONT, paper_bgcolor=_BG, margin=dict(l=0, r=0, t=8, b=0), height=460,
        legend=dict(orientation="h", x=0, y=-0.04, font=dict(size=12.5),
                    bgcolor="rgba(255,255,255,.85)", bordercolor="#e2e8f0", borderwidth=1),
    )
    return fig


_MEDALS = ["🥇", "🥈", "🥉", "④", "⑤"]


def _dim_bars_html(sup: dict) -> str:
    """单家供应商的 5 维评分横条。"""
    rows = ""
    for k in DIM_KEYS:
        v = sup["dims"][k]
        col = _score_color(v)
        rows += (
            f"<div class='sv-dim'>"
            f"<span class='sv-dim-l'>{DIM_BI[k]}</span>"
            f"<div class='sv-dim-track'><div class='sv-dim-fill' "
            f"style='width:{v:.0f}%;background:{col}'></div></div>"
            f"<span class='sv-dim-v' style='color:{col}'>{v:.0f}</span>"
            f"</div>"
        )
    return rows


def _champion_hero_html(c: dict) -> str:
    """跨四大基地的『战略首选』大字号领奖台卡。"""
    sc = _strategic_champion(c)
    if not sc:
        return ""
    bs, ch = sc
    col = _BASE_COLOR.get(bs["key"], "#0E8C3A")
    chips = "".join(f"<span class='sv-pt' style='--bcol:{col}'>{t}</span>"
                    for t in ch.get("quals", []))
    return (
        f"<div class='sv-champ' style='--bcol:{col}'>"
        f"<div class='sv-champ-medal'>🏆</div>"
        f"<div class='sv-champ-body'>"
        f"<div class='sv-champ-kicker'>Four bases · Strategic top pick (highest overall) · 四大基地 · 战略首选（综合评分最高）</div>"
        f"<div class='sv-champ-name'>{ch['name']}</div>"
        f"<div class='sv-champ-meta'>📍 SABIC {bs['cn']} base · 基地 · {ch.get('type','')} · "
        f"{verdict_for(ch)}</div>"
        f"<div class='sv-champ-note'>{ch.get('note','')}</div>"
        f"<div class='sv-pt-row'>{chips}</div>"
        f"</div>"
        f"<div class='sv-champ-score'><b>{ch['score']:.1f}</b><span>Overall · 综合评分</span></div>"
        f"</div>"
    )


def _base_strip_html(c: dict) -> str:
    """四大基地各自榜首的横向迷你领奖台。"""
    cells = ""
    for bs, ch in _base_champions(c):
        col = _BASE_COLOR.get(bs["key"], "#0E8C3A")
        cells += (
            f"<div class='sv-bc' style='--bcol:{col}'>"
            f"<div class='sv-bc-base'>◆ SABIC {bs['short']}</div>"
            f"<div class='sv-bc-score'>{ch['score']:.1f}</div>"
            f"<div class='sv-bc-name'>🥇 {ch['name']}</div>"
            f"<div class='sv-bc-verdict'>{verdict_for(ch)}</div>"
            f"</div>"
        )
    return f"<div class='sv-bc-row'>{cells}</div>"


def _weight_bars_html(c: dict) -> str:
    w = _weights(c)
    tot = sum(w.values()) or 1
    rows = ""
    for k in DIM_KEYS:
        pct = w.get(k, 0)
        rows += (
            f"<div class='sv-wt'>"
            f"<span class='sv-wt-l'>{DIM_BI[k]}</span>"
            f"<div class='sv-wt-track'><div class='sv-wt-fill' "
            f"style='width:{pct / max(w.values()) * 100:.0f}%'></div></div>"
            f"<span class='sv-wt-v'>{pct}%</span>"
            f"</div>"
        )
    return rows


def _champ_radar(c: dict):
    champs = _base_champions(c)
    if not champs:
        return None
    axes = [f"{DIM_EN.get(k,k)}<br>{DIM_CN[k]}" for k in DIM_KEYS]
    fig = go.Figure()
    for bs, ch in champs:
        col = _BASE_COLOR.get(bs["key"], "#0E8C3A")
        vals = [ch["dims"][k] for k in DIM_KEYS]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=axes + [axes[0]], fill="toself",
            name=f"{bs['short']} · {ch['name'][:8]}（{ch['score']:.0f}）",
            line=dict(color=col, width=2.2), opacity=0.45,
            hovertemplate="%{theta}：%{r:.0f}<extra></extra>",
        ))
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, height=440,
        margin=dict(l=40, r=40, t=30, b=30),
        polar=dict(bgcolor="#fbfdff",
                   radialaxis=dict(range=[40, 100], tickfont=dict(size=10),
                                   gridcolor="#e2e8f0", showline=False),
                   angularaxis=dict(tickfont=dict(size=12.5, color=_SABIC_DARK))),
        legend=dict(orientation="h", x=0, y=-0.12, font=dict(size=12)),
    )
    return fig


def _render_base_podium(c: dict, bs: dict) -> None:
    """单基地：Top3 领奖台 + 展开全部 5 家评分明细。"""
    col = _BASE_COLOR.get(bs["key"], "#0E8C3A")
    ranked = _ranked(c, bs["key"])
    if not ranked:
        return
    st.markdown(
        f"<div class='sv-pod-head' style='--bcol:{col}'>"
        f"<span class='sv-panel-dot'></span>"
        f"<span class='sv-panel-base'>SABIC {bs['cn']}</span>"
        f"<span class='sv-panel-feat'>{bs.get('feature','')}</span>"
        f"<span class='sv-pod-port'>🚢 {bs.get('port','')}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for i, sup in enumerate(ranked[:3]):
        sccol = _score_color(sup["score"])
        chips = "".join(f"<span class='sv-pt' style='--bcol:{col}'>{t}</span>"
                        for t in sup.get("quals", [])[:3])
        badge = ("<span class='sv-pod-rec'>Recommended · 采购推荐</span>"
                 if sup.get("role") == "primary" else "")
        with cols[i]:
            st.markdown(
                f"<div class='sv-pod' style='--bcol:{col}'>"
                f"<div class='sv-pod-top'><span class='sv-pod-medal'>{_MEDALS[i]}</span>"
                f"<span class='sv-pod-score' style='color:{sccol}'>{sup['score']:.1f}</span></div>"
                f"<div class='sv-pod-name'>{sup['name']}{badge}</div>"
                f"<div class='sv-pod-type'>● {sup.get('type','')}</div>"
                f"<div class='sv-pod-note'>{sup.get('note','')}</div>"
                f"<div class='sv-pt-row'>{chips}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    # ── 厂家逐一对比（图示之外的文字版结论）────────────────────────
    render_comparison(
        ranked, DIM_KEYS, DIM_BI, _weights(c), accent=col, key=f"{c['key']}_{bs['key']}",
        title=f"⚖️ SABIC {bs['cn']} · Head-to-Head · 厂家逐一对比 · 为什么是它、别家为什么不是最优",
    )

    with st.expander(f"📋 Expand all {len(ranked)} at SABIC {bs['cn']} · scoring + diligence · 展开全部 · 评分构成 + 逐家利弊尽调"):
        top_ref = ranked[0] if ranked else None
        for sup in ranked:
            ref = (ranked[1] if len(ranked) > 1 else None) if sup["rank"] == 1 else top_ref
            st.markdown(_diligence_compact_html(sup, ref), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# 咨询式尽职分析：把每个分数拆开 + 讲清优势/短板/适用取舍
# ═══════════════════════════════════════════════════════════════════════
def _buildup_html(scored: dict, with_method: bool = False) -> str:
    """5 维评分构成：每维显示『基准 + 各加分项 = 最终分』，让分数可复算。"""
    ex = explain_supplier(scored)
    rows = ""
    for k in DIM_KEYS:
        info = ex[k]
        v = info["score"]
        col = _score_color(v)
        chips = ""
        for i, (lbl, _desc, pts) in enumerate(info["items"]):
            if i == 0:
                chips += f"<span class='sv-bd-base'>{lbl} {pts:g}</span>"
            else:
                chips += f"<span class='sv-bd-add'>＋{lbl} <b>+{pts:g}</b></span>"
        method = f"<div class='sv-bd-method'>📐 {info['method']}</div>" if with_method else ""
        rows += (
            f"<div class='sv-bd'>"
            f"<div class='sv-bd-top'>"
            f"<span class='sv-bd-dim'>{DIM_BI[k]}</span>"
            f"<div class='sv-bd-track'><div class='sv-bd-fill' "
            f"style='width:{v:.0f}%;background:{col}'></div></div>"
            f"<span class='sv-bd-score' style='color:{col}'>{v:.0f}</span>"
            f"</div>"
            f"<div class='sv-bd-formula'>{chips}<span class='sv-bd-eq'>＝ {v:.0f}</span></div>"
            f"{method}"
            f"</div>"
        )
    return rows


def _proscons_html(an: dict) -> str:
    pros = "".join(f"<li>{p}</li>" for p in an["pros"]) or "<li>—</li>"
    cons = "".join(f"<li>{c}</li>" for c in an["cons"]) or "<li>—</li>"
    return (
        f"<div class='sv-sc'>"
        f"<div class='sv-sc-col sv-pros'><div class='sv-sc-h'>✅ Strengths · 核心优势</div><ul>{pros}</ul></div>"
        f"<div class='sv-sc-col sv-cons'><div class='sv-sc-h'>⚠️ Weaknesses & risks · 短板与风险</div><ul>{cons}</ul></div>"
        f"</div>"
    )


def _fit_html(an: dict) -> str:
    good = "".join(f"<span class='sv-fit good'>✔ Fit · 适用 · {x}</span>" for x in an["fit"])
    warn = "".join(f"<span class='sv-fit warn'>✘ Caution · 慎用 · {x}</span>" for x in an["caution"])
    return f"<div class='sv-fit-row'>{good}{warn}</div>"


def _tradeoff_html(champ: dict, runner: dict | None) -> str:
    if not runner:
        return ""
    deltas = [(DIM_BI[k], champ["dims"][k] - runner["dims"][k]) for k in DIM_KEYS]
    ups = sorted([d for d in deltas if d[1] >= 3], key=lambda x: -x[1])[:2]
    downs = sorted([d for d in deltas if d[1] <= -3], key=lambda x: x[1])[:1]
    parts = [f"<span class='sv-td up'>{n} leads · 领先 {dv:.0f}</span>" for n, dv in ups]
    parts += [f"<span class='sv-td down'>{n} behind · 落后 {abs(dv):.0f}</span>" for n, dv in downs]
    body = "".join(parts) if parts else "<span class='sv-td up'>Leads on all dimensions · 各维度全面领先</span>"
    note = ("↳ If this scenario values the lagging dimension more, prefer a backup or split/dual-source to hedge. · "
            "若该场景更看重落后维度，建议优先备选或采取分单/双供策略对冲。"
            if downs else "↳ Leads overall — usable as primary; keep 1 backup to hedge single-point risk & pricing. · "
            "综合领先，可作主供；仍建议保留 1 家备选以对冲单点风险与议价。")
    return (
        f"<div class='sv-tradeoff'>"
        f"<span class='sv-td-lbl'>⚖️ vs runner-up · 相较次选「{runner['name']}」（{runner['score']:.1f}）：</span>{body}"
        f"<div class='sv-td-note'>{note}</div>"
        f"</div>"
    )


def _diligence_full_html(scored: dict, runner: dict | None) -> str:
    """战略首选的完整尽调卡（结论先行 + 评分构成 + 利弊 + 适用 + 取舍）。"""
    an = analyze_supplier(scored)
    return (
        f"<div class='sv-dg'>"
        f"<div class='sv-dg-verdict'>🧭 Procurement call · 采购定调：{an['verdict']}</div>"
        f"<div class='sv-dg-label'>① How the score is computed · 评分如何算出 · 每一分都可复算</div>"
        f"<div class='sv-bd-wrap'>{_buildup_html(scored, with_method=True)}</div>"
        f"<div class='sv-dg-label'>② Pros & cons · 利弊分析</div>"
        f"{_proscons_html(an)}"
        f"<div class='sv-dg-label'>③ Fit & caution scenarios · 适用与慎用场景</div>"
        f"{_fit_html(an)}"
        f"<div class='sv-dg-label'>④ Trade-off vs runner-up · 与次选的取舍</div>"
        f"{_tradeoff_html(scored, runner)}"
        f"</div>"
    )


def _diligence_compact_html(sup: dict, runner: dict | None) -> str:
    """展开明细里每家供应商的紧凑尽调卡。"""
    an = analyze_supplier(sup)
    sccol = _score_color(sup["score"])
    return (
        f"<div class='sv-dgc'>"
        f"<div class='sv-dgc-h'>"
        f"<span class='sv-detail-rank'>{_MEDALS[sup['rank'] - 1]}</span>"
        f"<span class='sv-detail-name'>{sup['name']}</span>"
        f"<span class='sv-detail-score' style='color:{sccol}'>{sup['score']:.1f}</span>"
        f"</div>"
        f"<div class='sv-dgc-verdict'>🧭 {an['verdict']}</div>"
        f"<div class='sv-bd-wrap'>{_buildup_html(sup, with_method=False)}</div>"
        f"{_proscons_html(an)}"
        f"{_fit_html(an)}"
        f"</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# MRO 采购费率分析（多源交叉验证）—— 复用 equipment 价格报告样式 eq-*
# ═══════════════════════════════════════════════════════════════════════
def _fmt_rate(v) -> str:
    if v is None:
        return "—"
    if v < 100:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    if v < 1000:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{v:,.0f}"


def _rate_convergence_fig(ra: dict):
    rows = [(f"{s['short']}（{s['samples']}）", s["low"], s["avg"], s["high"])
            for s in ra["sources"]][::-1]
    fig = go.Figure()
    fig.add_vrect(x0=ra["rec_low"], x1=ra["rec_high"], fillcolor="rgba(124,58,237,.10)", line_width=0)
    fig.add_vline(x=ra["anchor"], line=dict(color="#7c3aed", width=2, dash="dash"))
    for lbl, lo, avg, hi in rows:
        fig.add_trace(go.Scatter(x=[lo, hi], y=[lbl, lbl], mode="lines",
                                 line=dict(color="#7c3aed", width=7), opacity=.35,
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=[avg], y=[lbl], mode="markers",
                                 marker=dict(color="#7c3aed", size=15, line=dict(color="white", width=2)),
                                 hovertemplate=f"{lbl}<br>Range · 区间 {_fmt_rate(lo)}–{_fmt_rate(hi)}<br>"
                                               f"Avg · 均值 <b>{_fmt_rate(avg)}</b><extra></extra>",
                                 showlegend=False))
    fig.update_layout(font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff",
                      height=58 * len(rows) + 90, margin=dict(l=10, r=20, t=20, b=10),
                      xaxis=dict(title=f"Rate · 费率（{ra['unit']}）", gridcolor="#eef2f7", zeroline=False),
                      yaxis=dict(automargin=True))
    return fig


def _rate_trend_fig(ra: dict):
    tr = ra.get("trend", [])
    if not tr:
        return None
    xs = [str(t["year"]) for t in tr]
    ys = [t["rate"] for t in tr]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers+text",
                             line=dict(color="#7c3aed", width=3, shape="spline"),
                             marker=dict(size=11, color="#7c3aed", line=dict(color="white", width=2)),
                             text=[_fmt_rate(y) for y in ys], textposition="top center",
                             textfont=dict(size=12, color=_SABIC_DARK),
                             hovertemplate="%{x} <b>%{y}</b><extra></extra>", showlegend=False))
    fig.update_layout(font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff", height=280,
                      margin=dict(l=10, r=20, t=20, b=10), xaxis=dict(gridcolor="#eef2f7"),
                      yaxis=dict(title=f"Rate · 费率（{ra['unit']}）", gridcolor="#eef2f7"))
    return fig


def _render_rate_report(c: dict, base_key: str) -> None:
    ra = load_service_rates().get(c["key"], {}).get(base_key)
    if not ra:
        st.info("No procurement rate analysis for this service yet. · 该服务暂无采购费率分析数据。")
        return
    bcn = next((b["cn"] for b in _bases() if b["key"] == base_key), base_key)
    conf = ra["confidence"]
    conf_col = "#0E8C3A" if conf >= 85 else ("#16a34a" if conf >= 75 else "#f59e0b")
    st.markdown(
        f"<div class='eq-pricehero' style='--bcol:#7c3aed'>"
        f"<div class='eq-ph-l'><div class='eq-ph-kicker'>💰 {bcn} · {c['cn']} · Suggested rate (multi-source cross-validated) · 建议采购费率（多源交叉验证）</div>"
        f"<div class='eq-ph-band'>{_fmt_rate(ra['rec_low'])} <span>–</span> {_fmt_rate(ra['rec_high'])} "
        f"<span class='eq-ph-unit'>{ra['unit']}</span></div>"
        f"<div class='eq-ph-anchor'>◆ Cross-anchor · 交叉锚定 <b>{_fmt_rate(ra['anchor'])} {ra['unit']}</b> · {ra['desc']}</div></div>"
        f"<div class='eq-ph-r'><div class='eq-ph-conf' style='color:{conf_col}'>{conf}<span>%</span></div>"
        f"<div class='eq-ph-conf-lbl'>Confidence · 验证置信度</div>"
        f"<div class='eq-ph-samp'>{ra['total_samples']} multi-source samples · 条多源样本 · dispersion · 离散度 {ra['dispersion']}%</div></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("##### 🧮 Three rate methods · cross-weighted anchor · 三路费率口径 · 交叉加权锚定")
    mcols = st.columns(len(ra["methods"]))
    for i, m in enumerate(ra["methods"]):
        adopt = "采纳" in m["name"]
        with mcols[i]:
            st.markdown(
                f"<div class='eq-method {'adopt' if adopt else ''}'>"
                f"<div class='eq-method-name'>{m['name'].replace('（采纳）','')}"
                f"{'<span class=eq-method-flag>adopted·采纳</span>' if adopt else ''}</div>"
                f"<div class='eq-method-price'>{_fmt_rate(m['rate'])}<span> {ra['unit']}</span></div>"
                f"<div class='eq-method-note'>{m['note']}</div></div>",
                unsafe_allow_html=True,
            )
    _rtor = deviation_tornado_figure(
        [(m["name"].replace("（采纳）", ""), m["rate"]) for m in ra["methods"]],
        ra["anchor"], value_fmt=_fmt_rate, unit=f" {ra['unit']}",
        dear_color="#7c3aed")
    if _rtor is not None:
        st.markdown("##### 🌪️ Rate sensitivity · deviation from anchor (right=dearer, left=cheaper) · 费率口径敏感性 · 各口径相对锚定费率的偏离")
        st.plotly_chart(_rtor, width="stretch", config={"displayModeBar": False},
                        key=f"sv_rtor_{c['key']}_{base_key}")
        st.caption("Green = below the cross-anchor (cheaper), purple = above (dearer); the gap between the two "
                   "longest bars = the negotiation elasticity, usable as upper/lower anchors in framework pricing.  \n"
                   "绿条＝该口径费率低于交叉锚定（更省），紫条＝高于锚定（更贵）；"
                   "最长两条之差＝费率谈判的弹性空间，可作为框架议价的上下锚点。")

    st.markdown("##### 📊 Rate-range convergence · purple band = suggested range, dashed = cross-anchor · 各口径费率区间收敛")
    st.plotly_chart(_rate_convergence_fig(ra), width="stretch",
                    config={"displayModeBar": False}, key=f"sv_rate_conv_{c['key']}_{base_key}")
    st.markdown("##### 🔎 Rate data provenance · three-source cross-check · 费率数据溯源 · 三源交叉")
    scols = st.columns(len(ra["sources"]))
    for i, s in enumerate(ra["sources"]):
        with scols[i]:
            st.markdown(
                f"<div class='eq-src' style='border-top-color:#7c3aed'>"
                f"<div class='eq-src-name'>{s['name']}</div>"
                f"<div class='eq-src-url' style='color:#7c3aed'>🔗 {s['url']}</div>"
                f"<div class='eq-src-avg' style='color:#7c3aed'>{_fmt_rate(s['avg'])}<span> {ra['unit']}</span></div>"
                f"<div class='eq-src-meta'>Range · 区间 {_fmt_rate(s['low'])}–{_fmt_rate(s['high'])} · <b>{s['samples']}</b> samples · 条</div>"
                f"<div class='eq-src-period'>📅 {s['period']}</div></div>",
                unsafe_allow_html=True,
            )
    tf = _rate_trend_fig(ra)
    if tf is not None:
        st.markdown("##### 📈 2022–2024 rate trend · 费率走势")
        st.plotly_chart(tf, width="stretch", config={"displayModeBar": False},
                        key=f"sv_rate_trend_{c['key']}_{base_key}")
    st.caption(
        f"Methodology: government/public-tender winning rates + industry pay & service-rate reports + company "
        f"historical contract rates, cross-weighted 'gov 40% · industry 35% · historical 25%', adjusted by each "
        f"base city's labor/service cost factor ({ra['cost_factor']}). Tax-inclusive composite — for budgeting & "
        f"negotiation reference only.  \n"
        f"方法论：政府采购/公共资源交易中标费率 + 行业薪酬与服务费率报告 + 企业历史合同费率，"
        f"按『政采 40% · 行业 35% · 历史 25%』交叉加权；并随基地城市人力/服务成本系数"
        f"（{ra['cost_factor']}）独立调整。费率为含税综合口径，仅供采购预算与议价参考。")


# ═══════════════════════════════════════════════════════════════════════
# 品类报告：四大基地地图导航
# ═══════════════════════════════════════════════════════════════════════
def render_service_report(cat_key: str) -> None:
    c = get_service(cat_key)
    if not c:
        st.error("Service category data not found. · 未找到该服务品类数据。")
        return

    if st.button("← Back to Services & Local Procurement / all categories · 返回综合服务与属地采购 / 全部品类", key="sv_back"):
        st.session_state.service_cat = None
        st.rerun()

    # ── 头部 ────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="sv-hero" style="--accent:{c['accent']}">
  <div class="sv-hero-l">
    <div class="sv-hero-ico">{c['icon']}</div>
    <div>
      <div class="sv-hero-kicker">🏢 Services & Local Procurement · Four-Base Navigation · 综合服务与属地采购 · 四大基地导航</div>
      <div class="sv-hero-title">{c['en']}</div>
      <div class="sv-hero-title" style="font-size:20px;color:#c0cfe0;font-weight:700;margin-top:0">{c['cn']}</div>
      <div class="sv-hero-tagline">{c['tagline']}</div>
    </div>
  </div>
  <div class="sv-hero-model">🧭 Procurement model · 采购模式：{c['model']}</div>
</div>
""", unsafe_allow_html=True)

    # ── 合规红线条 ──────────────────────────────────────────────────
    chips = "".join(f"<span class='sv-cmp-chip'>✔ {x}</span>" for x in c.get("compliance", []))
    st.markdown(
        f"<div class='sv-redline'>"
        f"<div class='sv-redline-h'>⛔ Entry red lines · 准入红线</div>"
        f"<div class='sv-redline-body'>{c.get('redline','')}</div>"
        f"<div class='sv-cmp-row'>{chips}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 🏆 战略首选领奖台 ───────────────────────────────────────────
    st.markdown(_champion_hero_html(c), unsafe_allow_html=True)
    st.markdown("#### 🥇 Four-Base Top Picks · Overall Score Comparison · 四大基地首选 · 综合评分对比")
    st.markdown(_base_strip_html(c), unsafe_allow_html=True)

    # ── 📑 战略首选尽调分析（咨询式）────────────────────────────────
    sc = _strategic_champion(c)
    if sc:
        bs_c, ch = sc
        ranked_c = _ranked(c, bs_c["key"])
        runner_c = ranked_c[1] if len(ranked_c) > 1 else None
        st.markdown("#### 📑 Strategic Top Pick · Due Diligence & Trade-offs · 战略首选 · 尽职分析与利弊取舍")
        st.markdown(
            f"<div class='sv-dg-head'>Subject · 分析对象：<b>{ch['name']}</b> &nbsp;·&nbsp; "
            f"SABIC {bs_c['cn']} base top pick · 基地首选 &nbsp;·&nbsp; overall · 综合 <b>{ch['score']:.1f}</b> &nbsp;·&nbsp; "
            f"{ch.get('type','')}　<span class='sv-dg-tag'>Reproducible scoring · auditable · 评分可复算 · 利弊可审计</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(_diligence_full_html(ch, runner_c), unsafe_allow_html=True)

    # ── 地图导航 ────────────────────────────────────────────────────
    st.markdown("#### 🗺️ Four-Base Service Navigation · pick a base, find its top pick · 四大基地服务商导航 · 哪个基地就找哪家首选，一图直达")
    _map = _base_map(c)
    if _map is not None:
        st.plotly_chart(_map, width="stretch",
                        config={"displayModeBar": False, "scrollZoom": True},
                        key=f"sv_map_{c['key']}")
        st.caption("◆ Diamonds = SABIC four bases: Shanghai (green) · Guangzhou Nansha (blue) · Fujian Gulei (orange) · "
                   "Chongqing (purple). Labels show each base's top service provider score; hover for "
                   "'top pick + backups + base feature'; scroll to zoom/drag.  \n"
                   "◆ 菱形为 SABIC 四大基地：上海(绿) · 广州南沙(蓝) · 福建漳州古雷(橙) · 重庆(紫) —— "
                   "标注显示各基地该品类首选服务商综合分；鼠标悬停看『首选 + 备选 + 基地特征』，可滚轮缩放拖拽。")
    else:
        st.info("china.json base map missing — skipping map navigation. · china.json 地图底图缺失，跳过地图导航。")

    # ── 📊 四大基地首选雷达对比 ─────────────────────────────────────
    st.markdown("#### 📊 Four-Base Top Picks · 5-Dimension Radar · 四大基地首选 · 5 维能力雷达对比")
    radar = _champ_radar(c)
    if radar is not None:
        st.plotly_chart(radar, width="stretch",
                        config={"displayModeBar": False}, key=f"sv_radar_{c['key']}")
        st.caption("Five dimensions: qualification & compliance / petrochemical fit / local fulfillment / "
                   "scale & brand backing / service assurance — the more each base's top pick extends outward, the stronger.  \n"
                   "五维：资质合规达标 / 石化行业适配 / 属地履约响应 / 规模与品牌背书 / 服务保障与兜底，"
                   "各基地首选越外扩越强。")

    # ── 📐 评分框架 ─────────────────────────────────────────────────
    with st.expander("📐 Scoring framework: 5-dim weighted expert model (category-specific) · 评分框架：5 维加权专家模型（本品类专属权重）", expanded=False):
        st.markdown(
            "Service suppliers have no QCC quantitative business fields (registered capital / hazmat license), "
            "so a **5-dimension weighted expert model** is used: each supplier's dimension scores derive from "
            "structured tags (scale tier / ownership / industry experience / certifications / local-fulfillment "
            "flags / primary role) — transparent, explainable, auditable.  \n"
            "服务类供应商无企查查工商量化字段（注册资本/危化品许可），故采用 **5 维加权"
            "专家模型**：每家供应商的维度分由其结构化标签（规模圈层 / 企业性质 / 行业经验 / "
            "资质认证 / 属地履约旗标 / 首选角色）派生，公式透明、可解释、可审计。"
        )
        st.markdown(
            f"<div class='sv-wt-wrap'>{_weight_bars_html(c)}</div>",
            unsafe_allow_html=True,
        )

    # ── 🏭 选交付基地 → 该基地服务商领奖台 + 采购费率分析 ──────────
    st.markdown("#### 🏭 Pick a Delivery Base · supplier ranking & rate analysis · 选择交付基地 · 查看该基地服务商排名与采购费率分析报告")
    _bkeys = [b["key"] for b in _bases()]
    if st.session_state.get("svc_plant") not in _bkeys:
        st.session_state.svc_plant = _bkeys[0]
    st.radio(
        "Delivery base · 交付基地", _bkeys,
        format_func=lambda k: next((f"{b['cn']} · {b.get('feature','')}"
                                    for b in _bases() if b["key"] == k), k),
        horizontal=True, label_visibility="collapsed", key="svc_plant",
    )
    _sel = st.session_state.svc_plant
    _bs = next(b for b in _bases() if b["key"] == _sel)
    _render_base_podium(c, _bs)

    st.markdown("---")
    _render_rate_report(c, _sel)

    # ── 采购建议 ────────────────────────────────────────────────────
    tips = c.get("tips", [])
    if tips:
        st.markdown("#### 🧾 Procurement Notes & Compliance Tips · 采购要点与合规提示")
        st.markdown(
            "<div class='sv-tips'>"
            + "".join(f"<div class='sv-tip'>＋ {t}</div>" for t in tips)
            + "</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════════════════════════════════
SERVICES_CSS = """
<style>
.st-key-sv_back{margin-top:2.6rem;}
/* 分区横幅 */
.sv-band{display:flex;align-items:center;gap:14px;margin:6px 0 14px;padding:14px 18px;
  background:linear-gradient(135deg,#0b1424 0%,#10233f 55%,#0a1628 100%);
  border-radius:14px;box-shadow:0 10px 30px -14px rgba(7,17,32,.5);}
.sv-band-bar{width:5px;height:46px;border-radius:4px;background:linear-gradient(#60a5fa,#2563eb);}
.sv-band-title{font-size:18px;font-weight:800;color:#fff;letter-spacing:.3px;}
.sv-band-sub{font-size:12.5px;color:#9fb3c8;margin-top:3px;max-width:1040px;line-height:1.55;}
/* 品类卡 */
.sv-card{position:relative;background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--accent);
  border-radius:14px;padding:15px 16px 12px;box-shadow:0 8px 24px -16px rgba(10,22,40,.45);
  transition:transform .12s ease,box-shadow .12s ease;min-height:188px;}
.sv-card:hover{transform:translateY(-2px);box-shadow:0 14px 30px -16px rgba(10,22,40,.5);}
.sv-card-top{display:flex;align-items:center;justify-content:space-between;}
.sv-ico{font-size:28px;}
.sv-tag{font-size:11px;font-weight:700;color:var(--accent);background:rgba(37,99,235,.06);
  border:1px solid rgba(37,99,235,.18);padding:2px 9px;border-radius:20px;}
.sv-name{font-size:19px;font-weight:800;color:#0a1628;margin:9px 0 1px;}
.sv-en{font-size:11.5px;color:#94a3b8;font-weight:600;letter-spacing:.02em;margin-bottom:5px;}
.sv-tagline{font-size:12.5px;color:#5a6780;line-height:1.5;min-height:36px;}
.sv-model{font-size:11.5px;color:var(--accent);font-weight:700;background:rgba(37,99,235,.05);
  border-radius:8px;padding:6px 9px;margin-top:6px;line-height:1.45;}
/* 报告 hero */
.sv-hero{background:linear-gradient(135deg,#071120 0%,#0d1d36 60%,#0a182c 100%);
  border-radius:16px;padding:22px 26px;margin:8px 0 14px;position:relative;overflow:hidden;
  box-shadow:0 16px 40px -18px rgba(7,17,32,.55);}
.sv-hero::after{content:'';position:absolute;top:-80px;right:-50px;width:300px;height:300px;
  border-radius:50%;background:radial-gradient(circle,var(--accent),transparent 68%);opacity:.25;filter:blur(10px);}
.sv-hero-l{display:flex;align-items:center;gap:16px;position:relative;z-index:1;}
.sv-hero-ico{font-size:44px;line-height:1;}
.sv-hero-kicker{font-size:12.5px;font-weight:700;letter-spacing:.12em;color:#7dd3fc;text-transform:uppercase;}
.sv-hero-title{font-size:32px;font-weight:800;color:#fff;margin:4px 0;}
.sv-hero-tagline{font-size:15px;color:#c0cfe0;}
.sv-hero-model{position:relative;z-index:1;margin-top:14px;font-size:14.5px;color:#d6e0ec;line-height:1.7;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:11px 14px;}
/* 红线条 */
.sv-redline{background:#fff7f7;border:1px solid #fbd5d5;border-left:5px solid #dc2626;
  border-radius:12px;padding:13px 18px;margin:6px 0 16px;}
.sv-redline-h{font-size:15px;font-weight:800;color:#b91c1c;margin-bottom:5px;}
.sv-redline-body{font-size:14px;color:#7f1d1d;line-height:1.7;}
.sv-cmp-row{display:flex;flex-wrap:wrap;gap:7px;margin-top:9px;}
.sv-cmp-chip{font-size:12px;font-weight:700;color:#0E8C3A;background:rgba(14,140,58,.08);
  border:1px solid rgba(14,140,58,.2);padding:2px 10px;border-radius:20px;}
/* 基地面板 */
.sv-panel{background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--bcol);
  border-radius:14px;padding:14px 16px;margin-bottom:14px;height:100%;
  box-shadow:0 8px 24px -18px rgba(10,22,40,.4);}
.sv-panel-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;}
.sv-panel-dot{width:11px;height:11px;border-radius:3px;background:var(--bcol);transform:rotate(45deg);}
.sv-panel-base{font-size:16px;font-weight:800;color:#0a1628;}
.sv-panel-feat{font-size:11.5px;font-weight:700;color:var(--bcol);background:color-mix(in srgb,var(--bcol) 10%,#fff);
  border:1px solid color-mix(in srgb,var(--bcol) 24%,#fff);padding:1px 9px;border-radius:20px;}
.sv-prim{display:flex;gap:10px;align-items:flex-start;background:#f8fafc;border:1px solid #eef2f7;
  border-radius:11px;padding:11px 12px;}
.sv-prim-medal{font-size:22px;line-height:1;}
.sv-prim-name{font-size:15.5px;font-weight:800;color:#0a1628;line-height:1.3;}
.sv-prim-type{font-size:12px;font-weight:700;color:var(--bcol);margin:3px 0 5px;}
.sv-prim-note{font-size:12.8px;color:#3a4a5f;line-height:1.6;}
.sv-pt-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;}
.sv-pt{font-size:10.5px;font-weight:700;color:var(--bcol);background:color-mix(in srgb,var(--bcol) 9%,#fff);
  border:1px solid color-mix(in srgb,var(--bcol) 22%,#fff);padding:1px 8px;border-radius:20px;}
.sv-bk-wrap{margin-top:9px;display:flex;flex-direction:column;gap:5px;}
.sv-bk{font-size:12.3px;color:#475569;line-height:1.55;background:#fcfdfe;border:1px dashed #e2e8f0;
  border-radius:8px;padding:6px 9px;}
.sv-bk b{color:#1e293b;}
.sv-port{font-size:11.5px;color:#64748b;margin-top:9px;padding-top:8px;border-top:1px dashed #eef1f5;}
/* 采购要点 */
.sv-tips{display:flex;flex-direction:column;gap:7px;margin:4px 0 18px;}
.sv-tip{font-size:14px;color:#15603a;line-height:1.7;background:#f6faf7;border:1px solid #e1efe6;
  border-radius:9px;padding:9px 13px;}
/* 品类卡·战略首选角标 */
.sv-card-champ{display:flex;align-items:center;gap:7px;margin-top:9px;padding:7px 10px;
  background:linear-gradient(135deg,#0b1424,#13233d);border-radius:9px;}
.sv-card-champ-lbl{font-size:10.5px;font-weight:700;color:#fcd34d;white-space:nowrap;}
.sv-card-champ-name{font-size:12px;font-weight:700;color:#e2e8f0;flex:1;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
.sv-card-champ-score{font-size:18px;font-weight:800;color:#34d399;line-height:1;}
/* 战略首选领奖台 */
.sv-champ{display:flex;align-items:center;gap:18px;margin:14px 0 6px;padding:18px 22px;
  background:linear-gradient(135deg,#071120 0%,#0d1d36 60%,#0a182c 100%);border-radius:16px;
  border-left:6px solid var(--bcol);box-shadow:0 16px 40px -18px rgba(7,17,32,.55);}
.sv-champ-medal{font-size:52px;line-height:1;}
.sv-champ-body{flex:1;}
.sv-champ-kicker{font-size:12px;font-weight:700;letter-spacing:.1em;color:#fcd34d;text-transform:uppercase;}
.sv-champ-name{font-size:27px;font-weight:800;color:#fff;margin:3px 0;line-height:1.2;}
.sv-champ-meta{font-size:13px;color:#9fb3c8;margin-bottom:4px;}
.sv-champ-note{font-size:12.5px;color:#c0cfe0;line-height:1.55;margin-bottom:6px;}
.sv-champ-score{text-align:center;padding-left:14px;border-left:1px solid rgba(255,255,255,.12);}
.sv-champ-score b{display:block;font-size:46px;font-weight:800;color:#34d399;line-height:1;}
.sv-champ-score span{font-size:11px;color:rgba(255,255,255,.5);letter-spacing:.05em;}
/* 四大基地榜首迷你领奖台 */
.sv-bc-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:4px 0 12px;}
.sv-bc{background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--bcol);border-radius:12px;
  padding:12px 13px;box-shadow:0 8px 22px -16px rgba(10,22,40,.4);}
.sv-bc-base{font-size:12px;font-weight:800;color:var(--bcol);}
.sv-bc-score{font-size:32px;font-weight:800;color:#0a1628;line-height:1.05;margin:2px 0;}
.sv-bc-name{font-size:12.5px;font-weight:700;color:#1e293b;line-height:1.35;min-height:34px;}
.sv-bc-verdict{font-size:11px;color:#64748b;margin-top:4px;}
/* 权重条 */
.sv-wt-wrap{margin-top:10px;display:flex;flex-direction:column;gap:7px;}
.sv-wt{display:flex;align-items:center;gap:10px;}
.sv-wt-l{width:200px;font-size:12px;color:#334155;font-weight:600;line-height:1.3;}
.sv-wt-track{flex:1;height:9px;background:#eef2f7;border-radius:5px;overflow:hidden;}
.sv-wt-fill{height:100%;background:linear-gradient(90deg,#60a5fa,#2563eb);border-radius:5px;}
.sv-wt-v{width:38px;text-align:right;font-size:12.5px;font-weight:700;color:#2563eb;}
/* 基地领奖台头 */
.sv-pod-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:16px 0 9px;
  padding-bottom:7px;border-bottom:2px solid color-mix(in srgb,var(--bcol) 30%,#fff);}
.sv-pod-port{margin-left:auto;font-size:11.5px;color:#64748b;}
/* Top3 领奖台卡 */
.sv-pod{background:#fff;border:1px solid #e6ebf2;border-top:4px solid var(--bcol);border-radius:13px;
  padding:13px 14px;height:100%;box-shadow:0 8px 24px -18px rgba(10,22,40,.4);}
.sv-pod-top{display:flex;align-items:center;justify-content:space-between;}
.sv-pod-medal{font-size:26px;line-height:1;}
.sv-pod-score{font-size:26px;font-weight:800;line-height:1;}
.sv-pod-name{font-size:14.5px;font-weight:800;color:#0a1628;margin:7px 0 2px;line-height:1.3;}
.sv-pod-rec{font-size:10px;font-weight:700;color:#fff;background:var(--bcol);border-radius:10px;
  padding:1px 7px;margin-left:6px;white-space:nowrap;}
.sv-pod-type{font-size:11.5px;font-weight:700;color:var(--bcol);margin-bottom:5px;}
.sv-pod-note{font-size:12px;color:#475569;line-height:1.55;min-height:54px;}
/* 全部明细 */
.sv-detail{border:1px solid #eef2f7;border-radius:10px;padding:11px 13px;margin-bottom:9px;background:#fcfdfe;}
.sv-detail-h{display:flex;align-items:center;gap:9px;margin-bottom:8px;}
.sv-detail-rank{font-size:18px;}
.sv-detail-name{font-size:14px;font-weight:800;color:#0a1628;flex:1;}
.sv-detail-score{font-size:16px;font-weight:800;}
.sv-dims{display:flex;flex-direction:column;gap:5px;}
.sv-dim{display:flex;align-items:center;gap:9px;}
.sv-dim-l{width:180px;font-size:11px;color:#475569;line-height:1.3;}
.sv-dim-track{flex:1;height:7px;background:#eef2f7;border-radius:4px;overflow:hidden;}
.sv-dim-fill{height:100%;border-radius:4px;}
.sv-dim-v{width:26px;text-align:right;font-size:11.5px;font-weight:700;}
/* 资质 chip 用基地色 */
.sv-pt{--bcol:#2563eb;}

/* ── 咨询式尽调分析 ─────────────────────────────────────── */
.sv-dg-head{font-size:13.5px;color:#334155;margin:2px 0 8px;}
.sv-dg-head b{color:#0a1628;}
.sv-dg-tag{font-size:11px;font-weight:700;color:#0E8C3A;background:rgba(14,140,58,.08);
  border:1px solid rgba(14,140,58,.22);padding:1px 9px;border-radius:20px;margin-left:6px;}
.sv-dg{background:#fff;border:1px solid #e6ebf2;border-radius:14px;padding:16px 18px;margin-bottom:16px;
  box-shadow:0 10px 30px -18px rgba(10,22,40,.45);}
.sv-dg-verdict{font-size:15px;font-weight:800;color:#0a1628;line-height:1.6;
  background:linear-gradient(135deg,#f3fbf6,#eefaf3);border:1px solid #cfeede;border-left:5px solid #0E8C3A;
  border-radius:10px;padding:11px 14px;margin-bottom:14px;}
.sv-dg-label{font-size:13px;font-weight:800;color:#0E8C3A;letter-spacing:.02em;margin:14px 0 8px;
  padding-bottom:5px;border-bottom:1px dashed #e2e8f0;}
.sv-dgc .sv-dg-label{margin:10px 0 6px;}
/* 评分构成 */
.sv-bd-wrap{display:flex;flex-direction:column;gap:11px;margin-bottom:4px;}
.sv-bd{background:#fbfdff;border:1px solid #eef2f7;border-radius:10px;padding:9px 12px;}
.sv-bd-top{display:flex;align-items:center;gap:10px;}
.sv-bd-dim{width:200px;font-size:12px;font-weight:700;color:#1e293b;flex-shrink:0;line-height:1.3;}
.sv-bd-track{flex:1;height:8px;background:#eef2f7;border-radius:5px;overflow:hidden;}
.sv-bd-fill{height:100%;border-radius:5px;}
.sv-bd-score{width:34px;text-align:right;font-size:16px;font-weight:800;}
.sv-bd-formula{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:7px 0 0 0;padding-left:2px;}
.sv-bd-base{font-size:11.5px;font-weight:700;color:#475569;background:#eef2f7;border-radius:6px;padding:2px 8px;}
.sv-bd-add{font-size:11.5px;color:#0E8C3A;background:rgba(14,140,58,.07);border:1px solid rgba(14,140,58,.18);
  border-radius:6px;padding:2px 8px;}
.sv-bd-add b{font-weight:800;}
.sv-bd-eq{font-size:11.5px;font-weight:800;color:#0a1628;margin-left:2px;}
.sv-bd-method{font-size:11px;color:#94a3b8;margin-top:6px;line-height:1.5;}
/* 利弊两栏 */
.sv-sc{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:6px 0 2px;}
.sv-sc-col{border-radius:11px;padding:11px 13px;border:1px solid;}
.sv-sc-col ul{margin:6px 0 0;padding-left:18px;}
.sv-sc-col li{font-size:12.8px;line-height:1.65;margin-bottom:5px;}
.sv-sc-h{font-size:13px;font-weight:800;}
.sv-pros{background:#f4fbf7;border-color:#cfeede;}
.sv-pros .sv-sc-h{color:#15803d;} .sv-pros li{color:#216a44;}
.sv-cons{background:#fffaf3;border-color:#fbe2c0;}
.sv-cons .sv-sc-h{color:#b45309;} .sv-cons li{color:#92600e;}
/* 适用 / 慎用 */
.sv-fit-row{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0 2px;}
.sv-fit{font-size:12px;font-weight:600;padding:4px 11px;border-radius:8px;line-height:1.45;}
.sv-fit.good{color:#15603a;background:#eef9f2;border:1px solid #cfeede;}
.sv-fit.warn{color:#9a3412;background:#fef3ec;border:1px solid #fbd9bf;}
/* 取舍 */
.sv-tradeoff{margin-top:10px;background:#f8fafc;border:1px solid #e8eef5;border-radius:11px;padding:11px 13px;}
.sv-td-lbl{font-size:12.8px;font-weight:700;color:#334155;margin-right:6px;}
.sv-td{display:inline-block;font-size:11.5px;font-weight:700;border-radius:20px;padding:2px 10px;margin:3px 5px 0 0;}
.sv-td.up{color:#15803d;background:rgba(14,140,58,.1);border:1px solid rgba(14,140,58,.22);}
.sv-td.down{color:#b45309;background:rgba(217,119,6,.1);border:1px solid rgba(217,119,6,.25);}
.sv-td-note{font-size:11.5px;color:#64748b;margin-top:7px;line-height:1.55;}
/* 紧凑尽调卡（展开明细）*/
.sv-dgc{border:1px solid #e6ebf2;border-radius:12px;padding:13px 15px;margin-bottom:12px;background:#fff;}
.sv-dgc-h{display:flex;align-items:center;gap:9px;margin-bottom:7px;}
.sv-dgc-verdict{font-size:12.5px;font-weight:700;color:#0a1628;background:#f3fbf6;border:1px solid #d6efe0;
  border-radius:8px;padding:7px 11px;margin-bottom:10px;line-height:1.5;}

@media (max-width:900px){.sv-hero-title{font-size:26px;}.sv-bc-row{grid-template-columns:repeat(2,1fr);}
  .sv-champ{flex-wrap:wrap;}.sv-sc{grid-template-columns:1fr;}.sv-bd-dim{width:96px;}}
</style>
"""
