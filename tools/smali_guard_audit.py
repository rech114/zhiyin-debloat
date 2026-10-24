#!/usr/bin/env python3
"""空值守卫极性检查 —— 专抓 if-eqz / if-nez 写反。

为什么需要:
    手写 smali 时把 "X 为 null 就返回" 写成 if-nez 是极易犯的错:
        if-nez v0, :ret      # 实际是 "v0 != 0 时跳" —— 参数非 null 反而直接返回
    后果不是崩溃, 而是**该方法的全部逻辑被静默跳过** ——
    外观上"功能没反应", 极难定位 (真踩过: 音质改写逻辑一次都没执行)。

判据 (只在这三种同时成立时才报):
    1. 指令是 if-nez vX, :L        (vX != 0 时跳走)
    2. :L 处紧接着就是 return-*     (跳走 = 提前返回)
    3. vX 的来源是"加载"而非"计算": sget-object / iget-object /
       move-result-object / 方法参数
    → 语义变成"参数非 null 就直接返回", 在业务代码里几乎不可能是有意的。

为什么可以当硬闸门:
    只在**我们自己写的**包 (com/apertus) 下启用。那里没有"已初始化就直接返回"
    这类合法早退, 所以命中即真错。作者原有代码不适用 (模式合法且量大)。

用法:
    smali_guard_audit.py <smali 根目录或单个文件> [...]
"""
import argparse
import re
import sys
from pathlib import Path

JUMP = re.compile(r'^\s*(if-[a-z]+)\s+(v\d+|p\d+),\s*(:\S+)')
LOADERS = (
    re.compile(r'^\s*sget-object\s+(v\d+),'),
    re.compile(r'^\s*iget-object\s+(v\d+),'),
    re.compile(r'^\s*move-result-object\s+(v\d+)'),
    # 基本类型的返回值也要算来源: 否则 "exists()Z -> move-result v / if-nez v, :ret"
    # 这种写反的守卫会被漏掉 (实测漏过一次)
    re.compile(r'^\s*move-result\s+(v\d+)'),
)
RET = re.compile(r'^\s*return(-void|-object|-wide)?\b')


def param_regs(method_line: str, nlocals: int):
    """把 .method 签名里的参数映射到寄存器名 (p0..pN)。"""
    m = re.search(r'\((.*)\)', method_line)
    if not m:
        return set()
    return {f"p{i}" for i in range(1, 1 + len(re.findall(r'\[|L[^;]*;|[IJFDZBCS]', m.group(1))))}


def check_method(lines, fname, base, problems):
    params = set()
    for l in lines[:4]:
        if l.strip().startswith(".method"):
            params = param_regs(l, 0)
    n = len(lines)
    for i, raw in enumerate(lines):
        m = JUMP.match(raw)
        if not m or m.group(1) != "if-nez":
            continue
        reg, label = m.group(2), m.group(3)
        # 目标标签处是否紧接着 return
        target = None
        for j in range(i + 1, n):
            if lines[j].strip() == label:
                target = j
                break
        if target is None:
            continue
        nxt = target + 1
        while nxt < n and (not lines[nxt].strip() or lines[nxt].strip().startswith((".line", ":"))):
            nxt += 1
        if nxt >= n or not RET.match(lines[nxt]):
            continue
        # 寄存器来源: 往前找最近一次赋值
        src = None
        for j in range(i - 1, max(-1, i - 30), -1):
            for pat in LOADERS:
                mm = pat.match(lines[j])
                if mm and mm.group(1) == reg:
                    src = "load"
                    break
            if src:
                break
            if re.match(r'^\s*(const|move|new-instance|aget|sget|iget|invoke)', lines[j]) and reg in lines[j]:
                src = "other"
                break
        if reg in params:
            src = "load"
        if src == "load":
            problems.append(
                f"{fname}:{base + i + 1}  if-nez {reg}, {label} —— {reg} 来自加载/参数, "
                f"跳走就 return, 等于\"非 null 直接返回\"。若本意是空值返回, 应为 if-eqz")


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

    print(f"检查 {len(files)} 个 .smali 文件的空值守卫极性")
    if problems:
        print(f"\n★ 发现 {len(problems)} 处可疑的反极性守卫:")
        for p in problems:
            print("   " + p)
        return 1
    print("✓ 未发现反极性空值守卫")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
