# 贡献指南（Contributing Guide）

本仓库与 `cadywang/serial-debug-bridge`、`cadywang/cadywang.github.io` 使用同一套治理规则：
**`main` 上的任何改动都必须来自 Pull Request，CI 全绿后用 Rebase and merge 合入。**

## 1. 开发环境

| 组件 | 要求 |
| --- | --- |
| Python | 3.8+（仅标准库；CI 用 3.11） |
| Codex CLI | 只有真实 run 需要；自测用 `tests/fake_codex.py` 代替 |
| Shell | Windows：PowerShell 5.1+；Linux/macOS：bash |

```bash
git clone git@github.com:cadywang/codex-agent-team.git
cd codex-agent-team
bash tools/dev-setup.sh          # 或：powershell -File tools/dev-setup.ps1
```

## 2. 提交前必须本地通过

```bash
python -m compileall -q harness tests tools
python tests/test_roles.py
python tests/test_codex.py
python tests/test_verdict.py
python tests/test_pipeline.py
python tests/test_check_commits.py
python tests/test_check_pr.py
python tools/check-commits.py --range main..HEAD
```

```powershell
# Windows 等价写法
py -3 -m compileall -q harness tests tools
py -3 tests/test_pipeline.py
```

> 自测**不调用模型、不联网、不碰设备**。`tests/fake_codex.py` 是一个会按环境变量
> 返回不同结论的假 `codex exec`，用来验证编排、闸门与落盘逻辑。

## 3. 提交规范：遵循 Linux 内核补丁约定

本仓库**强制**采用 Linux 内核的 commit message 规范，不使用 Conventional Commits
（`feat:` / `fix:` 这类标签会被 CI 拒绝）。

### 3.1 格式

```
<subsystem>: <祈使句摘要，不超过 72 字符，结尾不加句号>

<正文：说明 what 与 why，每行不超过 72~75 字符，可用空行分段>

<可选标签：Reported-by: / Link: / Fixes: / Reviewed-by: / Tested-by:>
Signed-off-by: <作者姓名> <作者邮箱>
```

* **subsystem** 取受影响的目录或模块名，例如 `harness:`、`agents:`、`tests:`、
  `tools:`、`ci:`、`docs:`、`repo:`；更细的写法如 `harness/codex:` 也可以。
* **摘要用祈使语气**（`add`、`keep`、`fix`，不是 `added`/`adds`/`adding`），
  禁止 `feat:`、`chore:`、`wip:`、`various:`、`bump` 等。
* 摘要与正文之间、正文与签名块之间各留一个空行。
* 正文解释**为什么**要改，不要逐行复述 diff；被放弃的方案、实测现象值得写下来。
* 修 bug 用内核格式标注来源：`Fixes: 0d75a9b ("harness: ...")`。

### 3.2 DCO 签名（必须）

每个提交都要有 `Signed-off-by:`，且与作者身份一致。首次克隆后跑一次环境配置：

```bash
bash tools/dev-setup.sh          # Windows: powershell -File tools/dev-setup.ps1
# 等价于：
#   git config core.hooksPath tools/git-hooks
```

装好后：

* `tools/git-hooks/prepare-commit-msg` 在消息缺少签名时**自动补**一行；
* `tools/git-hooks/commit-msg` 在提交前校验标题与正文，不合规直接拒绝。

不装钩子、或想显式签名时，用 `git commit -s`。

> `format.signOff` 在不同 git 版本上行为不一致（实测 git 2.55 不生效），
> 所以「自动签名」由钩子负责，不寄托在这个配置项上；CI 的 `Commit style`
> 步骤才是最终强制点。

### 3.3 一个提交只做一件逻辑上的事

功能、重构、格式化、文档不要混在一个提交里；每个提交都应能独立通过自测，保证
`git bisect` 有效。提交顺序按依赖排列：先数据结构，再实现，再测试，最后文档与 CI。

### 3.4 本地校验

```bash
python tools/check-commits.py --all                 # 全量
python tools/check-commits.py --range main~3..main  # 一段范围
python tools/check-pr.py --title "harness: add the debug gate" --body-file pr.md
```

紧急绕过本地钩子：`git commit --no-verify`（CI 仍会拦住，PR 无法合入）。

## 4. 代码风格

* 代码与注释用英文；`README`、`ARCHITECTURE`、`CONTRIBUTING`、`REVIEW_POLICY`、
  `SECURITY` 等面向使用者的文档用中文。
* UTF-8（无 BOM）+ LF（`.editorconfig` / `.gitattributes` 已强制）。
* Python：4 空格缩进，**只用标准库**，兼容 3.8（不用 `match`、不用运行时 `X | None`）；
  类型注解加 `from __future__ import annotations`。
* 模块内不 print 调试信息；CLI 输出走 `cli.py` 统一处理。
* 新增编排行为必须同时新增/更新 `tests/` 用例，并同步 `ARCHITECTURE.md`。

## 5. 改编排行为时的注意事项

1. **闸门语义只在一个地方改**：`harness/agentteam/verdict.py`。不要在流水线里散落正则。
2. **权限不要悄悄放宽**：把角色从 `read-only` 改成 `workspace-write` 属于行为变更，
   PR 必须在「影响面」里勾选并在说明里给出理由。
3. **新增角色不要顺手进主流水线**：先在 `roles.json` 注册并只提供手动入口，
   等有测试与真实 run 证据后再接入状态机。
4. **`flash` 永远不执行**：任何让编排器直接下发烧录命令的改动都不接受。
5. **改 `roles.json` 要同步 `ARCHITECTURE.md` 第 2 节的字段表**。

## 6. PR 流程

1. `git switch -c <subsystem>/<short-description>`；
2. 本地自测全绿，提交按内核规范并带 DCO；
3. `git rebase main` 保持线性历史，`git push -u origin <branch>`，开 PR；
4. **PR 标题**同样用 `<subsystem>: <祈使句摘要>`，模板里的「合并前清单」逐条勾选
   （`pr-gate` 会强制校验，少一项不能合并）；
5. CI 全绿后由维护者 **Rebase and merge**（分支自动删除）。**不要 Squash**：
   它会把整个 PR 压成一个提交，`Signed-off-by:` 也不再是原文。

单人维护模式下不设强制批准数（GitHub 不允许自批）；有协作者后按
[REVIEW_POLICY.md](REVIEW_POLICY.md) 提升为「至少 1 位他人批准」。

## 7. 许可

提交即表示同意你的贡献在 MIT 许可下发布（见 `LICENSE`）。
