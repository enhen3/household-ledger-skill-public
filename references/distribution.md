# GPL 候选版本与两种构建

候选版本 **0.3.0-preview.20261028.6**。作者 Soren；自有内容采用 GPL-2.0-only，见 [COPYRIGHT.txt](../COPYRIGHT.txt) 和完整 [LICENSE.txt](../LICENSE.txt)。账务算法沿用已验收实现；本版改善中文首页和安装说明，加入经审阅的原生Fava虚构截图；打包检查仅增加该JPEG的固定哈希审阅路径，RED省略图片。保留依赖、账务算法与许可条款。

## 状态与官方入口

公开领取仓库：https://github.com/enhen3/household-ledger-skill-public。从 Code → Download ZIP 获取源码，解压后找到直接含 SKILL.md 的目录。当前公开仓库是独立源码快照，不包含内部维护历史、备份或依赖实现。实际公开提交和两包哈希见交付回执；RED 尚未上架，也未验证平台内运行。

官方说明：“官方包可免费获取；第三方收费服务不代表官方提供或背书。”这只是来源与背书说明，不增加 GPL 的使用限制；符合 GPL 的商用和转售不需要再取得本项目的额外收费许可。

旧 .1、.2、.3 候选均保留在原目录；本版延续 .3 的 GPL 许可证，不覆盖旧包。当前包不包含旧的禁售或收费服务限制，不把两版许可证或校验值混用。详细变更见 CHANGELOG。

## 两种构建

| 构建 | 内容 | 差异 |
| --- | --- | --- |
| github-full | 完整源码候选 ZIP | 保留CI/Git辅助文件及已审阅Fava截图；ZIP本身不含.git历史 |
| redskill | RED Skill 平台格式候选 ZIP | 显式省略CI/Git辅助文件与JPEG截图；同步文件清单和图片审阅元数据，README保留公开原图链接 |

共同文件中的实际记账实现、文档和许可相同，另有图片文件取舍，构建元数据与文件清单也不同。两包哈希不同，使用包旁的 SHA256SUMS 和版本来源映射核对。

官方上传器 @xhs/skillhub-upload 0.1.1 的已核实规则为根 SKILL.md、单文件10 MiB、总30 MiB及后缀白名单；本地打包器在生成前检查所有文件，遇不支持文件直接失败，避免ZIP上传时静默丢弃。规则来源：[官方上传说明](https://redskill.xiaohongshu.net/uploader.md)。本轮没有安装/运行上传器，不声称平台真上传或运行通过。

## 下载 ZIP 自检与重打包

使用独立venv解释器和本包脚本绝对路径；输出到所有Git工作树之外的新路径，不覆盖原件：

```sh
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/maintain.py" check
"$VENV_DIR/bin/python" "$SKILL_DIR/scripts/build_distribution.py" \
  --variant redskill --output "/absolute/path/outside-git/ledger-redskill-review.zip"
```

完整包可构建 github-full 或 redskill；RED包只可重建 redskill，不能凭空恢复已省略的CI/Git辅助文件和截图。输出旁的.manifest.json记录包与内部文件哈希。两包带完整自有源码、测试、示例生成器、依赖声明和构建脚本，未捆绑wheel、venv或第三方二进制。

acceptance_receipt.py属于需要Git历史的维护者入口，不是下载ZIP的安装命令。普通使用者按README运行doctor、first_run、demo；maintain check在无.git时跳过历史扫描。

## 源码、依赖与再分发

依赖安装不自动满足一切分发义务。保留GPL文本、作者/修改说明及相应源码；若未来另行分发依赖二进制、容器或合并工程，需要检查其源码、署名与通知义务。参见 [权属与源码范围](ownership-and-source.md) 和 [第三方许可证核查](third-party-licenses.md)。第三方许可文本保留原字节，不改成Soren的许可。

本轮记录了实际依赖元数据与可取得的许可文本，但不是全链条法律审核。不得把requirements列出包名当成版权/许可义务全部满足。

## 范围与升级

基线曾在macOS 27.0.1 arm64、Python 3.12.13、Codex CLI 0.163.0做过真实显式和自然语言调用；本轮验收新增Fava本地浏览器、只读接口、虚构录制停点、新版解压/自检/重打包与静态格式规则。没有把新增浏览器功能视为所有Agent通过。Claude、WorkBuddy、Kimi、Hermes、MM1、Windows、真实账单和RED平台运行仍未测。

升级使用新源码目录和venv，先合成验收再切换入口。私人原件、配置、规则、审批回执和历史账本不覆盖、不上传、不自动重算。反馈只给版本/构建、环境、命令类别和脱敏错误；不附真实账单、密钥或私人路径。

默认图形界面还需要本机服务权限和浏览器访问，RED平台若不能运行本地服务则不能直接提供这一界面；不能把格式兼容当运行兼容。
