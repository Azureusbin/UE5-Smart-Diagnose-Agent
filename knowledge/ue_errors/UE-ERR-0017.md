---
id: UE-ERR-0017
title: 编译错误 C4716 / C4715 函数必须返回值或并非所有路径都有返回值
category: compile
keywords: [必须返回一个值, 函数没有返回值, 缺 return, C4716, C4715, return 漏了, 警告当错误, 编译不过 没见过 的错]
error_codes: ["C4716", "C4715", "C2220", "must return a value", "not all control paths return a value"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-warnings/compiler-warning-level-1-c4716
source: 来源：MS 官方文档（C4716/C4715）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

```
Tank.cpp(88): error C4716: "UMyTank::GetAmmo": 必须返回一个值
Tank.cpp(112): error C4715: "UMyTank::ResolveState": 不是所有的控件路径都返回值
Tank.cpp(88): error C2220: 以下警告被视为错误 - 没有生成"object"文件
```

常见于：函数末尾忘了 `return`、`if/else` 少写了一条分支、`switch` 里只有部分分支 return。

## 常见根因（按概率排序）

1. **忘写 `return`**（约 45%）：改代码时把最后一行 return 删了/注释了
2. **分支没覆盖全**（约 30%）：`if (bA) return X;` 之后没有 `return Y;`，或 switch 缺 default
3. **返回值类型变了但没改函数体**（约 10%）：函数从 `void` 改成 `bool`，还没补返回值
4. **`check()`/`ensure()` 里提前退出**（约 10%）：以为 `check` 一定不会返回，编译器不这么认为
5. **模板实例化后才有返回路径问题**（约 5%）

## 排查步骤

1. 报错给了函数名和行号（行号常是函数结尾的 `}`），打开这个函数，逐条路径问「这条走到头会 return 吗」
2. 非 void 函数里所有 `if` 都要有对应的 `return` 或 `else` 分支
3. 函数末尾补一条兜底 `return`（即便逻辑上“到不了”）——编译器只需要静态可证明

## 修复方案

1. 分支补齐 + 末尾兜底：
   ```cpp
   bool UMyTank::CanFire() const
   {
       if (Ammo <= 0)  { return false; }
       if (bReloading) { return false; }
       return true;                     // 兜底，别靠编译器推断
   }
   ```
2. switch 返回型写法，`default` 也别漏：
   ```cpp
   FString UMyTank::StateName() const
   {
       switch (State)
       {
           case EMyState::Idle:   return TEXT("Idle");
           case EMyState::Firing: return TEXT("Firing");
           default:               return TEXT("Unknown");   // 同时消 C4062，见 UE-ERR-0010
       }
   }
   ```
3. 确实不该有返回值就把返回类型改回 `void`（比如只打日志的“查询”函数）
4. 想让「不可能走到这里」显式化，用 `checkNoEntry();` 或 `unimplemented()`，它们后面仍需满足返回要求时补 `return`

## 容易误判的情况

- C4716/C4715 **本来是 warning**，在 UE5 里因为 `bWarningsAsErrors` 直接变编译错误——不要为了过编译去关全局警告
- 报错函数名是 `XXX::operator=` 或 lambda 时，行号可能指向封闭的类/函数，**往上一层找那个函数体**
- 若报错出现在**别人写的插件**里而你没有源码维护权，优先升级插件，别去 `Intermediate/` 里改生成代码
