---
id: UE-ERR-0010
title: 编译错误 C4062 枚举值未在 switch 中处理（UE5 默认当错误）
category: compile
keywords: [switch 枚举报错, 枚举没处理完, C4062, 警告被当成错误, TreatWarningsAsErrors, 新增枚举值就编译不过, 枚举未处理的分支]
error_codes: ["C4062", "C4061", "not handled in switch", "warning treated as error"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-warnings/compiler-warning-level-4-c4062
source: 来源：MS 官方文档（C4062）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

给某个枚举加了新值之后，编译突然失败：

```
Tank.cpp(66): error C4062: 枚举器"EMyState::Reloading"在 switch 中未处理
Tank.cpp(66): error C2220: 以下警告被视为错误 - 没有生成"object"文件
```

或：

```
warning C4061: 枚举器"EMyState::Reloading"在 switch 中未由 case 标签显式处理
```

关键点：UE5 默认开了 warnaserror，**警告会直接中断编译**。

## 常见根因（按概率排序）

1. **枚举加了新值但 switch 没跟着加分支**（约 65%）：尤其是引擎升级 / 别人提交了新枚举项
2. **蓝图的枚举（UENUM）改了但 C++ 侧 switch 没同步**（约 15%）
3. **自己开了 `bWarningsAsErrors` / `/WX`**（约 10%）：把本来只是 warning 的东西变成了 error
4. **switch 里没有 `default:`**（约 10%）：C4062/C4061 就是专挑「没有 default 又没覆盖全」的情况

## 排查步骤

1. 看报错里点名的**枚举值全名**（`EMyState::Reloading`），它直接告诉缺哪个分支
2. 打开那个 switch，确认是「漏了」还是「故意忽略」
3. `C2220 「以下警告被视为错误」`出现的，**根因是它上面那条 warning**，只看 C2220 会白忙

## 修复方案

1. 补上分支（最推荐）：
   ```cpp
   switch (State)
   {
       case EMyState::Idle:      break;
       case EMyState::Firing:    break;
       case EMyState::Reloading: OnReload(); break;   // 新增的补上
       default:                  break;
   }
   ```
2. 确实想显式忽略剩下的，用 `default:` 兜底而不是 `#pragma warning(disable:4062)`
3. 只想让某个文件降级警告（临时手段，别当常规做法）：在 `.Build.cs` 里针对该模块关掉，或文件头 `#pragma warning(disable : 4062)`——**记得留 TODO 注释**
4. 由引擎版本升级引入的：在 `Config/DefaultEngine.ini` 里核对 `[/Script/UnrealEd.ProjectPackagingSettings]` 之外，更该做的是跟着 Upgrade Notes 把 switch 补全

## 容易误判的情况

- **C4062 是 warning 编号，但 UE5 里它让你编译不过**——不要因为「只是个警告」就去关掉全局 warnaserror
- 报 `C2220` 时先往上找那条真正的 warning，C2220 本身没有信息量
- 如果错误的行号指向**你自己没写过的 switch**（引擎或插件代码），通常是它们在新引擎版本里还没适配，考虑升级/替换该插件，而不是去改引擎源码
