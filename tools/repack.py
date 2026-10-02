#!/usr/bin/env python3
"""APK 精确重建 —— 替换/删除指定条目, 其余条目按原样搬运.

为什么不用 zip 命令:
    APK 里 resources.arsc 和 lib/*.so 必须是 STORED(不压缩) 且对齐,
    一旦被重新 deflate, Android 11+ 会直接装不上 (targetSdk 30+ / extractNativeLibs=false).
    所以必须逐条保留原 infolist 的 compress_type。

用法:
    repack.py <src.apk> <dst.apk> [--set 归档内路径=本地文件]... [--drop 归档内路径]...
"""
import argparse
import fnmatch
import zipfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--set", action="append", default=[],
                    help="归档内路径=本地文件")
    ap.add_argument("--drop", action="append", default=[],
                    help="要删除的归档内路径 (支持 fnmatch 通配, 如 lib/*/libfoo.so)")
    args = ap.parse_args()

    replace, drop = {}, list(args.drop)
    for item in args.set:
        name, _, local = item.partition("=")
        replace[name] = Path(local)
    # 支持 "lib/*/liboctopus.so" 这类模式
    all_names = {i.filename for i in zipfile.ZipFile(args.src).infolist()}
    drop_set = set()
    for pat in drop:
        if any(ch in pat for ch in "*?["):
            drop_set |= {n for n in all_names if fnmatch.fnmatch(n, pat)}
        else:
            drop_set.add(pat)
    missing = set(replace) - all_names
    if missing:
        raise SystemExit(f"源包里不存在这些条目: {sorted(missing)}")

    with zipfile.ZipFile(args.src) as zin, zipfile.ZipFile(args.dst, "w") as zout:
        for info in zin.infolist():
            if info.filename in drop_set:
                continue
            data = (replace[info.filename].read_bytes() if info.filename in replace
                    else zin.read(info.filename))
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zout.writestr(zi, data, compress_type=info.compress_type)
    print(f"OK -> {args.dst}  (替换 {len(replace)}, 删除 {len(drop)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
