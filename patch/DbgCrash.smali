.class public Ldbg/Dbg$Crash;
.super Ljava/lang/Object;
.source "DbgCrash.java"

# 未捕获异常处理器。
# 用途: 删广告 SDK 类之后, 唯一可能的失败模式是 NoClassDefFoundError /
#      NoSuchMethodError —— 类还没执行就链接失败, 静默闪退。
#      本处理器把完整堆栈写进 debug.log, 直接点名是哪个类缺失。
# 行为: 记完日志后原样交回给原有的默认处理器, 不改变任何崩溃语义。

.implements Ljava/lang/Thread$UncaughtExceptionHandler;


.field private final prev:Ljava/lang/Thread$UncaughtExceptionHandler;


.method public constructor <init>(Ljava/lang/Thread$UncaughtExceptionHandler;)V
    .registers 2

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    iput-object p1, p0, Ldbg/Dbg$Crash;->prev:Ljava/lang/Thread$UncaughtExceptionHandler;

    return-void
.end method


.method public uncaughtException(Ljava/lang/Thread;Ljava/lang/Throwable;)V
    .registers 6

    :try_start
    const-string v0, "CRASH"

    invoke-static {p2}, Ldbg/Dbg;->stack(Ljava/lang/Throwable;)Ljava/lang/String;

    move-result-object v1

    invoke-static {v0, v1}, Ldbg/Dbg;->log1(Ljava/lang/String;Ljava/lang/String;)V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    goto :dbg_handoff

    :catch
    move-exception v0

    :dbg_handoff
    iget-object v0, p0, Ldbg/Dbg$Crash;->prev:Ljava/lang/Thread$UncaughtExceptionHandler;

    if-eqz v0, :dbg_done

    invoke-interface {v0, p1, p2}, Ljava/lang/Thread$UncaughtExceptionHandler;->uncaughtException(Ljava/lang/Thread;Ljava/lang/Throwable;)V

    :dbg_done
    return-void
.end method
