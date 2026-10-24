#!/usr/bin/env python3
"""smali 寄存器越界检查 —— 抓"把参数寄存器当局部变量用"。

为什么需要:
    smali 的 .registers N 是**总**寄存器数, 参数占据最后几个:
        .registers 6 + 2 个参数  ->  v0..v3 是局部, v4=p0, v5=p1
    如果补丁往 v4 写东西, 汇编器**不会报错**, 它会老老实实写进 p0 ——
    也就是把 `this` 覆盖成别的值, 后面再当对象用就抛 VerifyError。

    真实案例 (AboutActivity.initActivity, 3.7.0):
        .registers 6  (p0=this, p1=Bundle)
        补丁写了 const/16 v4, 0x8      <- v4 就是 p0
        结果 this 被改成整数 8, 打开"关于"页直接校验失败。

判据:
    逐行找 vN / pN 引用, 与 (.registers - 参数个数) 比较。
    vN 越界 或 pN 越界 即报错 (baksmali 本来就会把参数渲染成 pN,
    所以出现越界的 vN 一定是补丁写错了)。

用法:
    smali_regcheck.py <smali 根目录或文件> [...]
"""
import argparse
import re
import sys
from pathlib import Path

METHOD = re.compile(r'^\.method\s+(?:public |private |protected )?(static )?\S+\(([^)]*)\)')
REGS = re.compile(r'^\.registers\s+(\d+)')
VREF = re.compile(r'\bv(\d+)\b')
PREF = re.compile(r'\bp(\d+)\b')
# .registers 与 .locals 的区别: .locals 只数局部, 参数另算


def count_params(sig: str) -> int:
    """返回参数占用的**寄存器槽位数** —— long/double 占 2 个, 不是 1 个。
    (踩过: 按类型个数算, 导致 (J) 这种签名少算一个槽位, 误报 p2 越界)"""
    n, i = 0, 0
    while i < len(sig):
        c = sig[i]
        if c == '[':
            j = i
            while sig[j] == '[':
                j += 1
            if sig[j] == 'L':
                j = sig.index(';', j)
            i = j + 1
        elif c == 'L':
            i = sig.index(';', i) + 1
        else:
            i += 1
        n += 2 if c in 'JD' else 1
    return n


def check_method(lines, path, base, problems):
    header, nreg, nlocals = None, None, None
    for l in lines:
        s = l.strip()
        if s.startswith('.method'):
            header = s
        elif s.startswith('.registers'):
            m = REGS.match(s)
            if m:
                nreg = int(m.group(1))
        elif s.startswith('.locals'):
            m = re.match(r'\.locals\s+(\d+)', s)
            if m:
                nlocals = int(m.group(1))
    if header is None:
        return
    m = METHOD.match(header)
    if not m:
        return
    is_static = bool(m.group(1))
    npar = count_params(m.group(2)) + (0 if is_static else 1)
    if nreg is not None:
        loc = nreg - npar
    elif nlocals is not None:
        loc = nlocals
    else:
        return
    if loc < 0:
        problems.append(f"{path}:{base + 1}  .registers {nreg} 小于参数个数 {npar}")
        return
    for k, l in enumerate(lines):
        s = l.strip()
        if not s or s.startswith(('.', '#', ':')):
            continue
        for v in VREF.findall(s):
            if int(v) >= loc:
                problems.append(
                    f"{path}:{base + k + 1}  v{v} 越界: 该方法局部只有 v0..v{loc - 1}"
                    f" (总寄存器 {loc + npar}, 参数 {npar}) —— v{v} 实际是参数寄存器\n"
                    f"      {s[:92]}")
                break
        for p in PREF.findall(s):
            if int(p) >= npar:
                problems.append(
                    f"{path}:{base + k + 1}  p{p} 越界: 该方法只有 {npar} 个参数寄存器\n"
                    f"      {s[:92]}")
                break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        pp = Path(p)
        if pp.is_dir():
            files.extend(sorted(pp.rglob("*.smali")))
        elif pp.exists():
            files.append(pp)

    problems = []
    for f in files:
        lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        start = None
        for i, l in enumerate(lines):
            if l.startswith(".method"):
                start = i
            elif l.startswith(".end method") and start is not None:
                check_method(lines[start:i + 1], f.name, start, problems)
                start = None

    print(f"寄存器越界检查: {len(files)} 个文件")
    if problems:
        print(f"\n★ 发现 {len(problems)} 处越界:")
        for p in problems[:30]:
            print("   " + p)
        return 1
    print("✓ 未发现寄存器越界")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
