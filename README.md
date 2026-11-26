# codex-agent-team

把 Codex CLI 拆成一支**有明确分工和闸门**的 agent team：研究、编码、代码审查、
调试、测试、烧录各自只做一件事，谁也不能替代谁签字。

这不是「让一个模型反复自我检查」，而是把工程上的职责边界写成**可执行的编排**：
每个角色有独立的 prompt、独立的沙箱权限、独立的产物；阶段之间靠结构化结论
（`verdict: pass|fail`）交接，失败就退回 `debug`，通过才允许进入下一步。

## 角色

| 角色 | 职责 | 沙箱 | 能否改代码 | 产出 |
| --- | --- | --- | --- | --- |
| `research` | 读代码库、定位相关文件、给出可执行计划与风险 | read-only | 否 | `research`（目标、步骤、风险） |
| `coding` | 按计划实现改动，保持最小 diff | workspace-write | 是 | 代码改动 + 说明 |
| `review` | 只审不改，按严重级别给结论 | read-only | 否 | `verdict` + findings |
| `debug` | 针对失败结论定位根因并修复 | workspace-write | 是 | 修复 + 根因说明 |
| `test` | 跑仓库要求的检查与测试，如实报告 | workspace-write | 是（仅测试文件） | `verdict` + 命令输出摘要 |
| `flash` | 面向嵌入式设备的烧录计划 | read-only | 否 | 计划与命令，**默认不执行** |

## 一次 run 长什么样

```text
research ──► coding ──► review ──fail──► debug ──► review
                            │ pass                    (最多 N 轮)
                            ▼
                          test ──fail──► debug ──► test
                            │ pass
                            ▼
                     flash (可选，需 --allow-flash)
```

任何一轮闸门失败且轮次用尽，run 以非零退出码结束，并把「谁、在哪一步、因为什么失败」
写进 `manifest.json`。不自动提交、不自动推送、不自动合并——这些永远留给人类。

## 快速开始

要求：Python 3.8+（无第三方依赖）、Codex CLI（`codex` 在 PATH 上，或 `--codex` 指定）。

```bash
# 看一眼内置角色
python -m agentteam roles

# 对一个目标仓库跑完整流水线（产物落在 runs/）
python -m agentteam run \
    --task examples/task.example.md \
    --repo ../your-project \
    --out runs

# 只看编排会执行什么，不调用模型
python -m agentteam run --task examples/task.example.md --repo . --dry-run

# 需要烧录计划时才显式打开（仍然不会真的烧）
python -m agentteam run --task examples/flash.example.md --repo . --allow-flash
```

在 Windows 上用 PowerShell 时，把上面的 `python` 换成 `py -3` 即可。

## 目录

| 路径 | 说明 |
| --- | --- |
| `agents/` | 角色定义：`roles.json` + 每个角色一份 prompt |
| `harness/agentteam/` | 编排器（Python 标准库），负责调 `codex exec`、判闸门、落证据 |
| `harness/schemas/` | 结构化结论的 JSON Schema（交给 `codex exec --output-schema`） |
| `tests/` | 离线自测；`fake_codex.py` 让 CI 不需要真实模型 |
| `tools/` | 提交规范、PR 门禁、建仓脚本、本地钩子 |
| `governance/` | 分支保护与仓库设置，由建仓脚本施加 |
| `examples/` | 任务样例 |

## 设计原则

1. **闸门不可绕过**：`review` 与 `test` 的结论由结构化输出决定，不看「看起来没问题」。
2. **权限按角色收缩**：审查者只有只读沙箱；能改代码的只有 `coding` / `debug` / `test`。
3. **证据可复现**：每次 run 的 prompt、命令行、stdout/stderr、最后一条消息、结论都落盘。
4. **不越权**：不执行提交、推送、发布，不接触设备，不读取任何凭据文件。
5. **离线可测**：CI 只跑假 CLI 的自测，不调用真实模型、不联网。

## 文档

- [ARCHITECTURE.md](ARCHITECTURE.md)：角色模型、状态机、Codex 调用契约、失败语义
- [CONTRIBUTING.md](CONTRIBUTING.md)：提交规范（内核风格 + DCO）、PR 流程
- [REVIEW_POLICY.md](REVIEW_POLICY.md)：三道闸门与合并规则
- [SECURITY.md](SECURITY.md)：这个工具会碰到什么、不会碰什么

## 许可

MIT，见 [LICENSE](LICENSE)。
