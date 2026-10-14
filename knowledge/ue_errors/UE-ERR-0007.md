---
id: UE-ERR-0007
title: UHT 反射宏报错 「Unrecognized type」/ GENERATED_BODY 缺失
category: compile
keywords: [UHT 报错, UnrealHeaderTool, 反射宏, UCLASS, USTRUCT, UPROPERTY, GENERATED_BODY, 生成代码失败, 结构体编译不过, 反射相关报错]
error_codes: ["Unrecognized type", "Expected a class or struct", "must be a member of", "Missing 'GENERATED_BODY'", "LogUnrealHeaderTool"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-header-tool-for-unreal-engine
source: 来源：Epic 官方文档（UHT / 反射）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

编译前先跑 Unreal Header Tool，UHT 阶段就失败，还没轮到 C++ 编译器：

```
[1/4] MyTank.h(12): Error: Unrecognized type 'FMyConfig' - type must be a UCLASS, USTRUCT or UENUM
[2/4] MyTank.h(20): Error: Missing 'GENERATED_BODY' in 'UMyTank' - UCLASS requires it
[3/4] UnrealHeaderTool failed for target 'MyGameEditor'
```

编辑器里表现为「编译失败」但看不到 C++ 错误码，只有 `LogUnrealHeaderTool` 的输出。

## 常见根因（按概率排序）

1. **UPROPERTY 的类型不可反射**（约 40%）：属性类型不是 UCLASS/USTRUCT/UENUM，也不是允许的基础类型（裸 `std::string`、自定义非 USTRUCT 结构体、模板容器里的元素不合法）
2. **漏写宏**（约 25%）：UCLASS/USTRUCT 里没写 `GENERATED_BODY()`，或写在 `public:` 之后
3. **USTRUCT 里放了不能有的东西**（约 15%）：`UFUNCTION`、构造函数带参、继承 UObject、指针成员没加 `UPROPERTY`
4. **宏位置/写法错**（约 10%）：UCLASS 的参数写错（如 `UCLASS(Blueprintable)` 写成 `UCLASS("Blueprintable")`）
5. **枚举没写对底层类型**（约 10%）：`UENUM` 想暴露给蓝图却漏了 `: uint8`

## 排查步骤

1. 看 UHT 报的**第一条** Error，它会给出文件名 + 行号 + 具体类型名
2. 到那一行确认：类型是不是 `U`/`F`/`E` 打头且带反射宏？属性有没有 `UPROPERTY()`？
3. 编辑器 Output Log 里筛 `LogUnrealHeaderTool`，比看 VS 输出窗口更清楚

## 修复方案

1. 给要用在 `UPROPERTY` 里的自定义结构体补反射，注意 `GENERATED_BODY()` 必须在结构体**第一行**：
   ```cpp
   USTRUCT(BlueprintType)
   struct FMyConfig
   {
       GENERATED_BODY()
       UPROPERTY(EditAnywhere, BlueprintReadWrite) float Range = 1000.f;
   };
   ```
2. 暴露给蓝图的枚举一定写底层类型：`UENUM(BlueprintType) enum class EMyState : uint8 { Idle, Fire };`
3. `UPROPERTY` 里**不要**用 `std::` 容器和裸指针，换成 `TArray` / `TMap` / `TObjectPtr<T>` / `TSoftObjectPtr<T>`
4. 改完 UCLASS/USTRUCT 结构后重新生成工程文件再编译，别指望热重载

## 容易误判的情况

- UHT 的报错**经常连带刷一屏**，第一条才是根因，后面多是「因为上面失败所以没生成」
- 「Unrecognized type」有时指向的是**引擎自带的类型**，那多半是漏 include 或漏模块依赖（见 UE-ERR-0005 / UE-ERR-0012），不是反射写错
- 只改 .cpp 里的逻辑不会触发 UHT；**改动反射宏必须重新编译**，Live Coding 有时跟不上，重启编辑器最稳
