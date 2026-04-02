
<div align="center">

# 🍃 LaTeX Zen Editor (清阅编辑器)

**一个专为科研工作者设计的 LaTeX 沉浸式阅读与编辑器**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![PyQt5](https://img.shields.io/badge/PyQt5-GUI-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/你的用户名/你的项目名/pulls)

[English](#) | [简体中文](#)

</div>

---

## 💡 为什么需要清阅 (Zen)？

在撰写学术论文时，传统的 LaTeX 编辑器（如 TeXstudio, VSCode 等）往往会让满屏的 \begin{...}、\textbf{...} 和杂乱的注释干扰我们的思维。

**清阅 (LaTeX Zen Editor)** 诞生于一个纯粹的理念：**把干扰降到最低，让思想自然流淌。** 它不是用来替代专业的全功能 IDE，而是为你提供一个**护眼、专注、清爽的“心流 (Flow)”写作环境**。它可以无缝折叠 LaTeX 语法噪音，并提供一键编译预览。



## ✨ 核心特性 (Features)

### 🧘‍♂️ 沉浸式写作体验
- **Zen 模式自动折叠**：智能弱化 \begin、\end 等语法标签的视觉权重。
- **四款护眼主题**：精心调校的“暖光护眼”、“月光蓝”、“深色护眼”、“绿野仙踪”，久看不仅不累，甚至有点享受。
- **丝滑缩放**：按住 Ctrl + 鼠标滚轮，无极缩放代码字号。

### 🚀 极速学术生产力
- **一键编译预览**：按 F5 或 F6 直接调用 XeLaTeX / pdfLaTeX 编译并自动弹出 PDF（内置防乱码与崩溃保护）。
- **拖放即插入**：把图片拖入窗口，**自动生成** \begin{figure} 引用代码。
- **实时英文拼写检查**：红色波浪线提示错误，右键菜单一键智能修正。
- **智能辅助**：括号高亮匹配、自动闭合、快捷键一键包裹 (Ctrl+B/I/E/D/M)。

### 🗂️ 现代化的工程管理
- **左侧边栏**：集成“文档大纲树（自动同步跳转）”与“项目文件资源管理器”。
- **底部日志台**：随时查看编译过程，自动清理冗余的 .aux, .log 等垃圾文件。
- **快捷数学符号菜单**：一键插入希腊字母、矩阵、积分等常用公式。

---

## 🛠️ 安装与运行 (Installation)

目前本项目基于 Python 与 PyQt5 开发。只需简单的几步即可在本地运行：

**1. 克隆仓库**
git clone [https://github.com/RengangW/LaTeXZen.git](https://github.com/RengangW/LaTeXZen.git)
cd LaTexZen

**2. 安装依赖库**
建议使用虚拟环境，然后安装必要的依赖：
pip install PyQt5 pyspellchecker

*(注意：编译功能需要你本地已安装 TeX 运行环境，如 TeX Live 或 MiKTeX)*

**3. 运行程序**
python main.py

---

## ⌨️ 常用快捷键 (Shortcuts)

| 快捷键 | 功能说明 | 快捷键 | 功能说明 |
| --- | --- | --- | --- |
| F5 / F6 | 一键编译 (XeLaTeX / pdfLaTeX) | Ctrl + / | 快捷注释/取消注释 |
| Ctrl + Shift + Z | 切换 Zen 模式 (弱化语法) | Ctrl + B / I / E | 加粗 / 斜体 / 强调选中文本 |
| Ctrl + 滚轮 | 放大/缩小编辑器字号 | Ctrl + D / M | 插入行内公式 / 行间公式 |
| Ctrl + Shift + O | 显示/隐藏侧边栏 | Ctrl + G | 跳转到指定行 |
| Ctrl + Shift + L | 显示/隐藏编译日志输出台 | F11 | 全屏模式 |

---

## 🤝 贡献与反馈 (Contributing)

这是我的第一个开源项目！如果你喜欢这个工具，**请务必点一个 ⭐ Star 支持一下**，这将是我继续更新的最大动力！

发现 Bug 或有新功能建议？欢迎提交 Issue 或 Pull Request。

## 📜 许可证 (License)

本项目采用 MIT License 授权，你可以自由地使用、修改和分发。
