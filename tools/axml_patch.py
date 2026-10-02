#!/usr/bin/env python3
"""编译后布局 XML 的定点补丁 —— 改属性的 4 字节值, 文件大小不变.

为什么用这种方式:
    换图标 = 改 app:icon 的资源 ID (TYPE_REFERENCE, 4 字节整数)
    改尺寸 = 改 app:iconSize 的维度值 (TYPE_DIMENSION, 也是 4 字节)
    两者宽度固定, 所以原地改写即可 ——
    **不需要动字符串池、不需要重算 chunk size、更不需要重建 resources.arsc**。
    (apktool 重建资源会把 APK 弄坏, 实测产出 "Package info is null", 所以绕开它)

定位方式:
    给定一组"只可能出现在目标布局里"的资源 ID, 逐个扫描 APK 的 res/*.xml,
    谁的字节里同时含这组 ID, 谁就是目标。

用法:
    axml_patch.py <apk> --find-by 0x7f0801ee,0x7f080233 \
        --icon 0x7f0801ee=0x7f0801bc --icon 0x7f080233=0x7f080232 \
        --dim iconSize=0x1401=0x1a01 -o /tmp/patched.xml [--print-entry]
"""
import argparse
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from axml_strip import StringPool, chunk_header, RES_STRING_POOL_TYPE  # noqa: E402

RES_XML_START_ELEMENT = 0x0102


def patch(data: bytearray, icon_map: dict, dim_map: dict):
    """就地改值. 返回 (替换计数, 明细)."""
    _, _, size = chunk_header(data, 0)
    off = 8
    pool = None
    while off < size:
        ct, _h, cs = chunk_header(data, off)
        if ct == RES_STRING_POOL_TYPE:
            pool = StringPool(data, off)
            off += cs
            break
        off += cs
    if pool is None:
        raise SystemExit("找不到字符串池")

    hits = []
    cur = off
    while cur + 8 <= size:
        ct, _h, cs = chunk_header(data, cur)
        if cs <= 0:
            break
        if ct == RES_XML_START_ELEMENT:
            name_idx = struct.unpack_from("<I", data, cur + 20)[0]
            a_start, a_size, a_count = struct.unpack_from("<HHH", data, cur + 24)
            ap = cur + 16 + a_start
            for i in range(a_count):
                ao = ap + i * a_size
                _ns, a_name, _raw = struct.unpack_from("<III", data, ao)
                v_size, _r0, v_type, v_data = struct.unpack_from("<HBBI", data, ao + 12)
                nm = pool[a_name]
                new = None
                if v_type == 0x01 and v_data in icon_map:            # TYPE_REFERENCE
                    new = icon_map[v_data]
                elif v_type == 0x05 and nm in dim_map:               # TYPE_DIMENSION
                    new = dim_map[nm].get(v_data)
                if new is not None:
                    struct.pack_into("<I", data, ao + 16, new)
                    hits.append((pool[name_idx], nm, hex(v_data), hex(new)))
        cur += cs
    return hits


def find_entries(apk: Path, needle):
    """返回所有同时含这些资源 ID 的 res/*.xml 条目名."""
    out = []
    with zipfile.ZipFile(apk) as z:
        for n in z.namelist():
            if not (n.startswith("res/") and n.endswith(".xml")):
                continue
            d = z.read(n)
            if all(x in d for x in needle):
                out.append(n)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk", type=Path)
    ap.add_argument("--find-by", required=True,
                    help="逗号分隔的资源 ID, 用于定位目标 res/*.xml")
    ap.add_argument("--icon", action="append", default=[],
                    help="旧资源ID=新资源ID")
    ap.add_argument("--dim", action="append", default=[],
                    help="属性名=旧值=新值 (如 iconSize=0x1401=0x1a01)")
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--print-entry", action="store_true")
    ap.add_argument("--list-entries", action="store_true",
                    help="只列出所有命中的条目名然后退出 (用于同一份补丁要套到多个文件时)")
    args = ap.parse_args()

    needle = [struct.pack("<I", int(x, 16)) for x in args.find_by.split(",")]

    if args.list_entries:
        found = find_entries(args.apk, needle)
        for n in found:
            print(f"ENTRY={n}")
        print(f"# 命中 {len(found)} 个条目")
        return 0 if found else 1

    icon_map = {}
    for s in args.icon:
        o, n = s.split("=")
        icon_map[int(o, 16)] = int(n, 16)
    dim_map = {}
    for s in args.dim:
        name, o, n = s.split("=")
        dim_map.setdefault(name, {})[int(o, 16)] = int(n, 16)

    if args.out is None:
        raise SystemExit("需要 -o 指定输出文件")
    with zipfile.ZipFile(args.apk) as z:
        found = find_entries(args.apk, needle)
        if not found:
            raise SystemExit("没找到同时含这些资源 ID 的 res/*.xml")
        target = found[0]
        data = bytearray(z.read(target))

    before = len(data)
    hits = patch(data, icon_map, dim_map)
    assert len(data) == before, "长度变了, 不应该发生"

    args.out.write_bytes(bytes(data))
    print(f"目标条目: {target}  ({before} B -> {len(data)} B, 长度未变)")
    for tag, nm, o, n in hits:
        print(f"  {tag.split('.')[-1]:16} {nm:10} {o} -> {n}")
    if not hits:
        return 1
    if args.print_entry:
        print(f"ENTRY={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
