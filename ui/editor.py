# -*- coding: utf-8 -*-
import re
from PyQt5.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QApplication, QMenu
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QSize
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QPainter, QFontMetrics, QFont

from core.syntax import LaTeXZenHighlighter

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

class ZenEditor(QPlainTextEdit):
    content_changed = pyqtSignal()
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()

    def __init__(self, theme, spell_checker=None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._modified = False
        self._zen_mode = True
        
        self.spell_checker = spell_checker
        self.enable_spellcheck = spell_checker is not None

        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self._setup_font()
        self.apply_theme(theme)
        
        self.highlighter = LaTeXZenHighlighter(
            self.document(), theme, self._zen_mode, self.spell_checker
        )

        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        self.setTabStopDistance(QFontMetrics(self.font()).horizontalAdvance(' ') * 4)
        self.textChanged.connect(self._on_text_changed)

    def _setup_font(self):
        font_families = [
            "Cascadia Code", "JetBrains Mono", "Fira Code",
            "Source Code Pro", "Consolas", "Monaco",
            "Microsoft YaHei Mono", "微软雅黑"
        ]
        font = QFont()
        font.setStyleHint(QFont.Monospace)
        for family in font_families:
            font.setFamily(family)
            if QFontMetrics(font).horizontalAdvance('W') > 0:
                break
        font.setPointSize(13)
        font.setLetterSpacing(QFont.PercentageSpacing, 102)
        self.setFont(font)

    def apply_theme(self, theme):
        self.theme = theme
        t = theme
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {t['bg']};
                color: {t['fg']};
                border: none;
                selection-background-color: {t['selection_bg']};
                selection-color: {t['selection_fg']};
                padding-left: 8px;
                padding-top: 10px;
            }}
        """)
        if hasattr(self, 'highlighter'):
            self.highlighter.update_theme(theme, self._zen_mode)
        self.highlight_current_line()
        self.update()

    def set_zen_mode(self, enabled):
        self._zen_mode = enabled
        if hasattr(self, 'highlighter'):
            self.highlighter.update_theme(self.theme, enabled)
            
    def set_spellcheck(self, enabled):
        self.enable_spellcheck = enabled
        self.highlighter.set_spellcheck(enabled)

    def _on_text_changed(self):
        self._modified = True
        self.content_changed.emit()

    @property
    def is_modified(self):
        return self._modified

    def set_modified(self, value):
        self._modified = value

    def line_number_area_width(self):
        digits = max(1, len(str(self.blockCount())))
        space = 20 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        t = self.theme
        painter.fillRect(event.rect(), QColor(t['sidebar_bg']))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block)
                    .translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        current_line = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_line:
                    painter.setPen(QColor(t['fg']))
                    font = painter.font()
                    font.setBold(True)
                    painter.setFont(font)
                else:
                    painter.setPen(QColor(t['comment']))
                    font = painter.font()
                    font.setBold(False)
                    painter.setFont(font)

                painter.drawText(
                    0, top,
                    self.line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignRight | Qt.AlignVCenter, number
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in_requested.emit()
            else:
                self.zoom_out_requested.emit()
            event.accept()
        else:
            super().wheelEvent(event)
        
    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()

        if self.spell_checker and self.enable_spellcheck:
            cursor = self.cursorForPosition(event.pos())
            cursor.select(QTextCursor.WordUnderCursor)
            word = cursor.selectedText()

            if word and re.match(r'^[a-zA-Z]{2,}$', word):
                if not (word.isupper() or (not word.islower() and not word.istitle())):
                    if not self.spell_checker.known([word.lower()]):
                        candidates = self.spell_checker.candidates(word.lower())
                        if candidates:
                            spell_menu = QMenu("💡 拼写建议 (点击替换)", self)
                            for sug in list(candidates)[:5]:
                                if word.istitle():
                                    sug = sug.capitalize()
                                action = spell_menu.addAction(sug)
                                action.triggered.connect(lambda checked, s=sug, c=cursor: self._replace_word(c, s))
                            
                            if menu.actions():
                                first_action = menu.actions()[0]
                                menu.insertMenu(first_action, spell_menu)
                                menu.insertSeparator(first_action)
                            else:
                                menu.addMenu(spell_menu)

        menu.exec_(event.globalPos())
        
    def _replace_word(self, cursor, new_word):
        cursor.insertText(new_word)

    def keyPressEvent(self, e):
        cursor = self.textCursor()
        pairs = {'{': '}', '[': ']', '(': ')', '$': '$', '"': '"'}
        closing_chars = ['}', ']', ')', '$', '"']

        if e.text() in pairs and cursor.hasSelection():
            char = e.text()
            text = cursor.selectedText()
            cursor.insertText(char + text + pairs[char])
            return

        if e.text() in closing_chars and not cursor.hasSelection():
            pos = cursor.position()
            if pos < self.document().characterCount():
                if self.document().characterAt(pos) == e.text():
                    cursor.movePosition(QTextCursor.Right)
                    self.setTextCursor(cursor)
                    return

        if e.text() in pairs and not cursor.hasSelection():
            char = e.text()
            super().keyPressEvent(e) 
            pos = self.textCursor().position()
            self.insertPlainText(pairs[char]) 
            
            new_cursor = self.textCursor()
            new_cursor.setPosition(pos)
            self.setTextCursor(new_cursor)
            return

        if e.key() == Qt.Key_Backspace and not cursor.hasSelection():
            pos = cursor.position()
            if pos > 0 and pos < self.document().characterCount():
                char_left = self.document().characterAt(pos - 1)
                char_right = self.document().characterAt(pos)
                if char_left in pairs and pairs[char_left] == char_right:
                    cursor.deletePreviousChar() 
                    cursor.deleteChar()         
                    return

        if e.key() == Qt.Key_Return or e.key() == Qt.Key_Enter:
            line_text = cursor.block().text()
            indentation = len(line_text) - len(line_text.lstrip(' \t'))
            indent_str = line_text[:indentation]
            
            match = re.search(r'\\begin\{([^}]+)\}\s*$', line_text)

            super().keyPressEvent(e) 

            if match:
                env_name = match.group(1)
                extra_indent = "    " 
                self.insertPlainText(indent_str + extra_indent)
                
                current_pos = self.textCursor().position()
                
                self.insertPlainText("\n" + indent_str + f"\\end{{{env_name}}}")
                
                new_cursor = self.textCursor()
                new_cursor.setPosition(current_pos)
                self.setTextCursor(new_cursor)
            else:
                if indent_str:
                    self.insertPlainText(indent_str)
            return

        super().keyPressEvent(e)

    def toggle_comment(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.LineUnderCursor)

        start_pos = cursor.selectionStart()
        end_pos = cursor.selectionEnd()

        cursor.setPosition(start_pos)
        start_block = cursor.blockNumber()
        cursor.setPosition(end_pos)
        end_block = cursor.blockNumber()

        if cursor.positionInBlock() == 0 and end_block > start_block:
            end_block -= 1

        cursor.beginEditBlock()

        all_commented = True
        for i in range(start_block, end_block + 1):
            block = self.document().findBlockByNumber(i)
            text = block.text().lstrip()
            if not text.startswith('%'):
                all_commented = False
                break

        for i in range(start_block, end_block + 1):
            block = self.document().findBlockByNumber(i)
            cursor.setPosition(block.position())
            text = block.text()
            if all_commented:
                idx = text.find('%')
                if idx != -1:
                    cursor.setPosition(block.position() + idx)
                    cursor.deleteChar()
                    if cursor.positionInBlock() < len(block.text()) and self.document().characterAt(cursor.position()) == ' ':
                        cursor.deleteChar()
            else:
                stripped_text = text.lstrip()
                if not stripped_text.startswith('%'):
                    idx = len(text) - len(stripped_text)
                    cursor.setPosition(block.position() + idx)
                    cursor.insertText('% ')

        cursor.endEditBlock()

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(self.theme['line_highlight'])
            selection.format.setBackground(line_color)
            selection.format.setProperty(
                QTextCharFormat.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self._match_brackets(extra_selections)
        self.setExtraSelections(extra_selections)

    def _match_brackets(self, extra_selections):
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        pos = cursor.positionInBlock()

        pairs = {'{': '}', '[': ']', '(': ')', '}': '{', ']': '[', ')': '('}
        right_open = ['{', '[', '(']

        char_under = text[pos] if pos < len(text) else ''
        char_left = text[pos-1] if pos > 0 else ''

        match_char = ''
        start_pos = -1
        direction = 0 

        if char_under in pairs:
            match_char = pairs[char_under]
            start_pos = cursor.position()
            direction = 1 if char_under in right_open else -1
        elif char_left in pairs:
            match_char = pairs[char_left]
            start_pos = cursor.position() - 1
            direction = 1 if char_left in right_open else -1

        if start_pos != -1:
            doc = self.document()
            match_cursor = QTextCursor(doc)
            match_cursor.setPosition(start_pos)
            open_char = doc.characterAt(start_pos)

            count = 1
            max_search = 5000 
            search_count = 0

            while search_count < max_search:
                search_count += 1
                if direction == 1:
                    if not match_cursor.movePosition(QTextCursor.Right): break
                else:
                    if not match_cursor.movePosition(QTextCursor.Left): break

                curr_pos = match_cursor.position() if direction == 1 else match_cursor.position() - 1
                curr_char = doc.characterAt(curr_pos)

                if curr_char == open_char:
                    count += 1
                elif curr_char == match_char:
                    count -= 1
                    if count == 0:
                        fmt = QTextCharFormat()
                        fmt.setBackground(QColor(self.theme['accent']))
                        fmt.setForeground(QColor(self.theme['bg']))
                        fmt.setFontWeight(QFont.Bold)

                        orig_sel = QTextEdit.ExtraSelection()
                        orig_sel.format = fmt
                        c1 = QTextCursor(doc)
                        c1.setPosition(start_pos)
                        c1.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                        orig_sel.cursor = c1
                        extra_selections.append(orig_sel)

                        match_sel = QTextEdit.ExtraSelection()
                        match_sel.format = fmt
                        c2 = QTextCursor(doc)
                        c2.setPosition(curr_pos)
                        c2.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                        match_sel.cursor = c2
                        extra_selections.append(match_sel)
                        break