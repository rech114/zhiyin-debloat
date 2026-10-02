#!/usr/bin/env python3
"""只音 (com.zhiyin) 去变现层补丁应用器.

在 smali 树上就地打补丁。支持三种补丁类型:

  kind="method"  用 anchor(正则, 匹配 .method 头) 定位, 整个方法体替换成 body
  kind="drop"    精确删除某条 invoke 指令: 先按 setOnShowListener 的寄存器对定位弹窗,
                 再删掉紧随其后同一个 dialog 寄存器的 show() 调用
  kind="text"    字面量替换 (old -> new)

新增补丁只需往 PATCHES 里加一条。

用法:
    apply.py <smali 根目录>
"""
import argparse
import re
import sys
from pathlib import Path

# ================================================================ 补丁 1
# 工具点击入口。原逻辑: 若服务端下发的 adTools 含该工具名 -> 查本地已看广告次数
# -> 不够就弹"使用提醒"框。补丁: 直接执行原生的工具启动 runnable。
GATE_BYPASS = """.method public static ᛱᛱᛱᛱᛲ(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/tool/FunctionItem;Lcom/zhiyin/toolbox/bean/AppConfigBean;I)V
    .registers 6

    if-eqz p1, :debloat_ret

    if-eqz p0, :debloat_ret

    new-instance v1, Lcom/hzhj/libs/ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ;

    invoke-direct {v1, p0, p1}, Lcom/hzhj/libs/ᛱᛱᛳᛷᛱ/ᛱᛱᛱᛵᤞ;-><init>(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/tool/FunctionItem;)V

    invoke-interface {v1}, Ljava/lang/Runnable;->run()V

    :debloat_ret
    return-void
.end method
"""

# ================================================================ 补丁 2
# 限制弹窗总收口点, 全 App 的 3 个入口都汇到这里:
#   ToolAdHelper(工具点击) / MainActivity:4134(首页) / MusicActivity:10773(音乐播放器)
# 原逻辑: 弹框, 看满 N 次广告才调 OnAdLockCallback.ᛱᛱᛱᛱᛲ() 放行;
#         点"取消"调 ᛱᛱᛱᛱᛱ() —— MainActivity/MusicActivity 的实现是 finish() 退出 App。
# 补丁: 不弹窗, 直接当"广告已看完"放行。
DIALOG_BYPASS = """.method public ᛱᛱᛱᛱᲇ(Landroid/app/Activity;Ljava/lang/String;ILcom/zhiyin/toolbox/utils/ForceAdManager$OnAdLockCallback;)V
    .registers 5

    if-eqz p4, :debloat_ret

    invoke-interface {p4}, Lcom/zhiyin/toolbox/utils/ForceAdManager$OnAdLockCallback;->ᛱᛱᛱᛱᛲ()V

    :debloat_ret
    return-void
.end method
"""

# ================================================================ 补丁 3
# 开屏广告。原逻辑: 拉全屏开屏广告并等待其结束(超时兜底)。
# 补丁: 直接回调 onFinish(), 让 FirstActivity 立刻进主界面。
SPLASH_BYPASS = """.method public ᛱᛱᛱᛱᤝ()V
    .registers 2

    iget-object v0, p0, Lcom/zhiyin/toolbox/utils/HJSplashAdHelper;->ᛱᛱᛱᛱᤝ:Lcom/zhiyin/toolbox/utils/HJSplashAdHelper$OnSplashListener;

    if-eqz v0, :debloat_ret

    invoke-interface {v0}, Lcom/zhiyin/toolbox/utils/HJSplashAdHelper$OnSplashListener;->onFinish()V

    :debloat_ret
    return-void
.end method
"""

# ================================================================ 补丁 4
# 广告 SDK 初始化。原逻辑: HJAdsSdk.sharedAds().startWithAppId(app, appId)
# 补丁: 空实现 —— SDK 永不初始化, 开屏/插屏/激励/横幅全部不再请求,
#       也就不会再刷 "广告加载失败: exception when load"。
SDK_INIT_NOOP = """.method public ᛱᛱᛱᛱᛴ(Landroid/app/Application;Ljava/lang/String;Z)V
    .registers 4

    return-void
.end method
"""

PATCHES = [
    dict(kind="method",
         name="去掉工具广告门禁 (ToolAdHelper)",
         file="com/zhiyin/toolbox/utils/ToolAdHelper.smali",
         anchor=r"^\.method public static ᛱᛱᛱᛱᛲ\(Landroid/content/Context;"
                r"Lcom/zhiyin/toolbox/bean/tool/FunctionItem;"
                r"Lcom/zhiyin/toolbox/bean/AppConfigBean;I\)V$",
         body=GATE_BYPASS),

    dict(kind="method",
         name="去掉限制弹窗总出口 (ForceAdManager)",
         file="com/zhiyin/toolbox/utils/ForceAdManager.smali",
         anchor=r"^\.method public ᛱᛱᛱᛱᲇ\(Landroid/app/Activity;"
                r"Ljava/lang/String;I"
                r"Lcom/zhiyin/toolbox/utils/ForceAdManager\$OnAdLockCallback;\)V$",
         body=DIALOG_BYPASS),

    dict(kind="method",
         name="去掉开屏广告 (HJSplashAdHelper)",
         file="com/zhiyin/toolbox/utils/HJSplashAdHelper.smali",
         anchor=r"^\.method public ᛱᛱᛱᛱᤝ\(\)V$",
         body=SPLASH_BYPASS),

    dict(kind="method",
         name="关停广告 SDK 初始化 (HJAdManager)",
         file="com/zhiyin/toolbox/utils/HJAdManager.smali",
         anchor=r"^\.method public ᛱᛱᛱᛱᛴ\(Landroid/app/Application;"
                r"Ljava/lang/String;Z\)V$",
         body=SDK_INIT_NOOP),

    # MusicActivity.onCreate 里的 3 个变现弹窗: 任务(9974) / 公告(10163) / 强更(10526)。
    # 同类的功能弹窗 soundDialog/timerDialog 用的是 {v1, p1}, 不会被误伤。
    dict(kind="drop",
         name="去掉任务弹窗 (MusicActivity)",
         file="com/zhiyin/music/MusicActivity.smali",
         listener_regs="v6, v1", dialog_reg="v6"),

    dict(kind="drop",
         name="去掉公告弹窗 (MusicActivity)",
         file="com/zhiyin/music/MusicActivity.smali",
         listener_regs="v1, v8", dialog_reg="v1"),

    dict(kind="drop",
         name="去掉强更弹窗 (MusicActivity)",
         file="com/zhiyin/music/MusicActivity.smali",
         listener_regs="v1, v5", dialog_reg="v1"),

    # 「关于」页里的"欢迎加入软件官方交流群"卡片 (@id/ql)。
    # 只做两件事: initActivity 的 .registers 6 -> 7 (腾一个临时寄存器 v4),
    # 拿到卡片后立刻 setVisibility(GONE)。不碰布局资源, 不动点击逻辑。
    dict(kind="text",
         name="匿名交流群卡片: 扩容寄存器 (AboutActivity)",
         file="com/zhiyin/toolbox/activity/AboutActivity.smali",
         old=".method public initActivity(Landroid/os/Bundle;)V\n    .registers 6",
         new=".method public initActivity(Landroid/os/Bundle;)V\n    .registers 7"),

    dict(kind="text",
         name="去掉官方交流群卡片 (AboutActivity)",
         file="com/zhiyin/toolbox/activity/AboutActivity.smali",
         old="    iget-object p1, p1, Lcom/zhiyin/toolbox/databinding/ActivityAboutBinding;->"
             "ql:Lcom/google/android/material/card/MaterialCardView;\n"
             "\n    .line 289\n    .line 290\n"
             "    new-instance v0, Lcom/hzhj/libs/ᛱᛱᛳᛶᛴ/ᛱᛱᛱᛱᛷ;\n",
         new="    iget-object p1, p1, Lcom/zhiyin/toolbox/databinding/ActivityAboutBinding;->"
             "ql:Lcom/google/android/material/card/MaterialCardView;\n"
             "\n    const/16 v4, 0x8\n\n"
             "    invoke-virtual {p1, v4}, Landroid/view/View;->setVisibility(I)V\n"
             "\n    .line 289\n    .line 290\n"
             "    new-instance v0, Lcom/hzhj/libs/ᛱᛱᛳᛶᛴ/ᛱᛱᛱᛱᛷ;\n"),

    # ---------------------------------------------------------------- 补丁: 首页轮播引流 Banner
    # 首页顶部轮播的数据源是服务端下发的 musicBanners, 第 0 项就是「官方交流群」
    # (type="群聊", 点进去是 QQ 加群)。同数组里只有 "群聊" 和 "歌单" 两种 type,
    # 所以在这里按 type 过滤, 轮播项数和指示点会自动跟着变, 不留空白页。
    dict(kind="text",
         name="首页轮播过滤: 扩容寄存器 (MusicHomeHeadAdapter)",
         file="com/zhiyin/music/adapter/MusicHomeHeadAdapter.smali",
         old=".method public onBindView(Landroidx/viewbinding/ViewBinding;"
             "Ljava/util/HashMap;IILjava/util/ArrayList;)V\n    .registers 6",
         new=".method public onBindView(Landroidx/viewbinding/ViewBinding;"
             "Ljava/util/HashMap;IILjava/util/ArrayList;)V\n    .registers 11"),

    dict(kind="regex",
         name="首页轮播过滤掉 type=群聊 的引流 Banner",
         file="com/zhiyin/music/adapter/MusicHomeHeadAdapter.smali",
         pattern=r"(sget-object p2, Lcom/zhiyin/toolbox/activity/FirstActivity;->config:"
                 r"Lcom/zhiyin/toolbox/bean/AppConfigBean;\s*\n"
                 r"(?:\s*\.line \d+\s*\n)*\s*invoke-virtual \{p2\}, "
                 r"Lcom/zhiyin/toolbox/bean/AppConfigBean;->getMusicBanners\(\)Ljava/util/List;\s*\n"
                 r"(?:\s*\.line \d+\s*\n)*\s*move-result-object p2\s*\n)",
         repl=r"\1\n"
              "    new-instance v0, Ljava/util/ArrayList;\n\n"
              "    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V\n\n"
              "    invoke-interface {p2}, Ljava/util/List;->iterator()Ljava/util/Iterator;\n\n"
              "    move-result-object v1\n\n"
              "    :debloat_loop\n"
              "    invoke-interface {v1}, Ljava/util/Iterator;->hasNext()Z\n\n"
              "    move-result v2\n\n"
              "    if-eqz v2, :debloat_done\n\n"
              "    invoke-interface {v1}, Ljava/util/Iterator;->next()Ljava/lang/Object;\n\n"
              "    move-result-object v2\n\n"
              "    check-cast v2, Lcom/zhiyin/toolbox/bean/AppConfigBean$BannerItem;\n\n"
              "    const-string v3, \"群聊\"\n\n"
              "    invoke-virtual {v2}, Lcom/zhiyin/toolbox/bean/AppConfigBean$BannerItem;->"
              "getType()Ljava/lang/String;\n\n"
              "    move-result-object v4\n\n"
              "    invoke-virtual {v3, v4}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n\n"
              "    move-result v3\n\n"
              # if-eqz = v3==0 时跳转。v3 = "群聊".equals(type), 所以
              # v3==0 表示"不是群聊" → 跳去 add（保留）。这句本来就是对的。
              "    if-eqz v3, :debloat_keep\n\n"
              "    goto :debloat_loop\n\n"
              "    :debloat_keep\n"
              "    invoke-interface {v0, v2}, Ljava/util/List;->add(Ljava/lang/Object;)Z\n\n"
              "    goto :debloat_loop\n\n"
              "    :debloat_done\n"
              "    move-object p2, v0\n"),
]


def apply_method(text: str, patch: dict) -> str:
    m = re.search(patch["anchor"], text, re.MULTILINE)
    if not m:
        return "SKIP  (锚点未命中, 可能已打过)"
    end = text.index(".end method", m.start()) + len(".end method")
    return text[:m.start()] + patch["body"].rstrip("\n") + text[end:]


def apply_drop(text: str, patch: dict) -> str:
    """删掉某个变现弹窗的 show() 调用."""
    lines = text.split("\n")
    anchor = f"invoke-virtual {{{patch['listener_regs']}}}, Landroid/app/Dialog;->setOnShowListener("
    show = f"invoke-virtual {{{patch['dialog_reg']}}}, Landroid/app/Dialog;->show()V"
    for i, line in enumerate(lines):
        if anchor in line:
            for j in range(i + 1, min(i + 12, len(lines))):
                if lines[j].strip() == show:
                    del lines[j]
                    return "\n".join(lines)
            return "SKIP  (找到弹窗但没找到 show())"
    return "SKIP  (锚点未命中, 可能已打过)"


def apply_text(text: str, patch: dict) -> str:
    if patch["old"] not in text:
        return "SKIP  (原文未找到, 可能已打过补丁或作者改动了这段代码)"
    return text.replace(patch["old"], patch["new"], 1)


def apply_regex(text: str, patch: dict) -> str:
    out, n = re.subn(patch["pattern"], patch["repl"], text, count=1)
    return out if n else "SKIP  (正则未命中)"


def apply_file(text: str, patch: dict) -> str:
    """kind="file": 写入一个**新**类, 内容取自 patch 目录下的模板。

    为什么不直接内联成字符串: 新类有上百行 smali, 放进 PATCHES 会把这个文件撑得没法看,
    而且模板单独一个 .smali 文件可以直接用 smali 汇编器单独验证语法。
    """
    src = Path(__file__).resolve().parent / patch["src"]
    return src.read_text(encoding="utf-8")


HANDLERS = {"method": apply_method, "drop": apply_drop,
            "text": apply_text, "regex": apply_regex, "file": apply_file}



# ================================================================ 补丁 9
# 播放音质选择 (新增类)。
# 服务端下发的 config 里 kugouParams / qqParams / wyyApi 各带一个 level 字段,
# 客户端原样发出去 —— 所以音质是服务端定的。这个类在配置解析后统一改写它们,
# 把决定权挪到本地 (SharedPreferences: config/aq_level)。
OLD_OUTER = '    sput-object p1, Lcom/zhiyin/toolbox/activity/FirstActivity;->config:Lcom/zhiyin/toolbox/bean/AppConfigBean;'
NEW_OUTER = (OLD_OUTER
             + "\n\n    iget-object v0, p0, Lcom/zhiyin/toolbox/activity/FirstActivity$1;->"
             + 'ᛱᛱᛱᛱᛱ'
             + ":Lcom/zhiyin/toolbox/activity/FirstActivity;\n\n"
             + "    invoke-static {v0, p1}, Lcom/apertus/AqQuality;->apply"
             + "(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V\n\n"
             # 同一处顺带中和强更: 把 latestVersion 换成运行期版本, 各界面都不用再拆弹窗
             + "    invoke-static {v0, p1}, Lcom/apertus/ApertusConfig;->sanitize"
             + "(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V\n\n"
             # 接口兜底放在最后: 音质改写会动 wyyApi 的 level, 兜底只处理"空/坏地址"
             + "    invoke-static {v0, p1}, Lcom/apertus/ApertusApi;->sanitize"
             + "(Landroid/content/Context;Lcom/zhiyin/toolbox/bean/AppConfigBean;)V")

HOOK_OLD = '    invoke-direct {v1, p0}, Lcom/hzhj/libs/ᛱᛱᛳᛴᛶ/ᛱᛱᛱᛳᲁ;-><init>(Lcom/zhiyin/music/MusicActivity;)V'
HOOK_NEW = (HOOK_OLD
            + "\n\n    new-instance v2, Lcom/apertus/AqQuality;\n\n"
            + "    invoke-direct {v2}, Lcom/apertus/AqQuality;-><init>()V\n\n"
            + "    invoke-virtual {v0, v2}, Landroid/view/View;->"
            + "setOnLongClickListener(Landroid/view/View$OnLongClickListener;)V")

QUALITY_CLASS = dict(
    name="新增音质选择类 AqQuality",
    kind="file",
    file="com/apertus/AqQuality.smali",
    src="AqQuality.smali",
)

# ================================================================ 补丁 10
# 配置刚刚解析完、还没被任何地方读到的时候, 把本地档位套进去。
# FirstActivity$1 持有外部 FirstActivity, 正好当 Context 用。
QUALITY_APPLY = dict(
    name="配置解析后套用本地音质档位",
    kind="text",
    file="com/zhiyin/toolbox/activity/FirstActivity$1.smali",
    old=OLD_OUTER,
    new=NEW_OUTER,
)

# ================================================================ 补丁 11
# 长按音量按钮 -> 音质选择。
# 挂在 sound 按钮上: 它的单击已经给了音量面板, 长按是空着的。
# 用 v2 而不是 v1 —— v1 这时正握着单击监听器, 覆盖它会连带把单击也换掉。
QUALITY_HOOK = dict(
    name="长按音量按钮打开音质选择",
    kind="text",
    file="com/zhiyin/music/MusicActivity.smali",
    old=HOOK_OLD,
    new=HOOK_NEW,
)

# ================================================================ 补丁 12
# 配置本地兜底 (1/3): 远程取到就落盘。插在成功回调方法最前面, p1 就是原始响应体。
# 锚点只取"方法头 + .registers", 不碰探针行 —— smali_dbg 树里那些行是后加的,
# 干净树里没有, 拿它们当锚点会在这里 SKIP 而在那边命中。
OUTER_FIELD = 'ᛱᛱᛱᛱᛱ'

CFG_SAVE = dict(
    name="配置落盘 (远程成功时)",
    kind="regex",
    file="com/zhiyin/toolbox/activity/FirstActivity$1.smali",
    pattern=r"(\.method private synthetic ᛱᛱᛱᛱᛶ\(Ljava/lang/String;\)V\s*\n\s*\.registers \d+\n)",
    # 注意: 这里是 FirstActivity$1, p0 是内部类自己, **不是** Context。
    # 外部 Activity 在字段 ᛱᛱᛱᛱᛱ 里, 必须先 iget-object 取出来。
    # (真踩过两个坑: ① 直接传 p0 被校验器判 "type FirstActivity$1 but expected Context",
    #   整类加载失败; ② 字段名手写转义写错 -> 汇编不报错, 运行期才 NoSuchFieldError)
    repl=("\\1"
          "\n    iget-object v0, p0, Lcom/zhiyin/toolbox/activity/FirstActivity$1;->"
          + OUTER_FIELD +
          ":Lcom/zhiyin/toolbox/activity/FirstActivity;\n"
          "\n    invoke-static {v0, p1}, Lcom/apertus/ApertusConfig;->save"
          "(Landroid/content/Context;Ljava/lang/String;)V\n")
)

# 补丁 13
# 配置本地兜底 (2/3): 远程失败时读本地, 能兜住就直接进主界面, 不再弹"切换线路"。
CFG_FAILOVER = dict(
    name="配置兜底 (远程失败时读本地)",
    kind="regex",
    file="com/zhiyin/toolbox/activity/FirstActivity.smali",
    pattern=r"(\.method private handleLoadError\(\)V\s*\n\s*\.registers \d+\n)",
    repl=("\\1"
          "\n    invoke-static {p0}, Lcom/apertus/ApertusConfig;->failover"
          "(Lcom/zhiyin/toolbox/activity/FirstActivity;)Z\n\n"
          "    move-result v0\n\n"
          "    if-eqz v0, :apertus_cont\n\n"
          "    return-void\n\n"
          "    :apertus_cont\n"),
)

# 补丁 14
CFG_CLASS2 = dict(
    name="新增配置兜底类 ApertusConfig",
    kind="file",
    file="com/apertus/ApertusConfig.smali",
    src="ApertusConfig.smali",
)

# ================================================================ 补丁 15
# 关键播放接口的兜底: 服务端把 kugouApi/qqApi/wyyApi 清空或改成坏地址时, 用实测可用的
# 地址补上; 另支持一个本地覆盖文件 (api.txt), 作者服务器真挂了可以不改包直接换服务。
API_FALLBACK = dict(
    name="新增播放接口兜底类 ApertusApi",
    kind="file",
    file="com/apertus/ApertusApi.smali",
    src="ApertusApi.smali",
)

PATCHES = PATCHES + [API_FALLBACK]

PATCHES = PATCHES + [CFG_CLASS2, CFG_SAVE, CFG_FAILOVER]

PATCHES = PATCHES + [QUALITY_CLASS, QUALITY_APPLY, QUALITY_HOOK]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--strict", action="store_true",
                    help="任一补丁未命中就返回非零 —— 防止锚点失配时静默产出"
                         "'门禁还活着'的包。作者更新版本后必须开这个。")
    args = ap.parse_args()

    skipped = []
    for p in PATCHES:
        path = args.root / p["file"]
        if p["kind"] == "file":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(HANDLERS["file"]("", p), encoding="utf-8")
            print(f"OK    {p['name']} -> {p['file']} (新增类)")
            continue
        if not path.exists():
            print(f"SKIP  {p['name']}: 文件不存在")
            skipped.append(p["name"])
            continue
        text = path.read_text(encoding="utf-8")
        out = HANDLERS[p["kind"]](text, p)
        if isinstance(out, str) and out.startswith("SKIP"):
            print(f"{out}  <- {p['name']}")
            skipped.append(p["name"])
            continue
        path.write_text(out, encoding="utf-8")
        print(f"OK    {p['name']} -> {p['file']}")

    if skipped and args.strict:
        print(f"\n★ {len(skipped)} 个补丁未命中, --strict 模式判定失败:")
        for s in skipped:
            print(f"   - {s}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
