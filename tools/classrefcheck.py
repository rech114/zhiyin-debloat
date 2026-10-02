#!/usr/bin/env python3
"""静态引用完整性检查 (smali 层) —— 删类之后的安全闸门.

为什么要它:
    ART 在**类链接阶段**就会解析一个类的 superclass、实现的接口、以及所有字段的类型。
    只要其中任何一项指向了已被删除的类, 这个类就根本无法链接 ——
    代码一行都还没执行, 直接 NoClassDefFoundError 闪退。
    (这次踩过的同类教训: activity-alias 的 targetActivity 悬空 -> 装都装不上)

判据 (只报真悬空):
    对存活类 C 的每个引用 R,
    若 R 属于"原包类集合"却不在"现包类集合"里 -> 悬空, 必然失败。
    框架类 (android.*, java.*, kotlin.* 等) 本来就不在包里, 不参与判断。

用法:
    classrefcheck.py --before <原始 smali 根目录>... --after <删减后 smali 根目录>...
"""
import argparse
import re
from pathlib import Path

CLASS_DECL = re.compile(r"^\.class\b.*?(L[^\s;]+;)\s*$", re.MULTILINE)
SUPER = re.compile(r"^\.super\s+(L[^\s;]+;)", re.MULTILINE)
IMPLEMENTS = re.compile(r"^\.implements\s+(L[^\s;]+;)", re.MULTILINE)
FIELD = re.compile(r"^\.field\b[^\n]*?([^\s:]+):(L[^\s;]+;|\[*[VZBSCIJFD])\s*$", re.MULTILINE)
METHOD = re.compile(r"^\.method\b[^\n]*?(\([^\n]*?\)[^\s\n]+)\s*$", re.MULTILINE)
TYPE_IN_SIG = re.compile(r"L([A-Za-z0-9_$/]+);")
# 整份文本里的全部类引用 —— 含方法体里的 invoke / new-instance / const-class。
# 只查签名会漏掉"类被删了但代码还在调"的情况: 表现为点了按钮没反应,
# 而且静态检查还报"无悬空引用"(踩过这个坑)。
ANY_REF = re.compile(r"L[A-Za-z0-9_$/]+;")


def collect(root: Path):
    names, refs = set(), {}
    for path in root.rglob("*.smali"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = CLASS_DECL.search(text)
        if not m:
            continue
        cls = m.group(1)
        names.add(cls)
        sup = SUPER.search(text)
        refs[cls] = {
            "file": str(path),
            "super": sup.group(1) if sup else None,
            "ifaces": IMPLEMENTS.findall(text),
            "fields": [(fm.group(1), fm.group(2)) for fm in FIELD.finditer(text)],
            "methods": [mm.group(1) for mm in METHOD.finditer(text)],
            "all": set(ANY_REF.findall(text)),
        }
    return names, refs


def dump_names(roots, dest: Path) -> int:
    """只收集类名并落盘 —— 删类之前先跑一次, 避免在 CI 里复制整棵 smali 树."""
    names = set()
    for r in roots:
        n, _ = collect(Path(r))
        names |= n
    dest.write_text("\n".join(sorted(names)), encoding="utf-8")
    return len(names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", nargs="*", default=[])
    ap.add_argument("--before-names", type=Path,
                    help="之前用 --dump-names 存下的类名快照")
    ap.add_argument("--dump-names", type=Path,
                    help="只收集类名写到这里, 然后退出")
    ap.add_argument("--after", nargs="*", default=[])
    ap.add_argument("--max-report", type=int, default=40)
    args = ap.parse_args()

    if args.dump_names:
        n = dump_names(args.before or args.after, args.dump_names)
        print(f"类名快照: {n} 个 -> {args.dump_names}")
        return 0

    if args.before_names:
        before_names = set(args.before_names.read_text(encoding="utf-8").split())
        print(f"  [before] {args.before_names}: {len(before_names)} 类")
    else:
        before_names = set()
        for r in args.before:
            n, _ = collect(Path(r))
            before_names |= n
            print(f"  [before] {r}: {len(n)} 类")

    if not args.after:
        raise SystemExit("需要 --after")

    after_names, refs = set(), {}
    for r in args.after:
        n, rf = collect(Path(r))
        after_names |= n
        refs.update(rf)
        print(f"  [after ] {r}: {len(n)} 类")

    print(f"\n原包类 {len(before_names)} -> 现包类 {len(after_names)} "
          f"(删掉 {len(before_names - after_names)})")

    gone = before_names - after_names

    problems = []
    for cls, info in refs.items():
        if info["super"] and info["super"] in gone:
            problems.append((cls, "superclass", info["super"], info["file"]))
        for i in info["ifaces"]:
            if i in gone:
                problems.append((cls, "interface", i, info["file"]))
        for _fname, ftype in info["fields"]:
            if ftype.startswith("L") and ftype in gone:
                problems.append((cls, "field-type", ftype, info["file"]))
        for sig in info["methods"]:
            for t in TYPE_IN_SIG.findall(sig):
                if "L" + t + ";" in gone:
                    problems.append((cls, "method-sig", "L" + t + ";", info["file"]))
        # 方法体里的调用/实例化/类字面量 —— 漏掉这一项就等于闸门是瞎的
        for t in (info.get("all") or ()):
            if t in gone:
                problems.append((cls, "body-ref", t, info["file"]))

    if not problems:
        print("\nOK  无悬空引用 —— 所有存活类的 superclass / 接口 / 字段类型 / 方法签名"
              "都不指向已删除的类")
        return 0

    print(f"\n★ 发现 {len(problems)} 处悬空引用 (前 {args.max_report} 条):")
    for cls, kind, target, f in problems[:args.max_report]:
        print(f"   [{kind}] {cls}\n        -> {target}\n        @ {f}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
