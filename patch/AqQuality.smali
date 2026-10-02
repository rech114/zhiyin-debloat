.class public Lcom/apertus/AqQuality;
.super Ljava/lang/Object;
.implements Landroid/view/View$OnLongClickListener;
.implements Landroid/content/DialogInterface$OnClickListener;
.source "AqQuality.java"

# 播放音质选择。
#
# 背景: 音质本来由服务端下发的 config 决定 (kugouParams / qqParams / wyyApi 里的 level 字段),
#       客户端只是原样发出去。这里在配置解析完成后统一改写这几个字段, 从而让音质可选。
#
# 取值必须用**实测确认有效**的:
#   酷狗  standard -> _qu128 (128k mp3) | exhigh -> _qu320 (320k mp3) | lossless -> _quflac (FLAC)
#   注意: 传其它任何值 (hq/sq/320k/2000k/flac) 服务端都**静默回落**到 _qu128, 不报错。
#   网易云 standard 5.0M | exhigh 12.4M | lossless 31.0M | jymaster 173M (实测文件大小)
# QQ    与酷狗同一解析服务, 取值相同。
# 酷我不在这里: 它的音质是 dex 里硬编码的模板 (br=48kaac), 未经实测不敢改。

.field public static final NAMES:[Ljava/lang/String;

.field private static final KG:[Ljava/lang/String;

.field private static final WYY:[Ljava/lang/String;

# 弹窗回调里拿不到 Context, 显示时先存一份。作用域是当前 Activity, 可接受。
.field private static CTX:Landroid/content/Context;

.field private static final KEY:Ljava/lang/String; = "aq_level"

.field private static final PREF:Ljava/lang/String; = "config"

.field private static final DEF:I = 0x1


.method static constructor <clinit>()V
    .locals 5

    const/4 v0, 0x4

    new-array v1, v0, [Ljava/lang/String;

    const/4 v2, 0x0

    const-string v3, "标准音质 (128k)"

    aput-object v3, v1, v2

    const/4 v2, 0x1

    const-string v3, "高音质 (320k)"

    aput-object v3, v1, v2

    const/4 v2, 0x2

    const-string v3, "无损音质 (FLAC)"

    aput-object v3, v1, v2

    const/4 v2, 0x3

    const-string v3, "母带音质 (仅网易云生效)"

    aput-object v3, v1, v2

    sput-object v1, Lcom/apertus/AqQuality;->NAMES:[Ljava/lang/String;

    new-array v1, v0, [Ljava/lang/String;

    const/4 v2, 0x0

    const-string v3, "standard"

    aput-object v3, v1, v2

    const/4 v2, 0x1

    const-string v3, "exhigh"

    aput-object v3, v1, v2

    const/4 v2, 0x2

    const-string v3, "lossless"

    aput-object v3, v1, v2

    const/4 v2, 0x3

    const-string v3, "lossless"

    aput-object v3, v1, v2

    sput-object v1, Lcom/apertus/AqQuality;->KG:[Ljava/lang/String;

    new-array v1, v0, [Ljava/lang/String;

    const/4 v2, 0x0

    const-string v3, "standard"

    aput-object v3, v1, v2

    const/4 v2, 0x1

    const-string v3, "exhigh"

    aput-object v3, v1, v2

    const/4 v2, 0x2

    const-string v3, "lossless"

    aput-object v3, v1, v2

    const/4 v2, 0x3

    const-string v3, "jymaster"

    aput-object v3, v1, v2

    sput-object v1, Lcom/apertus/AqQuality;->WYY:[Ljava/lang/String;

    return-void
.end method


# 读取已存档位; 没存过时返回 DEF 并在界面上提示一次
.method public static idx(Landroid/content/Context;)I
    .locals 3

    const-string v0, "config"

    const/4 v1, 0x0

    invoke-virtual {p0, v0, v1}, Landroid/content/Context;->getSharedPreferences(Ljava/lang/String;I)Landroid/content/SharedPreferences;

    move-result-object v0

    const-string v1, "aq_level"

    const/4 v2, 0x1

    invoke-interface {v0, v1, v2}, Landroid/content/SharedPreferences;->getInt(Ljava/lang/String;I)I

    move-result v0

    return v0
.end method


# 把存档位写回 config 的三个字段。幂等, 每次配置加载后调用。
.method public static apply(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V
    .locals 8

    # p1(配置对象) 为 null 才返回
    if-eqz p1, :ret

    # p0(Context) 为 null 才返回
    if-eqz p0, :ret

    invoke-virtual {p1}, Lcom/zhiyin/toolbox/bean/AppConfigBean;->getOtherConfig()Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;

    move-result-object v0

    if-eqz v0, :ret

    invoke-static {p0}, Lcom/apertus/AqQuality;->idx(Landroid/content/Context;)I

    move-result v1

    const/4 v2, 0x4

    if-ge v1, v2, :clamp_ok

    const/4 v1, 0x2

    :clamp_ok
    if-ltz v1, :ok

    const/4 v1, 0x0

    :ok
    sget-object v2, Lcom/apertus/AqQuality;->KG:[Ljava/lang/String;

    aget-object v2, v2, v1

    sget-object v3, Lcom/apertus/AqQuality;->WYY:[Ljava/lang/String;

    aget-object v3, v3, v1

    # ---- kugouParams:  "level":"xxx" -> "level":"<kg>" ----
    invoke-virtual {v0}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->getKugouParams()Ljava/lang/String;

    move-result-object v4

    if-eqz v4, :skip_kg

    const-string v5, "\"level\":\"[^\"]*\""

    invoke-static {v2}, Lcom/apertus/AqQuality;->sub(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v4, v5, v6}, Ljava/lang/String;->replaceAll(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v0, v4}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->setKugouParams(Ljava/lang/String;)V

    :skip_kg
    # ---- qqParams ----
    invoke-virtual {v0}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->getQqParams()Ljava/lang/String;

    move-result-object v4

    if-eqz v4, :skip_qq

    const-string v5, "\"level\":\"[^\"]*\""

    invoke-static {v2}, Lcom/apertus/AqQuality;->sub(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v4, v5, v6}, Ljava/lang/String;->replaceAll(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v0, v4}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->setQqParams(Ljava/lang/String;)V

    :skip_qq
    # ---- wyyApi:  level=xxx -> level=<wyy> ----
    invoke-virtual {v0}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->getWyyApi()Ljava/lang/String;

    move-result-object v4

    if-eqz v4, :ret

    const-string v5, "level=[^&]*"

    invoke-static {v3}, Lcom/apertus/AqQuality;->sub2(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v4, v5, v6}, Ljava/lang/String;->replaceAll(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v0, v4}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->setWyyApi(Ljava/lang/String;)V

    :ret
    return-void
.end method


# 拼 "level":"xxx" 的替换串 (免去目标串里的引号转义)
.method private static sub(Ljava/lang/String;)Ljava/lang/String;
    .locals 2

    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "\"level\":\""

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v1, "\""

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    return-object v0
.end method


# 拼 level=xxx 的替换串
.method private static sub2(Ljava/lang/String;)Ljava/lang/String;
    .locals 2

    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "level="

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    return-object v0
.end method


# 长按音量按钮 -> 弹音质选择
.method public onLongClick(Landroid/view/View;)Z
    .locals 5

    invoke-virtual {p1}, Landroid/view/View;->getContext()Landroid/content/Context;

    move-result-object v0

    sput-object v0, Lcom/apertus/AqQuality;->CTX:Landroid/content/Context;

    new-instance v1, Lcom/google/android/material/dialog/MaterialAlertDialogBuilder;

    invoke-direct {v1, v0}, Lcom/google/android/material/dialog/MaterialAlertDialogBuilder;-><init>(Landroid/content/Context;)V

    const-string v2, "播放音质"

    invoke-virtual {v1, v2}, Lcom/google/android/material/dialog/MaterialAlertDialogBuilder;->setTitle(Ljava/lang/CharSequence;)Lcom/google/android/material/dialog/MaterialAlertDialogBuilder;

    move-result-object v1

    sget-object v2, Lcom/apertus/AqQuality;->NAMES:[Ljava/lang/String;

    invoke-static {v0}, Lcom/apertus/AqQuality;->idx(Landroid/content/Context;)I

    move-result v3

    new-instance v4, Lcom/apertus/AqQuality;

    invoke-direct {v4}, Lcom/apertus/AqQuality;-><init>()V

    invoke-virtual {v1, v2, v3, v4}, Landroidx/appcompat/app/AlertDialog$Builder;->setSingleChoiceItems([Ljava/lang/CharSequence;ILandroid/content/DialogInterface$OnClickListener;)Landroidx/appcompat/app/AlertDialog$Builder;

    move-result-object v1

    const-string v2, "关闭"

    const/4 v3, 0x0

    invoke-virtual {v1, v2, v3}, Landroidx/appcompat/app/AlertDialog$Builder;->setNegativeButton(Ljava/lang/CharSequence;Landroid/content/DialogInterface$OnClickListener;)Landroidx/appcompat/app/AlertDialog$Builder;

    move-result-object v1

    invoke-virtual {v1}, Landroidx/appcompat/app/AlertDialog$Builder;->show()Landroidx/appcompat/app/AlertDialog;

    const/4 v0, 0x1

    return v0
.end method


# 选中即存档并立即生效 (对下一首生效; 当前已取到的直链不会变)
.method public onClick(Landroid/content/DialogInterface;I)V
    .locals 4
    # 寄存器角色: v0=Context  v1=对象(SP/Editor/字符串数组)  v2=String键  v3=int

    invoke-interface {p1}, Landroid/content/DialogInterface;->dismiss()V

    sget-object v0, Lcom/apertus/AqQuality;->CTX:Landroid/content/Context;

    if-eqz v0, :done

    const-string v1, "config"

    const/4 v2, 0x0

    invoke-virtual {v0, v1, v2}, Landroid/content/Context;->getSharedPreferences(Ljava/lang/String;I)Landroid/content/SharedPreferences;

    move-result-object v1

    invoke-interface {v1}, Landroid/content/SharedPreferences;->edit()Landroid/content/SharedPreferences$Editor;

    move-result-object v1

    const-string v2, "aq_level"

    invoke-interface {v1, v2, p2}, Landroid/content/SharedPreferences$Editor;->putInt(Ljava/lang/String;I)Landroid/content/SharedPreferences$Editor;

    move-result-object v1

    invoke-interface {v1}, Landroid/content/SharedPreferences$Editor;->apply()V

    sget-object v1, Lcom/zhiyin/toolbox/activity/FirstActivity;->config:Lcom/zhiyin/toolbox/bean/AppConfigBean;

    invoke-static {v0, v1}, Lcom/apertus/AqQuality;->apply(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V

    # 现在的档位名回显, 确认改到位了
    sget-object v1, Lcom/apertus/AqQuality;->NAMES:[Ljava/lang/String;

    aget-object v1, v1, p2

    # v2 上面装载的是 String 键名, 不能拿来当 Toast 时长 ——
    # 校验器会以 "register v2 has type String but expected Integer" 拒绝整个类 (真踩过)。
    # 这里另用 v3 放 int。
    const/4 v3, 0x0

    invoke-static {v0, v1, v3}, Landroid/widget/Toast;->makeText(Landroid/content/Context;Ljava/lang/CharSequence;I)Landroid/widget/Toast;

    move-result-object v1

    invoke-virtual {v1}, Landroid/widget/Toast;->show()V

    :done
    return-void
.end method
