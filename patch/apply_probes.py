#!/usr/bin/env python3
"""给已打好补丁的 smali 树注入"验证探针".

用途: 生成既**已去变现、又写日志**的 verify 版, 一次安装同时验证修复效果与采集证据。
探针只做两件事: 在方法体开头打一行标记 + 必要时把 .registers 扩 1 给探针当临时寄存器,
不碰任何业务逻辑。

用法:
    apply_probes.py <smali 根目录>
"""
import re
import sys
from pathlib import Path

# 装未捕获异常处理器 —— 删广告 SDK 类之后, 失败模式只有"类链接失败",
# 静默闪退。装上它, 崩溃堆栈就会落到 debug.log 里, 直接点名缺失的类。
CRASH_HANDLER = ("\n    invoke-static {}, Ldbg/Dbg;->installCrashHandler()V\n")

# 必须最先执行: 用 Context 解析出真实的 Android/data/<pkg>/files 路径,
# 否则后面所有日志都写到硬编码路径上 (现代 Android 上那个目录可能还没被创建)。
INIT_PATHS = "    invoke-static {p0}, Ldbg/Dbg;->init(Landroid/content/Context;)V\n"

# 打印门禁方法收到的实参 —— 一眼看出到底哪个是 null
ARG_LOG = (
    '\n    const-string v2, "ARG-p0-context"\n\n'
    '    invoke-static {p0}, Ldbg/Dbg;->str(Ljava/lang/Object;)Ljava/lang/String;\n\n'
    '    move-result-object v3\n\n'
    '    invoke-static {v2, v3}, Ldbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V\n'
    '\n    const-string v2, "ARG-p1-item"\n\n'
    '    invoke-static {p1}, Ldbg/Dbg;->str(Ljava/lang/Object;)Ljava/lang/String;\n\n'
    '    move-result-object v3\n\n'
    '    invoke-static {v2, v3}, Ldbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V\n'
)

# (文件, 方法头正则, 原 .registers, 新 .registers, 标记文本, [额外注入指令], [前置指令])
PROBES = [
    ("com/zhiyin/toolbox/application/Application.smali",
     r"^\.method public onCreate\(\)V$",
     1, 2, "Application.onCreate", CRASH_HANDLER, INIT_PATHS),

    ("com/zhiyin/toolbox/utils/HJAdManager.smali",
     r"^\.method public ᛱᛱᛱᛱᛴ\(Landroid/app/Application;Ljava/lang/String;Z\)V$",
     4, 5, "PATCH OK > 广告 SDK 初始化已关停"),

    ("com/zhiyin/toolbox/utils/HJSplashAdHelper.smali",
     r"^\.method public ᛱᛱᛱᛱᤝ\(\)V$",
     2, 2, "PATCH OK > 开屏广告已旁路"),

    ("com/zhiyin/toolbox/utils/ForceAdManager.smali",
     r"^\.method public ᛱᛱᛱᛱᲇ\(Landroid/app/Activity;Ljava/lang/String;I"
     r"Lcom/zhiyin/toolbox/utils/ForceAdManager\$OnAdLockCallback;\)V$",
     5, 6, "PATCH OK > 限制弹窗已旁路(未弹窗)"),

    ("com/zhiyin/toolbox/utils/ToolAdHelper.smali",
     r"^\.method public static ᛱᛱᛱᛱᛲ\(Landroid/content/Context;"
     r"Lcom/zhiyin/toolbox/bean/tool/FunctionItem;"
     r"Lcom/zhiyin/toolbox/bean/AppConfigBean;I\)V$",
     6, 9, "PATCH OK > 工具门禁已旁路", ARG_LOG),
]


def inject(root: Path, file_: str, anchor: str, old_regs: int, new_regs: int, text: str,
           extra: str = "", pre: str = "") -> str:
    path = root / file_
    if not path.exists():
        return f"SKIP  文件不存在: {file_}"
    src = path.read_text(encoding="utf-8")
    m = re.search(anchor, src, re.MULTILINE)
    if not m:
        return f"SKIP  锚点未命中: {file_}"

    # 1) 方法头之后的第一条 .registers
    rm = re.search(r"^[ \t]*\.registers (\d+)[ \t]*$", src[m.end():], re.MULTILINE)
    if not rm:
        return f"SKIP  .registers 未找到: {file_}"
    if int(rm.group(1)) != old_regs:
        return f"SKIP  .registers 不是 {old_regs} (是 {rm.group(1)}), 可能已注入过"
    reg_start = m.end() + rm.start()
    reg_end = m.end() + rm.end()
    src = src[:reg_start] + f"    .registers {new_regs}" + src[reg_end:]

    # 2) 在 .registers 之后插入探针 (v0 是扩容后的本地寄存器, 此时必可用)
    at = reg_start + len(f"    .registers {new_regs}")
    probe = (f'\n{pre}\n    const-string v0, "{text}"\n\n'
             f"    invoke-static {{v0}}, Ldbg/Dbg;->mark(Ljava/lang/String;)V\n" + extra)
    path.write_text(src[:at] + probe + src[at:], encoding="utf-8")
    return f"OK    {text} -> {file_}"


TOOL_GUARD_OLD = """    new-instance v1, Lcom/hzhj/libs/ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ;

    invoke-direct {v1, p0, p1}, Lcom/hzhj/libs/ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ;-><init>(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/tool/FunctionItem;)V

    invoke-interface {v1}, Ljava/lang/Runnable;->run()V
"""

# 工具启动守卫: 把 v1.run() 整段包进 try/catch, 成功/失败/异常堆栈全部落日志。
# "点了没反应" 这类问题靠静态分析很难定位 (可能是 NoClassDefFoundError 被吞掉),
# 直接把真实异常打出来最快。
TOOL_GUARD_NEW = """    invoke-virtual {p1}, Lcom/zhiyin/toolbox/bean/tool/FunctionItem;->getName()Ljava/lang/String;

    move-result-object v0

    const-string v2, "TOOL-CLICK"

    invoke-static {v2, v0}, Ldbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V

    :try_start
    new-instance v1, Lcom/hzhj/libs/ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ;

    invoke-direct {v1, p0, p1}, Lcom/hzhj/libs/ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ;-><init>(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/tool/FunctionItem;)V

    const-string v2, "TOOL-LAUNCH-START"

    invoke-static {v2, v0}, Ldbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V

    invoke-interface {v1}, Ljava/lang/Runnable;->run()V

    const-string v2, "TOOL-LAUNCH-RETURNED"

    invoke-static {v2, v0}, LDbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :dbg_catch

    goto :debloat_ret

    :dbg_catch
    move-exception v3

    invoke-static {v3}, Ldbg/Dbg;->stack(Ljava/lang/Throwable;)Ljava/lang/String;

    move-result-object v3

    const-string v2, "TOOL-LAUNCH-THREW"

    invoke-static {v2, v3}, Ldbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V
"""


NULLCHECK_MARK_OLD = """    if-eqz p1, :debloat_ret

    if-nez p0, :debloat_ret
"""

# 分界标记: 放在两行判空之后、getName() 之前。
# 把两种可能彻底分开 ——
#   没看到 AFTER-NULLCHECK  -> 判空真的跳走了 (参数为 null)
#   看到 AFTER-NULLCHECK    -> 参数没问题, 是 getName() 自己抛异常
NULLCHECK_MARK_NEW = """    if-eqz p1, :debloat_ret

    if-nez p0, :debloat_ret

    const-string v2, "AFTER-NULLCHECK (参数都非空)"

    invoke-static {v2}, Ldbg/Dbg;->mark(Ljava/lang/String;)V
"""


def tool_launch_guard(root: Path) -> str:
    """给已打过门禁补丁的 ToolAdHelper 加启动守卫 (仅 debug 变体)."""
    path = root / "com/zhiyin/toolbox/utils/ToolAdHelper.smali"
    if not path.exists():
        return "SKIP  ToolAdHelper 不存在"
    text = path.read_text(encoding="utf-8")
    if TOOL_GUARD_OLD not in text:
        return "SKIP  未找到补丁后的门禁方法体"
    # 需要更多本地寄存器给守卫用: .registers 6 -> 8
    anchor = (r"^\.method public static ᛱᛱᛱᛱᛲ\(Landroid/content/Context;"
              r"Lcom/zhiyin/toolbox/bean/tool/FunctionItem;"
              r"Lcom/zhiyin/toolbox/bean/AppConfigBean;I\)V$")
    m = re.search(anchor, text, re.MULTILINE)
    if not m:
        return "SKIP  未找到门禁方法头"
    body = text[m.end():]
    rm = re.search(r"^[ \t]*\.registers (\d+)[ \t]*$", body, re.MULTILINE)
    if not rm:
        return "SKIP  .registers 未找到"
    cur = int(rm.group(1))
    body = body[:rm.start()] + f"    .registers {cur + 1}" + body[rm.end():]
    text = text[:m.end()] + body
    text = text.replace(TOOL_GUARD_OLD, TOOL_GUARD_NEW, 1)
    text = text.replace(NULLCHECK_MARK_OLD, NULLCHECK_MARK_NEW, 1)
    path.write_text(text, encoding="utf-8")
    return f"OK    工具启动守卫已注入 (.registers {cur} -> {cur + 1})"


# ---------------------------------------------------------------- 点击链逐环探针
# 只看到 "PATCH OK > 工具门禁已旁路" 却看不到后续, 说明链路在中途断了。
# 这里把从 View 点击到启动器的每一环都打上点, 一次定位断点。
CLICK_CHAIN = [
    # (文件, 方法头正则, 追加的标记)
    ("com/hzhj/libs/ᛱᛱᛳᛶᛵ/ᛱᛱᛱᛲᛲ.smali",
     r"^\.method public final onClick\(Landroid/view/View;\)V$",
     "CHAIN-1 工具胶囊的点击监听器被调用"),
    ("com/zhiyin/toolbox/adapter/ToolGroupAdapter.smali",
     r"^\.method public static synthetic ᛱᛱᛱᛱᛳ\(Landroid/content/Context;"
     r"Lcom/zhiyin/toolbox/bean/tool/FunctionItem;Landroid/view/View;\)V$",
     "CHAIN-2 适配器点击处理器被调用"),
]


def inject_mark(root: Path, file_: str, anchor: str, text: str) -> str:
    """在方法体最前面插一条 mark (不动寄存器: 用 v0 之前先保证 .registers 有余量)."""
    path = root / file_
    if not path.exists():
        return f"SKIP  文件不存在: {file_}"
    src = path.read_text(encoding="utf-8")
    m = re.search(anchor, src, re.MULTILINE)
    if not m:
        return f"SKIP  锚点未命中: {file_}"
    body = src[m.end():]
    rm = re.search(r"^[ \t]*\.registers (\d+)[ \t]*$", body, re.MULTILINE)
    if not rm:
        return f"SKIP  .registers 未找到: {file_}"
    nlocals = int(rm.group(1))
    new_locals = nlocals + 1
    body = body[:rm.start()] + f"    .registers {new_locals}" + body[rm.end():]
    at = rm.start() + len(f"    .registers {new_locals}")
    probe = f'\n    const-string v0, "{text}"\n\n    invoke-static {{v0}}, Ldbg/Dbg;->mark(Ljava/lang/String;)V\n'
    path.write_text(src[:m.end()] + body[:at] + probe + body[at:], encoding="utf-8")
    return f"OK    {text} -> {file_}"


def main() -> int:
    root = Path(sys.argv[1])
    for p in PROBES:
        print(inject(root, *p))
    print(tool_launch_guard(root))
    for f, a, t in CLICK_CHAIN:
        print(inject_mark(root, f, a, t))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
