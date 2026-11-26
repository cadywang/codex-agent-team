<!--
CI 门禁（勿删）：

  * 「合并前清单」小节里的每一项都由 .github/workflows/pr-gate.yml 强制校验，
    少勾一项就不能合并；改这里的条目等于改门禁，而模板本身也要走 PR。
  * PR 标题同样要符合内核规范 `<subsystem>: <祈使句摘要>`：网页端 squash 合并会把
    标题直接写成 main 上的提交标题，写错了只能事后才发现（历史改不回来）。
  * 「变更类型」「影响面清单」是多选，照实勾选即可，不要求全部勾上。

完整规则见 REVIEW_POLICY.md。
-->

## 变更说明

<!-- 这个 PR 解决什么问题？为什么需要它？ -->

## 变更类型

- [ ] 新功能（feat）
- [ ] 缺陷修复（fix）
- [ ] 仅文档（docs）
- [ ] 重构 / 可读性（refactor）
- [ ] 构建、CI、治理文件（build / ci / repo）
- [ ] **行为变更**：角色权限、闸门语义或状态机（必须同步 `ARCHITECTURE.md`）

## 影响面清单

- [ ] `agents/`（角色 prompt 或 `roles.json`）
- [ ] `harness/agentteam/`（编排器实现）
- [ ] `harness/schemas/`（结论格式）
- [ ] `tests/`（离线自测）
- [ ] `tools/`、`governance/`、`.github/`
- [ ] 文档

## 测试

请在本地执行并粘贴结果（不需要真实模型）：

```
python -m compileall -q harness tests tools
python tests/test_roles.py
python tests/test_codex.py
python tests/test_verdict.py
python tests/test_pipeline.py
```

- [ ] 已用 `--dry-run` 看过编排会执行的命令行（涉及调用参数时必填）

真实 run 证据（可选，涉及 prompt/闸门行为时建议附上）：

| 项 | 值 |
| --- | --- |
| `codex --version` |  |
| run id（`runs/` 下的目录名） |  |
| 最终状态 / 失败原因 |  |

## 合并前清单

> CI 强制逐条勾选（`pr-gate`）：**少一项就不能合并**。

- [ ] 离线自测已全部通过，输出贴在「测试」小节
- [ ] 改了角色权限、闸门或状态机时，`ARCHITECTURE.md` 已同步更新
- [ ] 代码与注释为英文，文档为中文
- [ ] 文件为 UTF-8（无 BOM）+ LF
- [ ] 未提交临时产物（`runs/`、`.tmp-*/`、`__pycache__/`）
- [ ] 每个 commit 遵循内核规范：`<subsystem>: 祈使句摘要`、正文 72 列折行，并带 `Signed-off-by:`（`git commit -s`）
- [ ] PR 标题遵循内核规范 `<subsystem>: 祈使句摘要>`
- [ ] 已更新 `CHANGELOG.md`（如面向用户的行为有变化）
- [ ] 已阅读并遵守 `SECURITY.md`（没有放宽沙箱、没有新增自动执行的外部命令）
