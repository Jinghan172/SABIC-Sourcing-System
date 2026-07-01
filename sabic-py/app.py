"""
SABIC 上海在线寻源系统 — Python / Streamlit 版
运行方式: streamlit run app.py

v3.0 改版：
- 移除全部演示数据（拜尔上海等虚拟企业）与 SABIC 历史合作内容
- 评分三维化（地理/规模/合规，全部可量化），移除相关性与专利评分
- 搜索移到主区域：输入英文代码/中文即联想缓存品类（与 local_cache JSON 一一对应），
  未缓存品类自动落到企查查实时 API
"""
from pathlib import Path as _Path
from dotenv import load_dotenv as _load
_load(_Path(__file__).parent / ".env.local", override=False)

import json
import re
from pathlib import Path
import streamlit as st
import pandas as pd

from utils.matcher import match_suppliers, LAST_SEARCH_META
from utils import sites
from utils.sabic_search import SABIC_SEARCH_STRATEGIES, get_category_priority
from utils.local_search import list_cache_categories, cache_status
from utils.scorer import DEFAULT_WEIGHTS, has_hazmat_license, _IND_CHEM, _IND_MFG
from utils.exporter import export_excel
from export_master import build_master
from utils.insights import decision_summary, supply_landscape, why_not_top
from components.charts import (
    radar_chart, bar_chart, bubble_chart,
    parallel_chart, heatmap_chart, compare_dataframe, china_map,
)
from components.core_materials import (
    render_core_cards, render_core_report, get_material, CORE_CSS,
)
from components.services import (
    render_service_cards, render_service_report, SERVICES_CSS,
)
from components.equipment import (
    render_equipment_cards, render_equipment_report, EQUIPMENT_CSS,
)
from components import home as home_nav
from components.home import HOME_CSS
from components.comparison import COMPARISON_CSS
from components.pricing import PRICING_CSS

APP_DIR = Path(__file__).resolve().parent

# 三类最核心物料：关键词 → 物料 key（用于搜索时直接路由到专家评审报告）
_CORE_KEYWORDS = {
    "TiO2":   ["tio2", "钛白粉", "氯化法钛白粉", "二氧化钛"],
    "FFS":    ["ffs", "ffs膜", "ffs重载塑料膜", "重载塑料膜", "重载膜"],
    "Pallet": ["pallet", "木托盘", "出口级木托盘", "托盘"],
}
# 这些品类已升级为"最核心物料"，从普通缓存品类列表/联想中移除（改走专家报告）
_CORE_HIDE_FILES = {"TiO2.json", "Pallet.json", "FlexPack.json"}


def _core_key_for(text: str) -> str | None:
    """输入文本若命中核心物料关键词，返回其 key，否则 None。"""
    t = (text or "").strip().lower()
    if not t:
        return None
    for key, kws in _CORE_KEYWORDS.items():
        if any(t == kw for kw in kws):
            return key
    return None

# ── 品类别名表（知识库辅助联想，不影响企查查数据）─────────────────────
try:
    with open(APP_DIR / "data" / "category_aliases.json", encoding="utf-8") as _af:
        _ALIASES: dict[str, list[str]] = {
            k: v for k, v in json.load(_af).items() if not k.startswith("_")
        }
except Exception:
    _ALIASES = {}


def _suggest_categories(text: str, max_n: int = 8) -> list[dict]:
    """
    输入英文代码/中文/别名片段，返回联想品类列表（每项 1:1 对应一个缓存 JSON 文件）。
    排序：精确命中 > 前缀 > 包含 > 别名精确 > 别名包含；同级内 P1 品类优先、收录企业多者优先。
    """
    q = (text or "").strip()
    if not q:
        return []
    ql = q.lower()
    ranked = []
    for cat in list_cache_categories():
        if cat["file"] in _CORE_HIDE_FILES:
            continue  # 核心物料改走专家报告，不在普通联想中出现
        en_l, cn = cat["en"].lower(), cat["cn"]
        aliases = _ALIASES.get(cat["en"], [])
        rank = None
        if ql == en_l or q == cn:
            rank = 0
        elif en_l.startswith(ql) or cn.startswith(q):
            rank = 1
        elif ql in en_l or q in cn:
            rank = 2
        elif any(ql == a.lower() for a in aliases):
            rank = 3
        elif any(ql in a.lower() for a in aliases):
            rank = 4
        if rank is not None:
            prio = SABIC_SEARCH_STRATEGIES.get(cn, {}).get("priority", 2)
            ranked.append((rank, prio, -cat["count"], cat))
    ranked.sort(key=lambda x: x[:3])
    return [c for _, _, _, c in ranked[:max_n]]


def _number_value(value) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _highlight_row_max(row):
    values = [_number_value(v) for v in row.values if v not in ("—", "")]
    values = [v for v in values if v is not None]
    if not values:
        return ["" for _ in row.values]

    max_value = max(values)
    return [
        "background-color:#f0faf4;color:#0E8C3A;font-weight:bold"
        if _number_value(v) == max_value else ""
        for v in row.values
    ]


def _side_head(icon: str, title: str) -> None:
    """侧栏分区标题：渐变竖条 + 图标 + 标题，与主区设计统一。"""
    st.markdown(
        f'<div class="side-head"><span class="sb-bar"></span>'
        f'<span class="sb-ico">{icon}</span>'
        f'<span class="sb-title">{title}</span></div>',
        unsafe_allow_html=True,
    )


# ── 页面配置 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SABIC Sourcing · 寻源系统",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局样式注入 ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 整体画布：柔和渐变底，提升质感 ───────────────────── */
.stApp {
    background:
      radial-gradient(900px 420px at 88% -8%, rgba(14,140,58,.06), transparent 60%),
      radial-gradient(720px 360px at -5% 4%, rgba(59,130,246,.05), transparent 55%),
      linear-gradient(180deg,#f3f6fb 0%, #eaeef5 100%);
}

/* ── 放大正文字号，整体更易读 ─────────────────────────── */
.block-container p, .block-container li, .block-container label,
.stMarkdown, .stMarkdown p, .stMarkdown li,
.stRadio label, .stCheckbox label, .stSelectbox label, .stMultiSelect label,
.stTextInput label, .stSlider label, .stNumberInput label {
    font-size: 15.5px !important;
}
.stTextInput input, .stNumberInput input { font-size: 15.5px !important; }
.block-container h3 { font-size: 20px !important; font-weight: 700; letter-spacing:.2px; }
.stCaption, [data-testid="stCaptionContainer"] { font-size: 13px !important; }

/* ── 选项卡更大更清晰 ─────────────────────────────────── */
button[data-baseweb="tab"] { font-size: 14.5px !important; padding: 6px 4px !important; }
button[data-baseweb="tab"] [data-testid="stMarkdownContainer"] p { font-size:14.5px !important; }

/* ── 按钮：更圆润、更有分量 ───────────────────────────── */
.stButton > button, .stDownloadButton > button {
    border-radius: 9px !important; font-weight: 600 !important; font-size: 14px !important;
    white-space: nowrap !important;
    transition: transform .12s ease, box-shadow .12s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-1px);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: linear-gradient(135deg,#0E8C3A,#27a84f) !important;
    border: none !important; box-shadow: 0 4px 14px rgba(14,140,58,.28) !important;
}

/* ── 侧栏标题 ─────────────────────────────────────────── */
section[data-testid="stSidebar"] .stMarkdown h3 { font-size: 16.5px !important; }
section[data-testid="stSidebar"] { background: #fbfcfe; }

/* ── 指标卡（st.metric）放大 ─────────────────────────── */
[data-testid="stMetricValue"] { font-size: 26px !important; }
[data-testid="stMetricLabel"] p { font-size: 13.5px !important; }

/* Hero 顶部横幅 */
.sabic-hero {
    background:
      radial-gradient(120% 140% at 92% -20%, rgba(16,185,129,.22) 0%, transparent 45%),
      radial-gradient(90% 120% at 8% 120%, rgba(59,130,246,.18) 0%, transparent 50%),
      linear-gradient(135deg,#071120 0%,#0d1d36 55%,#0a182c 100%);
    padding: 40px 44px 30px;
    border-radius: 18px;
    margin: -.4rem -.2rem 1.4rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 18px 48px -18px rgba(7,17,32,.55),
                inset 0 1px 0 rgba(255,255,255,.05);
}
/* 细网格肌理 */
.sabic-hero::before {
    content:'';
    position:absolute;inset:0;
    background:repeating-linear-gradient(0deg,transparent,transparent 33px,
        rgba(255,255,255,0.022) 33px,rgba(255,255,255,0.022) 34px),
        repeating-linear-gradient(90deg,transparent,transparent 33px,
        rgba(255,255,255,0.022) 33px,rgba(255,255,255,0.022) 34px);
    -webkit-mask-image:radial-gradient(120% 100% at 50% 0%,#000 35%,transparent 80%);
            mask-image:radial-gradient(120% 100% at 50% 0%,#000 35%,transparent 80%);
    pointer-events:none;
}
/* 右上发光光晕 */
.sabic-hero::after {
    content:'';position:absolute;top:-90px;right:-60px;
    width:340px;height:340px;border-radius:50%;
    background:radial-gradient(circle,rgba(16,185,129,.30),transparent 68%);
    filter:blur(14px);pointer-events:none;
}
.hero-inner { position:relative;z-index:1; }
.hero-badge {
    display:inline-flex;align-items:center;gap:8px;
    padding:5px 15px;border-radius:30px;
    background:rgba(16,185,129,.12);
    border:1px solid rgba(94,234,212,.32);
    backdrop-filter:blur(6px);
    font-size:11.5px;font-weight:700;letter-spacing:.16em;
    text-transform:uppercase;color:#5eead4;margin-bottom:18px;
}
.hero-badge .pulse {
    width:7px;height:7px;border-radius:50%;background:#34d399;
    box-shadow:0 0 0 0 rgba(52,211,153,.6);
    animation:heroPulse 2s infinite;
}
@keyframes heroPulse {
    0%{box-shadow:0 0 0 0 rgba(52,211,153,.55);}
    70%{box-shadow:0 0 0 8px rgba(52,211,153,0);}
    100%{box-shadow:0 0 0 0 rgba(52,211,153,0);}
}
.hero-title {
    font-size:36px;font-weight:300;color:rgba(255,255,255,.78);
    margin:0 0 12px;letter-spacing:.4px;line-height:1.28;max-width:880px;
}
.hero-title .lead { font-weight:300;color:rgba(255,255,255,.72); }
.hero-title .key {
    font-weight:800;
    background:linear-gradient(100deg,#5eead4 0%,#34d399 48%,#86efac 100%);
    -webkit-background-clip:text;background-clip:text;
    -webkit-text-fill-color:transparent;color:#34d399;
    text-shadow:0 4px 28px rgba(52,211,153,.25);
    white-space:nowrap;
}
.hero-sub { font-size:15px;color:rgba(255,255,255,.55);margin-bottom:26px;
    line-height:1.65;max-width:780px; }
.hero-sub b { color:#5eead4;font-weight:600; }
.hero-stats { display:flex;gap:0;border-top:1px solid rgba(255,255,255,.08);
    padding-top:20px;margin-top:6px; }
.hero-stat { padding:0 30px;position:relative; }
.hero-stat:first-child { padding-left:0; }
.hero-stat:not(:last-child)::after {
    content:'';position:absolute;right:0;top:6px;bottom:2px;
    width:1px;background:rgba(255,255,255,.08);
}
.hero-stat-val { font-size:28px;font-weight:800;color:#fff;line-height:1;
    letter-spacing:-.5px; }
.hero-stat-val.g { color:#34d399; }
.hero-stat-val.b { color:#60a5fa; }
.hero-stat-val.t { color:#5eead4; }
.hero-stat-lbl { font-size:11px;color:rgba(255,255,255,.42);
    text-transform:uppercase;letter-spacing:.1em;margin-top:7px;font-weight:600; }

/* 搜索区标题（与 hero 呼应）*/
.search-head { display:flex;align-items:center;gap:13px;margin:2px 0 14px; }
.search-head .s-bar {
    width:4px;height:30px;border-radius:4px;
    background:linear-gradient(180deg,#5eead4,#0E8C3A);
    box-shadow:0 2px 10px rgba(14,140,58,.35);
}
.search-head .s-txt { display:flex;flex-direction:column;line-height:1.2; }
.search-head .s-title { font-size:20px;font-weight:800;color:#0f1f38;letter-spacing:.3px; }
.search-head .s-sub { font-size:12.5px;color:#7c8aa0;margin-top:2px;font-weight:500; }
.search-head .s-pill {
    margin-left:auto;display:inline-flex;align-items:center;gap:6px;
    padding:5px 14px;border-radius:30px;
    background:linear-gradient(135deg,rgba(14,140,58,.10),rgba(59,130,246,.08));
    border:1px solid rgba(14,140,58,.22);
    font-size:12px;font-weight:600;color:#0E8C3A;
}
.search-head .s-pill .dot { background:#0E8C3A; }

/* 侧栏分区标题（紧凑版竖条风格）*/
.side-head { display:flex;align-items:center;gap:10px;margin:6px 0 10px; }
.side-head .sb-bar {
    width:3.5px;height:18px;border-radius:4px;
    background:linear-gradient(180deg,#5eead4,#0E8C3A);
    box-shadow:0 1px 6px rgba(14,140,58,.30);
}
.side-head .sb-ico { font-size:14px;line-height:1; }
.side-head .sb-title { font-size:15px;font-weight:800;color:#0f1f38;letter-spacing:.2px; }

/* API 状态条 */
.api-bar {
    display:flex;align-items:center;gap:10px;flex-wrap:wrap;
    padding:10px 16px;background:#fff;border:1px solid #e6ebf2;
    border-radius:10px;margin-bottom:14px;font-size:13px;
    box-shadow:0 1px 4px rgba(15,30,60,.04);
}
.api-lbl { font-weight:700;text-transform:uppercase;
    letter-spacing:.06em;color:#9ba8bb;margin-right:4px;font-size:11.5px; }
.api-chip {
    display:inline-flex;align-items:center;gap:5px;
    padding:4px 12px;border-radius:20px;font-size:12.5px;font-weight:500;
    border:1px solid;cursor:default;
}
.api-chip.on { background:rgba(14,140,58,.10);
    border-color:rgba(14,140,58,.4);color:#0E8C3A; }
.api-chip.off { background:rgba(156,163,175,.08);
    border-color:rgba(156,163,175,.25);color:#9ca3af; }
.dot { width:5px;height:5px;border-radius:50%;background:currentColor;
    display:inline-block; }

/* 供应商卡片 */
.sup-card {
    background:#fff;border:1px solid #e2e8f0;border-radius:10px;
    padding:12px 14px;margin-bottom:8px;cursor:pointer;
    transition:all .2s;position:relative;overflow:hidden;
}
.sup-card:hover { box-shadow:0 4px 12px rgba(0,0,0,.08);
    border-color:rgba(14,140,58,.25);transform:translateY(-1px); }
.sup-rank {
    display:inline-flex;align-items:center;justify-content:center;
    width:26px;height:26px;border-radius:6px;
    background:linear-gradient(135deg,#0E8C3A,#27a84f);
    color:#fff;font-weight:700;font-size:12px;flex-shrink:0;
}
.sup-name { font-weight:600;font-size:14.5px;color:#1a2233; }
.sup-meta { font-size:12.5px;color:#5a6780;margin-top:2px; }
.score-high { color:#059669;font-weight:700; }
.score-mid  { color:#d97706;font-weight:700; }
.score-low  { color:#dc2626;font-weight:700; }
.tier-t1 { background:rgba(14,140,58,.1);color:#0E8C3A;
    border:1px solid rgba(14,140,58,.2);padding:2px 9px;
    border-radius:5px;font-size:11.5px;font-weight:600; }
.tier-t2 { background:rgba(59,130,246,.1);color:#3b82f6;
    border:1px solid rgba(59,130,246,.2);padding:2px 9px;
    border-radius:5px;font-size:11.5px;font-weight:600; }
.tier-t3 { background:rgba(139,92,246,.1);color:#7c3aed;
    border:1px solid rgba(139,92,246,.2);padding:2px 9px;
    border-radius:5px;font-size:11.5px;font-weight:600; }

/* ── 智能采购决策卡 ───────────────────────────────────── */
.decide-wrap {
    background:linear-gradient(135deg,#0a1628 0%,#10243f 100%);
    border:1px solid rgba(94,234,212,.25);
    border-radius:14px;padding:18px 20px;margin:6px 0 14px;
    position:relative;overflow:hidden;
}
.decide-wrap::after{
    content:'';position:absolute;top:-40px;right:-30px;width:180px;height:180px;
    background:radial-gradient(circle,rgba(14,140,58,.25),transparent 70%);
    pointer-events:none;
}
.decide-kicker{
    font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
    color:#5eead4;margin-bottom:10px;display:flex;align-items:center;gap:6px;
}
.decide-top{display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap;}
.decide-medal{
    width:48px;height:48px;border-radius:12px;flex-shrink:0;
    background:linear-gradient(135deg,#facc15,#f59e0b);
    display:flex;align-items:center;justify-content:center;font-size:24px;
    box-shadow:0 4px 14px rgba(245,158,11,.4);
}
.decide-name{font-size:19px;font-weight:700;color:#fff;line-height:1.25;}
.decide-why{font-size:12.5px;color:rgba(255,255,255,.62);margin-top:3px;}
.decide-score-box{margin-left:auto;text-align:right;}
.decide-score{font-size:30px;font-weight:800;color:#34d399;line-height:1;}
.decide-score-lbl{font-size:10px;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:.06em;}
.decide-lead{
    display:inline-block;margin-top:5px;font-size:11px;font-weight:600;
    color:#86efac;background:rgba(14,140,58,.18);
    border:1px solid rgba(14,140,58,.4);padding:2px 9px;border-radius:20px;
}
.decide-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;}
.decide-tag{
    font-size:11px;color:#cbd5e1;background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.12);padding:2px 9px;border-radius:6px;
}
.scen-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;
    border-top:1px solid rgba(255,255,255,.08);padding-top:12px;}
.scen-card{
    flex:1;min-width:150px;background:rgba(255,255,255,.04);
    border:1px solid rgba(255,255,255,.1);border-radius:9px;padding:9px 11px;
}
.scen-label{font-size:10px;font-weight:600;letter-spacing:.05em;color:#93c5fd;
    text-transform:uppercase;margin-bottom:3px;}
.scen-name{font-size:13px;font-weight:600;color:#f1f5f9;line-height:1.3;}
.scen-why{font-size:10.5px;color:rgba(255,255,255,.45);margin-top:2px;}

/* ── 供应市场结构条 ───────────────────────────────────── */
.land-bar{
    display:flex;flex-wrap:wrap;gap:0;background:#fff;border:1px solid #e2e8f0;
    border-radius:10px;overflow:hidden;margin-bottom:14px;
}
.land-cell{flex:1;min-width:96px;padding:10px 14px;border-right:1px solid #eef2f7;}
.land-cell:last-child{border-right:none;}
.land-val{font-size:20px;font-weight:700;color:#0a1628;line-height:1;}
.land-val .u{font-size:12px;font-weight:500;color:#9ba8bb;}
.land-lbl{font-size:10.5px;color:#5a6780;margin-top:4px;}
.land-note{width:100%;background:#f8fafc;border-top:1px solid #eef2f7;
    padding:7px 14px;font-size:11.5px;color:#5a6780;}
.land-note b{color:#0E8C3A;}

/* ── 为什么不是它 ───────────────────────────────────── */
.wn-box{border-radius:10px;padding:12px 14px;margin:2px 0 10px;border:1px solid;}
.wn-box.top{background:#f0faf4;border-color:rgba(14,140,58,.3);}
.wn-box.lag{background:#fffbeb;border-color:#fcd34d;}
.wn-box.role{background:#eff6ff;border-color:#bfdbfe;}
.wn-verdict{font-size:13.5px;font-weight:700;color:#0a1628;display:flex;align-items:center;gap:7px;}
.wn-narr{font-size:12px;color:#5a6780;margin-top:5px;line-height:1.55;}
.wn-cmp{display:flex;gap:8px;margin-top:9px;}
.wn-dim{flex:1;background:rgba(255,255,255,.6);border:1px solid rgba(0,0,0,.05);
    border-radius:7px;padding:6px 8px;text-align:center;}
.wn-dim-lbl{font-size:10px;color:#5a6780;}
.wn-dim-vs{font-size:13px;font-weight:700;margin-top:2px;}
.wn-scen{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;}
.wn-scen-chip{font-size:11px;font-weight:600;color:#1d4ed8;background:#dbeafe;
    border:1px solid #bfdbfe;padding:2px 9px;border-radius:20px;}

/* 前三名奖牌 */
.medal-rank{
    display:inline-flex;align-items:center;justify-content:center;
    width:26px;height:26px;border-radius:6px;font-weight:700;font-size:13px;flex-shrink:0;
}
.medal-1{background:linear-gradient(135deg,#facc15,#f59e0b);color:#fff;box-shadow:0 2px 7px rgba(245,158,11,.35);}
.medal-2{background:linear-gradient(135deg,#cbd5e1,#94a3b8);color:#fff;}
.medal-3{background:linear-gradient(135deg,#fcd9b6,#d9a066);color:#fff;}

/* 移除 Streamlit 默认上方空白 */
.block-container { padding-top: 0.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ── 状态初始化 ────────────────────────────────────────────────────────
def _init():
    defaults = {
        "query": "",
        "filters": {
            "provinces":     [],
            "tiers":         [],
            "status_active": True,
            "company_type":  "factory_first",
            "min_capital":   0,
            "est_after":     1990,
            "only_hazmat":   False,
            "scope_keyword": "",
            "min_score":     0,
        },
        "weights": dict(DEFAULT_WEIGHTS),
        "selected_ids": [],
        "active_supplier": None,
        "chart_tab": "radar",
        "core_material": None,
        "service_cat": None,
        "equipment_cat": None,
        "equip_plant": None,
        "site": "SH",
        "lane": None,
        "svc_plant": "SH",
        "svc_weights": None,
        "eq_weights": None,
        "svc_filters": {},
        "eq_filters": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # 旧会话可能残留四维权重（含 relevance），重置为三维默认
    if set(st.session_state.weights.keys()) - {"geography", "scale", "compliance"}:
        st.session_state.weights = dict(DEFAULT_WEIGHTS)

_init()

# ── 核心物料样式 + 专家评审报告拦截 ──────────────────────────────────
st.markdown(CORE_CSS, unsafe_allow_html=True)
st.markdown(SERVICES_CSS, unsafe_allow_html=True)
st.markdown(EQUIPMENT_CSS, unsafe_allow_html=True)
st.markdown(HOME_CSS, unsafe_allow_html=True)
st.markdown(COMPARISON_CSS, unsafe_allow_html=True)
st.markdown(PRICING_CSS, unsafe_allow_html=True)

# ── 厂区 / 缓存状态：侧栏与报告拦截都要用，需在拦截前算好 ──
_site_key = st.session_state.get("site", "SH")
_site = sites.get_site(_site_key)
_cs = cache_status()

def _infer_active_lane() -> str | None:
    if st.session_state.get("core_material"):  return "core"
    if st.session_state.get("service_cat"):    return "mro"
    if st.session_state.get("equipment_cat"):  return "equipment"
    if st.session_state.get("query"):          return "material"
    return st.session_state.get("lane")

_active_lane = _infer_active_lane()


def _render_lane_sidebar(lane: str | None) -> None:
    """非原料大类的侧栏：服务 / 设备各自的权重滑块 + 专属筛选。"""
    if lane == "mro":
        from utils.services_scorer import DIM_KEYS as _K, DIM_CN as _CN, DIM_EN as _EN, DEFAULT_WEIGHTS as _DW
        from components.services import get_service as _get_svc
        _side_head("⚖️", "Service Scoring Weights · 服务评分权重")
        st.caption("Drag the 5 weights to re-rank suppliers live (auto-normalized). "
                   "Switching category loads its designed weights.  \n"
                   "拖动 5 维权重，服务商排名实时重排（自动归一化）。切换品类自动载入其设计权重。")
        _cat = st.session_state.get("service_cat")
        if _cat and st.session_state.get("svc_weights_cat") != _cat:
            _seed = (_get_svc(_cat) or {}).get("weights") or _DW
            for k in _K:
                st.session_state[f"svcw_{k}"] = int(_seed.get(k, _DW[k]))
            st.session_state.svc_weights_cat = _cat
        _vals = {k: st.slider(f"{_EN[k]} · {_CN[k]}", 0, 100, int(_DW[k]), 2, key=f"svcw_{k}")
                 for k in _K}
        if st.button("↺ Restore designed weights · 恢复该品类设计权重", key="svcw_reset", width="stretch"):
            for k in _K:
                st.session_state.pop(f"svcw_{k}", None)
            st.session_state.svc_weights_cat = None   # 触发按品类重新载入设计权重
            st.session_state.svc_weights = None
            st.rerun()
        st.session_state.svc_weights = _vals
        st.divider()
        _side_head("🔎", "Service Filters · 服务筛选")
        _topt = {"National top platform · 全国头部平台": "national_top",
                 "Regional leader · 区域龙头": "regional",
                 "Local vendor · 属地厂商": "local"}
        _sel = st.multiselect("Scale tier · 规模圈层", list(_topt.keys()), key="svcf_tiers",
                              placeholder="Any · 不限")
        _po = st.checkbox("Strategic primary per base only · 仅看各基地战略首选", key="svcf_primary")
        st.session_state.svc_filters = {
            "tiers": [_topt[s] for s in _sel] if _sel else None, "primary_only": _po}

    elif lane == "equipment":
        from utils.equipment_scorer import DIM_KEYS as _K, DIM_CN as _CN, DIM_EN as _EN, DEFAULT_WEIGHTS as _DW
        _side_head("⚖️", "Equipment Scoring Weights · 设备评分权重")
        st.caption("Drag the 5 weights to re-rank suppliers live (auto-normalized).  \n"
                   "拖动 5 维权重，供应商排名实时重排（自动归一化）。")
        _cur = st.session_state.get("eq_weights") or dict(_DW)
        _vals = {k: st.slider(f"{_EN[k]} · {_CN[k]}", 0, 100, int(_cur.get(k, _DW[k])), 2, key=f"eqw_{k}")
                 for k in _K}
        if st.button("↺ Restore default weights · 恢复默认权重", key="eqw_reset", width="stretch"):
            for k in _K:
                st.session_state.pop(f"eqw_{k}", None)
            st.session_state.eq_weights = None
            st.rerun()
        st.session_state.eq_weights = _vals
        st.divider()
        _side_head("🔎", "Equipment Filters · 设备筛选")
        _lo = st.checkbox("Local suppliers only · 仅看属地供应商", key="eqf_local")
        _qs = st.multiselect("Qualifications · 资质要求",
                             ["A1", "A2", "API Q1", "ISO 9001", "CE", "特种设备制造许可证（A级）", "OEM 原厂认证"],
                             key="eqf_quals", placeholder="Any · 不限")
        _ml = st.slider("Max acceptable lead time (days) · 最长可接受交期（天）", 30, 200, 200, 10, key="eqf_lead")
        st.session_state.eq_filters = {
            "local_only": _lo, "quals": _qs or None,
            "max_lead": _ml if _ml < 200 else None}

    elif lane == "core":
        _side_head("⚖️", "Scoring Notes · 评分说明")
        st.caption("Strategic raw materials use a 6-dimension expert review model "
                   "(capacity / qualification / technology / locality / scale / compliance). "
                   "Weights are fixed inside the expert report for due-diligence authority; "
                   "no sliders for now.  \n"
                   "核心原材料采用 6 维专家评审模型（产能 / 资质 / 技术 / 属地 / 规模 / 合规），"
                   "权重在专家报告内固定标定以体现尽调权威性，暂不开放滑块。")
    else:
        _side_head("🧭", "Procurement Category · 采购大类")
        st.caption("Pick a procurement category in the main area first (Strategic / Production "
                   "materials / Services MRO / Equipment); the sidebar will show that category's "
                   "own scoring weights and filters.  \n"
                   "请在主区先选择采购大类（核心原料 / 其他原料 / 服务 MRO / 化工设备），"
                   "侧栏会显示该大类专属的评分权重与筛选项。")


with st.sidebar:
    if _active_lane == "material":
        # ── 采购厂区（决定地理评分锚点）─────────────────────────────────
        _side_head("🏭", "Procurement Plant · 采购厂区")
        st.markdown(
            f"<div style='background:#f3fbf6;border:1px solid #cfeede;border-radius:9px;"
            f"padding:9px 12px;font-size:13px;color:#15603a'>"
            f"Current · 当前：<b>{_site['cn']}</b> · {_site['cluster']}<br>"
            f"<span style='font-size:11.5px;color:#5a6780'>Tier-1 ring · 一级圈：{'、'.join(_site['home'])}</span></div>",
            unsafe_allow_html=True,
        )
        st.caption("Choose the plant on the four-plant map inside a Production-material item page; "
                   "services / equipment are chosen within their own reports.  \n"
                   "厂区在「其他原料」品类页的四大工厂大地图上选择；服务 / 设备在各自报告内选择。")
        st.divider()

        # ── 筛选器 ──────────────────────────────────────────────────────
        _side_head("🔎", "Filters · 筛选条件")
        f = st.session_state.filters

        with open(APP_DIR / "data" / "regions.json", encoding="utf-8") as _f:
            _regions = json.load(_f)

        # ▶ 地域筛选（圈层随所选厂区动态划定）
        with st.expander("📍 Region · 地域", expanded=True):
            _home_s = "、".join(_site["home"][:4]) + ("…" if len(_site["home"]) > 4 else "")
            tier_options = {
                f"Tier-1 一级（{_site['cluster']}：{_home_s}）": 1,
                f"Tier-2 二级（{_site['cluster']}周边）": 2,
                "Tier-3 三级（其余外省）": 3,
            }
            sel_tier_labels = st.multiselect(
                "Geographic ring · 地理圈层", list(tier_options.keys()),
                default=[k for k, v in tier_options.items() if v in f.get("tiers", [])],
                placeholder="Any · 不限",
            )
            sel_tiers = [tier_options[l] for l in sel_tier_labels]

            _all_p = list(_regions.get("provinceCoords", {}).keys())
            tier1_p = _site["home"]
            tier2_p = _site["near"]
            tier3_p = [p for p in _all_p if p not in tier1_p and p not in tier2_p]
            if sel_tiers:
                pool = []
                if 1 in sel_tiers: pool += tier1_p
                if 2 in sel_tiers: pool += tier2_p
                if 3 in sel_tiers: pool += tier3_p
            else:
                pool = tier1_p + tier2_p + tier3_p

            sel_provinces = st.multiselect(
                "Provinces (multi-select) · 省份（支持多选）", pool,
                default=[p for p in f.get("provinces", []) if p in pool],
                placeholder="Any (nationwide) · 不限（全国）",
            )

        # ▶ 企业信息（来自企查查）
        with st.expander("🏢 Company Info · 企业信息", expanded=True):
            status_active = st.checkbox(
                "Active/operating companies only · 仅展示存续/在业企业",
                value=f.get("status_active", True),
                help="Filters out deregistered, revoked, moved-out, etc.  \n过滤掉注销、吊销、迁出等状态企业",
            )
            company_type = st.radio(
                "Company type (intermediaries excluded by default) · 企业类型（默认排除纯中介）",
                options=["factory_first", "manufacturer", "all"],
                format_func=lambda x: {
                    "factory_first": "Factory first (recommended) · 工厂优先（推荐）",
                    "manufacturer":  "Factories only · 只看工厂",
                    "all":           "All (incl. traders) · 全部（含贸易商）",
                }[x],
                index=["factory_first","manufacturer","all"].index(
                    f.get("company_type","factory_first")
                    if f.get("company_type") in ("factory_first","manufacturer","all") else "factory_first"),
            )
            min_capital = st.number_input(
                "Min. registered capital (10k CNY) · 最低注册资本（万元）",
                min_value=0, max_value=100_000,
                value=int(f.get("min_capital", 0)),
                step=100,
                help="0 = no limit; from QCC RegistCapi field  \n0 = 不限；来自企查查 RegistCapi 字段",
            )
            import datetime as _dt
            current_year = _dt.datetime.now().year
            est_after = st.slider(
                "Founded year ≥ · 成立年份 ≥",
                min_value=1980, max_value=current_year,
                value=f.get("est_after", 1990),
                help="From QCC StartDate field  \n来自企查查 StartDate 字段",
            )

        # ▶ 资质与行业
        with st.expander("📋 Qualifications & Keywords · 资质 & 关键词", expanded=False):
            only_hazmat = st.checkbox(
                "Has hazardous-chemicals business license · 含危险化学品经营资质",
                value=f.get("only_hazmat", False),
                help="Business scope contains hazardous-chemical keywords (negations like "
                     "'excluding hazardous chemicals' do not count)  \n"
                     "经营范围包含危险化学品关键词（'不含危化品'等否定表述不算）",
            )
            scope_keyword = st.text_input(
                "Extra keyword in business scope · 经营范围额外包含词",
                value=f.get("scope_keyword", ""),
                placeholder="e.g. 换热器 / ISO9001 / 出口",
                help="Exact match within QCC business-scope text  \n在企查查经营范围文本中精确匹配",
            )

        # ▶ 评分门槛
        with st.expander("🎯 Score Threshold · 评分门槛", expanded=False):
            min_score = st.slider(
                "Min. overall score · 最低综合评分",
                min_value=0, max_value=90,
                value=f.get("min_score", 0),
                step=5,
                help="Filters out companies below this score  \n过滤掉低于该分数的企业",
            )

        new_filters = {
            "provinces":     sel_provinces,
            "tiers":         sel_tiers,
            "status_active": status_active,
            "company_type":  company_type,
            "min_capital":   min_capital,
            "est_after":     est_after,
            "only_hazmat":   only_hazmat,
            "scope_keyword": scope_keyword,
            "min_score":     min_score,
        }
        if new_filters != st.session_state.filters:
            st.session_state.filters = new_filters
            st.rerun()

        st.divider()

        # ── 权重调节 ─────────────────────────────────────────────────────
        _side_head("⚖️", "Scoring Weights · 评分权重")
        st.caption("Each company's total = three scores × their weights. Drag sliders to "
                   "emphasize what you care about.  \n"
                   "每家企业的总分 = 三项分数 × 各自权重。拖动滑块调整你看重的方面。")

        with st.expander("📖 How is each score computed? (click) · 每个分数是怎么算出来的？", expanded=False):
            st.markdown(f"""
    **Total = Geography × weight + Scale × weight + Compliance × weight**
    (each scored out of 100; weights are the slider percentages on the right)
    **总分 = 地理 × 权重 + 规模 × 权重 + 合规 × 权重**
    （三项满分都是 100 分，权重就是右边滑块的百分比）

    ---

    **📍 Geography** — the closer to the **current plant ({_site['cn']})**, the higher
    - Distance & ring computed independently per selected plant (scores change when you switch plants)
    - {_site['cluster']} Tier-1 ring ({'、'.join(_site['home'])}) ≈ 95-100 pts
    - {_site['cluster']} Tier-2 surrounding ring ≈ 50-70 pts
    - Other provinces (Tier-3) ≈ 10-40 pts
    - Fine-tuned continuously by real km distance to {_site['short']}

    **📍 地理位置**　越靠近**当前厂区（{_site['cn']}）**，分越高
    - 距离与圈层都以所选厂区独立计算（切换厂区分数随之变化）
    - {_site['cluster']}一级圈（{'、'.join(_site['home'])}）≈ 95-100 分
    - {_site['cluster']}周边二级圈 ≈ 50-70 分
    - 其他外省（三级圈）≈ 10-40 分
    - 再根据距 {_site['short']} 的真实公里数连续微调

    **🏢 Scale** — the stronger, the higher
    - Registered capital: ≥1B = 100, 100M = 78, 10M = 50 pts
    - Years in business: ≥20y = 100, 10y = 70, 5y = 50 pts
    - Combined 65% : 35%

    **🏢 企业规模**　实力越强，分越高
    - 注册资本：10 亿以上 = 100 分，1 亿 = 78 分，1000 万 = 50 分
    - 成立年限：20 年以上 = 100 分，10 年 = 70 分，5 年 = 50 分
    - 两项按 65% : 35% 合并

    **✅ Compliance** — all from QCC business fields, summed item by item
    - Normal operating status (active) = 25 pts
    - Company role: factory 20 / factory+trade 16 / importer 8 / distributor 4 / intermediary 0
    - Hazardous-chemicals license (business scope; "excluding hazmat" doesn't count) = 20 pts
    - Production/safety license keywords = 10 pts
    - Chemical park 10 pts (general industrial park 5 pts)
    - Chemical industry 10 pts (other manufacturing 5 pts, per QCC industry classification)
    - Import/export business qualification = 5 pts

    **✅ 合规资质**　全部来自企查查工商字段，逐项累加
    - 经营状态正常（存续/在业）＝ 25 分
    - 企业角色：工厂 20 / 工厂兼贸易 16 / 进口商 8 / 经销商 4 / 中介 0
    - 危险化学品许可（经营范围，"不含危化品"不算）＝ 20 分
    - 生产/安全许可证关键词 ＝ 10 分
    - 化工园区 10 分（一般工业园区 5 分）
    - 化工类行业 10 分（其他制造业 5 分，看企查查行业分类）
    - 进出口经营资质 ＝ 5 分

    ---

    *All scores are computed automatically from QCC business data — no manual scoring.*
    *所有分数都从企查查的工商数据自动算出，没有人工打分。*
            """)

        w = st.session_state.weights
        w_geo  = st.slider("📍 Geography · 地理位置", 0, 100, int(w.get("geography", 0.35) * 100), 5,
                           help="Closer to Shanghai scores higher. Raise it if logistics cost matters.  \n"
                                "企业离上海越近分越高。看重物流成本就调高它。")
        w_scl  = st.slider("🏢 Scale · 企业规模", 0, 100, int(w.get("scale",    0.35) * 100), 5,
                           help="Larger capital and longer history score higher. Raise it if you value strength.  \n"
                                "注册资本越大、成立越久分越高。看重企业实力就调高它。")
        w_cmp  = st.slider("✅ Compliance · 合规资质", 0, 100, int(w.get("compliance",0.30) * 100), 5,
                           help="Full licenses, manufacturer status, chemical park score higher. Raise it if you value compliance.  \n"
                                "证照齐全、是制造商、在化工园区分越高。看重合规就调高它。")

        total_w = w_geo + w_scl + w_cmp
        if total_w > 0:
            new_weights = {
                "geography":  w_geo / total_w,
                "scale":      w_scl / total_w,
                "compliance": w_cmp / total_w,
            }
            if new_weights != st.session_state.weights:
                st.session_state.weights = new_weights
                st.rerun()
            st.caption("Auto-normalized to 100% · 已自动归一化，合计 100%")

        # 一键预设场景
        st.caption("Not sure how to tune? Just pick a scenario · 不知道怎么调？直接选一个场景：")
        pcol1, pcol2 = st.columns(2)
        if pcol1.button("⚖️ Balanced · 均衡推荐", width='stretch',
                        help="Geo 35 / Scale 35 / Compliance 30 — fits most cases  \n地理35 规模35 合规30，适合大多数情况"):
            st.session_state.weights = dict(DEFAULT_WEIGHTS)
            st.rerun()
        if pcol2.button("🚚 Proximity · 就近优先", width='stretch',
                        help="Emphasize geography — for urgent delivery / logistics-sensitive buys  \n加重地理位置，适合急需交付、看重物流的采购"):
            st.session_state.weights = {"geography":0.50,"scale":0.25,"compliance":0.25}
            st.rerun()
        pcol3, pcol4 = st.columns(2)
        if pcol3.button("🏆 Strength · 实力优先", width='stretch',
                        help="Emphasize scale — for bulk / long-term partnerships  \n加重企业规模，适合大宗、长期合作采购"):
            st.session_state.weights = {"geography":0.20,"scale":0.50,"compliance":0.30}
            st.rerun()
        if pcol4.button("🛡️ Compliance · 合规优先", width='stretch',
                        help="Emphasize compliance — for heavily-regulated categories like hazmat  \n加重合规资质，适合危化品等强监管品类"):
            st.session_state.weights = {"geography":0.20,"scale":0.30,"compliance":0.50}
            st.rerun()

    else:
        _render_lane_sidebar(_active_lane)
    st.divider()

    # ── 本地缓存状态 ────────────────────────────────────────────
    _side_head("📦", "Local Data Cache · 本地数据缓存")
    if _cs["count"] > 0:
        st.success(f"✓ **{_cs['count']}** categories cached — cache hits skip the API · "
                   f"已缓存 **{_cs['count']}** 个品类，搜索命中不调 API")
        with st.expander("View cached categories · 查看已缓存品类", expanded=False):
            st.caption("  ".join(_cs["files"]))
        st.caption("Data from the QCC MCP collection script (collect_local.py)  \n"
                   "数据来自企查查 MCP 采集脚本（collect_local.py）")
    else:
        st.warning("No local cache yet — all searches go through the QCC API · 暂无本地缓存，搜索全部走企查查 API")
        st.caption("Run collect_local.py to collect data for offline search  \n运行 collect_local.py 采集数据后可离线搜索")
    st.markdown("---")

    # ── 接口管理面板 ─────────────────────────────────────────────
    _side_head("🔌", "API Management · 接口管理")
    st.caption("Cache hits skip the API; uncached categories need the APIs below for live search.  \n"
               "本地缓存命中时不调 API；未缓存品类需开通以下接口实时搜索。")

    from utils.qcc_client import (is_configured as qcc_ok,
                                  is_qual_enabled, is_risk_enabled)
    _qcc  = qcc_ok()
    _qual = is_qual_enabled()
    _risk = is_risk_enabled()

    def _iface_row(order, name, code, on, mandatory, powers, cfg_hint):
        """渲染一个接口管理行"""
        if on:
            dot, dot_c, state = "●", "#0E8C3A", "Enabled · 已开通"
        elif mandatory:
            dot, dot_c, state = "●", "#d97706", "To configure · 待配置"
        else:
            dot, dot_c, state = "○", "#9ca3af", "Not enabled · 未开通"
        tag = ('<span style="background:#fee2e2;color:#dc2626;font-size:9px;'
               'padding:0 5px;border-radius:8px;margin-left:4px">Required for live search · 实时搜索必开</span>'
               if mandatory else
               '<span style="background:#f1f5f9;color:#64748b;font-size:9px;'
               'padding:0 5px;border-radius:8px;margin-left:4px">Optional · 可选</span>')
        st.markdown(
            f'<div style="border:1px solid #e2e8f0;border-radius:8px;'
            f'padding:8px 10px;margin:4px 0;background:white">'
            f'<div style="font-size:13px;font-weight:600;color:#0a1628">'
            f'<span style="color:{dot_c}">{dot}</span> '
            f'<span style="color:#9ba8bb;font-size:11px">{order}.</span> {name}{tag}</div>'
            f'<div style="font-size:11px;color:#5a6780;margin-top:3px">'
            f'<b>Used by · 对应网页：</b>{powers}</div>'
            f'<div style="font-size:11px;color:{dot_c};margin-top:2px">'
            f'Status · 状态：{state}'
            + (f' &nbsp;·&nbsp; <span style="color:#9ba8bb">{cfg_hint}</span>' if not on else "")
            + f'</div></div>',
            unsafe_allow_html=True,
        )

    _iface_row(1, "Company fuzzy search · 企业模糊搜索", "886", _qcc, True,
               "Uncached categories → live supplier list · 未缓存品类 → 实时搜索供应商列表",
               "Fill QCC_APP_KEY / SECRET · 填 QCC_APP_KEY / SECRET")
    _iface_row(2, "Company business info · 企业工商信息", "410", _qcc, True,
               "Live supplier details + 3-dimension scoring · 实时搜索的供应商详情 + 三维评分",
               "Same as above (same key) · 同上（同一组 Key）")
    _iface_row(3, "Qualification certs (255) · 资质证书", "0.3元", _qual, False,
               "Detail card 「📜 Cert verification · 资质证书核验」· auto-loads on opening details · 打开详情自动加载",
               "Fill QCC_QUAL_ENDPOINT · 填 QCC_QUAL_ENDPOINT")
    _iface_row(4, "Risk scan (736) · 风险扫描", "6元", _risk, False,
               "Detail card 「⚠️ Deep risk check · 深度风险核查」· only on manual button · 手动按钮才调用",
               "Fill QCC_RISK_ENDPOINT · 填 QCC_RISK_ENDPOINT")


if st.session_state.get("core_material"):
    render_core_report(st.session_state.core_material)
    st.stop()
if st.session_state.get("service_cat"):
    render_service_report(st.session_state.service_cat)
    st.stop()
if st.session_state.get("equipment_cat"):
    render_equipment_report(st.session_state.equipment_cat)
    st.stop()

# ── 计算匹配结果 ──────────────────────────────────────────────────────
_site_key = st.session_state.get("site", "SH")
_site = sites.get_site(_site_key)
_, results = match_suppliers(
    query=st.session_state.query,
    filters=st.session_state.filters,
    weights=st.session_state.weights,
    site_key=_site_key,
)

sel_ids = st.session_state.selected_ids
compare_suppliers = (
    [s for s in results if s["id"] in sel_ids] if sel_ids
    else results[:5]
)

# 统计
_cs = cache_status()
tier1_count   = sum(1 for s in results if s.get("_tier") == 1)
factory_count = sum(1 for s in results if s.get("_role") in ("manufacturer", "both"))
hazmat_count  = sum(1 for s in results if
    s.get("licenses", {}).get("hazardous_chemicals") or
    s.get("licenses", {}).get("hazmat_business"))
avg_score = (
    round(sum(s.get("score", 0) for s in results) / len(results), 1)
    if results else "—"
)

# ═══════════════════════════════════════════════════════════════════════
# Hero 顶部
# ═══════════════════════════════════════════════════════════════════════
# 未选品类（首页/大类浏览）显示全站规模；已进入某原料查询则显示该查询的匹配统计
if st.session_state.query:
    _hero_stats = (
        ("g", len(results),   "Matches<br>当前匹配"),
        ("b", tier1_count,    f"{_site['cluster']} Tier-1<br>{_site['cluster']}一级"),
        ("t", _cs['count'],   "Cached items<br>缓存品类"),
        ("",  avg_score,      "Avg score<br>平均评分"),
    )
else:
    _gs = home_nav.global_stats()
    _hero_stats = (
        ("g", _gs["categories"], "Categories<br>全站品类"),
        ("b", _gs["suppliers"],  "Vetted suppliers<br>优选供应商"),
        ("t", _cs['count'],      "Cached items<br>缓存品类"),
        ("",  _gs["plants"],     "Plants<br>大工厂"),
    )
_hero_stat_html = "".join(
    f'<div class="hero-stat"><div class="hero-stat-val {_c}">{_v}</div>'
    f'<div class="hero-stat-lbl">{_l}</div></div>'
    for _c, _v, _l in _hero_stats
)
st.markdown(f"""
<div class="sabic-hero">
 <div class="hero-inner">
  <div class="hero-badge"><span class="pulse"></span>SABIC {_site['cn']} · Smart Sourcing Decisions · 智能寻源决策</div>
  <div class="hero-title"><span class="lead">Enter a raw material —</span> we'll tell you <span class="key">which supplier to pick</span></div>
  <div class="hero-title" style="font-size:22px;margin-top:-2px"><span class="lead">请输入一种原材料，</span>告诉你<span class="key">选哪家供应商</span></div>
  <div class="hero-stats">{_hero_stat_html}</div>
 </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# 侧边栏：按当前大类上下文渲染（每类独立权重 + 专属筛选）
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# 主体内容
# ═══════════════════════════════════════════════════════════════════════

# 企查查接入状态（供下方逻辑判断使用，不在首页展示）
from utils.qcc_client import is_configured as _qcc_ok
_qcc_on = _qcc_ok()

# ═══════════════════════════════════════════════════════════════════════
# 搜索区（主区域顶部，始终显示）
# ═══════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="search-head">
  <div class="s-bar"></div>
  <div class="s-txt">
    <span class="s-title">All-Category Search · 全品类搜索</span>
    <span class="s-sub">Type an English code or Chinese name to search the whole site: Strategic / Production materials · Services MRO · Equipment　|　输入英文代码或中文名，联想全站：核心原料 · 其他原料 · 服务 MRO · 化工设备</span>
  </div>
  <span class="s-pill"><span class="dot"></span>4 categories · 全站四大类联想</span>
</div>
""", unsafe_allow_html=True)

search_col, btn_col = st.columns([5, 1])
with search_col:
    search_text = st.text_input(
        "Search · 搜索",
        value="",
        key="search_text",
        placeholder="Search all categories · 搜全站品类：PC / 聚碳酸酯 / 换热器 / 离心泵 / 人力外包 / 钛白粉 / nylon …",
        label_visibility="collapsed",
    )
with btn_col:
    do_search = st.button("Search · 搜索", width='stretch', type="primary")

# ── 全品类联想：跨「核心原料 / 其他原料 / 服务MRO / 化工设备」四大类 ──
_KIND_META = {
    "core":      ("⭐", "Strategic·核心原料"),
    "material":  ("🧪", "Production·其他原料"),
    "mro":       ("🏢", "Services·服务MRO"),
    "equipment": ("🏭", "Equipment·化工设备"),
}
_sugs = home_nav.unified_suggest(search_text, 12) if search_text else []

if search_text and _sugs:
    st.caption("🔎 All-category suggestions — click to open the report directly.  \n"
               "全品类联想（核心原料 / 其他原料 / 服务 MRO / 化工设备，点击直接进入报告）：")
    _scols = st.columns(4)
    for _i, _it in enumerate(_sugs):
        _ico, _lane_cn = _KIND_META.get(_it["kind"], ("•", ""))
        _suffix = "" if _it["kind"] == "equipment" else (
            f"（{_it['count']}）" if _it.get("count") != "" else "")
        with _scols[_i % 4]:
            _sug_name = f"{_it['en']} · {_it['cn']}" if _it.get("en") else _it["cn"]
            if st.button(f"{_ico} {_sug_name} · {_lane_cn}{_suffix}",
                         key=f"sug_{_it['kind']}_{_it.get('key', _it['cn'])}_{_i}",
                         width='stretch'):
                home_nav.enter_item(_it)
    if do_search:
        _exact = next((x for x in _sugs
                       if search_text.strip().lower() == (x.get("en") or "").lower()
                       or search_text.strip() == x["cn"]), None)
        home_nav.enter_item(_exact or _sugs[0])

elif do_search and search_text:
    # 联想未命中 → 作为原料品类（缓存或企查查实时搜索）
    st.session_state.lane = "material"
    st.session_state.query = search_text.strip()
    st.session_state.selected_ids = []
    st.session_state.active_supplier = None
    st.rerun()

if search_text and not _sugs:
    if _qcc_on:
        st.caption("ℹ️ No suggestion matched. Clicking Search will treat it as a material "
                   "category and call the QCC live API (consumes quota).  \n"
                   "全品类联想未命中，点「搜索」将作为原料品类调用企查查实时接口（消耗额度）")
    else:
        st.caption("⚠️ No suggestion matched, and no QCC API key configured — live search unavailable.  \n"
                   "全品类联想未命中，且未配置企查查 API Key，无法实时搜索")

# 当前查询状态行
if st.session_state.query:
    _q_col1, _q_col2 = st.columns([5, 1])
    with _q_col1:
        _lm = LAST_SEARCH_META
        _src_txt = ""
        if _lm.get("source") == "local_cache":
            _src_txt = (f"&nbsp;<span style='background:#f0faf4;color:#059669;"
                        f"font-size:11px;padding:1px 7px;border-radius:8px'>"
                        f"📦 Local cache · 本地缓存 {_lm.get('cache_file','')} · collected {_lm.get('collected_at','')[:10]}</span>")
        elif _lm.get("source") == "api":
            _src_txt = ("&nbsp;<span style='background:#eff6ff;color:#3b82f6;"
                        "font-size:11px;padding:1px 7px;border-radius:8px'>🌐 QCC live API · 企查查实时</span>")
        elif _lm.get("source") == "no_api":
            _src_txt = ("&nbsp;<span style='background:#fef2f2;color:#dc2626;"
                        "font-size:11px;padding:1px 7px;border-radius:8px'>⚠️ Not cached, no API · 未缓存且未配置 API</span>")
        st.markdown(
            f"**Current query · 当前查询：**「**{st.session_state.query}**」&nbsp;&nbsp;"
            f"<b style='color:#0E8C3A'>{len(results)}</b> matches · 家{_src_txt}",
            unsafe_allow_html=True,
        )
        if get_category_priority(st.session_state.query) == 2:
            st.caption("⚪ Extended category · not on the SABIC core procurement list  \n"
                       "扩展品类 · 不在 SABIC 核心采购清单内")
        # 企查查字段抓取失败不再在页面提示，直接沿用已有（缓存）数据
    with _q_col2:
        if st.button("✕ Clear · 清除", width='stretch'):
            st.session_state.query = ""
            st.session_state.selected_ids = []
            st.session_state.active_supplier = None
            st.rerun()
        if results:
            from utils.report import build_dossier_html
            _src_label = ("QCC live API · 企查查实时 API" if LAST_SEARCH_META.get("source") == "api"
                          else f"Local cache · 本地缓存（{LAST_SEARCH_META.get('cache_file','')} · {LAST_SEARCH_META.get('collected_at','')[:10]}）")
            _dossier_html = build_dossier_html(
                st.session_state.query, results,
                st.session_state.weights,
                meta={"source_label": _src_label, "site_key": _site_key},
            )
            st.download_button(
                "📄 Dossier · 背调报告",
                data=_dossier_html.encode("utf-8"),
                file_name=f"SABIC背调报告_{st.session_state.query}_{__import__('datetime').date.today()}.html",
                mime="text/html",
                width='stretch',
                type="primary",
                help="Generates a full dossier (decision verdict + market structure + top profile + "
                     "candidate comparison + verification channels). Open in a browser after download; "
                     "Ctrl+P to save as PDF.  \n"
                     "生成完整背调报告（决策结论+市场结构+首选档案+候选对比+核验渠道），下载后用浏览器打开，Ctrl+P 可存为 PDF",
            )
            excel_bytes = export_excel(results[:20], st.session_state.query or "供应商对比")
            st.download_button(
                "📥 Export Excel · 导出 Excel",
                data=excel_bytes,
                file_name=f"SABIC_供应商对比_{st.session_state.query}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch',
            )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════
# 空查询：搜索引导页（按分组浏览全部缓存品类）
# ═══════════════════════════════════════════════════════════════════════
if not st.session_state.query:
    _lane = st.session_state.get("lane")

    # ── 首页：未选大类 → 四大类入口 + 全品类总表导出 ──────────────────
    if _lane is None:
        home_nav.render_lane_selector()
        st.markdown("---")

        @st.cache_data(show_spinner="Compiling the all-category supplier master table… · 正在汇总全品类供应商总表…")
        def _master_workbook() -> bytes:
            return build_master()

        _mc1, _mc2 = st.columns([3, 1])
        with _mc1:
            st.markdown(
                "<div style='padding:6px 0'>"
                "<span style='font-size:15px;font-weight:700;color:#0a1628'>📊 All-Category Supplier Master Table · 全品类供应商总表</span>"
                "<span style='font-size:12.5px;color:#5a6780;margin-left:8px'>"
                "One Excel workbook covering the whole site: ① expert-reviewed strategic materials · "
                "② core procurement categories · ③ extended categories · ④ 15 service categories · "
                "⑤ process-equipment sourcing (each expanded by its own scoring model, multiple sheets).<br>"
                "一份 Excel 汇总全站：① 专家评审核心物料 · ② 核心采购品类 · "
                "③ 补充扩展品类 · ④ 综合服务 15 品类 · ⑤ 化工设备寻源（各按其评分模型展开，多 Sheet）。</span>"
                "</div>",
                unsafe_allow_html=True,
            )
        with _mc2:
            st.download_button(
                "⬇️ Export master table · 导出全品类总表",
                data=_master_workbook(),
                file_name=f"SABIC_供应商总表_全品类_{__import__('datetime').date.today():%Y%m%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch", type="primary",
                help="Covers every category's suppliers on the site: 6-dim expert materials, 3-dim business, "
                     "5-dim services, 5-dim equipment, with a summary cover.  \n"
                     "覆盖网页上全部品类的供应商：专家评审 6 维、工商 3 维、综合服务 5 维、化工设备 5 维，含汇总封面",
            )
        st.stop()

    # ── 已选大类 → 返回首页 + 该大类品类卡 ───────────────────────────
    _lane_meta = home_nav.LANE_BY_KEY.get(_lane, {})
    if st.button("← Back to home · 返回首页 · 重新选择采购大类", key="lane_back"):
        st.session_state.lane = None
        st.rerun()

    if _lane == "core":
        render_core_cards()
    elif _lane == "material":
        home_nav.render_material_browse()
    elif _lane == "mro":
        render_service_cards()
    elif _lane == "equipment":
        render_equipment_cards()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════
# 其他原料：品类报告头部 —— 返回 + 四大工厂总览大地图 + 厂区选择
# ═══════════════════════════════════════════════════════════════════════
if st.session_state.get("lane") != "material":
    st.session_state.lane = "material"
_mb1, _mb2 = st.columns([3, 1])
with _mb1:
    if st.button("← Back to Production materials · 返回其他原料 · 品类列表", key="mat_back"):
        st.session_state.query = ""
        st.session_state.selected_ids = []
        st.session_state.active_supplier = None
        st.rerun()
with _mb2:
    st.markdown(
        f"<div style='text-align:right;font-size:12.5px;color:#5a6780;padding-top:6px'>"
        f"Plant · 采购厂区：<b style='color:{ _site['color'] if 'color' in _site else '#0E8C3A'}'>"
        f"{_site['cn']}</b></div>", unsafe_allow_html=True)

st.markdown(f"#### 🗺️ {st.session_state.query} · Four-plant proximity sourcing overview · "
            f"四大工厂就近寻源总览 · 选厂区即按该厂独立重算地理分")
home_nav.render_material_overview(st.session_state.query)
st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════
# 智能采购决策卡 —— 本系统区别于企查查的核心：不只给数据，直接给结论
# ═══════════════════════════════════════════════════════════════════════
if results:
    _dec = decision_summary(results, _site_key)
    _land = supply_landscape(results, _site_key)

    if _dec:
        _tags_html = "".join(f"<span class='decide-tag'>{t}</span>" for t in _dec["top_tags"])
        _lead_html = (
            f"<div class='decide-lead'>↑ Leads runner-up by {_dec['lead']} pts · 领先第二名 {_dec['lead']} 分</div>"
            if _dec.get("lead") and _dec["lead"] > 0 else ""
        )
        _scen_html = ""
        if _dec["scenarios"]:
            _cards = "".join(
                f"<div class='scen-card'>"
                f"<div class='scen-label'>{s['icon']} {s['label']}</div>"
                f"<div class='scen-name'>{s['name']}</div>"
                f"<div class='scen-why'>{s['why']}</div>"
                f"</div>"
                for s in _dec["scenarios"]
            )
            _scen_html = f"<div class='scen-row'>{_cards}</div>"

        st.markdown(
            f"<div class='decide-wrap'>"
            f"  <div class='decide-kicker'>🎯 Procurement recommendation · auto-generated from current filters & weights · 采购决策建议 · 基于当前筛选与权重自动生成</div>"
            f"  <div class='decide-top'>"
            f"    <div class='decide-medal'>🥇</div>"
            f"    <div style='flex:1;min-width:200px'>"
            f"      <div class='decide-name'>{_dec['top_name']}</div>"
            f"      <div class='decide-why'>Why · 推荐理由：{_dec['top_why']}</div>"
            f"      <div class='decide-tags'>{_tags_html}</div>"
            f"    </div>"
            f"    <div class='decide-score-box'>"
            f"      <div class='decide-score'>{_dec['top_score']:.1f}</div>"
            f"      <div class='decide-score-lbl'>Overall score · 综合评分</div>"
            f"      {_lead_html}"
            f"    </div>"
            f"  </div>"
            f"  {_scen_html}"
            f"</div>",
            unsafe_allow_html=True,
        )

    # 供应市场结构条 —— 一眼看清整个供应版图（企查查只给你单家公司）
    if _land.get("n"):
        _avg = f"{_land['avg_dist']}<span class='u'> km</span>" if _land.get("avg_dist") else "—"
        _provs = "、".join(f"{p}{c}家" for p, c in _land["top_provs"])
        st.markdown(
            f"<div class='land-bar'>"
            f"  <div class='land-cell'><div class='land-val'>{_land['n']}</div>"
            f"      <div class='land-lbl'>Suppliers · 可选供应商</div></div>"
            f"  <div class='land-cell'><div class='land-val'>{_land['tier1']}</div>"
            f"      <div class='land-lbl'>{_site['cluster']} Tier-1 一级圈 ({_land['tier1_share']}%)</div></div>"
            f"  <div class='land-cell'><div class='land-val'>{_land['factories']}</div>"
            f"      <div class='land-lbl'>Factories · 工厂/制造商 ({_land['factory_share']}%)</div></div>"
            f"  <div class='land-cell'><div class='land-val'>{_land['hazmat']}</div>"
            f"      <div class='land-lbl'>Hazmat-licensed · 含危化品资质</div></div>"
            f"  <div class='land-cell'><div class='land-val'>{_avg}</div>"
            f"      <div class='land-lbl'>Avg dist. to {_site['short']} · 平均距{_site['short']}</div></div>"
            f"  <div class='land-cell'><div class='land-val' style='font-size:14px;padding-top:3px'>{_land['leader_name']}</div>"
            f"      <div class='land-lbl'>Capital leader · 资本龙头 · {_land['leader_cap']}</div></div>"
            f"  <div class='land-note'>📊 Supply map · 供应版图：mainly in · 主要集中在 <b>{_provs}</b> &nbsp;·&nbsp; {_land['geo_note']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════════════════════════════════════════
# 结果区：两栏布局
# ═══════════════════════════════════════════════════════════════════════
left_col, right_col = st.columns([4, 6], gap="medium")

# ── 左栏：供应商排名列表 ─────────────────────────────────────────────
with left_col:
    n_selected = len(sel_ids)
    st.markdown(
        f"**Supplier Ranking · 供应商排名** "
        f"<span style='font-size:12px;color:#9ba8bb'>Top {min(len(results), 15)}</span>"
        f"{'&nbsp;&nbsp;<span style=\"background:#f0f0ff;border:1px solid #c4b5fd;padding:1px 8px;border-radius:4px;font-size:11px;color:#7c3aed\">' + str(n_selected) + ' selected · 家已选对比</span>' if n_selected else ''}",
        unsafe_allow_html=True,
    )

    if not results:
        st.info("No matching suppliers found. Adjust your search or filters.  \n未找到匹配供应商，请调整搜索条件或筛选器。")
    else:
        for i, s in enumerate(results[:15]):
            sid      = s.get("id", "")
            name     = s.get("name", "") or s.get("shortName", "")
            score    = s.get("score", 0)
            province = s.get("province", "")
            tier     = s.get("_tier", 3)
            is_sel   = sid in sel_ids

            tier_cls  = ["","tier-t1","tier-t2","tier-t3"][tier]
            tier_lbl  = ["","T1·一级","T2·二级","T3·三级"][tier]
            score_cls = "score-high" if score >= 70 else ("score-mid" if score >= 50 else "score-low")

            card_cols = st.columns([0.5, 6, 2])
            with card_cols[0]:
                checked = st.checkbox(
                    "Compare · 对比", value=is_sel, key=f"sel_{i}_{sid}",
                    label_visibility="collapsed",
                )
                if checked != is_sel:
                    if checked and len(sel_ids) < 5:
                        st.session_state.selected_ids.append(sid)
                    elif not checked:
                        st.session_state.selected_ids = [x for x in sel_ids if x != sid]
                    st.rerun()

            with card_cols[1]:
                _city = s.get("city", "")
                _rank_cls = f"medal-rank medal-{i+1}" if i < 3 else "sup-rank"
                _rank_txt = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
                _role_s = s.get("_role", "unknown")
                _role_chip = ""
                if _role_s in ("manufacturer", "both"):
                    _role_chip = ("<span style='font-size:9px;color:#0E8C3A;background:rgba(14,140,58,.1);"
                                  "border:1px solid rgba(14,140,58,.2);padding:0 5px;border-radius:4px;"
                                  "margin-left:5px'>Factory·工厂</span>")
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;padding:6px 0'>"
                    f"  <div class='{_rank_cls}'>{_rank_txt}</div>"
                    f"  <div style='flex:1;min-width:0'>"
                    f"    <div class='sup-name'>{name}{_role_chip}</div>"
                    f"    <div class='sup-meta'>{province}{(' · ' + _city) if _city and _city != province else ''}</div>"
                    f"  </div>"
                    f"  <span class='{tier_cls}'>{tier_lbl}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with card_cols[2]:
                st.markdown(
                    f"<div style='text-align:right;padding:6px 0'>"
                    f"  <span class='{score_cls}' style='font-size:23px'>{score:.1f}</span>"
                    f"  <span style='font-size:11.5px;color:#9ba8bb'> pts</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # 维度迷你进度条（3 维，与左侧权重一一对应）
            dims = s.get("dimensions", {})
            bar_html = "".join(
                f"<div style='flex:1;text-align:center'>"
                f"  <div style='font-size:11.5px;color:#5a6780;margin-bottom:3px'>{lbl} "
                f"    <b style='color:{"#0E8C3A" if dims.get(k,0)>=70 else "#f59e0b" if dims.get(k,0)>=40 else "#ef4444"}'>"
                f"      {dims.get(k,0):.0f}</b></div>"
                f"  <div style='height:6px;background:#e2e8f0;border-radius:3px'>"
                f"    <div style='height:100%;width:{dims.get(k,0):.0f}%;"
                f"          background:{"#0E8C3A" if dims.get(k,0)>=70 else "#f59e0b" if dims.get(k,0)>=40 else "#ef4444"};"
                f"          border-radius:3px'></div>"
                f"  </div>"
                f"</div>"
                for k, lbl in zip(
                    ["geography","scale","compliance"],
                    ["Geo·地理","Scale·规模","Comp·合规"]
                )
            )
            st.markdown(
                f"<div style='display:flex;gap:8px;margin-bottom:8px;padding:0 4px'>{bar_html}</div>",
                unsafe_allow_html=True,
            )

            if st.button(f"View details · 查看详情", key=f"detail_{i}_{sid}",
                         width='stretch', type="secondary"):
                st.session_state.active_supplier = s
                st.rerun()

            st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

# ── 右栏：图表 + 统计 + 详情 ────────────────────────────────────────
with right_col:

    # 图表优先级：① 中国地图（供应版图）② 雷达图（多维对比）③ 热力矩阵（强弱交叉）
    # 其余（单项对比/并排表/平行坐标/气泡）作为补充靠后
    tab_labels = ["🗺️ China Map·中国地图","📡 Radar·雷达图","🌡️ Heatmap·热力矩阵",
                  "📊 Single Metric·单项对比","📋 Side-by-side·并排对比表","📈 Parallel·平行坐标","🫧 Bubble·气泡图"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        fig = china_map(results, _site_key)
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False}, key="chart_map")
        st.caption("Shade: supplier count per province · Bubbles: supplier location & score · ★: SABIC Shanghai base  \n"
                   "颜色深浅：该省供应商数量 · 气泡：供应商位置与评分 · ★：SABIC 上海基地")

    with tabs[1]:
        fig = radar_chart(compare_suppliers)
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False}, key="chart_radar")
        st.caption(f"Showing {'selected ' + str(len(sel_ids)) if sel_ids else 'Top 5'} suppliers · tick the left checkboxes to customize the comparison set  \n"
                   f"展示 {'已选 ' + str(len(sel_ids)) + ' 家' if sel_ids else 'Top 5'} 供应商 · 勾选左侧复选框可自定义对比组合")

    with tabs[2]:
        fig = heatmap_chart(results[:15])
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False}, key="chart_heatmap")
        st.caption("Rows: suppliers · Columns: 3-dimension scores · darker = higher; cross-reference to spot each one's strengths/weaknesses  \n"
                   "行：供应商 · 列：三维评分 · 颜色越深分越高，行列交叉一眼看清各家强弱项")

    with tabs[3]:
        metric_opt = st.selectbox(
            "Select metric · 选择指标",
            ["综合评分","地理评分","规模评分","合规资质"],
            format_func=lambda x: {"综合评分":"Overall · 综合评分","地理评分":"Geography · 地理评分",
                                   "规模评分":"Scale · 规模评分","合规资质":"Compliance · 合规资质"}[x],
            label_visibility="collapsed",
        )
        metric_map = {
            "综合评分":"score","地理评分":"geography",
            "规模评分":"scale","合规资质":"compliance",
        }
        fig = bar_chart(compare_suppliers, metric_map[metric_opt])
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False}, key=f"chart_bar_{metric_opt}")

    with tabs[4]:
        if len(compare_suppliers) < 2:
            st.info("Tick at least 2 suppliers on the left for a side-by-side comparison.  \n请在左侧勾选至少 2 家供应商进行并排对比。")
        else:
            df_cmp = compare_dataframe(compare_suppliers)
            st.dataframe(
                df_cmp.style.apply(_highlight_row_max, axis=1),
                width='stretch',
                height=480,
            )

    with tabs[5]:
        fig = parallel_chart(compare_suppliers)
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False}, key="chart_parallel")
        st.caption("Each line is one company · hover for exact per-dimension scores · click the legend to hide/show a company  \n"
                   "每条折线代表一家企业 · 悬停显示各维度精确分数 · 点击右侧图例可隐藏/显示某企业")

    with tabs[6]:
        fig = bubble_chart(results[:20])
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False}, key="chart_bubble")
        st.caption("X: registered capital (log) · Y: years in business · bubble size: overall score · color: geographic ring  \n"
                   "X轴：注册资本（对数）· Y轴：成立年限 · 气泡大小：综合评分 · 颜色：地理圈层")

    # ── 统计卡片 ───────────────────────────────────────────────────────
    st.markdown("---")
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric(f"{_site['cluster']} T1 · 一级圈", f"{tier1_count}",
               delta=None, help=f"{_site['cn']} Tier-1 ring · 一级圈：{'、'.join(_site['home'])}")
    sc2.metric("Factories · 工厂（制造商）", f"{factory_count}",
               delta=None, help="Business scope includes production/manufacturing (incl. factory+trade)  \n经营范围含生产/制造（含工厂兼贸易）")
    sc3.metric("Hazmat license · 危化品资质", f"{hazmat_count}",
               delta=None, help="Business scope includes hazmat license (negations excluded)  \n经营范围含危化品许可（否定表述不算）")
    sc4.metric("Avg score · 平均评分", f"{avg_score}",
               delta=None, help="Mean score of current filtered results  \n当前筛选结果的评分均值")

    # ── 供应商详情 ─────────────────────────────────────────────────────
    active = st.session_state.active_supplier
    if active:
        st.markdown("---")
        _src_map = {"local_cache": "📦 Local cache · 本地缓存（QCC MCP）", "api": "🌐 QCC live API · 企查查实时"}
        source_badge = (
            '<span style="background:#eff6ff;border:1px solid #3b82f6;'
            'padding:1px 8px;border-radius:4px;font-size:11px;color:#3b82f6">'
            f'Source · 数据来源：{_src_map.get(active.get("_source",""), active.get("_source","QCC·企查查"))}</span>'
        )
        st.markdown(
            f'#### 📋 {active.get("shortName") or active.get("name")} &nbsp; {source_badge}',
            unsafe_allow_html=True,
        )

        # ── 得分明细（让每个分数都有据可查）──────────────────────────
        _dims = active.get("dimensions", {})
        _w    = st.session_state.weights
        _total = active.get("score", 0)
        import datetime as _dtx
        _age = (_dtx.datetime.now().year - active.get("established", 0)) if active.get("established") else 0
        _cap_wan = active.get("registered_capital_wan", 0) or 0
        _cap_txt = f"{_cap_wan/10000:.1f}亿元" if _cap_wan >= 10000 else f"{_cap_wan:.0f}万元" if _cap_wan else "未知"

        st.markdown(f"**🎯 Overall score · 综合得分 {_total:.1f}** &nbsp;<span style='color:#9ba8bb;font-size:12px'>= weighted sum of the three below · 以下三项加权求和</span>", unsafe_allow_html=True)

        # 合规得分明细（与 scorer.score_compliance 逐项对应）
        _scope_d   = active.get("_business_scope", "") or ""
        _industry_d = active.get("industry", "") or ""
        _loc_d     = (active.get("address", "") or "") + " " + _scope_d
        _comp_parts = list(filter(None, [
            ("Active +25 · 存续25分" if (active.get('reg_status','存续') or '存续') in ('存续','在业','') else "Inactive 0 · 非存续0分"),
            {"manufacturer":"Factory +20 · 工厂20分","both":"Factory+trade +16 · 工厂兼贸易16分","importer":"Importer +8 · 进口商8分",
             "trader":"Distributor +4 · 经销商4分","agent":"Intermediary 0 · 中介0分","unknown":"Unclassified +8 · 未分类8分"}.get(active.get("_role","unknown")),
            ("Hazmat license +20 · 危化品许可20分" if (active.get('licenses',{}).get('hazardous_chemicals')
                                or has_hazmat_license(_scope_d)) else None),
            ("Production/safety license +10 · 生产/安全许可10分" if any(k in _scope_d for k in
                ["生产许可","安全生产许可","生产经营许可","全国工业产品生产许可"]) else None),
            ("Chemical park +10 · 化工园区10分" if any(k in _loc_d for k in ["化工园","化工区","化工园区","化学工业园"])
             else ("Industrial park +5 · 工业园区5分" if any(k in _loc_d for k in
                   ["工业园","工业区","经济开发区","高新区","经济技术开发区"]) else None)),
            ("Chemical industry +10 · 化工行业10分" if any(k in _industry_d for k in _IND_CHEM)
             else ("Manufacturing +5 · 制造行业5分" if any(k in _industry_d for k in _IND_MFG) else None)),
            ("Import/export +5 · 进出口5分" if any(k in _scope_d for k in ["进出口","货物及技术进出口"]) else None),
        ]))

        # 互联网公开信息核验：解释合规分为何被抬高（修正爬取低估）
        _rep = active.get("_reputation")
        if _rep:
            _comp_parts.append(f"🌐 Web-verified floor {int(_rep.get('floor',0))} · 互联网核验下限{int(_rep.get('floor',0))}分")

        _explain = [
            ("📍 Geography 地理位置", _dims.get("geography",0), int(_w.get("geography",0.35)*100),
             f"Registered in · 注册在 {active.get('province','—')}, ~{active.get('logistics',{}).get('distance_km_to_site') or active.get('logistics',{}).get('distance_km_to_shanghai','—')} km to {_site['short']} · 距{_site['short']}"),
            ("🏢 Scale 企业规模", _dims.get("scale",0), int(_w.get("scale",0.35)*100),
             (f"Capital · 注册资本 {_cap_txt} (65%)"
              + (f" + Founded {_age}y · 成立{_age}年 (35%)" if _age else "")) ),
            ("✅ Compliance 合规资质", _dims.get("compliance",0), int(_w.get("compliance",0.30)*100),
             " + ".join(_comp_parts) if _comp_parts else "No quantifiable compliance items · 无可量化合规项"),
        ]
        for _label, _score, _wt, _basis in _explain:
            _color = "#0E8C3A" if _score>=70 else "#f59e0b" if _score>=40 else "#ef4444"
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px'>"
                f"<span style='width:140px'>{_label}</span>"
                f"<span style='width:46px;text-align:right;font-weight:600;color:{_color}'>{_score:.0f}</span>"
                f"<span style='width:40px;color:#9ba8bb;font-size:11px'>×{_wt}%</span>"
                f"<div style='flex:1;height:6px;background:#e2e8f0;border-radius:3px'>"
                f"<div style='height:100%;width:{_score:.0f}%;background:{_color};border-radius:3px'></div></div>"
                f"</div>"
                f"<div style='font-size:11px;color:#9ba8bb;margin:0 0 4px 148px'>↳ {_basis}</div>",
                unsafe_allow_html=True,
            )
        if _rep:
            _tk = _rep.get("tag", "公开核验")
            _tc = (f"｜Ticker · 股票代码 {_rep['ticker']}" if _rep.get("ticker") else "")
            _aka = (f"｜aka · 亦称 {_rep['aka']}" if _rep.get("aka") else "")
            st.markdown(
                f"<div style='background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;"
                f"padding:8px 11px;margin:2px 0 4px;font-size:12px;color:#1e3a8a'>"
                f"🌐 <b>Public web verification · 互联网公开信息核验</b>　<span style='background:#dbeafe;border-radius:6px;"
                f"padding:0 6px'>{_tk}</span>{_tc}{_aka}<br>"
                f"<span style='color:#334155'>{_rep.get('note','')}</span><br>"
                f"<span style='color:#64748b;font-size:11px'>↳ Compliance score floored at "
                f"{int(_rep.get('floor',0))} per public info, so reliable firms aren't underrated when "
                f"license keywords can't be scraped. · 合规分已按公开信息设下限 "
                f"{int(_rep.get('floor',0))} 分，避免因爬取不到许可关键词而低估可靠企业。</span></div>",
                unsafe_allow_html=True,
            )
        st.markdown("<div style='border-bottom:1px solid #e2e8f0;margin:6px 0'></div>", unsafe_allow_html=True)

        # ── 为什么不是它：与首选逐维对比，给出落选原因 + 适用场景 ──────
        _wn = why_not_top(active, results, st.session_state.weights)
        if _wn:
            if _wn["is_top"]:
                st.markdown(
                    f"<div class='wn-box top'>"
                    f"<div class='wn-verdict'>🥇 {_wn['verdict']}</div>"
                    f"<div class='wn-narr'>{_wn['narrative']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                _box_cls = "role" if _wn["role_priority_reason"] else "lag"
                _icon = "⚖️" if _wn["role_priority_reason"] else "🤔"
                # 三维对比小卡（本企业 vs 首选）
                def _dim_html(d):
                    col = "#0E8C3A" if d["raw"] >= 0 else "#dc2626"
                    return (
                        f"<div class='wn-dim'>"
                        f"<div class='wn-dim-lbl'>{d['icon']} {d['label']}</div>"
                        f"<div class='wn-dim-vs' style='color:{col}'>"
                        f"{d['a']:.0f}<span style='font-size:10px;color:#9ba8bb'> vs {d['t']:.0f}</span></div>"
                        f"</div>"
                    )
                _cmp = "".join(_dim_html(d) for d in _wn["dim_gaps"])
                _scen = ""
                if _wn["scenario_fit"]:
                    _chips = "".join(
                        f"<span class='wn-scen-chip'>{s['icon']} Best for 「{s['scenario']}」· 它是之选 · {s['score']:.0f}</span>"
                        for s in _wn["scenario_fit"]
                    )
                    _scen = (f"<div class='wn-scen'>{_chips}</div>"
                             f"<div style='font-size:11px;color:#9ba8bb;margin-top:5px'>"
                             f"↳ If you value the scenarios above more, it actually fits better than the top pick. · "
                             f"若你更看重以上场景，它反而比首选更合适。</div>")
                st.markdown(
                    f"<div class='wn-box {_box_cls}'>"
                    f"<div class='wn-verdict'>{_icon} Why not the top pick · 为什么不是首选：{_wn['verdict']}"
                    f"<span style='font-weight:500;font-size:11px;color:#9ba8bb'>（vs {_wn['top_name']}）</span></div>"
                    f"<div class='wn-narr'>{_wn['narrative']}</div>"
                    f"<div class='wn-cmp'>{_cmp}</div>"
                    f"{_scen}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # ── 行 1：工商基本信息 + 合规资质 + 经营角色 ────────────────
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown("**🏢 Business Basics · 工商基本信息**")
            cap = active.get("registered_capital_wan", 0) or 0
            cap_str = f"{cap/10000:.1f} 亿元" if cap >= 10000 else f"{cap} 万元" if cap > 0 else "—"
            _na = "—"
            rows_d1 = [
                ("Full name · 企业全称",  active.get("name") or _na),
                ("Credit code · 统一信用代码", active.get("creditCode") or active.get("credit_code") or _na),
                ("Legal rep. · 法定代表人", active.get("legalPerson") or active.get("legal_person") or _na),
                ("Address · 注册地址",  (active.get("address") or _na)[:30] + ("…" if len(active.get("address") or "")>30 else "")),
                ("Province/City · 所在省市",  f"{active.get('province') or _na} {active.get('city') or ''}".strip()),
                ("Reg. capital · 注册资本",  cap_str),
                ("Founded · 成立年份",  f"{active.get('established')} 年" if active.get('established') else _na),
                ("Status · 经营状态",  active.get("reg_status") or "存续"),
                ("Industry · 所属行业",  active.get("industry") or _na),
            ]
            for k, v in rows_d1:
                st.markdown(f'<div style="font-size:13px;padding:2px 0"><span style="color:#5a6780">{k}：</span>{v}</div>',
                            unsafe_allow_html=True)

        with d2:
            lic = active.get("licenses", {})
            st.markdown("**✅ Qualifications & Compliance · 资质 & 合规**")
            def badge(ok, label, api_note=""):
                color = "#059669" if ok else "#9ca3af"
                icon  = "✓" if ok else "✗"
                note  = f' <span style="font-size:10px;color:#9ba8bb">{api_note}</span>' if api_note and not ok else ""
                return f'<div style="font-size:13px;padding:2px 0"><span style="color:{color}">{icon}</span> {label}{note}</div>'

            st.markdown(badge(
                lic.get("hazardous_chemicals") or lic.get("hazmat_business"),
                "Hazardous-chemicals license · 危险化学品经营许可证",
                "→ verify at MEM · 应急管理部核验"
            ), unsafe_allow_html=True)
            st.markdown(badge(lic.get("safety_production"), "Safety production license · 安全生产许可证",
                              "→ verify at MEM · 应急管理部核验"), unsafe_allow_html=True)
            st.markdown(badge(any(k in _scope_d for k in
                ["生产许可","安全生产许可","生产经营许可"]), "Production-license keywords · 生产许可证关键词"), unsafe_allow_html=True)
            st.markdown(badge(active.get("chemical_park"), "Inside a chemical park · 化工园区内企业"), unsafe_allow_html=True)
            st.markdown(badge(any(k in _scope_d for k in ["进出口","货物及技术进出口"]),
                              "Import/export qualification · 进出口经营资质"), unsafe_allow_html=True)

            st.markdown("<br>**🏭 Company type (from business scope) · 企业类型（来自经营范围）**", unsafe_allow_html=True)
            role_map = {
                "manufacturer": ("🏭 Factory (manufacturer) · 工厂（生产制造）", "#059669"),
                "both":         ("🏭 Factory + trade · 工厂兼贸易", "#3b82f6"),
                "importer":     ("🚢 Importer · 进口商", "#0891b2"),
                "trader":       ("🟡 Distributor · 经销商", "#d97706"),
                "agent":        ("⚠️ Intermediary/agent (suggest excluding) · 中介/代理（建议排除）", "#dc2626"),
                "unknown":      ("⚪ Unclassified · 未分类", "#9ca3af"),
            }
            role = active.get("_role", "unknown")
            rl, rc = role_map.get(role, ("⚪ Unclassified · 未分类", "#9ca3af"))
            st.markdown(f'<span style="color:{rc};font-weight:600">{rl}</span>', unsafe_allow_html=True)
            st.caption("Priority: factory > factory+trade > importer > distributor > intermediary  \n优先级：工厂 > 工厂兼贸易 > 进口商 > 经销商 > 中介")

        with d3:
            st.markdown("**📋 Business Scope (QCC Scope field) · 经营范围**")
            scope = active.get("_business_scope", "")
            if scope:
                st.markdown(
                    f'<div style="font-size:12px;color:#374151;background:#f9fafb;'
                    f'border:1px solid #e5e7eb;border-radius:6px;padding:8px;'
                    f'max-height:260px;overflow-y:auto;line-height:1.6">{scope[:800]}'
                    f'{"…" if len(scope)>800 else ""}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.caption("No business-scope data for this company (sole proprietors may lack this field in QCC)  \n该企业暂无经营范围数据（个体工商户在企查查工商接口可能无登记字段）")
            st.caption("Capacity / MOQ / quotes require an RFQ to the company — QCC business data does not include these  \n产能/起订量/报价需向企业询价，企查查工商数据不含这些")

        # ── 行 2：企查查扩展接口（开通后自动显示真实数据）──────────────
        st.markdown("---")
        st.caption("The info below is queried on demand — one API call per company view, to control cost  \n以下信息按需查询，仅在查看本企业时调用一次接口，控制成本")
        from utils.qcc_client import (get_qualifications, get_risk_info,
                                       is_qual_enabled, is_risk_enabled)
        ea1, ea2, ea3, ea4 = st.columns(4)

        with ea1:
            st.markdown("**📜 Certificate Verification · 资质证书核验**")
            if is_qual_enabled():
                _quals = get_qualifications(active.get("name", ""))
                if _quals and _quals.get("items"):
                    for q in _quals["items"][:4]:
                        _ok = q.get("status","") in ("有效","正常","")
                        st.markdown(
                            f'<div style="font-size:12px;padding:2px 0">'
                            f'<span style="color:{"#059669" if _ok else "#dc2626"}">'
                            f'{"✓" if _ok else "✗"}</span> {q.get("name","")}'
                            f'<span style="color:#9ba8bb"> {q.get("expire","")}</span></div>',
                            unsafe_allow_html=True)
                else:
                    st.caption("No certificate records found · 未查到资质证书记录")
            else:
                st.markdown(
                    '<div style="background:#f9fafb;border:1px dashed #d1d5db;'
                    'border-radius:6px;padding:8px;font-size:11px;color:#9ca3af;text-align:center">'
                    'Enable the "Certificates" API to<br>verify hazmat/safety-production licenses<br>'
                    '开通「资质证书」接口后<br>核验危化品/安全生产许可证</div>',
                    unsafe_allow_html=True)

        with ea2:
            st.markdown("**⚠️ Deep Risk Check · 深度风险核查**")
            if is_risk_enabled():
                _sid = active.get("id", "")
                _risk_cache_key = f"risk_{_sid}"
                _cached_risk = st.session_state.get(_risk_cache_key)

                if _cached_risk is None:
                    st.caption("QCC risk scan · 企查查风险扫描 · ¥6/scan · 6元/次")
                    if st.button("🔍 Check now · 立即核查", key=f"risk_btn_{_sid}",
                                 width='stretch',
                                 help="Calls QCC API 736: dishonesty / litigation / abnormal operation / shareholders, ¥6 each  \n调用企查查736接口，含失信/诉讼/经营异常/股东，每次6元"):
                        with st.spinner("Checking… · 正在核查..."):
                            _r = get_risk_info(active.get("name", ""))
                            st.session_state[_risk_cache_key] = _r or {"_empty": True}
                        st.rerun()
                else:
                    _risk = _cached_risk if not _cached_risk.get("_empty") else None
                    if _risk:
                        _flags = []
                        if _risk.get("dishonest"): _flags.append(("Dishonest debtor · 失信被执行人","#dc2626"))
                        if _risk.get("executed"):  _flags.append(("Person subject to enforcement · 被执行人","#dc2626"))
                        if _risk.get("abnormal"):  _flags.append(("Abnormal operation · 经营异常","#d97706"))
                        if _risk.get("penalty_count",0)>0:
                            _flags.append((f"Admin. penalties · 行政处罚 {_risk['penalty_count']}","#d97706"))
                        if _risk.get("lawsuit_count",0)>0:
                            _flags.append((f"Lawsuits · 涉诉 {_risk['lawsuit_count']}","#d97706"))
                        if _flags:
                            for txt, col in _flags:
                                st.markdown(f'<div style="font-size:12px;color:{col};padding:2px 0">⚠ {txt}</div>',
                                            unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="font-size:12px;color:#059669;padding:2px 0">✓ No major risks found · 未发现重大风险</div>',
                                        unsafe_allow_html=True)
                        st.caption("✓ Checked (no re-charge this session) · 已核查（本次会话不再重复扣费）")
                    else:
                        st.caption("No risk records found · 未查到风险记录")
            else:
                st.markdown(
                    '<div style="background:#f9fafb;border:1px dashed #d1d5db;'
                    'border-radius:6px;padding:8px;font-size:11px;color:#9ca3af;text-align:center">'
                    'Enable "Risk scan 736" for<br>manual checks (¥6/scan)<br>'
                    '开通「企业风险扫描736」<br>后可手动核查（6元/次）</div>',
                    unsafe_allow_html=True)

        with ea3:
            st.markdown("**👥 Shareholders · 股东信息**")
            _sid3 = active.get("id", "")
            _risk_data = st.session_state.get(f"risk_{_sid3}")
            _partners = (_risk_data or {}).get("partners", []) if _risk_data else []
            if _partners:
                for p in _partners[:5]:
                    st.markdown(
                        f'<div style="font-size:12px;padding:2px 0">'
                        f'{p.get("name","")} '
                        f'<span style="color:#9ba8bb">{p.get("ratio","")}</span></div>',
                        unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div style="background:#f9fafb;border:1px dashed #d1d5db;'
                    'border-radius:6px;padding:8px;font-size:11px;color:#9ca3af;text-align:center">'
                    'Click "Deep risk check" on the left<br>to also show shareholders<br>'
                    '点击左侧「深度风险核查」<br>后一并显示股东</div>', unsafe_allow_html=True)

        with ea4:
            st.markdown("**🔗 Verification Links · 核验链接**")
            st.markdown(
                f'<a href="https://www.gsxt.gov.cn/corp-query-homepage.html" '
                f'target="_blank" style="font-size:12px;color:#3b82f6">🏛 National Enterprise Credit · 国家企业信用信息公示</a><br>'
                f'<a href="https://www.mem.gov.cn/fw/cxfw/" '
                f'target="_blank" style="font-size:12px;color:#3b82f6">🔒 MEM qualification check · 应急管理部资质核验</a><br>'
                f'<a href="https://credit.customs.gov.cn/" '
                f'target="_blank" style="font-size:12px;color:#3b82f6">🛃 Customs credit query · 海关信用企业查询</a>',
                unsafe_allow_html=True
            )
            if active.get("_fetched_at"):
                st.caption(f"Data fetched · 数据拉取时间：{active.get('_fetched_at', '')[:10]}")
