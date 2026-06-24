"""
供应商背调报告生成 v1.0  —— 输出自成一体的 HTML 报告（内嵌样式、可直接打印为 PDF）。

这是企查查给不了的交付物：不是单家公司的工商页，而是面向某个采购品类的
「决策结论 + 供应市场结构 + 首选背调档案 + 候选对比 + 核验渠道」一体化报告，
打开即可阅读，Ctrl+P 即可存成 PDF 发给领导。无需任何额外依赖。
"""
from __future__ import annotations
from datetime import datetime
from html import escape

from utils.insights import (
    decision_summary, supply_landscape, supplier_highlights,
    why_not_top, ROLE_LABEL, cap_text,
)

GREEN = "#0E8C3A"
NAVY = "#0a1628"


def _e(v) -> str:
    return escape(str(v if v is not None else "—"))


def _cap(wan) -> str:
    wan = wan or 0
    if wan >= 10000:
        return f"{wan / 10000:.2f} 亿元"
    if wan > 0:
        return f"{wan:.0f} 万元"
    return "未披露"


def _age(s: dict) -> str:
    y = s.get("established", 0) or 0
    return f"{datetime.now().year - y} 年" if y else "—"


def _role_cn(s: dict) -> str:
    return ROLE_LABEL.get(s.get("_role", "unknown"), "类型待核")


def _tier_cn(t: int) -> str:
    return {1: "一级（沪苏浙皖）", 2: "二级（鲁粤鄂豫闽等）", 3: "三级（其余）"}.get(t, "—")


def _score_color(v: float) -> str:
    return GREEN if v >= 70 else "#d97706" if v >= 40 else "#dc2626"


def _compliance_badges(s: dict) -> list[tuple[str, bool]]:
    scope = s.get("_business_scope", "") or ""
    lic = s.get("licenses", {}) or {}
    return [
        ("经营状态存续/在业", (s.get("reg_status", "存续") or "存续") in ("存续", "在业", "")),
        ("工厂/制造商", s.get("_role") in ("manufacturer", "both")),
        ("危险化学品经营资质", bool(lic.get("hazardous_chemicals") or lic.get("hazmat_business"))),
        ("化工园区内企业", bool(s.get("chemical_park"))),
        ("进出口经营资质", any(k in scope for k in ["进出口", "货物及技术进出口"])),
    ]


# ──────────────────────────────────────────────────────────────────────
def build_dossier_html(query: str, results: list[dict],
                       weights: dict | None = None,
                       meta: dict | None = None) -> str:
    """生成完整背调报告 HTML 字符串。results 为已评分排序的供应商列表。"""
    meta = meta or {}
    now = datetime.now()
    report_id = f"SABIC-DD-{now:%Y%m%d}-{abs(hash(query)) % 9000 + 1000}"
    dec = decision_summary(results)
    land = supply_landscape(results)
    top = results[0] if results else None

    # ── 封面 ──
    cover = f"""
    <header class="cover">
      <div class="cover-badge">SABIC SHANGHAI · 智能寻源决策报告</div>
      <h1 class="cover-title">{_e(query)} · 供应商背调报告</h1>
      <div class="cover-sub">基于企查查同源工商数据 · 三维量化评分 · 自动决策建议</div>
      <div class="cover-meta">
        <span>报告编号：{report_id}</span>
        <span>生成日期：{now:%Y-%m-%d %H:%M}</span>
        <span>候选范围：{land.get('n', 0)} 家供应商</span>
        <span>数据来源：{_e(meta.get('source_label', '本地缓存（企查查 MCP 采集）'))}</span>
      </div>
    </header>
    """

    # ── 一、决策结论 ──
    if dec:
        tags = "".join(f"<span class='pill'>{_e(t)}</span>" for t in dec["top_tags"])
        lead = (f"<span class='lead-pill'>↑ 领先第二名 {dec['lead']} 分</span>"
                if dec.get("lead") and dec["lead"] > 0 else "")
        scen = ""
        if dec["scenarios"]:
            cards = "".join(
                f"<div class='scen'><div class='scen-l'>{_e(s['icon'])} {_e(s['label'])}之选</div>"
                f"<div class='scen-n'>{_e(s['name'])}</div>"
                f"<div class='scen-w'>{_e(s['why'])}</div></div>"
                for s in dec["scenarios"]
            )
            scen = f"<div class='scen-row'>{cards}</div>"
        decision = f"""
        <section class="sec">
          <h2><span class="num">1</span>采购决策结论</h2>
          <div class="decide">
            <div class="decide-head">
              <div class="medal">🥇</div>
              <div class="decide-main">
                <div class="decide-name">{_e(dec['top_name'])}</div>
                <div class="decide-why">推荐理由：{_e(dec['top_why'])}</div>
                <div class="pills">{tags}</div>
              </div>
              <div class="decide-score">
                <div class="ds-val">{dec['top_score']:.1f}</div>
                <div class="ds-lbl">综合评分</div>
                {lead}
              </div>
            </div>
            {scen}
          </div>
        </section>
        """
    else:
        decision = ""

    # ── 二、供应市场结构 ──
    if land.get("n"):
        provs = "、".join(f"{_e(p)} {c} 家" for p, c in land["top_provs"])
        avg = f"{land['avg_dist']} 公里" if land.get("avg_dist") else "—"
        landscape = f"""
        <section class="sec">
          <h2><span class="num">2</span>供应市场结构</h2>
          <div class="stat-grid">
            <div class="stat"><div class="stat-v">{land['n']}</div><div class="stat-l">可选供应商</div></div>
            <div class="stat"><div class="stat-v">{land['tier1']}<span>家</span></div><div class="stat-l">华东一级圈 · {land['tier1_share']}%</div></div>
            <div class="stat"><div class="stat-v">{land['factories']}<span>家</span></div><div class="stat-l">工厂/制造商 · {land['factory_share']}%</div></div>
            <div class="stat"><div class="stat-v">{land['hazmat']}<span>家</span></div><div class="stat-l">含危化品资质</div></div>
            <div class="stat"><div class="stat-v">{avg}</div><div class="stat-l">平均距上海</div></div>
            <div class="stat"><div class="stat-v" style="font-size:15px">{_e(land['leader_name'])}</div><div class="stat-l">资本龙头 · {_e(land['leader_cap'])}</div></div>
          </div>
          <p class="note">📊 供应版图主要集中在 <b>{provs}</b>。{_e(land['geo_note'])}。</p>
        </section>
        """
    else:
        landscape = ""

    # ── 三、首选供应商背调档案 ──
    dossier = ""
    if top:
        dims = top.get("dimensions", {})
        w = weights or {"geography": 0.35, "scale": 0.35, "compliance": 0.30}
        dim_rows = ""
        for k, lbl, icon in [("geography", "地理位置", "📍"), ("scale", "企业规模", "🏢"),
                             ("compliance", "合规资质", "✅")]:
            v = dims.get(k, 0)
            col = _score_color(v)
            wt = int(w.get(k, 0) * 100)
            dim_rows += f"""
            <div class="dim">
              <div class="dim-l">{icon} {lbl} <span class="dim-w">×{wt}%</span></div>
              <div class="bar"><div class="bar-f" style="width:{v:.0f}%;background:{col}"></div></div>
              <div class="dim-v" style="color:{col}">{v:.0f}</div>
            </div>"""
        badges = "".join(
            f"<span class='cb {'on' if ok else 'off'}'>{'✓' if ok else '✗'} {_e(lbl)}</span>"
            for lbl, ok in _compliance_badges(top)
        )
        info_rows = "".join(
            f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in [
                ("企业全称", top.get("name")),
                ("统一社会信用代码", top.get("creditCode") or top.get("credit_code")),
                ("法定代表人", top.get("legalPerson") or top.get("legal_person")),
                ("注册资本", _cap(top.get("registered_capital_wan", 0))),
                ("成立年限", _age(top)),
                ("经营状态", top.get("reg_status") or "存续"),
                ("所属省市", f"{top.get('province') or '—'} {top.get('city') or ''}".strip()),
                ("地理圈层", _tier_cn(top.get("_tier", 3))),
                ("距上海运距", f"约 {top.get('logistics', {}).get('distance_km_to_shanghai', '—')} 公里"),
                ("企业角色", _role_cn(top)),
                ("所属行业", top.get("industry")),
                ("注册地址", top.get("address")),
            ]
        )
        scope = top.get("_business_scope", "") or "—"
        dossier = f"""
        <section class="sec">
          <h2><span class="num">3</span>首选供应商背调档案</h2>
          <div class="dossier-head">
            <div class="dh-name">{_e(top.get('name'))}</div>
            <div class="dh-score" style="color:{_score_color(top.get('score', 0))}">{top.get('score', 0):.1f} <span>分</span></div>
          </div>
          <div class="two-col">
            <div>
              <h3>工商基本信息</h3>
              <table class="info">{info_rows}</table>
            </div>
            <div>
              <h3>三维评分明细</h3>
              <div class="dims">{dim_rows}</div>
              <h3 style="margin-top:14px">资质与合规</h3>
              <div class="cbs">{badges}</div>
            </div>
          </div>
          <h3 style="margin-top:14px">经营范围（企查查 Scope 原文）</h3>
          <div class="scope">{_e(scope)}</div>
        </section>
        """

    # ── 四、候选供应商对比 ──
    rows = ""
    for i, s in enumerate(results[:10]):
        dims = s.get("dimensions", {})
        rk = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
        hi = " class='row-top'" if i == 0 else ""
        rows += f"""
        <tr{hi}>
          <td class="rk">{rk}</td>
          <td class="nm">{_e(s.get('name'))}</td>
          <td>{_e(s.get('province'))}</td>
          <td>{_role_cn(s)}</td>
          <td>{_cap(s.get('registered_capital_wan', 0))}</td>
          <td>{_e(s.get('established') or '—')}</td>
          <td style="color:{_score_color(dims.get('geography', 0))}">{dims.get('geography', 0):.0f}</td>
          <td style="color:{_score_color(dims.get('scale', 0))}">{dims.get('scale', 0):.0f}</td>
          <td style="color:{_score_color(dims.get('compliance', 0))}">{dims.get('compliance', 0):.0f}</td>
          <td class="tot" style="color:{_score_color(s.get('score', 0))}">{s.get('score', 0):.1f}</td>
        </tr>"""
    compare = f"""
    <section class="sec">
      <h2><span class="num">4</span>候选供应商对比（Top {min(len(results), 10)}）</h2>
      <table class="cmp">
        <thead><tr>
          <th>#</th><th>企业名称</th><th>省份</th><th>角色</th><th>注册资本</th>
          <th>成立</th><th>地理</th><th>规模</th><th>合规</th><th>综合</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """

    # ── 五、核验渠道 & 声明 ──
    footer = f"""
    <section class="sec">
      <h2><span class="num">5</span>官方核验渠道与数据声明</h2>
      <ul class="links">
        <li>🏛 国家企业信用信息公示系统　https://www.gsxt.gov.cn</li>
        <li>🔒 应急管理部 · 危化品/安全生产资质核验　https://www.mem.gov.cn/fw/cxfw/</li>
        <li>🛃 海关信用企业查询　https://credit.customs.gov.cn</li>
      </ul>
      <p class="disclaim">
        本报告评分基于企查查工商登记数据（经营状态/注册资本/成立日期/经营范围/行业/注册地址）
        自动量化生成，三维权重为 地理 {int((weights or {}).get('geography', 0.35) * 100)}% ·
        规模 {int((weights or {}).get('scale', 0.35) * 100)}% ·
        合规 {int((weights or {}).get('compliance', 0.30) * 100)}%。
        产能、起订量、报价、实际履约能力需向企业询价并实地核验，工商数据不含上述信息。
        正式定点前请通过上述官方渠道二次核验资质有效性。
      </p>
      <div class="sign">SABIC 上海智能寻源系统 · {now:%Y-%m-%d} 自动生成 · 报告编号 {report_id}</div>
    </section>
    """

    return _PAGE.format(query=_e(query), body=cover + decision + landscape + dossier + compare + footer,
                        green=GREEN, navy=NAVY)


# ── 报告整体模板（内嵌打印友好样式）────────────────────────────────────
_PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{query} · SABIC 供应商背调报告</title>
<style>
  @page {{ size: A4; margin: 14mm 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC",sans-serif;
    color:#1a2233; margin:0; background:#eef2f7; font-size:15px; line-height:1.6; }}
  .sheet {{ max-width:880px; margin:20px auto; background:#fff; padding:0 0 28px;
    box-shadow:0 6px 30px rgba(0,0,0,.1); border-radius:10px; overflow:hidden; }}
  /* 封面 */
  .cover {{ background:linear-gradient(135deg,{navy} 0%,#10243f 60%,{navy} 100%);
    color:#fff; padding:34px 38px 30px; border-bottom:4px solid {green}; }}
  .cover-badge {{ display:inline-block; font-size:12px; letter-spacing:.14em;
    color:#5eead4; border:1px solid rgba(94,234,212,.4); background:rgba(14,140,58,.18);
    padding:4px 14px; border-radius:20px; margin-bottom:16px; }}
  .cover-title {{ font-size:30px; font-weight:800; margin:0 0 8px; }}
  .cover-sub {{ font-size:14px; color:rgba(255,255,255,.6); margin-bottom:20px; }}
  .cover-meta {{ display:flex; flex-wrap:wrap; gap:8px 26px; font-size:12.5px;
    color:rgba(255,255,255,.78); border-top:1px solid rgba(255,255,255,.12); padding-top:16px; }}
  /* 段落 */
  .sec {{ padding:22px 38px 4px; }}
  .sec h2 {{ font-size:19px; font-weight:700; color:{navy}; display:flex; align-items:center;
    gap:10px; margin:6px 0 16px; padding-bottom:9px; border-bottom:2px solid #eef2f7; }}
  .num {{ display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px;
    border-radius:8px; background:linear-gradient(135deg,{green},#27a84f); color:#fff;
    font-size:15px; font-weight:700; }}
  .sec h3 {{ font-size:14.5px; color:#374151; margin:0 0 9px; font-weight:700; }}
  /* 决策卡 */
  .decide {{ background:linear-gradient(135deg,{navy},#10243f); border-radius:12px; padding:20px; color:#fff; }}
  .decide-head {{ display:flex; gap:16px; align-items:flex-start; }}
  .medal {{ width:52px; height:52px; border-radius:13px; background:linear-gradient(135deg,#facc15,#f59e0b);
    display:flex; align-items:center; justify-content:center; font-size:27px; flex-shrink:0; }}
  .decide-main {{ flex:1; }}
  .decide-name {{ font-size:21px; font-weight:800; }}
  .decide-why {{ font-size:13px; color:rgba(255,255,255,.65); margin-top:4px; }}
  .pills {{ margin-top:10px; }}
  .pill {{ display:inline-block; font-size:12px; color:#cbd5e1; background:rgba(255,255,255,.08);
    border:1px solid rgba(255,255,255,.14); padding:3px 10px; border-radius:7px; margin:0 6px 6px 0; }}
  .decide-score {{ text-align:right; }}
  .ds-val {{ font-size:34px; font-weight:800; color:#34d399; line-height:1; }}
  .ds-lbl {{ font-size:11px; color:rgba(255,255,255,.45); text-transform:uppercase; letter-spacing:.06em; }}
  .lead-pill {{ display:inline-block; margin-top:7px; font-size:12px; font-weight:600; color:#86efac;
    background:rgba(14,140,58,.2); border:1px solid rgba(14,140,58,.45); padding:3px 10px; border-radius:20px; }}
  .scen-row {{ display:flex; gap:12px; margin-top:16px; border-top:1px solid rgba(255,255,255,.1); padding-top:14px; }}
  .scen {{ flex:1; background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.12);
    border-radius:9px; padding:11px 13px; }}
  .scen-l {{ font-size:11px; font-weight:700; color:#93c5fd; text-transform:uppercase; letter-spacing:.04em; }}
  .scen-n {{ font-size:14px; font-weight:700; margin-top:4px; }}
  .scen-w {{ font-size:11.5px; color:rgba(255,255,255,.5); margin-top:3px; }}
  /* 市场结构 */
  .stat-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
  .stat {{ background:#f8fafc; border:1px solid #eef2f7; border-radius:10px; padding:14px 16px; }}
  .stat-v {{ font-size:26px; font-weight:800; color:{navy}; line-height:1; }}
  .stat-v span {{ font-size:13px; color:#9ba8bb; font-weight:500; }}
  .stat-l {{ font-size:12.5px; color:#5a6780; margin-top:6px; }}
  .note {{ background:#f0faf4; border-left:4px solid {green}; padding:11px 14px; border-radius:0 8px 8px 0;
    font-size:13.5px; color:#374151; margin-top:14px; }}
  .note b {{ color:{green}; }}
  /* 档案 */
  .dossier-head {{ display:flex; align-items:center; justify-content:space-between;
    background:#f8fafc; border:1px solid #eef2f7; border-radius:10px; padding:14px 18px; margin-bottom:16px; }}
  .dh-name {{ font-size:18px; font-weight:800; color:{navy}; }}
  .dh-score {{ font-size:30px; font-weight:800; }}
  .dh-score span {{ font-size:14px; color:#9ba8bb; }}
  .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
  table.info {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.info th {{ text-align:left; color:#5a6780; font-weight:500; padding:5px 10px 5px 0;
    white-space:nowrap; vertical-align:top; width:96px; }}
  table.info td {{ padding:5px 0; color:#1a2233; border-bottom:1px solid #f1f5f9; }}
  .dim {{ display:flex; align-items:center; gap:10px; margin-bottom:9px; font-size:13px; }}
  .dim-l {{ width:120px; }}
  .dim-w {{ color:#9ba8bb; font-size:11px; }}
  .bar {{ flex:1; height:8px; background:#e2e8f0; border-radius:4px; }}
  .bar-f {{ height:100%; border-radius:4px; }}
  .dim-v {{ width:34px; text-align:right; font-weight:700; }}
  .cbs {{ display:flex; flex-wrap:wrap; gap:7px; }}
  .cb {{ font-size:12px; padding:3px 10px; border-radius:7px; border:1px solid; }}
  .cb.on {{ color:{green}; background:#f0faf4; border-color:rgba(14,140,58,.3); }}
  .cb.off {{ color:#9ca3af; background:#f9fafb; border-color:#e5e7eb; }}
  .scope {{ font-size:12.5px; color:#374151; background:#f9fafb; border:1px solid #eef2f7;
    border-radius:8px; padding:12px 14px; line-height:1.7; }}
  /* 对比表 */
  table.cmp {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  table.cmp th {{ background:{navy}; color:#fff; padding:9px 8px; font-weight:600; text-align:center; }}
  table.cmp td {{ padding:8px; text-align:center; border-bottom:1px solid #eef2f7; }}
  table.cmp td.nm {{ text-align:left; font-weight:600; color:{navy}; }}
  table.cmp td.rk {{ font-size:15px; }}
  table.cmp td.tot {{ font-weight:800; font-size:14px; }}
  table.cmp tr.row-top {{ background:#f0faf4; }}
  table.cmp tr:nth-child(even):not(.row-top) {{ background:#fafbfc; }}
  /* 声明 */
  .links {{ list-style:none; padding:0; margin:0 0 14px; font-size:13px; color:#374151; }}
  .links li {{ padding:5px 0; border-bottom:1px dashed #e5e7eb; }}
  .disclaim {{ font-size:12px; color:#6b7280; background:#f9fafb; border:1px solid #eef2f7;
    border-radius:8px; padding:12px 14px; line-height:1.8; }}
  .sign {{ text-align:center; font-size:11.5px; color:#9ba8bb; margin-top:18px; }}
  @media print {{ body {{ background:#fff; }} .sheet {{ box-shadow:none; margin:0; max-width:none; border-radius:0; }} }}
</style></head>
<body><div class="sheet">{body}</div></body></html>
"""
