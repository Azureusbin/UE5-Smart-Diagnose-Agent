---
id: UE-ERR-0004
title: Ensure condition failed 断言失败（不是崩溃）
category: crash
keywords: [Ensure, 断言, Assertion failed, 弹窗警告, 黄色警告, 没崩但报错]
error_codes: ["Ensure condition failed", "Assertion failed", "LogOutputDevice"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/asserts-in-unreal-engine
source: 来源：Epic 官方文档（Asserts）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

游戏**没有崩溃**，但日志里出现：

```
LogOutputDevice: Warning: Ensure condition failed: World != nullptr [File:...Engine\Source\Runtime\Engine\...]
```

或弹出一个可以点「Continue / Break」的警告框。编辑器里出现黄色警告。

## 常见根因（按概率排序）

1. **调用时机不对**（约 45%）：在 `BeginPlay` 之前 / 构造脚本里访问了还没准备好的对象（World、PlayerController）
2. **传了空参数给带 Ensure 的引擎 API**（约 30%）
3. **网络复制顺序问题**（约 15%）：客户端在属性同步完成前就用了它
4. **项目自己代码里的 check/ensure 被触发**（约 10%）

## 排查步骤

1. 读 Ensure 的**条件表达式原文**（如 `World != nullptr`），它直接告诉你哪个东西不该为空
2. 看 `[File: ...]` 定位是引擎还是项目代码触发的
3. 看这行日志**前面几行**在做什么，确认调用时机

## 修复方案

1. 把访问挪到正确时机：`BeginPlay` / `PostInitializeComponents` / Timer 延迟一帧
2. 调用前判空并提前 return，不要靠 Ensure 兜底
3. 网络相关：在 `OnRep_` 回调里处理，不要在构造函数里读同步属性

## 容易误判的情况

- **Ensure 不是崩溃**，游戏通常还能继续跑；但如果频繁触发，后面很可能真的崩——先修 Ensure
- 不要为了「让日志干净」而直接注释掉引擎里的 ensure，那会掩盖真实问题
- 出包（Shipping）里 ensure 会被编译掉，所以「编辑器里报、打包后不报」是正常的，**不代表问题解决了**
