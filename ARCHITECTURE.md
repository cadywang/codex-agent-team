# 架构（ARCHITECTURE）

本文说明 agent team 的**职责边界**、**交接协议**和**失败语义**。改了编排行为就要改这里，
两者不一致时以代码为准并在同一个提交里修正本文件。

## 1. 不变量

以下几条是设计前提，任何改动都不能破坏：

1. **一个角色只做一件事**。`review` 不改代码，`coding` 不给自己判通过。
2. **结论必须结构化**。闸门只看 `{"verdict": "pass"|"fail"}`，不看自由文本里的语气。
3. **权限按角色收缩**。能写工作区的角色是 `coding` / `debug` / `test`，其余只读。
4. **失败可归因**。每个阶段都记录角色、退出码、耗时、结论来源、失败原因。
5. **外壳不做危险动作**。编排器不提交、不推送、不发布、不烧录、不读凭据。
6. **离线可验证**。所有自测在假 CLI 上跑通，不依赖模型与网络。

## 2. 角色模型

角色由 `agents/roles.json` 描述，prompt 是 `agents/<id>.md`。字段含义：

| 字段 | 含义 |
| --- | --- |
| `id` | 唯一标识，也是 run 目录里的子目录名 |
| `name` | 展示名 |
| `description` | 一句话职责，写进 `roles` 列表输出 |
| `sandbox` | 传给 `codex exec --sandbox`：`read-only` / `workspace-write` / `danger-full-access` |
| `writes` | 是否允许修改工作区。`false` 的角色跑完会比对 `git status`，有改动即判违规 |
| `gate` | 是否需要 `verdict` 才能通过；只有 `review` / `test` 为 `true` |
| `timeout_seconds` | 单阶段超时，超时视为失败 |
| `output_schema` | 可选，`harness/schemas/` 下的 JSON Schema，交给 `--output-schema` |
| `requires_flag` | 可选，需要命令行开关才启用（目前只有 `flash` 用 `--allow-flash`） |
| `extra_args` | 可选，附加给 `codex exec` 的参数（例如 `--model`） |

校验在启动 run 之前完成：缺 prompt、重复 id、未知 sandbox、找不到 schema 都会直接失败，
不会跑到一半才发现。`danger-full-access` 只允许通过显式配置启用，默认角色表里没有它。

## 3. 状态机

```text
            ┌──────────────┐
  start ───►│   research   │  read-only，产出计划
            └──────┬───────┘
                   ▼
            ┌──────────────┐
            │    coding    │  workspace-write
            └──────┬───────┘
                   ▼
            ┌──────────────┐  fail   ┌──────────────┐
            │    review    ├────────►│    debug     │
            └──────┬───────┘         └──────┬───────┘
                   │ pass                   │
                   │        ◄───────────────┘ 回到 review
                   ▼
            ┌──────────────┐  fail   ┌──────────────┐
            │     test     ├────────►│    debug     │
            └──────┬───────┘         └──────┬───────┘
                   │ pass                   │
                   │        ◄───────────────┘ 回到 test
                   ▼
            ┌──────────────┐  仅当 --allow-flash
            │    flash     │  只产出计划，不执行
            └──────┬───────┘
                   ▼
                  done
```

`--max-debug-rounds`（默认 2）分别约束 `review` 与 `test` 的回退次数：任意一条链
用尽轮次就终止 run，退出码 1。`research` 失败直接终止——计划都拿不到，后面的角色
只会瞎猜。

## 4. 交接协议

编排器为每个阶段拼出统一的 prompt：

```text
<角色 prompt 全文>

## Agent role
<role id>

## Task
<任务原文>

## Run context
- workdir: <目标仓库绝对路径>
- run: <run id>
- previous stages: <角色: 结论 列表>

## Gate requirements
<该角色的闸门要求，例如「只审不改；最后一条消息必须是 verdict JSON」>
```

结论读取顺序：

1. `codex exec -o <file>` 写出的**最后一条消息**；
2. 该消息里的 JSON 对象（`{"verdict": ...}`）；
3. 退化路径：消息中的 `VERDICT: PASS` / `VERDICT: FAIL` 标记行；
4. 都没有 → `unknown`，闸门按失败处理。

结论来源会写进 `manifest.json` 的 `verdict_source` 字段，方便排查「为什么它说通过了」。

## 5. Codex 调用契约

每个阶段执行一次：

```text
codex exec \
  --cd <workdir> \
  --sandbox <role.sandbox> \
  --color never \
  --skip-git-repo-check \
  -o <stage>/last-message.md \
  [--output-schema <schema>] \
  [--model <model>] \
  -            # prompt 从 stdin 读，避免命令行长度与引号问题
```

选择这些参数的理由：

- **prompt 走 stdin**：任务描述常含中文、换行、反引号，命令行传参会踩 Windows 的
  引号规则；`codex exec -` 明确支持 stdin。
- **`-o` 而不是解析 stdout**：`--json` 事件流适合留档，但结论要一个干净的最终消息。
- **`--output-schema`**：让 review/test 的结论是机器可判的 JSON，而不是靠正则猜。
- **`--skip-git-repo-check`**：允许对非 git 目录做研究/审查（例如解压出来的源码树）。
- **cwd 同时设为 workdir**：codex 的 `--cd` 决定它的工作根，进程 cwd 决定相对路径
  与脚本行为，两者必须一致。

stdout/stderr 原样落盘为 `events.jsonl` / `stderr.log`；超时可配置，默认值来自
`roles.json`，被 SIGKILL 的子进程按失败处理。

## 6. 产物

```text
runs/<UTC 时间戳>-<任务 slug>/
├── task.md                 # 任务原文
├── manifest.json           # 阶段列表、结论、退出码、耗时、最终状态
├── 01-research/
│   ├── prompt.md
│   ├── command.txt         # 实际执行的 argv（dry-run 时只有这个）
│   ├── last-message.md
│   ├── events.jsonl
│   └── stderr.log
├── 02-coding/
└── ...
```

`runs/` 在 `.gitignore` 里：证据属于一次具体执行，不进版本库。

## 7. 安全边界

| 风险 | 处理 |
| --- | --- |
| 模型误删文件 | 只有 `workspace-write` 角色能写，且写入范围是目标仓库；审查者只读 |
| 烧录把设备写坏 | `flash` 只出计划与命令，编排器**不执行**；需要人自己确认后运行 |
| 凭据泄漏到 prompt | 编排器只读取任务文件与角色 prompt，不读取 `.env`、token 文件 |
| 自动提交/推送 | 编排器从不执行 `git commit`、`git push`、`gh` 等有副作用的命令 |
| 无限循环烧钱 | 每个阶段有超时，回退轮次有上限，run 有总阶段数上限 |

## 8. 扩展点

- **加角色**：在 `agents/` 放 prompt，在 `roles.json` 加条目，必要时加 schema；
  编排器按 id 取用，不需要改代码（除非要进入主流水线）。
- **改闸门**：`harness/agentteam/verdict.py` 是唯一的结论解析入口。
- **接 CI**：`python -m agentteam run ... --dry-run` 可以检查编排；真实 run 需要模型配额，
  因此默认不进 CI。
- **换模型**：`--model` 或 `roles.json` 的 `extra_args`，按角色分别指定（研究用小模型、
  编码用大模型是合理的）。
