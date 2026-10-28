# 第三方许可与源码说明

本候选自有代码、测试、示例与文档采用 GPL-2.0-only，作者 Soren，范围见 [COPYRIGHT.txt](../COPYRIGHT.txt)。[LICENSE.txt](../LICENSE.txt) 是从 Beancount 3.2.3 官方标签取得的 GPLv2 完整原文；其中附录的示例文字不改变本项目明确选择的 GPL-2.0-only。第三方文本和依赖不重新归属 Soren，也不被本项目重新许可。

## 已完成的核对

- 已移除自有内容的禁售、收费服务等额外限制；旧 0.2.0-preview.20261027.1 只作历史保留，不是新版附加条款。
- Beancount 3.2.3 上游 [pyproject.toml](https://raw.githubusercontent.com/beancount/beancount/3.2.3/pyproject.toml) 明确声明 GPL-2.0-only；完整 [COPYING](https://raw.githubusercontent.com/beancount/beancount/3.2.3/COPYING) 已保留。
- 本次安装环境的 16 个运行依赖已记录版本、许可证元数据和上游位置；可取得的 36 份版权/许可文本附在 third-party-notices，原位置和 SHA256 见 [文本索引](third-party-notice-index.json)。35 份保持原字节，FreeType 文本只将 Latin-1 版权符号转为 UTF-8，保留措辞并记录前后哈希。文件名统一加 .txt，以兼容 RED Skill。
- 两个 ZIP 包含本项目实际可修改源码、测试、示例生成器、构建脚本和安装依赖声明，不包含依赖实现源码、wheel、二进制、venv 或账本；附依赖许可文本不意味着附了全部依赖源码。

| 依赖 | 核对版本 | 安装元数据声明 |
| --- | --- | --- |
| beancount | 3.2.3 | GPL-2.0-only |
| pdfplumber | 0.11.10 | MIT（classifier） |
| openpyxl | 3.1.5 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| python-dateutil | 3.0.0 | 双许可，BSD / Apache classifiers |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| pdfminer.six | 20260107 | MIT |
| pypdfium2 | 5.14.0 | BSD-3-Clause、Apache-2.0 及捆绑组件许可 |
| pillow | 13.0.0 | MIT-CMU，许可文件还含组件通知 |
| et_xmlfile | 2.0.0 | MIT，另有 Python 许可文本 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.12 | BSD-3-Clause |
| charset-normalizer | 3.5.2 | MIT |
| tzdata | 2026.5 | Apache-2.0 |
| six | 1.17.0 | MIT |

完整机器记录见 [dependency-license-snapshot.json](dependency-license-snapshot.json)。它是此次已测试环境快照，直接依赖固定版本，传递依赖仍由安装器解析；未来安装不保证得到完全相同依赖树。

## 当前纯源码分发范围与未解决边界

**采用 GPL-2.0-only 移除了原自定义条款的额外限制，但不等于全依赖链已经获得兼容性确认。** Apache 官方[兼容说明](https://www.apache.org/licenses/GPL-compatibility.html)记录 Apache-2.0 与 GPLv2 的兼容问题。本次实际依赖包含 regex 的 Apache-2.0 AND CNRI-Python、tzdata 的 Apache-2.0，以及 PDFium 相关组件文本；是否在本项目具体分发形态构成受约束的组合作品、双许可可选项与其他例外如何适用，本次没有法律结论。不能把 pip 另行安装依赖当成自动免责，也不能仅凭元数据断言当前源码 ZIP 必然违法。

本次有限实务判断限定为公开本项目自有源码、文档、合成夹具与依赖声明，保留GPL-2.0-only及第三方通知，不捆绑依赖实现；上游组合许可疑点不自动等于禁止公开这些自有源码的硬阻碍。这不是全依赖兼容或法律审核通过的保证。Beancount实际导入regex；regex的Apache与历史CPython/CNRI条件不是任选，未找到可引用的特许例外。组合及二进制再分发风险仍保留，不把pip安装作为自动免责。若未来捆绑依赖源码、wheel、可执行文件或 venv，须重新核对该形态的完整义务；这些 ZIP 当前不宣称提供了依赖的完整对应源码。不得把上游代码改署为 Soren。

本轮未换依赖、未重写记账功能，未声称法律审核通过；也未发现能据本次有限检查确证的自有代码权属冲突。来源核查边界见 [ownership-and-source.md](ownership-and-source.md)。

## Fava 展示依赖（0.3 候选新增）

固定 Fava 1.30.16，项目 https://github.com/beancount/fava ，PyPI https://pypi.org/project/fava/1.30.16/ ，元数据 SPDX=MIT，完整版权/许可证与AUTHORS保留。它以常规依赖运行，包内只有本项目适配代码，没有Fava或其依赖的源码/二进制实现。通过独立安装并不自动解除其他分发义务。

本次环境新增依赖和许可原文索引见 fava-dependency-license-snapshot.json，实际安装版本可查。beanquery 0.2.0与beangulp 0.2.0提供GPLv2文本；TatSu-LTS为BSD，Flask/Werkzeug等为BSD，Fava及多项工具为MIT；chardet 7.7.0元数据为0BSD。这里记录证据，不假称所有传递依赖均为MIT。PLY wheel未单列许可文件，元数据声明BSD；当前不分发其实现，发布二进制/容器前另核原始版权声明。

本版没有引入 fava-dashboards、fava-theming、ECharts或私人看板源码。前版已记录的 regex 2026.9.29 Apache-2.0 AND CNRI-Python 与GPLv2许可疑点仍未因本次可视化测试而解决，作为未解决的组合再分发风险保留；不因此声称此纯源码包必然违法或已获得整体法律批准，未修改用户选定许可证。未发现新的明确冲突不等于法律审核或绝对兼容保证。
