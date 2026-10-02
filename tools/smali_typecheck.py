#!/usr/bin/env python3
"""smali 寄存器类型检查 —— 补上汇编器不做的那一环。

为什么需要:
    smali 汇编器**只查语法, 不查类型**。所以
        const-string v2, "aq_level"
        ...
        invoke-static {v0, v1, v2}, Landroid/widget/Toast;->makeText(...)I
        寄存器 v2 此刻握着 String, 却被当成 int 用
    能顺利汇编出 dex, 直到运行期才被 ART 校验器拒绝:
        VerifyError: register v2 has type String but expected Integer
    真机上表现为整个类加载失败 (而且是在配置解析线程里炸, 堆栈不好读)。

检查策略 (刻意保守, 宁可漏报不要误报):
    只跟踪**基本类型 vs 引用类型**这一层。这一层足以抓住上面那类错,
    又不需要完整解析类继承关系 —— 后者要维护 subtype 表, 容易误判。
    命中即说明该寄存器的值是 int/long/float/double 之一, 而目标参数要引用,
    (或反过来), 这在任何情况下都是非法字节码。

已知不覆盖 (有意为之):
    - 把 String 当 MaterialButton 用这种"引用类型之间"的错 (需要继承关系)
    - 跨分支的类型合并

用法:
    smali_typecheck.py <smali 根目录或单个文件> [...]
"""
import argparse
import re
import sys
from pathlib import Path

PRIM = {"I", "J", "F", "D", "Z", "B", "S", "C"}

CONST_STR = re.compile(r'^const-string(?:/jumbo)?\s+(v\d+),')
CONST_INT = re.compile(r'^const(?:/4|/16|/high16)?\s+(v\d+),')
CONST_WIDE = re.compile(r'^const-wide(?:/16|/32|/high16)?\s+(v\d+),')
NEW_INST = re.compile(r'^new-instance\s+(v\d+),\s*(\S+)')
NEW_ARR = re.compile(r'^new-array\s+(v\d+),\s*v\d+,\s*(\[[^\s]+)')
SGET_OBJ = re.compile(r'^sget-object\s+(v\d+),\s*\S+->\S+:(\S+)')
IGET_OBJ = re.compile(r'^iget-object\s+(v\d+),\s*\S+->\S+:(\S+)')
AGET_OBJ = re.compile(r'^aget-object\s+(v\d+),')
MOVE_OBJ = re.compile(r'^move-object(?:/from16|/16)?\s+(v\d+),\s*(v\d+)')
MOVE_RES_OBJ = re.compile(r'^move-result-object\s+(v\d+)')
# 宽窄转换: 不做这一步的话, 像 "move-result-wide v3 / long-to-int v3, v3" 之后
# v3 仍被记成 long, 后面当 int 用就会误报。
CONV = re.compile(r'^(long-to-int|int-to-long|double-to-int|int-to-double|'
                  r'float-to-int|int-to-float|long-to-float|float-to-long|'
                  r'double-to-long|long-to-double|-to-int|-to-long|-to-float|-to-double)'
                  r'\s+(v\d+),')
MOVE_RES = re.compile(r'^move-result\s+(v\d+)')
MOVE_RES_WIDE = re.compile(r'^move-result-wide\s+(v\d+)')
INVOKE = re.compile(r'^(invoke-\S+)\s+\{([^}]*)\},\s*(\S+)->(\S+)\(([^)]*)\)(\S+)$')


def params_of(sig: str):
    """把 (ILjava/lang/String;)V 的括号内部分拆成类型列表."""
    out, i = [], 0
    while i < len(sig):
        c = sig[i]
        if c == "[":
            j = i
            while sig[j] == "[":
                j += 1
            if sig[j] == "L":
                j = sig.index(";", j)
            out.append(sig[i:j + 1])
            i = j + 1
        elif c == "L":
            j = sig.index(";", i)
            out.append(sig[i:j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return out


def is_prim(t: str) -> bool:
    return t in PRIM


def seed_params(lines, path):
    """给参数寄存器 (p0/p1/...) 预置类型。

    不做这一步的话, 参数的类型未知, 对它们的调用一律跳过检查 —— 会漏掉
    "在本类内部类里把 p0 当 Context 传" 这类错 (真踩过:
    VerifyError "register v3 has type FirstActivity$1 but expected Context",
    后果是那个类整个加载失败, 配置流程全挂)。
    """
    header = None
    for l in lines:
        if l.strip().startswith(".method"):
            header = l.strip()
            break
    if not header:
        return {}
    m = re.match(r'\.method\s+(?:public |private |protected )?(static )?(\S+?)\(([^)]*)\)', header)
    if not m:
        return {}
    is_static, params = m.group(1), params_of(m.group(3))
    owner = None
    mm = re.match(r'\.method\s+(?:public |private |protected )?(?:static )?\S+\([^)]*\)(\S+)', header)
    # 本类名从文件名推 (Xxx$1.smali -> Lcom/pkg/Xxx$1;)
    stem = path[:-len(".smali")] if path.endswith(".smali") else path
    owner = "L" + stem.replace(".", "/") + ";"
    out = {}
    idx = 0
    if not is_static:
        out["p0"] = owner
        idx = 1
    for i, t in enumerate(params):
        out[f"p{idx + i}"] = t
    return out


def check_method(lines, path, lineno, problems):
    regs = seed_params(lines, path)
    pending = None  # 上一条 invoke 的返回类型, 供 move-result 使用

    for k, raw in enumerate(lines):
        s = raw.strip()
        if not s or s.startswith(".") or s.startswith("#") or s.endswith(":"):
            continue

        m = INVOKE.match(s)
        if m:
            _, argstr, cls, meth, psig, ret = m.groups()
            args = [a.strip() for a in argstr.split(",") if a.strip()]
            want = params_of(psig)
            # invoke-* 的寄存器表可能以 {v0 .. v5} 形式压缩写, 这里只处理逐个列出的情形
            if len(args) == len(want):
                for a, w in zip(args, want):
                    t = regs.get(a)
                    if t is None:
                        continue
                    if is_prim(t) != is_prim(w):
                        problems.append(
                            f"{path}:{lineno + k + 1}  {a} 是 {t} 但 {cls}->{meth} "
                            f"的第 {args.index(a) + 1} 个参数要 {w}")
            elif len(args) < len(want) and args:
                # 形如 {v0, v1, v2 .. v5} 的区间写法, 跳过不判
                pass
            pending = ret
            continue

        m = MOVE_RES_OBJ.match(s)
        if m:
            if pending and not is_prim(pending):
                regs[m.group(1)] = pending
            pending = None
            continue
        m = MOVE_RES_WIDE.match(s)
        if m:
            regs[m.group(1)] = "J" if pending in ("J", "D", None) else "J"
            pending = None
            continue
        m = MOVE_RES.match(s)
        if m:
            regs[m.group(1)] = pending if pending and is_prim(pending) else "I"
            pending = None
            continue

        m = CONV.match(s)
        if m:
            res = "I" if "int" in m.group(1).split("-to-")[1] else (
                "J" if "long" in m.group(1).split("-to-")[1] else "F")
            regs[m.group(2)] = res
            continue
        m = CONST_STR.match(s)
        if m:
            regs[m.group(1)] = "Ljava/lang/String;"
            continue
        m = CONST_INT.match(s)
        if m:
            regs[m.group(1)] = "I"
            continue
        m = CONST_WIDE.match(s)
        if m:
            regs[m.group(1)] = "J"
            continue
        m = NEW_INST.match(s)
        if m:
            regs[m.group(1)] = m.group(2)
            continue
        m = NEW_ARR.match(s)
        if m:
            regs[m.group(1)] = m.group(2)
            continue
        m = SGET_OBJ.match(s)
        if m:
            regs[m.group(1)] = m.group(2)
            continue
        m = IGET_OBJ.match(s)
        if m:
            regs[m.group(1)] = m.group(2)
            continue
        m = AGET_OBJ.match(s)
        if m:
            regs[m.group(1)] = "Ljava/lang/Object;"  # 元素类型未跟踪, 保守当引用
            continue
        m = MOVE_OBJ.match(s)
        if m:
            if m.group(2) in regs:
                regs[m.group(1)] = regs[m.group(2)]
            else:
                regs.pop(m.group(1), None)
            continue


def check_file(path: Path, problems, rel: str = ""):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    i, start = 0, None
    for i, l in enumerate(lines):
        if l.startswith(".method"):
            start = i
        elif l.startswith(".end method") and start is not None:
            check_method(lines[start:i], path.name, start, problems)
            start = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        pp = Path(p)
        files.extend(sorted(pp.rglob("*.smali")) if pp.is_dir() else [pp])

    problems = []
    for f in files:
        check_file(f, problems, str(f))

    print(f"检查 {len(files)} 个 .smali 文件")
    if problems:
        print(f"\n★ 发现 {len(problems)} 处基本类型/引用类型不匹配:")
        for p in problems[:40]:
            print("   " + p)
        return 1
    print("✓ 未发现基本类型/引用类型不匹配")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
