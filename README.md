# DocxToMarkdown

Windows 桌面工具，支持 DOCX 与 GitHub Flavored Markdown 双向转换，可处理单个文件或整批目录。界面支持中文与 English。

## 功能

- DOCX → Markdown、Markdown → DOCX。
- 批量转换，支持递归扫描和保留目录结构。
- DOCX 图片提取；Markdown 转 DOCX 时按源文件目录查找图片。
- 智能同步：通过 SHA-256 判断内容是否变化；首次同步已有目标时兼容比较修改时间。
- 全部覆盖、仅转换不存在的文件。
- 保存同步设置、一键同步、取消任务及转换报告。

## 从源码运行

开发环境：Windows、Python 3.12、Pandoc。Python 依赖版本固定在 `requirements.txt` 中。

1. 安装 Python 3.12（包含 Windows 的 `py` 启动器）。
2. 安装 [Pandoc](https://pandoc.org/installing.html)，将 `pandoc.exe` 加入 PATH，或安装到 `%ProgramFiles%\Pandoc\pandoc.exe`。
3. 在本目录打开 PowerShell，执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

直接调用虚拟环境中的 Python，不需要激活环境。源码运行时需要单独安装 Pandoc；源码包不包含 EXE 或第三方程序。

应用也支持通过 `DOCX_TO_MARKDOWN_PANDOC` 环境变量指定 Pandoc 路径，或读取本目录下的 `tools/pandoc.exe`。`build.ps1` 使用 PATH 或 `%ProgramFiles%\Pandoc\pandoc.exe` 查找 Pandoc；自定义安装位置请先加入 PATH。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖转换规则、双向转换、图片路径、同步记录、设置及界面交互。界面测试使用 Qt offscreen 平台；真实转换测试在未找到 Pandoc 时会跳过，因此完整验证需要安装 Pandoc。

## 生成 Windows EXE

```powershell
.\build.ps1
```

脚本会创建虚拟环境、安装依赖、执行测试，然后通过 PyInstaller 打包，并嵌入本机的 Pandoc。测试失败时停止打包。

输出为 `dist/DocxToMarkdown.exe`，并复制到项目根目录的 `DocxToMarkdown.exe`。该 EXE 可直接双击运行，不需要另装 Python 或 Pandoc。构建生成的 `.spec`、缓存、虚拟环境和 EXE 已列入 `.gitignore`。

## 使用与数据位置

选择输入文件或目录、转换方向、输出目录和转换方式，点击生成按钮，确认摘要后开始转换。常用任务可以保存同步设置，以后一键同步。

输出目录中的 `conversion-report.csv` 保存任务结果，`.docx-to-markdown-sync.json` 保存智能同步记录。用户设置保存在 `%APPDATA%\DocxToMarkdown\settings.json`，界面语言保存在同目录的 `preferences.json`。

勾选“完成后删除记录文件”会删除本程序生成的报告和同步记录，保留转换结果及提取的图片。删除同步记录后，下次智能同步退回修改时间判断。

## 开发文件

```text
DocxToMarkdown/
├── app/                  # 应用源码、界面、转换引擎和翻译
├── tests/                # 核心与界面测试
├── .gitignore            # 排除开发环境和生成产物
├── build.ps1             # Windows 打包入口
├── requirements.txt      # 固定版本的 Python 依赖
├── version_info.txt      # EXE 版本资源
└── README.md
```

应用版本在 `app/__init__.py` 中；发布时同步更新 `version_info.txt` 中的版本信息。

## 交接与上传 GitHub

这是从当前工作目录整理的源码快照，包含当时尚未提交的源码修改和新增测试。原项目及其 Git 历史保持原样。

源码目录只保留开发所需文件，排除了原 `.git`、虚拟环境、打包缓存、EXE、旧脚本备份、空资源目录，以及带本机绝对路径的生成 `.spec`。接收方可以直接按上述步骤运行和开发。

将交接 ZIP 解压到原项目以外的独立目录，把解压后的 `DocxToMarkdown` 作为新仓库根目录。先确定项目许可证，再添加 `LICENSE`，然后执行：

```powershell
git init -b main
git add .
git status --short
git commit -m "Initial source release"
```

随后在 GitHub 创建空仓库，并按照该仓库页面提示添加 remote 和 push。源码包未关联 GitHub 仓库，也未上传。生成的 EXE 可以通过 GitHub Releases 单独提供。

## 许可证

项目许可证待作者确定，本源码快照尚未加入 `LICENSE`；公开发布前请补充。公开仓库与授予开源使用权限的区别见 [GitHub 许可证说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)。

第三方依赖保留各自许可证。发布包含第三方组件的 EXE 时，需按所用版本核对许可文本、声明与分发要求，参考 [Qt for Python 许可证](https://doc.qt.io/qtforpython-6/licenses.html)、[Pandoc 许可说明](https://github.com/jgm/pandoc/blob/main/COPYRIGHT)和 [PyInstaller 许可证](https://pyinstaller.org/en/stable/license.html)。源码包未打包这些第三方组件。
