---
id: UE-ERR-0005
title: 编译错误 error C2065 未声明的标识符
category: compile
keywords: [编译错误, 找不到标识符, 未声明, 缺少头文件, include, C2065, 编译不过]
error_codes: ["C2065", "C2039", "C2027"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-errors-1/compiler-error-c2065
source: 来源：MS 官方文档 + 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

编译 C++ 时报：

```
error C2065: 'UMyThing': undeclared identifier
error C2039: 'Foo': is not a member of 'UMyClass'
```

通常出现在：新写了一段代码、升级引擎版本、或者改了头文件之后。

## 常见根因（按概率排序）

1. **缺 include**（约 55%）：用了某类型但没 include 它的头文件
2. **头文件包含顺序 / 前向声明不够**（约 20%）：只前置声明了 `class UMyThing;`，但代码里要访问它的成员
3. **UE 版本升级后 API 改名或换模块**（约 15%）：旧的 `#include "Engine.h"` 之类
4. **拼写 / 大小写**（约 10%）：UE 的类名区分大小写，`UMyThing` 写成 `UmyThing`

## 排查步骤

1. 从报错抄下**标识符全名**，在引擎源码（或 IDE 的 Go to Definition）里确认它属于哪个头文件、哪个模块
2. `C2039 is not a member of` 说明类型找到了但成员不对 → 多半是版本差异
3. 检查 `.Build.cs` 是否包含该类型所在模块

## 修复方案

1. 补 include：`#include "Components/StaticMeshComponent.h"` 这类**具体路径**，不要图省事 include 大杂烩
2. 加模块依赖到 `.Build.cs`，再重新生成工程文件
3. 版本升级导致的改名：查该版本的 **Upgrade Notes / Deprecation** 列表，按新 API 改

## 容易误判的情况

- `C2065` 的**第一条**才是根因，后面几十条常常是连带错误；修第一条后重新编译再判断
- 如果报错指向**引擎自己的头文件**，通常是引擎没编译完 / 安装损坏，不是项目代码问题
- IntelliSense 画红线但编译能过 → 是 IDE 缓存问题，**不要**照着红线改代码
