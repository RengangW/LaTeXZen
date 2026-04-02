# -*- coding: utf-8 -*-
import re
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from core.parser import LaTeXParser

class LaTeXZenHighlighter(QSyntaxHighlighter):
    def __init__(self, parent, theme, zen_mode=True, spell_checker=None):
        super().__init__(parent)
        self.theme = theme
        self.zen_mode = zen_mode
        self.spell_checker = spell_checker
        self.enable_spellcheck = spell_checker is not None
        self._build_rules()

    def set_spellcheck(self, enabled):
        self.enable_spellcheck = enabled
        self.rehighlight()

    def update_theme(self, theme, zen_mode=None):
        self.theme = theme
        if zen_mode is not None:
            self.zen_mode = zen_mode
        self._build_rules()
        self.rehighlight()

    def _build_rules(self):
        self.rules = []
        t = self.theme

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor(t["comment"]))
        comment_fmt.setFontItalic(True)
        if self.zen_mode:
            c = QColor(t["comment"])
            c.setAlpha(120)
            comment_fmt.setForeground(c)

        cmd_fmt = QTextCharFormat()
        if self.zen_mode:
            c = QColor(t["fold_marker"])
            cmd_fmt.setForeground(c)
            cmd_fmt.setFontPointSize(max(8, QApplication.font().pointSize() - 2))
        else:
            cmd_fmt.setForeground(QColor(t["keyword"]))

        brace_fmt = QTextCharFormat()
        if self.zen_mode:
            c = QColor(t["fold_marker"])
            brace_fmt.setForeground(c)
        else:
            brace_fmt.setForeground(QColor(t["accent"]))

        math_fmt = QTextCharFormat()
        math_fmt.setForeground(QColor(t["math"]))
        math_fmt.setFontItalic(True)

        heading_fmt = QTextCharFormat()
        heading_fmt.setForeground(QColor(t["heading"]))
        heading_fmt.setFontWeight(QFont.Bold)

        env_fmt = QTextCharFormat()
        if self.zen_mode:
            env_fmt.setForeground(QColor(t["fold_marker"]))
        else:
            env_fmt.setForeground(QColor(t["keyword"]))
            env_fmt.setFontWeight(QFont.Bold)

        bold_content_fmt = QTextCharFormat()
        bold_content_fmt.setFontWeight(QFont.Bold)
        bold_content_fmt.setForeground(QColor(t["fg"]))

        italic_content_fmt = QTextCharFormat()
        italic_content_fmt.setFontItalic(True)
        italic_content_fmt.setForeground(QColor(t["fg"]))

        self.rules.append((re.compile(r'\\[a-zA-Z@]+'), cmd_fmt, 0))
        self.rules.append((re.compile(r'[{}]'), brace_fmt, 0))
        self.rules.append((re.compile(r'[\[\]]'), brace_fmt, 0))

        for cmd in LaTeXParser.SECTION_COMMANDS:
            pattern = re.compile(rf'\\{cmd}\*?\s*(?:\[.*?\])?\s*\{{([^}}]*)\}}')
            self.rules.append((pattern, heading_fmt, 1))

        self.rules.append((re.compile(r'\\textbf\s*\{([^}]*)\}'), bold_content_fmt, 1))
        self.rules.append((re.compile(r'\\(?:textit|emph)\s*\{([^}]*)\}'), italic_content_fmt, 1))
        self.rules.append((re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)'), math_fmt, 0))
        self.rules.append((re.compile(r'\\\(.*?\\\)'), math_fmt, 0))
        self.rules.append((re.compile(r'\\(?:begin|end)\s*\{[^}]*\}'), env_fmt, 0))

        self.comment_pattern = re.compile(r'(?<!\\)%.*$')
        self.comment_fmt = comment_fmt

    def highlightBlock(self, text):
        for pattern, fmt, group in self.rules:
            for match in pattern.finditer(text):
                start = match.start(group)
                length = match.end(group) - start
                self.setFormat(start, length, fmt)

        match = self.comment_pattern.search(text)
        if match:
            self.setFormat(match.start(), len(text) - match.start(), self.comment_fmt)

        if self.enable_spellcheck and self.spell_checker:
            for m in re.finditer(r'(?<!\\)\b[a-zA-Z]{2,}\b', text):
                word = m.group()
                if word.isupper() or (not word.islower() and not word.istitle()):
                    continue
                if not self.spell_checker.known([word.lower()]):
                    fmt = self.format(m.start())
                    fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                    fmt.setUnderlineColor(Qt.red)
                    self.setFormat(m.start(), len(word), fmt)