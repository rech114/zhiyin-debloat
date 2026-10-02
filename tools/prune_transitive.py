#!/usr/bin/env python3
"""传递闭包式剪枝 —— 删广告 SDK 类的正确做法.

为什么不能按包名列举:
    作者把一部分广告包装代码放在了 com/hzhj/libs/ 命名空间下 (和自有库混在一起),
    按包名前缀列举必然漏掉, 实测漏了 621 处悬空引用。

做法 (迭代到不动点):
    1) 先删掉已知的广告 SDK 包
    2) 然后反复扫: 只要某个类引用了已删除的类, 它本身就是广告代码, 一并删掉
    3) 直到没有新的可删类为止
    com/zhiyin(业务本体) 与 com/hzhj/openads(类型桥) 是保护名单, 永不自动删除 ——
    它们若仍有悬空引用, 会原样报出来, 由人决定怎么修。

用法:
    prune_transitive.py --root <smali 根目录> [--root ...] [--dry-run]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classrefcheck import TYPE_IN_SIG, collect  # noqa: E402

PROTECTED = ("Lcom/zhiyin/", "Lcom/hzhj/openads/")

# 整份 smali 文本里出现的所有类引用: 包含方法体里的 invoke / new-instance /
# const-class / check-cast 等等, 而不只是签名。
# 这是必须的 —— 只查签名会漏掉"类被删了但代码还在调它"的情况:
# 表现就是点了按钮没反应 (NoClassDefFoundError), 而且静态闸门也发现不了。
ANY_REF = re.compile(r"L[A-Za-z0-9_$/]+;")


def is_protected(cls: str) -> bool:
    return cls.startswith(PROTECTED)


def refs_of(info) -> set:
    """签名级引用 (super / 接口 / 字段类型 / 方法签名)."""
    out = set()
    if info["super"]:
        out.add(info["super"])
    out |= set(info["ifaces"])
    out |= {t for _n, t in info["fields"] if t.startswith("L")}
    for sig in info["methods"]:
        out |= {"L" + t + ";" for t in TYPE_IN_SIG.findall(sig)}
    return out


def all_refs(info) -> set:
    """全量引用: 只要文件里出现了这个类名就算."""
    try:
        text = Path(info["file"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(ANY_REF.findall(text))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", required=True)
    ap.add_argument("--before-names", type=Path,
                    help="删类之前的类名快照; 用它作为 deleted 的种子")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-rounds", type=int, default=40)
    args = ap.parse_args()

    names, refs = set(), {}
    for r in args.root:
        n, rf = collect(Path(r))
        names |= n
        refs.update(rf)
    print(f"扫描 {len(names)} 个类")

    # 关键: 上一步已经用包名 rm 掉了一批类, 这里必须知道"哪些不见了",
    # 否则 deleted 起始为空, 第一轮就假收敛 (踩过)。
    deleted = set()
    if args.before_names:
        before = set(args.before_names.read_text(encoding="utf-8").split())
        deleted = before - names
        print(f"删前快照 {len(before)} 类 -> 已知消失 {len(deleted)} 类")
    # 全量引用表 (含方法体), 以及"被受保护类引用"的集合 —— 后者是删除的禁区
    full = {c: all_refs(i) for c, i in refs.items()}
    kept = set()
    for c in names:
        if is_protected(c):
            kept |= full[c]
    print(f"受保护类共引用 {len(kept)} 个外部类, 这些一律不删")

    for rnd in range(1, args.max_rounds + 1):
        alive = names - deleted
        victims = []
        for c in alive:
            if is_protected(c) or c in kept:
                continue
            # 只要它引用了已删的类, 它就是广告代码
            if full[c] & deleted:
                victims.append(c)
        if not victims:
            print(f"第 {rnd} 轮: 收敛, 无新增可删类")
            break
        deleted |= set(victims)
        print(f"第 {rnd} 轮: 新增删除 {len(victims)} 个类 (累计 {len(deleted)})")

    if not args.dry_run:
        removed = 0
        for cls in deleted:
            info = refs.get(cls)
            if not info:
                # 属于"上一步用包名已经 rm 掉"的那批, 文件早没了, 跳过
                continue
            p = Path(info["file"])
            if p.exists():
                p.unlink()
                removed += 1
        print(f"实际删除文件 {removed} 个")

    # 受保护类里仍有引用指向已删类的 —— 这就是会导致"点了没反应"的元凶
    leftover = []
    for cls in (names - deleted):
        miss = full[cls] & deleted
        if miss:
            leftover.append((cls, sorted(miss)[:4]))

    print(f"\n共删除 {len(deleted)} 个类")
    if leftover:
        print(f"受保护类中仍有 {len(leftover)} 个悬空引用 (需人工处理):")
        for cls, miss in leftover[:30]:
            print(f"   {cls}\n        -> {miss}")
        return 1
    print("受保护类无悬空引用 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
