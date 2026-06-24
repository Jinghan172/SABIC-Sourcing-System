"""
SABIC 上海采购专项搜索策略
品类来源：SABIC Categories.xlsx（化工原材料 + 助剂 + 包装，非设备）+ 行业相关补充品类
每个品类：中文名 → 企查查中文搜索关键词；同时记录英文简称用于快捷按钮

priority: 1 = P1 核心采购品类（来自 Categories.xlsx，SABIC 官方采购清单）
priority: 2 = P2 扩展品类（行业高度相关的补充品类，不在 Categories 清单内）
"""
from __future__ import annotations
import json
from pathlib import Path

# ── SABIC 采购品类搜索策略 ────────────────────────────────────────────
# 结构：中文品类名 → {keywords, en, group, priority}
SABIC_SEARCH_STRATEGIES = {
    # ═══════════════════════════════════════════════════════════════
    # 原材料 RMs — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "ABS树脂": {"keywords": ["ABS树脂生产", "ABS工程塑料制造"], "en": "ABS", "group": "原材料 RMs", "priority": 1},
    "聚丙烯": {"keywords": ["聚丙烯生产", "PP树脂制造"], "en": "PP", "group": "原材料 RMs", "priority": 1},
    "聚碳酸酯": {"keywords": ["聚碳酸酯生产", "PC树脂制造"], "en": "PC", "group": "原材料 RMs", "priority": 1},
    "PET聚酯": {"keywords": ["聚对苯二甲酸乙二醇酯", "PET切片生产"], "en": "PET", "group": "原材料 RMs", "priority": 1},
    "PBT聚酯": {"keywords": ["聚对苯二甲酸丁二醇酯", "PBT树脂制造"], "en": "PBT", "group": "原材料 RMs", "priority": 1},
    "聚甲基丙烯酸甲酯": {"keywords": ["PMMA生产", "亚克力树脂制造"], "en": "PMMA", "group": "原材料 RMs", "priority": 1},
    "聚苯醚": {"keywords": ["聚苯醚生产", "PPO树脂制造"], "en": "PPO", "group": "原材料 RMs", "priority": 1},
    "聚苯乙烯": {"keywords": ["聚苯乙烯生产", "GPPS HIPS制造"], "en": "PS", "group": "原材料 RMs", "priority": 1},
    "双酚A": {"keywords": ["双酚A生产", "双酚A制造"], "en": "BPA", "group": "原材料 RMs", "priority": 1},
    "1,4-丁二醇": {"keywords": ["1,4-丁二醇生产", "BDO制造"], "en": "BDO", "group": "原材料 RMs", "priority": 1},
    "丙烯腈": {"keywords": ["丙烯腈生产", "丙烯腈制造"], "en": "AcN", "group": "原材料 RMs", "priority": 1},
    "马来酸酐": {"keywords": ["马来酸酐生产", "顺酐制造"], "en": "MA", "group": "原材料 RMs", "priority": 1},
    "苯酐": {"keywords": ["苯酐生产", "邻苯二甲酸酐制造"], "en": "PA", "group": "原材料 RMs", "priority": 1},
    "间苯二甲酸": {"keywords": ["间苯二甲酸生产", "IPA制造"], "en": "IPA", "group": "原材料 RMs", "priority": 1},
    "己烷": {"keywords": ["己烷生产", "正己烷制造"], "en": "Hexane", "group": "原材料 RMs", "priority": 1},
    "蓖麻油": {"keywords": ["蓖麻油生产", "蓖麻油加工"], "en": "Castor Oil", "group": "原材料 RMs", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 原材料 RMs — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "铝粉": {"keywords": ["铝粉生产", "铝银浆制造", "球形铝粉生产"], "en": "AlPow", "group": "原材料 RMs", "priority": 1},
    "BDDMA单体": {"keywords": ["1,4-丁二醇二甲基丙烯酸酯生产", "BDDMA制造"], "en": "BDDMA", "group": "原材料 RMs", "priority": 1},
    "1-己烯": {"keywords": ["1-己烯生产", "己烯共聚单体制造"], "en": "Hex1", "group": "原材料 RMs", "priority": 1},
    "异丁烷": {"keywords": ["异丁烷生产", "液化异丁烷制造"], "en": "Isobutane", "group": "原材料 RMs", "priority": 1},
    "异己烷": {"keywords": ["异己烷生产", "异己烷制造"], "en": "Isohexane", "group": "原材料 RMs", "priority": 1},
    "正庚烷": {"keywords": ["正庚烷生产", "正庚烷制造"], "en": "nHeptane", "group": "原材料 RMs", "priority": 1},
    "聚丁二烯橡胶": {"keywords": ["聚丁二烯橡胶生产", "顺丁橡胶制造", "BR橡胶生产"], "en": "PBR", "group": "原材料 RMs", "priority": 1},
    "PCCD聚酯": {"keywords": ["PCCD生产", "聚环己烷二甲醇碳酸酯"], "en": "PCCD", "group": "原材料 RMs", "priority": 1},
    "PCT/PCTG聚酯": {"keywords": ["PCTG生产", "PCT聚酯制造", "改性聚酯生产"], "en": "PCT", "group": "原材料 RMs", "priority": 1},
    "SAN树脂": {"keywords": ["SAN树脂生产", "苯乙烯丙烯腈共聚物制造"], "en": "SAN", "group": "原材料 RMs", "priority": 1},
    "三羟基苯乙酮": {"keywords": ["三羟基苯乙酮生产", "THPE制造", "苯乙酮衍生物"], "en": "THPE", "group": "原材料 RMs", "priority": 1},
    "3-巯基丙酸": {"keywords": ["3-巯基丙酸生产", "有机硫化物制造"], "en": "3MPA", "group": "原材料 RMs", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 原材料 RMs — P2（聚合物补充）
    # ═══════════════════════════════════════════════════════════════
    "尼龙6": {"keywords": ["聚酰胺6生产", "PA6切片制造", "尼龙6工程塑料"], "en": "PA6", "group": "原材料 RMs", "priority": 2},
    "尼龙66": {"keywords": ["聚酰胺66生产", "PA66工程塑料", "尼龙66制造"], "en": "PA66", "group": "原材料 RMs", "priority": 2},
    "尼龙12": {"keywords": ["聚酰胺12生产", "PA12制造"], "en": "PA12", "group": "原材料 RMs", "priority": 2},
    "热塑性聚氨酯": {"keywords": ["TPU弹性体生产", "热塑性聚氨酯制造"], "en": "TPU", "group": "原材料 RMs", "priority": 2},
    "聚甲醛": {"keywords": ["聚甲醛生产", "POM工程塑料制造"], "en": "POM", "group": "原材料 RMs", "priority": 2},
    "聚苯硫醚": {"keywords": ["聚苯硫醚生产", "PPS工程塑料制造"], "en": "PPS", "group": "原材料 RMs", "priority": 2},
    "聚醚醚酮": {"keywords": ["PEEK生产", "聚醚醚酮制造"], "en": "PEEK", "group": "原材料 RMs", "priority": 2},
    "液晶聚合物": {"keywords": ["液晶聚合物生产", "LCP树脂制造"], "en": "LCP", "group": "原材料 RMs", "priority": 2},
    "热塑性弹性体": {"keywords": ["TPE弹性体生产", "热塑性橡胶制造"], "en": "TPE", "group": "原材料 RMs", "priority": 2},
    "乙烯醋酸乙烯共聚物": {"keywords": ["EVA生产", "乙烯醋酸乙烯共聚物制造"], "en": "EVA", "group": "原材料 RMs", "priority": 2},
    "高密度聚乙烯": {"keywords": ["HDPE生产", "高密度聚乙烯制造"], "en": "HDPE", "group": "原材料 RMs", "priority": 2},
    "线性低密度聚乙烯": {"keywords": ["LLDPE生产", "线性低密度聚乙烯制造"], "en": "LLDPE", "group": "原材料 RMs", "priority": 2},
    "聚氯乙烯": {"keywords": ["PVC生产", "聚氯乙烯制造"], "en": "PVC", "group": "原材料 RMs", "priority": 2},
    "聚乙烯醇缩丁醛": {"keywords": ["PVB生产", "聚乙烯醇缩丁醛制造"], "en": "PVB", "group": "原材料 RMs", "priority": 2},
    "聚砜": {"keywords": ["聚砜生产", "PSU工程塑料制造"], "en": "PSU", "group": "原材料 RMs", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 原材料 RMs — P2（化工原料补充）
    # ═══════════════════════════════════════════════════════════════
    "苯乙烯": {"keywords": ["苯乙烯生产", "苯乙烯单体制造"], "en": "Styrene", "group": "原材料 RMs", "priority": 2},
    "己内酰胺": {"keywords": ["己内酰胺生产", "尼龙6原料制造"], "en": "Caprolactam", "group": "原材料 RMs", "priority": 2},
    "己二酸": {"keywords": ["己二酸生产", "尼龙66原料制造"], "en": "Adipic Acid", "group": "原材料 RMs", "priority": 2},
    "二苯甲烷二异氰酸酯": {"keywords": ["MDI生产", "异氰酸酯制造"], "en": "MDI", "group": "原材料 RMs", "priority": 2},
    "甲苯二异氰酸酯": {"keywords": ["TDI生产", "甲苯二异氰酸酯制造"], "en": "TDI", "group": "原材料 RMs", "priority": 2},
    "环氧氯丙烷": {"keywords": ["环氧氯丙烷生产", "ECH制造"], "en": "ECH", "group": "原材料 RMs", "priority": 2},
    "碳酸二甲酯": {"keywords": ["碳酸二甲酯生产", "DMC制造"], "en": "DMC", "group": "原材料 RMs", "priority": 2},
    "乙二醇": {"keywords": ["乙二醇生产", "MEG制造"], "en": "EG", "group": "原材料 RMs", "priority": 2},
    "苯酚": {"keywords": ["苯酚生产", "纯苯酚制造"], "en": "Phenol", "group": "原材料 RMs", "priority": 2},
    "丙酮": {"keywords": ["丙酮生产", "丙酮制造"], "en": "Acetone", "group": "原材料 RMs", "priority": 2},
    "丙烯酸": {"keywords": ["丙烯酸生产", "丙烯酸制造"], "en": "Acrylic Acid", "group": "原材料 RMs", "priority": 2},
    "正丁醇": {"keywords": ["正丁醇生产", "丁醇制造"], "en": "Butanol", "group": "原材料 RMs", "priority": 2},
    "乙酸乙酯": {"keywords": ["乙酸乙酯生产", "醋酸乙酯制造"], "en": "EtOAc", "group": "原材料 RMs", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 阻燃剂 Flame Retardants — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "溴系阻燃剂": {"keywords": ["溴系阻燃剂生产", "溴化阻燃剂制造"], "en": "Br-FR", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "四溴双酚A": {"keywords": ["四溴双酚A生产", "TBBPA制造"], "en": "TBBPA", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "间苯二酚双磷酸酯": {"keywords": ["RDP阻燃剂", "磷酸酯阻燃剂生产"], "en": "RDP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "双酚A双磷酸酯": {"keywords": ["BDP阻燃剂", "双酚A双磷酸酯"], "en": "BDP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "磷酸三苯酯": {"keywords": ["磷酸三苯酯生产", "TPP制造"], "en": "TPP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "三氧化二锑": {"keywords": ["三氧化二锑生产", "锑白粉制造"], "en": "ATO", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "聚磷酸蜜胺": {"keywords": ["聚磷酸蜜胺生产", "MPP阻燃剂"], "en": "MPP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "二乙基次膦酸铝": {"keywords": ["次膦酸铝生产", "磷系阻燃剂制造"], "en": "Al-Phos", "group": "阻燃剂 Flame Retardants", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 阻燃剂 Flame Retardants — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "ATO母粒": {"keywords": ["三氧化二锑母粒生产", "ATO阻燃母粒制造"], "en": "ATO-MB", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "溴化丙烯酸酯": {"keywords": ["溴化丙烯酸酯生产", "溴系丙烯酸酯阻燃剂"], "en": "BrAcr", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "溴化环氧树脂": {"keywords": ["溴化环氧树脂生产", "溴化环氧阻燃剂制造"], "en": "BrEpoxy", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "溴素": {"keywords": ["溴素生产", "液溴制造", "溴化工生产"], "en": "Bromine", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "溴化聚苯乙烯": {"keywords": ["溴化聚苯乙烯生产", "BrPS阻燃剂制造"], "en": "BrPS", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "TBBPA二缩水甘油醚": {"keywords": ["TBBPA二缩水甘油醚生产", "溴化环氧活性阻燃剂"], "en": "TBBPA-DGE", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "TBBPA甲基苯基醚": {"keywords": ["TBBPA甲基苯基醚生产", "溴化阻燃剂制造"], "en": "TBBPA-MPE", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "溴化碳酸酯低聚物": {"keywords": ["溴化碳酸酯低聚物生产", "溴化PC低聚物"], "en": "BrCO", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "双酚A磷酸二苯酯": {"keywords": ["双酚A双磷酸酯生产", "BDP阻燃剂制造"], "en": "BPA-DP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "膨胀型磷系阻燃剂": {"keywords": ["膨胀型阻燃剂生产", "IFR阻燃体系制造"], "en": "IntP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "全氟丁基磺酸钾": {"keywords": ["磺酸钾盐阻燃剂生产", "KSS制造"], "en": "KSS", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "芳香族磺酸钠": {"keywords": ["芳香族磺酸钠生产", "磺酸盐阻燃剂制造"], "en": "NATS", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "苯氧基磷腈": {"keywords": ["环状磷腈阻燃剂生产", "苯氧基磷腈制造"], "en": "Phosphazene", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "间苯二酚": {"keywords": ["间苯二酚生产", "间苯二酚制造"], "en": "Resorcinol", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "全氟乙基磺酸钾": {"keywords": ["全氟乙基磺酸钾生产", "Rimar盐制造"], "en": "Rimar", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "Sol-DP磷酸酯": {"keywords": ["Sol-DP磷酸酯生产", "脂肪族磷酸二苯酯"], "en": "SolDP", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "特种滑石粉": {"keywords": ["特种滑石粉生产", "阻燃级滑石粉制造"], "en": "SpecTalc", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "STB磺酸盐": {"keywords": ["芳香族磺酸盐生产", "STB阻燃剂制造"], "en": "STB", "group": "阻燃剂 Flame Retardants", "priority": 1},
    "磷酸三烯丙酯": {"keywords": ["磷酸三烯丙酯生产", "TAP制造"], "en": "TAP", "group": "阻燃剂 Flame Retardants", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 阻燃剂 Flame Retardants — P2
    # ═══════════════════════════════════════════════════════════════
    "氢氧化铝": {"keywords": ["氢氧化铝阻燃剂生产", "ATH制造"], "en": "ATH", "group": "阻燃剂 Flame Retardants", "priority": 2},
    "氢氧化镁": {"keywords": ["氢氧化镁阻燃剂生产", "MDH制造"], "en": "MDH", "group": "阻燃剂 Flame Retardants", "priority": 2},
    "硼酸锌": {"keywords": ["硼酸锌生产", "阻燃硼酸锌制造"], "en": "Zinc Borate", "group": "阻燃剂 Flame Retardants", "priority": 2},
    "红磷": {"keywords": ["红磷阻燃剂生产", "包覆红磷制造"], "en": "Red Phosphorus", "group": "阻燃剂 Flame Retardants", "priority": 2},
    "三聚氰胺": {"keywords": ["三聚氰胺生产", "蜜胺制造"], "en": "Melamine", "group": "阻燃剂 Flame Retardants", "priority": 2},
    "DOPO磷阻燃剂": {"keywords": ["DOPO生产", "有机磷阻燃剂制造"], "en": "DOPO", "group": "阻燃剂 Flame Retardants", "priority": 2},
    "防滴落剂": {"keywords": ["防滴落剂生产", "抗熔滴剂制造"], "en": "Anti-drip", "group": "阻燃剂 Flame Retardants", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 抗冲改性剂 Impact Modifiers — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "氢化苯乙烯嵌段共聚物": {"keywords": ["SEBS生产", "热塑性弹性体制造"], "en": "SEBS", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "苯乙烯丁二烯嵌段共聚物": {"keywords": ["SBS生产", "SBS弹性体制造"], "en": "SBS", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "聚烯烃弹性体": {"keywords": ["POE生产", "聚烯烃弹性体制造"], "en": "POE", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "甲基丙烯酸酯丁二烯苯乙烯": {"keywords": ["MBS树脂生产", "MBS改性剂"], "en": "MBS", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "马来酸酐接枝PE": {"keywords": ["马来酸酐接枝", "相容剂生产"], "en": "PE-MA", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "有机硅抗冲剂": {"keywords": ["有机硅母粒生产", "硅酮母粒制造"], "en": "Silicon-IM", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 抗冲改性剂 Impact Modifiers — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "丙烯酸酯抗冲改性剂": {"keywords": ["ACR抗冲改性剂生产", "丙烯酸酯抗冲剂制造", "丙烯酸酯核壳结构改性剂"], "en": "AIM", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "PTFE包覆SAN": {"keywords": ["PTFE包覆SAN生产", "TSAN防滴落剂制造"], "en": "TSAN", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "SEP嵌段共聚物": {"keywords": ["SEP生产", "苯乙烯乙烯丙烯嵌段共聚物"], "en": "SEP", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},
    "马来酸酐接枝PP": {"keywords": ["马来酸酐接枝聚丙烯生产", "PP-g-MA制造"], "en": "PP-MA", "group": "抗冲改性剂 Impact Modifiers", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 抗冲改性剂 Impact Modifiers — P2
    # ═══════════════════════════════════════════════════════════════
    "相容剂": {"keywords": ["相容剂生产", "增容剂制造"], "en": "Compatibilizer", "group": "抗冲改性剂 Impact Modifiers", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 氟塑料 Fluoropolymers — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "ETFE氟塑料": {"keywords": ["ETFE生产", "乙烯四氟乙烯共聚物制造"], "en": "ETFE", "group": "氟塑料 Fluoropolymers", "priority": 1},
    "PTFE分散液": {"keywords": ["PTFE乳液生产", "聚四氟乙烯分散液制造"], "en": "PTFE-D", "group": "氟塑料 Fluoropolymers", "priority": 1},
    "PTFE粉": {"keywords": ["聚四氟乙烯粉生产", "PTFE模压粉制造"], "en": "PTFE-P", "group": "氟塑料 Fluoropolymers", "priority": 1},
    "聚偏氟乙烯": {"keywords": ["PVDF生产", "聚偏氟乙烯制造", "偏氟乙烯树脂"], "en": "PVDF", "group": "氟塑料 Fluoropolymers", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 稳定剂 Stabilizers — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "抗氧剂": {"keywords": ["抗氧剂生产", "酚类抗氧剂制造"], "en": "AO", "group": "稳定剂 Stabilizers", "priority": 1},
    "受阻胺光稳定剂": {"keywords": ["受阻胺光稳定剂", "HALS生产"], "en": "HALS", "group": "稳定剂 Stabilizers", "priority": 1},
    "紫外线吸收剂": {"keywords": ["紫外线吸收剂生产", "UV吸收剂制造"], "en": "UV", "group": "稳定剂 Stabilizers", "priority": 1},
    "热稳定剂": {"keywords": ["热稳定剂生产", "热稳定剂制造"], "en": "Heat-Stab", "group": "稳定剂 Stabilizers", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 稳定剂 Stabilizers — P2
    # ═══════════════════════════════════════════════════════════════
    "成核剂": {"keywords": ["成核剂生产", "塑料成核剂制造"], "en": "Nucleating Agent", "group": "稳定剂 Stabilizers", "priority": 2},
    "增塑剂": {"keywords": ["增塑剂生产", "DINP制造", "DOP生产"], "en": "Plasticizer", "group": "稳定剂 Stabilizers", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 硬脂酸盐/润滑 Stearates — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "金属硬脂酸盐": {"keywords": ["硬脂酸盐生产", "硬脂酸钙制造"], "en": "Met-Stearate", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},
    "季戊四醇硬脂酸酯": {"keywords": ["PETS生产", "季戊四醇硬脂酸酯"], "en": "PETS", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},
    "蒙旦蜡": {"keywords": ["蒙旦蜡生产", "褐煤蜡制造"], "en": "Montan-Wax", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},
    "抗静电剂": {"keywords": ["抗静电剂生产", "抗静电剂制造"], "en": "Anti-static", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 硬脂酸盐/润滑 Stearates — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "甘油单硬脂酸酯": {"keywords": ["甘油单硬脂酸酯生产", "GMS制造", "单甘酯生产"], "en": "GMS90", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},
    "滑爽剂": {"keywords": ["滑爽剂生产", "油酸酰胺制造", "爽滑剂生产"], "en": "Slip", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},
    "复合稳定剂预混料": {"keywords": ["复合稳定剂生产", "预混稳定剂制造", "一体化助剂包"], "en": "Preblends", "group": "硬脂酸盐/润滑 Stearates", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 硬脂酸盐/润滑 Stearates — P2
    # ═══════════════════════════════════════════════════════════════
    "脱模剂": {"keywords": ["脱模剂生产", "塑料脱模剂制造"], "en": "Mold Release", "group": "硬脂酸盐/润滑 Stearates", "priority": 2},
    "硅油": {"keywords": ["硅油生产", "聚二甲基硅氧烷制造"], "en": "Silicone Oil", "group": "硬脂酸盐/润滑 Stearates", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 色料/增强 Colorants & Reinforcements — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "炭黑": {"keywords": ["炭黑生产", "色素炭黑制造"], "en": "CB", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "钛白粉": {"keywords": ["钛白粉生产", "二氧化钛制造"], "en": "TiO2", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "玻璃纤维": {"keywords": ["玻璃纤维生产", "玻纤制造"], "en": "GF", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "碳纤维": {"keywords": ["碳纤维生产", "碳纤维制造"], "en": "CF", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "滑石粉": {"keywords": ["滑石粉生产", "滑石粉加工"], "en": "Talc", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "色母粒": {"keywords": ["色母粒生产", "着色母粒制造"], "en": "Color-MB", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "有机颜料": {"keywords": ["有机颜料生产", "有机颜料制造"], "en": "Org-Pig", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "无机颜料": {"keywords": ["无机颜料生产", "无机颜料制造"], "en": "Inorg-Pig", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 色料/增强 Colorants & Reinforcements — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "碳纳米管": {"keywords": ["碳纳米管生产", "多壁碳纳米管制造"], "en": "CNT", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "导电炭黑": {"keywords": ["导电炭黑生产", "导电碳黑制造"], "en": "ConductCB", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "染料": {"keywords": ["分散染料生产", "工业染料制造", "活性染料生产"], "en": "Dyes", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "再生碳纤维": {"keywords": ["再生碳纤维生产", "回收碳纤维制造"], "en": "RCF", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "有机硅烷": {"keywords": ["硅烷偶联剂生产", "有机硅烷制造"], "en": "Siloxane", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "聚乙烯蜡": {"keywords": ["聚乙烯蜡生产", "PE蜡制造", "氧化聚乙烯蜡"], "en": "WAX", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "硫化锌": {"keywords": ["硫化锌生产", "硫化锌制造"], "en": "ZnS", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},
    "炭黑母粒": {"keywords": ["炭黑母粒生产", "黑色母粒制造", "炭黑色母制造"], "en": "CBMB", "group": "色料/增强 Colorants & Reinforcements", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 色料/增强 Colorants & Reinforcements — P2
    # ═══════════════════════════════════════════════════════════════
    "重质碳酸钙": {"keywords": ["重质碳酸钙生产", "碳酸钙填料制造"], "en": "CaCO3", "group": "色料/增强 Colorants & Reinforcements", "priority": 2},
    "云母粉": {"keywords": ["云母粉生产", "绢云母制造"], "en": "Mica", "group": "色料/增强 Colorants & Reinforcements", "priority": 2},
    "硫酸钡": {"keywords": ["硫酸钡生产", "超细硫酸钡制造"], "en": "BaSO4", "group": "色料/增强 Colorants & Reinforcements", "priority": 2},
    "硅灰石": {"keywords": ["硅灰石生产", "针状硅灰石制造"], "en": "Wollastonite", "group": "色料/增强 Colorants & Reinforcements", "priority": 2},
    "高岭土": {"keywords": ["煅烧高岭土生产", "高岭土填料制造"], "en": "Kaolin", "group": "色料/增强 Colorants & Reinforcements", "priority": 2},
    "硅烷偶联剂": {"keywords": ["硅烷偶联剂生产", "有机硅烷制造"], "en": "Silane", "group": "色料/增强 Colorants & Reinforcements", "priority": 2},

    # ═══════════════════════════════════════════════════════════════
    # 包装 Packaging — P1（Categories.xlsx 原有）
    # ═══════════════════════════════════════════════════════════════
    "木托盘": {"keywords": ["木托盘生产", "木制托盘制造"], "en": "Pallet", "group": "包装 Packaging", "priority": 1},
    "集装袋": {"keywords": ["集装袋生产", "吨袋制造"], "en": "FIBC", "group": "包装 Packaging", "priority": 1},
    "散装内衬袋": {"keywords": ["集装箱内衬袋", "散装内衬生产"], "en": "Bulk-Liner", "group": "包装 Packaging", "priority": 1},
    "瓦楞纸箱": {"keywords": ["瓦楞纸箱生产", "纸箱制造"], "en": "Corrugated", "group": "包装 Packaging", "priority": 1},

    # ═══════════════════════════════════════════════════════════════
    # 包装 Packaging — P1 新增（Categories.xlsx）
    # ═══════════════════════════════════════════════════════════════
    "软包装": {"keywords": ["工业软包装生产", "塑料编织袋制造", "复合软包装生产"], "en": "FlexPack", "group": "包装 Packaging", "priority": 1},
}

# ── 快捷搜索按钮（英文简称 + 中文名，按采购大类分组）──────────────────
QUICK_CATEGORIES = {
    "原材料 RMs": [
        ("ABS", "ABS树脂"),
        ("PP", "聚丙烯"),
        ("PC", "聚碳酸酯"),
        ("PET", "PET聚酯"),
        ("PBT", "PBT聚酯"),
        ("PMMA", "聚甲基丙烯酸甲酯"),
        ("PPO", "聚苯醚"),
        ("PS", "聚苯乙烯"),
        ("BPA", "双酚A"),
        ("BDO", "1,4-丁二醇"),
        ("AcN", "丙烯腈"),
        ("MA", "马来酸酐"),
        ("PA", "苯酐"),
        ("IPA", "间苯二甲酸"),
        ("Hexane", "己烷"),
        ("Castor Oil", "蓖麻油"),
        ("AlPow", "铝粉"),
        ("BDDMA", "BDDMA单体"),
        ("Hex1", "1-己烯"),
        ("Isobutane", "异丁烷"),
        ("Isohexane", "异己烷"),
        ("nHeptane", "正庚烷"),
        ("PBR", "聚丁二烯橡胶"),
        ("PCCD", "PCCD聚酯"),
        ("PCT", "PCT/PCTG聚酯"),
        ("SAN", "SAN树脂"),
        ("THPE", "三羟基苯乙酮"),
        ("3MPA", "3-巯基丙酸"),
        ("PA6", "尼龙6"),
        ("PA66", "尼龙66"),
        ("PA12", "尼龙12"),
        ("TPU", "热塑性聚氨酯"),
        ("POM", "聚甲醛"),
        ("PPS", "聚苯硫醚"),
        ("PEEK", "聚醚醚酮"),
        ("LCP", "液晶聚合物"),
        ("TPE", "热塑性弹性体"),
        ("EVA", "乙烯醋酸乙烯共聚物"),
        ("HDPE", "高密度聚乙烯"),
        ("LLDPE", "线性低密度聚乙烯"),
        ("PVC", "聚氯乙烯"),
        ("PVB", "聚乙烯醇缩丁醛"),
        ("PSU", "聚砜"),
        ("Styrene", "苯乙烯"),
        ("Caprolactam", "己内酰胺"),
        ("Adipic Acid", "己二酸"),
        ("MDI", "二苯甲烷二异氰酸酯"),
        ("TDI", "甲苯二异氰酸酯"),
        ("ECH", "环氧氯丙烷"),
        ("DMC", "碳酸二甲酯"),
        ("EG", "乙二醇"),
        ("Phenol", "苯酚"),
        ("Acetone", "丙酮"),
        ("Acrylic Acid", "丙烯酸"),
        ("Butanol", "正丁醇"),
        ("EtOAc", "乙酸乙酯"),
    ],
    "阻燃剂 Flame Retardants": [
        ("Br-FR", "溴系阻燃剂"),
        ("TBBPA", "四溴双酚A"),
        ("RDP", "间苯二酚双磷酸酯"),
        ("BDP", "双酚A双磷酸酯"),
        ("TPP", "磷酸三苯酯"),
        ("ATO", "三氧化二锑"),
        ("MPP", "聚磷酸蜜胺"),
        ("Al-Phos", "二乙基次膦酸铝"),
        ("ATO-MB", "ATO母粒"),
        ("BrAcr", "溴化丙烯酸酯"),
        ("BrEpoxy", "溴化环氧树脂"),
        ("Bromine", "溴素"),
        ("BrPS", "溴化聚苯乙烯"),
        ("TBBPA-DGE", "TBBPA二缩水甘油醚"),
        ("TBBPA-MPE", "TBBPA甲基苯基醚"),
        ("BrCO", "溴化碳酸酯低聚物"),
        ("BPA-DP", "双酚A磷酸二苯酯"),
        ("IntP", "膨胀型磷系阻燃剂"),
        ("KSS", "全氟丁基磺酸钾"),
        ("NATS", "芳香族磺酸钠"),
        ("Phosphazene", "苯氧基磷腈"),
        ("Resorcinol", "间苯二酚"),
        ("Rimar", "全氟乙基磺酸钾"),
        ("SolDP", "Sol-DP磷酸酯"),
        ("SpecTalc", "特种滑石粉"),
        ("STB", "STB磺酸盐"),
        ("TAP", "磷酸三烯丙酯"),
        ("ATH", "氢氧化铝"),
        ("MDH", "氢氧化镁"),
        ("Zinc Borate", "硼酸锌"),
        ("Red Phosphorus", "红磷"),
        ("Melamine", "三聚氰胺"),
        ("DOPO", "DOPO磷阻燃剂"),
        ("Anti-drip", "防滴落剂"),
    ],
    "抗冲改性剂 Impact Modifiers": [
        ("SEBS", "氢化苯乙烯嵌段共聚物"),
        ("SBS", "苯乙烯丁二烯嵌段共聚物"),
        ("POE", "聚烯烃弹性体"),
        ("MBS", "甲基丙烯酸酯丁二烯苯乙烯"),
        ("PE-MA", "马来酸酐接枝PE"),
        ("Silicon-IM", "有机硅抗冲剂"),
        ("AIM", "丙烯酸酯抗冲改性剂"),
        ("TSAN", "PTFE包覆SAN"),
        ("SEP", "SEP嵌段共聚物"),
        ("PP-MA", "马来酸酐接枝PP"),
        ("Compatibilizer", "相容剂"),
    ],
    "氟塑料 Fluoropolymers": [
        ("ETFE", "ETFE氟塑料"),
        ("PTFE-D", "PTFE分散液"),
        ("PTFE-P", "PTFE粉"),
        ("PVDF", "聚偏氟乙烯"),
    ],
    "稳定剂 Stabilizers": [
        ("AO", "抗氧剂"),
        ("HALS", "受阻胺光稳定剂"),
        ("UV", "紫外线吸收剂"),
        ("Heat-Stab", "热稳定剂"),
        ("Nucleating Agent", "成核剂"),
        ("Plasticizer", "增塑剂"),
    ],
    "硬脂酸盐/润滑 Stearates": [
        ("Met-Stearate", "金属硬脂酸盐"),
        ("PETS", "季戊四醇硬脂酸酯"),
        ("Montan-Wax", "蒙旦蜡"),
        ("Anti-static", "抗静电剂"),
        ("GMS90", "甘油单硬脂酸酯"),
        ("Slip", "滑爽剂"),
        ("Preblends", "复合稳定剂预混料"),
        ("Mold Release", "脱模剂"),
        ("Silicone Oil", "硅油"),
    ],
    "色料/增强 Colorants & Reinforcements": [
        ("CB", "炭黑"),
        ("TiO2", "钛白粉"),
        ("GF", "玻璃纤维"),
        ("CF", "碳纤维"),
        ("Talc", "滑石粉"),
        ("Color-MB", "色母粒"),
        ("Org-Pig", "有机颜料"),
        ("Inorg-Pig", "无机颜料"),
        ("CNT", "碳纳米管"),
        ("ConductCB", "导电炭黑"),
        ("Dyes", "染料"),
        ("RCF", "再生碳纤维"),
        ("Siloxane", "有机硅烷"),
        ("WAX", "聚乙烯蜡"),
        ("ZnS", "硫化锌"),
        ("CBMB", "炭黑母粒"),
        ("CaCO3", "重质碳酸钙"),
        ("Mica", "云母粉"),
        ("BaSO4", "硫酸钡"),
        ("Wollastonite", "硅灰石"),
        ("Kaolin", "高岭土"),
        ("Silane", "硅烷偶联剂"),
    ],
    "包装 Packaging": [
        ("Pallet", "木托盘"),
        ("FIBC", "集装袋"),
        ("Bulk-Liner", "散装内衬袋"),
        ("Corrugated", "瓦楞纸箱"),
        ("FlexPack", "软包装"),
    ],
}



def get_search_plan(query: str) -> list[str]:
    """给定品类名（中文或英文简称），返回企查查搜索关键词列表。"""
    # 直接命中中文名
    if query in SABIC_SEARCH_STRATEGIES:
        return SABIC_SEARCH_STRATEGIES[query]["keywords"]
    # 英文简称 → 找对应中文
    for cn, cfg in SABIC_SEARCH_STRATEGIES.items():
        if cfg.get("en", "").lower() == query.lower():
            return cfg["keywords"]
    # 通用兜底
    generic = [f"{query}生产", f"{query}制造"]
    return generic


def get_qcc_filters(query: str) -> dict:
    """专项策略不再附带隐藏过滤，返回空（筛选完全由用户控制）。"""
    return {}


def get_all_sabic_keywords() -> list[str]:
    """返回所有品类的中文名（用于搜索建议）。"""
    return list(SABIC_SEARCH_STRATEGIES.keys())


def get_quick_categories() -> dict:
    """返回快捷按钮分组数据 {大类: [(英文, 中文), ...]}"""
    return QUICK_CATEGORIES


def get_category_priority(query: str) -> int | None:
    """给定品类名（中文或英文简称），返回 priority（1=P1核心，2=P2扩展），未命中返回 None。"""
    if query in SABIC_SEARCH_STRATEGIES:
        return SABIC_SEARCH_STRATEGIES[query].get("priority")
    for cn, cfg in SABIC_SEARCH_STRATEGIES.items():
        if cfg.get("en", "").lower() == query.lower():
            return cfg.get("priority")
    return None
