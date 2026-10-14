---
id: UE-ERR-0018
title: UnrealBuildTool 报错 Build.cs 写法错误 / 找不到模块
category: build
keywords: [Build.cs 报错, UBT 报错, 找不到模块, 模块依赖没配, UnrealBuildTool failed, 加不上模块, 编译规则错误, ModuleRules]
error_codes: ["UnrealBuildTool", "ModuleRules", "Could not find definition for module", "MissingModuleRulesException", "CS0117", "CS0246"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-build-tool-in-unreal-engine
source: 来源：Epic 官方文档（UBT / Build.cs）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

还没到 C++ 编译，UnrealBuildTool 自己就失败：

```
[1/2] Compile [x64] MyGame.Build.cs
MyGame.Build.cs(8,36): error CS0246: 未能找到类型或命名空间名"ReadOnlyTargetRules"
UnrealBuildTool failed. See log for more details.
```

或：

```
ERROR: Could not find definition for module 'MyOtherModule' (referenced via Target.cs)
ERROR: Missing precompiled manifest for 'MyModule'
```

编辑器表现为「编译失败」，Output Log 里全是 UBT 的话。

## 常见根因（按概率排序）

1. **`Build.cs` 语法/API 错**（约 35%）：少了 `using UnrealBuildTool;`、类名没跟模块名一致、构造函数不叫 `ModuleRules` 规范名
2. **模块依赖没配或名字拼错**（约 30%）：代码里 include 了别的模块的头，但 `PublicDependencyModuleNames` 里没写，或写成错误大小写
3. **`.uproject` 的 Modules 列表与磁盘上 `Source/` 不一致**（约 20%）：删了模块没更新 .uproject，或新模块没登记
4. **Build.cs 版本不对**（约 10%）：从旧引擎拷来的写法用了已改名的 API（如 `bEnableShadowVariableWarnings` 之类）
5. **目标平台/配置写错**（约 5%）：`Target.cs` 里 `DefaultBuildSettings` 与新引擎版本不兼容

## 排查步骤

1. 精确定位：报错第一行会给出 `Build.cs` 文件名 + 行号 + CS 编号，按那个改
2. 把报错里的模块名与磁盘目录、`.uproject` 里的 `Modules` 列表三者对照
3. 想确认某个依赖名字对不对：在引擎 `Engine/Source/` 下找同名目录，**大小写必须完全一致**（如 `UMG`、`SlateCore`、`EnhancedInput`）

## 修复方案

1. 标准 `Build.cs` 骨架（照这个比对）：
   ```csharp
   using UnrealBuildTool;

   public class MyGame : ModuleRules
   {
       public MyGame(ReadOnlyTargetRules Target) : base(Target)
       {
           PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

           PublicDependencyModuleNames.AddRange(new string[] {
               "Core", "CoreUObject", "Engine", "InputCore",
               "EnhancedInput", "UMG"          // 用到什么加什么
           });

           PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
       }
   }
   ```
   注意：类名必须与模块名（也是目录名、也是 .Build.cs 前缀）一致。
2. 加依赖后**必须重新生成工程文件**再编译：右键 `.uproject` → Generate Visual Studio project files
3. 新模块要同时登记在两处：`.uproject` 的 `"Modules"` 数组 + `Source/<Module>/<Module>.Build.cs`
4. 改了依赖还报旧错：删 `Binaries/`、`Intermediate/` 后重新生成工程文件

## 容易误判的情况

- `Build.cs` 是 **C# 脚本**，报的是 `CSxxxx` 而不是 `Cxxxx`——看到 CS 就别去找 C++ 代码的问题
- 「Could not find definition for module X」里的 X 常在**你自己项目里**，但根因可能是 .uproject 没登记它，而不是依赖没加
- 只改 `.Build.cs` 不会自动生效，**热重载不处理构建规则**，一定要重新生成工程文件并整体重编
- 「Missing precompiled manifest」通常出现在装了 Marketplace 插件时，多半是插件版本与引擎不匹配（见 UE-ERR-0020），不是 Build.cs 本身写错
