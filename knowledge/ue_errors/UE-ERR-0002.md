---
id: UE-ERR-0002
title: 游戏崩溃 EXCEPTION_ACCESS_VIOLATION 访问违例（空指针）
category: crash
keywords: [崩溃, 闪退, 空指针, 访问违例, 一进游戏就崩, 开火崩, 崩溃弹窗, 报错弹窗]
error_codes: ["EXCEPTION_ACCESS_VIOLATION", "Fatal error", "Unhandled Exception"]
source_url: https://dev.epicgames.com/community/learning/tutorials
source: 来源：Epic 社区 + 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

游戏直接闪退，或弹出 `Fatal error!` 对话框；`Saved/Logs/*.log` 末尾出现：

```
LogWindows: Error: === Critical error: ===
LogWindows: Error: Fatal error!
LogWindows: Error: Unhandled Exception: EXCEPTION_ACCESS_VIOLATION reading address 0x0000000000000000
[Callstack] 0x0000... UnrealEditor-MyGame.dll!UMyTank::OnFire() [D:\Proj\Source\MyGame\Tank.cpp:88]
[Callstack] 0x0000... UnrealEditor-Engine.dll!UWorld::Tick(...)
```

关键词：`reading address 0x0`（读空指针）、`writing address`（写非法地址）。

## 常见根因（按概率排序）

1. **指针为空就用了**（约 60%）：`GetOwner()`、`GetWorld()`、`Cast` 结果没判空
2. **对象已被销毁**（约 20%）：异步回调 / Timer / 动画通知触发时，Actor 已经 `Destroy()` 了
3. **数组越界**（约 10%）：索引没做 `IsValidIndex` 检查
4. **访问了正在被 GC 或加载中的资源**（约 10%）

## 排查步骤

1. 看崩溃栈里**第一个业务帧**（非 Engine/非 UnrealEditor-Engine 的那一行），那基本就是出错位置
2. 打开对应 `.cpp` 的行号，检查该行用到的所有指针
3. 确认这个函数是被谁调用的（事件 / Timer / 动画通知），触发时机是否对象还活着

## 修复方案

1. 所有可能为空的返回值在使用前判空：
   ```cpp
   if (UWorld* World = GetWorld()) { /* 再用 */ }
   ```
2. 用 `IsValid(Obj)` 替代裸指针判断（能同时挡掉「已销毁但内存还在」）
3. 异步回调里绑定 `TWeakObjectPtr`，并在回调开头 `if (!WeakPtr.IsValid()) return;`
4. 数组访问前 `if (Arr.IsValidIndex(i))`

## 容易误判的情况

- **栈顶是引擎模块**（`UnrealEditor-Engine.dll`、`CoreUObject`）不代表引擎有 bug，通常是你传了非法参数进去
- `Ensure condition failed` 不是崩溃，是断言失败（见 UE-ERR-0004），**不要**按崩溃处理
- 只有 `0xC0000005` 这种地址码而没有 Callstack：先确认符号是否正确加载，再谈定位
