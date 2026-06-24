"""生成 SABIC 寻源系统 API 接入完整指南 PDF"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path

def _reg():
    for fp in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
               '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc']:
        if Path(fp).exists():
            try:
                pdfmetrics.registerFont(TTFont('NC', fp))
                pdfmetrics.registerFont(TTFont('NC-B', fp))
                return 'NC', 'NC-B'
            except Exception:
                pass
    return 'Helvetica', 'Helvetica-Bold'

FN, FB = _reg()

G  = colors.HexColor('#0E8C3A')
GL = colors.HexColor('#f0faf4')
BL = colors.HexColor('#3b82f6')
BL2= colors.HexColor('#eff6ff')
AM = colors.HexColor('#f59e0b')
AM2= colors.HexColor('#fffbeb')
DK = colors.HexColor('#0a1628')
GR = colors.HexColor('#5a6780')
GRL= colors.HexColor('#f2f5f9')
BD = colors.HexColor('#e2e8f0')
W, H = A4

def S(n, **kw):
    base = dict(fontName=FN, fontSize=10, leading=16, spaceAfter=4)
    base.update(kw)
    return ParagraphStyle(n, **base)

sH1 = S('h1', fontName=FB, fontSize=18, leading=24, textColor=DK, spaceAfter=6, spaceBefore=16)
sH2 = S('h2', fontName=FB, fontSize=13, leading=18, textColor=DK, spaceAfter=4, spaceBefore=12)
sH3 = S('h3', fontName=FB, fontSize=10, leading=15, textColor=GR, spaceAfter=3, spaceBefore=8)
sB  = S('b',  textColor=colors.HexColor('#1a2233'), alignment=TA_JUSTIFY)
sBB = S('bb', fontName=FB, textColor=colors.HexColor('#1a2233'))
sCO = S('co', fontName='Courier', fontSize=8, leading=12,
        textColor=colors.HexColor('#1e293b'), leftIndent=8, backColor=GRL)
sNG = S('ng', fontSize=9, leading=13, textColor=colors.HexColor('#064e3b'))
sNA = S('na', fontSize=9, leading=13, textColor=colors.HexColor('#78350f'))
sNB = S('nb', fontSize=9, leading=13, textColor=colors.HexColor('#1e3a5f'))
sFT = S('ft', fontSize=8, leading=11, textColor=GR, alignment=TA_CENTER)
sTOC= S('tc', textColor=DK)
sTOs= S('ts', fontSize=9, textColor=GR, leftIndent=14)

W_BODY = W - 40*mm

def rule(c=BD, t=0.5): return HRFlowable(width='100%', thickness=t, color=c, spaceAfter=5, spaceBefore=2)
def sp(v=4): return Spacer(1, v*mm)

def box(text, sty, bc, bg, icon=''):
    p = Paragraph(f'{icon}  {text}' if icon else text, sty)
    t = Table([[p]], colWidths=[W_BODY])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),bg),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LINEBEFORE',(0,0),(0,-1),3,bc),('LINEAFTER',(0,0),(0,-1),3,bc),
    ]))
    return t

def code(lines):
    txt = '<br/>'.join(
        l.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        for l in lines)
    p = Paragraph(f'<font name="Courier" size="8">{txt}</font>', sCO)
    t = Table([[p]], colWidths=[W_BODY])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),GRL),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('LINEBEFORE',(0,0),(0,-1),2,BL),
    ]))
    return t

def tbl(headers, rows, cws=None):
    if cws is None:
        cw = W_BODY / len(headers)
        cws = [cw]*len(headers)
    data = [[Paragraph(f'<b>{h}</b>', sBB) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), sB) for c in row])
    t = Table(data, colWidths=cws, repeatRows=1)
    ts = TableStyle([
        ('BACKGROUND',(0,0),(-1,0),DK),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),FB),('FONTSIZE',(0,0),(-1,0),9),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('GRID',(0,0),(-1,-1),0.4,BD),('VALIGN',(0,0),(-1,-1),'TOP'),
    ])
    for i in range(1, len(data)):
        if i%2==0: ts.add('BACKGROUND',(0,i),(-1,i),GL)
    t.setStyle(ts)
    return t

def p(text, style=None):
    return Paragraph(text, style or sB)

def h1(text): return Paragraph(text, sH1)
def h2(text): return Paragraph(text, sH2)
def h3(text): return Paragraph(text, sH3)

# ══════════════════════════════════════════════════════════════════════
def build():
    story = []

    # ── 封面 ─────────────────────────────────────────────────────────
    hero_rows = [
        [Paragraph('<font color="#5eead4"><b>▮  SABIC Shanghai  ·  采购与供应链部</b></font>',
                   S('cx', fontName=FB, fontSize=9, textColor=colors.HexColor('#5eead4'), alignment=TA_CENTER))],
        [sp(8)],
        [Paragraph('<font color="white" size="22"><b>在线寻源系统</b></font>',
                   S('ct', fontName=FB, fontSize=22, leading=30, textColor=colors.white, alignment=TA_CENTER))],
        [Paragraph('<font size="14">API 完整接入指南</font>',
                   S('cs', fontSize=14, leading=20, textColor=colors.HexColor('#cbd5e1'), alignment=TA_CENTER))],
        [sp(4)],
        [Paragraph('含开放搜索架构改造 · 企查查/天眼查接入 · 工业品扩展方案',
                   S('cd', fontSize=9, textColor=GR, alignment=TA_CENTER))],
        [sp(8)],
        [HRFlowable(width='50%', thickness=1, color=G, hAlign='CENTER')],
        [sp(4)],
        [Paragraph('版本 v1.1  ·  仅供内部使用  ·  2026',
                   S('cf', fontSize=9, textColor=GR, alignment=TA_CENTER))],
    ]
    hero = Table(hero_rows, colWidths=[W_BODY])
    hero.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),DK),
        ('TOPPADDING',(0,0),(0,0),40),('BOTTOMPADDING',(0,len(hero_rows)-1),(-1,len(hero_rows)-1),40),
        ('LEFTPADDING',(0,0),(-1,-1),20),('RIGHTPADDING',(0,0),(-1,-1),20),
        ('TOPPADDING',(0,1),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-2),2),
    ]))
    story.append(hero)
    story.append(PageBreak())

    # ── 目录 ─────────────────────────────────────────────────────────
    story.append(h1('目  录'))
    story.append(rule(G, 1.5))
    toc = [
        ('1', '改动概览（5 分钟速读）'),
        ('2', '第一步：注册与配置 API'),
        ('  2.1', '天眼查 vs 企查查 最终选择'),
        ('  2.2', '注册天眼查并获取 Token'),
        ('  2.3', '阿里云函数计算代理部署'),
        ('  2.4', '环境变量配置'),
        ('3', '第二步：开放搜索架构改造'),
        ('  3.1', '现有架构的根本限制'),
        ('  3.2', '目标架构'),
        ('  3.3', '新文件说明（已提供，无需编写）'),
        ('  3.4', '需要修改的现有文件'),
        ('4', '第三步：工业设备搜索扩展'),
        ('  4.1', '为什么化学品和工业设备要分开处理'),
        ('  4.2', '品类配置文件 categories.py'),
        ('  4.3', '搜索关键词策略'),
        ('5', '接入注意事项'),
        ('  5.1', '额度保护——最重要'),
        ('  5.2', '数据质量问题'),
        ('  5.3', '生产商 vs 经销商识别逻辑'),
        ('  5.4', '安全与合规'),
        ('6', '分阶段实施路线图'),
        ('7', '附录：环境变量与 API 端点速查'),
    ]
    for num, title in toc:
        ind = 14 if num.startswith(' ') else 0
        story.append(Paragraph(
            f'{"  " if ind else ""}<b>{num.strip()}</b>  {title}',
            S('ti', fontName=FN if ind else FB, fontSize=9.5, leading=17,
              textColor=GR if ind else DK, leftIndent=ind)))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §1
    # ════════════════════════════════════════════════════════════════
    story.append(h1('1  改动概览（5 分钟速读）'))
    story.append(rule(G, 1.5))
    story.append(p('接入 API 后，系统将从演示模式切换到实时数据模式。'
                   '下表列出了所有需要创建或修改的文件，以及每个文件的改动幅度。'))
    story.append(sp(2))
    story.append(tbl(
        ['文件', '操作', '改动量', '说明'],
        [
            ['utils/tyc_client.py',  '新建 ✓', '全新', '天眼查 API 客户端，含速率限制和磁盘缓存'],
            ['utils/open_search.py', '新建 ✓', '全新', '开放搜索引擎，突破 chemicals.json 限制'],
            ['utils/categories.py',  '新建',   '全新', '品类配置，覆盖化学品 + 工业设备'],
            ['utils/matcher.py',     '修改',   '+30行', '新增 API 模式分支，保留演示模式兜底'],
            ['app.py',               '修改',   '+50行', '新增搜索模式切换、加载状态、分页控件'],
            ['.env.local',           '新建',   '5行',  '存放 Token，已在 .gitignore，不提交 Git'],
            ['requirements.txt',     '修改',   '+2行', '新增 diskcache, python-dotenv'],
        ],
        cws=[46*mm, 20*mm, 18*mm, 86*mm],
    ))
    story.append(sp(3))
    story.append(box(
        'tyc_client.py 和 open_search.py 已在项目中提供完整实现，你只需要'
        '配置环境变量 + 修改 matcher.py 和 app.py 的少量代码即可启用。',
        sNG, G, GL, '✦'))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §2
    # ════════════════════════════════════════════════════════════════
    story.append(h1('2  第一步：注册与配置 API'))
    story.append(rule(G, 1.5))

    story.append(h2('2.1  天眼查 vs 企查查——最终建议'))
    story.append(tbl(
        ['维度', '天眼查', '企查查'],
        [
            ['免费额度',    '个人 100–500 次/日',    '试用版 100 次/日（30天）'],
            ['鉴权方式',    'Header: Authorization: Token（最简单）', 'MD5 签名（较复杂）'],
            ['经营范围搜索','word 参数匹配名称+经营范围', 'keyword 参数，能力相同'],
            ['数据时效',    'T+1 更新',              'T+1 更新'],
            ['数据来源',    '国家企业信用信息公示系统', '国家企业信用信息公示系统'],
            ['现有代码',    '已完整实现（tyc_client.py）', '需修改 Header 和签名逻辑'],
            ['结论',        '⭐ 推荐，直接可用',       '可备用，需额外开发'],
        ],
        cws=[32*mm, 70*mm, 68*mm],
    ))
    story.append(sp(2))
    story.append(box('两家数据本质相同（均来自工商局公示系统）。天眼查个人注册门槛低、'
                     '鉴权最简单、现有代码已完整对接，优先使用天眼查。',
                     sNG, G, GL, '✦'))

    story.append(h2('2.2  注册天眼查并获取 Token'))
    steps = [
        '访问 https://open.tianyancha.com/，用手机号注册账号',
        '进入个人中心 → 实名认证，上传身份证正反面（约 5 分钟，即时通过）',
        '进入 API 商城，搜索并申请以下两个接口（通常即时通过）：',
        '  ▸ 搜索-企业模糊搜索  endpoint: open/cloud/search',
        '  ▸ 工商-企业基本信息(加强版)  endpoint: ic/baseinfoV2/2.0',
        '申请通过后，在"我的接口" → Token 管理页面复制 Token（32位字符串）',
        '妥善保存 Token，后续填入 .env.local，不要提交到代码仓库',
    ]
    for s in steps:
        ind = 14 if s.startswith('  ') else 0
        story.append(Paragraph(
            ('  ' if ind else '• ') + s.strip(),
            S('si', leftIndent=ind+8, spaceAfter=3)))
    story.append(sp(2))
    story.append(box('⚠  Token 泄露后请立即在天眼查后台重置 Token，旧 Token 立即失效。'
                     '  Token 只存在 .env.local 和阿里云 FC 环境变量中，永远不写进代码。',
                     sNA, AM, AM2, '⚠'))

    story.append(h2('2.3  阿里云函数计算代理（生产环境必须）'))
    story.append(p('浏览器不能直接调用天眼查 API（CORS 限制 + Token 安全问题）。'
                   '必须通过服务端代理中转。项目已在 proxy-functions/tianyancha/ '
                   '提供完整代理代码，无需自己编写，按以下步骤部署：'))
    story.append(sp(2))
    story.append(tbl(
        ['步骤', '操作'],
        [
            ['1', '登录 fcnext.console.aliyun.com → 创建函数 → HTTP 函数 → Node.js 20'],
            ['2', '将 proxy-functions/tianyancha/index.js 内容粘贴到代码编辑器 → 部署代码'],
            ['3', '函数配置 → 环境变量 → 添加 TYC_TOKEN=<你的Token>，ALLOWED_ORIGIN=<前端域名>'],
            ['4', '触发器管理 → 复制 HTTP 触发器 URL（形如 https://xxx.fcapp.run/）'],
            ['5', '将 URL 填入 .env.local 的 TYC_PROXY_URL 变量（见 2.4）'],
            ['6', '用下方 curl 命令验证通路'],
        ],
        cws=[10*mm, 160*mm],
    ))
    story.append(sp(2))
    story.append(code([
        '# 验证代理（把 <URL> 替换为你的 FC 触发器 URL）',
        'curl -X POST <URL> -H "Content-Type: application/json" \\',
        '  -d \'{"endpoint":"open/cloud/search","params":{"word":"中石化","pageSize":3}}\'',
        '',
        '# 预期返回（error_code=0 表示成功）:',
        '# {"error_code":0,"result":{"items":[...],"total":123}}',
    ]))

    story.append(h2('2.4  环境变量配置'))
    story.append(p('在项目根目录创建 .env.local 文件（已在 .gitignore，不会提交）：'))
    story.append(code([
        '# sabic-py/.env.local',
        '',
        '# 天眼查代理 URL（阿里云 FC 触发器 URL）—— 生产环境必填',
        'TYC_PROXY_URL=https://tianyancha-proxy-xxxxx.fcapp.run/',
        '',
        '# 天眼查 Token（仅本地直连调试用，生产环境放 FC 环境变量）',
        'TYC_TOKEN=',
        '',
        '# PubChem 启用（无需 Key，免费接口）',
        'PUBCHEM_ENABLED=true',
        '',
        '# 高德地图 Key（P4 阶段接入，现在可以留空）',
        'AMAP_KEY=',
    ]))
    story.append(p('在 app.py 顶部（import streamlit 之前）加入以下两行：'))
    story.append(code([
        'from pathlib import Path',
        'from dotenv import load_dotenv',
        'load_dotenv(Path(__file__).parent / ".env.local")',
        '',
        '# 同时在 requirements.txt 增加一行：',
        'python-dotenv>=1.0.0',
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §3
    # ════════════════════════════════════════════════════════════════
    story.append(h1('3  第二步：开放搜索架构改造'))
    story.append(rule(G, 1.5))

    story.append(h2('3.1  现有架构的根本限制'))
    story.append(p('当前系统在 chemicals.json 中硬编码了 15 种化学品，'
                   '搜索逻辑是：用户输入 → 在这 15 条记录里模糊匹配 → '
                   '把匹配到的化学品与 suppliers.json 的 30 家虚拟供应商关联评分。'
                   '搜索液压泵或任何不在列表里的产品，会直接返回空结果或无意义结果。'))
    story.append(sp(2))
    story.append(box('根本原因：现在是"先有供应商列表，再从里面找"；'
                     '目标是"先搜索，动态建立供应商列表"——这是架构层面的改变，不是简单加几行代码。',
                     sNA, AM, AM2, '⚠'))

    story.append(h2('3.2  目标架构'))
    story.append(tbl(
        ['阶段', '说明'],
        [
            ['用户输入', '任意产品名称，如：液压泵、换热器、聚乙烯、工业滤芯'],
            ['Step 1',   '调用天眼查 open/cloud/search，关键词={产品}制造，拿到候选企业列表'],
            ['Step 2',   '快速过滤：经营范围必须包含查询词 + 含制造/生产/加工等生产动词'],
            ['Step 3',   '批量调用 ic/baseinfoV2/2.0 获取企业详情（有磁盘缓存，已拉过的不重复消耗额度）'],
            ['Step 4',   'tyc_to_supplier() 把天眼查字段映射成系统 Supplier 格式'],
            ['Step 5',   'score_supplier() 五维评分 → 排序展示'],
            ['兜底',     'API 未配置或调用失败时，自动回退到演示模式（suppliers.json）'],
        ],
        cws=[22*mm, 148*mm],
    ))

    story.append(h2('3.3  新文件说明（已提供，无需编写）'))
    story.append(tbl(
        ['文件', '核心功能'],
        [
            ['utils/tyc_client.py',
             '_call_tyc()：统一调用天眼查 | 令牌桶速率限制 | '
             'diskcache 磁盘缓存（search 6h / detail 7天）| '
             'classify_company_role()：判断制造商/经销商 | '
             'is_relevant_to_query()：判断经营范围是否涉及查询品'],
            ['utils/open_search.py',
             'open_search()：开放搜索主入口，接受任意关键词 | '
             'tyc_to_supplier()：天眼查字段到系统 Supplier 格式映射 | '
             'is_api_configured()：检测 API 是否就绪'],
        ],
        cws=[50*mm, 120*mm],
    ))

    story.append(h2('3.4  需要修改的现有文件'))

    story.append(h3('① utils/matcher.py — 加入 API 模式分支（改动约 30 行）'))
    story.append(code([
        '# 在文件顶部新增 import',
        'from utils.open_search import open_search, is_api_configured',
        '',
        '# 修改 match_suppliers() 函数签名，新增 use_api 参数',
        'def match_suppliers(query="", suppliers=None, filters=None,',
        '                    weights=None, use_api=None):',
        '',
        '    # use_api=None 表示自动判断；True 强制 API；False 强制演示数据',
        '    should_use_api = use_api if use_api is not None else is_api_configured()',
        '',
        '    if should_use_api and query:',
        '        # ── API 模式：动态搜索 ──────────────────────────',
        '        result = open_search(query=query, filters=filters, weights=weights)',
        '        return None, result["suppliers"]   # chemical=None（不限化学品）',
        '',
        '    # ── 演示模式（原有逻辑，保持不变）──────────────────',
        '    # ... 以下原有代码不动 ...',
    ]))

    story.append(sp(3))
    story.append(h3('② app.py — 新增模式切换和加载状态（改动约 50 行）'))
    story.append(code([
        '# 1. 文件顶部加载环境变量（已在 2.4 中说明）',
        'from dotenv import load_dotenv',
        'load_dotenv(Path(__file__).parent / ".env.local")',
        '',
        '# 2. 在侧边栏搜索区加模式切换开关',
        'from utils.open_search import is_api_configured',
        'api_ready = is_api_configured()',
        'use_api = st.toggle(',
        '    "启用实时 API 搜索",',
        '    value=api_ready,',
        '    disabled=not api_ready,',
        '    help="需配置 TYC_PROXY_URL" if not api_ready else "已连接天眼查"',
        ')',
        '',
        '# 3. 调用 match_suppliers 时传入 use_api，并加 spinner',
        'with st.spinner("正在从天眼查搜索，请稍候..."):',
        '    chemical, results = match_suppliers(',
        '        query=st.session_state.query,',
        '        suppliers=all_suppliers,',
        '        filters=st.session_state.filters,',
        '        weights=st.session_state.weights,',
        '        use_api=use_api,   # ← 新增此参数',
        '    )',
        '',
        '# 4. API 模式下搜索结果显示数据来源标注',
        'if use_api and results:',
        '    st.caption("数据来源：天眼查 · 仅供参考，请人工复核资质")',
    ]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §4
    # ════════════════════════════════════════════════════════════════
    story.append(h1('4  第三步：工业设备搜索扩展'))
    story.append(rule(G, 1.5))

    story.append(h2('4.1  为什么化学品和工业设备要分开处理'))
    story.append(tbl(
        ['差异点', '化学品（如聚乙烯）', '工业设备（如液压泵）'],
        [
            ['识别方式', 'CAS 号精确匹配，无歧义', '只有产品名，存在同名不同用途'],
            ['危化品资质', '核心评分项（35分）', '通常不需要，改为生产许可证'],
            ['地理分布', '集中在化工园区', '分散，可能在工业园区'],
            ['最小起订量', '吨级', '台/套/批'],
            ['天眼查搜索策略', '直接用产品名+生产', '产品名+制造 或 设备+制造'],
        ],
        cws=[30*mm, 72*mm, 68*mm],
    ))
    story.append(sp(2))
    story.append(box('建议新建 utils/categories.py，用配置字典区分品类，scorer.py 按品类使用不同评分规则。',
                     S('nb2', fontSize=9, leading=13, textColor=colors.HexColor('#1e3a5f')),
                     BL, BL2, 'ℹ'))

    story.append(h2('4.2  品类配置文件（utils/categories.py）— 需新建此文件'))
    story.append(code([
        'CATEGORIES = {',
        '    "chemical": {',
        '        "name": "化工原料",',
        '        "keywords": ["化学品","原料","单体","聚合物","溶剂","树脂"],',
        '        "search_suffix": "生产",    # 天眼查搜索时追加的后缀',
        '        "score_rules": {',
        '            "hazmat_weight": 0.35,  # 危化品资质在合规分里的权重',
        '            "park_bonus": 5,',
        '        },',
        '        "unit": "吨",',
        '    },',
        '    "equipment": {',
        '        "name": "工业设备",',
        '        "keywords": ["泵","阀","换热器","反应釜","压缩机","过滤器",',
        '                     "搅拌","离心机","蒸发器","干燥机","塔"],',
        '        "search_suffix": "制造",',
        '        "score_rules": {',
        '            "hazmat_weight": 0,     # 设备不需要危化品证',
        '            "park_bonus": 0,',
        '            "iso_bonus": 10,        # ISO9001 质量体系加分',
        '        },',
        '        "unit": "台/套",',
        '    },',
        '    "instrument": {',
        '        "name": "仪器仪表",',
        '        "keywords": ["传感器","变送器","分析仪","流量计","压力表","温度计"],',
        '        "search_suffix": "制造",',
        '        "unit": "台",',
        '    },',
        '}',
        '',
        'def detect_category(query: str) -> str:',
        '    for cat_key, cfg in CATEGORIES.items():',
        '        if any(kw in query for kw in cfg["keywords"]):',
        '            return cat_key',
        '    return "chemical"  # 默认化工品',
    ]))

    story.append(h2('4.3  搜索关键词策略'))
    story.append(tbl(
        ['产品示例', '推荐搜索词', '原因'],
        [
            ['聚乙烯',  '聚乙烯制造',   '加"制造"过滤经销商'],
            ['双酚A',   '双酚A生产',    'CAS 80-05-7 对应产品'],
            ['液压泵',  '液压泵制造',   '过滤维修/代理商'],
            ['换热器',  '换热器设备制造','更精确匹配设备厂'],
            ['工业滤芯','过滤器滤芯生产','同义词展开'],
            ['反应釜',  '反应釜生产制造','避免搜到维修服务'],
        ],
        cws=[30*mm, 54*mm, 86*mm],
    ))
    story.append(sp(2))
    story.append(box('open_search.py 已实现基础策略：当查询词长度 ≤6 时自动追加"制造"。'
                     '更精细的控制可在 categories.py 的 search_suffix 字段按品类配置。',
                     sNG, G, GL, '✦'))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §5
    # ════════════════════════════════════════════════════════════════
    story.append(h1('5  接入注意事项'))
    story.append(rule(G, 1.5))

    story.append(h2('5.1  额度保护——这是最重要的一点'))
    story.append(box('个人开发者每日免费额度有限（约 100–500 次）。'
                     '一个不小心的循环调用就能耗尽一天的额度。'
                     'tyc_client.py 已内置令牌桶速率限制（每秒最多 2 次）和磁盘缓存，'
                     '但你仍需理解以下规则。',
                     sNA, AM, AM2, '⚠'))
    story.append(sp(3))
    story.append(tbl(
        ['规则', '说明', '代码位置'],
        [
            ['search 结果缓存 6 小时', '同一关键词 6 小时内只调一次搜索 API', 'CACHE_TTL["search"]'],
            ['detail 结果缓存 7 天',   '同一企业详情 7 天内不重复拉取',       'CACHE_TTL["detail"]'],
            ['速率限制 2 次/秒',       '令牌桶限流，突发最多 5 次',           '_RATE_LIMITER'],
            ['批量最多 3 并发',        'batch_get_details(max_workers=3)',     'tyc_client.py'],
            ['page_size ≤ 20',         '每次搜索最多返回 20 家，不要拉 100 家', 'open_search.py'],
            ['演示模式兜底',           'API 失败自动回退 suppliers.json',      'matcher.py'],
        ],
        cws=[46*mm, 86*mm, 38*mm],
    ))

    story.append(h2('5.2  数据质量问题'))
    story.append(tbl(
        ['问题', '原因', '应对策略'],
        [
            ['经营范围包含产品≠真正生产', '很多公司登记范围很宽泛，注册了但未必实际生产', '依赖采购员人工审核，系统只做初筛'],
            ['注册资本虚高',             '部分中小企业注册资本不实缴',                   '参考但不唯一依赖，结合成立年限'],
            ['企业已注销未更新',         '天眼查数据有 T+1 延迟',                        '过滤 regStatus 非存续/在业的企业'],
            ['同名企业混淆',             '全国多家同名企业',                             '用统一社会信用代码做唯一标识'],
            ['危化品资质推断不准',       '天眼查基础版不直接返回许可证',                 '需调行政许可接口或人工核验'],
            ['产能/价格无法获取',        '工商信息不含产能和报价',                       '留默认值，采购员人工录入'],
        ],
        cws=[38*mm, 60*mm, 72*mm],
    ))

    story.append(h2('5.3  生产商 vs 经销商识别逻辑'))
    story.append(code([
        '经营范围出现 [制造/生产/研发/加工/合成]  → manufacturer（制造商）',
        '经营范围出现 [销售/经销/代理/批发/贸易]  → trader（经销商）',
        '两类词都有                               → both（制造+贸易）',
        '两类词均无                               → unknown（需人工判断）',
        '',
        '# open_search() 默认 include_traders=False，只返回制造商和 both',
        '# 搜索工业设备时建议传入 include_traders=True，',
        '# 因为很多小型设备厂同时做集成和销售',
    ]))
    story.append(sp(2))
    story.append(box('此方法准确率约 75-85%。遇到大量 unknown 时，可在 app.py 加'
                     '一个"包含经销商"勾选框，让采购员自行决定是否查看。',
                     S('nb3', fontSize=9, leading=13, textColor=colors.HexColor('#1e3a5f')),
                     BL, BL2, 'ℹ'))

    story.append(h2('5.4  安全与合规'))
    story.append(tbl(
        ['要点', '说明'],
        [
            ['Token 不进代码',    '.env.local 已在 .gitignore，绝不提交到 Git 仓库'],
            ['FC 代理来源限制',   '生产环境 ALLOWED_ORIGIN 改为公司域名，禁止 * 通配符'],
            ['磁盘缓存权限',      '.cache/ 目录只有应用用户可读，不暴露到 Web 路径'],
            ['天眼查使用协议',    '数据仅供内部采购决策使用，不得对外发布或出售'],
            ['法人姓名脱敏',      '法定代表人姓名不在系统里直接展示，仅供内部核验'],
        ],
        cws=[38*mm, 132*mm],
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §6
    # ════════════════════════════════════════════════════════════════
    story.append(h1('6  分阶段实施路线图'))
    story.append(rule(G, 1.5))
    story.append(tbl(
        ['阶段', '工作内容', '工作量', '完成后效果'],
        [
            ['P0 本地演示',   '当前状态，虚拟数据运行',
             '已完成', '可向团队演示系统功能'],
            ['P1 天眼查接入', '注册+申请接口 / FC 代理部署 / .env 配置 / matcher.py 加 use_api 分支',
             '1–2 天', '搜索聚乙烯可返回天眼查真实企业，五维评分正常运行'],
            ['P2 开放品类',   '创建 categories.py / open_search.py 按品类调整搜索词 / app.py 加品类筛选',
             '1 天', '搜索液压泵、换热器等工业设备可返回制造商列表'],
            ['P3 PubChem',   '创建 utils/chemical_api.py / 自动拉取 CAS/GHS 信息展示',
             '0.5 天', '化学品详情页显示分子式、危险等级等权威信息'],
            ['P4 高德地图',  '申请高德 Key / 地理编码替换省会坐标 / 公路距离替换直线距离',
             '1 天', '地理评分更准确，地图上显示精确供应商位置'],
            ['P5 资质核验',  '危化品证跳转应急管理部官网 / 人工核验流程 + 核验记录存档',
             '0.5 天', '采购员可一键核验资质，系统记录核验状态'],
            ['P6 内部主数据', '对接 ERP 导出的历史合作供应商，填充历史评分维度',
             '需 IT 支持', '历史合作评分维度有真实数据支撑'],
        ],
        cws=[20*mm, 76*mm, 18*mm, 56*mm],
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════
    # §7
    # ════════════════════════════════════════════════════════════════
    story.append(h1('7  附录：环境变量与 API 端点速查'))
    story.append(rule(G, 1.5))

    story.append(h2('环境变量总表'))
    story.append(tbl(
        ['变量名', '存放位置', '必填', '说明'],
        [
            ['TYC_PROXY_URL',   '.env.local（前端）',   '生产必填', '阿里云 FC 触发器 URL'],
            ['TYC_TOKEN',       '.env.local（本地）',   '本地可选', '天眼查 Token，生产用 FC 环境变量'],
            ['TYC_TOKEN',       'FC 环境变量',          '生产必填', '同上，放在服务端'],
            ['ALLOWED_ORIGIN',  'FC 环境变量',          '生产必填', '前端部署域名，防 Token 盗用'],
            ['PUBCHEM_ENABLED', '.env.local',           '可选',     'true 时启用化学品信息查询'],
            ['AMAP_KEY',        'FC 环境变量',          'P4 阶段',  '高德 Web 服务 Key'],
        ],
        cws=[44*mm, 40*mm, 22*mm, 64*mm],
    ))

    story.append(sp(4))
    story.append(h2('天眼查核心 API 端点'))
    story.append(tbl(
        ['端点', '说明', '已在 FC 白名单', '建议接入阶段'],
        [
            ['open/cloud/search',  '企业关键词搜索，匹配名称+经营范围', '✓ 已配置', 'P1'],
            ['ic/baseinfoV2/2.0',  '企业工商基本信息加强版',            '✓ 已配置', 'P1'],
            ['admin/license/2.0',  '行政许可（含生产许可证）',          '需手动加', 'P5'],
            ['judicial/ktgg/2.0',  '司法风险-开庭公告（风险评估）',     '需手动加', 'P6'],
        ],
        cws=[52*mm, 70*mm, 24*mm, 24*mm],
    ))

    story.append(sp(8))
    story.append(rule(BD, 0.5))
    story.append(Paragraph(
        '© SABIC Shanghai 采购与供应链部  ·  API 接入指南 v1.1  ·  仅供内部使用',
        sFT))

    return story

# ── 生成 PDF ─────────────────────────────────────────────────────────
def generate(out_path):
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=18*mm,  bottomMargin=18*mm,
        title='SABIC 寻源系统 API 接入完整指南',
        author='SABIC Shanghai 采购与供应链部',
    )
    doc.build(build())
    print(f'PDF 生成完成: {out_path}')

if __name__ == '__main__':
    generate('/mnt/user-data/outputs/SABIC_API接入完整指南.pdf')
