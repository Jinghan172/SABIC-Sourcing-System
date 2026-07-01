# -*- coding: utf-8 -*-
"""
透明价格工具箱（全站共享）—— 让每个采购价都『可溯源 + 可信度自评』。

设计动机：采购最怕两件事 —— 数字不准、来源不明。本模块把每个价格拆成三层透明结构，
被核心物料专家评审、设备寻源、综合服务/MRO 三大模块共用，口径与样式统一：

  ① 可信度自评 reliability_badge —— 一眼看清这个价能不能直接用：
       high   公开市场指数 / 已核验中标价支撑           → 可直接进预算
       medium 有真实招标佐证，但中标单价未公开 → 多方测算   → 议价参考
       low    无公开招标单价 → 估测，务必以书面报价为准      → 仅作量级参考
  ② 招标/行情溯源 render_tender_evidence —— 直接把最有代表性的真实公开信息摆上来：
       中标公告 / 框架协议 / 市场指数，逐条带采购方、日期、数量、单价、来源链接，可点开回溯。
  ③ 多方交叉测算 render_triangulation —— 不是拍一个均价，而是市场指数 / 招标佐证 /
       成本加成 / 龙头报价多路口径并列，收敛到一个锚定值，并标注本次估测的可信度。

对外接口：
  RELIABILITY, PRICE_TAG                 常量表
  reliability_badge(level, note="")  -> HTML 字符串（醒目可信度条）
  render_tender_evidence(cases, ...)     真实招标/行情案例卡（Streamlit 直接渲染）
  render_triangulation(methods, ...)     多方交叉测算收敛
  price_tag_html(tag)                -> 单个价签 HTML
  PRICING_CSS                            样式（在 app.py 注入一次）
"""
from __future__ import annotations
import streamlit as st

# ── 可信度三档（核心：让"准不准"自己说话）──────────────────────────────
RELIABILITY = {
    "high":   ("✅ High · 高可靠", "#0E8C3A",
               "Backed by public market index / verified award price · 公开市场指数或已核验中标价支撑，可直接进预算"),
    "medium": ("🟡 Medium · 中等", "#d97706",
               "Real tenders found but award unit-price undisclosed → triangulated · 有真实招标佐证、中标单价未公开，多方测算，供议价参考"),
    "low":    ("🔴 Low · 低可靠", "#ef4444",
               "No public tender unit-price → estimate only, defer to written quote · 无公开招标单价，仅为估测，务必以书面报价为准"),
}

# ── 单条价格的来源属性价签 ─────────────────────────────────────────────
PRICE_TAG = {
    "verified":   ("✅ Verified · 公开指数/中标", "pt-verified"),
    "tender":     ("📑 Tender-backed · 招标佐证·单价未公开", "pt-tender"),
    "estimate":   ("🟡 Triangulated · 多方测算", "pt-estimate"),
    "unreliable": ("🔴 Estimate · 估测·不准", "pt-unreliable"),
    "rfq":        ("✉️ RFQ · 需询价", "pt-rfq"),
}


def price_tag_html(tag: str) -> str:
    label, cls = PRICE_TAG.get(tag, PRICE_TAG["estimate"])
    return f"<span class='pt {cls}'>{label}</span>"


def reliability_badge(level: str, note: str = "") -> str:
    """醒目的可信度条 —— 放在价格区块顶部，先把"这个价能不能用"说清楚。"""
    label, color, default_note = RELIABILITY.get(level, RELIABILITY["low"])
    return (
        f"<div class='pr-badge' style='--prc:{color}'>"
        f"<span class='pr-dot'></span>"
        f"<span class='pr-label'>Data reliability · 数据可信度：{label}</span>"
        f"<span class='pr-note'>{note or default_note}</span>"
        f"</div>"
    )


# ── 真实招标/行情溯源卡 ────────────────────────────────────────────────
def render_tender_evidence(cases: list[dict], accent: str = "#0E8C3A",
                           title: str | None = None) -> None:
    """把最有代表性的真实公开信息直接摆上来，逐条可点开回溯。
    case 字段：title 标题 · buyer 采购方 · date 日期 · qty 数量/口径 ·
              unit_price 单价文本(可"未公开") · platform 平台 · url 链接 · note 备注。"""
    if not cases:
        return
    st.markdown(
        f"##### 🔎 {title or 'Representative public tenders & market quotes · 代表性真实招标成交 / 公开行情，逐条可溯源'}")
    cards = ""
    for c in cases:
        up = c.get("unit_price") or "未公开 · undisclosed"
        undis = ("未公开" in up) or ("undisclosed" in up.lower())
        url = c.get("url", "")
        link = (f"<a class='tc-src' href='{url}' target='_blank' rel='noopener'>🔗 {c.get('platform','source')} ↗</a>"
                if url else f"<span class='tc-src tc-src-x'>📄 {c.get('platform','')}</span>")
        cards += (
            f"<div class='tc-card' style='--accent:{accent}'>"
            f"<div class='tc-plat'>{c.get('platform','')}</div>"
            f"<div class='tc-title'>{c.get('title','')}</div>"
            f"<div class='tc-meta'>🏛️ {c.get('buyer','')}</div>"
            f"<div class='tc-meta'>📅 {c.get('date','')} · 📦 {c.get('qty','')}</div>"
            f"<div class='tc-price {'tc-undis' if undis else ''}'>{up}</div>"
            + (f"<div class='tc-note'>{c.get('note','')}</div>" if c.get('note') else "")
            + f"<div class='tc-srcrow'>{link}</div>"
            f"</div>"
        )
    st.markdown(f"<div class='tc-grid'>{cards}</div>", unsafe_allow_html=True)


# ── 「本次估算参考了哪些标书」清单（不带链接，纯列举）──────────────────
def render_referenced_tenders(cases: list[dict], accent: str = "#0E8C3A",
                              title: str | None = None, note: str | None = None) -> None:
    """在价格估算模块内，明确列出这份估算参考了哪些真实公开标书。
    与顶部『招标溯源卡』呼应，但这里是紧凑清单、贴着估算结论，让读者一眼看清
    『这个价是照着哪些标书算出来的』。case 字段同 render_tender_evidence。"""
    if not cases:
        return
    st.markdown(
        f"##### 📋 {title or 'Which real public tenders this estimate is based on · 本次估算参考了哪些真实公开标书'}")
    rows = ""
    for c in cases:
        up = c.get("unit_price") or "未公开 · undisclosed"
        undis = ("未公开" in up) or ("undisclosed" in up.lower())
        price_txt = ("Award unit-price undisclosed · 中标单价未公开" if undis else up)
        rows += (
            f"<div class='rt-item' style='--accent:{accent}'>"
            f"<div class='rt-head'>"
            f"<span class='rt-date'>📅 {c.get('date','')}</span>"
            f"<span class='rt-buyer'>🏛️ {c.get('buyer','')}</span>"
            + (f"<span class='rt-plat'>{c.get('platform','')}</span>" if c.get('platform') else "")
            + f"</div>"
            f"<div class='rt-title'>{c.get('title','')}</div>"
            f"<div class='rt-price {'rt-undis' if undis else 'rt-known'}'>{price_txt}</div>"
            f"</div>"
        )
    st.markdown(f"<div class='rt-list'>{rows}</div>", unsafe_allow_html=True)
    default_note = ("Framework-tender award unit-prices are usually not published, so this estimate triangulates these "
                    "tenders with platform framework pricing, shortlisted-supplier quotes and the historical trend — it "
                    "is a model, not a copy of any single award price. · "
                    "框架招标的中标单价通常不公开，故本估算是把上述标书与『平台框架价 + 供应商报价 + 历史走势』"
                    "交叉建模测算得出，并非照搬某一条中标价。")
    st.markdown(f"<div class='rt-note'>ℹ️ {note or default_note}</div>", unsafe_allow_html=True)


# ── 多方交叉测算收敛 ───────────────────────────────────────────────────
def render_triangulation(methods: list[dict], anchor: str | None = None,
                         level: str = "medium", accent: str = "#0E8C3A",
                         title: str | None = None) -> None:
    """多路口径并列 → 收敛到锚定值，并标注可信度。
    method 字段：name 口径名 · value 该口径价 · note 说明。"""
    if not methods:
        return
    st.markdown(
        f"##### 🧮 {title or 'Multi-method cross-estimate · converging to an anchor · 多方交叉测算 · 收敛到建议锚定价'}")
    cells = ""
    for m in methods:
        cells += (
            f"<div class='tri-cell'>"
            f"<div class='tri-name'>{m.get('name','')}</div>"
            f"<div class='tri-val'>{m.get('value','')}</div>"
            f"<div class='tri-note'>{m.get('note','')}</div>"
            f"</div>"
        )
    anchor_html = ""
    if anchor:
        color = RELIABILITY.get(level, RELIABILITY["low"])[1]
        anchor_html = (
            f"<div class='tri-anchor' style='--prc:{color}'>"
            f"<span class='tri-anchor-lbl'>◆ Suggested anchor · 建议锚定价</span>"
            f"<span class='tri-anchor-val'>{anchor}</span>"
            f"</div>"
        )
    st.markdown(f"<div class='tri-wrap'><div class='tri-grid'>{cells}</div>{anchor_html}</div>",
                unsafe_allow_html=True)


PRICING_CSS = """
<style>
/* ── 可信度条 ── */
.pr-badge{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:6px 0 12px;padding:9px 14px;
  background:color-mix(in srgb,var(--prc) 8%,#fff);border:1px solid color-mix(in srgb,var(--prc) 30%,#fff);
  border-left:5px solid var(--prc);border-radius:10px;}
.pr-dot{width:10px;height:10px;border-radius:50%;background:var(--prc);box-shadow:0 0 0 4px color-mix(in srgb,var(--prc) 18%,#fff);}
.pr-label{font-size:13px;font-weight:800;color:#0a1628;}
.pr-note{font-size:11.5px;color:#5a6780;line-height:1.5;flex:1;min-width:240px;}
/* ── 价签 ── */
.pt{font-size:10.5px;font-weight:700;padding:2px 9px;border-radius:20px;white-space:nowrap;display:inline-block;}
.pt-verified{color:#0E8C3A;background:rgba(14,140,58,.08);border:1px solid rgba(14,140,58,.28);}
.pt-tender{color:#2563eb;background:rgba(37,99,235,.08);border:1px solid rgba(37,99,235,.26);}
.pt-estimate{color:#d97706;background:rgba(217,119,6,.09);border:1px solid rgba(217,119,6,.28);}
.pt-unreliable{color:#dc2626;background:rgba(220,38,38,.08);border:1px solid rgba(220,38,38,.3);}
.pt-rfq{color:#64748b;background:#f1f5f9;border:1px solid #e2e8f0;}
/* ── 招标溯源卡 ── */
.tc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(252px,1fr));gap:12px;margin:6px 0 14px;}
.tc-card{background:#fff;border:1px solid #e6ebf2;border-top:3px solid var(--accent);border-radius:12px;
  padding:12px 13px;box-shadow:0 8px 22px -18px rgba(10,22,40,.4);display:flex;flex-direction:column;}
.tc-plat{font-size:10.5px;font-weight:800;color:var(--accent);letter-spacing:.02em;text-transform:uppercase;}
.tc-title{font-size:13px;font-weight:800;color:#0a1628;line-height:1.4;margin:3px 0 5px;}
.tc-meta{font-size:11.5px;color:#5a6780;line-height:1.55;}
.tc-price{font-size:20px;font-weight:800;color:#0a1628;margin:6px 0 2px;line-height:1.15;}
.tc-undis{font-size:13px;font-weight:700;color:#94a3b8;}
.tc-note{font-size:11px;color:#64748b;line-height:1.5;margin-top:2px;}
.tc-srcrow{margin-top:auto;padding-top:8px;}
.tc-src{font-size:11.5px;font-weight:700;color:var(--accent);text-decoration:none;}
.tc-src:hover{text-decoration:underline;}
.tc-src-x{color:#94a3b8;font-weight:600;}
/* ── 参考标书清单 ── */
.rt-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin:6px 0 8px;}
.rt-item{background:#fff;border:1px solid #e6ebf2;border-left:4px solid var(--accent);border-radius:10px;
  padding:10px 13px;box-shadow:0 6px 18px -16px rgba(10,22,40,.4);}
.rt-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:11.5px;color:#5a6780;}
.rt-buyer{font-weight:700;color:#334155;}
.rt-plat{margin-left:auto;font-size:10.5px;font-weight:700;color:var(--accent);
  background:color-mix(in srgb,var(--accent) 8%,#fff);border:1px solid color-mix(in srgb,var(--accent) 24%,#fff);
  padding:1px 8px;border-radius:20px;}
.rt-title{font-size:13px;font-weight:700;color:#0a1628;line-height:1.4;margin:4px 0 5px;}
.rt-price{font-size:12px;font-weight:700;display:inline-block;padding:2px 9px;border-radius:6px;}
.rt-undis{color:#64748b;background:#f1f5f9;border:1px solid #e2e8f0;}
.rt-known{color:#0E8C3A;background:rgba(14,140,58,.08);border:1px solid rgba(14,140,58,.24);}
.rt-note{font-size:11.5px;color:#64748b;line-height:1.6;margin:2px 0 12px;padding:8px 12px;
  background:#f8fafc;border:1px dashed #dbe3ec;border-radius:8px;}
/* ── 多方测算 ── */
.tri-wrap{display:flex;flex-wrap:wrap;gap:12px;align-items:stretch;margin:6px 0 14px;}
.tri-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px;flex:1;min-width:280px;}
.tri-cell{background:#fbfdff;border:1px solid #e6ebf2;border-radius:10px;padding:10px 12px;}
.tri-name{font-size:11.5px;font-weight:700;color:#475569;line-height:1.35;min-height:32px;}
.tri-val{font-size:17px;font-weight:800;color:#0a1628;margin:3px 0;}
.tri-note{font-size:10.5px;color:#94a3b8;line-height:1.45;}
.tri-anchor{display:flex;flex-direction:column;justify-content:center;gap:4px;min-width:200px;padding:14px 18px;
  border-radius:12px;background:linear-gradient(135deg,#071120,#0d2a1d);border-left:5px solid var(--prc);}
.tri-anchor-lbl{font-size:11.5px;font-weight:700;color:#fcd34d;}
.tri-anchor-val{font-size:24px;font-weight:800;color:#fff;line-height:1.15;}
</style>
"""
