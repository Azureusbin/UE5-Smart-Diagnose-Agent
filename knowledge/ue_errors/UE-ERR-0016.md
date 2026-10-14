---
id: UE-ERR-0016
title: 编译错误 C2664 / C2665 无法将参数转换（FString 与 TCHAR 混用）
category: compile
keywords: [参数类型不匹配, 无法转换参数, FString 报错, 字符串类型不对, C2664, C2665, TEXT 宏, 中文乱码报错, 传参类型错]
error_codes: ["C2664", "C2665", "C2440", "cannot convert from", "no overload matches"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-errors-1/compiler-error-c2664
source: 来源：MS 官方文档（C2664/C2665/C2440）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

调引擎 API 时参数类型不对：

```
Tank.cpp(52): error C2664: "void UGameplayStatics::PlaySound2D(...)": 无法将参数 2 从 "const char [6]" 转换为 "USoundBase *"
Tank.cpp(60): error C2665: "FString::Printf": 没有重载函数可以转换所有参数类型
Tank.cpp(77): error C2440: "初始化": 无法从 "const char *" 转换为 "FString"
```

常见的“字符串类”报错：`L"..."`、`"..."`、`TEXT("...")`、`FString`、`FName`、`FText` 四者互转写错。

## 常见根因（按概率排序）

1. **字符串字面量忘了 `TEXT()`**（约 35%）：`LogTemp("hi")` 应为 `UE_LOG(..., TEXT("hi"))`；UE 默认 `TCHAR` 是宽字符，`"abc"` 是窄字符
2. **参数顺序/类型看错**（约 25%）：给了 `FName`，函数要 `FString`（或反过来）；把 `UClass*` 和 `TSubclassOf<>` 混用
3. **`FString` 与 `const TCHAR*` 混用**（约 20%）：需要 `*MyFString` 或 `MyFString.Len() > 0` 判断
4. **传了错误的重载参数个数**（约 10%）：可变参数 `Printf` 的格式串和实参不匹配
5. **CVar / 枚举隐式转换**（约 10%）：`int32` 传 `float` 位置、`uint8` 传枚举

## 排查步骤

1. 读报错的三段：**函数全名 + 第几个参数 + 从什么类型到什么类型**，直接对着改
2. 看目标函数的真实签名（F12 Go to Definition），别猜
3. `C2665 没有重载匹配` 多是**可变参数**：检查 `Printf` 的格式串 `%s/%d/%f` 与实参是否一一对应

## 修复方案

1. 字符串字面量统一加 `TEXT()`：
   ```cpp
   UE_LOG(LogTemp, Warning, TEXT("Ammo = %d"), Ammo);
   FString Msg = TEXT("已装填");
   ```
2. 三种字符串类型按用途选，转换写全：
   ```cpp
   FName   Key   = FName(TEXT("Ammo"));        // 资源名/键：FName
   FString Path  = Key.ToString();             // FName → FString
   FText   Label = FText::FromString(Path);    // FString → FText（给 UI）
   const TCHAR* Raw = *Path;                   // FString → const TCHAR*
   ```
3. 蓝图类引用用 `TSubclassOf<AActor>`，不要直接传 `UClass*`；要 `UClass*` 时写 `MyClass.Get()`
4. 参数类型不匹配又确实想传：显式构造目标类型（`FString(MyName)`），别指望隐式转换

## 容易误判的情况

- `error C2664 ... 无法将参数 ... 从 "const char [6]"` 十有八九就是**漏了 TEXT()**，不用怀疑引擎
- `%s` 在 UE 的 `FString::Printf` 里要传 `TCHAR*`（`*FString`），传 `FString` 对象会再报一条 C2664
- 报错行看起来完全正确时，注意**宏展开**：`UE_LOG`/`check` 里的错误常把行号指到宏使用处而不是真实位置，往上一行看调用参数
