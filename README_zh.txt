轻松文本对比 EasyTextDiff 1.2.3

项目仓库：https://github.com/XinhaoLiu94/EasyTextDiff

一个使用 PyQt5 编写的本地文本对比工具。启动后直接粘贴两段文字，
支持代码、TXT、Markdown 等纯文本。界面默认跟随 Windows 的应用主题，
右上角外观按钮可切换浅色、深色或跟随系统。

运行
1. 解压完整的 EasyTextDiff 文件夹，双击 EasyTextDiff.exe。
2. 请保留 _internal 文件夹，复制程序时复制整个 EasyTextDiff 文件夹。
3. 便携版无需另装 Python。源码运行：在项目目录执行 python -m pip install -e .，
   然后运行 python -m easytextdiff；安装后的 GUI 命令为 easytextdiff。

使用
• 左右两栏直接输入，或点击粘贴按钮从剪贴板填入整段文字。
• 左右两栏始终可以编辑，差异直接显示在原文中，不需要切换输入与查看模式。
• 停止输入约 500 ms 后自动更新原文高亮，保持编辑焦点；也可关闭自动比较。
• Ctrl+Enter 或 F5 立即重新比较；F7 / F8 跳到上一处 / 下一处差异。
• 红色为删除，绿色为新增，较深底色标出行内变动。
• 中间箭头将当前选中的差异直接应用到目标栏；在同一栏中可 Ctrl+Z 撤销并继续编辑。
• 两侧保留原始行数，不插入对齐占位行；光标、中文输入与撤销沿用原生编辑器行为。
• 支持忽略空白、忽略大小写、按对应关系同步滚动、Ctrl+F 查找。
• 支持 Verilog / SystemVerilog、C / C++、Python、JSON 语法高亮；每侧底部可选择语言。
• 右侧概览条显示整份文本的差异分布，点击可以跳转。
• 支持拖入文件或点击文件图标导入；识别 UTF-8、UTF-16 BOM、GB18030。
• 单个导入文件最大 4 MB。超大或高度重复的文本可能显示较粗粒度的差异块。
• 右上角可导出逐行对齐的独立 HTML 报告，更多菜单可复制 unified diff、保存任一侧文本。
• unified diff 反映真实原文差异，不受“忽略空白 / 大小写”的显示选项影响。
• “新建比较”或 Ctrl+N 打开独立标签，不清空原会话；Ctrl+W 关闭当前标签。
• Ctrl+S 保存当前侧；Ctrl+Shift+S 另存为并选择编码与换行。
• 关闭、导入替换与关闭标签时提示保存、放弃或取消；保存失败会中止后续操作。
• 不自动保存输入或恢复会话；仅记住外观、窗口大小与自动比较偏好。

数据与格式
界面中的导航、概览与同步滚动使用比较行与原始行的对应关系，不保证两侧屏幕行
严格水平对齐。界面不添加空白占位行，复制和保存始终使用真实原文；HTML 报告仍对齐展示。
文本只在本机处理。导入不会覆盖原文件，只有明确执行保存才会写入文件。
这是纯文本比较器；Word、PDF 等格式需先提取文字。内部换行统一为 LF，
普通保存保留原编码、BOM 与换行；另存为可选择 UTF-8、UTF-8 BOM、UTF-16 LE/BE BOM、
GB18030，以及 LF、CRLF、CR。混合换行在未编辑时保留原字节，编辑后统一前确认。
同路径保存会检查外部修改并提示是否覆盖；写入失败不会更新保存基线。

源码与许可
这是独立的 PyQt5 实现，参考双栏对比工作方式，未包含 WinMerge 源码。
应用源码采用 GPL-3.0-or-later，全文见 LICENSE.txt。
便携包包含 source 目录与 third_party 依赖许可、版本和来源说明。
若使用 GitHub 源码，应用模块位于 src/easytextdiff/；先安装项目，再以
python -m easytextdiff 启动，完整说明见 README.md。

开发与验证
Python 3.12 / PyQt5 5.15。运行 python -m easytextdiff --demo 可查看内置示例。
开发环境先执行 python -m pip install -e .；测试通过正常的 easytextdiff 包导入运行。
测试：python -m unittest discover -s tests -v
可设置 QT_QPA_PLATFORM=offscreen 进行自动化测试。
Windows 的 offscreen 平台可能没有可用字体，视觉检查请使用实际窗口。
构建入口为 python scripts/build_windows.py，依赖安装与完整说明见 PACKAGING.txt。
架构采用会话级 MVP 与应用服务分层，详细边界见 docs/ARCHITECTURE.md。
