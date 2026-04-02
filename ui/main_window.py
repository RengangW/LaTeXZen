# -*- coding: utf-8 -*-
import os
import re
import platform
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QFileSystemModel,
    QTreeView, QTextEdit, QToolBar, QAction, QLabel, QSlider, QComboBox,
    QMessageBox, QFileDialog, QShortcut, QMenu, QActionGroup, QStatusBar, QPlainTextEdit
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QSettings, QModelIndex
from PyQt5.QtGui import QKeySequence, QFontMetrics, QFont, QTextCursor

try:
    from spellchecker import SpellChecker
    HAS_SPELLCHECKER = True
except ImportError:
    HAS_SPELLCHECKER = False

from ui.themes import THEMES
from ui.editor import ZenEditor
from ui.dialogs import FindReplaceDialog
from core.compiler import CompileThread
from core.parser import LaTeXParser

class OutlinePanel(QTreeWidget):
    navigate_to_line = pyqtSignal(int)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAnimated(True)
        self.itemClicked.connect(self._on_item_clicked)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self.theme = theme
        t = theme
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {t['sidebar_bg']};
                color: {t['fg']};
                border: none;
                font-size: 12px;
                padding: 5px;
            }}
            QTreeWidget::item {{
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: {t['selection_bg']};
                color: {t['selection_fg']};
            }}
            QTreeWidget::item:hover {{
                background-color: {t['line_highlight']};
            }}
        """)

    def update_outline(self, text):
        self.clear()
        structure = LaTeXParser.extract_document_structure(text)
        stack = [(self.invisibleRootItem(), -1)]

        for item_data in structure:
            level = item_data['level']
            title = item_data['title']
            line = item_data['line']
            cmd = item_data['command']

            while stack and stack[-1][1] >= level:
                stack.pop()

            parent = stack[-1][0] if stack else self.invisibleRootItem()

            prefix_map = {
                'chapter': '📖',
                'section': '📄',
                'subsection': '📎',
                'subsubsection': '•',
                'paragraph': '¶',
                'subparagraph': '·',
            }
            prefix = prefix_map.get(cmd, '•')
            tree_item = QTreeWidgetItem(parent, [f"{prefix} {title}"])
            tree_item.setData(0, Qt.UserRole, line)

            stack.append((tree_item, level))

        self.expandAll()

    def sync_with_line(self, current_line):
        self.blockSignals(True) 
        iterator = QTreeWidgetItemIterator(self)
        best_item = None
        max_line = -1

        while iterator.value():
            item = iterator.value()
            line = item.data(0, Qt.UserRole)
            if line is not None and line <= current_line:
                if line > max_line:
                    max_line = line
                    best_item = item
            iterator += 1

        if best_item:
            self.setCurrentItem(best_item)
            self.scrollToItem(best_item)

        self.blockSignals(False)

    def _on_item_clicked(self, item, column):
        line = item.data(0, Qt.UserRole)
        if line is not None:
            self.navigate_to_line.emit(line)


class StatusInfo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self.file_label = QLabel("未打开文件")
        self.pos_label = QLabel("行 1, 列 1")
        self.word_count_label = QLabel("0 字")
        self.mode_label = QLabel("🧘 Zen 模式")
        self.save_label = QLabel("")

        for label in [self.file_label, self.pos_label,
                      self.word_count_label, self.mode_label,
                      self.save_label]:
            layout.addWidget(label)

        layout.addStretch()


class LaTeXZenMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.recent_files = [] 
        self.max_recent = 5
        self.current_theme_name = "暖光护眼 (推荐)"
        self.current_theme = THEMES[self.current_theme_name]
        
        self.compile_thread = None

        self._auto_save_timer = QTimer()
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._outline_update_timer = QTimer()
        self._outline_update_timer.setSingleShot(True)
        self._outline_update_timer.timeout.connect(self._update_outline)

        self.spell_checker = None
        if HAS_SPELLCHECKER:
            self.spell_checker = SpellChecker()

        self._setup_ui()
        self.find_dialog = FindReplaceDialog(self.editor, self) 
        self._setup_menus()     
        self._setup_shortcuts() 
        self._apply_global_theme()
        self._load_settings()

        self.setWindowTitle("LaTeX 清阅编辑器 - 旗舰增强版 V1.5")
        self.resize(1300, 850)
        
        self.setAcceptDrops(True)

    def _setup_ui(self):
        self.status_info = StatusInfo()
        self.statusBar().addWidget(self.status_info)
        self.statusBar().setStyleSheet("QStatusBar { border-top: 1px solid; }")

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.v_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(self.v_splitter)

        self.h_splitter = QSplitter(Qt.Horizontal)
        self.v_splitter.addWidget(self.h_splitter)

        self.left_tabs = QTabWidget()
        self.left_tabs.setMinimumWidth(200)
        self.left_tabs.setMaximumWidth(400)

        self.outline = OutlinePanel(self.current_theme)
        self.outline.navigate_to_line.connect(self._navigate_to_line)
        self.left_tabs.addTab(self.outline, "📑 大纲")

        self.file_model = QFileSystemModel()
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.setColumnHidden(1, True) 
        self.file_tree.setColumnHidden(2, True) 
        self.file_tree.setColumnHidden(3, True) 
        self.file_tree.setHeaderHidden(True)
        self.file_tree.doubleClicked.connect(self._on_file_tree_double_clicked)
        self.left_tabs.addTab(self.file_tree, "📁 项目")

        self.editor = ZenEditor(self.current_theme, self.spell_checker)
        self.editor.content_changed.connect(self._on_content_changed)
        self.editor.cursorPositionChanged.connect(self._update_cursor_pos)
        self.editor.document().setDocumentMargin(15)
        
        self.editor.zoom_in_requested.connect(self._zoom_in)
        self.editor.zoom_out_requested.connect(self._zoom_out)

        self.h_splitter.addWidget(self.left_tabs)
        self.h_splitter.addWidget(self.editor)
        self.h_splitter.setStretchFactor(0, 0)
        self.h_splitter.setStretchFactor(1, 1)
        self.h_splitter.setSizes([250, 950])

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setPlaceholderText(">> 编译日志输出控制台，准备就绪...")
        self.log_console.setMinimumHeight(100)
        self.v_splitter.addWidget(self.log_console)
        
        self.log_console.hide()

        self._setup_toolbar()

    def _setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        open_action = QAction("📂 打开", self)
        open_action.setToolTip("打开 .tex 文件 (Ctrl+O)")
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)

        save_action = QAction("💾 保存", self)
        save_action.setToolTip("保存到原文件 (Ctrl+S)")
        save_action.triggered.connect(self.save_file)
        toolbar.addAction(save_action)
        
        compile_action = QAction("🚀 编译预览", self)
        compile_action.setToolTip("使用 XeLaTeX 一键编译当前文件并打开 PDF (F5)")
        compile_action.triggered.connect(lambda: self._compile_doc("xelatex"))
        toolbar.addAction(compile_action)

        toolbar.addSeparator()

        self.zen_toggle = QAction("🧘 Zen 模式", self)
        self.zen_toggle.setCheckable(True)
        self.zen_toggle.setChecked(True)
        self.zen_toggle.setToolTip("切换 Zen 模式 - 隐藏语法噪音 (Ctrl+Shift+Z)")
        self.zen_toggle.triggered.connect(self._toggle_zen_mode)
        toolbar.addAction(self.zen_toggle)

        self.wrap_toggle = QAction("↩️ 自动换行", self)
        self.wrap_toggle.setCheckable(True)
        self.wrap_toggle.setChecked(False) 
        self.wrap_toggle.setToolTip("自动折行以适应窗口宽度")
        self.wrap_toggle.triggered.connect(self._toggle_word_wrap)
        toolbar.addAction(self.wrap_toggle)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  字号: "))
        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(10, 24)
        self.font_size_slider.setValue(13)
        self.font_size_slider.setFixedWidth(120)
        self.font_size_slider.setToolTip("调整字体大小 (Ctrl+滚轮)")
        self.font_size_slider.valueChanged.connect(self._change_font_size)
        toolbar.addWidget(self.font_size_slider)

        self.font_size_label = QLabel(" 13pt ")
        toolbar.addWidget(self.font_size_label)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  行距: "))
        self.line_spacing_slider = QSlider(Qt.Horizontal)
        self.line_spacing_slider.setRange(100, 250)
        self.line_spacing_slider.setValue(160)
        self.line_spacing_slider.setFixedWidth(100)
        self.line_spacing_slider.setToolTip("调整行间距")
        self.line_spacing_slider.valueChanged.connect(self._change_line_spacing)
        toolbar.addWidget(self.line_spacing_slider)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  主题: "))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.setCurrentText(self.current_theme_name)
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        self.theme_combo.setFixedWidth(150)
        toolbar.addWidget(self.theme_combo)

        toolbar.addSeparator()

        sidebar_toggle = QAction("📑 侧边栏", self)
        sidebar_toggle.setCheckable(True)
        sidebar_toggle.setChecked(True)
        sidebar_toggle.setToolTip("显示/隐藏左侧大纲与项目结构 (Ctrl+Shift+O)")
        sidebar_toggle.triggered.connect(self._toggle_sidebar)
        toolbar.addAction(sidebar_toggle)
        self.sidebar_toggle = sidebar_toggle
        
        log_toggle = QAction("💻 日志台", self)
        log_toggle.setCheckable(True)
        log_toggle.setChecked(False)
        log_toggle.setToolTip("显示/隐藏底部编译输出控制台")
        log_toggle.triggered.connect(self._toggle_log_console)
        toolbar.addAction(log_toggle)
        self.log_toggle = log_toggle

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+W"), self, self.close) 

    def _setup_menus(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction("打开(&O)...", self.open_file, "Ctrl+O")

        self.recent_menu = file_menu.addMenu("最近打开")
        self._update_recent_menu()

        file_menu.addAction("保存(&S)", self.save_file, "Ctrl+S")
        file_menu.addAction("另存为(&A)...", self.save_file_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        file_menu.addAction("退出(&Q)", self.close, "Ctrl+Q")

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")
        edit_menu.addAction("撤销", self.editor.undo, "Ctrl+Z")
        edit_menu.addAction("重做", self.editor.redo, "Ctrl+Y")
        edit_menu.addSeparator()
        edit_menu.addAction("注释/取消注释", self.editor.toggle_comment, "Ctrl+/")
        edit_menu.addSeparator()
        edit_menu.addAction("查找...", self._show_find, "Ctrl+F")
        edit_menu.addAction("替换...", self._show_replace, "Ctrl+H")
        edit_menu.addAction("跳转到行...", self._goto_line, "Ctrl+G")
        edit_menu.addSeparator()
        
        self.spell_action = QAction("英文拼写检查与建议", self, checkable=True)
        self.spell_action.setChecked(HAS_SPELLCHECKER)
        self.spell_action.triggered.connect(self._toggle_spellcheck)
        edit_menu.addAction(self.spell_action)

        # 插入菜单
        insert_menu = menubar.addMenu("插入(&I)")
        insert_menu.addAction("加粗文字 \\textbf{}", lambda: self._wrap_text("\\textbf{", "}"), "Ctrl+B")
        insert_menu.addAction("斜体文字 \\textit{}", lambda: self._wrap_text("\\textit{", "}"), "Ctrl+I")
        insert_menu.addAction("强调文字 \\emph{}", lambda: self._wrap_text("\\emph{", "}"), "Ctrl+E")
        insert_menu.addSeparator()
        insert_menu.addAction("行内公式 $...$", lambda: self._wrap_text("$", "$"), "Ctrl+D")
        insert_menu.addAction("行间公式 $$...$$", lambda: self._wrap_text("$$\n", "\n$$"), "Ctrl+M")
        
        math_menu = insert_menu.addMenu("常用数学与希腊符号 (Math & Greek)")
        math_menu.addAction("𝛼 (\\alpha)", lambda: self._insert_snippet("\\alpha"))
        math_menu.addAction("𝛽 (\\beta)", lambda: self._insert_snippet("\\beta"))
        math_menu.addAction("𝛾 (\\gamma)", lambda: self._insert_snippet("\\gamma"))
        math_menu.addAction("𝜃 (\\theta)", lambda: self._insert_snippet("\\theta"))
        math_menu.addAction("𝜇 (\\mu)", lambda: self._insert_snippet("\\mu"))
        math_menu.addAction("𝜋 (\\pi)", lambda: self._insert_snippet("\\pi"))
        math_menu.addAction("𝜎 (\\sigma)", lambda: self._insert_snippet("\\sigma"))
        math_menu.addSeparator()
        math_menu.addAction("分数 (\\frac)", lambda: self._insert_snippet("\\frac{分子}{分母}"))
        math_menu.addAction("求和 (\\sum)", lambda: self._insert_snippet("\\sum_{i=1}^{n}"))
        math_menu.addAction("积分 (\\int)", lambda: self._insert_snippet("\\int_{a}^{b} x \\,dx"))
        math_menu.addAction("极限 (\\lim)", lambda: self._insert_snippet("\\lim_{x \\to \\infty}"))

        insert_menu.addSeparator()
        insert_menu.addAction("插入图片 (或直接拖入文件)", self._insert_image_dialog)
        insert_menu.addSeparator()
        insert_menu.addAction("无序列表 (itemize)", lambda: self._insert_snippet("\\begin{itemize}\n  \\item \n  \\item \n\\end{itemize}\n"))
        insert_menu.addAction("有序列表 (enumerate)", lambda: self._insert_snippet("\\begin{enumerate}\n  \\item \n  \\item \n\\end{enumerate}\n"))
        insert_menu.addAction("标准表格 (tabular)", lambda: self._insert_snippet("\\begin{table}[htbp]\n  \\centering\n  \\begin{tabular}{|c|c|c|}\n    \\hline\n    A & B & C \\\\\n    \\hline\n    1 & 2 & 3 \\\\\n    \\hline\n  \\end{tabular}\n  \\caption{表格标题}\n  \\label{tab:my_label}\n\\end{table}\n"))
        insert_menu.addAction("矩阵 (bmatrix)", lambda: self._insert_snippet("\\begin{bmatrix}\n  1 & 0 \\\\\n  0 & 1\n\\end{bmatrix}"))

        # 构建与编译菜单
        build_menu = menubar.addMenu("构建(&B)")
        build_menu.addAction("一键编译 (XeLaTeX)", lambda: self._compile_doc("xelatex"), "F5")
        build_menu.addAction("一键编译 (pdfLaTeX)", lambda: self._compile_doc("pdflatex"), "F6")
        build_menu.addSeparator()
        build_menu.addAction("打开生成的 PDF 预览", self._open_pdf)
        build_menu.addSeparator()
        build_menu.addAction("清理编译垃圾文件 (.aux, .log等)", self._clean_aux_files)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")
        view_menu.addAction("Zen 模式", self._toggle_zen_mode, "Ctrl+Shift+Z")
        view_menu.addAction("侧边栏 (项目大纲)", self._toggle_sidebar, "Ctrl+Shift+O")
        view_menu.addAction("编译输出控制台", self._toggle_log_console, "Ctrl+Shift+L")
        view_menu.addAction("自动换行", self._toggle_word_wrap)
        view_menu.addAction("全屏", self._toggle_fullscreen, "F11")
        view_menu.addSeparator()
        view_menu.addAction("放大字体", self._zoom_in, "Ctrl+=")
        view_menu.addAction("缩小字体", self._zoom_out, "Ctrl+-")

        theme_menu = view_menu.addMenu("主题")
        theme_group = QActionGroup(self)
        for name in THEMES:
            action = QAction(name, self, checkable=True)
            action.setChecked(name == self.current_theme_name)
            action.triggered.connect(lambda checked, n=name: self._change_theme(n))
            theme_group.addAction(action)
            theme_menu.addAction(action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction("关于", self._show_about)
        help_menu.addAction("快捷键列表", self._show_shortcuts)

    def _apply_global_theme(self):
        t = self.current_theme

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {t['bg']};
            }}
            QMenuBar {{
                background-color: {t['toolbar_bg']};
                color: {t['fg']};
                border-bottom: 1px solid {t['border']};
                padding: 2px;
                font-size: 13px;
            }}
            QMenuBar::item:selected {{
                background-color: {t['selection_bg']};
                border-radius: 4px;
            }}
            QMenu {{
                background-color: {t['sidebar_bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 30px 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {t['selection_bg']};
            }}
            QToolBar {{
                background-color: {t['toolbar_bg']};
                border-bottom: 1px solid {t['border']};
                padding: 4px 8px;
                spacing: 4px;
            }}
            QToolButton {{
                background-color: transparent;
                color: {t['fg']};
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 13px;
            }}
            QToolButton:hover {{
                background-color: {t['selection_bg']};
            }}
            QToolButton:checked {{
                background-color: {t['selection_bg']};
                font-weight: bold;
            }}
            QStatusBar {{
                background-color: {t['toolbar_bg']};
                color: {t['comment']};
                border-top: 1px solid {t['border']};
                font-size: 12px;
                padding: 2px 10px;
            }}
            QLabel {{
                color: {t['fg']};
                font-size: 12px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {t['border']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {t['accent']};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QComboBox {{
                background-color: {t['sidebar_bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t['sidebar_bg']};
                color: {t['fg']};
                selection-background-color: {t['selection_bg']};
                border: 1px solid {t['border']};
            }}
            QSplitter::handle {{
                background-color: {t['border']};
                width: 1px;
            }}
            QDialog {{
                background-color: {t['sidebar_bg']};
                color: {t['fg']};
            }}
            QLineEdit {{
                background-color: {t['bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                padding: 4px;
                border-radius: 3px;
            }}
            QPushButton {{
                background-color: {t['toolbar_bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                padding: 4px 8px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {t['selection_bg']};
            }}
            QTabWidget::pane {{
                border: 1px solid {t['border']};
                background: {t['sidebar_bg']};
            }}
            QTabBar::tab {{
                background: {t['toolbar_bg']};
                color: {t['fg']};
                padding: 6px 16px;
                border: 1px solid {t['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {t['sidebar_bg']};
                font-weight: bold;
                border-top: 2px solid {t['accent']};
            }}
            QTreeView {{
                background-color: {t['sidebar_bg']};
                color: {t['fg']};
                border: none;
                font-size: 12px;
            }}
            QTreeView::item:selected {{
                background-color: {t['selection_bg']};
                color: {t['selection_fg']};
            }}
            QTreeView::item:hover {{
                background-color: {t['line_highlight']};
            }}
        """)

        self.editor.apply_theme(t)
        self.outline.apply_theme(t)
        
        self.log_console.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t['sidebar_bg']};
                color: {t['comment']};
                font-family: Consolas, monospace;
                font-size: 12px;
                border: 1px solid {t['border']};
                padding: 5px;
            }}
        """)

    # --- 文件操作 ---
    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开 LaTeX 文件", "",
            "LaTeX 文件 (*.tex);;所有文件 (*.*)"
        )
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path):
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "错误", "文件不存在。")
            self._remove_recent_file(file_path)
            return

        try:
            content = None
            for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                QMessageBox.critical(self, "错误", "无法读取文件：编码不支持")
                return

            self.current_file = file_path
            self.editor.setPlainText(content)
            self.editor.set_modified(False)

            filename = os.path.basename(file_path)
            self.status_info.file_label.setText(f"📄 {filename}")
            self.setWindowTitle(f"LaTeX 清阅编辑器 - {filename}")

            self._update_outline()
            self._add_recent_file(file_path)
            
            dir_path = os.path.dirname(file_path)
            self.file_model.setRootPath(dir_path)
            self.file_tree.setRootIndex(self.file_model.index(dir_path))

            self._auto_save_timer.start(60000)

            self.status_info.save_label.setText("✅ 已加载")
            QTimer.singleShot(3000, lambda: self.status_info.save_label.setText(""))

        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败:\n{e}")

    def save_file(self):
        if not self.current_file:
            self.save_file_as()
            return

        try:
            content = self.editor.toPlainText()
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(content)

            self.editor.set_modified(False)
            self.status_info.save_label.setText("✅ 已保存")
            self.setWindowTitle(
                f"LaTeX 清阅编辑器 - {os.path.basename(self.current_file)}"
            )
            QTimer.singleShot(3000, lambda: self.status_info.save_label.setText(""))

        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存文件:\n{e}")

    def save_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "",
            "LaTeX 文件 (*.tex);;所有文件 (*.*)"
        )
        if file_path:
            self.current_file = file_path
            self._add_recent_file(file_path)
            self.save_file()

    def _auto_save(self):
        if self.current_file and self.editor.is_modified:
            self.save_file()
            self.status_info.save_label.setText("🔄 自动保存")
            QTimer.singleShot(2000, lambda: self.status_info.save_label.setText(""))

    def _add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        self.recent_files.insert(0, file_path)
        if len(self.recent_files) > self.max_recent:
            self.recent_files = self.recent_files[:self.max_recent]
        self._update_recent_menu()

    def _remove_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        self._update_recent_menu()

    def _update_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            empty_action = QAction("(无记录)", self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return

        for path in self.recent_files:
            action = QAction(os.path.basename(path), self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self._load_file(p))
            self.recent_menu.addAction(action)

        self.recent_menu.addSeparator()
        clear_action = QAction("清空记录", self)
        clear_action.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_action)

    def _clear_recent(self):
        self.recent_files.clear()
        self._update_recent_menu()
        
    def _on_file_tree_double_clicked(self, index: QModelIndex):
        file_path = self.file_model.filePath(index)
        if os.path.isfile(file_path):
            if file_path.lower().endswith('.tex'):
                if self.editor.is_modified:
                    reply = QMessageBox.question(self, "切换文件", "当前文件有未保存的修改，切换前是否保存？",
                                                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
                    if reply == QMessageBox.Save:
                        self.save_file()
                    elif reply == QMessageBox.Cancel:
                        return
                self._load_file(file_path)
            elif file_path.lower().endswith('.pdf'):
                self._open_specific_pdf(file_path)
            else:
                try:
                    if platform.system() == 'Darwin':
                        subprocess.call(('open', file_path))
                    elif platform.system() == 'Windows':
                        os.startfile(file_path)
                    else:
                        subprocess.call(('xdg-open', file_path))
                except:
                    pass

    # --- 编译与清理功能 ---
    def _compile_doc(self, engine="xelatex"):
        if not self.current_file:
            QMessageBox.warning(self, "提示", "在编译前，请先保存文件。")
            self.save_file_as()
            if not self.current_file: return
        
        if self.editor.is_modified:
            self.save_file()
            
        self.status_info.save_label.setText(f"⏳ 正在编译({engine})... 请稍候")
        
        self.log_console.clear()
        self.log_console.append(f"[{engine}] 编译开始...")
        if not self.log_console.isVisible():
            self._toggle_log_console()
        
        self.compile_thread = CompileThread(self.current_file, engine)
        self.compile_thread.finished.connect(self._on_compile_finished)
        self.compile_thread.start()

    def _on_compile_finished(self, success, message, full_log):
        self.log_console.append(full_log)
        
        if success:
            self.status_info.save_label.setText("✅ " + message)
            self.log_console.append("\n" + "="*40 + f"\n编译结束: {message}\n" + "="*40)
            self._open_pdf() 
        else:
            self.status_info.save_label.setText("❌ 编译失败")
            self.log_console.append("\n" + "!"*40 + f"\n编译失败: 存在致命错误\n" + "!"*40)
            QMessageBox.warning(self, "编译失败", "编译遇到致命错误，请查看底部日志控制台进行排查。")
            
        QTimer.singleShot(4000, lambda: self.status_info.save_label.setText(""))

    def _open_pdf(self):
        if not self.current_file: return
        pdf_path = os.path.splitext(self.current_file)[0] + ".pdf"
        self._open_specific_pdf(pdf_path)
        
    def _open_specific_pdf(self, pdf_path):
        if os.path.exists(pdf_path):
            try:
                if platform.system() == 'Darwin':       
                    subprocess.call(('open', pdf_path))
                elif platform.system() == 'Windows':    
                    os.startfile(pdf_path)
                else:                                   
                    subprocess.call(('xdg-open', pdf_path))
            except Exception as e:
                QMessageBox.warning(self, "打开失败", f"无法调用系统阅读器:\n{str(e)}")
        else:
            QMessageBox.warning(self, "提示", "未找到对应的 PDF 文件。")

    def _clean_aux_files(self):
        if not self.current_file: return
        base_name = os.path.splitext(self.current_file)[0]
        exts = ['.aux', '.log', '.out', '.toc', '.gz', '.fls', '.fdb_latexmk', '.synctex.gz', '.bbl', '.blg']
        count = 0
        for ext in exts:
            path = base_name + ext
            if os.path.exists(path):
                try:
                    os.remove(path)
                    count += 1
                except:
                    pass
        
        msg = f"🧹 成功清理了 {count} 个辅助文件"
        self.status_info.save_label.setText(msg)
        QMessageBox.information(self, "清理完成", msg)
        QTimer.singleShot(3000, lambda: self.status_info.save_label.setText(""))

    def _insert_snippet(self, text):
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    # --- 视图与格式化操作 ---
    def _toggle_zen_mode(self):
        if hasattr(self, 'zen_toggle'):
            is_zen = self.zen_toggle.isChecked()
        else:
            is_zen = not self.editor._zen_mode
            self.zen_toggle.setChecked(is_zen)

        self.editor.set_zen_mode(is_zen)
        mode_text = "🧘 Zen 模式" if is_zen else "📝 完整模式"
        self.status_info.mode_label.setText(mode_text)

    def _toggle_word_wrap(self):
        if hasattr(self, 'wrap_toggle'):
            do_wrap = self.wrap_toggle.isChecked()
        else:
            do_wrap = self.editor.lineWrapMode() == QPlainTextEdit.NoWrap

        if do_wrap:
            self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        else:
            self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)

    def _toggle_sidebar(self):
        visible = not self.left_tabs.isVisible()
        self.left_tabs.setVisible(visible)
        if hasattr(self, 'sidebar_toggle'):
            self.sidebar_toggle.setChecked(visible)
            
    def _toggle_log_console(self):
        visible = not self.log_console.isVisible()
        self.log_console.setVisible(visible)
        if hasattr(self, 'log_toggle'):
            self.log_toggle.setChecked(visible)

    def _toggle_spellcheck(self):
        if not HAS_SPELLCHECKER:
            QMessageBox.warning(self, "缺少依赖库", 
                "未检测到 'pyspellchecker' 库。\n\n"
                "请打开终端或命令行，运行以下命令安装：\n"
                "pip install pyspellchecker"
            )
            self.spell_action.setChecked(False)
            return
            
        is_enabled = self.spell_action.isChecked()
        self.editor.set_spellcheck(is_enabled)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _change_theme(self, theme_name):
        if theme_name in THEMES:
            self.current_theme_name = theme_name
            self.current_theme = THEMES[theme_name]
            self._apply_global_theme()
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentText(theme_name)
            self.theme_combo.blockSignals(False)

    def _change_font_size(self, size):
        font = self.editor.font()
        font.setPointSize(size)
        self.editor.setFont(font)
        self.font_size_label.setText(f" {size}pt ")
        self.editor.setTabStopDistance(
            QFontMetrics(self.editor.font()).horizontalAdvance(' ') * 4
        )

    def _change_line_spacing(self, value):
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = cursor.blockFormat()
        fmt.setLineHeight(value, 1)  
        cursor.setBlockFormat(fmt)
        cursor.clearSelection()
        self.editor.setTextCursor(cursor)

    def _zoom_in(self):
        current = self.font_size_slider.value()
        self.font_size_slider.setValue(min(current + 1, 24))

    def _zoom_out(self):
        current = self.font_size_slider.value()
        self.font_size_slider.setValue(max(current - 1, 10))

    def _wrap_text(self, left_wrapper, right_wrapper):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(left_wrapper + text + right_wrapper)
        else:
            cursor.insertText(left_wrapper + right_wrapper)
            cursor.movePosition(QTextCursor.Left, n=len(right_wrapper))
            self.editor.setTextCursor(cursor)

    def _insert_image_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.pdf *.eps);;所有文件 (*.*)"
        )
        if file_path:
            self._insert_image_code(file_path)

    def _insert_image_code(self, file_path):
        rel_path = file_path
        if self.current_file:
            try:
                rel_path = os.path.relpath(file_path, os.path.dirname(self.current_file))
            except ValueError:
                pass
        
        rel_path = rel_path.replace('\\', '/')
        base_name = os.path.basename(file_path).split('.')[0]
        
        image_code = (
            f"\\begin{{figure}}[htbp]\n"
            f"  \\centering\n"
            f"  \\includegraphics[width=0.8\\textwidth]{{{rel_path}}}\n"
            f"  \\caption{{{base_name}}}\n"
            f"  \\label{{fig:{base_name}}}\n"
            f"\\end{{figure}}\n"
        )
        self.editor.insertPlainText(image_code)

    # --- 导航 ---
    def _navigate_to_line(self, line_number):
        block = self.editor.document().findBlockByLineNumber(line_number)
        cursor = self.editor.textCursor()
        cursor.setPosition(block.position())
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()
        self.editor.setFocus()

    def _goto_line(self):
        from PyQt5.QtWidgets import QInputDialog
        line, ok = QInputDialog.getInt(
            self, "跳转到行", "行号:",
            self.editor.textCursor().blockNumber() + 1,
            1, self.editor.document().blockCount()
        )
        if ok:
            self._navigate_to_line(line - 1)

    def _show_find(self):
        self.find_dialog.show()
        self.find_dialog.focus_find()
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.find_dialog.find_input.setText(cursor.selectedText())

    def _show_replace(self):
        self.find_dialog.show()
        self.find_dialog.focus_replace()
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.find_dialog.find_input.setText(cursor.selectedText())

    # --- 内容更新 ---
    def _on_content_changed(self):
        if self.current_file:
            self.setWindowTitle(
                f"LaTeX 清阅编辑器 - {os.path.basename(self.current_file)} *"
            )
        self._outline_update_timer.start(1000)
        text = self.editor.toPlainText()
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        total = chinese_chars + english_words
        self.status_info.word_count_label.setText(f"约 {total} 字/词")

    def _update_cursor_pos(self):
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.status_info.pos_label.setText(f"行 {line}, 列 {col}")
        
        self.outline.sync_with_line(line - 1)

    def _update_outline(self):
        text = self.editor.toPlainText()
        self.outline.update_outline(text)

    # --- 对话框 ---
    def _show_about(self):
        QMessageBox.about(
            self, "关于 LaTeX 清阅编辑器",
            """<h2>LaTeX 清阅编辑器 v1.5.1 (旗舰增强版)</h2>
            <p>专为科研工作者设计的 LaTeX 生产力工具</p>
            <h3>✨ 核心亮点</h3>
            <ul>
            <li>🚀 <b>一键编译</b> - F5/F6 自动编译并预览 PDF，底部完整日志输出！</li>
            <li>🗂️ <b>项目管理</b> - 左侧标签页集成文档大纲与本地项目资源管理器。</li>
            <li>🧹 <b>空间清理</b> - 自动清理编译冗余文件</li>
            <li>🧘 <b>Zen 模式</b> - 折叠语法噪音，专注内容</li>
            <li>🎨 <b>护眼配色</b> - 4 套精心调校的主题</li>
            <li>🖱️ <b>缩放自由</b> - 按住 Ctrl 滚动鼠标滑轮随时调节代码大小</li>
            <li>💡 <b>智能输入</b> - 丰富代码模板、快捷插入常数数学符号、拖拽传图</li>
            <li>📝 <b>拼写检查</b> - 英语词汇错词提醒与一键替换</li>
            </ul>
            <p>让你的 LaTeX 写作体验如清风般舒适 🍃</p>"""
        )

    def _show_shortcuts(self):
        QMessageBox.information(
            self, "快捷键列表",
            """<h3>快捷键列表</h3>
            <table cellpadding="4">
            <tr><td><b>F5 / F6</b></td><td>一键编译 (XeLaTeX / pdfLaTeX)</td></tr>
            <tr><td><b>Ctrl+滚轮</b></td><td>放大 / 缩小代码字体</td></tr>
            <tr><td><b>Ctrl+O</b></td><td>打开文件</td></tr>
            <tr><td><b>Ctrl+S</b></td><td>保存文件</td></tr>
            <tr><td><b>Ctrl+Shift+S</b></td><td>另存为</td></tr>
            <tr><td><b>Ctrl+Shift+Z</b></td><td>切换 Zen 模式</td></tr>
            <tr><td><b>Ctrl+Shift+O</b></td><td>显示/隐藏侧边栏</td></tr>
            <tr><td><b>Ctrl+Shift+L</b></td><td>显示/隐藏编译日志输出台</td></tr>
            <tr><td><b>Ctrl+/</b></td><td>快捷注释/取消注释</td></tr>
            <tr><td><b>Ctrl+F</b></td><td>查找</td></tr>
            <tr><td><b>Ctrl+H</b></td><td>替换</td></tr>
            <tr><td><b>Ctrl+B</b></td><td>加粗文本</td></tr>
            <tr><td><b>Ctrl+I</b></td><td>斜体文本</td></tr>
            <tr><td><b>Ctrl+E</b></td><td>强调文本</td></tr>
            <tr><td><b>Ctrl+D</b></td><td>行内公式</td></tr>
            <tr><td><b>Ctrl+M</b></td><td>行间公式</td></tr>
            <tr><td><b>Ctrl+G</b></td><td>跳转到行</td></tr>
            <tr><td><b>F11</b></td><td>全屏</td></tr>
            <tr><td><b>Ctrl+Z</b></td><td>撤销</td></tr>
            <tr><td><b>Ctrl+Y</b></td><td>重做</td></tr>
            </table>"""
        )

    # --- 设置持久化 ---
    def _load_settings(self):
        settings = QSettings("LaTeXZenEditor", "Settings")
        theme = settings.value("theme", "暖光护眼 (推荐)")
        if theme in THEMES:
            self._change_theme(theme)
        
        font_size = settings.value("font_size", 13, type=int)
        self.font_size_slider.setValue(font_size)
        
        wrap_mode = settings.value("wrap_mode", False, type=bool)
        self.wrap_toggle.setChecked(wrap_mode)
        self._toggle_word_wrap()

        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        recent = settings.value("recent_files", [])
        if recent:
            self.recent_files = [f for f in recent if os.path.exists(f)]
            self._update_recent_menu()

        last_file = settings.value("last_file", "")
        if last_file and os.path.exists(last_file):
            self._load_file(last_file)

    def _save_settings(self):
        settings = QSettings("LaTeXZenEditor", "Settings")
        settings.setValue("theme", self.current_theme_name)
        settings.setValue("font_size", self.font_size_slider.value())
        settings.setValue("wrap_mode", self.wrap_toggle.isChecked())
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("recent_files", self.recent_files)
        if self.current_file:
            settings.setValue("last_file", self.current_file)

    def closeEvent(self, event):
        if self.editor.is_modified:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "文件已修改，是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                self.save_file()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        self._save_settings()
        event.accept()

    # --- 拖放支持 ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(('.tex', '.png', '.jpg', '.jpeg', '.pdf', '.eps')):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.endswith('.tex'):
                self._load_file(file_path)
                break
            elif file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf', '.eps')):
                self._insert_image_code(file_path)
                break