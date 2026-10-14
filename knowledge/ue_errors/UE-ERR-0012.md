---
id: UE-ERR-0012
title: 编译错误 C2011 类型重定义 / 符号冲突
category: compile
keywords: [类型重定义, 重复定义, 符号冲突, 第三方库冲突, C2011, 头文件保护, 命名冲突, 和引擎重名]
error_codes: ["C2011", "C2371", "C2872", "LNK2005", "redefinition"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-errors-1/compiler-error-c2011
source: 来源：MS 官方文档（C2011/C2371/LNK2005）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

引入第三方库、或者自己写了同名类型之后：

```
MyTypes.h(12): error C2011: "FVector": "struct" 类型重定义
MyLib.h(30): error C2371: "int32": 重定义；不同的基类型
```

链接阶段还可能伴生：

```
error LNK2005: "public: void __cdecl Print(void)" (?Print@@YAXXZ) 已经在 MyLib.lib 中定义
error LNK1169: 找到一个或多个多重定义的符号
```

## 常见根因（按概率排序）

1. **和引擎类型重名**（约 40%）：自己写了 `FVector`、`TArray`、`FString`、`FMath` 之类，或第三方库里有同名类
2. **头文件没有 include guard**（约 20%）：漏了 `#pragma once`，头文件被间接 include 两次就重定义
3. **第三方库和 UE 的类型冲突**（约 20%）：整包 include 了某库的 `Common.h` / `Windows.h` 之类，宏或类型名撞车（`check`、`verify`、`TEXT` 都是重灾区）
4. **同名 .cpp 被两个模块编译**（约 10%）：文件同时出现在两个模块目录里
5. **第三方静态库和 UE 各带了一份同名实现**（约 10%）：链接期 LNK2005

## 排查步骤

1. 看报错的两个声明分别在哪个文件——**先看哪个是「你不想要的」**
2. 搜是不是和引擎重名：在引擎 `Source/Runtime/` 下搜该类型名，命中就说明撞了
3. 检查自己的头文件顶部有没有 `#pragma once`
4. 第三方库：确认是在 `.Build.cs` 里当模块依赖引，而不是把它的 .h 一股脑复制进 `Source/`

## 修复方案

1. 自己起的名字加项目前缀（UE 风格）：
   ```cpp
   struct FMyGameVector { ... };   // 不要叫 FVector
   ```
2. 每个头文件第一行加 `#pragma once`
3. 第三方库只在 .cpp 里 include，头文件里用前向声明隔开：
   ```cpp
   // MyTank.h
   class ThirdPartyThing;                       // 前向声明，不暴露库头文件
   // MyTank.cpp
   #include "third_party/thing.h"             // 库头文件只出现在这里
   ```
4. 冲突的是 `Windows.h` 这类平台头：放到**最后** include，并在它前面定义 `WIN32_LEAN_AND_MEAN`；宏冲突用 `#undef` 精确解除
5. 在 `.Build.cs` 里正确引用第三方库（`PublicIncludePaths` / `PublicAdditionalLibraries`），而不是复制源码

## 容易误判的情况

- `C2011` 报的**不一定是「多写了一份」**，常见是引擎里本来就有同名类型——先搜引擎再改自己
- **LNK2005 与 C2011 常常是同一个根因的两面**（同一份实现进了两次），别当成两个独立问题分别修
- `C2872 "X": 不明确的符号` 性质不同：那是命名空间歧义（`using namespace` 撞车），加限定名 `MyGame::Foo` 即可
- 第三方库「能编译过但链接报 LNK2005」时，**不要**用 `/FORCE:MULTIPLE` 硬链接，那会把运行期不确定行为带进包里
