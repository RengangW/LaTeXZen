# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt5.QtGui import QTextCursor, QTextDocument
from PyQt5.QtCore import Qt

class FindReplaceDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("查找与替换")
        self.setWindowFlags(Qt.Tool) 
        self.resize(350, 120)

        layout = QGridLayout(self)

        layout.addWidget(QLabel("查找:"), 0, 0)
        self.find_input = QLineEdit()
        layout.addWidget(self.find_input, 0, 1, 1, 3)

        layout.addWidget(QLabel("替换为:"), 1, 0)
        self.replace_input = QLineEdit()
        layout.addWidget(self.replace_input, 1, 1, 1, 3)

        self.btn_find_prev = QPushButton("上一个")
        self.btn_find_next = QPushButton("下一个")
        self.btn_replace = QPushButton("替换")
        self.btn_replace_all = QPushButton("全部替换")

        layout.addWidget(self.btn_find_prev, 2, 0)
        layout.addWidget(self.btn_find_next, 2, 1)
        layout.addWidget(self.btn_replace, 2, 2)
        layout.addWidget(self.btn_replace_all, 2, 3)

        self.btn_find_next.clicked.connect(self.find_next)
        self.btn_find_prev.clicked.connect(self.find_prev)
        self.btn_replace.clicked.connect(self.replace)
        self.btn_replace_all.clicked.connect(self.replace_all)

        self.find_input.returnPressed.connect(self.find_next)
        self.replace_input.returnPressed.connect(self.replace)

    def find_next(self):
        text = self.find_input.text()
        if not text: return
        found = self.editor.find(text)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(text)

    def find_prev(self):
        text = self.find_input.text()
        if not text: return
        options = QTextDocument.FindBackward
        found = self.editor.find(text, options)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.editor.setTextCursor(cursor)
            self.editor.find(text, options)

    def replace(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == self.find_input.text():
            cursor.insertText(self.replace_input.text())
        self.find_next()

    def replace_all(self):
        text = self.find_input.text()
        if not text: return
        replace_text = self.replace_input.text()

        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cursor)

        count = 0
        while self.editor.find(text):
            self.editor.textCursor().insertText(replace_text)
            count += 1

        cursor.endEditBlock()
        QMessageBox.information(self, "替换完毕", f"共替换了 {count} 处匹配项。")

    def focus_find(self):
        self.find_input.setFocus()
        self.find_input.selectAll()

    def focus_replace(self):
        self.replace_input.setFocus()
        self.replace_input.selectAll()