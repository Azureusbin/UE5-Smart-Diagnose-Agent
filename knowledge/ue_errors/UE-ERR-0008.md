---
id: UE-ERR-0008
title: 编译错误 C2662 / C2663 不能将 this 指针从 const 转换为非 const
category: compile
keywords: [const 报错, 常量成员函数, 不能将 this 指针转换, 在 const 函数里改数组, 编译不过 const, 无法将参数从 const 转换, TArray Add 报错]
error_codes: ["C2662", "C2663", "C2678", "cannot convert 'this' pointer", "discards qualifiers"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-errors-1/compiler-error-c2662
source: 来源：MS 官方文档（C2662/C2663）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

给成员函数加了 `const`（或重写了一个 `const` 的引擎虚函数）之后，编译报：

```
Tank.cpp(42): error C2662: "int32 TArray<int32,TSizedDefaultAllocator<32>>::Add(const int32 &)": 不能将 "this" 指针从 "const TArray<...>" 转换为 "TArray<...> &"
Tank.cpp(50): error C2663: "UMyTank::Fire": 2 个重载没有 "this" 指针的合法转换
MyTank.h(18): error C2678: 二进制"=": 没有找到接受"const FMyConfig"类型的左操作数
```

报错里总会出现 `const` 和 `this 指针` 这两个词。

## 常见根因（按概率排序）

1. **在 `const` 成员函数里改了成员**（约 55%）：`int32 GetAmmo() const { Ammo--; }` 这类笔误，或调的 helper 忘加 `const`
2. **该函数不该是 const**（约 20%）：它确实要改状态（扣血、加数组），声明时就写错了 `const`
3. **调的另一个成员函数不是 const**（约 15%）：本函数是 const，但它调了非 const 的 `Recalc()`
4. **容器/迭代器 const 用法错**（约 10%）：对 `const TArray&` 调 `Add`/`Remove`，或 `for (auto& X : ConstArray)` 想改元素

## 排查步骤

1. 报错行号定位到 `.cpp` 那行，看它**碰了哪个成员变量**（报错会点名 `Add`、`operator=`、成员函数名）
2. 回到头文件看该函数签名有没有 `const`，以及被它调用的成员函数有没有 `const`
3. 分清两种意图：只想读 → 给被调函数补 `const`；真要写 → 去掉本函数的 `const`

## 修复方案

1. 只读的场景，给整条调用链补 `const`：
   ```cpp
   int32 UMyTank::GetAmmo() const { return Ammo; }        // 只读就 const
   bool  UMyTank::CanFire() const { return Ammo > 0; }    // 改成读 Ammo，或由调用方判
   ```
2. 要改状态的场景，去掉 const（不要用 `mutable` 硬压过去）：
   ```cpp
   void UMyTank::Fire() { Ammo--; }   // 不是 GetXxx，就别带 const
   ```
3. 只想遍历不改元素时用 `const auto&`；要改就用非 const 引用：
   ```cpp
   for (const FMyConfig& Cfg : Configs) { /* 只读 */ }
   ```
4. 覆写引擎虚函数时**照抄基类签名**（含 `const`、`override`），签名不一致会另外报 C3668 / override 相关错误

## 容易误判的情况

- `C2662/C2663` 的**根因往往在被调用的那个函数上**，报错行只是「受害者」；先看它调的谁
- 别为了消错就 `const_cast` 或把成员全加 `mutable`——那只是把编译期能发现的问题推迟到运行期
- 如果报错出现在**引擎头文件的 inline 函数里**，通常是你传进去的类型不对（如传了 const 引用），不是引擎的问题
