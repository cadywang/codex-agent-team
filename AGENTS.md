# AGENTS.md - codex-agent-team

本文件是 **Codex 在本仓库内工作** 时的规则。仓库的对外说明见 `README.md`，
设计约束见 `ARCHITECTURE.md`。两者与本文冲突时，先按本文执行，再在 PR 里提出修正。

## 这个仓库是什么

一个基于 Codex CLI 的 agent team 编排器：`agents/` 定义角色，`harness/agentteam/`
负责按状态机调用 `codex exec` 并判定闸门。它**不实现模型**，只实现分工、权限与证据。

## 动手前

1. 读 `README.md`、`ARCHITECTURE.md`、`CONTRIBUTING.md`。
2. 跑 `git status`，确认没有别人（或你自己）未提交的改动。
3. 改动涉及编排行为时，先确认状态机与闸门语义，再动代码。

## 不可协商的规则

- **提交信息**：Linux 内核风格 `<subsystem>: <祈使句摘要>`，≤72 列、不加句号、
  正文 72~75 列折行、必须带 `Signed-off-by:`（`git commit -s`）。
  禁止 `feat:` / `fix:` / `chore:` 这类 conventional-commit 标签。
- **分支**：从 `main` 切 `<subsystem>/<短描述>`；`main` 只能通过 PR 以
  **Rebase and merge** 进入，不直推、不强推、不 squash。
- **依赖**：`harness/` 只用 Python 标准库，Python 3.8+ 可运行。不新增第三方包。
- **测试**：改动必须能在**离线**条件下验证；不允许自测依赖真实模型、网络或设备。
- **语言**：代码、注释、提交信息用英文；面向使用者的文档用中文。
- **编码**：UTF-8（无 BOM）+ LF。

## 绝不做的事

- 不执行 `git commit` / `git push` / `git reset --hard` / `git clean -fd`。
- 不执行 `gh`、不创建 PR、不打 tag、不发 release。
- 不读取任何凭据文件（`.gh-token`、`.env`、`~/.codex/auth.json`），不把 token 写进代码或文档。
- 不让任何角色在无人确认的情况下烧录设备；`flash` 角色只产出计划。

## 目录职责

| 路径 | 谁能改 |
| --- | --- |
| `agents/*.md` | 角色 prompt，改行为先改这里 |
| `agents/roles.json` | 角色权限表，改动要同时更新 `ARCHITECTURE.md` 第 2 节 |
| `harness/agentteam/` | 编排器实现，配套 `tests/` |
| `harness/schemas/` | 结论 schema，改动要兼容 `verdict.py` |
| `tests/` | 离线自测，必须一直全绿 |
| `tools/` | 提交规范与建仓脚本，改动等价于改门禁，需单独提交 |
| `governance/` | 分支保护的实际来源，改完要重跑 `tools/create-github-repo.ps1` |

## 本地验证（提交前必须全过）

```powershell
python -m compileall -q harness tests tools
python tests/test_roles.py
python tests/test_codex.py
python tests/test_verdict.py
python tests/test_pipeline.py
python tools/check-commits.py --range main..HEAD
```

## 交付说明

完成一次改动后，说明：改了什么、改了哪些文件、怎么验证、还有什么未确认。
