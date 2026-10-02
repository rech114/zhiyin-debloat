#!/usr/bin/env python3
"""删除 apktool 解码树里的广告 SDK 原生库与 assets 插件.

判定依据是**逐个 .so 查了引用方**, 不是按名字猜:
    Pglbizssdk_ml / panglearmor / pangleflipped / tobEmbedEncrypt -> ms.bz.bd(穿山甲)
    octopus                           -> com.hzhj 里的 2 个 SDK 合成桥接类
    sgcore                            -> com.yxcorp.kuaishou.addfp(快手设备指纹)
    plt-base / ti-monitor             -> classes6 广告
    commonV2DevInfo                   -> 全 dex 无任何引用

**明确保留** (App 自身业务在用, 删了就是破坏功能):
    yuv-decoder                       -> jp.co.cyberagent.android.gpuimage (GPUImage 滤镜)
    image_processing_util_jni
    surface_util_jni

**暂留待确认**:
    ttmplayer_lite / avmdl_lite / tt_ugen_layout -> 需反汇编 classes4/5 定位引用方

用法:
    strip_payload.py <apktool 解码树> [--dry-run]
"""
import argparse
import sys
from pathlib import Path

DROP_SO = {
    "libPglbizssdk_ml.so",
    "libpanglearmor.so",
    "libpangleflipped.so",
    "libtobEmbedEncrypt.so",
    "libplt-base.so",
    "libti-monitor.so",
    "liboctopus.so",
    "libsgcore.so",
    "libcommonV2DevInfo.so",
}

# 动态加载的广告插件 jar (百青藤 / 广点通), SDK 不初始化就永不加载
DROP_ASSETS = {
    "bdxadsdk.jar",
    "gdt_plugin/gdtadv2.jar",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    freed = 0
    hits = []

    for so in sorted(args.tree.rglob("*.so")):
        if so.name in DROP_SO:
            hits.append(so)
            freed += so.stat().st_size

    for rel in sorted(DROP_ASSETS):
        p = args.tree / "assets" / rel
        if p.exists():
            hits.append(p)
            freed += p.stat().st_size

    for p in hits:
        print(f"  - {p.relative_to(args.tree)}  ({p.stat().st_size:,} B)")
        if not args.dry_run:
            p.unlink()

    # 删空的 gdt_plugin 目录
    gp = args.tree / "assets" / "gdt_plugin"
    if gp.is_dir() and not any(gp.iterdir()) and not args.dry_run:
        gp.rmdir()

    print(f"共 {len(hits)} 个文件, 释放 {freed / 1048576:.2f} MB"
          f"{' (dry-run, 未实际删除)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
