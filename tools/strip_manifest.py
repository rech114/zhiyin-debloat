#!/usr/bin/env python3
"""从 apktool 解码出的 AndroidManifest.xml 里摘除广告 SDK 的组件声明.

为什么必须"先摘声明":
    Manifest 里声明的 ContentProvider 是**系统在 Application.onCreate 之前自动实例化**的。
    如果不摘掉声明就删掉对应类 (或删掉它依赖的 .so), App 会在启动瞬间崩,
    而且崩溃发生在任何应用代码运行之前, 日志探针也救不回来。

策略: 只删「组件声明」, 不碰 <queries>/<uses-permission>/<meta-data> 之外的东西;
      宿主自己的组件 (com.zhiyin / com.app.yxcds) 一律保留。

用法:
    strip_manifest.py <AndroidManifest.xml> [--dry-run]
"""
import argparse
import re
import sys
from pathlib import Path

# 广告 SDK 的包名前缀
AD_PREFIXES = (
    "com.qq.e.",
    "com.kwad.",
    "com.bytedance.",
    "com.byazt.",
    "com.pangle.",
    "com.baidu.mobads.",
    "com.sigmob.",
    "com.mobads.",
    "com.beizi.",
    "com.octopus.",
    "com.ss.android.",
    "ms.bz.bd.",
    "com.octet.",
)

# 会被系统实例化的组件标签
COMPONENT_TAGS = ("activity", "activity-alias", "service", "receiver", "provider")

SELF_CLOSING = re.compile(
    r"<(?P<tag>%s)\b(?P<attrs>[^>]*?)/>" % "|".join(COMPONENT_TAGS))
PAIRED = re.compile(
    r"<(?P<tag>%s)\b(?P<attrs>[^>]*?)>(?P<body>.*?)</\1>" % "|".join(COMPONENT_TAGS),
    re.DOTALL)
NAME = re.compile(r'android:name="([^"]*)"')
AUTHORITY = re.compile(r'android:authorities="([^"]*)"')


def is_ad(attrs: str) -> bool:
    names = NAME.findall(attrs) + AUTHORITY.findall(attrs)
    return any(n.startswith(AD_PREFIXES) for n in names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    text = args.manifest.read_text(encoding="utf-8")
    removed = []

    def repl_self(m):
        if not is_ad(m.group("attrs")):
            return m.group(0)
        names = NAME.findall(m.group("attrs"))
        removed.append((m.group("tag"), names[0] if names else "?"))
        return ""

    def repl_pair(m):
        if not is_ad(m.group("attrs")):
            return m.group(0)
        names = NAME.findall(m.group("attrs"))
        removed.append((m.group("tag"), names[0] if names else "?"))
        return ""

    out = SELF_CLOSING.sub(repl_self, text)
    out = PAIRED.sub(repl_pair, out)

    print(f"摘除组件 {len(removed)} 个:")
    for tag, name in removed[:80]:
        print(f"  - <{tag}> {name}")
    if len(removed) > 80:
        print(f"  ... 其余 {len(removed) - 80} 个")

    if args.dry_run:
        return 0
    args.manifest.write_text(out, encoding="utf-8")
    print(f"已写回 {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
