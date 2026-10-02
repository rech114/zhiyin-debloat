# zhiyin-debloat

只音 (`com.app.yxcds.zy.yz` v3.6.0) 去变现层构建流水线。

只用 GitHub Actions 的 x86_64 `zipalign`/签名链，本地不自己对齐。

## 结构

```
base/test.apk               原始 APK (未改动)
dexs/classes7-debug.dex     插桩版: 保留广告门禁, 加日志探针
dexs/classes7-clean.dex     去变现版: 门禁已旁路, 无日志
tools/repack.py             APK 精确重建 (逐条保留压缩方式)
tools/apkcheck.py           产物验收 (对齐/压缩/签名)
keystore/zhiyin.jks         签名密钥 (debug 与 clean 同一把, 免卸载重装)
```

## 产物

| 文件 | 用途 |
|---|---|
| `zhiyin-debug-*.apk` | 采集日志用。装它 -> 触发限制界面 -> 取 `/storage/emulated/0/MusicDebug/debug.log` |
| `zhiyin-clean-*.apk` | 最终交付。广告门禁已摘除，音乐功能不动 |

## 日志

`/storage/emulated/0/Android/data/com.app.yxcds.zy.yz/files/debug.log`

免权限目录（App 自己的外置沙箱），不需要"管理所有文件"授权。

## 补丁说明（实测确认）

广告门禁有 **3 个入口**，全部汇入 `ForceAdManager.ᛱᛱᛱᛱᲇ()`：

| # | 入口 | 场景 |
|---|---|---|
| 1 | `ToolAdHelper.ᛱᛱᛱᛱᛲ` | 工具点击 |
| 2 | `MainActivity:4134` | 首页每日功能 |
| 3 | `MusicActivity:10773` | **音乐播放器（听歌本身）** |

`OnAdLockCallback`：`ᛱᛱᛱᛱᛲ()` = 放行；`ᛱᛱᛱᛱᛱ()` = 取消（MainActivity/MusicActivity 的实现是 `finish()` 退出 App）。

补丁只做两件事：
1. `ToolAdHelper.ᛱᛱᛱᛱᛲ` 直接执行工具启动 runnable；
2. `ForceAdManager.ᛱᛱᛱᛱᲇ` 不弹窗，直接调 `ᛱᛱᛱᛱᛲ()` 放行 —— 一处覆盖全部 3 个入口。

音乐功能（酷狗/QQ/网易云解析、播放、下载）一行未动。

## 三个变体

| 变体 | 门禁 | 广告 SDK | 日志探针 | 用途 |
|---|---|---|---|---|
| `debug` | 保留 | 保留 | 有 | 复现原始限制界面采数据 |
| `clean` | 已摘 | 已关停 | 无 | 最终交付 |
| `verify` | 已摘 | 已关停 | 有 | **既修复又记录**，一次安装同时验证+取证 |

日志: `/storage/emulated/0/Android/data/com.app.yxcds.zy.yz/files/debug.log`
verify/debug 版的日志里出现 `PATCH OK > ...` 就说明补丁生效。

## 补丁 8: 「官方交流群」卡片

`AboutActivity.initActivity` 里拿到 `@id/ql` 卡片后立刻 `setVisibility(GONE)`。
布局资源 `activity_about.xml` 与点击逻辑均未改动（`.registers` 6->7 腾了个临时寄存器）。

## 变体总表

| 变体 | 门禁 | 广告SDK初始化 | 广告 so/jar | Manifest广告组件 | 日志探针 | 崩溃抓栈 |
|---|---|---|---|---|---|---|
| `debug` | 保留 | 保留 | 保留 | 保留 | 有 | 无 |
| `clean` | 已摘 | 已关停 | 保留 | 保留 | 无 | 无 |
| `verify` | 已摘 | 已关停 | 保留 | 保留 | 有 | 无 |
| `slim` | 已摘 | 已关停 | **已删** | **已摘139个** | 无 | 无 |
| `slimdbg` | 已摘 | 已关停 | **已删** | **已摘139个** | 有 | **有** |

`slimdbg` 用于为「空壳化 openads + 删 2.6 万广告类」采集前置信息：
装上后正常使用一轮，若有类链接失败，`CRASH | <完整堆栈>` 会直接点名缺失的类。
