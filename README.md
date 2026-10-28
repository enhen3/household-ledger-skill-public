# 家庭记账 Skill · 公开预览版

**用途：**把已支持的银行、支付宝、微信账单整理成待复核的家庭账本、中文月报与本地浏览器图表；保留来源、发现疑似重复、缺证据时保持未完成。先跑虚构样例，再决定如何接入真实数据。

作者 **Soren**。自有内容采用 **GPL-2.0-only**，见 [版权与许可范围](COPYRIGHT.txt) 和完整 [LICENSE.txt](LICENSE.txt)。允许遵守GPL的使用、修改、再分发及商用/转售，不附加旧版的禁售或收费服务限制。第三方依赖保留各自许可证。

当前源码版本 **0.3.0-preview.20261028.4**。免费领取：本仓库 **Code → Download ZIP**。请先跑合成样例，再决定如何接入真实账单。历史候选包保留，源码ZIP与自定义打包ZIP的目录结构和哈希不同，不能混用校验值。依赖及源码义务见 [第三方许可核查](references/third-party-licenses.md)。

## 新增默认图形展示与录制样例

安装依赖后，Agent 将明确指定的候选制成只读月份快照，用 Fava 在本机浏览器查看图表和逐笔来源。默认直接打开原生 Fava 损益表，根地址与启动提示指向同一页面。标题保留候选和 pending 标示；侧栏“候选状态与口径”是辅助页，可查期间、覆盖和正式边界；候选没有完整期初余额，不把资产页当家庭净资产。页面不能替你批准用途。

> 使用内置 recording_demo 在新的空目录准备2001年4月虚构账单，先停在重复确认；等我确认后再导入。让我确认已知用途，保留320元待核，打开只读Fava；等我实际回答“生日礼物，仅本笔”后生成新候选与新视图。禁止读取任何真实账本，不自动填写我的确认，不调用 self-test 充当真人演示。

新样例有16笔资金交易、2笔支付佐证和1行重复导出。已知用途确认后 pending=1、净支出5724元；320元礼物确认后净支出6044元、收入12000元、pending=0。自动自检与真人初始材料严格分开。完整命令、独立控制总额、录制停点、刷新和重置见 **[本地图形账本与真人录制](references/visual-demo.md)**。

默认展示使用上游Fava核心，不等于迁移私人四页Dashboard或内置飞书。RED包包含相同本地适配器，但平台是否允许起localhost服务未实测；只有文件白名单验证通过。

## 原有17元自动验收样例

可直接对已安装本 Skill 的 Agent 说：

> 只用 first_run 和 demo 的内置虚构账单，演示导入、银行与支付记录关联、用途确认和中文月报。列出每一步实际产物、待办与失败，不读取真实账单。再解释现有重复导入测试如何阻止重复计入；不要把平台关联当成确认重复。

| 场景 | 随包夹具与可核验结果 |
| --- | --- |
| 虚构账单 → 待确认 | first_run：3 行银行 + 1 行支付宝；12 元支付与银行关联，形成 3 笔资金交易，不再增加一笔消费。查看 normalized、merged.json 和 review.json |
| 确认用途 → 中文月报 | first_run 自带明确标为合成的确认：12 元礼物，其余餐饮含退款净 5 元；reports/2001-02.md 净支出 17.00、pending=0、complete。reviewed.review-receipt.json 保留确认依据；程序的合成确认不是用户真实批准 |
| 发现疑似重复 → 先停住 | 既有 DuplicateTests 使用“一笔 12 元旧导出 + 含同笔 12 元和新笔 8 元的扩展导出”：未确认时失败；确认具体重复对后才保留 2 笔、合计 20 元。这是另一组夹具，不与上述 17 元样例混算 |
| 只确认一笔 | 对已有队列说“这笔是礼物，只确认本笔”，并指明实际来源 ID。已有合成测试从 2 项中只批准 1 项，余下 pending=1，不生成 future 规则；真实使用须记录真实回答 |
| 缺证据或输入失败 | demo 保留 1 项待确认且 close_status=unknown；未知文件/异常交易非零退出，不以“没解析出来”当零支出或成功 |

同一 first_run 输出目录重放两次应字节一致；带可靠来源身份的已导入历史不会作为新钱输出。这些是合成测试范围，不是任意账单都能自动正确去重的承诺。

安装和运行命令在下方。处理后先看“读入 / 疑似重复 / 待确认 / 候选已包含 / 失败原因与来源”小结；未知保持未知。月报会注明期间、筛选、覆盖笔数、是否全量及 pending 是否计入金额，见 [小结口径](references/result-summary.md)。

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

仅支持文档中列出的 CNY 银行 CSV、可提取文本的已知招行 PDF、支付宝 CSV、微信 XLSX；扫描 OCR、多币种、复杂分拆、跨月冲销、自动获取账单和生产迁移不在本版范围。详情见 [操作契约](references/workflow.md)、[首次配置](references/first-use.md)。

脚本本地解析不意味着云端 Agent 不外传。Agent 读取的文件/工具输出可能进入其模型与日志服务。即使使用Codex CLI，只要它连接云端模型，Agent上下文仍可能外传；只有在本地终端直接运行账务脚本且不把真实输出发回云端，才能避免这一Agent路径。真实使用前明确宿主的数据去向，并优先使用合成样例或经审阅的最小字段；见 [隐私说明](references/privacy.md)。

## 下载 ZIP 的可执行自检

下载包不含 .git。普通安装者使用 doctor、first_run、demo；完整本地自检可从任意 CWD 运行：

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/maintain.py" check
```

它会检查当前包清单、隐私模式、回归与合成重放；没有 Git 时不执行历史审计。**不要在下载 ZIP 中运行 acceptance_receipt.py 或 publish**：前者需要完整 Git 历史，后者属于另行授权的维护流程。

需要本地重新打包时，先读 distribution.json 的 build_kind，并使用 [候选版本说明](references/distribution.md) 的命令。GitHub 完整包和 RED Skill 包是同一核心版本的两种构建，哈希不同。RED Skill 仅通过静态格式规则模拟，不表示平台上传或运行已经通过。

[既有基线验收](references/acceptance.md) · [候选版本与包差异](references/distribution.md) · [维护合同](references/maintenance.md)

官方宿主规范：[Codex](https://learn.chatgpt.com/docs/build-skills)、[Claude Code](https://code.claude.com/docs/en/skills)、[WorkBuddy](https://open.workbuddy.cn/docs/skill)、[Kimi Code](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)。
