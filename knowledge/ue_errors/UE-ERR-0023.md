---
id: UE-ERR-0023
title: 打包失败 DirectoryNotFoundException 找不到 Intermediate\Source\<项目名>.Target.cs
category: build
keywords: [打包失败, 打包报错, BUILD FAILED, ExitCode=1, DirectoryNotFoundException, Target.cs 找不到, 纯蓝图工程打包, 无源码项目打包, 改成 C++ 工程后打包失败, 加源码后打包报错, 蓝图工程打包报错, Turnkey, BuildCookRun, 打包 Unknown Error]
error_codes: ["DirectoryNotFoundException", "Could not find a part of the path", "Intermediate\\Source", "Target.cs", "ExitCode=1", "PackagingResults: Error: Unknown Error"]
source_url: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-automation-tool-for-unreal-engine
source: 来源：真实用户提交的打包日志（UE 5.7）+ 用户回访确认修复 + 人工整理
updated: 2026-10-15
repro: 同一个工程先作为无源码项目（纯蓝图）打包，之后改成有源码项目（C++ 工程）再打包即必现；删掉 Intermediate 重新打包恢复正常
---
## 症状

编辑器里点「打包」（Platforms → Windows → Package Project），或者跑 BuildCookRun 时，日志最后是：

```
UATHelper: Warning: 打包 (Windows): Cleaning old temporary Target files for MyProject
    because it no longer being treated as a code-based project for any enabled platform.
UATHelper: Error: 打包 (Windows): System.IO.DirectoryNotFoundException:
    Could not find a part of the path 'F:\MyProject\Intermediate\Source\MyProject.Target.cs'.
   at Microsoft.Win32.SafeHandles.SafeFileHandle.CreateFile(...)
   at System.IO.File.ReadAllBytesAsync(String path, CancellationToken cancellationToken)
   at UnrealBuildTool.DynamicCompilation.ParseSyntaxTreeAsync(...)
(see C:\Users\<用户>\AppData\Roaming\Unreal Engine\AutomationTool\Logs\D+UE_5.7\Log.txt for full exception trace)
UATHelper: 打包 (Windows): AutomationTool exiting with ExitCode=1 (Error_Unknown)
UATHelper: 打包 (Windows): BUILD FAILED
PackagingResults: Error: Unknown Error
```

几个容易看漏的上下文特征（这份日志里都有）：

- 项目**没有 `Source/` 目录**，是纯蓝图工程；UAT 命令行里带 **`-nocompile -nocompileuat`**
- 报错**紧跟在** `Setting up ProjectParams for ...uproject` 之后，`Parsing command line` 阶段是好的
- 前面还有一句 `UATHelper: 打包 (Windows): BUILD SUCCESSFUL`——那是 Turnkey 校验 SDK 那一步的成功，**不是**打包成功
- 抛异常的调用链里出现 `DynamicCompilation.ParseSyntaxTreeAsync`，说明 UBT 正在**读一个本该由它自己生成的 .cs 文件**

**已确认的复现路径（实测）**：同一个工程先作为**无源码项目**（纯蓝图工程）打过包，之后改成**有源码项目**（加了 `Source/`、成为 C++ 工程）再打包，就必现这个报错；**删掉 `Intermediate` 重新打包即恢复正常**。

## 常见根因（按概率排序）

1. **工程从「无源码项目」改成「有源码项目」后 `Intermediate` 状态不一致**（约 40%，**已实测确认**）：`Intermediate/Source/*.Target.cs` 是 UBT 按「当前是不是代码工程」动态生成/清理的；无源码项目打包时按非代码工程生成/清过一套，改成有源码项目再打包时，UBT 一边清理旧的、一边去读新的，就命中这个异常。删掉 `Intermediate` 重新打包即可恢复
2. **`Intermediate/` 被删/被清，临时 Target 文件没重建**（约 30%）：手动删过 `Intermediate`、清理软件/磁盘清理工具清空过它，或上次打包中断留下半残状态；随后 UBT 又执行了上面那句 "Cleaning old temporary Target files"，把 `Intermediate\Source` 下的文件清掉后立刻去读，就报这个异常
3. **项目从别的机器/网盘拷过来，少了 `Intermediate`**（约 15%）：新机器上第一次打包时，`Intermediate/Source/*.Target.cs` 从来没生成过
4. **中途打断 / 杀软、同步盘占用**（约 10%）：打包过程中 `Intermediate` 被锁或被动过，文件处于「刚被清理、尚未重写」的窗口
5. **引擎装在非默认盘（如 `D:\UE_5.7`）+ 项目在另一盘（`F:\`）时的路径状态错乱**（约 5%）：不常见，但出现「路径明明该有却没有」时可怀疑

> 注意区分两个方向：**从有源码项目改成无源码项目**时，只会出现「no longer being treated as a code-based project」那类清理警告（警告本身无害）；**从无源码项目改成有源码项目**才会变成上面的致命异常。

## 排查步骤

1. 先定位**第一条 Error**，不要看最后的 `PackagingResults: Error: Unknown Error`——后者没有信息量
2. 到资源管理器里确认这个文件到底在不在：
   ```powershell
   Test-Path 'F:\MyProject\Intermediate\Source\MyProject.Target.cs'
   Get-ChildItem 'F:\MyProject' -Force | Select-Object Name      # 看有没有 Source / Intermediate
   ```
3. 确认工程类型：有 `Source/<项目名>/<项目名>.Build.cs` 就是代码工程；没有就是**纯蓝图工程**（本报告属于这种），处理方式不同
4. 看日志里有没有紧邻的 `Cleaning old temporary Target files ...` 警告——有就基本坐实是「清理掉了又去读」
5. 关掉编辑器（UAT/UBT 不能和编辑器同时写 `Intermediate`），再操作下一步

## 修复方案

1. **删掉整个 `Intermediate` 目录，然后重新打包**（实测有效，优先做这个）：
   - 完全关闭 UE 编辑器和 VS/Rider（UAT/UBT 不能和编辑器同时写 `Intermediate`）
   - 删除 `F:\MyProject\Intermediate`（**不要删 `Content` 和 `Config`**）
   - 重新打开项目，确认 `Intermediate\Source\MyProject.Target.cs` 已按当前工程类型重新生成，再打包
   - 从无源码项目改成有源码项目时，**改动之后第一次打包前**就该做这一步
2. 只想重建 Target 文件、不想开编辑器：在项目目录下执行
   ```powershell
   & 'D:\UE_5.7\Engine\Build\BatchFiles\GenerateProjectFiles.bat' -project="F:\MyProject\MyProject.uproject" -game -rocket
   ```
   或右键 `MyProject.uproject` → **Generate Visual Studio project files**
3. 删了 `Intermediate` 仍报同样的错：再依次删 `Saved`、`Binaries`（`Saved` 是缓存与日志，删掉不丢资产）后重开项目；确认 `.uproject` 里的 `Modules` 列表与磁盘上的 `Source/` 一致
4. 如果这个工程**本来有 C++**（`Source/` 被误删）：恢复 `Source/<项目名>/`、`<项目名>.Build.cs` 与 `Source/<项目名>.Target.cs`，或干脆用「C++ 基础工程」模板新建一份再把 `Content`/`Config` 搬过去；纯蓝图工程则**不需要**这些文件
5. 换一个干净的输出目录再打包（本报告用的是 `E:/Dabao5.7/MyProject`）：输出目录不要放在项目目录里、不要放在会被同步/清理工具处理的盘符下
6. 别让打包中断：打包期间不要点 Cancel、不要用杀软全盘扫描、不要用网盘同步 `Intermediate`

## 容易误判的情况

- **`PackagingResults: Error: Unknown Error` 不是根因**，它只是「UAT 以非零码退出」的兜底文案；真正原因在上面那条 `DirectoryNotFoundException`
- 日志里的 `BUILD SUCCESSFUL`（Turnkey SDK 校验那一段）**不代表打包成功**，别拿它去否定报错
- 那一大段 `at Microsoft.Win32...` / `at UnrealBuildTool...` 是 UBT 内部的托管调用栈，**不用逐行读**，只要看清异常类型（`DirectoryNotFoundException`）和缺失路径
- **不要手写一个 `Intermediate\Source\MyProject.Target.cs` 塞进去**：那是 UBT 的生成物，手写的没有 `.uproject` 状态支撑，会引出新的构建规则错误；正确做法是让它重建
- 这条与 C++ 编译错误无关：日志里没有 `C2065`/`LNK2019` 这类错误码；看到 C1083「无法打开包括文件」才该去看 UE-ERR-0006 / UE-ERR-0020
- 与 UE-ERR-0021（插件预编译清单缺失）区分：那条报 `Missing precompiled manifest` 且指向 `Plugins/`；本条指向项目自己的 `Intermediate/Source`
- 「工程能被编辑器正常打开、只是打包失败」很正常——编辑器用的是另一套临时文件路径，不要因为能打开就认为 `Intermediate` 是完好的
- 见到那句 `Cleaning old temporary Target files ... no longer being treated as a code-based project` **不要**去改 `.uproject` 或手加 `Source/`：它多半只是切换构建类型时的正常清理动作，真正的致命错误是紧跟其后的异常
