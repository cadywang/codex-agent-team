# 变更记录（CHANGELOG）

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 六个角色定义（`research` / `coding` / `review` / `debug` / `test` / `flash`），
  每个角色独立的沙箱权限与 prompt。
- `harness/agentteam` 编排器：按状态机调用 `codex exec`，prompt 走 stdin、
  结论走 `-o` + `--output-schema`，全过程落盘到 `runs/<run-id>/`。
- 闸门语义：`review` / `test` 的 `verdict` 为唯一通过条件；失败回退 `debug`，
  轮次上限可配置。
- `flash` 角色默认只产出计划，需要 `--allow-flash` 才会进入流水线，且从不执行烧录。
- 离线自测：`tests/fake_codex.py` 假 CLI + 角色/命令构造/结论解析/流水线四组用例。
- 仓库治理：内核风格提交门禁（含 DCO）、PR 标题与合并清单门禁、分支保护配置、
  建仓脚本与本地钩子。
