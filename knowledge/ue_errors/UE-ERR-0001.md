---
id: UE-ERR-0001
title: 链接失败 LNK2019 未解析的外部符号
category: build
keywords: [链接错误, 编译失败, 打包失败, 找不到函数, LNK2019, 未解析的外部符号, 第三方库]
error_codes: ["LNK2019", "LNK1120"]
source_url: https://learn.microsoft.com/cpp/error-messages/tool-errors/linker-tools-error-lnk2019
source: 来源：MS 官方文档 + 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

编译到链接阶段报错，日志里出现：

```
error LNK2019: unresolved external symbol "public: void __cdecl UMyClass::Foo(void)" ...
error LNK1120: 1 unresolved externals
```

常见于：新加了 C++ 类 / 调了某个引擎 API / 引入第三方库之后。

## 常见根因（按概率排序）

1. **函数只有声明没有实现**（约 50%）：头文件里写了声明，.cpp 里忘了实现，或实现没加进模块
2. **模块依赖没配**：用到了另一个 Module 的函数，但 `.Build.cs` 的 `PublicDependencyModuleNames` 里没加它
3. **第三方库没链接**：`lib` 没写进 `.Build.cs` 的 `PublicAdditionalLibraries`
4. **签名不一致**（约 10%）：声明和定义的参数/const 修饰不一致，链接器按名字找符号找不到

## 排查步骤

1. 从报错里抄下**完整符号名**（`?Foo@UMyClass@@...`），它比函数名更精确
2. 在项目里全文搜索这个函数名，确认有没有实现体
3. 看 `Source/<Project>/<Module>.Build.cs` 的依赖列表

## 修复方案

1. 补上实现，或把实现文件加入模块
2. 在 `.Build.cs` 里加依赖，例如：`PublicDependencyModuleNames.AddRange(new string[] { "MyOtherModule" });`
3. 改完 `.Build.cs` 必须**重新生成工程文件**（右键 .uproject → Generate Project Files），再编译

## 容易误判的情况

- 如果是 `LNK2019` 指向**引擎自己的函数**（如 `UEngine::Something`），通常是引擎版本不匹配或安装了不完整的引擎，不是项目代码问题
- 一个 `LNK2019` 常见会连带一串 `LNK1120`，**只修第一个**就行
