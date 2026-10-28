# 安装、首次试跑与排错细节

首页提供最短入口；本页保留完整安装与自检说明。

## 获取与安装

官方领取入口：[GitHub 源码仓库](https://github.com/enhen3/household-ledger-skill-public)。点击 **Code → Download ZIP**，解压 `household-ledger-skill-public-main`，确认这个目录直接包含 `SKILL.md`、`scripts/`、`references/`、`examples/` 和 `requirements.txt`。将整个目录改名为 `household-ledger-skill` 后放到对应Agent项目目录，不要只复制SKILL.md，也不要重复嵌套一层仓库目录。

以已实测的Codex项目安装为例，最终路径是 **项目/.agents/skills/household-ledger-skill/SKILL.md**。在该项目中打开新会话，再使用下方“第一句话”和独立venv命令。其他Agent放置方式见表格；目录规范可适配不等于宿主实测通过。

Skill源码免费获取；模型订阅、Agent工具或API调用、网络和电脑成本由使用者自行承担，免费Skill不代表免费模型额度。官方不要求收费领取。第三方收费服务不代表官方提供或背书。

## 要求与放置位置

需要 Python **3.11 或 3.12**，以及能执行本地 Python 的 Agent。已验证 CLI 环境包括 Ubuntu 24.04 / macOS 14 的 Python 3.11、3.12，以及本地 macOS 27.0.1 的 Python 3.12.13；CI 通过不等于所有 Agent 宿主通过。宿主需允许读取所选 Skill、执行该 venv 的 Python，以及写入用户指定的合成目录；按宿主正常审批，不授予无关目录权限。首次安装依赖需要包源网络；依赖为 beancount 3.2.3、pdfplumber 0.11.10、openpyxl 3.1.5、Fava 1.30.16。浏览器展示需要宿主允许本机只读服务；服务固定绑定127.0.0.1，不需要飞书账号。传递依赖由安装器解析，实际版本应记录。

解压后确认包根目录直接有 SKILL.md，把**整个目录**放到对应宿主的项目级位置，保留 scripts、references、examples、tests 等目录：

| Agent | 项目级安装方式 | 证据 |
| --- | --- | --- |
| Codex | 项目/.agents/skills/household-ledger-skill/ | 基线在 macOS 27.0.1 + Python 3.12.13 + CLI 0.163.0 显式及自然语言调用通过 |
| Claude Code | 项目/.claude/skills/household-ledger-skill/ | 官方目录规范；本包宿主实测待做 |
| WorkBuddy | 按技能界面导入本地包，确认实际解压位置 | 官方规范可适配；本包宿主实测待做 |
| Kimi Code | 项目/.kimi-code/skills/household-ledger-skill/，也支持 .agents/skills | 官方规范可适配；本包宿主实测待做 |

不是放进去就一定能运行。先确认宿主发现正确 SKILL.md、使用正确解释器；权限、依赖和平台运行环境须满足要求。Windows、Python 3.13+、真实账单版式及其他宿主不能视为已通过。

## 对 Agent 说的第一句话

> 使用 household-ledger-skill。先只用自带的虚构账单，检查 Python 与依赖，实际跑通首次导入、重复导入、复核、对账和中文月报。先确认源码目录、venv 解释器和仓库外的合成输出目录。不要读取真实账本，不改源码、不推送或发布。给我实际 Skill 路径、执行结果及月报。

这句话不授权宿主寻找私人账单或自动发布。若需要安装依赖，先说明安装位置与包源。不要把系统默认 python3 当成正确版本，也不要假设一次 activate 会传到下一次工具调用。

## 一份合成样例跑通

在自己选择的独立目录创建 venv；下面把 SKILL_DIR、VENV_DIR 两个路径改成自己的绝对路径。示例使用 python3.12；只有 Python 3.11 时，将创建 venv 那一行改用 python3.11。源码/Skill、venv、数据是三个不同位置，输出必须在**所有 Git 工作树之外**。

```sh
SKILL_DIR="/absolute/path/to/household-ledger-skill"
VENV_DIR="/absolute/path/to/new-ledger-venv"
python3.12 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install -r "$SKILL_DIR/requirements.txt"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/review.py" doctor
FIRST_OUTPUT="$(mktemp -d)"
INCOMPLETE_OUTPUT="$(mktemp -d)"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/first_run.py" --output "$FIRST_OUTPUT"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/demo.py" --output "$INCOMPLETE_OUTPUT"
```

若分多次调用工具，每次重新设置所需变量或直接传完整绝对路径；不要假定前一次 shell 的变量仍存在。首次配置及后续操作文档均使用相同的绝对解释器和脚本路径。

doctor 应为 ready=true。完整示例应有 synthetic_only=true、two_runs_byte_identical=true、close_status=complete、pending=0、net_expenses="17.00"、private_rule_reused=true、production_published=false。读回 FIRST_OUTPUT 下 reports/2001-02.md。缺证据示例应保持 unknown、pending=1。全部身份、金额和确认均为程序内置虚构夹具；不能当真实用户的账务确认。

## 升级、排错与范围

升级请使用新源码目录/新 venv，先跑合成验收，再切换项目级 Skill；保留旧版本以便回退。**不要覆盖私人配置、原始账单、规则、审批回执、候选或月报**，也不因更新代码重算正式历史账。

失败先看 doctor、明确的格式错误和待核项。反馈提供候选版本、build_kind、Python/OS/Agent 版本、失败命令类别与脱敏错误类型；不要附真实账单、账户、商户明细、密钥、私人绝对路径或完整云端日志。不能因另一台机器 push/pull 成功就认定自己的安装通过。

仅支持文档中列出的 CNY 银行 CSV、可提取文本的已知招行 PDF、支付宝 CSV、微信 XLSX；扫描 OCR、多币种、复杂分拆、跨月冲销、自动获取账单和生产迁移不在本版范围。详情见 [操作契约](workflow.md)、[首次配置](first-use.md)。

脚本本地解析不意味着云端 Agent 不外传。Agent 读取的文件/工具输出可能进入其模型与日志服务。即使使用Codex CLI，只要它连接云端模型，Agent上下文仍可能外传；只有在本地终端直接运行账务脚本且不把真实输出发回云端，才能避免这一Agent路径。真实使用前明确宿主的数据去向，并优先使用合成样例或经审阅的最小字段；见 [隐私说明](privacy.md)。

## 下载 ZIP 的可执行自检

下载包不含 .git。普通安装者使用 doctor、first_run、demo；完整本地自检可从任意 CWD 运行：

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/maintain.py" check
```

它会检查当前包清单、隐私模式、回归与合成重放；没有 Git 时不执行历史审计。**不要在下载 ZIP 中运行 acceptance_receipt.py 或 publish**：前者需要完整 Git 历史，后者属于另行授权的维护流程。

需要本地重新打包时，先读 distribution.json 的 build_kind，并使用 [候选版本说明](distribution.md) 的命令。GitHub 完整包和 RED Skill 包是同一核心版本的两种构建，哈希不同。RED Skill 仅通过静态格式规则模拟，不表示平台上传或运行已经通过。

[既有基线验收](acceptance.md) · [候选版本与包差异](distribution.md) · [维护合同](maintenance.md)

官方宿主规范：[Codex](https://learn.chatgpt.com/docs/build-skills)、[Claude Code](https://code.claude.com/docs/en/skills)、[WorkBuddy](https://open.workbuddy.cn/docs/skill)、[Kimi Code](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)。
