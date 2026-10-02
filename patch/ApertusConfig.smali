.class public Lcom/apertus/ApertusConfig;
.super Ljava/lang/Object;
.source "ApertusConfig.java"

# 配置本地兜底 + 强更中和。
#
# 背景: 原版每次启动都从网络取配置, **没有任何本地缓存**。作者的配置服务器一旦下线,
#       应用就卡在启动页进不去 —— 这是最直接的一个"远程开关"。
#
# 策略 (远程优先, 保持配置新鲜):
#   1. 每次成功取到远程配置 -> 立刻落盘覆盖 (save)
#   2. 远程取不到 -> 读本地兜底 (failover), 有就直接进主界面
#   3. 顺带中和 updateConfig: 把 latestVersion 设成**运行期已安装版本**,
#      forceUpdate 置空。这样各处的更新弹窗条件恒为假, 不用逐处拆弹窗。
#
# 存储用 App 已有的 SharedPreferences("config"), 不引入新文件。

.field private static final PREF:Ljava/lang/String; = "config"

.field private static final KEY:Ljava/lang/String; = "cfg_cache"

.field private static final MIN:I = 0x10


# 落盘。每次远程成功后调用, 覆盖旧值 -> 缓存始终跟着远程走。
.method public static save(Landroid/content/Context;Ljava/lang/String;)V
    .locals 3

    if-eqz p0, :ret

    if-eqz p1, :ret

    # 太短的响应多半是错误页, 不拿它覆盖好缓存
    invoke-virtual {p1}, Ljava/lang/String;->length()I

    move-result v1

    const/16 v2, 0x10

    if-ge v1, v2, :ret

    const-string v1, "config"

    const/4 v2, 0x0

    invoke-virtual {p0, v1, v2}, Landroid/content/Context;->getSharedPreferences(Ljava/lang/String;I)Landroid/content/SharedPreferences;

    move-result-object v1

    invoke-interface {v1}, Landroid/content/SharedPreferences;->edit()Landroid/content/SharedPreferences$Editor;

    move-result-object v1

    const-string v2, "cfg_cache"

    invoke-interface {v1, v2, p1}, Landroid/content/SharedPreferences$Editor;->putString(Ljava/lang/String;Ljava/lang/String;)Landroid/content/SharedPreferences$Editor;

    move-result-object v1

    invoke-interface {v1}, Landroid/content/SharedPreferences$Editor;->apply()V

    :ret
    return-void
.end method


# 远程失败时的兜底。成功返回 true (此时已跳到主界面, 调用方应直接 return)。
# navigateToMain() 是 private 调不到, 所以这里自己发 Intent。
.method public static failover(Lcom/zhiyin/toolbox/activity/FirstActivity;)Z
    .locals 4

    if-eqz p0, :no

    const-string v0, "config"

    const/4 v1, 0x0

    invoke-virtual {p0, v0, v1}, Landroid/content/Context;->getSharedPreferences(Ljava/lang/String;I)Landroid/content/SharedPreferences;

    move-result-object v0

    const-string v1, "cfg_cache"

    const/4 v2, 0x0

    invoke-interface {v0, v1, v2}, Landroid/content/SharedPreferences;->getString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    if-eqz v0, :no

    invoke-virtual {v0}, Ljava/lang/String;->length()I

    move-result v1

    const/16 v2, 0x10

    if-ge v1, v2, :no

    :try_start
    invoke-static {}, Lcom/hjq/gson/factory/GsonFactory;->getSingletonGson()Lcom/google/gson/Gson;

    move-result-object v1

    const-class v2, Lcom/zhiyin/toolbox/bean/AppConfigBean;

    invoke-virtual {v1, v0, v2}, Lcom/google/gson/Gson;->fromJson(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Lcom/zhiyin/toolbox/bean/AppConfigBean;
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :no

    if-eqz v1, :no

    sput-object v1, Lcom/zhiyin/toolbox/activity/FirstActivity;->config:Lcom/zhiyin/toolbox/bean/AppConfigBean;

    invoke-static {p0, v1}, Lcom/apertus/AqQuality;->apply(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V

    invoke-static {p0, v1}, Lcom/apertus/ApertusConfig;->sanitize(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V

    new-instance v2, Landroid/content/Intent;

    const-class v3, Lcom/zhiyin/music/MusicActivity;

    invoke-direct {v2, p0, v3}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    invoke-virtual {p0, v2}, Lcom/zhiyin/toolbox/activity/FirstActivity;->startActivity(Landroid/content/Intent;)V

    invoke-virtual {p0}, Lcom/zhiyin/toolbox/activity/FirstActivity;->finish()V

    const/4 v0, 0x1

    return v0

    :no
    const/4 v0, 0x0

    return v0
.end method


# 中和强更: 把服务端给的 latestVersion 换成运行期已安装版本, forceUpdate 置空。
# 各处的判断都是 "latestVersion 与本地版本不一致 -> 弹更新框", 换成一致之后自然不弹,
# 不用逐个界面去删弹窗。
.method public static sanitize(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V
    .locals 3

    if-eqz p1, :ret

    if-eqz p0, :ret

    invoke-virtual {p1}, Lcom/zhiyin/toolbox/bean/AppConfigBean;->getUpdateConfig()Lcom/zhiyin/toolbox/bean/AppConfigBean$UpdateConfig;

    move-result-object v0

    if-eqz v0, :ret

    invoke-static {p0}, Lcom/zhiyin/toolbox/utils/Utils;->ᛱᛱᛱᛱᲈ(Landroid/content/Context;)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v0, v1}, Lcom/zhiyin/toolbox/bean/AppConfigBean$UpdateConfig;->setLatestVersion(Ljava/lang/String;)V

    const-string v1, ""

    invoke-virtual {v0, v1}, Lcom/zhiyin/toolbox/bean/AppConfigBean$UpdateConfig;->setForceUpdate(Ljava/lang/String;)V

    :ret
    return-void
.end method
