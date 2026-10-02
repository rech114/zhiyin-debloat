#!/usr/bin/env python3
"""resources.arsc 字符串池改写 —— 用于改资源字符串 (如 app_name).

为什么需要专门写:
    改资源字符串的值 = 改字符串池里的一条 entry。新值长度通常和旧值不同,
    于是池的数据区变长, 后面所有条目的偏移都要跟着挪, 还要修正:
        - 池的 size
        - stylesStart (样式区在字符串数据之后)
        - RES_TABLE 的 size (它包着池和所有 package chunk)
    不能当成普通的字节替换来做。

不需要处理的:
    - 各条目的 offset 数组本身位置不变 (它紧跟在池头之后)
    - stringsStart 不变 (= headerSize + 4*count + 4*styleCount)
    - package chunk 内部的偏移都是相对自身起点的, 整块平移不受影响
    - 池不是 SORTED 时无需重排

用法:
    arsc_rename.py <resources.arsc> --replace "旧=A新" [-o 输出] [--dry-run]
"""
import argparse
import struct
from pathlib import Path


def read_str(data: bytes, off: int, utf8: bool):
    """读池里一条 entry, 返回 (字符串, 下一条目起点). 支持 UTF-8 / UTF-16 两种编码."""
    p = off
    if utf8:
        n = data[p]
        p += 2 if n & 0x80 else 1
        ln = data[p]
        p += 2 if ln & 0x80 else 1
        return data[p:p + ln].decode("utf-8", "replace"), p + ln + 1
    w = struct.unpack_from("<H", data, p)[0]
    if w & 0x8000:
        n = ((w & 0x7FFF) << 16) | struct.unpack_from("<H", data, p + 2)[0]
        p += 4
    else:
        n = w
        p += 2
    return data[p:p + n * 2].decode("utf-16-le", "replace"), p + n * 2 + 2


def write_str(s: str, utf8: bool) -> bytes:
    """拼一条 entry. UTF-8 时字符数与字节数各自编码; UTF-16 时长度为字符数."""
    if utf8:
        b = s.encode("utf-8")
        if len(s) > 0x7FFF or len(b) > 0x7FFF:
            raise ValueError(f"字符串过长: {len(s)} 字符 / {len(b)} 字节")

        def enc(n: int) -> bytes:
            return bytes([n]) if n <= 0x7F else bytes([0x80 | (n >> 8), n & 0xFF])

        return enc(len(s)) + enc(len(b)) + b + b"\x00"
    b = s.encode("utf-16-le")
    n = len(b) // 2
    if n > 0x7FFFFFFF:
        raise ValueError("字符串过长")
    if n > 0x7FFF:
        head = struct.pack("<HH", 0x8000 | (n >> 16), n & 0xFFFF)
    else:
        head = struct.pack("<H", n)
    return head + b + b"\x00\x00"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arsc", type=Path)
    ap.add_argument("--replace", action="append", default=[], help="旧=新 (精确匹配)")
    ap.add_argument("--replace-prefix", action="append", default=[],
                    help="旧前缀=新前缀 (用于包名: authorities / 权限名都是 getPackageName() 派生的)")
    ap.add_argument("--package-name", help="改 resources.arsc 里 ResTable_package 的包名 (固定 256 字节字段)")
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repl = {}
    for item in args.replace:
        o, _, n = item.partition("=")
        repl[o] = n
    prefixes = []
    for item in args.replace_prefix:
        o, _, n = item.partition("=")
        prefixes.append((o, n))

    def mapped(val: str):
        if val in repl:
            return repl[val]
        for o, n in prefixes:
            if val.startswith(o):
                return n + val[len(o):]
        return None

    data = bytearray(args.arsc.read_bytes())
    t_type, t_hdr, table_size = struct.unpack_from("<HHI", data, 0)
    # RES_TABLE(0x0002) 头 12 字节 / RES_XML(0x0003, 即 AndroidManifest) 头 8 字节,
    # 两者都是"池紧随头部", 所以直接取 headerSize 即可通用。
    if t_type not in (0x0002, 0x0003):
        raise SystemExit(f"不认识的文件类型 0x{t_type:04x} (预期 RES_TABLE 或 RES_XML)")
    pool_off = t_hdr
    ptype, phdr, psize = struct.unpack_from("<HHI", data, pool_off)
    if ptype != 0x0001:
        raise SystemExit(f"第一个 chunk 不是字符串池 (type=0x{ptype:04x})")
    ent_cnt, style_cnt, flags, sstart, ystart = struct.unpack_from(
        "<IIIII", data, pool_off + 8)
    utf8 = bool(flags & 0x100)
    print(f"字符串池: count={ent_cnt} styles={style_cnt} size={psize} "
          f"stringsStart={sstart} stylesStart={ystart} 编码={'UTF-8' if utf8 else 'UTF-16'}")

    base = pool_off + sstart
    offs = [struct.unpack_from("<I", data, pool_off + phdr + 4 * k)[0]
            for k in range(ent_cnt)]
    # 字符串数据区的终点: 有 styles 时是 stylesStart, 没有时就是池末尾。
    # (踩过: styleCount=0 时 stylesStart 恒为 0, 拿它当终点会算出负数区间)
    data_end = (ystart if style_cnt else psize) - sstart
    ends = offs[1:] + [data_end]

    # 只改命中的那几条, 其余条目字节原样保留 ——
    # 全量重编码会因编码形态差异导致池体积莫名变化 (踩过: 少了 9956 字节),
    # 而"就地拼接"只动目标条目, 差异完全可预期。
    hits = []
    for k in range(ent_cnt):
        s, _ = read_str(bytes(data), base + offs[k], utf8)
        n = mapped(s)
        if n is not None:
            # 新旧值在第一遍就取好: 拼接阶段 offs 会被平移, 那时再回读会读到错位的串
            hits.append((k, s, n))
    if not hits:
        print("没有匹配到要替换的字符串")
        return 1

    blob = bytearray(data[base + offs[0]: base + ends[-1]])
    shift = 0
    for k, old_s, new_s in hits:
        new_bytes = write_str(new_s, utf8)
        old_len = ends[k] - offs[k]
        # offs[k] 在之前的迭代里已经按累计位移改过了, 这里**不能再加 shift**,
        # 否则从第二个命中开始位置就会多平移一次 (踩过: 25 条只改对 24 条)
        st = offs[k]
        blob[st: st + old_len] = new_bytes
        d = len(new_bytes) - old_len
        shift += d
        print(f"  #{k}  {old_s!r} -> {new_s!r}  "
              f"({old_len}B -> {len(new_bytes)}B, {d:+d})")
        # 该条之后的所有条目偏移都平移
        for j in range(k + 1, ent_cnt):
            offs[j] += d
        ends = [e + d if i >= k else e for i, e in enumerate(ends)]

    new_sstart = sstart
    # 池的 size 必须 4 字节对齐 —— AAPT 会以 "not on an integer boundary" 拒绝非对齐的池。
    # 改一名字符串常导致 +1/-1 这类破坏对齐的位移, 所以在字符串数据区末尾补 padding 补回来。
    pad = (-(psize + shift)) % 4
    if pad:
        print(f"补 {pad} 字节 padding 以保持 4 字节对齐")
        blob += b"\x00" * pad
        shift += pad
    # stylesStart 只在真有 styles 时才有意义
    new_ystart = (ystart + shift) if style_cnt else 0
    new_psize = psize + shift
    assert new_psize % 4 == 0, new_psize
    print(f"池: {psize} -> {new_psize} B ({shift:+d}); "
          f"stylesStart {ystart} -> {new_ystart}")

    if args.dry_run:
        return 0

    new_pool = bytearray()
    new_pool += struct.pack("<HHI", ptype, phdr, new_psize)
    new_pool += struct.pack("<IIIII", ent_cnt, style_cnt, flags, new_sstart, new_ystart)
    for o in offs:
        new_pool += struct.pack("<I", o)
    # 池结构 = 头 + 字符串偏移表 + 样式偏移表 + 字符串数据 + 样式数据
    # 样式偏移表容易被漏掉 (它和 stringsStart 的算法里那 4*styleCount 是同一段)
    new_pool += data[pool_off + phdr + 4 * ent_cnt:
                     pool_off + phdr + 4 * ent_cnt + 4 * style_cnt]
    new_pool += blob
    if style_cnt:
        new_pool += data[pool_off + ystart: pool_off + psize]
    assert len(new_pool) == new_psize, (len(new_pool), new_psize)

    out = bytearray()
    out += data[:pool_off]
    out += new_pool
    out += data[pool_off + psize:]
    struct.pack_into("<I", out, 4, table_size + shift)   # size 字段恒在偏移 4

    # ResTable_package 的包名是**定长 256 字节 UTF-16** 字段, 直接覆盖 + 补零, 长度不变。
    if args.package_name:
        nb = args.package_name.encode("utf-16-le") + b"\x00\x00"
        assert len(nb) <= 256, "包名超过 127 字符"
        pb = pool_off + new_psize
        done = 0
        while pb + 8 <= len(out):
            ct, ch, cs = struct.unpack_from("<HHI", out, pb)
            if cs <= 0:
                break
            if ct == 0x0200:
                out[pb + 12: pb + 12 + 256] = nb.ljust(256, b"\x00")
                done += 1
            pb += cs
        print(f"  包名字段已改写 {done} 处 -> {args.package_name}")
        assert done == 1, f"预期 1 个 package chunk, 实际 {done}"

    dest = args.out or args.arsc
    dest.write_bytes(bytes(out))
    print(f"已写回 {dest}  ({len(data)} -> {len(out)} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
