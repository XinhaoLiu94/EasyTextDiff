# 首次发布到 GitHub

本地项目已准备好源码、文档、许可证和自动测试配置。按下面的步骤建立远程仓库，再推送源码。

## 建立仓库并推送源码

1. 本项目的远程仓库为 [XinhaoLiu94/EasyTextDiff](https://github.com/XinhaoLiu94/EasyTextDiff)。首次关联时保持远程仓库为空，不自动创建 README、许可证或 .gitignore；这些文件已经在本地准备好。
2. 在项目目录中执行下面的命令。如果 Git 提示缺少提交身份，先设置自己使用的 Git 姓名与邮箱。

```powershell
git init -b main
git add .
git diff --cached --stat
git commit -m "Initial EasyTextDiff release"
git remote add origin https://github.com/XinhaoLiu94/EasyTextDiff.git
git push -u origin main
```

如果项目已经初始化过 Git 仓库，可跳过第一条命令；从源码 ZIP 开始时，第一条命令会创建 `main` 分支。提交前检查暂存文件，确认远程地址属于自己的账号。请使用自己的 GitHub 登录方式，不要把访问令牌写进源码或远程 URL。

建议仓库简介：

> A paste-first desktop text diff tool with editable source panes, live inline highlights and local processing.

可选主题：`diff`、`text-comparison`、`pyqt5`、`desktop-app`、`python`。

## 检查自动测试

第一次推送后，在 GitHub 的 Actions 页面确认 `Tests` 工作流通过。该工作流先通过 `pip install -e .` 安装项目，再运行 Windows / Python 3.12 下的 unittest，仓库配置只申请内容读取权限。

## 发布 Windows 便携版

1. 按 [PACKAGING.txt](../PACKAGING.txt) 安装项目与构建依赖，在 Windows 上执行 `python scripts/build_windows.py`。
2. 验证 `dist/EasyTextDiff/EasyTextDiff.exe` 启动、粘贴比较、文件导入、明暗切换和报告导出。
3. 将完整的 `dist/EasyTextDiff` 文件夹压缩为 ZIP。保留 `_internal`、应用源码与依赖说明，不要只上传 EXE。
4. 在确认测试与实际窗口检查完成后，将 [更新记录](../CHANGELOG.md) 中相应版本的“待发布”改为发布日期，提交并创建与应用版本一致的标签（当前为 `v1.2.3`）与 GitHub Release，再附上便携包。

源码仓库只提交项目源文件与文档；构建目录、下载缓存和便携版二进制通过 `.gitignore` 排除。较大的便携包放在 Release 附件中。
