# -*- coding: utf-8 -*-
"""
厂家逐一对比模块 —— 图示之外的「文字版」对比，三类报告通用。

核心物料 / 综合服务 / 化工设备三份报告都以图表 + 领奖台为主，本模块补一段
纯文字的 head-to-head 对比，把抽象的综合分翻译成采购能直接读的结论：
  · 最优解凭什么是它（领先在哪几维、领先次席多少分）；
  · 每一家具体的评分依据（最拿得出手的维度）；
  · 别家为什么不是最优（核心短板维度 + 加权拖累多少分），
    以及它在哪个场景下反而能反超（某一维全场最高）。

纯函数 + 一个渲染入口，无外部依赖；输入是任意已带 `score` / `dims` 的供应商
列表（核心物料 6 维、服务 5 维、设备 5 维都适用），维度键与中文名由调用方传入。

对外接口：
  build_comparison(companies, dim_keys, dim_cn, weights) -> dict | None
  render_comparison(...)  -> 在当前位置渲染整段文字对比
  COMPARISON_CSS          -> 样式（在 app.py 注入一次）
"""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

_FONT = dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=14)
_BG = "rgba(0,0,0,0)"


def _normalize_weights(weights: dict, dim_keys: list[str]) -> dict:
    """权重可为百分数（合计~100）或小数（合计~1），统一归一化为小数。"""
    w = {k: float((weights or {}).get(k, 0)) for k in dim_keys}
    s = sum(w.values()) or 1.0
    return {k: w[k] / s for k in dim_keys}


def build_comparison(companies: list[dict], dim_keys: list[str],
                     dim_cn: dict, weights: dict) -> dict | None:
    """把一组已评分供应商压成结构化的逐家对比结论。companies 内每项需含
    `name` / `score` / `dims`（dims 为 {dim_key: 0-100}）。"""
    ranked = sorted([c for c in (companies or []) if c.get("dims")],
                    key=lambda c: -c.get("score", 0))
    if not ranked:
        return None

    w = _normalize_weights(weights, dim_keys)
    champ = ranked[0]
    cd = champ.get("dims", {})
    runner = ranked[1] if len(ranked) > 1 else None
    # 各维度全场最高值（用于判定「某家在该维是全场最强」）
    dim_max = {k: max(c.get("dims", {}).get(k, 0) for c in ranked) for k in dim_keys}

    def _leads(c: dict) -> list[str]:
        """该家在哪些维度上是全场最高（含并列），按权重降序。"""
        d = c.get("dims", {})
        ls = [k for k in dim_keys if d.get(k, 0) >= dim_max[k] - 1e-6]
        return sorted(ls, key=lambda k: -w[k])

    rows = []
    for i, c in enumerate(ranked):
        d = c.get("dims", {})
        leads = _leads(c)
        if i == 0:
            # 最优解：每个领先维度领先次席多少分
            lead_details = []
            for k in leads:
                margin = (d.get(k, 0) - runner.get("dims", {}).get(k, 0)) if runner else 0
                lead_details.append({"k": k, "v": d.get(k, 0), "margin": round(margin, 1)})
            rows.append({
                "is_champ": True, "rank": 1,
                "name": c.get("name"), "score": c.get("score"),
                "type": c.get("type", ""), "leads": lead_details,
                "n_first": len(leads), "n_dim": len(dim_keys),
            })
        else:
            gaps = []
            for k in dim_keys:
                raw = round(d.get(k, 0) - cd.get(k, 0), 1)   # <0 = 落后最优解
                gaps.append({"k": k, "raw": raw, "weighted": round(raw * w[k], 1),
                             "a": d.get(k, 0), "t": cd.get(k, 0)})
            losses = sorted([g for g in gaps if g["raw"] < -0.5],
                            key=lambda g: g["weighted"])
            rows.append({
                "is_champ": False, "rank": i + 1,
                "name": c.get("name"), "score": c.get("score"),
                "type": c.get("type", ""),
                "total_gap": round(c.get("score", 0) - champ.get("score", 0), 1),
                "losses": losses, "scenarios": leads,   # leads = 全场最强的维度
            })
    return {"rows": rows, "champ_name": champ.get("name"), "dim_cn": dim_cn}


# ═══════════════════════════════════════════════════════════════════════
# 差距归因「龙卷风」图：把最优解对次席的综合分领先，按维度拆成加权贡献
# ═══════════════════════════════════════════════════════════════════════
def tornado_figure(companies: list[dict], dim_keys: list[str], dim_cn: dict,
                   weights: dict, accent: str = "#0E8C3A"):
    """最优解（榜首）vs 次席（第二名）逐维加权差异的发散条形图（龙卷风）。
    每条 = (首选该维分 − 次席该维分) × 归一化权重，单位＝综合分；绿色为首选
    在该维领先、橙色为反被次席反超。按绝对值排序 → 上宽下窄的龙卷风形。
    各条加总恰等于两者综合分差。返回 (fig, 首选, 次席, 综合分差) 或 None。"""
    ranked = sorted([c for c in (companies or []) if c.get("dims")],
                    key=lambda c: -c.get("score", 0))
    if len(ranked) < 2:
        return None
    w = _normalize_weights(weights, dim_keys)
    champ, runner = ranked[0], ranked[1]
    cd, rd = champ.get("dims", {}), runner.get("dims", {})
    contribs = [(k, round((cd.get(k, 0) - rd.get(k, 0)) * w[k], 2)) for k in dim_keys]
    # 升序按绝对值排 → plotly 先画的落在底部，最大者落顶部，形成龙卷风
    contribs.sort(key=lambda x: abs(x[1]))
    labels = [dim_cn.get(k, k) for k, _ in contribs]
    vals = [v for _, v in contribs]
    colors = [accent if v >= 0 else "#f59e0b" for v in vals]
    texts = [f"{'＋' if v >= 0 else '－'}{abs(v):.1f}" for v in vals]

    fig = go.Figure(go.Bar(
        y=labels, x=vals, orientation="h",
        marker=dict(color=colors, line=dict(color="white", width=1.2)),
        text=texts, textposition="outside", textfont=dict(size=12.5),
        cliponaxis=False,
        hovertemplate="%{y}<br>Contribution to score gap · 对综合分差的贡献 %{x:.2f}<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color="#94a3b8", width=1.4))
    # 头条领先分＝各条加总（加权维度差），保证「条形之和＝标注数字」自洽。
    # 服务/设备评分即维度加权均值，与综合分差完全相等；核心物料含专项加分，
    # 二者相差不超过约 1 分，故标注口径统一取维度加权差。
    total = round(sum(vals), 1)
    amax = max((abs(v) for v in vals), default=1) or 1
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff",
        height=58 * len(vals) + 70, margin=dict(l=10, r=40, t=12, b=24),
        xaxis=dict(title="Weighted contribution to score gap · 对综合分差的加权贡献", gridcolor="#eef2f7",
                   zeroline=False, range=[-amax * 1.35, amax * 1.35]),
        yaxis=dict(automargin=True),
    )
    return fig, champ, runner, total


# ═══════════════════════════════════════════════════════════════════════
# 定价口径敏感性龙卷风：各价格/费率口径相对交叉锚定价的偏离
# ═══════════════════════════════════════════════════════════════════════
def deviation_tornado_figure(items: list[tuple], anchor: float, *, value_fmt,
                             unit: str = "", cheap_color: str = "#0E8C3A",
                             dear_color: str = "#f59e0b"):
    """各定价口径相对锚定价的偏离发散条形图（价格敏感性龙卷风）。
    items＝[(口径名, 该口径定价), …]，anchor＝交叉锚定价；条 = 口径价 − 锚定价，
    绿色＝低于锚定（更省），橙色＝高于锚定（更贵）。按偏离绝对值排序成龙卷风形，
    一眼看清「最高口径 vs 最低口径」的议价弹性空间。value_fmt 为金额格式化函数。"""
    pts = [(str(l), float(v)) for l, v in (items or []) if v is not None]
    if not pts or anchor is None:
        return None
    devs = sorted([(l, round(v - anchor, 4), v) for l, v in pts],
                  key=lambda x: abs(x[1]))   # 偏离最大者排顶部 → 龙卷风
    labels = [d[0] for d in devs]
    vals = [d[1] for d in devs]
    colors = [dear_color if d > 0 else cheap_color for d in vals]
    texts = [f"{'＋' if d >= 0 else '－'}{value_fmt(abs(d))}{unit}" for d in vals]
    customdata = [value_fmt(d[2]) + unit for d in devs]

    fig = go.Figure(go.Bar(
        y=labels, x=vals, orientation="h",
        marker=dict(color=colors, line=dict(color="white", width=1.2)),
        text=texts, textposition="outside", textfont=dict(size=12.5), cliponaxis=False,
        customdata=customdata,
        hovertemplate="%{y}<br>Price · 该口径定价 %{customdata}<br>Deviation from anchor · 相对锚定价偏离 %{text}<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color="#0E8C3A", width=1.6, dash="dash"))
    amax = max((abs(v) for v in vals), default=1) or 1
    fig.update_layout(
        font=_FONT, paper_bgcolor=_BG, plot_bgcolor="#fbfdff",
        height=52 * len(vals) + 96, margin=dict(l=10, r=48, t=34, b=26),
        xaxis=dict(title=f"Deviation from cross-anchor price · 相对交叉锚定价的偏离（{unit.strip() or '单位'}）",
                   gridcolor="#eef2f7", zeroline=False, range=[-amax * 1.5, amax * 1.5]),
        yaxis=dict(automargin=True),
        annotations=[dict(x=0, y=1.05, yref="paper", showarrow=False,
                          text="◆ Cross-anchor price (baseline) · 交叉锚定价（基准线）", font=dict(color="#0E8C3A", size=12))],
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# 渲染
# ═══════════════════════════════════════════════════════════════════════
_MEDALS = ["🥇", "🥈", "🥉", "④", "⑤", "⑥", "⑦", "⑧"]


def _champ_html(r: dict, dim_cn: dict, accent: str) -> str:
    chips = ""
    for ld in r["leads"]:
        name = dim_cn.get(ld["k"], ld["k"])
        if ld["margin"] >= 0.5:
            tail = f"<i>leads runner-up by · 领先次席 {ld['margin']:g}</i>"
        else:
            tail = "<i>tied highest · 并列最高</i>"
        chips += (f"<span class='cmp-lead'>{name} <b>{ld['v']:.0f}</b> {tail}</span>")
    if r["leads"]:
        verdict = (f"Takes <b>{r['n_first']}</b> of {r['n_dim']} scoring dimensions as the field's best — "
                   f"the most balanced optimum with no clear weak spot. · "
                   f"在 {r['n_dim']} 个评分维度里拿下 <b>{r['n_first']}</b> 项全场第一，"
                   f"是各维最均衡、且无明显短板的最优解。")
    else:
        verdict = ("Highest weighted total with no clear weak dimension — the current optimum. · "
                   "综合加权后总分居首，各维无明显短板，是当前最优解。")
    return (
        f"<div class='cmp-card cmp-champ' style='--accent:{accent}'>"
        f"<div class='cmp-head'>"
        f"<span class='cmp-medal'>🥇</span>"
        f"<span class='cmp-name'>{r['name']}</span>"
        f"<span class='cmp-tag-best'>Best · 最优解</span>"
        f"<span class='cmp-score'>{r['score']:.1f}</span>"
        f"</div>"
        f"<div class='cmp-why'><b>Why it wins · 凭什么是它：</b>{verdict}</div>"
        f"<div class='cmp-chips'>{chips}</div>"
        f"</div>"
    )


def _runner_html(r: dict, dim_cn: dict, champ_name: str) -> str:
    medal = _MEDALS[min(r["rank"] - 1, len(_MEDALS) - 1)]
    gap = abs(r["total_gap"])
    # 评分依据：核心短板叙述
    if r["losses"]:
        main = r["losses"][0]
        parts = (f"Key weakness in <b>{dim_cn.get(main['k'], main['k'])}</b> "
                 f"({main['a']:.0f} vs best {main['t']:.0f}, weighted drag {abs(main['weighted']):g}) · "
                 f"核心短板在 <b>{dim_cn.get(main['k'], main['k'])}</b>"
                 f"（{main['a']:.0f} vs 最优解 {main['t']:.0f}，加权拖累 {abs(main['weighted']):g} 分）")
        if len(r["losses"]) > 1:
            sec = r["losses"][1]
            parts += (f"; then {dim_cn.get(sec['k'], sec['k'])} ({sec['a']:.0f} vs {sec['t']:.0f})"
                      f" · 其次是 {dim_cn.get(sec['k'], sec['k'])}（{sec['a']:.0f} vs {sec['t']:.0f}）")
        why = parts + "."
    else:
        why = ("All dimensions are close to the best; the gap is just fine weighted differences. · "
               "各维度与最优解接近，差距来自综合加权的细微差异。")
    # 场景反超：该家某一维是全场最强
    scen = ""
    if r["scenarios"]:
        names = "、".join(dim_cn.get(k, k) for k in r["scenarios"])
        scen = (f"<div class='cmp-scen'>✔ Scenario edge · 场景反超：if you most value · 若最看重 <b>{names}</b>, "
                f"it's the field's strongest — a priority backup for that scenario. · 它是全场最强，可作该场景的优先备选。</div>")
    return (
        f"<div class='cmp-card'>"
        f"<div class='cmp-head'>"
        f"<span class='cmp-medal'>{medal}</span>"
        f"<span class='cmp-name'>{r['name']}</span>"
        f"<span class='cmp-tag-gap'>behind best · 落后最优解 {gap:g}</span>"
        f"<span class='cmp-score cmp-score-sm'>{r['score']:.1f}</span>"
        f"</div>"
        f"<div class='cmp-why'><b>Why not the best · 为什么不是最优：</b>{why}</div>"
        f"{scen}"
        f"</div>"
    )


def render_comparison(companies: list[dict], dim_keys: list[str], dim_cn: dict,
                      weights: dict, *, accent: str = "#0E8C3A",
                      title: str = "⚖️ Head-to-Head Comparison · 厂家逐一对比 · 为什么是它、别家为什么不是最优",
                      intro: str | None = None, max_runners: int = 5,
                      key: str | None = None) -> None:
    """在当前位置渲染整段文字版对比 + 差距归因龙卷风图。companies 应为同一可比
    集合（同一品类/基地/工厂）。传入 key 时渲染龙卷风图（plotly 需唯一 key）。"""
    data = build_comparison(companies, dim_keys, dim_cn, weights)
    if not data:
        return
    st.markdown(f"#### {title}")
    if intro is None:
        intro = ("Below, each supplier's scoring rationale in words: where the optimum is strong and by how much "
                 "it leads; each other firm's key weak dimension and weighted drag, and the scenarios where it is "
                 "actually the better choice. · "
                 "下面用文字逐家说清评分依据：最优解强在哪、领先多少；其余各家的核心短板"
                 "是哪一维、加权拖累多少分，以及它们在什么场景下反而更值得选。")
    st.caption(intro)

    # ── 差距归因龙卷风图（图示版「为什么是它」）──────────────────────
    if key is not None:
        tor = tornado_figure(companies, dim_keys, dim_cn, weights, accent)
        if tor is not None:
            fig, champ, runner, total = tor
            st.markdown(
                f"<div class='cmp-tor-head'>🌪️ Gap-attribution tornado · 差距归因龙卷风：optimum · 最优解 "
                f"<b>{champ.get('name')}</b> leads runner-up · 综合领先次席「{runner.get('name')}」"
                f"<b style='color:{accent}'> {total:g}</b> —— broken down into weighted per-dimension contributions · 这 {total:g} 分由各维度加权拆解而来</div>",
                unsafe_allow_html=True,
            )
            st.plotly_chart(fig, width="stretch",
                            config={"displayModeBar": False}, key=f"cmp_tor_{key}")
            st.caption("Green = weighted lead the top pick gains in that dimension; orange = where the runner-up "
                       "overtakes it; the bars sum to the optimum's weighted lead (the source of the score gap). "
                       "Longer bar = more decisive for 'why it wins'.  \n"
                       "绿条＝该维度为首选贡献的加权领先分，橙条＝首选在该维反被次席反超；"
                       "各条加总＝最优解对次席的加权维度领先（即综合分差的来源）。"
                       "条越长，说明这一维对「为什么是它」越关键。")

    html = "<div class='cmp-wrap'>"
    runners = 0
    for r in data["rows"]:
        if r["is_champ"]:
            html += _champ_html(r, dim_cn, accent)
        else:
            if runners >= max_runners:
                continue
            html += _runner_html(r, dim_cn, data["champ_name"])
            runners += 1
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# 样式
# ═══════════════════════════════════════════════════════════════════════
COMPARISON_CSS = """
<style>
.cmp-wrap{display:flex;flex-direction:column;gap:10px;margin:4px 0 16px;}
.cmp-card{background:#fff;border:1px solid #e6ebf2;border-left:4px solid #cbd5e1;
  border-radius:11px;padding:12px 15px;box-shadow:0 6px 18px -16px rgba(10,22,40,.4);}
.cmp-champ{border-left-color:var(--accent);
  background:linear-gradient(135deg,#f3fbf6 0%,#fbfffd 60%);}
.cmp-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;}
.cmp-medal{font-size:20px;line-height:1;}
.cmp-name{font-size:15.5px;font-weight:800;color:#0a1628;}
.cmp-tag-best{font-size:11px;font-weight:700;color:#0E8C3A;background:rgba(14,140,58,.1);
  border:1px solid rgba(14,140,58,.25);padding:1px 9px;border-radius:20px;}
.cmp-tag-gap{font-size:11px;font-weight:700;color:#b45309;background:rgba(217,119,6,.09);
  border:1px solid rgba(217,119,6,.22);padding:1px 9px;border-radius:20px;}
.cmp-score{margin-left:auto;font-size:19px;font-weight:800;color:#0E8C3A;}
.cmp-score-sm{font-size:16px;color:#475569;}
.cmp-why{font-size:13.5px;color:#33415a;line-height:1.7;margin-top:7px;}
.cmp-why b{color:#0a1628;}
.cmp-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:9px;}
.cmp-lead{font-size:12px;color:#15603a;background:#eef9f2;border:1px solid #cfeede;
  border-radius:20px;padding:2px 11px;line-height:1.5;}
.cmp-lead b{font-weight:800;}
.cmp-lead i{font-style:normal;color:#0E8C3A;opacity:.8;}
.cmp-scen{font-size:12.5px;color:#1d4ed8;background:#eff6ff;border:1px solid #c7ddfb;
  border-radius:9px;padding:7px 11px;margin-top:8px;line-height:1.6;}
.cmp-scen b{color:#1e40af;}
.cmp-tor-head{font-size:13.5px;color:#33415a;line-height:1.7;margin:2px 0 4px;
  padding:9px 13px;background:#f8fafc;border:1px solid #e6ebf2;border-radius:10px;}
.cmp-tor-head b{color:#0a1628;}
@media (max-width:900px){.cmp-score{margin-left:0;}}
</style>
"""
