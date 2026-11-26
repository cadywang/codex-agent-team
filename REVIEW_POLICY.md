# 审查与合并规则（REVIEW_POLICY）

> 一句话：**`main` 上的任何改动都必须来自 Pull Request，并通过 CI 的全部必需检查；
> 没有人（包括管理员）可以直接推送或改写 `main`。**

本仓库与 `cadywang/serial-debug-bridge`、`cadywang/cadywang.github.io` 使用同一套审查思路：
**闸门不可绕过、自动校验先行、合并前必须有人过目**。本仓库没有发布环节，落地动作就是 PR 合并。

## 一、三道闸门

| 闸门 | 位置 | 拦什么 | 能不能绕过 |
| --- | --- | --- | --- |
| ① 分支保护 | `governance/branch-protection.json` + `governance/repository-settings.json`（由 `tools/create-github-repo.ps1` 施加） | 直推 `main`、强推、删分支、检查没绿就合并、用 Squash 压缩历史 | 不能：`enforce_admins: true` + 空 bypass |
| ② 自动校验 | `.github/workflows/ci.yml` + `.github/workflows/pr-gate.yml` | BOM/CRLF、语法、编排器自测、commit 规范 + DCO、PR 标题与「合并前清单」 | 不能：改 CI 自己也要走同一个 PR 流程 |
| ③ 人工审查 | PR 本身 | 维护者看过 diff、验证步骤与自测输出后才合并 | 单人维护时维护者即作者（GitHub 不允许自批，因此不设强制批准数）；有协作者后提升为「必须他人批准」 |

## 二、日常流程

```bash
git switch -c harness/debug-gate        # <subsystem>/<short-description>
# ... 改代码、文档、自测 ...
python tools/check-commits.py --range main..HEAD
git commit -s                           # DCO 签名，见 CONTRIBUTING.md §3
git rebase main
git push -u origin harness/debug-gate
# 开 PR → 等 CI 全绿 → 维护者审阅 → Rebase and merge
```

## 三、必须保持同步的文件

| 改了 | 必须同时改 |
| --- | --- |
| `agents/roles.json`（权限、超时、沙箱） | `ARCHITECTURE.md` 第 2 节字段表 |
| 闸门判定逻辑（`harness/agentteam/verdict.py`） | `tests/test_verdict.py`、`ARCHITECTURE.md` 第 4 节 |
| 状态机（`harness/agentteam/pipeline.py`） | `ARCHITECTURE.md` 第 3 节、`tests/test_pipeline.py` |
| 角色 prompt 的产出格式 | 对应 `harness/schemas/*.schema.json` 与假 CLI |
| 面向用户的行为 | `README.md`、`CHANGELOG.md` |
| `governance/*.json` | 重跑 `tools/create-github-repo.ps1` 让远端生效 |

## 四、几个实测过的坑

1. **只能 Rebase and merge，不许 Squash**：Squash 会把整个 PR 压成一个提交，标题变成
   PR 标题、正文拼成一坨、每个提交的 `Signed-off-by:` 不再是原文。所以提交信息必须
   一开始就写对，PR 标题也要符合内核规范。
2. **`strict` 检查要求 PR 追上最新 `main`**：main 前进后旧 PR 需要 rebase 才能合并。
3. **单人维护不要设 `required_approving_review_count: 1`**：GitHub 不允许自己批准自己的 PR。
4. **dependabot 的提交永远不符合内核风格**：CI 用 `--skip-bots` 放行 `*[bot]` 的提交。
5. **`codex exec` 的参数会随版本变化**：`harness/agentteam/codex.py` 里冻结了用到的
   参数集，升级 CLI 后先跑 `python -m agentteam run --dry-run` 看命令行，再跑真实 run。

## 五、调整规则

| 想做什么 | 怎么做 |
| --- | --- |
| 收紧到「必须他人批准」 | 加协作者后把 `required_approving_review_count` 设为 1，并开启 code owner 审核，重跑建仓脚本 |
| 只要最基础保护 | 把 `required_pull_request_reviews` 与 `required_status_checks` 置空后重新施加 |
| 改合并方式 | 改 `governance/repository-settings.json` 的合并开关，再跑建仓脚本 |
| 临时救急 | 改 GitHub Settings → Rules 后重跑脚本恢复；**不要**长期留 bypass |

## 六、提交前的本地自查

```bash
python tools/check-commits.py --range main..HEAD
python tools/check-pr.py --title "<subsystem>: 祈使句摘要>" --body-file pr.md
python -m compileall -q harness tests tools
python tests/test_pipeline.py
```
