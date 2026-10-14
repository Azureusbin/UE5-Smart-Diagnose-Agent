---
id: UE-ERR-0006
title: 编译错误 「Unable to find definition of 'XXX.generated.h'」找不到 Generated 头文件
category: compile
keywords: [找不到头文件, 打不开 generated.h, 新建类编译不过, 新手第一个编译错误, UCLASS, GENERATED_BODY, 无法打开包括文件, 第一次编译就报错]
error_codes: ["C1083", "Cannot open include file", "Unable to find definition of", "generated.h"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-classes-in-unreal-engine
updated: 2026-10-13
---
## 症状

新加了一个 C++ 类，或刚 clone 下别人的工程，第一次编译就失败：

```
MyTank.h(9): fatal error C1083: 无法打开包括文件: "MyTank.generated.h": No such file or directory
```

或 Unreal Header Tool / UnrealBuildTool 报：

```
Unable to find definition of 'MyTank.generated.h' - the file does not exist
```

注意：这个头文件**不在硬盘上、也不该手动创建**，它由 UHT 在编译时生成到 `Intermediate/Build/.../Inc/`。

## 常见根因（按概率排序）

1. **编译方式不对**（约 60%）：直接按 VS 的「生成/构建」或用 CMake 思路编译，跳过了 UBT，UHT 压根没跑
2. **没有先重新生成工程文件**（约 20%）：新加了 .h/.cpp 或改了 `.Build.cs`，IDE 工程还是旧的
3. **文件放错目录**（约 10%）：新类丢在 `Source/` 根下或模块外，没被模块的 `*.Build.cs` 扫到
4. **`Intermediate/` 缓存坏了**（约 10%）：上次编译中断，生成物半残

## 排查步骤

1. 确认类的头文件在 `Source/<Project>/` 或 `Source/<Project>/<Sub>/` 下，**和模块的 .Build.cs 同属一个模块**
2. 确认头文件里写了 `#include "MyTank.generated.h"`，且它在**所有 include 的最后一行**（见 UE-ERR-0009）
3. 确认是用编辑器的 **Compile 按钮 / Live Coding**，或 VS 里 `Development Editor` 配置构建，而不是空的默认配置

## 修复方案

1. 重新生成工程文件：右键 `MyGame.uproject` → **Generate Visual Studio project files**（命令行：`"<引擎>\Engine\Build\BatchFiles\Build.bat" -projectfiles -project="D:\Proj\MyGame.uproject" -game -rocket -progress`）
2. 关掉编辑器 → 删掉项目根的 `Binaries/`、`Intermediate/`、`Saved/` 三个目录 → 重新生成工程文件 → 编译（**先删 Intermediate，不要删 Source**）
3. 直接从编辑器新建类：Content Browser → **C++ Class**（这样 UHT 需要的骨架、模块归属都是对的）

## 容易误判的情况

- 报错说 `Cannot open include file: 'MyTank.generated.h'` 时，**不要去磁盘上手动造这个文件**，也不要把它加进 git——它是编译产物，造出来只会掩盖真正的原因
- 如果报错指向**引擎**的 generated.h（`Engine.generated.h` 之类），通常是引擎没编译完整 / 安装损坏，不是项目代码问题
- 只有 IntelliSense 画红线说找不到 `.generated.h`、但 UBT 编译能过 → 是 IDE 索引问题，见 UE-ERR-0018，**不要照着红线改代码**
