"""
买化塑 (ibuychem.com) 数据客户端
官网：https://www.ibuychem.com/
定位：化工 / 塑料 / 精细化工 B2B 电商平台，覆盖 20 万+ 化工原料规格数据

数据价值（与企查查的互补性）：
  - 企查查：工商注册信息（法律层面存续）
  - 买化塑：实际产品上架数据（市场层面经营活跃度）
  - 若企业在买化塑有报价 → 证明企业真实在市场上销售
  - 产品 CAS 号、规格参数、报价区间 → 比企查查经营范围更精确

当前状态：买化塑暂无公开 API，采用本地数据导入方案。

══════════════════════════════════════════════════════════════
本地数据导入步骤（手动，每月更新一次即可）：
══════════════════════════════════════════════════════════════
Step 1 ─ 下载供应商数据
  1. 打开 https://www.ibuychem.com/supplier/list
  2. 在搜索框输入产品名（如"聚乙烯"），选择分类
  3. 筛选：地区=全国，企业类型=制造商
  4. 点击右上角"导出" → 下载 Excel 文件

Step 2 ─ 存放目录
  将下载的文件重命名为 <产品名>.xlsx
  放入 sabic-py/data/ibuychem/ 目录

  示例：
    data/ibuychem/聚乙烯.xlsx
    data/ibuychem/双酚A.xlsx
    data/ibuychem/换热器.xlsx

Step 3 ─ Excel 列名规范（系统自动识别以下列名）
  必须包含：公司名称（或"企业名称"/"供应商名称"）
  可选包含：省份、产品名称、规格、价格、CAS号、认证、联系方式

Step 4 ─ 加载验证
  运行以下命令确认数据已正确加载：
    python -c "from utils.ibuychem_client import get_all_suppliers; print(get_all_suppliers()[:3])"
══════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "ibuychem"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# 列名归一化映射（买化塑导出 Excel 的各种列名 → 标准字段名）
_COL_MAP = {
    # 公司名
    "公司名称": "name", "企业名称": "name", "供应商名称": "name", "单位名称": "name",
    "company": "name", "Company": "name",
    # 省份
    "省份": "province", "所在地": "province", "地区": "province",
    # 产品
    "产品名称": "product", "主营产品": "product", "品名": "product",
    # 规格
    "规格": "spec", "型号": "spec",
    # 价格
    "价格": "price", "报价": "price", "单价": "price",
    # CAS
    "CAS号": "cas", "CAS": "cas",
    # 认证
    "认证": "certification", "资质": "certification",
}

_PROVINCE_KEYWORDS = [
    "上海","江苏","浙江","安徽","山东","广东","福建","湖北","湖南",
    "河南","河北","四川","重庆","北京","天津","辽宁","吉林","黑龙江",
    "陕西","甘肃","新疆","内蒙古","云南","贵州","广西","海南","西藏",
    "宁夏","青海","山西","江西",
]


def _norm_province(raw: str) -> str:
    if not raw:
        return ""
    for p in _PROVINCE_KEYWORDS:
        if p in str(raw):
            return p
    return str(raw)[:4]


def _load_excel(path: Path) -> list[dict]:
    try:
        import pandas as pd
        df = pd.read_excel(path, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        # 列名归一化
        rename = {}
        for col in df.columns:
            for orig, std in _COL_MAP.items():
                if orig in col or col in orig:
                    rename[col] = std
                    break
        df = df.rename(columns=rename)
        if "name" not in df.columns:
            logger.warning(f"买化塑文件 {path.name} 缺少公司名列，跳过")
            return []
        # 提取省份（从地址推断）
        if "province" not in df.columns and "address" in df.columns:
            df["province"] = df["address"].apply(_norm_province)
        elif "province" in df.columns:
            df["province"] = df["province"].apply(_norm_province)
        df = df.dropna(subset=["name"])
        return df.to_dict("records")
    except ImportError:
        logger.warning("需要安装 openpyxl：pip install openpyxl")
        return []
    except Exception as e:
        logger.warning(f"读取 {path.name} 失败: {e}")
        return []


def _load_json(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("items", [])
    except Exception as e:
        logger.warning(f"读取 {path.name} 失败: {e}")
        return []


def search_by_keyword(keyword: str) -> list[dict]:
    """
    在本地已下载的买化塑数据中搜索与关键词相关的供应商。
    先查精确匹配的文件名，再在所有文件中做内容匹配。
    """
    results = []
    seen_names: set[str] = set()

    # 1. 按文件名精确匹配
    for suffix in (".xlsx", ".xls", ".json"):
        f = _DATA_DIR / f"{keyword}{suffix}"
        if f.exists():
            items = _load_excel(f) if suffix in (".xlsx", ".xls") else _load_json(f)
            for item in items:
                n = str(item.get("name", ""))
                if n and n not in seen_names:
                    seen_names.add(n)
                    results.append({**item, "_source_ibc": True, "_ibc_keyword": keyword})
            if results:
                return results

    # 2. 全量文件中关键词模糊匹配
    for f in _DATA_DIR.iterdir():
        if f.suffix not in (".xlsx", ".xls", ".json"):
            continue
        items = _load_excel(f) if f.suffix in (".xlsx", ".xls") else _load_json(f)
        for item in items:
            prod = str(item.get("product", "")) + str(item.get("name", ""))
            if keyword in prod:
                n = str(item.get("name", ""))
                if n and n not in seen_names:
                    seen_names.add(n)
                    results.append({**item, "_source_ibc": True, "_ibc_keyword": keyword})
    return results


def get_all_suppliers() -> list[dict]:
    """返回本地所有已加载的买化塑供应商（去重后）"""
    seen: set[str] = set()
    all_items = []
    for f in _DATA_DIR.iterdir():
        if f.suffix in (".xlsx", ".xls"):
            for item in _load_excel(f):
                n = str(item.get("name", ""))
                if n and n not in seen:
                    seen.add(n)
                    all_items.append(item)
        elif f.suffix == ".json":
            for item in _load_json(f):
                n = str(item.get("name", ""))
                if n and n not in seen:
                    seen.add(n)
                    all_items.append(item)
    return all_items


def is_loaded() -> bool:
    """检查本地是否有买化塑数据文件"""
    return any(_DATA_DIR.iterdir())


def get_data_summary() -> dict:
    """返回已加载的数据文件统计"""
    files = list(_DATA_DIR.iterdir())
    return {
        "file_count":     len([f for f in files if f.suffix in (".xlsx",".xls",".json")]),
        "supplier_count": len(get_all_suppliers()),
        "files":          [f.name for f in files],
    }
