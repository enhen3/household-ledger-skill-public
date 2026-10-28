# 处理小结与月报口径

面向用户先用现有 CLI JSON 的 `summary.text` 作小结，再给产物路径和下一步。`summary` 是附加字段，原 `result`、`operation`、`pending`、`approved`、`close_status`、错误消息与退出码保持原义；最终状态仍以这些字段和实际产物为准。操作成功不等于月结 complete，partial 不能写成全部成功。

## 六项固定小结

| 小结 | 有证据时如何填写 | 不可推断的内容 |
| --- | --- | --- |
| 读入 | normalize 的规范化交易行数；match 的银行与平台输入行数；prepare 的队列项数；build 的输入标准行数 | 不是所有原始文件物理行数。未知写未知，不能把不同阶段相加 |
| 疑似重复 | 指出原错误中的重叠来源 ID，说明仍待核；没有独立计数时写未知 | 银行与平台关联、备注匹配不算确认重复；不能用输入减输出反推重复数 |
| 待确认 | prepare/approve 的 pending；build 的实际候选 pending；report 的月内 pending | 匹配阶段的 unresolved 是来源匹配问题数，不直接换算成待确认交易笔数 |
| 候选已包含 | build 读回候选中的交易数；report/verify 的当前候选、当前月份交易数 | approve 成功不是生成候选；候选不是正式账本，也不表示本次新增了这么多笔 |
| 失败 | 本命令失败为 1 次操作；失败行数无统计写未知，保留原因 | 一条异常不能宣称全批只有一行失败；非零退出不写成功 |
| 原因/来源行 | 使用已有 message、source ID、解析器给出的页/行或 issues 文件 | 没有定位就写未知，不杜撰行号；外发反馈先脱敏 |

`summary` 的 null 表示没有可靠计数，不是 0。`failed_operations=0` 只说明该次命令没有抛出已处理异常，不说明 sources 齐全、没有疑似重复或可以发布。命令重放的统计不累加。register 只能说已收到原件，note 只是备注，不冒充已导入交易。

示例话术：读入 2 行；疑似重复数量未知；候选实际包含 1 笔；待确认 0；本次操作失败 0；未正式入账。只有在本次产物确实支持这些数值时使用；不能套用样例数字。

## 月报范围

月报 JSON 新增 `scope`，包括含首尾的期间、Transaction/CNY 筛选、支出/收入科目范围、候选覆盖笔数、财务交易笔数、带 pending 的财务交易笔数、是否截断及数据范围。没有新增任意条件查询接口：现有功能是指定候选账本和月份的汇总。

- `truncated=false` 仅指 supplied_candidate_and_month 内全量，不证明现实世界账单齐全；来源完整性仍看 close_status、coverage、blockers。
- 不额外按成员过滤。成员标签用于原有分组/归属检查，不因配置遗漏成员就静默过滤。
- 支出/收入按 Expenses/Income 科目原有逻辑汇总；带 pending 的财务分录仍可能进入总额，`pending_financial_transactions` 如实标明。暂挂和内部划转不进入收入/消费；退款冲减支出。
- 如果 Agent 只展示若干待办，要另说“展示 N / 总计 M 项”，不能把展示列表当全部。原 JSON/Markdown 月报保留全部月内待办。

旧机器字段与 schema_version=1 保留，新增 `summary` / `scope` 各自带 schema_version=1。旧月报没有 scope，不能默认为 0 或全量；需要新输出目录重新生成并验证。不可覆盖不同字节的旧报告，旧数据和审批记录保留。
