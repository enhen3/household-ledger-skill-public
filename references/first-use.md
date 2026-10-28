# 首次配置与最短使用路径

## 安装后只做一次

1. 按 README 创建虚拟环境、检查依赖并跑合成示例；升级后重跑。日常备注不重复安装和整套验收。
2. 确认运行模式：合成 / 本地 CLI 或已核验本地模型 / 云端 Agent 最小字段。云端模式说明实际服务及日志设置；未知时明确未知。
3. 请用户指定 Git 仓库之外的私人目录，确认成员代号、资金账户和必需来源。代号可不用真实姓名。
4. 由 Agent 执行 init 生成配置并让用户确认，不要求用户自己写 JSON。不得因账单缺失删除 required_streams。

以下只是虚构示例；PRIVATE 必须由用户指定，不在任何 Git 工作树内。SKILL_DIR 和 VENV_DIR 是 README 已确认的源码与 venv 绝对路径。新终端或新工具调用需重新给出这些变量，不能依赖当前 CWD 或上次 activate。

```sh
SKILL_DIR="/absolute/path/to/household-ledger-skill"
VENV_DIR="/absolute/path/to/new-ledger-venv"
PRIVATE="/absolute/path/outside-all-git/ledger-private"
```

首次配置：

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/review.py" init --root "$PRIVATE" --owner alice \
  --source alice:bank:Assets:Alice:Bank \
  --source alice:alipay:Assets:Alice:Bank
```

生成 config.json、inbox、rules、runs、statement-inbox。不同内容拒绝覆盖已有配置；变更时用新版本文件确认差异。

## 支付方式

从用户指定账单读取必要支付方式标签，展示后生成私人 payment-map.json。虚构标签 SYNTHETIC Bank 对应 {"account":"Assets:Alice:Bank","backing":"bank"}；钱包对应独立资金账户和 backing=wallet。付款账户未知时询问，不靠商户推测。

## 每次月结

在私人 runs/<月份>/<批次>/ 创建新候选路径，按 workflow.md 执行。旧批次保留，不覆盖不同内容。已入账标准行可通过 match --history 显式提供；不要把旧月上下文当新资金。

Agent 组织调用、解释待办，用户确认生活用途和适用范围。确认记录必须对应实际回答，不得套用合成示例的 confirmed_by / confirmation_ref。
