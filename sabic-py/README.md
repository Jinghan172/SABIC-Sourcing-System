# SABIC 上海在线寻源系统

**版本 v1.7-fix2** · Python / Streamlit · 仅供内部使用

---

## 系统简介

针对 SABIC 上海工厂采购场景的供应商智能匹配系统。输入产品名称，系统从三个数据源检索、评分、交叉验证，帮助采购员快速筛选可信赖的制造商。

**三源交叉验证架构：**

```
企查查（工商权威）+ 化工网（行业活跃度）+ 买化塑（产品真实性）
                       ↓
                置信度评分（0–100%）
                       ↓
             带标注的供应商排名列表
```

---

## 快速启动

```bash
cd sabic-py
pip install -r requirements.txt
streamlit run app.py
# 浏览器打开 http://localhost:8501
```

> **演示模式**：无需配置任何 API Key 即可运行，使用内置虚拟数据（30 家供应商）。所有图表、筛选器、交叉验证功能均可正常演示。

---

## 接入真实数据

### 1. 企查查（P1，优先接入）

```bash
cp .env.example .env.local
# 填写 QCC_APP_KEY 和 QCC_SECRET_KEY
```

注册地址：https://openapi.qcc.com/  
注册后申请「FuzzySearch/GetList」和「ECIV4/GetBasicDetailsByName」两个接口，在「Token 管理」页复制 AppKey 和 SecretKey。

认证方式（已在 `utils/qcc_client.py` 实现，无需手动处理）：
```
Token = MD5(AppKey + 当前时间戳 + SecretKey).toUpperCase()
```

配置好后重启 Streamlit，侧边栏「企查查」状态变为绿色，可搜索任意产品。

### 2. 化工网（P2，可选）

注册地址：https://api.chemnet.com  
获取 API Key 后填入 `.env.local` 的 `CHEMNET_API_KEY`。
化工网提供行业活跃度验证，补充企查查工商数据。

### 3. 买化塑（无需 API，手动更新）

1. 打开 https://www.ibuychem.com/supplier/list
2. 搜索产品名 → 筛选「制造商」→ 导出 Excel
3. 重命名为 `<产品名>.xlsx` 放入 `data/ibuychem/` 目录
4. 重启 Streamlit 自动加载

示例：`data/ibuychem/换热器.xlsx`、`data/ibuychem/离心泵.xlsx`

---

## 项目结构

```
sabic-py/
├── app.py                        # 主应用
├── requirements.txt
├── Dockerfile
├── .env.example                  # 配置模板（可提交）
├── .env.local                    # 实际密钥（不提交，本地创建）
├── .streamlit/config.toml
│
├── data/
│   ├── suppliers.json            # 演示供应商（30 家）
│   ├── chemicals.json            # 演示化学品（15 种）
│   ├── categories.json           # 采购品类配置（10 类，57 种产品）
│   ├── synonyms.json             # 同义词表（67 条，自动生成）
│   ├── regions.json              # 省份地理 + 圈层数据
│   ├── china.json                # 中国地图 GeoJSON（1.2 MB）
│   ├── chemnet/                  # 化工网缓存（自动生成，可删除）
│   └── ibuychem/                 # 买化塑手动下载文件（*.xlsx）
│
├── utils/
│   ├── qcc_client.py             # 企查查客户端（MD5签名 + 6h搜索缓存 + 7天详情缓存）
│   ├── chemnet_client.py         # 化工网客户端（Bearer Token）
│   ├── ibuychem_client.py        # 买化塑本地数据加载器
│   ├── cross_validator.py        # 三源交叉验证引擎
│   ├── sabic_search.py           # SABIC 专项搜索策略（19 品类）
│   ├── open_search.py            # 开放搜索（企查查动态搜索任意产品）
│   ├── matcher.py                # 匹配核心（9 维筛选）
│   ├── scorer.py                 # 四维量化评分 v2.0
│   └── exporter.py               # Excel 导出
│
└── components/
    └── charts.py                 # 7 种 Plotly 图表
```

---

## 评分模型（v2.0）

四维全量化，所有指标来自企查查客观字段：

| 维度 | 权重 | 数据来源 | 计算方式 |
|---|---|---|---|
| 地理位置 | 30% | Province → 圈层 + 距离 km | `0.70 × 圈层分 + 0.30 × 距离分` |
| 企业规模 | 30% | RegistCapi + StartDate | `0.65 × 资本对数分 + 0.35 × 年限分` |
| 合规资质 | 25% | Status + 经营范围分类 + 危化品 | 布尔标志加权（最高 100） |
| 经营相关度 | 15% | Scope 文本匹配查询词 | 词频 + 同义词 + 制造商加成 |

权重可在侧边栏「评分权重」区域调整，自动归一化。

---

## 交叉验证置信度

| 条件 | 置信度 |
|---|---|
| 企查查有记录（基础） | 60% |
| 化工网命中 | +20% |
| 买化塑命中 | +15% |
| 两源同时命中（额外） | +10% |
| 产品名与查询词匹配 | +8% |
| 上限 | 100% |

供应商卡片显示：百分比 + 三源圆点（● 命中 / ○ 未命中）  
列表顶部显示：本次搜索的化工网命中数、买化塑命中数、置信度均值  
详情页显示：各源匹配相似度、化工网报价参考、买化塑产品规格

---

## 筛选器（9 维）

| 分组 | 筛选项 | 对应企查查字段 |
|---|---|---|
| 📍 地域 | 圈层（一/二/三级）+ 省份多选 | Province |
| 🏢 企业信息 | 仅存续 / 企业类型 / 最低注册资本 / 成立年份 ≥ | Status / 经营范围 / RegistCapi / StartDate |
| 📋 资质 | 含危化品资质 / 经营范围包含词 | Scope 文本匹配 |
| 🎯 评分 | 最低综合评分 | 计算后过滤 |

---

## 图表说明

| 标签 | 类型 | 功能 |
|---|---|---|
| 雷达图 | `go.Scatterpolar` | 对比选中企业的多维得分 |
| 柱状图 | `go.Bar` | 按指定维度排名 |
| 供应商对比 | `st.dataframe` | 多家并排数据表 |
| 维度剖面 | `go.Scatter` | 每家企业一条折线，悬停显示各维度精确分 |
| 热力矩阵 | `go.Heatmap` | 企业×维度热图，红→绿高对比色阶 |
| 气泡图 | `go.Scatter` | 均价 × 产能 × 综合评分 |
| 中国地图 | `go.Choropleth + Scattergeo` | 省份热力 + 供应商位置 |

---

## SABIC 专项搜索品类（19 个）

侧边栏搜索框下方有快捷按钮，一键发起精准搜索：

**化工原料**：聚乙烯、聚丙烯、双酚A、乙二醇  
**工艺设备**：换热器、反应釜、离心泵、磁力泵、压缩机、球阀、调节阀  
**仪器仪表**：流量计、DCS 控制系统、压力变送器  
**包装 & MRO**：IBC 吨桶、密封件、滤芯  
**助剂**：抗氧剂、阻燃剂

每个品类配置了 2–4 个精细搜索词（如「换热器」→「换热器制造/管壳式换热器生产/板式换热器制造」），过滤贸易商干扰。

---

## Docker 部署

```bash
docker build -t sabic-sourcing:v1.7 .

docker run -d \
  --name sabic-app \
  -p 8501:8501 \
  -e QCC_APP_KEY="your_key" \
  -e QCC_SECRET_KEY="your_secret" \
  -v $(pwd)/data/ibuychem:/app/data/ibuychem \
  -v $(pwd)/.cache:/app/.cache \
  sabic-sourcing:v1.7
```

---

## 常见问题

**搜索没有结果** → 演示模式下虚拟数据不含全部品类，接入企查查后可搜索任意产品。

**企查查 401 错误** → Token 需每次请求实时生成。确认 `QCC_APP_KEY` 和 `QCC_SECRET_KEY` 正确填写后重启。

**地图不显示** → 确认 `data/china.json` 存在（约 1.2 MB）。

**plotly_chart DuplicateElementId** → 请使用 v1.7-fix2 版本，旧版本中所有 `st.plotly_chart` 已添加唯一 `key`。

**买化塑加载后无变化** → 确认文件在 `data/ibuychem/` 目录，且 Excel 含「公司名称」列，重启后生效。

**ImportError: cannot import name 'SUPPLIERS_RAW' from 'utils.sabic_search'** → 已在 fix2 修复。确保使用最新版 `app.py`。

---

## 版本历史

| 版本 | 变更内容 |
|---|---|
| **v1.7-fix2** | 修复 `SUPPLIERS_RAW` 导入路径错误；演示模式交叉验证始终运行；侧边栏数据源状态面板；供应商卡片置信度标签 + 三源圆点 |
| v1.7 | 化工网/买化塑客户端；三源交叉验证引擎；SABIC 专项搜索策略（19 品类）；部署报告 PDF |
| v1.6 | plotly_chart 重复 ID 修复；供应商详情卡增强（工商+资质+API预留）；采购品类配置文件（10 类 57 产品） |
| v1.5 | 四维量化评分 v2.0（去主观维度）；企查查式增强筛选器（9 维）；地图散点颜色修复 |
| v1.4 | 平行坐标改为维度剖面折线图；热力图色阶改造；checkbox 空 label 修复 |
| v1.3-qcc | 切换企查查；开放产品搜索；中国地图 GeoJSON |

---

*SABIC Shanghai · 采购与供应链部 · 仅供内部使用*
