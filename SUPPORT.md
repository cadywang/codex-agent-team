# 支持（Support）

## 先看文档

| 问题 | 看哪里 |
| --- | --- |
| 怎么跑一次 run | `README.md` 的「快速开始」 |
| 角色、闸门、状态机怎么设计 | `ARCHITECTURE.md` |
| 提交规范、PR 流程 | `CONTRIBUTING.md` |
| 为什么 `main` 不能直推 | `REVIEW_POLICY.md` |

## 自己先确认

```bash
python -m agentteam roles          # 角色表是否能加载
python -m agentteam run --task examples/task.example.md --repo . --dry-run
python tests/test_pipeline.py      # 编排逻辑是否正常（离线）
codex --version                    # 真实 run 需要 CLI
```

## 提问渠道

* 功能建议 / 缺陷：用仓库的 Issue 模板。
* 安全问题：不要开 Issue，见 `SECURITY.md`。
