#!/usr/bin/env python3
"""二进制 AndroidManifest.xml (AXML) 定点手术 —— 摘除广告 SDK 的组件声明.

为什么不用 apktool:
    apktool b 会重建 resources.arsc 并把资源短名还原成规范名 (约 3000 个条目改名),
    实测产出的包直接 "Package info is null" 装不上。
    而我们只需要删掉 manifest 里的几十个元素 —— 犯不着把整个资源表重编一遍。

原理 (AXML 是分块结构):
    RES_XML
      |-- StringPool      <- 元素流之前, 删除元素不影响它
      |-- ResourceMap     <- 同上
      `-- 元素流: START_NAMESPACE / START_ELEMENT / END_ELEMENT / END_NAMESPACE
    所以只需: 摘掉目标元素的字节区间 + 修正外层 chunk 的 size 字段。
    字符串池里的旧字符串原样留着 (不引用了而已), 零风险。

用法:
    axml_strip.py <AndroidManifest.xml> [-o 输出] [--dry-run]
"""
import argparse
import struct
import sys
from pathlib import Path

RES_XML_TYPE = 0x0003
RES_STRING_POOL_TYPE = 0x0001
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103

COMPONENT_TAGS = {"activity", "activity-alias", "service", "receiver", "provider"}

AD_PREFIXES = (
    "com.qq.e.", "com.kwad.", "com.bytedance.", "com.byazt.", "com.pangle.",
    "com.baidu.mobads.", "com.sigmob.", "com.mobads.", "com.beizi.",
    "com.octopus.", "com.ss.android.", "ms.bz.bd.", "com.octet.",
)

TYPE_STRING = 0x03


class StringPool:
    """只读的 AXML 字符串池 (UTF-8 / UTF-16 都支持)."""

    def __init__(self, data: bytes, off: int):
        (_type, hdr, _size, count, _styles, flags,
         strings_start, _styles_start) = struct.unpack_from("<HHIIIIII", data, off)
        self.data = data
        self.base = off + strings_start
        self.offsets = [struct.unpack_from("<I", data, off + hdr + 4 * i)[0]
                        for i in range(count)]
        self.utf8 = bool(flags & 0x100)

    def __getitem__(self, idx: int) -> str:
        p = self.base + self.offsets[idx]
        d = self.data
        if self.utf8:
            n = d[p]
            p += 2 if n & 0x80 else 1          # 高位置1表示后面跟2字节长度
            ln = d[p]
            p += 2 if ln & 0x80 else 1
            return d[p:p + ln].decode("utf-8", "replace")
        n = struct.unpack_from("<H", d, p)[0]
        p += 4 if n & 0x8000 else 2
        return d[p:p + n * 2].decode("utf-16-le", "replace")


def chunk_header(data: bytes, off: int):
    return struct.unpack_from("<HHI", data, off)


def scan(pool: StringPool, data: bytes, start: int, end: int):
    """产出 (tag, 起始字节, 结束字节, {属性名: 字符串值})."""
    off = start
    stack = []
    while off + 8 <= end:
        ctype, _hdr, csize = chunk_header(data, off)
        if csize <= 0:
            break
        if ctype == RES_XML_START_ELEMENT_TYPE:
            # ResXMLTree_node(16) + ns(4) + name(4) + attrExt(attributeStart@24,
            # attributeSize@26, attributeCount@28, ...)
            name_idx = struct.unpack_from("<I", data, off + 20)[0]
            a_start, a_size, a_count = struct.unpack_from("<HHH", data, off + 24)
            ap = off + 16 + a_start
            attrs = {}
            for i in range(a_count):
                a_off = ap + i * a_size
                _a_ns, a_name, _raw = struct.unpack_from("<III", data, a_off)
                _v_size, _r0, v_type, v_data = struct.unpack_from("<HBBI", data, a_off + 12)
                if v_type == TYPE_STRING:
                    attrs[pool[a_name]] = pool[v_data]
            stack.append((pool[name_idx], off, attrs))
        elif ctype == RES_XML_END_ELEMENT_TYPE:
            if stack:
                tag, so, attrs = stack.pop()
                yield tag, so, off + csize, attrs
        off += csize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--drop-permission", action="append", default=[],
                    help="要摘除的 uses-permission 名字 (可重复)。"
                         "只在元素流里删声明, 不碰字符串池。")
    args = ap.parse_args()

    data = args.manifest.read_bytes()
    root_type, _root_hdr, root_size = chunk_header(data, 0)
    assert root_type == RES_XML_TYPE, f"不是 AXML (type=0x{root_type:04x})"

    off = 8
    pool = None
    while off < root_size:
        ctype, _hdr, csize = chunk_header(data, off)
        if ctype == RES_STRING_POOL_TYPE:
            pool = StringPool(data, off)
            off += csize
            break
        off += csize
    if pool is None:
        raise SystemExit("找不到字符串池")

    elems = list(scan(pool, data, off, root_size))

    def is_ad(v):
        return bool(v) and v.startswith(AD_PREFIXES)

    kill = set()

    # 第一步之前: 按名单摘除 uses-permission。
    # 只删 manifest 里的声明 —— 这样系统在安装时就不会把它列给用户,
    # 也不会在运行期弹出授权框。App 代码若调用需要该权限的 API, 会直接拿到
    # 拒绝 (SecurityException 或被 try 捕获), 而不是"静默拿到权限"。
    if args.drop_permission:
        want = set(args.drop_permission)
        for i, (tag, _s, _e, attrs) in enumerate(elems):
            if tag == "uses-permission" and attrs.get("name") in want:
                kill.add(i)

    # 第一步: 类名本身就是广告 SDK 的组件
    for i, (tag, _s, _e, attrs) in enumerate(elems):
        if tag in COMPONENT_TAGS and is_ad(attrs.get("name")):
            kill.add(i)

    # 第二步: 消除悬空引用。
    # 关键教训: <activity-alias> 的 android:name 常常是**宿主自己的包名**
    # (例: com.app.yxcds.zy.yz.kwad.KwadHandlerActivity), 按名字永远匹配不到广告前缀,
    # 但它的 android:targetActivity 指向的广告 Activity 已经被删了 ——
    # Android 会因此判定 INSTALL_PARSE_FAILED_MANIFEST_MALFORMED。
    # 所以凡是 target 已不存在 (或本身是广告) 的 alias 一并摘掉, 迭代到稳定。
    while True:
        alive = {attrs.get("name") for i, (tag, _s, _e, attrs) in enumerate(elems)
                 if tag == "activity" and i not in kill}
        added = False
        for i, (tag, _s, _e, attrs) in enumerate(elems):
            if i in kill or tag != "activity-alias":
                continue
            tgt = attrs.get("targetActivity")
            if tgt and (is_ad(tgt) or tgt not in alive):
                kill.add(i)
                added = True
        if not added:
            break

    ranges = [(s, e, tag, attrs.get("name") or attrs.get("targetActivity"))
              for i, (tag, s, e, attrs) in enumerate(elems) if i in kill]

    if not ranges:
        print("没有匹配到广告组件 (可能已处理过)")
        return 0

    ranges.sort()
    merged = []
    for s, e, tag, value in ranges:
        if merged and s < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2].append((tag, value))
        else:
            merged.append([s, e, [(tag, value)]])

    cut = sum(e - s for s, e, _ in merged)
    print(f"摘除 {len(ranges)} 个广告组件 (合并为 {len(merged)} 段, 共 {cut} 字节):")
    for _s, _e, items in merged:
        for tag, value in items:
            print(f"   - <{tag}> {value}")
    print(f"文件 {len(data)} -> {len(data) - cut} 字节")

    if args.dry_run:
        return 0

    out = bytearray()
    prev = 0
    for s, e, _ in merged:
        out += data[prev:s]
        prev = e
    out += data[prev:]
    struct.pack_into("<I", out, 4, len(out))          # 修正 RES_XML chunk size

    dest = args.out or args.manifest
    dest.write_bytes(bytes(out))
    print(f"已写回 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
