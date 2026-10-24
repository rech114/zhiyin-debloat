#!/usr/bin/env python3
"""smali 类引用存在性检查 —— 抓"补丁引用了不存在的类"。

为什么需要:
    smali 汇编器**不校验类是否存在**。补丁里写一个不存在的类名, 照样汇编出 dex,
    直到运行期走到那条指令才抛 NoClassDefFoundError。

    真实案例 (3.7.0):
        作者把"工具启动器"类从 ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ 改名成 ᛱᛱᛳᤝᛸ/ᛱᛱᛱᛵᤞ,
        而补丁里写死了旧名 -> 工具页一点就崩。

做法:
    1. 扫所有 dex 树的 *.smali, 得到"包里真实存在的类"集合
    2. 扫待检文件里的指令, 抽出引用的类 (new-instance / const-class / check-cast /
       instance-of / invoke-* / sget-object / iget-object 等)
    3. 引用的类若既不在集合里、也不是系统框架类 -> 报错

框架类按前缀白名单排除 (android/ java/ javax/ dalvik/ sun/ org/xmlpull 等),
它们本来就不在 dex 里。

用法:
    smali_refcheck.py --roots <dex树1> [<dex树2> ...] --check <文件或目录> [...]
"""
import argparse
import re
import sys
from pathlib import Path

FRAMEWORK = (
    "Landroid/", "Ljava/", "Ljavax/", "Ldalvik/", "Lsun/", "Lorg/xmlpull/",
    "Lorg/json/", "Lorg/apache/http/", "Lorg/w3c/dom/", "Lorg/xml/sax/",
    "Lcom/android/internal/", "Llibcore/",
)

# 可能带类引用的指令
REF = [
    re.compile(r'^\s*new-instance\s+v\d+,\s*(\S+)'),
    re.compile(r'^\s*const-class\s+v\d+,\s*(\S+)'),
    re.compile(r'^\s*check-cast\s+v\d+,\s*(\S+)'),
    re.compile(r'^\s*instance-of\s+v\d+,\s*v\d+,\s*(\S+)'),
    re.compile(r'^\s*new-array\s+v\d+,\s*v\d+,\s*(\S+)'),
    re.compile(r'^\s*(?:sget|sput)-\w+\s+v\d+,\s*(\S+?);'),
    re.compile(r'^\s*(?:iget|iput)-\w+\s+v\d+,\s*v\d+,\s*(\S+?);'),
    re.compile(r'^\s*invoke-\S+\s+\{[^}]*\},\s*(\S+?);'),
    re.compile(r'^\s*filled-new-instance\s+v\d+,\s*(\S+)'),
]


def collect_existing(roots):
    """返回包里真实存在的类描述符集合."""
    have = set()
    for r in roots:
        for f in r.rglob("*.smali"):
            rel = f.relative_to(r).as_posix()[:-len(".smali")]
            have.add("L" + rel + ";")
    return have


def check(files, have, problems):
    for f in files:
        lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        for i, l in enumerate(lines):
            for pat in REF:
                m = pat.match(l)
                if not m:
                    continue
                cls = m.group(1).strip()
                if not cls.startswith("L") or not cls.endswith(";"):
                    continue
                if cls.startswith(FRAMEWORK):
                    continue
                if cls not in have:
                    problems.append(f"{f.name}:{i + 1}  引用了不存在的类 {cls}\n      {l.strip()[:92]}")
                break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", required=True, help="dex 树根目录 (用于建类索引)")
    ap.add_argument("--check", nargs="+", required=True, help="待检文件或目录")
    a = ap.parse_args()

    have = collect_existing([Path(r) for r in a.roots])
    files = []
    for p in a.check:
        pp = Path(p)
        if pp.is_dir():
            files.extend(sorted(pp.rglob("*.smali")))
        elif pp.exists():
            files.append(pp)

    problems = []
    check(files, have, problems)

    print(f"类引用检查: 索引 {len(have)} 个类, 待检 {len(files)} 个文件")
    if problems:
        print(f"\n★ 发现 {len(problems)} 处引用不存在:")
        for p in problems[:30]:
            print("   " + p)
        return 1
    print("✓ 所有类引用都能在包内找到")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
