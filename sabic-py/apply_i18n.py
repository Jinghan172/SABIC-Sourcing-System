# -*- coding: utf-8 -*-
"""
把 data/*.json 里的中文 prose 字段就地改成「English · 中文」双语。
- 模板族（编号/价格等只差数字的）用正则生成英文；其余用 data/i18n_en.json 字典。
- 幂等：转换后值不再匹配中文键/正则，可重复运行。
- 首次运行为每个文件写 .bak 备份。
用法： python apply_i18n.py          # 应用
       python apply_i18n.py --check  # 只报告未翻译项，不写文件
"""
import json, re, sys, shutil
from pathlib import Path
from i18n_fields import PROSE_FIELDS

BASE = Path(__file__).resolve().parent / "data"
DICT = json.loads((BASE / "i18n_en.json").read_text(encoding="utf-8")) \
    if (BASE / "i18n_en.json").exists() else {}

_CN = re.compile(r'[一-鿿]')
def has_cn(s): return isinstance(s, str) and bool(_CN.search(s))

# 复合 note 前缀（设备）：前缀 + ；+ 工艺亮点（亮点复用 edge 字典）
_COMPOSITE_PREFIX = {
    "防台风应急物资储备": "Typhoon emergency stock",
    "大件山地物流运输保障": "Heavy-cargo mountain logistics assured",
    "C5-M海洋防腐涂层配套": "C5-M marine anti-corrosion coating",
}

def _en_for(v: str):
    """返回该中文值的英文；命中模板或字典返回英文，否则 None。"""
    if v in DICT:
        return DICT[v]
    # T1 设备参考价说明
    m = re.match(r'^基于中石化2022-2023框架协议公告均价，同类均价约(.+?)，本供应商预估(.+?)$', v)
    if m:
        return (f"Based on SINOPEC 2022-2023 framework public average; "
                f"peer avg ~{m.group(1)}, this supplier est. {m.group(2)}")
    # T2 公开中标费率条数
    m = re.match(r'^(\d+) 条公开中标费率$', v)
    if m: return f"{m.group(1)} public award rates"
    # T2b 政采费率口径情景样本（明确为建模、非已核验中标）
    m = re.match(r'^锚定政采/公共资源交易费率口径 · (\d+) 组情景样本（非逐条已核验中标，真实招标见溯源卡）$', v)
    if m:
        return (f"anchored to gov/public-tender rate caliber · {m.group(1)} modeled scenario "
                f"samples (not per-item verified awards; see provenance card)")
    # T3 历史合同结算份数
    m = re.match(r'^(\d+) 份历史合同结算$', v)
    if m: return f"{m.group(1)} historical contract settlements"
    # T3b 历史合同费率口径情景样本
    m = re.match(r'^同类历史合同结算口径 · (\d+) 组情景样本$', v)
    if m: return f"same-type historical contract-rate caliber · {m.group(1)} modeled scenario samples"
    # T4 三平台中标公告按样本量加权
    m = re.match(r'^3 平台 (\d+) 条中标公告按样本量加权$', v)
    if m: return f"3 platforms, {m.group(1)} award notices weighted by sample size"
    # T5 复合 note：前缀；亮点
    m = re.match(r'^(' + '|'.join(map(re.escape, _COMPOSITE_PREFIX)) + r')；(.+)$', v)
    if m:
        edge_en = DICT.get(m.group(2))
        if edge_en:
            return f"{_COMPOSITE_PREFIX[m.group(1)]}; {edge_en}"
    # T6 标准工商核验行
    m = re.match(r'^✅ 存续 · 注册资本 (.+?) · 成立 (\d{4})（企查查核验）$', v)
    if m:
        return f"✅ Active · reg. capital {m.group(1)} · founded {m.group(2)} (QCC-verified)"
    return None

def walk(o, want, miss):
    if isinstance(o, dict):
        for k, val in list(o.items()):
            if k in want and isinstance(val, str) and has_cn(val):
                en = _en_for(val)
                if en is not None:
                    o[k] = f"{en} · {val}"          # 翻译
                elif ' · ' not in val:
                    miss.append(val)                # 真正未翻译（无分隔，需补字典）
                # 含 ' · ' 且无法翻译 → 已是双语，跳过（幂等）
            else:
                walk(val, want, miss)
    elif isinstance(o, list):
        for x in o: walk(x, want, miss)

def main():
    check = '--check' in sys.argv
    all_miss = {}
    for f, want in PROSE_FIELDS.items():
        p = BASE / f
        d = json.loads(p.read_text(encoding="utf-8"))
        miss = []
        walk(d, set(want), miss)
        all_miss[f] = sorted(set(miss))
        if not check:
            bak = p.with_suffix('.json.bak')
            if not bak.exists():
                shutil.copy2(p, bak)
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    total_miss = sum(len(v) for v in all_miss.values())
    print(("CHECK" if check else "APPLIED") + f"  untranslated={total_miss}")
    for f, ms in all_miss.items():
        if ms:
            print(f"\n--- {f}: {len(ms)} untranslated ---")
            for s in ms[:60]: print("  " + s)
    return total_miss

if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
