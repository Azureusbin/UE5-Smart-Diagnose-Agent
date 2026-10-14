---
id: UE-ERR-0011
title: 编译错误 C4996 / deprecated API 已弃用（引擎升级后重灾区）
category: compile
keywords: [升级引擎后编译不过, 弃用 API, deprecated, C4996, 函数被标记为已弃用, UE4 升 UE5 编译报错, 旧写法不能用了]
error_codes: ["C4996", "C4800", "deprecated", "UE_DEPRECATED"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-warnings/compiler-warning-level-3-c4996
source: 来源：MS 官方文档（C4996）+ Epic 升级说明 + 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

把工程从旧版本（UE4 → UE5，或 UE5.1 → 5.4/5.5）升上来之后，一编译刷屏：

```
Tank.cpp(88): error C4996: "UMyTank::FireWeapon": FireWeapon 已弃用: 请改用 FireWeaponAt
Tank.cpp(95): error C4996: "AActor::GetActorLocationAndRotation": 已弃用
```

或报已删除的宏 / 类型：

```
error C2039: "GetRootComponent": 不是 "AActor" 的成员
error C2065: "TSubclassOf": 未声明的标识符
```

## 常见根因（按概率排序）

1. **引擎版本升级，API 改名 / 换模块**（约 50%）：UE5 把很多返回裸指针的接口换成 `TObjectPtr<T>`，把 `FString::operator+` 之类做了收紧
2. **第三方插件还是老版本**（约 20%）：插件内部用的旧 API 在你新引擎上被删了
3. **一直在用非公开 API**（约 15%）：`Private/` 下的头文件、`ENGINE_API` 没标的函数，升级后就没了
4. **弃用但没删**（约 15%）：编译能过只是 warning，别的地方开了 warnaserror 就变错误

## 排查步骤

1. 读 C4996 的**后半句提示**——UE 通常直接写了替换方案（`请改用XXX`），这是最快的修复线索
2. 到引擎源码里搜那个旧符号（VS 里 F12 / 或在引擎 `Source/` 里全文搜），看它现在是改名了、还是移到了别的模块
3. 查对应版本的 **Upgrade Notes / Deprecations** 页面，确认改动是有意的还是需要新模块依赖

## 修复方案

1. 按提示换新 API，例如：
   ```cpp
   // 旧
   // FireWeapon();
   // 新
   FireWeaponAt(MuzzleLocation);
   ```
2. 指针成员统一改成 `TObjectPtr<T>`（UE5 推荐，UPROPERTY 里裸指针会报弃用）：
   ```cpp
   UPROPERTY() TObjectPtr<UStaticMeshComponent> Mesh;
   ```
3. 换了模块的 API：在 `.Build.cs` 里补依赖，再重新生成工程文件
4. 插件导致的：优先升级插件；它没更新就换插件，或把那段代码搬进自己的模块

## 容易误判的情况

- **C4996 有时只是 warning**，但因为 UE 开了 `bWarningsAsErrors` 而编译失败——别急着全局关警告，先按提示换 API
- 「升级后报一堆找不到的符号」不一定是 API 删除，**也可能是没重新生成工程文件**（见 UE-ERR-0006），先重新生成再看
- 用 `#pragma warning(disable : 4996)` 压下去能让今天编译过，但等这个 API 真被删（下个大版本）时会一次性爆掉，属于技术债
