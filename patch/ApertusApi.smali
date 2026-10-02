.class public Lcom/apertus/ApertusApi;
.super Ljava/lang/Object;
.source "ApertusApi.java"

# 关键播放接口的兜底与外部覆盖。
#
# 现状: kugouApi / qqApi / wyyApi 三个地址都由服务端下发。服务端只要把它们清空或
#       改成坏地址, 播放就全废 —— 这是第二个"远程开关"。
#
# 做法 (填空白, 不抢有效值):
#   1. 服务端给了非空值 -> 原样用 (保持和原版一致, 也保持音质档位能力)
#   2. 服务端给的为空 -> 填上**实测确认可用**的兜底地址
#   3. 本地覆盖文件优先于以上两者 —— 作者服务器真挂了, 把新地址写进这个文件即可继续用,
#      不需要重新打包。路径与调试日志同目录 (getExternalFilesDir):
#          Android/data/com.apertus.music/files/api.txt
#      格式, 一行一个, 写哪个覆盖哪个:
#          kg=https://your-host/v1/music/resolve-url
#          qq=https://your-host/v1/music/resolve-url
#          wyy=http://your-host/music.php?level=exhigh&id=
#
# 关于网易云: 存在一个公开接口 https://music.163.com/song/media/outer/url?id=
#   无需签名即可用 (实测 302 跳 CDN)。但它只给标准音质, 而作者的服务能出无损/母带。
#   所以这里**不**默认切过去, 只在 api.txt 里写明它是备选 —— 音质和可用性让用户自己权衡。

.field private static final KG_FALLBACK:Ljava/lang/String; = "https://musicserver.haitangw.cc/v1/music/resolve-url"

.field private static final QQ_FALLBACK:Ljava/lang/String; = "https://musicserver.haitangw.cc/v1/music/resolve-url"

.field private static final WYY_FALLBACK:Ljava/lang/String; = "http://47.109.94.179/music_v1.php?level=exhigh&id="

.field private static final OVERRIDE_FILE:Ljava/lang/String; = "api.txt"


# 取本地覆盖文件内容; 文件不存在或读失败返回 null
.method private static readOverrides(Landroid/content/Context;)Ljava/lang/String;
    .locals 6

    const/4 v0, 0x0

    :try_start
    invoke-virtual {p0}, Landroid/content/Context;->getExternalFilesDir()Ljava/io/File;

    move-result-object v1

    # getExternalFilesDir 可能返回 null (外部存储不可用)
    if-eqz v1, :ret

    new-instance v2, Ljava/io/File;

    const-string v3, "api.txt"

    invoke-direct {v2, v1, v3}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    invoke-virtual {v2}, Ljava/io/File;->exists()Z

    move-result v3

    if-eqz v3, :ret

    invoke-virtual {v2}, Ljava/io/File;->length()J

    move-result-wide v3

    long-to-int v3, v3

    const/4 v4, 0x4

    if-ge v3, v4, :ret

    new-instance v4, Ljava/io/FileInputStream;

    invoke-direct {v4, v2}, Ljava/io/FileInputStream;-><init>(Ljava/io/File;)V

    new-array v3, v3, [B

    invoke-virtual {v4, v3}, Ljava/io/InputStream;->read([B)I

    invoke-virtual {v4}, Ljava/io/InputStream;->close()V

    new-instance v5, Ljava/lang/String;

    const-string v4, "UTF-8"

    invoke-direct {v5, v3, v4}, Ljava/lang/String;-><init>([BLjava/lang/String;)V

    move-object v0, v5
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :ret

    :ret
    return-object v0
.end method


# 从覆盖文本里取某个键的值; 没有返回 null
.method private static pick(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
    .locals 7

    if-eqz p0, :no

    if-eqz p1, :no

    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v1, "="

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const-string v1, "\n"

    invoke-virtual {p0, v1}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    move-result-object v1

    array-length v2, v1

    const/4 v3, 0x0

    :loop
    if-ge v3, v2, :no

    aget-object v4, v1, v3

    invoke-virtual {v4}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v4, v0}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v5

    if-eqz v5, :next

    invoke-virtual {v0}, Ljava/lang/String;->length()I

    move-result v5

    invoke-virtual {v4, v5}, Ljava/lang/String;->substring(I)Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/String;->length()I

    move-result v6

    if-lez v6, :next

    return-object v5

    :next
    add-int/lit8 v3, v3, 0x1

    goto :loop

    :no
    const/4 v0, 0x0

    return-object v0
.end method


# 规则: 本地覆盖 > 服务端非空值 > 兜底常量
.method private static resolve(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
    .locals 1

    if-eqz p0, :chk

    invoke-virtual {p0}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/String;->length()I

    move-result v0

    # 长度为 0 才跳到下一条(覆盖/兜底); 非空则直接用这个值
    if-eqz v0, :chk

    return-object p0

    :chk
    if-eqz p1, :fallback

    invoke-virtual {p1}, Ljava/lang/String;->trim()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/String;->length()I

    move-result v0

    if-eqz v0, :fallback

    return-object p1

    :fallback
    return-object p2
.end method


# 入口: 在配置解析后、音质改写之后调用
.method public static sanitize(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V
    .locals 6

    if-eqz p1, :ret

    if-eqz p0, :ret

    invoke-virtual {p1}, Lcom/zhiyin/toolbox/bean/AppConfigBean;->getOtherConfig()Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;

    move-result-object v0

    if-eqz v0, :ret

    invoke-static {p0}, Lcom/apertus/ApertusApi;->readOverrides(Landroid/content/Context;)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v0}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->getKugouApi()Ljava/lang/String;

    move-result-object v2

    const-string v3, "kg"

    invoke-static {v1, v3}, Lcom/apertus/ApertusApi;->pick(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    sget-object v4, Lcom/apertus/ApertusApi;->KG_FALLBACK:Ljava/lang/String;

    invoke-static {v2, v3, v4}, Lcom/apertus/ApertusApi;->resolve(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->setKugouApi(Ljava/lang/String;)V

    invoke-virtual {v0}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->getQqApi()Ljava/lang/String;

    move-result-object v2

    const-string v3, "qq"

    invoke-static {v1, v3}, Lcom/apertus/ApertusApi;->pick(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    sget-object v4, Lcom/apertus/ApertusApi;->QQ_FALLBACK:Ljava/lang/String;

    invoke-static {v2, v3, v4}, Lcom/apertus/ApertusApi;->resolve(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->setQqApi(Ljava/lang/String;)V

    invoke-virtual {v0}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->getWyyApi()Ljava/lang/String;

    move-result-object v2

    const-string v3, "wyy"

    invoke-static {v1, v3}, Lcom/apertus/ApertusApi;->pick(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    sget-object v4, Lcom/apertus/ApertusApi;->WYY_FALLBACK:Ljava/lang/String;

    invoke-static {v2, v3, v4}, Lcom/apertus/ApertusApi;->resolve(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2}, Lcom/zhiyin/toolbox/bean/AppConfigBean$OtherConfig;->setWyyApi(Ljava/lang/String;)V

    :ret
    return-void
.end method
