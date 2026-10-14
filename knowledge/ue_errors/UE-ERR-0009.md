---
id: UE-ERR-0009
title: generated.h 必须放在 include 最后一行（include 顺序错误）
category: compile
keywords: [include 顺序, generated.h 放哪, 头文件顺序, UCLASS 报错, 找不到 class, 编译错误 头文件, UHT 报 找不到类型, 循环 include]
error_codes: ["generated.h", "Unable to find 'class'", "does not have a GENERATED_BODY", "C2504", "base class undefined"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-uproject-file-format
source: 来源：Epic 官方文档 + 社区实践 + 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

头文件的 include 顺序不对时，编译/UHT 报这些看着毫不相关的错：

```
MyTank.h(8): Error:  Unable to find 'class' with name 'UMyTankBase'
MyTank.h(14): Error:  UMyTank does not have a GENERATED_BODY or GENERATED_UCLASS_BODY
MyTank.h(20): error C2504: "UMyTankBase": 未定义基类
```

典型场景：自己手写了 `#include "MyTank.generated.h"`，但把它放在了**其他 include 的上面**（尤其是放在了基类头文件前面）。

## 常见根因（按概率排序）

1. **`.generated.h` 不是最后一个 include**（约 70%）：IDE 的自动 include 补全把它顶到前面去了
2. **基类只做了前向声明**（约 15%）：`class UMyTankBase;` 不够，继承基类必须看到**完整定义**，要 include 基类头文件
3. **两个头文件互相 include**（约 10%）：A.h 含 B.h、B.h 又含 A.h，前向声明能解决
4. **顺序对了但没重新生成工程**（约 5%）：改了 include 但工程文件/中间产物是旧的

## 排查步骤

1. 打开报错的头文件，看最后一行 include 是不是 `#include "XXX.generated.h"`——**必须是最后一行，后面不能再有 #include**
2. 报 `未定义基类 / base class undefined` 时，检查这个类的基类头文件有没有被 include（前向声明不算）
3. 报 `does not have a GENERATED_BODY` 时，检查宏写在不在类体第一行、有没有被 `#if` 包住

## 修复方案

1. 按 UE 官方顺序整理头文件：
   ```cpp
   #include "CoreMinimal.h"
   #include "GameFramework/Actor.h"
   #include "Components/StaticMeshComponent.h"
   #include "MyTank.generated.h"      // ← 永远最后一个
   ```
2. 头文件里能用前向声明就别 include（减少循环依赖）：
   ```cpp
   class UStaticMeshComponent;        // 声明
   UPROPERTY() TObjectPtr<UStaticMeshComponent> Mesh;   // 只用在指针成员，够了
   ```
   只有在**继承基类、按值使用、调它的成员函数**时才必须在头文件里 include 完整定义。
3. 出现互相 include 时，把其中一边改成前向声明 + 在 .cpp 里 include
4. 改完 include 后重新生成工程文件再编译

## 容易误判的情况

- 这条错误的报错文本**完全不提 include 顺序**，只会在你顺着文件往下看时才发现——所以「莫名找不到自己刚写的类」优先怀疑这一条
- `C2504 未定义基类` 也可能是**模块依赖没配**（基类在别的模块里），见 UE-ERR-0012
- 头文件里 include 顺序问题在 VS 里可能只在**你打开那个文件时**才报，切走就消失，别当成 IDE 抽风
