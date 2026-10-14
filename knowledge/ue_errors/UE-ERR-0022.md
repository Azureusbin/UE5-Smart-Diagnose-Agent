---
id: UE-ERR-0022
title: IntelliSense 满屏红线但编译能过（IDE 索引问题，不是编译错误）
category: compile
keywords: [满屏红线, IntelliSense 报错, 编辑器画红线但能编译, 找不到定义, VS 花屏, 智能提示失效, 假报错, 红线但不是错误]
error_codes: ["E0020", "E0135", "IntelliSense", "cannot open source file", "C1083"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine
source: 来源：Epic 官方文档（VS 配置）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

VS / Rider 里一片红：`E0020 未定义标识符 UMyTank`、`E0135 class "AActor" 没有成员 "GetWorld"`、`无法打开源文件 "MyTank.generated.h"`……

但**按下编译却成功了**（或编辑器里 Compile 按钮是绿的）。红线的行号和真实编译输出对不上。

## 常见根因（按概率排序）

1. **没重新生成工程文件**（约 40%）：新加了类/改了 `.Build.cs`，IDE 工程还是旧的，索引里没有这些文件
2. **IntelliSense 的 include 路径没跟上 UBT**（约 20%）：UBT 编译时用的路径和 IDE 索引配置不一致
3. **索引缓存坏了**（约 20%）：`.vs/`、`*.VC.db`、Rider 的 caches 损坏
4. **没装/没启用 UE 的 VS 工具**（约 10%）：Visual Studio Tools for Unreal Engine、或没装「使用 C++ 的游戏开发」工作负载
5. **Live Coding 后的临时状态**（约 10%）：热重载期间索引短暂错乱，重启 IDE 就好

## 排查步骤

1. 判断真假：**看 UBT/Output Log 的编译输出**——只要 UBT 编译过，红线就是假的
2. 确认工程文件是新的：`.uproject` → Generate Visual Studio project files（会重写 `.vcxproj` 和 include 路径）
3. 看该文件是否属于当前工程：VS 里文件路径对不上 `Source/` 的，是残留的旧引用

## 修复方案

1. 关掉 VS/Rider → 删 `Binaries/`、`Intermediate/`、`.vs/`（Rider 删 `.idea/` 与 caches）→ 重新生成工程文件 → 打开 sln
2. 重新生成后仍红：关闭 VS → 删除解决方案目录下的 `*.VC.db` → 重开，让它重新索引（大项目首次索引要几分钟）
3. 装齐 VS 组件：Visual Studio Installer → 「使用 C++ 的游戏开发」+「Unreal Engine 安装程序」/ VS Tools for UE
4. 用 Rider 的话：Settings → Languages & Frameworks → C++ → 重新生成/刷新项目模型

## 容易误判的情况

- **红线 ≠ 编译错误**：本条的判定标准就是「编译真的过了」。此时**绝对不要照红线改代码**，那会引入真实错误
- 反过来也成立：**编译失败但 IDE 一片干净**（索引过期）时，以 UBT 输出为准
- 只有 `MyTank.generated.h` 一条红线、其他都正常，多数就是索引没更新，不用怀疑 UHT
- 和 UE-ERR-0006 区分：0006 是**编译器**真的找不到 generated.h（编译失败）；本条是**只有 IDE** 找不到（编译成功）
