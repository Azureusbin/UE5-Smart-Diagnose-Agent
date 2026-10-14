---
id: UE-ERR-0014
title: 编译错误 C4335 Mac 行结束符 / UTF-8 BOM 与 C4819 编码问题
category: compile
keywords: [中文乱码报错, 编码问题, BOM, 行结束符, C4335, C4819, 从 mac 拷的代码, 拷贝代码编译不过, 中文注释报错]
error_codes: ["C4335", "C4819", "C2001", "Mac file format detected", "newline in constant"]
source_url: https://learn.microsoft.com/cpp/error-messages/compiler-errors-1/compiler-error-c4335
source: 来源：MS 官方文档（C4335/C4819）+ 人工整理（演示数据）
updated: 2026-10-13
---
## 症状

从 Mac / Linux / 网页复制粘贴过来的文件，编译直接失败在第一行附近：

```
CoreMinimal.h(1): error C4335: 检测到 Mac 文件格式: 请将源文件转换为 DOS 格式或 UNIX 格式
Tank.cpp(28): error C2001: 常量中有换行符
Tank.cpp(31): warning C4819: 该文件包含不能在当前代码页(936)中表示的字符
```

或者中文注释/中文字符串变成乱码，引号被“吃掉”，报「未结束的字符串」。

## 常见根因（按概率排序）

1. **行尾是 LF（Mac/UNIX）而非 CRLF**（约 45%）：C4335 专指这个，MSVC 有时能容错、有时直接报错
2. **文件不是 UTF-8**（约 25%）：被存成 GBK/ANSI，里面有中文就乱码，C4819 会提示
3. **带 BOM 的 UTF-8**（约 15%）：多数时候能用，但和某些工具链/第三方头文件混用时会出怪错
4. **字符串里混了中文全角标点**（约 15%）：`“` `”` `；` 被当成代码字符，报「未结束的字符串 / 常量中有换行符」

## 排查步骤

1. 看报错文件名和行号是不是**第 1 行**——编码/行尾问题几乎总在第 1 行或字符串行
2. VS：文件 → 高级保存选项，看「行尾」和「编码」当前是什么
3. 用十六进制视图或命令确认行尾：
   ```powershell
   Format-Hex -Path .\Tank.cpp -Count 32      # 看有没有 0D 0A
   ```
4. 怀疑全角标点时，把那一行的引号/分号删掉重打一遍（从报错的「字符串」里找）

## 修复方案

1. 统一转成 **UTF-8 (无 BOM) + CRLF**：
   ```powershell
   $p = '.\Source\MyGame\Tank.cpp'
   $t = [IO.File]::ReadAllText($p) -replace "`r`n", "`n" -replace "`n", "`r`n"
   [IO.File]::WriteAllText($p, $t, (New-Object Text.UTF8Encoding($false)))   # $false = 不带 BOM
   ```
2. VS 里：文件 → 高级保存选项 → 编码选「UTF-8 无签名」、行尾选「Windows (CR LF)」→ 保存
3. 全角标点：养成习惯，代码区只用半角；中文字符串统一用 `TEXT("中文")`，不要让中文出现在标识符里
4. 大批量文件处理时用编辑器统一换行符（VS Code 右下角 CRLF/LF 点一下 → 全部转换）

## 容易误判的情况

- C4335 说「Mac 文件格式」只是**行尾风格**问题，跟「代码在 Mac 上写的」无关，Windows 上用 Git 也可能被换成 LF（`core.autocrlf` 配置引起）
- `C4819` 是警告，通常是「某处真有非 ASCII 字符」的信号，**不要**只靠加 `/wd4819` 压掉——先确认那是不是你想写的中文
- 中文注释本身**不是**问题，UE 官方也允许；出问题的是编码与行尾，所以「把中文注释全删掉」属于治标不治本
