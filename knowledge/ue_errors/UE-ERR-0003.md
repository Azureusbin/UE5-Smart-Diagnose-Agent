---
id: UE-ERR-0003
title: 蓝图编译失败 LogBlueprint could not be compiled
category: compile
keywords: [蓝图编译, 蓝图报错, 编译不过, 蓝图打不开, 构造脚本, 循环依赖, 组件丢失]
error_codes: ["LogBlueprint", "could not be compiled", "Error: [Compiler]"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprints-visual-scripting-in-unreal-engine
source: 来源：Epic 官方文档 + 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

打开或保存蓝图时报错，Output Log / Message Log 里出现：

```
LogBlueprint: Error: [Compiler] BP_Tank : Could not be compiled. Please fix the compile errors...
LogBlueprint: Error: [Compiler] BP_Tank  Error:  This blueprint has compile errors
```

蓝图标题栏出现感叹号，编辑器提示「Blueprint could not be compiled」。

## 常见根因（按概率排序）

1. **引用了被删除的资产/组件**（约 35%）：蓝图里连着一个已被删掉的组件或类，节点变红
2. **父类改过签名**（约 25%）：父类 C++ 改了函数参数/名字，子蓝图里的节点失效
3. **构造脚本里有非法操作**（约 20%）：在 Construction Script 里做了只能运行时做的事（如访问 World、Spawn）
4. **蓝图循环依赖**（约 10%）：A 引用 B，B 又引用 A
5. **同名类冲突 / 热重载残留**（约 10%）

## 排查步骤

1. 打开蓝图，看**哪些节点是红色**——编译器会直接指出位置
2. Output Log 里搜 `LogBlueprint`，读**第一条** Error（后面的常常是连带错误）
3. 若是父类改动引起：用「Refresh Nodes」（右键节点 → Refresh Node）重连一遍

## 修复方案

1. 删掉红色节点并重新连；如果是被删组件，从 Components 面板重新添加同名组件
2. 父类改动：修好 C++ 后**编译 C++，再重启编辑器**（热重载不可靠），然后 Refresh Nodes
3. 构造脚本里的非法操作，挪到 `BeginPlay` 里
4. 循环依赖：把公共部分抽到一个 `BPL_` 前缀的蓝图函数库或 C++ 里

## 容易误判的情况

- **打开蓝图时弹的「有未保存改动」不是编译错误**，别混在一起
- 只有重启编辑器后才消失的报错，多半是热重载残留，**不是**蓝图本身的错
- 报错提到 `CDO`（Class Default Object）通常是构造脚本问题，不是运行时逻辑
