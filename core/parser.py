# -*- coding: utf-8 -*-
import re

class LaTeXParser:
    """解析 LaTeX 源码，提取结构化内容"""

    SECTION_COMMANDS = [
        'chapter', 'section', 'subsection', 'subsubsection',
        'paragraph', 'subparagraph'
    ]

    @staticmethod
    def extract_document_structure(text):
        """提取文档大纲结构"""
        structure = []
        lines = text.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 忽略被注释的标题
            if stripped.startswith('%'):
                continue
            for cmd in LaTeXParser.SECTION_COMMANDS:
                pattern = rf'\\{cmd}\*?\s*(?:\[.*?\])?\s*\{{(.*?)\}}'
                match = re.search(pattern, stripped)
                if match:
                    structure.append({
                        'level': LaTeXParser.SECTION_COMMANDS.index(cmd),
                        'title': match.group(1),
                        'line': i,
                        'command': cmd
                    })
                    break
        return structure