# 本地图形账本与真人录制

本版默认展示层是 **Fava 1.30.16**（MIT），通过正常 PyPI 依赖安装；不复制第三方实现、不要求飞书账户。它读取本 Skill 已验证的 Beancount 候选的独立月份快照。默认直接打开原生 Fava 损益表，保留原生日记账和来源元数据；状态口径页只作为侧栏辅助链接。这里只读展示，不批准用途、不改账、不发布生产。

曾有私人环境使用 Fava + fava-dashboards + fava-theming。当前包接入可独立安装的上游 Fava 核心，没有迁移私人四页看板、投资持仓、主题或飞书集成。不能把独立系统的功能声称为本包已交付。

## 安装与启动

沿 README 创建 Python 3.11/3.12 venv，并安装 requirements.txt；现在含固定 Fava 1.30.16。首次下载需要网络；正常查看只访问本机。运行环境必须允许本地 Python 服务绑定端口；仅有聊天或云端沙箱的宿主不一定能在用户电脑浏览器提供 localhost。RED Skill 的文件过滤通过也不证明平台允许启动服务。

下面变量都必须改成自己的绝对路径，每次新 shell/工具调用重新设置。SOURCE_LEDGER、CONFIG 是用户明确指定的本地候选和配置。真实数据不得放入 Git 工作树；源文件不改写。

```sh
SKILL_DIR="/absolute/path/to/household-ledger-skill"
VENV_DIR="/absolute/path/to/ledger-venv"
SOURCE_LEDGER="/absolute/path/to/candidate/household.beancount"
CONFIG="/absolute/path/to/private/config.json"
VIEW_DIR="/absolute/path/to/new-view-directory"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/visualize.py" prepare \
  --ledger "$SOURCE_LEDGER" --config "$CONFIG" --month 2001-04 --output "$VIEW_DIR"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/visualize.py" serve --view "$VIEW_DIR" --port 5231
```

将月份改成账本实际月份。仅对确定为虚构的数据给 prepare 加 `--synthetic`，不能把真实数据改标签后用于录制。看到启动信息后，在本机浏览器打开 `http://127.0.0.1:5231/`。Ctrl-C 停止本次服务。端口占用时选另一个高位端口，不停止别人的服务；宿主拒绝绑定时走正常审批，不开放 0.0.0.0、不建隧道。

默认打开原生 Fava 损益表及其原生导航，不经过自制状态页。标题显示月份、只读候选、pending 和非正式状态；侧栏“候选状态与口径”可选查看期间、覆盖笔数和待办，该辅助页不是 Fava 图表。Fava 的“收入”按贷方负数显示，例如工资 -12000，辅助状态页将收入正向展示 12000；这是相同账务符号的展示差异，不是负工资。候选没有独立期初余额，资产负债页不能当完整净资产报告。Fava 的编辑/导入入口可能仍显示，但写请求会被只读模式拒绝；分类确认回到 Agent 流程。

显示快照冻结，确认后另建候选和展示目录，停止旧进程再启动新目录；浏览器刷新旧目录不会自动替换数据。每个视图都保留来源账本、快照和报告哈希。只接受本项目 Open/Transaction 候选，拒绝 plugin/include、任意扩展、凭证文件和查询指令；不加载环境变量中别的账本。

## 今天录制的全新虚构月份

2001 年 4 月，demo 为虚构成员：16 行银行资金记录，2 行支付宝辅助记录，另有1行重复导出。包括工资、房租、餐饮、交通、订阅、水电、书籍、健康、宠物、出行等；4月14日86.50元退款冲减4月3日买菜；4月12日320元商店付款等待人说明用途。没有真实人物、银行账户号或用户历史。

这份样例与原17元 first_run 分开。新目录不是操作系统沙盒；新会话仍应明确禁止读取其他目录。无需重装 Codex 或删除记忆。下面例子是 Agent 代操作的真实命令合同；用户只需回答确认问题，不需手写 JSON。

### 1. 准备原始输入，停在疑似重复

```sh
DEMO_DIR="/absolute/path/to/new-recording-demo"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/recording_demo.py" prepare --output "$DEMO_DIR"
```

产物：inputs 下3份CSV、normalized、private/config.json、fixture-facts.json、duplicate-stop.json。**没有自动审批、合并或候选账本**。原始 CSV 由随包 Python 生成，兼容 RED 的文件后缀限制，不用从个人目录取样。

对 Agent 说：

> 只用我指定 DEMO_DIR 内的虚构账单和这份 Skill，禁止读取其他私人目录。先显示疑似重复的两条来源行，不自动删除。问我是否确为同一笔，等我回答后再保存确认。

人检查后回答：

> 确认重复导出的买菜记录与主账单4月3日486.50元是同一笔，保留主账单这一行。

Agent 复制 overlap-confirmation.template.json 为 overlap-answer.json，记录**本次实际** confirmed_by（可用别名）、带时区 confirmed_at、confirmation_ref（本次回答/消息引用），不使用 self-test 字段，再运行：

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/recording_demo.py" merge \
  --workspace "$DEMO_DIR" --confirmation "$DEMO_DIR/overlap-answer.json"
```

16 笔资金交易保留；支付宝是同笔支付佐证，不额外增加支出。review.json 仍有16项待复核。重复导出确认和用途确认是两种不同判断。

### 2. 确认已知项目，保留一笔用途待确认

Agent 展示 partial-decisions.template.json 对应15笔建议及退款关联。人核对虚构设定后实际回答：

> 这15笔按展示分类确认，仅本笔有效。86.50元是4月3日买菜的部分退款，冲减餐饮；320元商店付款先别分类。虚构主银行账单16笔、有符号净额5956元，支付宝2笔、有符号净额-806.50元，期间均为4月全月，我已核对。

Agent 据真实回答生成 partial-answer.json，并填写 reconciliation.template.json 的每个 source 的实际确认字段，保存为 source-totals-answer.json。独立控制总额在 fixture-facts.json 和原CSV中可查，不能从解析后报表倒填“银行证据”。

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/recording_demo.py" stage \
  --workspace "$DEMO_DIR" --name partial --review "$DEMO_DIR/review.json" \
  --decisions "$DEMO_DIR/partial-answer.json" --reconciliation "$DEMO_DIR/source-totals-answer.json"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/visualize.py" serve \
  --view "$DEMO_DIR/stages/partial/view" --port 5231
```

浏览器应显示 **pending=1、provisional、净支出5724.00元**；320元暂挂，不进入支出分类。这不是已完成月结。若不给 reconciliation，仍可展示，但必须保留 unknown，不能宣布完整。

### 3. 人实际解释用途，再打开新状态

人回答：

> 4月12日320元是给朋友买生日礼物，归入礼物，只确认这笔，不设以后自动规则。

Agent 使用 stages/partial/next-review.json 中未确认的实际 ID，生成 final-answer.json：review_sha256 对准该文件；decisions 只有该 ID、category=`Expenses:Gifts`、scope=`once`，附本次真实确认字段。其他已确认行由 next-review 保留，不重写旧回执。

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/recording_demo.py" stage \
  --workspace "$DEMO_DIR" --name confirmed --review "$DEMO_DIR/stages/partial/next-review.json" \
  --decisions "$DEMO_DIR/final-answer.json" --reconciliation "$DEMO_DIR/source-totals-answer.json"
# 在旧服务终端 Ctrl-C；再启动新的快照
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/visualize.py" serve \
  --view "$DEMO_DIR/stages/confirmed/view" --port 5231
```

新视图原生 Fava 收入科目显示-12000.00（贷方，实际收入12000.00）、净支出6044.00、礼物320.00、餐饮净额672.00、16笔、pending=0、complete。complete 仅指这份虚构来源与候选的核对；**production_published 永远 false**。Fava 日记账展开单笔，可查看 source_id/source_ids/review_basis；这里只读追溯。

### 4. 简短录制顺序

1. 说明是虚构账单，展示3个输入文件和疑似重复停点。
2. 人确认同笔，再确认已知用途，保留320元待核；直接打开原生 Fava，标题应为待确认1、待复核（provisional）。
3. 人真实输入“生日礼物，只本笔”；运行新阶段。
4. 直接打开原生 Fava 损益表，再用原生导航查看礼物/退款流水来源；需要核对覆盖口径时再点辅助状态链接；收束为候选核对完成。

不要剪掉关键批准使其看起来无须确认；不将自动自检回执冒充真人互动。飞书可作为将来的另行适配方向，本包没有内置。

## 自动自检与重录

```sh
TEST_OUTPUT="/absolute/path/to/new-automated-test"
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/recording_demo.py" self-test --output "$TEST_OUTPUT"
```

该命令明确写入 `AUTOMATED SYNTHETIC SELF-TEST; not a human approval`；用于回归和核对画面，**不能作真人录制初始目录**。重录重新运行 prepare 到新的空目录，保留旧目录/回执，不删除或覆盖。

跨宿主边界：本轮实际验证本地 Python/Fava 与 macOS 浏览器。此前 Codex 宿主发现能力有单独基线；新增可视化没有重新实测 Claude/WorkBuddy/Kimi、RED 平台内服务能力、Windows或M1消费端。没有账户登录、云端部署、公开发布或生产写入。
