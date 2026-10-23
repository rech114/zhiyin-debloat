#!/usr/bin/env python3
"""一站式品牌替换: 图标 + 应用名.

做三件事:
  1. 由源图生成 5 个密度的启动图标 (普通 + 圆形), 替换 APK 里的 mipmap
  2. 改 resources.arsc 里 app_name 的值
  3. 把自适应图标 (v26+) 的前景指向新的 mipmap

图标条目的定位**不靠文件名、也不靠文件体积**, 而是解析 resources.arsc:
从资源 ID 拆出 (package, typeId, entryIndex), 找到对应 ResTable_type chunk,
再按 config 里的 density 字段分出密度。这样作者换版、改混淆名都不影响。

为什么前景要改:
    Android 8+ 优先用 mipmap-anydpi-v26/ic_launcher.xml (自适应图标),
    它引用的是矢量 @drawable/ic_launcher_foreground —— 不指向我们换掉的位图,
    所以不改这里, 新图标在 Android 8+ 上根本不会显示。

用法:
    make_branding.py --apk base/test.apk --icon base/icon.png --outdir work/branding \
        --rename "只音=Apertus"
    输出: 各条目文件 + 供 repack 使用的 `--set 条目=文件` 参数
"""
import argparse
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


from axml_patch import patch as axml_apply  # noqa: E402

DENSITY = {120: ("mdpi", 48), 160: ("mdpi", 48), 240: ("hdpi", 72),
           320: ("xhdpi", 96), 480: ("xxhdpi", 144), 640: ("xxxhdpi", 192),
           0: ("mdpi", 48)}
TYPE_STRING = 0x03
DENSITY_ANY = 0xFFFE          # anydpi (自适应图标所在的 config)
NO_ENTRY = 0xFFFFFFFF         # 资源表里表示"该 config 下不存在此条目"


def blank_entries(arsc: bytearray, type_id: int, entry_ids, density=DENSITY_ANY):
    """把某个 config 下的若干条目标记为"不存在"。

    为什么要这么做:
        Android 8+ 的启动图标走 mipmap-anydpi-v26 的 <adaptive-icon>, 会盖过密度位图。
        而自适应图标的 <foreground> 必须指向**别的** drawable —— 一旦指向 ic_launcher
        自身, 就形成
            mipmap/ic_launcher -> BW.xml -> foreground -> mipmap/ic_launcher -> ...
        加载时抛 "Recursive reference in drawable", 直接崩溃 (真踩过)。

        把 anydpi 下的条目标记为 0xFFFFFFFF 后, 解析器找不到它, 会自然回落到密度位图,
        不需要重建整个 arsc 结构。
    """
    _, t_hdr, _, _ = struct.unpack_from("<HHII", arsc, 0)
    pool_off = t_hdr
    psize = struct.unpack_from("<I", arsc, pool_off + 4)[0]

    off, total, hits = pool_off + psize, len(arsc), 0
    while off + 8 <= total:
        ct, ch, cs = struct.unpack_from("<HHI", arsc, off)
        if cs <= 0:
            break
        if ct == 0x0200:
            sub = off + ch
            while sub + 8 <= off + cs:
                sct, sch, scs = struct.unpack_from("<HHI", arsc, sub)
                if scs <= 0:
                    break
                if sct == 0x0201 and arsc[sub + 8] == type_id:
                    if struct.unpack_from("<H", arsc, sub + 20 + 14)[0] == density:
                        for e in entry_ids:
                            struct.pack_into("<I", arsc, sub + sch + 4 * e, NO_ENTRY)
                            hits += 1
                sub += scs
        off += cs
    return hits


def parse_arsc_paths(arsc: bytes):
    """返回 {(typeId, entryIdx, density): 'res/xx.webp'}."""
    _, t_hdr, _, _ = struct.unpack_from("<HHII", arsc, 0)
    pool_off = t_hdr
    cnt, _sty, flags, sstart, _ystart = struct.unpack_from("<IIIII", arsc, pool_off + 8)
    assert flags & 0x100, "只支持 UTF-8 字符串池"
    base = pool_off + sstart
    phdr = struct.unpack_from("<H", arsc, pool_off + 2)[0]
    offs = [struct.unpack_from("<I", arsc, pool_off + phdr + 4 * k)[0] for k in range(cnt)]

    def s(k):
        p = base + offs[k]
        n = arsc[p]
        p += 2 if n & 0x80 else 1
        ln = arsc[p]
        p += 2 if ln & 0x80 else 1
        return arsc[p:p + ln].decode("utf-8", "replace")

    psize = struct.unpack_from("<I", arsc, pool_off + 4)[0]
    out, off, total = {}, pool_off + psize, len(arsc)
    while off + 8 <= total:
        ct, ch, cs = struct.unpack_from("<HHI", arsc, off)
        if cs <= 0:
            break
        if ct == 0x0200:                        # RES_TABLE_PACKAGE
            sub = off + ch
            while sub + 8 <= off + cs:
                sct, sch, scs = struct.unpack_from("<HHI", arsc, sub)
                if scs <= 0:
                    break
                if sct == 0x0201:               # RES_TABLE_TYPE
                    tid = arsc[sub + 8]
                    dens = struct.unpack_from("<H", arsc, sub + 20 + 14)[0]
                    ecnt, e_start = struct.unpack_from("<II", arsc, sub + 12)
                    for e in range(ecnt):
                        # 条目偏移数组在 sub+headerSize; entriesStart 是条目"数据"的起点
                        eo = struct.unpack_from("<I", arsc, sub + sch + 4 * e)[0]
                        if eo == 0xFFFFFFFF:
                            continue
                        ent = sub + e_start + eo
                        _vsize, eflags, _key = struct.unpack_from("<HHI", arsc, ent)
                        if eflags & 0x0001:     # FLAG_COMPLEX
                            continue
                        _sz, _r0, dt, dd = struct.unpack_from("<HBBI", arsc, ent + 8)
                        if dt == TYPE_STRING:
                            out[(tid, e, dens)] = s(dd)
                sub += scs
        off += cs
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", type=Path, required=True)
    ap.add_argument("--icon", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--rename", action="append", default=[])
    ap.add_argument("--package", help="新包名 (写进 resources.arsc 的 ResTable_package 字段)")
    ap.add_argument("--launcher-id", default="0x7f10001d")
    ap.add_argument("--round-id", default="0x7f10001e")
    ap.add_argument("--foreground-id", default="0x7f0801d0")
    ap.add_argument("--legacy-logo-id", default="0x7f0801cd")   # drawable/ic_icon
    args = ap.parse_args()

    from PIL import Image, ImageDraw
    args.outdir.mkdir(parents=True, exist_ok=True)
    sets = []

    arsc = zipfile.ZipFile(args.apk).read("resources.arsc")

    def rid(x):
        v = int(x, 16)
        return (v >> 24) & 0xFF, (v >> 16) & 0xFF, v & 0xFFFF

    paths = parse_arsc_paths(arsc)
    print(f"arsc 解析出 {len(paths)} 个字符串型资源条目")

    src = Image.open(args.icon).convert("RGBA")
    for lamp, tag in ((args.launcher_id, ""), (args.round_id, "_round")):
        _, tid, eidx = rid(lamp)
        found = {d: p for (t, e, d), p in paths.items()
                 if t == tid and e == eidx and d in DENSITY}
        if not found:
            print(f"★ 未找到 {lamp} 的条目")
            return 1
        print(f"{lamp} -> {len(found)} 个密度: {sorted(found)}")
        for d, path in found.items():
            _name, px = DENSITY[d]
            img = src
            if tag:
                m = Image.new("L", (src.size[0],) * 2, 0)
                ImageDraw.Draw(m).ellipse((0, 0, src.size[0] - 1, src.size[0] - 1), fill=255)
                img = src.copy()
                img.putalpha(m)
            out = args.outdir / (path.replace("/", "_") + tag + ".png")
            img.resize((px, px), Image.LANCZOS).save(out)
            sets.append(f"--set {path}={out}")
            print(f"   density={d:5} {px:3}px -> {path}")

    # 开屏/加载页的旧 logo: 布局里引用的是 @drawable/ic_icon (作者自己的矢量 logo),
    # 不是启动图标, 所以换 mipmap 换不到它。把引用改指到 @mipmap/ic_launcher。
    ic_icon = int(args.legacy_logo_id, 16)
    target_id = int(args.launcher_id, 16)
    log_hits = 0
    with zipfile.ZipFile(args.apk) as z:
        for n in z.namelist():
            if not (n.startswith("res/") and n.endswith(".xml")):
                continue
            data = bytearray(z.read(n))
            if struct.pack("<I", ic_icon) not in data:
                continue
            hits = axml_apply(data, {ic_icon: target_id}, {})
            if not hits:
                continue
            out = args.outdir / n.replace("/", "_")
            out.write_bytes(bytes(data))
            sets.append(f"--set {n}={out}")
            log_hits += len(hits)
            print(f"  旧 logo 引用 {n}: {len(hits)} 处 -> ic_launcher")
    assert log_hits >= 3, f"预期至少 3 处旧 logo 引用, 实际 {log_hits} (资源 ID 可能变了)"

    # 自适应图标: 绝不能让前景指向 ic_launcher 自己 (会 Recursive reference 崩溃)。
    # 改用"把 anydpi 下的条目标记为不存在", 让系统回落到密度位图。
    arsc_b = bytearray(arsc)
    _, launcher_tid, launcher_e = rid(args.launcher_id)
    _, round_tid, round_e = rid(args.round_id)
    assert launcher_tid == round_tid, "两个启动图标应在同一个 type 下"
    n = blank_entries(arsc_b, launcher_tid, [launcher_e, round_e])
    print(f"已把 anydpi 下 {n} 个启动图标条目标记为不存在 (回落到密度位图)")
    assert n == 2, f"预期屏蔽 2 个 anydpi 条目, 实际 {n}"
    arsc = bytes(arsc_b)

    if args.rename:
        src_arsc = args.outdir / "_in.arsc"
        src_arsc.write_bytes(arsc)
        dst = args.outdir / "resources.arsc"
        cmd = [sys.executable, str(Path(__file__).parent / "arsc_rename.py"),
               str(src_arsc), "-o", str(dst)]
        for r in args.rename:
            cmd += ["--replace", r]
        if args.package:
            cmd += ["--package-name", args.package]
        subprocess.run(cmd, check=True)
        sets.append(f"--set resources.arsc={dst}")

    print("\n--- repack 参数 ---")
    for s in sets:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
