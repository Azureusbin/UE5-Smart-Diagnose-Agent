---
id: UE-ERR-0020
title: 编译错误 C1010 在查找预编译头时遇到意外的文件结尾
category: compile
keywords: [预编译头, PCH, C1010, pch.h, 忘了 include CoreMinimal, 新建 cpp 编译不过, 第三方 cpp 加进项目报错, 空文件编译报错, SharedPCH]
error_codes: ["C1010", "C1083", "unexpected end of file while looking for precompiled header", "PCHUsage"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-errors-1/fatal-error-c1010
source: 来源：MS 官方文档（C1010）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

新建了一个 .cpp，或者往项目里塞了一个第三方 .cpp，编译报：

```
MyUtil.cpp: fatal error C1010: 在查找预编译头时遇到意外的文件结尾。是否忘记了向源中添加 "#include "pch.h""?
```

或：

```
fatal error C1083: 无法打开预编译头文件: "MyGame.pch": No such file or directory
```

特点：**报错文件本身一行代码都没问题**，甚至是个空文件；同一模块别的 .cpp 编得好好的。

## 常见根因（按概率排序）

1. **.cpp 里没有第一个 include `CoreMinimal.h`**（约 50%）：UBT 对这个模块启用了 PCH，编译器在文件末尾都没等到 PCH 头，直接报 C1010
2. **第三方 .cpp 带进来的写法**（约 20%）：外部库的源文件不写 UE 的头文件，被直接丢进 `Source/`
3. **Unity Build（合并编译）**（约 15%）：`bUseUnity` 把多个 .cpp 合成一个，某个文件里的 `#include` 被 `#if` 包住或位置不对就触发
4. **`Intermediate/` 里的 PCH 产物缺失**（约 10%）：上次编译中断，`.pch` 没生成完，报 C1083 那种
5. **模块 PCH 设置冲突**（约 5%）：`.Build.cs` 里 `PCHUsage` 与文件实际写法不一致

## 排查步骤

1. 打开报错的 .cpp，看**第一行**是不是 `#include "CoreMinimal.h"`（或该模块的 PCH 头）
2. 确认这个文件是不是第三方代码——如果是，别改它的内容，改模块配置（见下）
3. 报 C1083（找不到 .pch 文件）时，先删 `Intermediate/` 重新生成工程文件再编译，排除产物残缺

## 修复方案

1. 自己的文件：在 .cpp **最顶部**加 PCH 头（顺序在所有 include 之前）：
   ```cpp
   #include "CoreMinimal.h"      // 必须第一行
   #include "MyUtil.h"
   ```
2. 第三方 / 自动生成的 .cpp（不能改内容）：在 `.Build.cs` 里对该模块关掉强制 PCH
   ```csharp
   PCHUsage = PCHUsageMode.NoPCHs;      // 或 UseSharedPCHs（按模块取舍）
   ```
3. 怀疑是 Unity Build 合并引起的，先单独验证：
   ```csharp
   bUseUnity = false;                   // 临时关闭，确认后在文件里补齐 include
   ```
4. 改完 `.Build.cs` 一定重新生成工程文件，并删 `Intermediate/` 让 PCH 重新生成

## 容易误判的情况

- **C1010 说的 "pch.h" 是 MSVC 的默认名**，UE 项目里对应的通常是 `CoreMinimal.h`——别真的去建一个 `pch.h`
- 报错行号常指在**文件最后**（因为编译器读到 EOF 才报），别被行号带偏，问题在第一行
- C1083「无法打开 MyGame.pch」**不是**你漏了 include，而是中间产物缺失/损坏，属于另一个处理路径
- 只给这一个文件 `#pragma warning(disable)` 或加 `/Y-` 是无效的——PCH 是编译选项层面的，必须在 `.Build.cs` 或文件包含上解决
- 一般不需要为了消这个错把 `PCHUsage` 改成 `NoPCHs` 长期跑，那会让整个模块编译变慢
