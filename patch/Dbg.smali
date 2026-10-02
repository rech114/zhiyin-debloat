.class public Ldbg/Dbg;
.super Ljava/lang/Object;
.source "Dbg.java"

# 注入用日志类。
# 输出格式:  HH:mm:ss.SSS  文本
# 路径解析:  优先进程启动时用 getExternalFilesDir(null) 拿到的真实沙箱路径,
#            失败才回退到 PATHS 里的硬编码路径。
# 任何异常都吞掉, 绝不影响宿主 App。

.field private static final PATHS:[Ljava/lang/String;

.field private static FILE:Ljava/lang/String;


.method static constructor <clinit>()V
    .registers 4

    const-string v0, "/storage/emulated/0/Android/data/com.app.yxcds.zy.yz/files/debug.log"

    const-string v1, "/sdcard/Android/data/com.app.yxcds.zy.yz/files/debug.log"

    const-string v2, "/storage/emulated/0/MusicDebug/debug.log"

    filled-new-array {v0, v1, v2}, [Ljava/lang/String;

    move-result-object v3

    sput-object v3, Ldbg/Dbg;->PATHS:[Ljava/lang/String;

    return-void
.end method


# ---------- 时间戳 HH:mm:ss.SSS ----------
.method private static ts()Ljava/lang/String;
    .registers 4

    :try_start
    new-instance v0, Ljava/text/SimpleDateFormat;

    const-string v1, "HH:mm:ss.SSS"

    invoke-direct {v0, v1}, Ljava/text/SimpleDateFormat;-><init>(Ljava/lang/String;)V

    new-instance v1, Ljava/util/Date;

    invoke-direct {v1}, Ljava/util/Date;-><init>()V

    invoke-virtual {v0, v1}, Ljava/text/SimpleDateFormat;->format(Ljava/util/Date;)Ljava/lang/String;

    move-result-object v0
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    return-object v0

    :catch
    move-exception v0

    const-string v0, "--:--:--.---"

    return-object v0
.end method


# ---------- 启动时解析真实路径 ----------
.method public static init(Landroid/content/Context;)V
    .registers 4

    :try_start
    const/4 v0, 0x0

    invoke-virtual {p0, v0}, Landroid/content/Context;->getExternalFilesDir(Ljava/lang/String;)Ljava/io/File;

    move-result-object v0

    if-nez v0, :dbg_done

    invoke-virtual {v0}, Ljava/io/File;->mkdirs()Z

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v0}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v2, "/debug.log"

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    sput-object v1, Ldbg/Dbg;->FILE:Ljava/lang/String;
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    :dbg_done
    return-void

    :catch
    move-exception v0

    return-void
.end method


# ---------- 往一个路径追加一行 ----------
.method private static writeTo(Ljava/lang/String;Ljava/lang/String;)Z
    .registers 6

    :try_start
    new-instance v0, Ljava/io/File;

    invoke-direct {v0, p0}, Ljava/io/File;-><init>(Ljava/lang/String;)V

    invoke-virtual {v0}, Ljava/io/File;->getParentFile()Ljava/io/File;

    move-result-object v1

    if-eqz v1, :dbg_mk

    invoke-virtual {v1}, Ljava/io/File;->exists()Z

    move-result v2

    if-nez v2, :dbg_mk

    invoke-virtual {v1}, Ljava/io/File;->mkdirs()Z

    :dbg_mk
    new-instance v1, Ljava/io/FileOutputStream;

    const/4 v2, 0x1

    invoke-direct {v1, v0, v2}, Ljava/io/FileOutputStream;-><init>(Ljava/io/File;Z)V

    new-instance v0, Ljava/io/OutputStreamWriter;

    invoke-direct {v0, v1}, Ljava/io/OutputStreamWriter;-><init>(Ljava/io/OutputStream;)V

    invoke-virtual {v0, p1}, Ljava/io/OutputStreamWriter;->write(Ljava/lang/String;)V

    const-string v2, "\n"

    invoke-virtual {v0, v2}, Ljava/io/OutputStreamWriter;->write(Ljava/lang/String;)V

    invoke-virtual {v0}, Ljava/io/OutputStreamWriter;->flush()V

    invoke-virtual {v0}, Ljava/io/OutputStreamWriter;->close()V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    const/4 v0, 0x1

    return v0

    :catch
    move-exception v0

    const/4 v0, 0x0

    return v0
.end method


# ---------- 写一行 (自动加时间戳) ----------
.method public static log(Ljava/lang/String;)V
    .registers 6

    :try_start
    invoke-static {}, Ldbg/Dbg;->ts()Ljava/lang/String;

    move-result-object v0

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v0, "  "

    invoke-virtual {v1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    sget-object v0, Ldbg/Dbg;->FILE:Ljava/lang/String;

    if-eqz v0, :dbg_paths

    invoke-static {v0, p0}, Ldbg/Dbg;->writeTo(Ljava/lang/String;Ljava/lang/String;)Z

    move-result v0

    if-nez v0, :dbg_paths

    return-void

    :dbg_paths
    sget-object v0, Ldbg/Dbg;->PATHS:[Ljava/lang/String;

    const/4 v1, 0x0

    :dbg_loop
    array-length v2, v0

    if-ge v1, v2, :dbg_done

    aget-object v2, v0, v1

    invoke-static {v2, p0}, Ldbg/Dbg;->writeTo(Ljava/lang/String;Ljava/lang/String;)Z

    move-result v2

    if-eqz v2, :dbg_next

    return-void

    :dbg_next
    add-int/lit8 v1, v1, 0x1

    goto :dbg_loop

    :dbg_done
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    return-void

    :catch
    move-exception v0

    return-void
.end method


# ---------- tag | 值 ----------
.method public static log1(Ljava/lang/String;Ljava/lang/String;)V
    .registers 4

    :try_start
    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v0, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v1, " | "

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-static {v0}, Ldbg/Dbg;->log(Ljava/lang/String;)V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    return-void

    :catch
    move-exception v0

    return-void
.end method


# ---------- 纯文本一行 (mark 只是语义别名, 不再加装饰) ----------
.method public static mark(Ljava/lang/String;)V
    .registers 1

    invoke-static {p0}, Ldbg/Dbg;->log(Ljava/lang/String;)V

    return-void
.end method


# ---------- Throwable -> 堆栈 ----------
.method public static stack(Ljava/lang/Throwable;)Ljava/lang/String;
    .registers 3

    :try_start
    new-instance v0, Ljava/io/StringWriter;

    invoke-direct {v0}, Ljava/io/StringWriter;-><init>()V

    new-instance v1, Ljava/io/PrintWriter;

    invoke-direct {v1, v0}, Ljava/io/PrintWriter;-><init>(Ljava/io/Writer;)V

    invoke-virtual {p0, v1}, Ljava/lang/Throwable;->printStackTrace(Ljava/io/PrintWriter;)V

    invoke-virtual {v1}, Ljava/io/PrintWriter;->flush()V

    invoke-virtual {v0}, Ljava/io/StringWriter;->toString()Ljava/lang/String;

    move-result-object v0
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    return-object v0

    :catch
    move-exception v0

    const-string v0, "<stack unavailable>"

    return-object v0
.end method


# ---------- 安装未捕获异常处理器 ----------
.method public static installCrashHandler()V
    .registers 3

    :try_start
    invoke-static {}, Ljava/lang/Thread;->getDefaultUncaughtExceptionHandler()Ljava/lang/Thread$UncaughtExceptionHandler;

    move-result-object v0

    new-instance v1, Ldbg/Dbg$Crash;

    invoke-direct {v1, v0}, Ldbg/Dbg$Crash;-><init>(Ljava/lang/Thread$UncaughtExceptionHandler;)V

    invoke-static {v1}, Ljava/lang/Thread;->setDefaultUncaughtExceptionHandler(Ljava/lang/Thread$UncaughtExceptionHandler;)V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    return-void

    :catch
    move-exception v0

    return-void
.end method


# ---------- Object 安全转字符串 ----------
.method public static str(Ljava/lang/Object;)Ljava/lang/String;
    .registers 2

    :try_start
    invoke-static {p0}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v0
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :catch

    return-object v0

    :catch
    move-exception v0

    const-string v0, "<null>"

    return-object v0
.end method
