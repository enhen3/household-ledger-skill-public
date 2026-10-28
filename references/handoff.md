# 公开预览版交接

- 版本 **0.3.0-preview.20261028.4**；作者 Soren；自有内容 GPL-2.0-only，第三方通知保留。
- 官方源码与后续领取来源：https://github.com/enhen3/household-ledger-skill-public。Code → Download ZIP；解压后将整个目录改名为household-ledger-skill，按README安装。
- 公开仓库为独立新历史，不是内部仓库的fork，不含内部Git对象或私密备份。不要将旧维护仓库的历史merge/push到这里。
- 本版只整理公开领取/费用/隐私说明和分发元数据；账务算法、依赖、Fava界面与真人确认停点保持不变。
- github-full与redskill是同一源码版本的两种构建，文件清单与哈希不同。RED仅静态格式验证，尚未上架、未验证平台运行localhost服务。
- 基线Codex项目发现与调用曾在macOS27.0.1/Python3.12.13/CLI0.163.0实测；Fava本机浏览器已实测。最终提交CI结果见交付回执。其他Agent与Windows未声称通过。
- Skill源码免费不等于模型、Agent订阅或API免费。云端Agent读取的账单片段可能进入模型与日志；先用虚构样例。
- 图形页面固定本机127.0.0.1、只读候选，不会自动批准或发布正式账本。飞书未内置。
- MM1等已有消费端应明确改用上述公开来源：保留旧克隆和私人数据，另建目录clone并合成验收，不直接合并旧历史；有未提交改动先审阅补丁。拉取、安装和运行验证分开记录，本次未远程操作MM1。
- GPL允许依其条款商用和再分发；第三方服务不代表官方背书。纯源码分发范围及未解决的组合/二进制再分发问题见third-party-licenses.md，不声称完整法律审核。
