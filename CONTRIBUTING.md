# 参与轻松文本对比 EasyTextDiff

欢迎提交可复现的问题、界面建议和小范围 Pull Request。较大的功能或架构调整，请先通过 Issue 说明使用场景和预期行为。

## 准备开发环境

推荐 Windows 和 Python 3.12，创建虚拟环境的命令见 [README.md](README.md)。运行时依赖仅为 `requirements.txt` 中的 PyQt5；测试使用 Python 自带的 unittest。

在所用虚拟环境中安装项目并运行测试：

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

应用代码位于 `src/easytextdiff/`，包内沿用会话级 MVP 与应用服务分层。测试使用 `easytextdiff` 包导入，不在测试中添加 `sys.path` 路径补丁。入口为 `python -m easytextdiff` 或安装后的 `easytextdiff` GUI 命令；构建脚本位于 `scripts/build_windows.py`。

修改对比或合并算法时，请覆盖真实的输入与输出，保留中文、Unicode、空行、末尾换行和插入 / 删除行映射的行为，不向原文加入对齐占位行。修改界面时，请在实际窗口检查浅色、深色、最小窗口尺寸与键盘操作。

## 提交 Issue

请写明系统、Python / PyQt5 版本、复现步骤、预期与实际结果。对比问题最好提供能重现的两段短文本；请先替换其中的个人或业务信息。

## 提交 Pull Request

说明解决了什么问题、用户操作后的行为，以及如何验证。保持每次变更范围清楚，避免混入缓存、打包产物和环境配置。已有测试通过后，仅为新增行为或实际回归补充必要测试。

新增依赖时说明用途和许可。提交的代码应能够按照本项目的 GPL-3.0-or-later 许可分发。
