---
id: UE-ERR-0021
title: 插件/第三方库编译失败 版本不匹配（Marketplace 插件重灾区）
category: build
keywords: [插件编译失败, 插件报错, Marketplace 插件, 第三方库, 插件版本不对, 装插件后编译不过, Fab 插件, 模块找不到插件]
error_codes: ["Could not be compiled", "Missing precompiled manifest", "plugin", "unresolved external symbol", "C1083"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/plugins-in-unreal-engine
source: 来源：Epic 官方文档（Plugins）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

装了插件/第三方库之后，编译失败，且报错文件**不在你自己的 Source 里**：

```
ERROR: Missing precompiled manifest for 'MyPlugin'. This plugin was most likely not compiled for the current engine version.
MyPlugin\Source\MyPlugin\Private\MyPluginActor.cpp(31): error C2039: "XXX": 不是 "AActor" 的成员
ERROR: Plugin 'MyPlugin' failed to load because module 'MyPlugin' could not be found.
```

编辑器启动时可能直接弹「以下插件不兼容，是否禁用」。

## 常见根因（按概率排序）

1. **插件版本与引擎版本不匹配**（约 45%）：UE5.3 的插件装到 UE5.5 上，旧 API 已删/改名
2. **只有预编译包、没有源码**（约 20%）：插件只给了对应版本的 `.dll`/manifest，换引擎后就找不到
3. **缺模块依赖**（约 15%）：插件要的引擎模块（如 `EnhancedInput`、`Niagara`）没被启用
4. **插件之间互相依赖**（约 10%）：装 A 要 B，B 没启用或版本不对
5. **.uproject 里启用项没登记**（约 10%）：插件在 `Plugins/` 里但没在 Plugins 面板启用

## 排查步骤

1. 先确认报错文件路径：**在 `Plugins/` 下**就基本锁定是插件问题，不动自己代码
2. 打开 `.uproject`（或用编辑器 Plugins 面板）看该插件的 `EngineVersion` / 支持版本
3. 读第一条 C++ 错误：如果是「已弃用/不是成员」，说明插件源码适配的是旧引擎

## 修复方案

1. **优先升级插件**到支持当前引擎的版本（Fab/商城页面会标引擎版本区间）
2. 插件有源码（`Plugins/<Name>/Source/`）时，可以让 UBT 就地重编：删掉 `Plugins/<Name>/Binaries`、`Intermediate`，重新生成工程文件后整体编译
3. 只有预编译包的：找作者要「源码版」或对应引擎版本的包；没有就换插件
4. 缺模块：编辑器 → Edit → Plugins 里启用依赖项，或在自己的 `.Build.cs` 补上插件要求的模块名
5. 临时绕开：Plugins 面板禁用该插件 → 重启编辑器（先让项目能开，再解决兼容性）

## 容易误判的情况

- 报错文件在插件目录里时，**不要直接改插件源码**——下次插件升级改动就丢了；正确做法是升级插件或换实现
- `Missing precompiled manifest` 不是「文件损坏」，就是**版本/平台不匹配**，删 `Intermediate` 重试基本无效
- 引擎自带的插件（`Engine/Plugins/`）报错，通常是自己项目里**没启用它依赖的模块**，或者是引擎安装不完整
- 「装了插件后编辑器起不来」：先禁用插件启动，把项目救回来，再按上面流程处理兼容性
