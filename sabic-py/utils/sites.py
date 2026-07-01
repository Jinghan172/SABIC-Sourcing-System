# -*- coding: utf-8 -*-
"""
多厂区寻源 —— 厂区定义与『按所选厂区独立计算』的地理评分基础设施  v1.0

本系统原先地理评分固定以上海为基准。现支持四大厂区，用户选定哪个厂区，
该厂区的地理分（距离曲线 + 属地圈层）就以该厂区为锚点独立计算：
  · SH 上海浦东   · NS 广州南沙   · GL 福建漳州（古雷）   · CQ 重庆

距离口径：
  · 上海(SH)：沿用既有人工标定的『各省→上海』公路里程表（保持历史评分一致）。
  · 其余厂区：用各省省会经纬度（regions.json provinceCoords）与厂区坐标做大圆距离，
    再乘 1.25 公路系数近似到厂里程；厂区本省按属地最近距离处理。

属地圈层（home=一级 / near=二级 / 其余=三级）按厂区所在经济区就近划定，
一级圈再给少量『物流成熟度』加成。所有口径透明、可解释、可复算。
"""
from __future__ import annotations
import json
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

_DATA = Path(__file__).parent.parent / "data"
try:
    _REGIONS = json.loads((_DATA / "regions.json").read_text(encoding="utf-8"))
    _PC = _REGIONS.get("provinceCoords", {})
except Exception:
    _PC = {}

DEFAULT_SITE = "SH"
SITE_ORDER = ["SH", "NS", "GL", "CQ"]

SITES = {
    "SH": {"key": "SH", "cn": "上海浦东", "short": "上海", "en": "Shanghai Pudong",
           "cluster_en": "East China", "province": "上海",
           "lat": 31.2304, "lng": 121.4737, "cluster": "华东", "color": "#0E8C3A",
           "home": ["上海", "江苏", "浙江", "安徽"],
           "near": ["山东", "江西", "福建", "湖北", "河南", "湖南"]},
    "NS": {"key": "NS", "cn": "广州南沙", "short": "南沙", "en": "Guangzhou Nansha",
           "cluster_en": "South China", "province": "广东",
           "lat": 22.7716, "lng": 113.5566, "cluster": "华南", "color": "#2563eb",
           "home": ["广东", "广西", "湖南", "江西", "福建", "海南"],
           "near": ["湖北", "贵州", "浙江", "云南", "上海", "江苏"]},
    "GL": {"key": "GL", "cn": "福建漳州古雷", "short": "古雷", "en": "Fujian Gulei",
           "cluster_en": "SE Coast", "province": "福建",
           "lat": 23.74, "lng": 117.54, "cluster": "东南沿海", "color": "#f59e0b",
           "home": ["福建", "广东", "浙江", "江西"],
           "near": ["江苏", "上海", "湖南", "安徽", "广西", "湖北"]},
    "CQ": {"key": "CQ", "cn": "重庆", "short": "重庆", "en": "Chongqing",
           "cluster_en": "Southwest", "province": "重庆",
           "lat": 29.563, "lng": 106.5516, "cluster": "西南", "color": "#a855f7",
           "home": ["重庆", "四川", "贵州", "云南", "陕西"],
           "near": ["湖北", "湖南", "广西", "甘肃", "河南", "江西"]},
}

# 各省 → 上海 公路里程（人工标定，保持上海厂区历史评分一致）
_SH_ROAD = {
    "上海": 0, "江苏": 280, "浙江": 180, "安徽": 450, "山东": 680,
    "广东": 1450, "湖北": 900, "河南": 800, "福建": 900,
    "北京": 1200, "天津": 1100, "河北": 1050, "辽宁": 1600, "吉林": 1900,
    "黑龙江": 2200, "湖南": 1000, "江西": 750, "四川": 2000, "重庆": 1800,
    "陕西": 1500, "山西": 1300, "贵州": 1800, "云南": 2400, "广西": 1700,
    "新疆": 4000, "甘肃": 2500, "内蒙古": 1800,
}

_ROAD_FACTOR = 1.25   # 大圆距离 → 近似公路里程
_LOCAL_KM = 45.0      # 厂区本省（属地）最近距离


def get_site(key: str) -> dict:
    return SITES.get(key, SITES[DEFAULT_SITE])


def all_sites() -> list[dict]:
    return [SITES[k] for k in SITE_ORDER]


def _haversine(lat1, lng1, lat2, lng2) -> float:
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def province_tier(province: str, site_key: str = DEFAULT_SITE) -> int:
    """属地圈层：1=本经济区一级圈 / 2=邻近二级圈 / 3=外省三级圈。"""
    site = get_site(site_key)
    if province in site["home"]:
        return 1
    if province in site["near"]:
        return 2
    return 3


def distance_to_site(province: str, site_key: str = DEFAULT_SITE) -> float:
    """某省到所选厂区的近似到厂里程（km）。"""
    site = get_site(site_key)
    if province == site["province"]:
        return _LOCAL_KM
    if site_key == "SH" and province in _SH_ROAD:
        return float(_SH_ROAD[province])
    pc = _PC.get(province)
    if pc and "lat" in pc and "lng" in pc:
        d = _haversine(pc["lat"], pc["lng"], site["lat"], site["lng"]) * _ROAD_FACTOR
        return round(max(d, _LOCAL_KM), 0)
    # 坐标缺失兜底：按圈层给中性距离
    t = province_tier(province, site_key)
    return 350.0 if t == 1 else (820.0 if t == 2 else 1500.0)


def tier_label(tier: int, site_key: str = DEFAULT_SITE) -> str:
    site = get_site(site_key)
    return {1: f"{site['cluster']} T1·一级圈", 2: f"{site['cluster']} T2·周边二级圈",
            3: "T3·外省三级圈"}.get(tier, "")


def cluster_name(site_key: str = DEFAULT_SITE) -> str:
    return get_site(site_key)["cluster"]
