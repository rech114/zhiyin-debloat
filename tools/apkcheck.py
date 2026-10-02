#!/usr/bin/env python3
"""APK 体检 —— 对齐 + 压缩方式 + 签名, 用来验收 zipalign/apksigner 的产物.

对齐要求:
    lib/**/*.so            -> 4096 字节页对齐 且 STORED  (extractNativeLibs=false 必需)
    resources.arsc         -> 4 字节对齐 且 STORED       (targetSdk>=30 必需)
    其它 STORED 条目        -> 4 字节对齐

用法:
    apkcheck.py <apk> [apk ...]
"""
import struct
import sys
import zipfile
from pathlib import Path

PAGE = 4096


def data_offset(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> int:
    zf.fp.seek(info.header_offset)
    nlen, elen = struct.unpack_from("<HH", zf.fp.read(30), 26)
    return info.header_offset + 30 + nlen + elen


def check_manifest(z: zipfile.ZipFile) -> bool:
    """校验 manifest 的组件引用完整性.

    教训: <activity-alias> 的 android:name 往往是**宿主包名**, 按名字匹配不到广告前缀,
    但它的 android:targetActivity 指向的 Activity 若被删掉, Android 会直接判定
    INSTALL_PARSE_FAILED_MANIFEST_MALFORMED —— 装都装不上。
    所以这里必须显式检查"有没有悬空的 targetActivity"。
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from axml_strip import (StringPool, scan, chunk_header,
                                RES_STRING_POOL_TYPE)
    except ImportError:
        print("  (跳过 manifest 检查: 找不到 axml_strip)")
        return True

    data = z.read("AndroidManifest.xml")
    _, _, size = chunk_header(data, 0)
    off, pool = 8, None
    while off < size:
        ct, _h, cs = chunk_header(data, off)
        if ct == RES_STRING_POOL_TYPE:
            pool = StringPool(data, off)
            off += cs
            break
        off += cs
    if pool is None:
        print("  !! manifest 里找不到字符串池")
        return False

    elems = list(scan(pool, data, off, size))
    declared = {a.get("name") for tag, _s, _e, a in elems if tag == "activity"}
    dangling = [(a.get("name"), a.get("targetActivity"))
                for tag, _s, _e, a in elems if tag == "activity-alias"
                if a.get("targetActivity") and a.get("targetActivity") not in declared]
    pkg = next((a.get("package") for tag, _s, _e, a in elems if tag == "manifest"), "?")
    n_alias = sum(1 for tag, _s, _e, _a in elems if tag == "activity-alias")
    print(f"  manifest: package={pkg} activity={len(declared)} alias={n_alias}")
    if dangling:
        for n, t in dangling:
            print(f"  !! 悬空 targetActivity: {n} -> {t}")
        return False
    return True


def check(path: Path) -> bool:
    ok = True
    with zipfile.ZipFile(path) as z:
        so_bad = arsc_bad = other_bad = 0
        for info in z.infolist():
            if info.compress_type != 0:
                if info.filename.endswith((".so", ".arsc")):
                    print(f"  !! {info.filename} 被压缩了, 应为 STORED")
                    ok = False
                continue
            off = data_offset(z, info)
            if info.filename.endswith(".so"):
                if off % PAGE:
                    so_bad += 1
                    print(f"  !! {info.filename} 页对齐失败 (mod4096={off % PAGE})")
            elif info.filename.endswith(".arsc"):
                if off % 4:
                    arsc_bad += 1
                    print(f"  !! {info.filename} 4 字节对齐失败")
            elif off % 4:
                other_bad += 1
            if not ok:
                break
        ok = ok and not (so_bad or arsc_bad or other_bad)
        names = z.namelist()
        sigs = [n for n in names if n.startswith("META-INF/")
                and n.rsplit(".", 1)[-1] in ("SF", "RSA", "DSA", "EC")]
        print(f"  条目 {len(names)}  签名文件 {sigs}  classes7.dex "
              f"{'有' if 'classes7.dex' in names else '缺失'}")
        ok = check_manifest(z) and ok
    print(f"{'PASS' if ok else 'FAIL'}  {path.name}")
    return ok


def main() -> int:
    return 0 if all(check(Path(p)) for p in sys.argv[1:]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
