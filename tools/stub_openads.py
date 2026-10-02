#!/usr/bin/env python3
"""把 com/hzhj/openads 包空壳化 —— 删广告 SDK 类之前的必要一步.

为什么需要:
    App 本体通过 com.hzhj.openads(64 个类) 这一层桥梁引用广告 SDK 类型, 例如:
        .field public ᛱᛱᛱᛱᛱ:Lcom/hzhj/openads/HJAdsSdkReward;     (HJAdManager)
        .field public ᛱᛱᛱᛱᤞ:Lcom/hzhj/openads/HJAdsSdkSplash;     (HJSplashAdHelper)
    ART 链接时会解析这些字段类型, 所以 HJAdsSdkReward / HJAdsSdkSplash 这两个类名必须存在。
    但它们的内部实现又全都指向真正的广告 SDK —— 一旦删掉 SDK, 它们自己就链接失败了。

做法:
    把每个 openads 类压成"只有类名 + superclass + 接口"的空壳, 清空所有字段和方法。
    这样:
      - 类型解析全部保留 (App 侧的字段不再悬空)
      - 空壳内部没有任何广告 SDK 引用, 不会连带把 SDK 类拖回来
      - 这些类的成员在去广告版里本来就不会被执行 (所有调用点都已旁路)

另外处理两处会让空壳自身悬空的地方:
      - .super 指向待删广告类   -> 改成 Ljava/lang/Object;
      - .implements 指向待删类  -> 直接丢弃

用法:
    stub_openads.py <smali 根目录>...
"""
import re
import sys
from pathlib import Path

PKG = "com/hzhj/openads/"

# 这些前缀的类会被删除, 空壳不能引用它们
AD_PREFIXES = (
    "Lcom/kwad/", "Lcom/byazt/", "Lcom/bytedance/", "Lcom/pangle/",
    "Lcom/baidu/mobads/", "Lcom/sigmob/", "Lcom/mobads/", "Lcom/beizi/",
    "Lcom/octopus/", "Lcom/ss/android/", "Lms/bz/bd/", "Lcom/yxcorp/",
    "Lcom/octet/",
)

CLASS_LINE = re.compile(r"^(\.class\b[^\n]*)$", re.MULTILINE)
SUPER = re.compile(r"^\.super\s+(L[^\s;]+;)", re.MULTILINE)
IMPLEMENTS = re.compile(r"^\.implements\s+(L[^\s;]+;)", re.MULTILINE)


def is_ad(t: str) -> bool:
    return t.startswith(AD_PREFIXES)


def stub(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    cm = CLASS_LINE.search(text)
    if not cm:
        return "SKIP(no .class)"
    cls_line = cm.group(1)

    sup = SUPER.search(text)
    sup_t = sup.group(1) if sup else "Ljava/lang/Object;"
    replaced_super = False
    if is_ad(sup_t):
        sup_t, replaced_super = "Ljava/lang/Object;", True

    all_ifaces = IMPLEMENTS.findall(text)
    kept = [i for i in all_ifaces if not is_ad(i)]
    dropped = len(all_ifaces) - len(kept)

    out = [cls_line, f".super {sup_t}", ""]
    for i in kept:
        out.append(f".implements {i}")
    if kept:
        out.append("")
    out.append("# debloat: 广告实现已清空 (调用点全部旁路), 仅保留类型以维持链接")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

    note = []
    if replaced_super:
        note.append("super->Object")
    if dropped:
        note.append(f"丢{dropped}接口")
    return "OK " + (",".join(note) if note else "stub")


def main() -> int:
    total = 0
    for root in (Path(a) for a in sys.argv[1:]):
        for path in sorted(root.rglob("*.smali")):
            rel = str(path.relative_to(root)).replace("\\", "/")
            if not rel.startswith(PKG):
                continue
            r = stub(path)
            if r.startswith("OK"):
                total += 1
    print(f"空壳化 {total} 个 openads 类")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
