# -*- coding: utf-8 -*-
"""
综合服务名录构建器 —— 把 15 品类 × 4 基地 × 5 供应商的完整矩阵 + 评分标签
编译为 data/services.json（评分由 utils/services_scorer.py 运行时复算）。

这是 services.json 的『可维护源文件』：要增删供应商或调标签，改这里再
`python data/build_services.py` 重新生成即可，不要手改 services.json。

每个供应商标签：
  tier   national_top / regional / local      规模圈层
  nature foreign / soe / joint / private       企业性质
  sector petrochem / chemical / industrial / general  行业适配
  quals  [...]  资质/合规标签（数量驱动『资质合规』维度，并作展示 chip）
  local  [park_official/onsite/warehouse/local_branch/regional_hub] 属地履约旗标
  role   primary（首选，每基地恰 1 家）/ backup
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
OLD = json.loads((BASE / "services.json").read_text(encoding="utf-8"))
META = {c["key"]: c for c in OLD["categories"]}

DEFAULT_W = {"qual": 30, "sector": 22, "local": 20, "scale": 16, "service": 12}
WEIGHTS = {
    "manpower":      {"qual": 34, "sector": 18, "local": 18, "scale": 18, "service": 12},
    "event":         {"qual": 24, "sector": 16, "local": 22, "scale": 26, "service": 12},
    "advertising":   {"qual": 24, "sector": 16, "local": 22, "scale": 26, "service": 12},
    "office_leasing":{"qual": 24, "sector": 14, "local": 26, "scale": 24, "service": 12},
    "office_maint":  {"qual": 32, "sector": 16, "local": 24, "scale": 16, "service": 12},
    "it_hardware":   {"qual": 40, "sector": 16, "local": 16, "scale": 16, "service": 12},
    "consulting":    {"qual": 26, "sector": 26, "local": 10, "scale": 26, "service": 12},
    "shuttle":       {"qual": 30, "sector": 14, "local": 26, "scale": 18, "service": 12},
    "security":      {"qual": 34, "sector": 18, "local": 22, "scale": 14, "service": 12},
    "it_software":   {"qual": 34, "sector": 18, "local": 14, "scale": 20, "service": 14},
    "catering":      {"qual": 38, "sector": 16, "local": 18, "scale": 16, "service": 12},
    "insurance":     {"qual": 24, "sector": 14, "local": 16, "scale": 34, "service": 12},
    "mro_service":   {"qual": 26, "sector": 24, "local": 26, "scale": 12, "service": 12},
    "mro":           {"qual": 24, "sector": 22, "local": 28, "scale": 14, "service": 12},
    "lab":           {"qual": 34, "sector": 20, "local": 22, "scale": 12, "service": 12},
}

# 少量按新规范修正的品类元信息（消防维保归入办公运维 / 安保仅日常巡查）
META_OVERRIDE = {
    "office_maint": {
        "redline": "消防维保检测正式归入本品类：须绑定应急管理部「社会消防技术服务信息系统」"
                   "备案的消防机构，承担月度维保与年度消电检技术责任；高空/用电特种作业持证上岗。",
        "compliance": ["消防维保机构备案（应急管理部）", "特种作业持证（高空/用电）",
                       "EHS 现场管理", "年度消电检"],
        "tips": ["消防维保与法定检测由物业主体对接备案机构，权责与安保完全分离",
                 "设施维保纳入 EHS 作业许可，明确保洁/绿化/消防 SLA 标准"],
    },
    "security": {
        "redline": "须持《保安服务许可证》，满足化工厂区反恐防暴标准；仅负责门禁值守、"
                   "巡逻与日常消防点位巡查，不承担消防系统技术维保（已剥离至办公运维品类）。",
        "compliance": ["保安服务许可证", "反恐防暴标准", "日常消防巡查", "危化品车辆管控"],
        "tips": ["消防系统技术维保已剥离至办公运维，安保只做日常巡查，权责匹配",
                 "门禁与巡查须与 EHS 应急联动，核心物资安保由属地国企主供"],
    },
}


def S(name, typ, note, tier, nature, sector, quals, local, role="backup"):
    return {"name": name, "type": typ, "note": note, "tier": tier, "nature": nature,
            "sector": sector, "quals": quals, "local": local, "role": role}


# ════════════════════════════════════════════════════════════════════
# 15 品类 × 4 基地 × 5 供应商
# ════════════════════════════════════════════════════════════════════
ROSTERS = {
# ── 1. 人力外包 ──────────────────────────────────────────────────────
"manpower": {
"SH": [
 S("外企德科 FESCO Adecco 浦东分公司","国际派遣龙头","外资化工首选，RBA 劳工合规体系成熟","national_top","foreign","chemical",["RBA一级","外资合规","反贿赂"],["local_branch"],"primary"),
 S("中智上海浦东分公司","国企人力","人事代理+员工福利一体，审计经验丰富","national_top","soe","chemical",["RBA一级","社保合规","福利一体"],["local_branch"]),
 S("任仕达上海浦东分公司","全球人力","高端技术人才寻访+岗位外包","national_top","foreign","chemical",["RBA一级","高端寻访"],["local_branch"]),
 S("上海卧阳人力资源","园区派遣","张江注册，浦东化工园区一线批量用工","local","private","industrial",["RBA二级","园区深耕"],["local_branch","onsite"]),
 S("上海中蓝企业服务集团","劳务派遣","浦东人才港，派遣+社保公积金全代理","regional","private","industrial",["RBA二级","社保代理"],["local_branch"]),
],
"NS": [
 S("外企德科广州南沙分公司","国际派遣龙头","外资企业专属，RBA 合规体系完善","national_top","foreign","chemical",["RBA一级","外资专属"],["local_branch"],"primary"),
 S("广州南仕邦人力南沙分公司","属地龙头","长期服务化工外企，南沙头部","regional","private","chemical",["RBA二级","化工外企"],["local_branch","onsite"]),
 S("红海人力集团南沙分公司","本土龙头","派遣+灵活用工全覆盖","regional","private","industrial",["RBA二级","灵活用工"],["local_branch"]),
 S("广州仕邦人力南沙分部","自贸区服务","石化企业用工合规经验","regional","private","petrochem",["RBA二级","石化用工"],["local_branch","onsite"]),
 S("广州南方人才租赁南沙办事处","国企背景","大批量一线岗位外包","regional","soe","industrial",["RBA二级","批量外包"],["local_branch"]),
],
"GL": [
 S("外企德科厦门分公司古雷项目部","国际派遣龙头","漳厦联动，外资炼化 RBA 合规适配","national_top","foreign","petrochem",["RBA一级","炼化合规"],["onsite","regional_hub"],"primary"),
 S("漳州红海人力古雷办事处","炼化驻点","古雷驻点，一线劳务外包核心","local","private","petrochem",["RBA二级","炼化驻点"],["onsite","local_branch"]),
 S("厦门仕邦人力古雷项目部","外资经验","外资化工岗位外包，两地联动保供","regional","private","chemical",["RBA二级","外资化工"],["onsite","regional_hub"]),
 S("漳州漳浦劳务派遣有限公司","本地用工","属地注册，园区本地资源深厚","local","private","industrial",["RBA二级","本地用工"],["local_branch","onsite"]),
 S("福建海峡人力古雷服务站","省属平台","省属人力平台，适配大型项目用工","regional","soe","industrial",["RBA二级","省属平台"],["onsite"]),
],
"CQ": [
 S("外企德科重庆分公司","国际派遣龙头","外资化工人事外包首选，全球合规审计","national_top","foreign","chemical",["RBA一级","外资合规"],["local_branch"],"primary"),
 S("重庆中智人力资源","国企人力","员工福利+社保一体化","national_top","soe","chemical",["RBA一级","福利一体"],["local_branch"]),
 S("重庆新强人力资源","川渝龙头","派遣+岗位外包+人事代理","regional","private","industrial",["RBA二级","川渝龙头"],["local_branch"]),
 S("重庆外服人力资源","老牌服务","制造/化工用工经验丰富","regional","soe","chemical",["RBA二级","化工用工"],["local_branch"]),
 S("重庆汇博人才服务有限公司","区域头部","批量+灵活用工全覆盖","regional","private","industrial",["RBA二级","灵活用工"],["local_branch"]),
],
},
# ── 2. 会务活动 ──────────────────────────────────────────────────────
"event": {
"SH": [
 S("上海中旅国际会展浦东分公司","外资峰会","外宾接待经验丰富，适配国际化","national_top","soe","general",["合规招待","双语执行"],["local_branch"],"primary"),
 S("上海励展展览服务浦东分部","大型展会","客户开放日全案执行","national_top","foreign","industrial",["合规招待","全案执行"],["local_branch"]),
 S("上海博华国际展览浦东办事处","工业展会","石化行业专场活动经验","regional","joint","petrochem",["石化专场"],["local_branch"]),
 S("上海奥达会展服务有限公司","园区会务","张江工业园区技术交流会","local","private","industrial",["园区合规"],["onsite","local_branch"]),
 S("上海张江会务服务中心","属地平台","张江科学城会场+执行一体","local","private","industrial",["属地留痕"],["park_official","onsite"]),
],
"NS": [
 S("广州广交会展览南沙分部","大型展会","产品发布会全案执行","national_top","soe","industrial",["合规招待","全案执行"],["local_branch"],"primary"),
 S("广州南沙自贸区会展服务中心","官方平台","自贸区政策宣讲+企业峰会配套","local","soe","industrial",["自贸区合规","官方平台"],["park_official","onsite"]),
 S("广州毕加展览南沙分公司","搭建策划","展台搭建+活动策划一体","regional","private","industrial",["园区合规"],["local_branch"]),
 S("广州米修会务服务有限公司","本地落地","企业年会、客户答谢落地强","local","private","general",["本地执行"],["onsite","local_branch"]),
 S("广州叁鑫会务南沙项目部","属地执行","商务会议、技术交流响应快","local","private","general",["属地留痕"],["onsite"]),
],
"GL": [
 S("厦门会展集团漳州项目部","大型会议","漳厦联动，炼化行业会议全案","national_top","soe","petrochem",["合规招待","炼化会议"],["onsite","regional_hub"],"primary"),
 S("漳州古雷港会务服务中心","园区官方","石化峰会、项目对接专属服务","local","soe","petrochem",["港区合规","官方平台"],["park_official","onsite"]),
 S("厦门艾迪会展古雷分部","外资经验","外宾接待+双语执行","regional","joint","chemical",["双语执行"],["onsite","regional_hub"]),
 S("漳州龙文会务服务有限公司","本地执行","企业年会、厂区活动落地","local","private","general",["本地执行"],["onsite","local_branch"]),
 S("漳州盛典会务策划有限公司","属地团队","园区开放日、安全主题活动","local","private","industrial",["安全主题"],["onsite"]),
],
"CQ": [
 S("重庆国际博览中心会务分公司","官方执行","大型工业展会、行业峰会官方团队","national_top","soe","industrial",["合规招待","官方平台"],["local_branch"],"primary"),
 S("重庆艾斯会展服务有限公司","外资经验","双语执行+外宾接待","regional","joint","chemical",["双语执行"],["local_branch"]),
 S("重庆宏帆会务服务有限公司","园区活动","技术交流会全案服务","regional","private","industrial",["园区合规"],["onsite","local_branch"]),
 S("重庆西部会展服务中心","属地平台","西永/九龙坡产业园企业年会","local","private","industrial",["产业园合规"],["park_official","onsite"]),
 S("重庆嘉华会务策划有限公司","本地落地","厂区安全活动、品牌发布","local","private","general",["安全主题"],["onsite"]),
],
},
# ── 3. 广告宣传 ──────────────────────────────────────────────────────
"advertising": {
"SH": [
 S("奥美广告上海浦东分公司","品牌全案","企业形象宣传，适配外资全球标准","national_top","foreign","general",["广告法合规","品牌审核"],["local_branch"],"primary"),
 S("上海蓝标广告浦东分部","工业传播","工业品牌、展会物料、厂区文化","national_top","private","industrial",["广告法合规"],["local_branch"]),
 S("上海墨马广告有限公司","厂区标识","VI 系统、宣传物料制作","regional","private","industrial",["设计制作"],["onsite","local_branch"]),
 S("上海灵思广告张江分公司","科技工业","数字化宣传物料","regional","private","industrial",["数字物料"],["local_branch"]),
 S("上海浦东广告传播有限公司","属地国企","户外广告、厂区宣传栏制作安装","local","soe","general",["属地制作"],["onsite","local_branch"]),
],
"NS": [
 S("广东省广集团南沙分公司","品牌全案","石化企业形象宣传、展会物料","national_top","soe","petrochem",["广告法合规","品牌审核","石化经验"],["onsite","local_branch"],"primary"),
 S("广州盛世长城南沙项目部","外资服务","品牌视觉标准化","national_top","foreign","chemical",["广告法合规","品牌审核"],["onsite","local_branch"]),
 S("广州蓝色创意广告南沙分部","工业推广","厂区文化墙、宣传物料","regional","private","industrial",["设计制作"],["local_branch"]),
 S("广州南沙广告有限公司","属地国企","园区户外广告、厂区标识","local","soe","industrial",["属地制作"],["park_official","onsite"]),
 S("广州晶彩广告南沙分公司","快速落地","喷绘、标识、宣传栏","local","private","general",["快速响应"],["onsite"]),
],
"GL": [
 S("厦门广告集团漳州分公司","品牌宣传","漳厦联动，石化企业 VI 系统落地","national_top","private","petrochem",["广告法合规","石化经验"],["onsite","regional_hub"],"primary"),
 S("厦门华亿传媒古雷分部","工业经验","安全文化、品牌物料制作","regional","private","chemical",["安全文化"],["onsite","regional_hub"]),
 S("漳州古雷港广告传媒中心","园区官方","厂区标识、安全宣传物料","local","soe","petrochem",["港区合规","官方平台"],["park_official","onsite"]),
 S("漳州鸿图广告有限公司","本地制作","厂区宣传栏、户外广告安装","local","private","industrial",["属地制作"],["onsite","local_branch"]),
 S("漳州先锋广告策划有限公司","快速响应","喷绘、标识、活动物料","local","private","general",["快速响应"],["onsite"]),
],
"CQ": [
 S("重庆奥美广告分公司","外资品牌","全球化视觉标准适配","national_top","foreign","chemical",["广告法合规","品牌审核"],["local_branch"],"primary"),
 S("重庆高戈广告有限公司","西南头部","工业企业品牌推广、展会物料","national_top","private","industrial",["广告法合规"],["local_branch"]),
 S("重庆广告产业园传媒公司","工业全案","厂区视觉系统、宣传物料","regional","private","industrial",["设计制作"],["onsite","local_branch"]),
 S("重庆西部广告传媒有限公司","属地制作","西永产业园厂区标识、宣传栏","local","private","industrial",["产业园合规"],["park_official","onsite"]),
 S("重庆智派广告策划有限公司","快速响应","喷绘、灯箱、安全标识","local","private","general",["快速响应"],["onsite"]),
],
},
# ── 4. 办公场地租赁 ─────────────────────────────────────────────────
"office_leasing": {
"SH": [
 S("仲量联行（JLL）浦东商业地产部","国际代理","办公/研发楼选址+租赁谈判","national_top","foreign","general",["合同合规","消防验收","尽调透明"],["local_branch"],"primary"),
 S("戴德梁行浦东分部","国际代理","工业地产+写字楼一体化","national_top","foreign","industrial",["合同合规","消防验收"],["local_branch"]),
 S("第一太平戴维斯浦东分公司","高端写字楼","外资企业总部办公选址","national_top","foreign","general",["合同合规","产权核验"],["local_branch"]),
 S("上海张江高科租赁服务中心","园区官方","张江科学城研发办公楼","local","soe","industrial",["官方平台","产权核验"],["park_official","onsite"]),
 S("上海外高桥保税区租赁服务公司","保税办公","保税办公+仓储一体","local","soe","industrial",["保税合规"],["onsite","local_branch"]),
],
"NS": [
 S("仲量联行南沙商业地产部","国际代理","自贸区写字楼、产业园选址","national_top","foreign","general",["合同合规","消防验收","尽调透明"],["local_branch"],"primary"),
 S("戴德梁行广州南沙分部","国际代理","工业配套办公、总部楼租赁","national_top","foreign","industrial",["合同合规","消防验收"],["local_branch"]),
 S("南沙自贸区写字楼租赁服务中心","官方平台","自贸区政策适配办公场地","local","soe","industrial",["官方平台","自贸区合规"],["park_official","onsite"]),
 S("合富辉煌南沙商业租赁部","本土龙头","工业园区办公选址","regional","private","industrial",["产权核验"],["local_branch"]),
 S("广州南沙城投租赁服务部","区属国企","产业园办公楼、配套场地","local","soe","industrial",["官方平台"],["park_official","onsite"]),
],
"GL": [
 S("厦门链家商业地产古雷分部","区域代理","漳厦联动，写字楼、产业园选址","national_top","private","industrial",["合同合规","产权核验"],["onsite","regional_hub"],"primary"),
 S("古雷港经济开发区招商租赁中心","园区官方","园区配套办公楼、研发楼租赁","local","soe","petrochem",["官方平台","港区合规"],["park_official","onsite"]),
 S("漳州古雷城投办公租赁服务部","区属国企","炼化项目配套办公场地","local","soe","petrochem",["官方平台"],["park_official","onsite"]),
 S("福建中原地产古雷项目部","工业地产","配套办公+倒班宿舍一体租赁","regional","private","industrial",["产权核验"],["onsite","local_branch"]),
 S("漳州漳浦写字楼租赁服务中心","属地平台","县城+园区办公场地联动","local","private","general",["属地服务"],["onsite"]),
],
"CQ": [
 S("仲量联行重庆商业地产部","国际代理","写字楼、产业园办公选址","national_top","foreign","general",["合同合规","消防验收","尽调透明"],["local_branch"],"primary"),
 S("戴德梁行重庆分公司","国际代理","工业配套办公、总部楼租赁","national_top","foreign","industrial",["合同合规","消防验收"],["local_branch"]),
 S("重庆龙湖商业租赁事业部","本土龙头","高端写字楼、产业园办公","regional","private","industrial",["产权核验"],["local_branch"]),
 S("重庆两江新区写字楼租赁中心","官方平台","产业园、研发办公楼租赁","local","soe","industrial",["官方平台"],["park_official","onsite"]),
 S("重庆九龙坡产业园租赁服务部","属地平台","工业园区配套办公场地","local","soe","industrial",["产业园合规"],["park_official","onsite"]),
],
},
# ── 5. 办公运维保洁（含消防维保）────────────────────────────────────
"office_maint": {
"SH": [
 S("上海松林物业浦东分公司","化工物业","保洁+维保+绿化一体，绑定备案消防机构维保与年度消电检","national_top","private","petrochem",["消防维保备案","特种作业持证","EHS适配","年度消电检"],["onsite","local_branch"],"primary"),
 S("上海永升物业浦东项目部","上市物业","办公区保洁、设施巡检、报修响应","national_top","private","industrial",["特种作业持证","EHS适配","消防协作"],["onsite","local_branch"]),
 S("上海上房物业浦东分公司","国企物业","办公楼运维、保洁标准化，可对接消防检测","national_top","soe","industrial",["特种作业持证","消防协作"],["local_branch"]),
 S("上海浦江物业张江分部","园区运维","保洁、设施维修、绿植养护","regional","private","industrial",["EHS适配","消防协作"],["onsite","local_branch"]),
 S("上海蓝盾保洁服务有限公司","专项保洁","办公区日常清洁","local","private","general",["环卫资质"],["onsite"]),
],
"NS": [
 S("广州保利物业南沙项目部","上市物业","工业园区办公运维+绿化，绑定备案消防检测","national_top","private","industrial",["消防维保备案","特种作业持证","EHS适配","年度消电检"],["onsite","local_branch"],"primary"),
 S("广州越秀物业南沙分公司","国企物业","办公楼运维、保洁标准化+消防技术服务","national_top","soe","industrial",["消防维保备案","特种作业持证"],["onsite","local_branch"]),
 S("广州南沙物业运维服务中心","园区官方","办公区保洁+设施维保，绑定建筑消防检测中心","local","soe","petrochem",["消防维保备案","官方平台","年度消电检"],["park_official","onsite"]),
 S("广州城建物业南沙分部","本土物业","办公设施维保+保洁一体","regional","private","industrial",["EHS适配","消防协作"],["local_branch"]),
 S("广州洁特保洁服务有限公司","专项保洁","办公区日常清洁","local","private","general",["环卫资质"],["onsite"]),
],
"GL": [
 S("厦门联发物业古雷项目部","园区运维","漳厦联动，办公运维标准化，对接备案消防服务","national_top","private","petrochem",["消防维保备案","特种作业持证","EHS适配"],["onsite","regional_hub"],"primary"),
 S("古雷港园区物业运维中心","园区官方","保洁+维保+绿化，绑定本地备案消防机构维保检测","local","soe","petrochem",["消防维保备案","官方平台","年度消电检"],["park_official","onsite"]),
 S("福建恒安物业古雷分部","工业物业","办公区运维+安全巡检","regional","private","industrial",["特种作业持证","消防协作"],["onsite","local_branch"]),
 S("漳州漳浦物业保洁服务公司","属地团队","办公日常保洁、设施维修","local","private","general",["环卫资质"],["onsite","local_branch"]),
 S("漳州洁美保洁服务有限公司","专项保洁","办公区专项清洁","local","private","general",["环卫资质"],["onsite"]),
],
"CQ": [
 S("重庆龙湖物业九龙坡分公司","上市物业","办公保洁、维保标准化，绑定备案消防年度维保检测","national_top","private","industrial",["消防维保备案","特种作业持证","EHS适配","年度消电检"],["onsite","local_branch"],"primary"),
 S("重庆金科物业西永分部","本土龙头","产业园办公运维+绿化养护","national_top","private","industrial",["特种作业持证","消防协作"],["onsite","local_branch"]),
 S("重庆融创物业工业园分部","工业物业","办公运维+厂区配套保洁","regional","private","industrial",["EHS适配","消防协作"],["onsite","local_branch"]),
 S("重庆大正物业有限公司","老牌物业","办公区保洁、设施巡检维修","regional","private","general",["特种作业持证"],["local_branch"]),
 S("重庆洁万家保洁服务公司","专项保洁","办公日常保洁、专项清洁","local","private","general",["环卫资质"],["onsite"]),
],
},
# ── 6. IT 硬件与基建 ────────────────────────────────────────────────
"it_hardware": {
"SH": [
 S("上海华东电脑股份有限公司","机房集成","服务器/网络/机房基建一体，配套数据销毁","national_top","soe","chemical",["ISO27001","NAID销毁","等保合规","机房基建"],["onsite","local_branch"],"primary"),
 S("神州数码上海浦东分公司","全品类分销","机房部署+硬件维保，配套合规销毁","national_top","private","industrial",["ISO27001","NAID销毁","等保合规"],["onsite","local_branch"]),
 S("戴尔科技上海浦东服务中心","企业级原厂","服务器、存储，原厂维保","national_top","foreign","industrial",["ISO27001","原厂维保"],["local_branch"]),
 S("新华三上海浦东办事处","网络基建","网络设备、云计算基础设施","national_top","private","industrial",["ISO27001","网络基建"],["local_branch"]),
 S("上海网联信息科技有限公司","驻场运维","浦东本地 IT 硬件驻场、故障抢修","local","private","industrial",["驻场运维"],["onsite","local_branch"]),
],
"NS": [
 S("广州南天信息南沙分部","本土龙头","机房基建、网络设备部署，配套数据销毁","national_top","soe","chemical",["ISO27001","NAID销毁","等保合规","机房基建"],["onsite","local_branch"],"primary"),
 S("神州数码广州分公司","全品类分销","企业级设备供应+维保，配套资产处置","national_top","private","industrial",["ISO27001","NAID销毁","等保合规"],["onsite","local_branch"]),
 S("广州佳都科技南沙项目部","智能安防","安防+IT 基建一体，适配化工园区","regional","private","petrochem",["ISO27001","园区适配"],["onsite","local_branch"]),
 S("新华三广州南沙办事处","网络基建","网络、服务器、云计算解决方案","national_top","private","industrial",["ISO27001","网络基建"],["local_branch"]),
 S("广州华南资讯科技有限公司","机房部署","工业园区 IT 硬件部署、机房建设","local","private","industrial",["机房基建"],["onsite","local_branch"]),
],
"GL": [
 S("厦门纵横集团漳州项目部","基建运维","漳厦联动，机房基建+网络部署，配套合规销毁","national_top","private","petrochem",["ISO27001","NAID销毁","机房基建"],["onsite","regional_hub"],"primary"),
 S("神州数码厦门分公司","企业级供应","服务器、网络设备全覆盖","national_top","private","industrial",["ISO27001","等保合规"],["regional_hub","local_branch"]),
 S("厦门科华恒盛漳州分部","机房供电","UPS、机房供配电基础设施，工业级","national_top","private","petrochem",["机房基建","工业级"],["onsite","regional_hub"]),
 S("新华三漳州办事处","工业网络","工业级网络设备适配石化场景","national_top","private","petrochem",["ISO27001","网络基建"],["local_branch"]),
 S("漳州信华科技有限公司","驻场运维","本地 IT 硬件运维、上门抢修","local","private","industrial",["驻场运维"],["onsite","local_branch"]),
],
"CQ": [
 S("重庆神州数码分公司","全品类分销","企业级设备供应+维保，配套数据销毁","national_top","private","industrial",["ISO27001","NAID销毁","等保合规","机房基建"],["onsite","local_branch"],"primary"),
 S("重庆浪潮信息办事处","服务器存储","服务器、存储，工业级场景适配","national_top","soe","industrial",["ISO27001","原厂维保"],["local_branch"]),
 S("新华三重庆办事处","网络基建","网络设备、服务器、云计算基础设施","national_top","private","industrial",["ISO27001","网络基建"],["local_branch"]),
 S("重庆邮电大学科技产业公司","技术背景","机房基建、网络部署","regional","soe","industrial",["机房基建"],["onsite","local_branch"]),
 S("重庆西南信息产业有限公司","驻场运维","工业园区 IT 硬件部署、驻场运维","local","private","industrial",["驻场运维"],["onsite","local_branch"]),
],
},
# ── 7. 咨询服务 ──────────────────────────────────────────────────────
"consulting": {
"SH": [
 S("埃森哲上海浦东分公司","国际综合","供应链/数字化/EHS 合规全领域，外资首选","national_top","foreign","chemical",["FCPA","GDPR","EHS体系","进出口合规"],["local_branch"],"primary"),
 S("毕马威上海浦东分公司","国际四大","财务/进出口合规、反贿赂体系","national_top","foreign","chemical",["FCPA","进出口合规","反贿赂"],["local_branch"]),
 S("波士顿咨询上海浦东分部","战略咨询","战略、运营管理，全球化适配","national_top","foreign","chemical",["FCPA","战略咨询"],["local_branch"]),
 S("上海安元 EHS 咨询公司","石化专项","石化 EHS、安全合规、体系认证","regional","private","petrochem",["EHS体系","石化专项"],["local_branch"]),
 S("上海化工研究院咨询中心","技术专项","石化工艺、环保、技术咨询","regional","soe","petrochem",["技术专项","环保合规"],["local_branch"]),
],
"NS": [
 S("普华永道广州南沙分部","国际四大","税务合规、供应链咨询，外资适配","national_top","foreign","chemical",["FCPA","GDPR","进出口合规"],["local_branch"],"primary"),
 S("毕马威广州南沙服务部","国际四大","自贸区合规、财务、进出口咨询","national_top","foreign","chemical",["FCPA","进出口合规","反贿赂"],["local_branch","onsite"]),
 S("广州德勤咨询南沙项目部","国际四大","管理咨询、数字化转型、合规体系","national_top","foreign","chemical",["FCPA","数字化"],["onsite","local_branch"]),
 S("广州安环科技咨询有限公司","石化专项","石化 EHS、安全评价、环保合规","regional","private","petrochem",["EHS体系","安全评价"],["local_branch"]),
 S("广东省石化研究院咨询中心","技术专项","石化工艺、技术、环保咨询","regional","soe","petrochem",["技术专项","环保合规"],["local_branch"]),
],
"GL": [
 S("毕马威厦门分公司漳州服务部","国际四大","财务/税务/进出口合规","national_top","foreign","chemical",["FCPA","进出口合规","反贿赂"],["onsite","regional_hub"],"primary"),
 S("厦门安环科技古雷项目部","石化专项","石化 EHS、安全评价、环保专项","regional","private","petrochem",["EHS体系","安全评价","石化专项"],["onsite","regional_hub"]),
 S("福建省石化规划设计院咨询部","炼化技术","炼化项目工艺、规划、技术咨询","regional","soe","petrochem",["技术专项","炼化规划"],["local_branch"]),
 S("漳州 EHS 安全咨询中心","属地服务","安全生产、应急管理咨询","local","private","petrochem",["EHS体系","应急管理"],["onsite","local_branch"]),
 S("厦门合众咨询古雷分部","管理咨询","人力、管理体系、园区运营","regional","private","industrial",["管理体系"],["onsite","regional_hub"]),
],
"CQ": [
 S("德勤重庆分公司","国际四大","管理咨询、财务合规、数字化转型","national_top","foreign","chemical",["FCPA","GDPR","数字化"],["local_branch"],"primary"),
 S("毕马威重庆分公司","国际四大","税务合规、供应链、内控体系","national_top","foreign","chemical",["FCPA","进出口合规","反贿赂"],["local_branch"]),
 S("重庆赛西 EHS 安全咨询","EHS专项","西南石化 EHS、合规、体系认证","regional","private","petrochem",["EHS体系","体系认证","石化专项"],["local_branch"]),
 S("重庆安评安全技术咨询","安全评价","安全评价、应急预案、标准化","regional","private","petrochem",["安全评价","应急管理"],["local_branch"]),
 S("四川省化工设计院重庆咨询部","技术专项","石化工艺、环保、工程技术","regional","soe","petrochem",["技术专项","环保合规"],["local_branch"]),
],
},
# ── 8. 通勤班车/车辆租赁 ────────────────────────────────────────────
"shuttle": {
"SH": [
 S("上海强生交通集团浦东分公司","国企客运","通勤大巴、商务车，线路成熟","national_top","soe","industrial",["营运资质","从业资格","车辆安检","承运保险"],["onsite","local_branch"],"primary"),
 S("上海久事公交客运浦东项目部","公交背景","大型厂区通勤班车运营","national_top","soe","industrial",["营运资质","从业资格","车辆安检"],["onsite","local_branch"]),
 S("上海大众交通浦东分公司","本土龙头","通勤班车、临时用车全覆盖","national_top","soe","general",["营运资质","车辆安检"],["local_branch"]),
 S("上海锦江汽车租赁浦东分部","商务车队","大巴/商务车，外资服务经验","regional","soe","general",["营运资质","承运保险"],["local_branch"]),
 S("上海浦东巴士旅游客运","属地车队","化工园区通勤班车定制线路","local","private","industrial",["营运资质","线路定制"],["onsite","local_branch"]),
],
"NS": [
 S("广州交通集团南沙客运部","本土龙头","大巴、商务车全品类租赁","national_top","soe","industrial",["营运资质","从业资格","车辆安检","承运保险"],["onsite","local_branch"],"primary"),
 S("广州二汽南沙分公司","公交背景","通勤大巴、员工班车运营","national_top","soe","industrial",["营运资质","从业资格","车辆安检"],["onsite","local_branch"]),
 S("广州粤运客运南沙项目部","省属客运","跨区域通勤、商务用车","national_top","soe","general",["营运资质","承运保险"],["local_branch"]),
 S("广州南沙交通发展有限公司","区属国企","园区通勤班车、定制线路","local","soe","industrial",["营运资质","线路定制"],["park_official","onsite"]),
 S("广州广骏汽车租赁南沙分部","本地车队","通勤班车、临时用车响应快","local","private","general",["营运资质"],["onsite","local_branch"]),
],
"GL": [
 S("漳州长运集团古雷分公司","市属客运","通勤大巴、定制化线路","national_top","soe","industrial",["营运资质","从业资格","车辆安检","承运保险"],["onsite","local_branch"],"primary"),
 S("漳州闽运客运古雷分部","省属客运","厂区通勤、员工接送","national_top","soe","industrial",["营运资质","从业资格","车辆安检"],["onsite","local_branch"]),
 S("厦门鹭运集团漳州项目部","区域客运","漳厦联动，商务车、通勤班车","regional","soe","general",["营运资质","承运保险"],["onsite","regional_hub"]),
 S("漳浦县汽车运输公司","属地国企","漳浦县城-古雷厂区通勤班车","local","soe","industrial",["营运资质","线路定制"],["onsite","local_branch"]),
 S("漳州捷顺汽车租赁有限公司","本地服务","商务车、临时用车灵活租赁","local","private","general",["营运资质"],["onsite"]),
],
"CQ": [
 S("重庆交运集团通勤客运分公司","市属国企","大型厂区通勤班车运营，适配山地","national_top","soe","industrial",["营运资质","从业资格","车辆安检","承运保险"],["onsite","local_branch"],"primary"),
 S("重庆公交集团租赁分公司","公交背景","工业园区通勤定制线路","national_top","soe","industrial",["营运资质","从业资格","车辆安检"],["onsite","local_branch"]),
 S("重庆长途汽车运输集团","本土龙头","通勤大巴、跨区域班车","national_top","soe","general",["营运资质","承运保险"],["local_branch"]),
 S("重庆愉客行汽车租赁","本地平台","商务车、班车灵活租赁","regional","soe","general",["营运资质"],["local_branch"]),
 S("重庆国泰汽车租赁有限公司","本土服务","通勤班车、临时用车","local","private","general",["营运资质"],["onsite"]),
],
},
# ── 9. 安保服务（仅日常巡查）────────────────────────────────────────
"security": {
"SH": [
 S("浦东新区保安服务总公司","国企持证","化工园区安保、门禁、反恐，负责日常消防巡查","national_top","soe","petrochem",["保安许可","反恐防暴","日常消防巡查","危化品车管控"],["onsite","local_branch"],"primary"),
 S("上海中保华安保安浦东分公司","外资经验","外资企业安保经验，标准化管理","national_top","soe","chemical",["保安许可","反恐防暴","标准化"],["local_branch"]),
 S("上海赛夫保安服务有限公司","工业安保","门禁、巡逻、消防值守","regional","private","industrial",["保安许可","日常消防巡查"],["onsite","local_branch"]),
 S("上海圣泰保安服务有限公司","属地持证","厂区安防+临时勤务","local","private","industrial",["保安许可"],["onsite","local_branch"]),
 S("上海宗保保安服务有限公司","属地安保","园区安保、秩序维护","local","private","general",["保安许可"],["onsite"]),
],
"NS": [
 S("南沙保安服务有限公司","国企持证","化工园区封闭式安保、消防值守，日常巡查","national_top","soe","petrochem",["保安许可","反恐防暴","日常消防巡查","危化品车管控"],["park_official","onsite"],"primary"),
 S("广州越秀保安南沙分公司","市属国企","厂区安防、门禁、反恐标准","national_top","soe","industrial",["保安许可","反恐防暴"],["onsite","local_branch"]),
 S("广东金盾保安服务南沙公司","本土安保","厂区巡逻、危化品车辆管控","regional","private","petrochem",["保安许可","危化品车管控"],["onsite","local_branch"]),
 S("广州中保国安南沙分部","工业安保","标准化管理、持证上岗","regional","private","industrial",["保安许可","标准化"],["local_branch"]),
 S("广州粤盾保安服务有限公司","属地安保","园区安保、秩序维护","local","private","general",["保安许可"],["onsite"]),
],
"GL": [
 S("古雷港安保服务有限公司","园区官方","炼化厂区持证安保、门禁值守，适配反恐标准","local","soe","petrochem",["保安许可","反恐防暴","日常消防巡查","危化品车管控"],["park_official","onsite"],"primary"),
 S("漳州保安服务总公司古雷分公司","市属国企","大型炼化项目安保经验","national_top","soe","petrochem",["保安许可","反恐防暴"],["onsite","local_branch"]),
 S("厦门银盾安保古雷项目部","外资标准","漳厦联动，外资化工安保标准化","regional","private","chemical",["保安许可","标准化"],["onsite","regional_hub"]),
 S("漳浦县保安服务公司","属地国企","厂区安保、巡逻、消防值守","local","soe","industrial",["保安许可","日常消防巡查"],["onsite","local_branch"]),
 S("福建中安保安古雷分部","本地服务","园区安保、危化品车辆管控","local","private","petrochem",["保安许可","危化品车管控"],["onsite"]),
],
"CQ": [
 S("重庆保安集团九龙坡分公司","市属国企","厂区安保、反恐防暴、门禁","national_top","soe","industrial",["保安许可","反恐防暴","日常消防巡查"],["onsite","local_branch"],"primary"),
 S("重庆中保华安保安分公司","外资经验","外资企业安保经验，标准化管理","national_top","soe","chemical",["保安许可","反恐防暴","标准化"],["local_branch"]),
 S("重庆渝盾保安服务有限公司","本土龙头","工业园区安保、消防值守","regional","private","industrial",["保安许可","日常消防巡查"],["onsite","local_branch"]),
 S("重庆赛夫保安服务有限公司","工业安保","门禁、巡逻一体","regional","private","industrial",["保安许可"],["onsite","local_branch"]),
 S("重庆金盾保安服务公司","本地服务","厂区巡逻、秩序维护","local","private","general",["保安许可"],["onsite"]),
],
},
# ── 10. IT 软件服务 ─────────────────────────────────────────────────
"it_software": {
"SH": [
 S("SAP 中国上海浦东分公司","ERP 原厂","ERP 系统实施/运维，外资核心管理软件","national_top","foreign","chemical",["ISO27001","数据安全法","ERP原厂"],["local_branch"],"primary"),
 S("用友网络上海浦东分公司","国产 ERP","财务、供应链管理软件，本土化强","national_top","private","industrial",["ISO27001","等保合规","ERP落地"],["onsite","local_branch"]),
 S("金蝶软件上海浦东服务中心","云 ERP","企业管理软件、云 ERP，化工方案","national_top","private","chemical",["ISO27001","等保合规"],["onsite","local_branch"]),
 S("上海泛微网络科技","协同 OA","流程审批、数字化办公","national_top","private","industrial",["ISO27001","流程数字化"],["local_branch"]),
 S("上海启明软件股份有限公司","定制开发","定制软件、企业信息化系统","regional","private","industrial",["定制开发","驻场运维"],["onsite","local_branch"]),
],
"NS": [
 S("金蝶软件广州南沙分公司","云 ERP","云 ERP、供应链管理，工业适配","national_top","private","chemical",["ISO27001","等保合规","ERP落地"],["onsite","local_branch"],"primary"),
 S("用友网络广州分部","国产 ERP","财务、生产管理软件，本土实施","national_top","private","industrial",["ISO27001","等保合规"],["onsite","local_branch"]),
 S("广州远光软件有限公司","能源化工","能源化工行业管理软件、财务系统","national_top","soe","petrochem",["ISO27001","行业方案"],["onsite","local_branch"]),
 S("广州赛意信息科技南沙分部","数字化","ERP 实施、数字化转型，制造业","regional","private","industrial",["ISO27001","数字化"],["onsite","local_branch"]),
 S("广州广电运通软件南沙项目部","信息化","信息化系统、智能办公","regional","soe","industrial",["信息化","驻场运维"],["onsite","local_branch"]),
],
"GL": [
 S("厦门鼎捷软件古雷项目部","制造 ERP","制造业 ERP，石化生产管理适配","national_top","private","petrochem",["ISO27001","行业方案","ERP落地"],["onsite","regional_hub"],"primary"),
 S("金蝶软件厦门分公司漳州分部","云 ERP","云 ERP、供应链管理，工业方案","national_top","private","chemical",["ISO27001","等保合规"],["onsite","regional_hub"]),
 S("厦门用友软件漳州服务部","国产 ERP","ERP、财务软件，漳厦实施运维","national_top","private","industrial",["ISO27001","等保合规"],["onsite","regional_hub"]),
 S("福建星网锐捷软件漳州分部","工业软件","工业软件、智能办公系统","regional","private","industrial",["信息化"],["onsite","local_branch"]),
 S("漳州正航软件有限公司","本土服务","生产管理、进销存系统","local","private","industrial",["定制开发","驻场运维"],["onsite","local_branch"]),
],
"CQ": [
 S("金蝶软件重庆分公司","云 ERP","云 ERP、企业管理软件，西南服务","national_top","private","chemical",["ISO27001","等保合规","ERP落地"],["onsite","local_branch"],"primary"),
 S("用友网络重庆分公司","国产 ERP","财务、供应链、生产管理全系列","national_top","private","industrial",["ISO27001","等保合规"],["onsite","local_branch"]),
 S("重庆金算盘软件有限公司","本土龙头","财务、ERP、化工行业方案","regional","private","chemical",["ISO27001","行业方案"],["onsite","local_branch"]),
 S("重庆中联信息产业","协同办公","信息化、协同办公系统定制","regional","private","industrial",["信息化","定制开发"],["onsite","local_branch"]),
 S("重庆南华中天软件","工业软件","工业软件、数字化办公实施运维","local","private","industrial",["驻场运维"],["onsite","local_branch"]),
],
},
# ── 11. 团餐食堂服务 ────────────────────────────────────────────────
"catering": {
"SH": [
 S("中快餐饮上海浦东分公司","全国龙头","工业园区食堂标准化运营，食安体系完善","national_top","private","industrial",["食品经营许可","第三方抽检","留样溯源","健康证"],["onsite","local_branch"],"primary"),
 S("上海麦金地餐饮张江分部","高端团餐","外资企业食堂、员工餐定制","national_top","private","chemical",["食品经营许可","留样溯源","健康证"],["onsite","local_branch"]),
 S("上海新尚餐饮管理有限公司","园区托管","浦东化工园区封闭式食堂托管","regional","private","petrochem",["食品经营许可","留样溯源","健康证"],["onsite","local_branch"]),
 S("上海一片天餐饮管理","本土团餐","工业园区食堂托管、食材溯源","regional","private","industrial",["食品经营许可","留样溯源"],["onsite","local_branch"]),
 S("上海绿捷快餐有限公司","本地团餐","员工餐、商务接待餐一体","local","private","general",["食品经营许可","健康证"],["onsite"]),
],
"NS": [
 S("中快餐饮广东南沙分公司","全国龙头","标准化食堂运营，配套 SGS/华测食安抽检","national_top","private","industrial",["食品经营许可","第三方抽检","留样溯源","健康证"],["onsite","local_branch"],"primary"),
 S("广州鸿骏膳食南沙分部","珠三角龙头","工业园区食堂托管","national_top","private","industrial",["食品经营许可","留样溯源","健康证"],["onsite","local_branch"]),
 S("广州千喜鹤餐饮南沙项目部","全国品牌","员工餐、接待餐服务","national_top","private","industrial",["食品经营许可","第三方抽检","健康证"],["onsite","local_branch"]),
 S("南沙绿源餐饮管理有限公司","属地托管","工业园食堂托管，化工园区经验","regional","private","petrochem",["食品经营许可","留样溯源"],["onsite","local_branch"]),
 S("广州和兴隆餐饮管理","本土团餐","食材溯源、食堂标准化运营","local","private","general",["食品经营许可","健康证"],["onsite"]),
],
"GL": [
 S("中快餐饮福建古雷项目部","全国龙头","大型厂区食堂标准化运营，第三方食安抽检","national_top","private","petrochem",["食品经营许可","第三方抽检","留样溯源","健康证"],["onsite","regional_hub"],"primary"),
 S("漳州福海创配套团餐服务商","炼化配套","炼化项目厂区食堂运营经验丰富","local","private","petrochem",["食品经营许可","留样溯源","健康证"],["park_official","onsite"]),
 S("厦门味友餐饮古雷分部","区域团餐","漳厦联动，团餐托管、接待餐","national_top","private","industrial",["食品经营许可","留样溯源"],["onsite","regional_hub"]),
 S("古雷港园区食堂运营中心","园区官方","炼化项目职工食堂托管","local","soe","petrochem",["食品经营许可","官方平台","健康证"],["park_official","onsite"]),
 S("漳州盛辉餐饮管理有限公司","本地服务","职工食堂、食材配送","local","private","general",["食品经营许可","健康证"],["onsite"]),
],
"CQ": [
 S("中快餐饮重庆工业园项目部","全国龙头","工业园区食堂标准化运营，第三方食安抽检","national_top","private","industrial",["食品经营许可","第三方抽检","留样溯源","健康证"],["onsite","local_branch"],"primary"),
 S("重庆德庄团餐管理有限公司","本土龙头","职工食堂、团餐配送","national_top","private","industrial",["食品经营许可","留样溯源","健康证"],["onsite","local_branch"]),
 S("重庆美心餐饮管理","本地团餐","工业园区食堂托管、食安管控","regional","private","industrial",["食品经营许可","留样溯源"],["onsite","local_branch"]),
 S("重庆愉筷餐饮团餐分部","本土服务","员工餐、食堂承包","local","private","general",["食品经营许可","健康证"],["onsite"]),
 S("重庆奇爽团餐服务有限公司","本地团餐","厂区食堂、食材一体","local","private","general",["食品经营许可","健康证"],["onsite"]),
],
},
# ── 12. 员工保险福利 ────────────────────────────────────────────────
"insurance": {
"SH": [
 S("中国人保财险浦东支公司","头部险企","补充医疗、团体意外、厂区财产险","national_top","soe","industrial",["保险资质","团险合规","财产险"],["local_branch"],"primary"),
 S("中国平安养老险上海浦东分公司","头部险企","企业年金、团体寿险、员工福利","national_top","joint","industrial",["保险资质","团险合规","年金"],["local_branch"]),
 S("太平洋人寿浦东分部","头部险企","团体健康险、意外险定制","national_top","soe","general",["保险资质","团险合规"],["local_branch"]),
 S("友邦保险上海浦东团险部","外资团险","外资企业全球医疗福利适配","national_top","foreign","general",["保险资质","团险合规","全球福利"],["local_branch"]),
 S("中智上海员工福利中心","福利一体","团体险、补充医疗、福利一体方案","regional","soe","general",["团险合规","福利一体"],["local_branch"]),
],
"NS": [
 S("中国平安财险南沙营业部","头部险企","团体意外、补充医疗、企业财产险","national_top","joint","industrial",["保险资质","团险合规","财产险"],["onsite","local_branch"],"primary"),
 S("中国人保财险南沙支公司","头部险企","团险、财产险一体化","national_top","soe","industrial",["保险资质","团险合规","财产险"],["local_branch"]),
 S("太平洋人寿南沙分公司","头部险企","团体健康险、福利计划定制","national_top","soe","general",["保险资质","团险合规"],["local_branch"]),
 S("泰康养老险南沙项目部","头部险企","企业年金、团体寿险、健康福利","national_top","private","general",["保险资质","年金"],["onsite","local_branch"]),
 S("广州中智员工福利分部","福利一体","团险+补充医疗一体","regional","soe","general",["团险合规","福利一体"],["local_branch"]),
],
"GL": [
 S("中国人保财险漳浦支公司","头部险企","属地国企，团险、厂区财产险一体","national_top","soe","industrial",["保险资质","团险合规","财产险"],["onsite","local_branch"],"primary"),
 S("中国平安财险漳州古雷营业部","头部险企","团体意外、补充医疗，响应快","national_top","joint","industrial",["保险资质","团险合规"],["onsite","local_branch"]),
 S("太平洋人寿漳州分公司","头部险企","团体健康险、福利定制","national_top","soe","general",["保险资质","团险合规"],["local_branch"]),
 S("泰康养老漳州分部","头部险企","企业年金、团体寿险、健康管理","national_top","private","general",["保险资质","年金"],["local_branch"]),
 S("厦门中智员工福利漳州服务部","福利一体","漳厦联动，外资企业福利方案","regional","soe","chemical",["团险合规","福利一体"],["onsite","regional_hub"]),
],
"CQ": [
 S("太平洋财险重庆分公司","头部险企","团险、财产险、安全生产责任险","national_top","soe","industrial",["保险资质","团险合规","财产险","安责险"],["local_branch"],"primary"),
 S("中国人保财险重庆九龙坡支公司","头部险企","团体意外、补充医疗","national_top","soe","industrial",["保险资质","团险合规","财产险"],["onsite","local_branch"]),
 S("中国平安养老险重庆分公司","头部险企","企业年金、团体寿险、福利计划","national_top","joint","general",["保险资质","年金"],["local_branch"]),
 S("泰康养老重庆分公司","头部险企","团体健康险、福利定制","national_top","private","general",["保险资质","团险合规"],["local_branch"]),
 S("重庆中智员工福利中心","福利一体","团险+健康管理一体","regional","soe","general",["团险合规","福利一体"],["local_branch"]),
],
},
# ── 13. MRO 运维服务（驻场维保）─────────────────────────────────────
"mro_service": {
"SH": [
 S("上海宝信设备运维公司","石化驻场","设备驻场维保、电气仪表检修，石化经验","national_top","soe","petrochem",["持证作业","SAP对接","驻场维保"],["onsite","local_branch"],"primary"),
 S("上海石化设备检修公司浦东分部","石化检修","石化专用设备维保、计划检修抢修","national_top","soe","petrochem",["持证作业","石化专用"],["onsite","local_branch"]),
 S("上海电气运维服务浦东分公司","动静设备","动/静设备维保，持证作业团队","national_top","soe","industrial",["持证作业","驻场维保"],["onsite","local_branch"]),
 S("震坤行工业设备运维中心","MRO一体","通用设备维保+抢修，属地快速响应","national_top","private","industrial",["MRO一体","快速响应"],["onsite","warehouse"]),
 S("西域智慧供应链运维服务部","物料运维","MRO 物料+运维一体，驻场检修","national_top","private","industrial",["MRO一体","驻场维保"],["onsite","warehouse"]),
],
"NS": [
 S("广州广石化设备检修公司南沙分部","石化检修","石化设备维保、计划检修，本土技术","national_top","soe","petrochem",["持证作业","石化专用","驻场维保"],["onsite","local_branch"],"primary"),
 S("广州华南重工运维服务公司","重型维保","重型设备、机泵维保，石化适配","regional","private","petrochem",["持证作业","石化专用"],["onsite","local_branch"]),
 S("广州工控设备运维南沙项目部","工业集团","市属工业集团，设备维保、故障抢修","national_top","soe","industrial",["持证作业","驻场维保"],["onsite","local_branch"]),
 S("震坤行广州设备运维部","MRO一体","驻场服务、快速抢修","national_top","private","industrial",["MRO一体","快速响应"],["onsite","warehouse"]),
 S("广州机电设备运维有限公司","通用维保","通用工业设备维保、电气仪表","regional","private","industrial",["持证作业"],["onsite","local_branch"]),
],
"GL": [
 S("古雷石化设备运维中心","园区配套","炼化设备驻场维保、计划检修","local","soe","petrochem",["持证作业","石化专用","驻场维保"],["park_official","onsite"],"primary"),
 S("漳州福海创设备检修公司","炼化配套","机泵、塔器、管道维保","local","private","petrochem",["持证作业","石化专用"],["onsite","local_branch"]),
 S("中密控股运维服务古雷分部","密封专项","机械密封、泵阀专项维保，石化专用","national_top","private","petrochem",["持证作业","机械密封"],["onsite","regional_hub"]),
 S("福建石化设备检修公司古雷站","省属技术","炼化设备大修、抢修","regional","soe","petrochem",["持证作业","石化专用"],["onsite","local_branch"]),
 S("厦门机电设备运维古雷项目部","通用维保","漳厦联动，电气仪表、通用设备维保","regional","private","industrial",["持证作业","驻场维保"],["onsite","regional_hub"]),
],
"CQ": [
 S("重庆川维设备检修公司","石化配套","化工设备维保、计划检修","national_top","soe","petrochem",["持证作业","石化专用","驻场维保"],["onsite","local_branch"],"primary"),
 S("重庆化工设备检修中心","化工大修","西南化工设备维保、大修专项","regional","soe","petrochem",["持证作业","石化专用"],["onsite","local_branch"]),
 S("震坤行重庆设备运维部","MRO一体","驻场服务、故障抢修","national_top","private","industrial",["MRO一体","快速响应"],["onsite","warehouse"]),
 S("重庆机电设备运维有限公司","通用维保","通用工业设备维保抢修，本土团队","regional","private","industrial",["持证作业"],["onsite","local_branch"]),
 S("重庆重钢设备运维分公司","重型维保","重型设备、机泵维保","regional","soe","industrial",["持证作业","驻场维保"],["onsite","local_branch"]),
],
},
# ── 14. MRO 物料供应 ────────────────────────────────────────────────
"mro": {
"SH": [
 S("京东工业上海浦东仓","数字化平台","全品类 MRO，SAP 对接，2 小时应急配送","national_top","private","industrial",["SAP直连","区块链溯源","双轨集采","危废双供"],["warehouse","onsite"],"primary"),
 S("震坤行工业超市浦东店","智能仓储","石化 MRO 全品类，智能柜 24h 领料","national_top","private","petrochem",["智能仓","双轨集采"],["warehouse","onsite"]),
 S("西域智慧供应链浦东备货中心","华东大仓","全品类工业品，外资服务经验，区域兜底","national_top","private","industrial",["华东大仓","区域兜底"],["warehouse","regional_hub"]),
 S("上海超润供应链","特种化工","润滑、密封耗材专项，本地仓配","regional","private","chemical",["特种耗材"],["warehouse","local_branch"]),
 S("上海工品汇浦东分公司","通用 MRO","通用耗材，性价比高，属地配送","local","private","industrial",["通用耗材"],["warehouse","local_branch"]),
],
"NS": [
 S("京东工业华南广州仓","数字化平台","盐雾防腐备件专项备货，1 小时直达南沙，危废双供","national_top","private","petrochem",["C5-M防腐","SAP直连","双轨集采","危废双供"],["warehouse","onsite"],"primary"),
 S("广州广镒机电南沙仓","本地现货","石化阀门、泵件、电工仪表，C5-M 防腐","local","private","petrochem",["C5-M防腐","本地现货"],["warehouse","onsite"]),
 S("震坤行南沙服务中心","智能仓储","珠三角化工客户覆盖，防腐备件达标","national_top","private","petrochem",["智能仓","C5-M防腐"],["warehouse","local_branch"]),
 S("广州颐达工业设备","当日配送","五金、密封、劳保 MRO 当日配送","regional","private","industrial",["当日配送","盐雾检测"],["warehouse","onsite"]),
 S("西域华南佛山仓","区域大仓","全品类工业品，1 小时直达南沙兜底","national_top","private","industrial",["区域兜底"],["warehouse","regional_hub"]),
],
"GL": [
 S("漳州腾雷工贸古雷仓","本地兜底","石化 MRO 全品类，5km 防台应急实体库，危废双供","local","private","petrochem",["防台应急库","危废双供","本地现货"],["warehouse","onsite"],"primary"),
 S("中密控股古雷项目部","密封专用","机械密封、泵阀专用备件，炼化核心配套","national_top","private","petrochem",["机械密封","炼化配套"],["onsite","regional_hub"]),
 S("京东工业厦门仓","数字化平台","全国调拨兜底，非极端天气 1.5h 直达","national_top","private","industrial",["SAP直连","全国调拨"],["regional_hub","warehouse"]),
 S("震坤行厦门服务中心","智能仓储","非台风季区域应急补货","national_top","private","industrial",["智能仓","区域兜底"],["warehouse","regional_hub"]),
 S("西域厦门仓","区域大仓","漳厦联动，常规物料当日达","national_top","private","industrial",["区域兜底","当日配送"],["warehouse","regional_hub"]),
],
"CQ": [
 S("京东工业西南重庆仓","数字化平台","山城物流适配，配送车标配防滑，危废双供","national_top","private","industrial",["山地物流","SAP直连","双轨集采","危废双供"],["warehouse","onsite"],"primary"),
 S("华之杰（重庆）工业技术","本地大仓","5000㎡自有仓，石化全品类现货，山区绕行预案","regional","private","petrochem",["本地现货","山地物流"],["warehouse","onsite"]),
 S("震坤行重庆仓","智能仓储","西南全品类 MRO，智能仓+自动对账","national_top","private","industrial",["智能仓","山地物流"],["warehouse","local_branch"]),
 S("重庆科沃德机电","本地现货","五金、仪表、劳保维修物料现货","local","private","industrial",["本地现货","山地物流"],["warehouse","onsite"]),
 S("西域西南总仓","区域大仓","全品类工业品，西南区域兜底","national_top","private","industrial",["区域兜底"],["warehouse","regional_hub"]),
],
},
# ── 15. 实验室物料与设备 ────────────────────────────────────────────
"lab": {
"SH": [
 S("上海沪试实验室器材","属地主供","华东主流供应商，浦东就近发货，危货车配送","national_top","private","chemical",["危化运输许可","易制毒管控","就近发货"],["warehouse","local_branch"],"primary"),
 S("国药集团化学试剂上海分公司","国企龙头","试剂/耗材/仪器全覆盖，溯源合规","national_top","soe","chemical",["危化运输许可","溯源合规","全品类"],["warehouse","local_branch"]),
 S("泰坦科技浦东分公司","研发适配","实验室耗材+仪器一体，合规配送","national_top","private","chemical",["危化运输许可","合规配送"],["warehouse","local_branch"]),
 S("赛默飞世尔上海浦东服务中心","进口仪器","分析仪器，原厂维保+耗材","national_top","foreign","chemical",["原厂维保","进口仪器"],["local_branch"]),
 S("安捷伦科技上海浦东办事处","色谱质谱","石化化验室适配","national_top","foreign","petrochem",["原厂维保","石化适配"],["local_branch"]),
],
"NS": [
 S("国药集团化学试剂广州分公司","国企龙头","试剂耗材合规溯源，品类齐全，配送资质完备","national_top","soe","chemical",["危化运输许可","溯源合规","全品类"],["warehouse","local_branch"],"primary"),
 S("广州科仪仪器有限公司","属地主供","本地配送，化验室试剂、玻璃仪器全覆盖","local","private","chemical",["危化运输许可","就近配送"],["warehouse","onsite"]),
 S("赛默飞世尔广州南沙服务部","进口仪器","分析仪器+耗材，石化化验室方案","national_top","foreign","petrochem",["原厂维保","石化适配"],["local_branch"]),
 S("安捷伦科技广州分部","实验室仪器","仪器、耗材，原厂技术支持","national_top","foreign","chemical",["原厂维保","进口仪器"],["local_branch"]),
 S("广州化学试剂厂","本土生产","常规化验试剂快速供应","local","private","chemical",["试剂生产"],["warehouse","onsite"]),
],
"GL": [
 S("国药集团化学试剂厦门分公司","国企龙头","试剂耗材漳厦就近配送，合规溯源","national_top","soe","chemical",["危化运输许可","溯源合规","全品类"],["warehouse","regional_hub"],"primary"),
 S("厦门翔昀实验室设备古雷分部","炼化定点","古雷炼化定点，仪器+耗材一体，持证专车","local","private","petrochem",["危化运输许可","炼化定点"],["onsite","regional_hub"]),
 S("福建省喜玛拉雅科技","长期供货","化验试剂、分析仪器配件，配送资质齐全","regional","private","petrochem",["危化运输许可","炼化定点"],["onsite","local_branch"]),
 S("赛默飞世尔厦门服务中心","进口仪器","实验室仪器、耗材，石化化验室适配","national_top","foreign","petrochem",["原厂维保","石化适配"],["regional_hub"]),
 S("福建化玻仪器古雷项目部","本地响应","玻璃仪器、常规耗材，属地快速","local","private","chemical",["就近配送"],["onsite"]),
],
"CQ": [
 S("国药集团化学试剂重庆分公司","国企龙头","试剂、耗材合规溯源","national_top","soe","chemical",["危化运输许可","溯源合规","全品类"],["warehouse","local_branch"],"primary"),
 S("重庆科瑞仪器有限公司","属地主供","本地配送，化验设备、耗材一体，持证专车","local","private","chemical",["危化运输许可","就近配送"],["warehouse","onsite"]),
 S("赛默飞世尔重庆服务中心","进口仪器","进口分析仪器，原厂维保+耗材","national_top","foreign","petrochem",["原厂维保","石化适配"],["local_branch"]),
 S("安捷伦科技重庆办事处","色谱质谱","西南石化化验室适配","national_top","foreign","petrochem",["原厂维保","石化适配"],["local_branch"]),
 S("重庆化学试剂总厂","本土生产","常规化验试剂现货充足","local","private","chemical",["试剂生产"],["warehouse","onsite"]),
],
},
}

# ════════════════════════════════════════════════════════════════════
ORDER = ["manpower", "event", "advertising", "office_leasing", "office_maint",
         "it_hardware", "consulting", "shuttle", "security", "it_software",
         "catering", "insurance", "mro_service", "mro", "lab"]
BASE_KEYS = ["SH", "NS", "GL", "CQ"]
KEEP = ["key", "en", "cn", "icon", "accent", "tagline", "model"]

cats = []
for key in ORDER:
    m = META[key]
    ov = META_OVERRIDE.get(key, {})
    cat = {k: m[k] for k in KEEP}
    cat["redline"] = ov.get("redline", m.get("redline", ""))
    cat["compliance"] = ov.get("compliance", m.get("compliance", []))
    cat["tips"] = ov.get("tips", m.get("tips", []))
    cat["weights"] = WEIGHTS.get(key, DEFAULT_W)
    roster = ROSTERS[key]
    cat["bases"] = {b: {"suppliers": roster[b]} for b in BASE_KEYS}
    # 校验：每基地恰 5 家、恰 1 家 primary
    for b in BASE_KEYS:
        sl = roster[b]
        assert len(sl) == 5, f"{key}/{b} 供应商数={len(sl)}≠5"
        prim = [s for s in sl if s["role"] == "primary"]
        assert len(prim) == 1, f"{key}/{b} primary 数={len(prim)}≠1"
    cats.append(cat)

out = {
    "section": OLD["section"],
    "bases": OLD["bases"],
    "dim_keys": ["qual", "sector", "local", "scale", "service"],
    "dim_cn": {"qual": "资质合规达标", "sector": "石化行业适配", "local": "属地履约响应",
               "scale": "规模与品牌背书", "service": "服务保障与兜底"},
    "default_weights": DEFAULT_W,
    "categories": cats,
}

(BASE / "services.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
n = sum(len(ROSTERS[k][b]) for k in ORDER for b in BASE_KEYS)
print(f"OK · {len(cats)} 品类 × 4 基地 × 5 供应商 = {n} 家，已写入 services.json")
