import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import sys
import io
import threading
import re

from core import (
    split_token, Parser, Checker, Interpreter,
    LexerError, ParseError, CheckError, EclException,
    KEYWORDS, BUILTIN_TYPES,
)


# ============================================================================
# 语法高亮规则
# ============================================================================

# 高亮 token 类型 -> (颜色, 是否加粗)
HIGHLIGHT_COLORS = {
    "keyword":   ("#0033cc", True),   # def / end / if / for / ref / code ...
    "type":      ("#008080", False),  # int / str / list / dict ...
    "builtin":   ("#795e26", False),  # print / len / str / int ...
    "string":    ("#a31515", False),  # "..." / '...'
    "code":      ("#7a3e9d", False),  # `...`
    "comment":   ("#008000", False),  # # ...
    "number":    ("#098658", False),  # 42 / 3.14 / 0xFF
    "operator":  ("#000000", True),   # <- / -> / <-> / ..= ...
    "punct":     ("#666666", False),  # ( ) [ ] { } , :
}

# 内置函数名（用于高亮）
BUILTIN_FUNCS = {
    "print", "input", "type", "len", "str", "int", "float", "bool",
    "range", "abs", "max", "min", "sum",
}

# 操作符（按长度降序，保证 <-> 先于 <- 匹配）
ECL_OPERATORS = sorted([
    "**=", "//=", "..=", "+=", "-=", "*=", "/=", "%=", "<->",
    "**", "//", "..", "==", "!=", "<=", ">=", "->", "<-", "<<", ">>",
    "=>", "=<",
    "+", "-", "*", "/", "%", "=", "<", ">", "!", "|", "&", "^", "~",
], key=len, reverse=True)


def highlight_code(text_widget):
    """对 Text 控件应用 ECL 语法高亮"""
    # 先清空所有高亮
    for tag in HIGHLIGHT_COLORS:
        text_widget.tag_remove(tag, "1.0", tk.END)

    src = text_widget.get("1.0", "end-1c")
    i = 0
    n = len(src)

    def add_tag(tag, start, end):
        text_widget.tag_add(tag, f"1.0 + {start} chars", f"1.0 + {end} chars")

    while i < n:
        ch = src[i]

        # 注释 #
        if ch == "#":
            end = src.find("\n", i)
            if end == -1:
                end = n
            add_tag("comment", i, end)
            i = end
            continue

        # 块注释 /* */
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            if end == -1:
                end = n
            else:
                end += 2
            add_tag("comment", i, end)
            i = end
            continue

        # 字符串 "..." / '...'
        if ch in "\"'":
            quote = ch
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == quote:
                    j += 1
                    break
                if src[j] == "\n":
                    break
                j += 1
            add_tag("string", i, j)
            i = j
            continue

        # 代码字符串 `...`
        if ch == "`":
            j = i + 1
            while j < n and src[j] != "`":
                j += 1
            if j < n:
                j += 1
            add_tag("code", i, j)
            i = j
            continue

        # 数字
        if ch.isdigit():
            j = i
            while j < n and (src[j].isalnum() or src[j] in "._"):
                j += 1
            add_tag("number", i, j)
            i = j
            continue

        # 标识符 / 关键字 / 类型 / 内置函数
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            if word in KEYWORDS:
                add_tag("keyword", i, j)
            elif word in BUILTIN_TYPES:
                add_tag("type", i, j)
            elif word in BUILTIN_FUNCS:
                add_tag("builtin", i, j)
            i = j
            continue

        # 操作符
        matched = False
        for op in ECL_OPERATORS:
            if src[i:i + len(op)] == op:
                add_tag("operator", i, i + len(op))
                i += len(op)
                matched = True
                break
        if matched:
            continue

        # 标点
        if ch in "()[]{}.,:":
            add_tag("punct", i, i + 1)
            i += 1
            continue

        i += 1


# ============================================================================
# IDE 主类
# ============================================================================

class EclIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("ECL IDE - EasyCodingLanguage")
        self.root.geometry("1000x750")
        self.current_file = None

        # 停止标志
        self.stop_event = threading.Event()
        self.running = False

        # 自动补全状态
        self.completion_popup = None
        self.completion_listbox = None
        self.completion_words = []

        # ---------- 工具栏 ----------
        toolbar = tk.Frame(root)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.run_btn = tk.Button(toolbar, text="▶ 运行 (F5)", command=self.run_code,
                                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.run_btn.pack(side=tk.LEFT, padx=4, pady=4)

        self.stop_btn = tk.Button(toolbar, text="■ 停止", command=self.stop_code,
                                  bg="#f44336", fg="white", font=("Arial", 10, "bold"),
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=4, pady=4)

        tk.Button(toolbar, text="保存", command=self.save_file).pack(
            side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="打开", command=self.open_file).pack(
            side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="清空输出", command=self.clear_output).pack(
            side=tk.LEFT, padx=4)

        # ---------- 主区域 ----------
        paned = tk.PanedWindow(root, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 编辑区
        editor_frame = tk.Frame(paned)
        self.line_numbers = tk.Text(editor_frame, width=4, padx=4, takefocus=0,
                                    border=0, background="#f0f0f0",
                                    state=tk.DISABLED, font=("Consolas", 12))
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.NONE,
                                                font=("Consolas", 12), undo=True)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 配置高亮 tag
        for tag, (color, bold) in HIGHLIGHT_COLORS.items():
            self.editor.tag_config(tag, foreground=color,
                                   font=("Consolas", 12, "bold") if bold else ("Consolas", 12))
        self.editor.tag_config("error_line", background="#ffe0e0")
        self.editor.tag_config("current_line", background="#f5f5f5")

        # 事件绑定
        self.editor.bind("<KeyRelease>", self.on_key_release)
        self.editor.bind("<MouseWheel>", self.sync_scroll)
        self.editor.bind("<Button-1>", self.on_click)
        self.editor.bind("<Tab>", self.on_tab)
        self.editor.bind("<Escape>", lambda e: self.hide_completion())
        self.editor.bind("<Down>", self.on_completion_down)
        self.editor.bind("<Up>", self.on_completion_up)
        self.editor.bind("<Return>", self.on_completion_enter)

        paned.add(editor_frame, stretch="always")

        # 输出区
        output_frame = tk.Frame(paned)
        self.output = scrolledtext.ScrolledText(output_frame, height=10,
                                                font=("Consolas", 11),
                                                state=tk.DISABLED)
        self.output.pack(fill=tk.BOTH, expand=True)
        self.output.tag_config("error", foreground="#d32f2f")
        self.output.tag_config("ok", foreground="#388e3c")
        self.output.tag_config("info", foreground="#1976d2")
        paned.add(output_frame, stretch="never")

        # 快捷键
        self.root.bind("<F5>", lambda e: self.run_code())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-space>", lambda e: self.show_completion())

        self.update_line_numbers()
        self.apply_highlight()

    # ========================================================================
    # P1: 语法高亮
    # ========================================================================

    def apply_highlight(self):
        highlight_code(self.editor)

    def on_key_release(self, event=None):
        self.update_line_numbers()
        self.apply_highlight()
        if event and event.keysym not in ("Down", "Up", "Return", "Escape"):
            self.show_completion(auto=True)

    def on_click(self, event=None):
        self.update_line_numbers()
        self.hide_completion()

    # ========================================================================
    # 行号
    # ========================================================================

    def update_line_numbers(self):
        lines = self.editor.get("1.0", "end-1c").count("\n") + 1
        nums = "\n".join(str(i) for i in range(1, lines + 1))
        self.line_numbers.config(state=tk.NORMAL)
        self.line_numbers.delete("1.0", tk.END)
        self.line_numbers.insert("1.0", nums)
        self.line_numbers.config(state=tk.DISABLED)

    def sync_scroll(self, event):
        self.line_numbers.yview_moveto(self.editor.yview()[0])
        return "break"

    # ========================================================================
    # P3: 自动补全
    # ========================================================================

    def collect_completion_words(self):
        """收集补全候选：关键字 + 类型 + 内置函数 + 变量名 + 函数名"""
        words = set()
        words.update(KEYWORDS)
        words.update(BUILTIN_TYPES)
        words.update(BUILTIN_FUNCS)
        # 从源码里提取标识符作为变量名/函数名候选
        src = self.editor.get("1.0", "end-1c")
        for m in re.finditer(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", src):
            words.add(m.group(0))
        return sorted(words)

    def get_current_word(self):
        """获取光标前的标识符前缀"""
        line, col = self.editor.index(tk.INSERT).split(".")
        line = int(line)
        col = int(col)
        start = f"{line}.0"
        line_text = self.editor.get(start, f"{line}.end")
        if col > len(line_text):
            col = len(line_text)
        before = line_text[:col]
        m = re.search(r"[a-zA-Z_][a-zA-Z0-9_]*$", before)
        if m:
            return m.group(0)
        return ""

    def show_completion(self, auto=False):
        prefix = self.get_current_word()
        all_words = self.collect_completion_words()

        if auto and len(prefix) < 2:
            self.hide_completion()
            return

        if prefix:
            candidates = [w for w in all_words if w.startswith(
                prefix) and w != prefix]
        else:
            candidates = all_words

        if not candidates:
            self.hide_completion()
            return

        self.completion_words = candidates[:15]

        # 弹出 Listbox
        if self.completion_popup is None:
            self.completion_popup = tk.Toplevel(self.root)
            self.completion_popup.wm_overrideredirect(True)
            self.completion_popup.wm_attributes("-topmost", True)

            frame = tk.Frame(self.completion_popup,
                             bg="#ffffff", bd=1, relief=tk.SOLID)
            frame.pack(fill=tk.BOTH, expand=True)

            self.completion_listbox = tk.Listbox(frame, height=len(self.completion_words),
                                                 font=("Consolas", 11), activestyle="none",
                                                 selectbackground="#cce8ff", bd=0)
            self.completion_listbox.pack(fill=tk.BOTH, expand=True)

            self.completion_listbox.bind(
                "<Button-1>", self.on_completion_click)
            self.completion_listbox.bind(
                "<Double-Button-1>", self.on_completion_click)

        self.completion_listbox.delete(0, tk.END)
        for w in self.completion_words:
            self.completion_listbox.insert(tk.END, w)
        self.completion_listbox.config(
            height=min(len(self.completion_words), 10))

        if self.completion_words:
            self.completion_listbox.selection_set(0)

        # 定位到光标下方
        try:
            x, y, w, h = self.editor.bbox(tk.INSERT)
            self.completion_popup.geometry(
                f"+{x + self.editor.winfo_rootx()}+{y + h + self.editor.winfo_rooty()}")
            self.completion_popup.deiconify()
        except tk.TclError:
            pass

    def hide_completion(self):
        if self.completion_popup:
            self.completion_popup.withdraw()

    def on_completion_down(self, event):
        if self.completion_popup and self.completion_popup.winfo_viewable():
            sel = self.completion_listbox.curselection()
            if sel:
                idx = sel[0]
                if idx < len(self.completion_words) - 1:
                    self.completion_listbox.selection_clear(idx)
                    self.completion_listbox.selection_set(idx + 1)
                    self.completion_listbox.see(idx + 1)
            return "break"
        return None

    def on_completion_up(self, event):
        if self.completion_popup and self.completion_popup.winfo_viewable():
            sel = self.completion_listbox.curselection()
            if sel:
                idx = sel[0]
                if idx > 0:
                    self.completion_listbox.selection_clear(idx)
                    self.completion_listbox.selection_set(idx - 1)
                    self.completion_listbox.see(idx - 1)
            return "break"
        return None

    def on_completion_enter(self, event):
        if self.completion_popup and self.completion_popup.winfo_viewable():
            sel = self.completion_listbox.curselection()
            if sel:
                self.insert_completion(self.completion_words[sel[0]])
            return "break"
        return None

    def on_completion_click(self, event):
        sel = self.completion_listbox.curselection()
        if sel:
            self.insert_completion(self.completion_words[sel[0]])

    def insert_completion(self, word):
        prefix = self.get_current_word()
        if prefix:
            # 删除已输入的前缀
            line, col = self.editor.index(tk.INSERT).split(".")
            col = int(col)
            line = int(line)
            start = f"{line}.{col - len(prefix)}"
            self.editor.delete(start, tk.INSERT)
        self.editor.insert(tk.INSERT, word)
        self.hide_completion()
        self.apply_highlight()

    def on_tab(self, event):
        # Tab 键弹出补全
        self.show_completion()
        return "break"

    # ========================================================================
    # 输出
    # ========================================================================

    def write_output(self, text, tag=None):
        self.output.config(state=tk.NORMAL)
        if tag:
            self.output.insert(tk.END, text, tag)
        else:
            self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.config(state=tk.DISABLED)

    def clear_output(self):
        self.output.config(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.config(state=tk.DISABLED)

    # ========================================================================
    # P2: 运行 / 停止
    # ========================================================================

    def run_code(self):
        if self.running:
            return
        code = self.editor.get("1.0", "end-1c")
        if not code.strip():
            return

        self.clear_output()
        self.write_output(f"── 运行 {self.current_file or '<未保存>'} ──\n", "info")

        # 清除错误行高亮
        self.editor.tag_remove("error_line", "1.0", tk.END)

        self.running = True
        self.stop_event.clear()
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        threading.Thread(target=self._run_in_thread,
                         args=(code,), daemon=True).start()

    def stop_code(self):
        self.stop_event.set()

    def _run_in_thread(self, code):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured = io.StringIO()
        sys.stdout = captured
        sys.stderr = captured

        error_info = None
        try:
            tokens = split_token(code)
            parser = Parser(tokens)
            program = parser.parse()

            checker = Checker()
            checker.check(program)

            interp = Interpreter()

            # 注入 stop_event 检查
            original_exec_statement = interp.exec_statement
            stop_event = self.stop_event

            def checked_exec_statement(stmt, scope, labels, pc):
                if stop_event.is_set():
                    raise EclException('InterruptError', '用户中断执行')
                return original_exec_statement(stmt, scope, labels, pc)

            interp.exec_statement = checked_exec_statement
            interp.interpret(program)

        except LexerError as e:
            error_info = (f"词法错误: {e}", e.line, e.col)
        except ParseError as e:
            error_info = (f"语法错误: {e}", e.line, e.col)
        except CheckError as e:
            error_info = (f"检查错误: {e}", e.line, e.col)
        except EclException as e:
            if self.stop_event.is_set():
                error_info = ("已停止执行", 0, 0)
            else:
                error_info = (f"运行时错误: {e}", e.line, e.col)
        except Exception as e:
            error_info = (f"内部错误: {type(e).__name__}: {e}", 0, 0)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        out = captured.getvalue()
        self.root.after(0, lambda: self._finish_run(out, error_info))

    def _finish_run(self, out, error_info):
        if out:
            self.write_output(out)

        if error_info:
            msg, line, col = error_info
            self.write_output(msg + "\n", "error")
            if line > 0:
                start = f"{line}.0"
                end = f"{line}.end"
                self.editor.tag_add("error_line", start, end)
                self.editor.see(start)
                self.editor.mark_set(tk.INSERT, f"{line}.{max(col - 1, 0)}")
                self.editor.focus_set()
            self.write_output("── 执行失败 ──\n", "error")
        else:
            self.write_output("── 执行完成 ──\n", "ok")

        self.running = False
        self.run_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    # ========================================================================
    # 文件
    # ========================================================================

    def save_file(self):
        if not self.current_file:
            path = filedialog.asksaveasfilename(
                defaultextension=".ecl",
                filetypes=[("ECL 文件", "*.ecl"), ("所有文件", "*.*")])
            if not path:
                return
            self.current_file = path
        with open(self.current_file, "w", encoding="utf-8") as f:
            f.write(self.editor.get("1.0", "end-1c"))
        self.root.title(f"ECL IDE - {self.current_file}")

    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("ECL 文件", "*.ecl"), ("所有文件", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", code)
        self.current_file = path
        self.root.title(f"ECL IDE - {path}")
        self.update_line_numbers()
        self.apply_highlight()


if __name__ == "__main__":
    root = tk.Tk()
    ide = EclIDE(root)
    root.mainloop()
