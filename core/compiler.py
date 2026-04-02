# -*- coding: utf-8 -*-
import os
import subprocess
import platform
from PyQt5.QtCore import QThread, pyqtSignal

class CompileThread(QThread):
    finished = pyqtSignal(bool, str, str) # 成功标志, 提示信息, 完整日志输出

    def __init__(self, file_path, engine="xelatex"):
        super().__init__()
        self.file_path = file_path
        self.engine = engine

    def run(self):
        try:
            dir_name = os.path.dirname(self.file_path)
            base_name = os.path.basename(self.file_path)
            # 使用 nonstopmode 以免出现错误时卡在命令行等待输入
            cmd = [self.engine, "-interaction=nonstopmode", base_name]
            
            # 隐藏 Windows 下的控制台窗口
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # 不使用 text=True，直接捕获字节流，自己进行安全解码
            process = subprocess.run(
                cmd, cwd=dir_name, capture_output=True, timeout=120, startupinfo=startupinfo
            )
            
            # 安全解码输出，避免 Windows 下 gbk/utf-8 冲突导致崩溃
            def safe_decode(b_str):
                if not b_str:
                    return ""
                try:
                    return b_str.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return b_str.decode('gbk')
                    except UnicodeDecodeError:
                        return b_str.decode('utf-8', errors='replace')

            stdout_text = safe_decode(process.stdout)
            stderr_text = safe_decode(process.stderr)
            full_log = stdout_text + "\n" + stderr_text
            
            # LaTeX 哪怕有警告也会生成 PDF（只要不是致命错误）。通常返回 0 表示完全成功
            if process.returncode == 0:
                self.finished.emit(True, "编译成功", full_log)
            else:
                # 检查是否生成了 pdf 文件（因为有时有警告也会生成 PDF）
                pdf_path = os.path.splitext(self.file_path)[0] + ".pdf"
                if os.path.exists(pdf_path) and os.path.getmtime(pdf_path) > os.path.getmtime(self.file_path) - 5:
                    self.finished.emit(True, "编译完成，但包含警告或非致命错误", full_log)
                else:
                    self.finished.emit(False, "编译失败，请检查 LaTeX 语法错误。", full_log)
        except FileNotFoundError:
            self.finished.emit(False, f"未找到编译器 '{self.engine}'，请确认已安装 TeX 环境并配置了环境变量。", "")
        except subprocess.TimeoutExpired:
            self.finished.emit(False, "编译超时 (超过120秒)。", "")
        except Exception as e:
            self.finished.emit(False, f"编译时发生未知错误: {str(e)}", "")