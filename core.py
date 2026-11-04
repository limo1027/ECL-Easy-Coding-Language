#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECL (Easy Control Language) 解释器完整实现
包含：词法分析、语法解析、类型检查、解释执行
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Union
import sys

_NO_MAGIC = object()


class NullValue:
    """ECL 的 null：表示没有实现 / 没有指向"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "null"

    def __bool__(self):
        return False


NULL = NullValue()
# ============================================================================
# 词法分析
# ============================================================================


class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type_, value, line, col):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, {self.line}, {self.col})"


class LexerError(Exception):
    def __init__(self, message, line, col):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"[行 {line}, 列 {col}] {message}")


KEYWORDS = {
    'def', 'end', 'if', 'elif', 'else', 'for', 'while', 'continue',
    'break', 'return', 'class', 'import', 'from', 'as', 'try', 'except',
    'finally', 'raise', 'global', 'last', 'using', 'ref', 'define',
    'with', 'match', 'case', 'goto', 'label', 'public', 'private',
    'const', 'True', 'False', 'null', 'none', 'any', 'in', 'and', 'or', 'not',
}

OPERATORS = [
    '**=', '//=', '..=', '+=', '-=', '*=', '/=', '%=', '<->',
    '**', '//', '..', '==', '!=', '<=', '>=', '->', '<-', '<<', '>>',
    '+', '-', '*', '/', '%', '=', '<', '>', '!', '|', '&', '^', '~',
    '(', ')', '[', ']', '{', '}', '.', ',', ':', ';', '@',
]

BUILTIN_TYPES = {
    'int', 'str', 'float', 'double', 'bool', 'boolean',
    'list', 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any', 'none',
}

MAGIC_METHODS = {
    '+': '__add__', '-': '__sub__', '*': '__mul__',
    '/': '__div__', '//': '__floordiv__', '%': '__mod__',
    '**': '__pow__', '<': '__lt__', '>': '__gt__',
    '<=': '__le__', '>=': '__ge__', '=': '__eq__',
    '==': '__eq__', '!=': '__ne__', '|': '__bor__',
    '&': '__band__', '^': '__xor__', '<<': '__lshift__',
    '>>': '__rshift__',
}

REVERSE_METHODS = {
    '+': '__radd__', '-': '__rsub__', '*': '__rmul__',
    '/': '__rdiv__', '//': '__rfloordiv__', '%': '__rmod__',
    '**': '__rpow__', '<': '__gt__', '>': '__lt__',
    '<=': '__ge__', '>=': '__le__', '=': '__eq__',
    '==': '__eq__', '!=': '__ne__', '|': '__ror__',
    '&': '__rand__', '^': '__rxor__', '<<': '__rlshift__',
    '>>': '__rrshift__',
}


def split_token(code):
    """将源码切分为 Token 列表"""
    tokens = []
    i = 0
    n = len(code)
    line = 1
    col = 1

    def current():
        return code[i] if i < n else ''

    def peek(offset=1):
        pos = i + offset
        return code[pos] if pos < n else ''

    def advance():
        nonlocal i, col
        i += 1
        col += 1

    def advance_line():
        nonlocal i, col, line
        while i < n and code[i] != '\n':
            i += 1
            col += 1
        if i < n:
            i += 1
        line += 1
        col = 1

    def read_string(quote):
        start_line, start_col = line, col
        advance()
        segments = []          # [(kind, content, line, col), ...]
        buf = []
        seg_line, seg_col = line, col

        def flush_buf():
            nonlocal buf, seg_line, seg_col
            if buf:
                segments.append(('str', ''.join(buf), seg_line, seg_col))
                buf = []
                seg_line, seg_col = line, col

        while i < n:
            ch = current()

            # 反斜杠转义（保留原有：\n \t \r \\ \" \' \0）
            if ch == '\\':
                advance()
                if i >= n:
                    raise LexerError("反斜杠后缺少转义字符", line, col)
                esc = current()
                mapping = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\',
                           '"': '"', "'": "'", '0': '\0'}
                buf.append(mapping.get(esc, '\\' + esc))
                advance()

            # $$ 转义，输出字面 $
            elif ch == '$' and peek() == '$':
                buf.append('$')
                advance()   # 跳过第一个 $
                advance()   # 跳过第二个 $

            # $name 变量插值
            elif ch == '$' and (peek().isalpha() or peek() == '_'):
                flush_buf()
                advance()   # 跳过 $
                name_start = i
                name_line, name_col = line, col
                while i < n and (current().isalnum() or current() == '_'):
                    advance()
                segments.append(
                    ('var', code[name_start:i], name_line, name_col))
                seg_line, seg_col = line, col

            # ${expr} 表达式插值
            elif ch == '$' and peek() == '{':
                flush_buf()
                advance()
                advance()
                expr_line, expr_col = line, col
                depth = 1
                expr_buf = []
                while i < n and depth > 0:
                    c = current()
                    if c == '\\':
                        advance()
                        if i < n:
                            esc = current()
                            mapping = {'n': '\n', 't': '\t', 'r': '\r',
                                       '\\': '\\', '"': '"', "'": "'", '0': '\0'}
                            expr_buf.append(mapping.get(esc, '\\' + esc))
                            advance()
                    elif c == '{':
                        depth += 1
                        expr_buf.append(c)
                        advance()
                    elif c == '}':
                        depth -= 1
                        if depth > 0:
                            expr_buf.append(c)
                        advance()
                    elif c == '\n':
                        expr_buf.append('\n')
                        advance_line()
                    else:
                        expr_buf.append(c)
                        advance()
                if depth != 0:
                    raise LexerError("${...} 未闭合", expr_line, expr_col)
                segments.append(
                    ('expr', ''.join(expr_buf), expr_line, expr_col))

            elif ch == quote:
                advance()
                flush_buf()
                return segments, start_line, start_col

            elif ch == '\n':
                raise LexerError("字符串未闭合（遇到换行）", start_line, start_col)

            else:
                buf.append(ch)
                advance()

        raise LexerError("字符串未闭合", start_line, start_col)

    def read_code_string():
        start_line, start_col = line, col
        advance()  # 跳过 `
        value = []
        while i < n:
            ch = current()
            if ch == '`':
                advance()
                return ''.join(value), start_line, start_col
            if ch == '\n':
                value.append('\n')
                advance_line()
            else:
                value.append(ch)
                advance()
        raise LexerError("代码字符串未闭合", start_line, start_col)

    def read_number():
        start_i = i
        start_line, start_col = line, col
        is_float = False
        is_double = False

        if current() == '0' and peek() in ('b', 'B', 'o', 'O', 'x', 'X'):
            base_ch = peek().lower()
            advance()
            advance()
            valid = {'b': '01_', 'o': '01234567_',
                     'x': '0123456789abcdefABCDEF_'}[base_ch]
            while i < n and current() in valid:
                advance()
            raw = code[start_i:i].replace('_', '')
            base = {'b': 2, 'o': 8, 'x': 16}[base_ch]
            try:
                return ('INT', int(raw[2:], base), start_line, start_col)
            except ValueError:
                raise LexerError(f"无效数字: {raw}", start_line, start_col)

        while i < n:
            ch = current()
            if ch.isdigit() or ch == '_':
                advance()
            elif ch == '.' and not is_float and peek().isdigit():
                is_float = True
                advance()
            elif ch in 'eE' and not is_float:
                is_float = True
                advance()
                if current() in '+-':
                    advance()
            elif ch in 'dD' and not is_double:
                is_double = True
                advance()
                break
            else:
                break

        raw = code[start_i:i].replace('_', '')
        try:
            if is_double:
                return ('DOUBLE', float(raw.rstrip('dD')), start_line, start_col)
            elif is_float:
                return ('FLOAT', float(raw), start_line, start_col)
            else:
                return ('INT', int(raw), start_line, start_col)
        except ValueError:
            raise LexerError(f"无效数字: {raw}", start_line, start_col)

    def read_identifier():
        start_i = i
        start_line, start_col = line, col
        while i < n and (current().isalnum() or current() == '_'):
            advance()
        value = code[start_i:i]
        if value in KEYWORDS:
            return ('KEYWORD', value, start_line, start_col)
        return ('IDENTIFIER', value, start_line, start_col)

    while i < n:
        ch = current()

        if ch in ' \t\r':
            advance()
            continue
        if ch == '\n':
            advance_line()
            continue

        if ch == ";":
            tokens.append(Token('SYMBOL', ";", line, col))
        # 注释
        if ch == '#':
            while i < n and current() != '\n':
                advance()
            continue
        if ch == '/' and peek() == '/' and peek(2) == '/':
            while i < n and current() != '\n':
                advance()
            continue
        if ch == '/' and peek() == '*':
            start_line, start_col = line, col
            advance()
            advance()
            closed = False
            while i < n:
                if current() == '*' and peek() == '/':
                    advance()
                    advance()
                    closed = True
                    break
                if current() == '\n':
                    advance_line()
                else:
                    advance()
            if not closed:
                raise LexerError("块注释未闭合", start_line, start_col)
            continue

        if ch in '"\'"':
            segments, sl, sc = read_string(ch)
            if len(segments) == 1 and segments[0][0] == 'str':
                tokens.append(Token('STRING', segments[0][1], sl, sc))
            else:
                tokens.append(Token('INTERP_STRING', segments, sl, sc))
            continue

        if ch.isdigit() or (ch == '.' and peek().isdigit()):
            typ, value, sl, sc = read_number()
            tokens.append(Token(typ, value, sl, sc))
            continue

        if ch.isalpha() or ch == '_':
            typ, value, sl, sc = read_identifier()
            tokens.append(Token(typ, value, sl, sc))
            continue

        if ch == '`':
            value, sl, sc = read_code_string()
            tokens.append(Token('CODE_STRING', value, sl, sc))
            continue
        matched = False
        for op in OPERATORS:
            if code[i:i + len(op)] == op:
                tokens.append(Token('SYMBOL', op, line, col))
                for _ in range(len(op)):
                    advance()
                matched = True
                break
        if matched:
            continue

        raise LexerError(f"未知字符: {ch!r}", line, col)

    tokens.append(Token('EOF', 'EOF', line, col))
    return tokens


# ============================================================================
# AST 节点 —— 全部携带 line/col
# ============================================================================

# ============================================================================
# AST 节点 —— 全部携带 line/col（放在字段最后，避免 dataclass 默认值顺序问题）
# ============================================================================

class Node:
    """AST 节点标记基类（不定义 dataclass 字段，避免继承默认值顺序问题）"""
    line: int
    col: int


class Expr(Node):
    pass


class Stmt(Node):
    pass


# ---------- 表达式 ----------

@dataclass
class Literal(Expr):
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class Variable(Expr):
    name: str
    line: int = 0
    col: int = 0


@dataclass
class Binary(Expr):
    left: Expr
    op: str
    right: Expr
    line: int = 0
    col: int = 0


@dataclass
class Unary(Expr):
    op: str
    right: Expr
    line: int = 0
    col: int = 0


@dataclass
class Assign(Expr):
    name: Any          # str 或 Variable 或 Attribute（这里存 Variable/Attribute 节点）
    value: Expr
    is_ref: bool = False
    line: int = 0
    col: int = 0


@dataclass
class Swap(Expr):
    left: str
    right: str
    line: int = 0
    col: int = 0


@dataclass
class Call(Expr):
    func: Expr
    args: List[Expr]
    kwargs: List[tuple]
    line: int = 0
    col: int = 0


@dataclass
class Attribute(Expr):
    obj: Expr
    attr: str
    line: int = 0
    col: int = 0


@dataclass
class IfExpr(Expr):
    condition: Expr
    then_expr: Expr
    else_expr: Expr
    line: int = 0
    col: int = 0


@dataclass
class ListExpr(Expr):
    elements: List[Expr]
    fixed_length: Optional[int] = None
    line: int = 0
    col: int = 0


@dataclass
class DictExpr(Expr):
    items: List[tuple]
    line: int = 0
    col: int = 0


@dataclass
class Subscript(Expr):
    obj: Expr
    index: Expr
    line: int = 0
    col: int = 0


@dataclass
class RangeExpr(Expr):
    start: Expr
    end: Expr
    step: Optional[Expr] = None
    inclusive: bool = False
    line: int = 0
    col: int = 0


@dataclass
class CodeLiteral(Expr):
    source: str
    line: int = 0
    col: int = 0
# ---------- 语句 ----------


@dataclass
class ExprStmt(Stmt):
    expr: Expr
    line: int = 0
    col: int = 0


@dataclass
class DefineStmt(Stmt):
    name: str
    type_name: Optional[str]
    value: Optional[Expr]
    is_ref: bool = False
    is_const: bool = False
    line: int = 0
    col: int = 0


@dataclass
class FuncDefStmt(Stmt):
    name: str
    params: List[dict]
    varargs: Optional[str]
    varargs_type: Optional[str]
    kwargs: Optional[str]
    kwargs_type: Optional[str]
    defaults: dict
    body: List[Stmt]
    is_single_line: bool
    return_type: Optional[str] = None
    line: int = 0
    col: int = 0


@dataclass
class ClassDefStmt(Stmt):
    name: str
    bases: List[str]
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class IfStmt(Stmt):
    condition: Expr
    body: List[Stmt]
    elifs: List[tuple]
    else_body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class ForStmt(Stmt):
    variable: Optional[str]
    iterable: Optional[Expr]
    range_expr: Optional[RangeExpr]
    count: Optional[Expr]
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class ReturnStmt(Stmt):
    value: Optional[Expr]
    line: int = 0
    col: int = 0


@dataclass
class BreakStmt(Stmt):
    line: int = 0
    col: int = 0


@dataclass
class ContinueStmt(Stmt):
    line: int = 0
    col: int = 0


@dataclass
class GotoStmt(Stmt):
    label: str
    line: int = 0
    col: int = 0


@dataclass
class LabelStmt(Stmt):
    name: str
    line: int = 0
    col: int = 0


@dataclass
class ImportStmt(Stmt):
    module: str
    alias: Optional[str]
    names: List[tuple]
    line: int = 0
    col: int = 0


@dataclass
class TryStmt(Stmt):
    body: List[Stmt]
    excepts: List[dict]
    else_body: Optional[List[Stmt]]
    finally_body: Optional[List[Stmt]]
    line: int = 0
    col: int = 0


@dataclass
class RaiseStmt(Stmt):
    exception: Expr
    line: int = 0
    col: int = 0


@dataclass
class WithStmt(Stmt):
    items: List[tuple]
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class MatchStmt(Stmt):
    value: Expr
    cases: List[dict]
    line: int = 0
    col: int = 0


@dataclass
class UsingStmt(Stmt):
    name: str
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class DecoratorStmt(Stmt):
    target: str
    name: Optional[str]
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class Program:
    body: List[Stmt]


# ============================================================================
# 代码块工具
# ============================================================================

class GlobalView:
    """code 对象执行后返回的全局视图"""

    def __init__(self, cells, interpreter):
        self.cells = cells          # dict[str, Cell]
        self.interpreter = interpreter

    def get(self, name):
        if name in self.cells:
            return self.cells[name].value
        return None

    def set(self, name, value):
        if name in self.cells:
            self.cells[name].value = value
        else:
            self.cells[name] = Cell(value)

    def keys(self):
        return list(self.cells.keys())

    def __repr__(self):
        return f"<global {list(self.cells.keys())}>"


class CodeObject:
    """code 类型的值：延迟解析的代码块"""

    def __init__(self, source, scope, interpreter, line=0, col=0):
        self.source = source
        self.scope = scope
        self.interpreter = interpreter
        self.line = line
        self.col = col
        self._stmts = None

    def _parse(self):
        if self._stmts is not None:
            return self._stmts
        try:
            tokens = split_token(self.source)
            parser = Parser(tokens)
            program = parser.parse()
        except (LexerError, ParseError) as e:
            self.interpreter.error(
                f"code 对象解析失败: {e}", self, 'SyntaxError')
        self._stmts = program.body
        return self._stmts

    def run(self):
        stmts = self._parse()
        code_globals = {}
        parent_scope = dict(self.scope)
        for k, v in parent_scope.items():
            code_globals[k] = v
        for k, v in self.interpreter.globals.items():
            if k not in code_globals:
                code_globals[k] = v

        compiler = Compiler()
        code, exception_table = compiler.compile_program(Program(stmts))
        vm = VM(code, exception_table, code_globals, self.interpreter)
        vm.run()

        new_cells = {k: v for k, v in code_globals.items()
                     if k not in parent_scope and k not in self.interpreter.globals}
        return GlobalView(new_cells, self.interpreter)

    def __repr__(self):
        return f"<code object at {self.line}:{self.col}>"

# ============================================================================
# 语法分析
# ============================================================================


class ParseError(Exception):
    def __init__(self, message, line, col):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"[行 {line}, 列 {col}] {message}")


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.n = len(tokens)

    # ---------- 基础工具 ----------

    def current(self):
        return self.tokens[self.pos] if self.pos < self.n else None

    def peek(self, offset=1):
        idx = self.pos + offset
        return self.tokens[idx] if idx < self.n else None

    def advance(self):
        tok = self.current()
        self.pos += 1
        return tok

    def error(self, msg, tok=None):
        if tok is None:
            tok = self.current()
        if tok is not None:
            raise ParseError(msg, tok.line, tok.col)
        last = self.tokens[-1] if self.tokens else None
        if last:
            raise ParseError(msg, last.line, last.col)
        raise ParseError(msg, 0, 0)

    def expect(self, type_, value=None):
        tok = self.current()
        if not tok or tok.type != type_ or (value is not None and tok.value != value):
            expected = f"'{value}'" if value is not None else f"类型 {type_}"
            actual = f"'{tok.value}'" if tok else "文件末尾"
            self.error(f"期望 {expected}，但得到 {actual}", tok)
        return self.advance()

    def match(self, type_, value=None):
        tok = self.current()
        return bool(tok and tok.type == type_ and (value is None or tok.value == value))

    def match_value(self, value):
        tok = self.current()
        return bool(tok and tok.value == value)

    # ---------- 入口 ----------

    def parse(self):
        stmts = []
        while not self.match('EOF'):
            # 跳过开头的分号
            while self.match('SYMBOL', ';'):
                self.advance()
            if self.match('EOF'):
                break
            stmt = self.parse_statement()
            if stmt is not None:
                stmts.append(stmt)
            # 跳过语句后的分号（一个或多个）
            while self.match('SYMBOL', ';'):
                self.advance()
        return Program(stmts)

    # ---------- 语句 ----------

    def parse_statement(self):
        tok = self.current()
        if tok is None or self.match('EOF'):
            return None
        if tok.type == 'KEYWORD' and tok.value == 'end':
            return None

        # 类型声明（int x <- 1 / list[5] int m <- [...]）
        if tok.value in BUILTIN_TYPES and tok.type in ('KEYWORD', 'IDENTIFIER', 'TYPE'):
            return self.parse_typed_define()

        # 用户自定义类型声明：ClassName varName <- ...
        # 形如：Point p <- Point(3, 4)
        if (tok.type == 'IDENTIFIER'
                and self.peek()
                and self.peek().type == 'IDENTIFIER'
                and self.peek(2)
                and self.peek(2).type == 'SYMBOL'
                and self.peek(2).value == '<-'):
            return self.parse_user_typed_define()

        # 关键字语句
        if tok.type == 'KEYWORD':
            kw = tok.value
            if kw == 'global':
                # 判断是 global g <- expr 还是 global.x <- expr
                nxt = self.peek()
                if nxt and nxt.type == 'IDENTIFIER' and self.peek(2) and self.peek(2).value == '<-':
                    # global g <- expr：变量声明
                    self.advance()  # 跳过 global
                    name = self.expect('IDENTIFIER')
                    self.expect('SYMBOL', '<-')
                    value = self.parse_expr()
                    return DefineStmt(name.value, 'global', value,
                                      is_ref=False, is_const=False,
                                      line=tok.line, col=tok.col)
                else:
                    # global.x <- expr 或 global.x：作用域限定，作为表达式处理
                    return self.parse_expression_statement()
            if kw == 'if':
                return self.parse_if()
            if kw == 'for':
                return self.parse_for()
            if kw == 'while':
                return self.parse_while()
            if kw == 'def':
                return self.parse_function()
            if kw == 'class':
                return self.parse_class()
            if kw == 'return':
                return self.parse_return()
            if kw == 'break':
                self.advance()
                return BreakStmt(line=tok.line, col=tok.col)
            if kw == 'continue':
                self.advance()
                return ContinueStmt(line=tok.line, col=tok.col)
            if kw == 'goto':
                self.advance()
                label = self.expect('IDENTIFIER')
                return GotoStmt(label.value, line=tok.line, col=tok.col)
            if kw == 'label':
                self.advance()
                name = self.expect('IDENTIFIER')
                self.expect('SYMBOL', ':')
                return LabelStmt(name.value, line=tok.line, col=tok.col)
            if kw == 'import':
                return self.parse_import()
            if kw == 'from':
                return self.parse_from()
            if kw == 'try':
                return self.parse_try()
            if kw == 'raise':
                self.advance()
                exc = self.parse_expr()
                return RaiseStmt(exc, line=tok.line, col=tok.col)
            if kw == 'with':
                return self.parse_with()
            if kw == 'match':
                return self.parse_match()
            if kw == 'using':
                return self.parse_using()
            if kw == 'ref':
                return self.parse_ref()
            if kw == 'define':
                return self.parse_define()
            if kw == 'const':
                return self.parse_const()

        # 单行函数检测: f(x) -> int <- ...
        if tok.type == 'IDENTIFIER' and self.peek() and self.peek().value == '(':
            result = self.try_parse_single_line_function()
            if result is not None:
                return result

        # 装饰器
        if tok.type == 'SYMBOL' and tok.value == '@':
            return self.parse_decorator()

        # 表达式语句
        return self.parse_expression_statement()

    def parse_user_typed_define(self):
        """解析用户自定义类型声明：ClassName varName <- expr"""
        start = self.current()
        type_name = self.advance().value          # 类名
        name = self.expect('IDENTIFIER')          # 变量名
        self.expect('SYMBOL', '<-')
        value = self.parse_expr()
        return DefineStmt(name.value, type_name, value,
                          is_ref=False, is_const=False,
                          line=start.line, col=start.col)

    def parse_typed_define(self):
        start = self.current()
        base_type = self.advance().value
        type_params = []
        if self.match('SYMBOL', '['):
            self.advance()
            if self.match('INT') or self.match('IDENTIFIER') or self.match('TYPE'):
                type_params.append(self.advance().value)
            else:
                type_params.append(self.parse_expr())
            self.expect('SYMBOL', ']')

        elem_type = None
        nxt = self.current()
        if nxt and (nxt.type in ('IDENTIFIER', 'TYPE') and nxt.value in BUILTIN_TYPES):
            elem_type = self.advance().value

        name = self.expect('IDENTIFIER')

        value = None
        if self.match('SYMBOL', '<-'):
            self.advance()
            value = self.parse_expr()

        full_type = base_type
        for p in type_params:
            full_type += f'[{p}]'
        if elem_type:
            full_type += ' ' + elem_type

        return DefineStmt(name.value, full_type, value,
                          is_ref=False, is_const=False,
                          line=start.line, col=start.col)

    def parse_ref(self):
        start = self.current()
        self.expect('KEYWORD', 'ref')
        name = self.expect('IDENTIFIER')
        self.expect('SYMBOL', '<-')
        value = self.parse_expr()
        return DefineStmt(name.value, None, value, is_ref=True, is_const=False,
                          line=start.line, col=start.col)

    def parse_define(self):
        start = self.current()
        self.expect('KEYWORD', 'define')
        type_name = None
        nxt = self.current()
        if nxt and nxt.type in ('IDENTIFIER', 'TYPE') and nxt.value in BUILTIN_TYPES:
            type_name = self.advance().value
        name = self.expect('IDENTIFIER')
        value = None
        if self.match('SYMBOL', '<-'):
            self.advance()
            value = self.parse_expr()
        return DefineStmt(name.value, type_name, value,
                          is_ref=False, is_const=False,
                          line=start.line, col=start.col)

    def parse_const(self):
        start = self.current()
        self.expect('KEYWORD', 'const')
        type_name = None
        nxt = self.current()
        if nxt and nxt.type in ('IDENTIFIER', 'TYPE') and nxt.value in BUILTIN_TYPES:
            type_name = self.advance().value
        name = self.expect('IDENTIFIER')
        value = None
        if self.match('SYMBOL', '<-'):
            self.advance()
            value = self.parse_expr()
        return DefineStmt(name.value, type_name, value,
                          is_ref=False, is_const=True,
                          line=start.line, col=start.col)

    def parse_return(self):
        tok = self.current()
        self.advance()
        if self.match('SYMBOL', ':') or self.match('EOF') or self.match('KEYWORD', 'end'):
            return ReturnStmt(None, line=tok.line, col=tok.col)
        val = self.parse_expr()
        return ReturnStmt(val, line=tok.line, col=tok.col)

    def parse_expression_statement(self):
        expr = self.parse_expr()
        return ExprStmt(expr, line=expr.line, col=expr.col)

    # ---------- 函数 ----------

    def try_parse_single_line_function(self):
        """尝试解析单行函数 f(int x) -> int <- expr，失败则回退"""
        saved = self.pos
        try:
            name_tok = self.advance()
            name = name_tok.value
            self.expect('SYMBOL', '(')
            params = []
            while not self.match('SYMBOL', ')'):
                ptype = None
                nxt = self.current()
                # 参数可以带类型: int x
                if nxt and nxt.type in ('IDENTIFIER', 'TYPE') and nxt.value in BUILTIN_TYPES:
                    ptype = self.advance().value
                pname_tok = self.expect('IDENTIFIER')
                params.append({'name': pname_tok.value,
                              'type': ptype, 'default': None})
                if self.match('SYMBOL', ','):
                    self.advance()
                else:
                    break
            self.expect('SYMBOL', ')')

            return_type = None
            if self.match('SYMBOL', '->'):
                self.advance()
                rt = self.current()
                if rt and rt.type in ('IDENTIFIER', 'TYPE', 'KEYWORD'):
                    return_type = self.advance().value
                else:
                    self.error("期望返回值类型", rt)

            if not self.match('SYMBOL', '<-'):
                self.pos = saved
                return None
            self.advance()

            body_expr = self.parse_expr()
            # ★ 关键修复：单行函数体是返回值，不是普通表达式语句
            body_stmt = ReturnStmt(
                body_expr, line=body_expr.line, col=body_expr.col)

            return FuncDefStmt(
                name=name,
                params=params,
                varargs=None,
                varargs_type=None,
                kwargs=None,
                kwargs_type=None,
                defaults={},
                body=[body_stmt],
                is_single_line=True,
                return_type=return_type,
                line=name_tok.line,
                col=name_tok.col,
            )
        except (ParseError, LexerError):
            self.pos = saved
            return None

    def parse_function(self):
        start = self.current()
        self.expect('KEYWORD', 'def')
        name = self.expect('IDENTIFIER')
        self.expect('SYMBOL', '(')

        params = []
        varargs = None
        varargs_type = None
        kwargs = None
        kwargs_type = None
        defaults = {}

        while not self.match('SYMBOL', ')'):
            if self.match('SYMBOL', '**'):
                self.advance()
                kwargs = self.expect('IDENTIFIER').value
                if self.match('SYMBOL', ','):
                    self.advance()
                continue

            if self.match('SYMBOL', '*'):
                self.advance()
                varargs = self.expect('IDENTIFIER').value
                if self.match('SYMBOL', ','):
                    self.advance()
                continue

            ptype = None
            nxt = self.current()
            if nxt and nxt.type in ('IDENTIFIER', 'TYPE') and nxt.value in BUILTIN_TYPES:
                ptype = self.advance().value

            pname = self.expect('IDENTIFIER').value

            default = None
            if self.match('SYMBOL', '='):
                self.advance()
                default = self.parse_expr()
                defaults[pname] = default

            params.append({'name': pname, 'type': ptype, 'default': default})

            if self.match('SYMBOL', ','):
                self.advance()
            elif not self.match('SYMBOL', ')'):
                self.error("期望 ',' 或 ')'", self.current())

        self.expect('SYMBOL', ')')

        # 返回值类型
        return_type = None
        if self.match('SYMBOL', '->'):
            self.advance()
            rt = self.current()
            if rt and rt.type in ('IDENTIFIER', 'TYPE', 'KEYWORD'):
                return_type = self.advance().value
            else:
                self.error("期望返回值类型", rt)

        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end') and not self.match('EOF'):
            stmt = self.parse_statement()
            if stmt is not None:
                body.append(stmt)
        self.expect('KEYWORD', 'end')

        return FuncDefStmt(
            name=name.value,
            params=params,
            varargs=varargs,
            varargs_type=varargs_type,
            kwargs=kwargs,
            kwargs_type=kwargs_type,
            defaults=defaults,
            body=body,
            is_single_line=False,
            return_type=return_type,
            line=start.line,
            col=start.col,
        )

    def parse_class(self):
        start = self.current()
        self.expect('KEYWORD', 'class')
        name = self.expect('IDENTIFIER')
        bases = []
        if self.match('SYMBOL', '('):
            self.advance()
            while not self.match('SYMBOL', ')'):
                bases.append(self.expect('IDENTIFIER').value)
                if self.match('SYMBOL', ','):
                    self.advance()
            self.expect('SYMBOL', ')')
        self.expect('SYMBOL', ':')
        body = []
        while not self.match('KEYWORD', 'end') and not self.match('EOF'):
            stmt = self.parse_statement()
            if stmt is not None:
                body.append(stmt)
        self.expect('KEYWORD', 'end')
        return ClassDefStmt(name.value, bases, body,
                            line=start.line, col=start.col)

    def parse_if(self):
        start = self.current()
        self.expect('KEYWORD', 'if')
        cond = self.parse_expr()
        self.expect('SYMBOL', ':')
        body = []
        while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'elif') \
                and not self.match('KEYWORD', 'else') and not self.match('EOF'):
            s = self.parse_statement()
            if s is not None:
                body.append(s)

        elifs = []
        while self.match('KEYWORD', 'elif'):
            self.advance()
            ec = self.parse_expr()
            self.expect('SYMBOL', ':')
            eb = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'elif') \
                    and not self.match('KEYWORD', 'else') and not self.match('EOF'):
                s = self.parse_statement()
                if s is not None:
                    eb.append(s)
            elifs.append((ec, eb))

        else_body = []
        if self.match('KEYWORD', 'else'):
            self.advance()
            self.expect('SYMBOL', ':')
            while not self.match('KEYWORD', 'end') and not self.match('EOF'):
                s = self.parse_statement()
                if s is not None:
                    else_body.append(s)

        self.expect('KEYWORD', 'end')
        return IfStmt(cond, body, elifs, else_body,
                      line=start.line, col=start.col)

    def parse_for(self):
        start = self.current()
        self.expect('KEYWORD', 'for')

        variable = None
        iterable = None
        range_expr = None
        count = None

        if self.match('INT'):
            count = self.parse_expr()
        else:
            variable = self.expect('IDENTIFIER').value
            self.expect('KEYWORD', 'in')
            # 判断是否为 range 写法
            if self.match('INT') and (self.peek() and self.peek().value in ('..', '..=')):
                range_expr = self.parse_range()
            else:
                iterable = self.parse_expr()

        self.expect('SYMBOL', ':')
        body = []
        while not self.match('KEYWORD', 'end') and not self.match('EOF'):
            s = self.parse_statement()
            if s is not None:
                body.append(s)
        self.expect('KEYWORD', 'end')
        return ForStmt(variable, iterable, range_expr, count, body,
                       line=start.line, col=start.col)

    def parse_range(self):
        start = self.current()
        left = self.parse_expr()
        inclusive = False
        if self.match('SYMBOL', '..='):
            self.advance()
            inclusive = True
        elif self.match('SYMBOL', '..'):
            self.advance()
        else:
            self.error("期望 '..' 或 '..='", self.current())
        right = self.parse_expr()
        step = None
        if self.match('SYMBOL', '+'):
            self.advance()
            step = self.parse_expr()
        return RangeExpr(left, right, step, inclusive,
                         line=start.line, col=start.col)

    def parse_while(self):
        start = self.current()
        self.expect('KEYWORD', 'while')
        cond = self.parse_expr()
        self.expect('SYMBOL', ':')
        body = []
        while not self.match('KEYWORD', 'end') and not self.match('EOF'):
            s = self.parse_statement()
            if s is not None:
                body.append(s)
        self.expect('KEYWORD', 'end')
        return WhileStmt(cond, body, line=start.line, col=start.col)

    def parse_import(self):
        start = self.current()
        self.expect('KEYWORD', 'import')
        module = self.expect('IDENTIFIER').value
        alias = None
        if self.match('KEYWORD', 'as'):
            self.advance()
            alias = self.expect('IDENTIFIER').value
        return ImportStmt(module, alias, [], line=start.line, col=start.col)

    def parse_from(self):
        start = self.current()
        self.expect('KEYWORD', 'from')
        module = self.expect('IDENTIFIER').value
        self.expect('KEYWORD', 'import')
        names = []
        while True:
            name = self.expect('IDENTIFIER').value
            alias = None
            if self.match('KEYWORD', 'as'):
                self.advance()
                alias = self.expect('IDENTIFIER').value
            names.append((name, alias))
            if not self.match('SYMBOL', ','):
                break
            self.advance()
        return ImportStmt(module, None, names, line=start.line, col=start.col)

    def parse_try(self):
        start = self.current()
        self.expect('KEYWORD', 'try')
        self.expect('SYMBOL', ':')
        body = []
        while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'except') \
                and not self.match('KEYWORD', 'else') and not self.match('KEYWORD', 'finally') \
                and not self.match('EOF'):
            s = self.parse_statement()
            if s is not None:
                body.append(s)

        excepts = []
        while self.match('KEYWORD', 'except'):
            self.advance()
            exc_type = None
            exc_name = None
            if self.match('IDENTIFIER'):
                exc_type = self.advance().value
                if self.match('KEYWORD', 'as'):
                    self.advance()
                    exc_name = self.expect('IDENTIFIER').value
            self.expect('SYMBOL', ':')
            eb = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'except') \
                    and not self.match('KEYWORD', 'else') and not self.match('KEYWORD', 'finally') \
                    and not self.match('EOF'):
                s = self.parse_statement()
                if s is not None:
                    eb.append(s)
            excepts.append({'type': exc_type, 'name': exc_name, 'body': eb})

        else_body = None
        if self.match('KEYWORD', 'else'):
            self.advance()
            self.expect('SYMBOL', ':')
            else_body = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'finally') \
                    and not self.match('EOF'):
                s = self.parse_statement()
                if s is not None:
                    else_body.append(s)

        finally_body = None
        if self.match('KEYWORD', 'finally'):
            self.advance()
            self.expect('SYMBOL', ':')
            finally_body = []
            while not self.match('KEYWORD', 'end') and not self.match('EOF'):
                s = self.parse_statement()
                if s is not None:
                    finally_body.append(s)

        self.expect('KEYWORD', 'end')
        return TryStmt(body, excepts, else_body, finally_body,
                       line=start.line, col=start.col)

    def parse_with(self):
        start = self.current()
        self.expect('KEYWORD', 'with')
        items = []
        while True:
            name = self.expect('IDENTIFIER').value
            self.expect('SYMBOL', '<-')
            value = self.parse_expr()
            items.append((name, value))
            if not self.match('SYMBOL', ','):
                break
            self.advance()
        self.expect('SYMBOL', ':')
        body = []
        while not self.match('KEYWORD', 'end') and not self.match('EOF'):
            s = self.parse_statement()
            if s is not None:
                body.append(s)
        self.expect('KEYWORD', 'end')
        return WithStmt(items, body, line=start.line, col=start.col)

    def parse_match(self):
        start = self.current()
        self.expect('KEYWORD', 'match')
        value = self.parse_expr()
        self.expect('SYMBOL', ':')
        cases = []
        while not self.match('KEYWORD', 'end') and not self.match('EOF'):
            self.expect('KEYWORD', 'case')
            pattern = self.parse_expr()
            self.expect('SYMBOL', ':')
            cb = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'case') \
                    and not self.match('EOF'):
                s = self.parse_statement()
                if s is not None:
                    cb.append(s)
            cases.append({'pattern': pattern, 'body': cb})
        self.expect('KEYWORD', 'end')
        return MatchStmt(value, cases, line=start.line, col=start.col)

    def parse_using(self):
        start = self.current()
        self.expect('KEYWORD', 'using')
        name = self.expect('IDENTIFIER').value
        self.expect('SYMBOL', ';')
        body = []
        while not self.match('KEYWORD', 'using') and not self.match('KEYWORD', 'end') \
                and not self.match('EOF'):
            s = self.parse_statement()
            if s is not None:
                body.append(s)
        return UsingStmt(name, body, line=start.line, col=start.col)

    def parse_decorator(self):
        start = self.current()
        self.expect('SYMBOL', '@')
        target = self.expect('IDENTIFIER').value
        name = None
        if self.match('SYMBOL', '.'):
            self.advance()
            name = self.expect('IDENTIFIER').value
        func = self.parse_function()
        return DecoratorStmt(target, name, func.body,
                             line=start.line, col=start.col)

    # ================================================================
    # 表达式解析（全部携带 line/col）
    # ================================================================

    def parse_expr(self):
        node = self.parse_assignment()

        # 三目：expr if cond else expr
        if self.match('KEYWORD', 'if'):
            saved = self.pos
            self.advance()
            try:
                self.parse_expr()
                if self.match('SYMBOL', ':'):
                    self.pos = saved
                    return node
            except (ParseError, LexerError):
                pass
            self.pos = saved

            self.advance()
            condition = self.parse_expr()
            self.expect('KEYWORD', 'else')
            else_expr = self.parse_expr()
            return IfExpr(condition, node, else_expr,
                          line=node.line, col=node.col)

        return node

    def parse_assignment(self):
        left = self.parse_or_expr()

        if self.match('SYMBOL', '<-'):
            op_tok = self.advance()
            right = self.parse_expr()
            if isinstance(left, (Variable, Attribute)):
                return Assign(left, right, is_ref=False,
                              line=op_tok.line, col=op_tok.col)
            self.error("赋值左侧必须是变量或属性", op_tok)

        if self.match('SYMBOL', '<->'):
            op_tok = self.advance()
            right = self.parse_expr()
            if isinstance(left, Variable) and isinstance(right, Variable):
                return Swap(left.name, right.name,
                            line=op_tok.line, col=op_tok.col)
            self.error("交换操作需要两个变量", op_tok)

        return left

    def parse_or_expr(self):
        left = self.parse_and_expr()
        while self.match('KEYWORD', 'or'):
            op = self.advance()
            right = self.parse_and_expr()
            left = Binary(left, 'or', right, line=op.line, col=op.col)
        return left

    def parse_and_expr(self):
        left = self.parse_compare_expr()
        while self.match('KEYWORD', 'and'):
            op = self.advance()
            right = self.parse_compare_expr()
            left = Binary(left, 'and', right, line=op.line, col=op.col)
        return left

    def parse_compare_expr(self):
        left = self.parse_add_expr()
        ops = {'=', '==', '!=', '<', '>', '<=', '>='}
        while self.match('SYMBOL') and self.current().value in ops:
            op = self.advance()
            right = self.parse_add_expr()
            left = Binary(left, op.value, right, line=op.line, col=op.col)
        return left

    def parse_add_expr(self):
        left = self.parse_mul_expr()
        while self.match('SYMBOL') and self.current().value in ('+', '-'):
            op = self.advance()
            right = self.parse_mul_expr()
            left = Binary(left, op.value, right, line=op.line, col=op.col)
        return left

    def parse_mul_expr(self):
        left = self.parse_pow_expr()
        while self.match('SYMBOL') and self.current().value in ('*', '/', '//', '%'):
            op = self.advance()
            right = self.parse_pow_expr()
            left = Binary(left, op.value, right, line=op.line, col=op.col)
        return left

    def parse_pow_expr(self):
        left = self.parse_unary_expr()
        if self.match('SYMBOL', '**'):
            op = self.advance()
            right = self.parse_unary_expr()
            return Binary(left, '**', right, line=op.line, col=op.col)
        return left

    def parse_unary_expr(self):
        tok = self.current()
        if tok and tok.type == 'SYMBOL' and tok.value in ('-', '~', '!'):
            op = self.advance()
            right = self.parse_unary_expr()
            return Unary(op.value, right, line=op.line, col=op.col)
        if tok and tok.type == 'KEYWORD' and tok.value == 'not':
            op = self.advance()
            right = self.parse_unary_expr()
            return Unary('not', right, line=op.line, col=op.col)
        return self.parse_primary()

    def parse_primary(self):
        tok = self.current()
        if tok is None:
            self.error("意外的文件末尾")

        # 字面量
        if tok.type in ('INT', 'FLOAT', 'DOUBLE', 'STRING'):
            self.advance()
            node = Literal(tok.value, line=tok.line, col=tok.col)
            return self._parse_postfix(node)

        # 关键字字面量
        if tok.type == 'KEYWORD' and tok.value in ('True', 'False', 'none', 'null'):
            self.advance()
            value = {'True': True, 'False': False,
                     'none': None, 'null': NULL}[tok.value]
            node = Literal(value, line=tok.line, col=tok.col)
            return self._parse_postfix(node)

        if tok.type == 'KEYWORD' and tok.value == 'global':
            self.advance()
            node = Variable('global', line=tok.line, col=tok.col)
            return self._parse_postfix(node)
        # 括号表达式
        if tok.type == 'SYMBOL' and tok.value == '(':
            self.advance()
            expr = self.parse_expr()
            self.expect('SYMBOL', ')')
            return self._parse_postfix(expr)

        # 列表
        if tok.type == 'SYMBOL' and tok.value == '[':
            return self.parse_list()

        # 字典
        if tok.type == 'SYMBOL' and tok.value == '{':
            return self.parse_dict()

        # 标识符 / 调用
        if tok.type in ('IDENTIFIER', 'TYPE'):
            return self.parse_identifier_or_call()

        # 代码字符串 `...`
        if tok.type == 'CODE_STRING':
            self.advance()
            return CodeLiteral(tok.value, line=tok.line, col=tok.col)
        # 插值字符串
        if tok.type == 'INTERP_STRING':
            self.advance()
            return self._parse_interp_string(tok.value, tok.line, tok.col)
        self.error(f"意外的 token: {tok.type} {tok.value!r}", tok)

    def _parse_interp_string(self, segments, line, col):
        """把插值字符串的 segments 拆成 Binary('+', ...) 拼接"""
        parts = []
        for kind, content, sline, scol in segments:
            if kind == 'str':
                parts.append(Literal(content, line=sline, col=scol))
            elif kind == 'var':
                inner = Variable(content, line=sline, col=scol)
                parts.append(Call(
                    Variable('str', line=sline, col=scol),
                    [inner], [], line=sline, col=scol))
            elif kind == 'expr':
                sub_tokens = split_token(content)
                sub_parser = Parser(sub_tokens)
                try:
                    expr = sub_parser.parse_expr()
                except ParseError as e:
                    self.error(f"插值表达式语法错误: {e}", self.current())
                parts.append(Call(
                    Variable('str', line=sline, col=scol),
                    [expr], [], line=sline, col=scol))
        if not parts:
            return Literal("", line=line, col=col)
        node = parts[0]
        for p in parts[1:]:
            node = Binary(node, '+', p, line=line, col=col)
        return node

    def parse_identifier_or_call(self):
        tok = self.advance()
        name = tok.value

        # 函数调用
        if self.match('SYMBOL', '('):
            self.advance()
            args = []
            kwargs = []
            while not self.match('SYMBOL', ')'):
                if self.match('IDENTIFIER') and self.peek() and self.peek().value == '=':
                    key = self.advance().value
                    self.expect('SYMBOL', '=')
                    val = self.parse_expr()
                    kwargs.append((key, val))
                else:
                    args.append(self.parse_expr())
                if self.match('SYMBOL', ','):
                    self.advance()
                else:
                    break
            self.expect('SYMBOL', ')')
            node = Call(Variable(name, line=tok.line, col=tok.col),
                        args, kwargs, line=tok.line, col=tok.col)
            return self._parse_postfix(node)

        node = Variable(name, line=tok.line, col=tok.col)
        return self._parse_postfix(node)

    def _parse_postfix(self, node):
        """处理属性访问、下标访问、调用链"""
        while True:
            if self.match('SYMBOL', '.'):
                dot = self.advance()
                attr = self.expect('IDENTIFIER')
                node = Attribute(node, attr.value,
                                 line=dot.line, col=dot.col)
            elif self.match('SYMBOL', '['):
                lb = self.advance()
                index = self.parse_expr()
                self.expect('SYMBOL', ']')
                node = Subscript(node, index, line=lb.line, col=lb.col)
            elif self.match('SYMBOL', '('):
                self.advance()
                args = []
                kwargs = []
                while not self.match('SYMBOL', ')'):
                    if self.match('IDENTIFIER') and self.peek() and self.peek().value == '=':
                        key = self.advance().value
                        self.expect('SYMBOL', '=')
                        val = self.parse_expr()
                        kwargs.append((key, val))
                    else:
                        args.append(self.parse_expr())
                    if self.match('SYMBOL', ','):
                        self.advance()
                    else:
                        break
                self.expect('SYMBOL', ')')
                node = Call(node, args, kwargs,
                            line=node.line, col=node.col)
            else:
                break
        return node

    def parse_list(self):
        start = self.current()
        self.expect('SYMBOL', '[')
        elements = []
        if not self.match('SYMBOL', ']'):
            while True:
                elements.append(self.parse_expr())
                if not self.match('SYMBOL', ','):
                    break
                self.advance()
                if self.match('SYMBOL', ']'):
                    break
        self.expect('SYMBOL', ']')
        return ListExpr(elements, line=start.line, col=start.col)

    def parse_dict(self):
        start = self.current()
        self.expect('SYMBOL', '{')
        items = []
        if not self.match('SYMBOL', '}'):
            while True:
                key = self.parse_expr()
                self.expect('SYMBOL', ':')
                value = self.parse_expr()
                items.append((key, value))
                if not self.match('SYMBOL', ','):
                    break
                self.advance()
                if self.match('SYMBOL', '}'):
                    break
        self.expect('SYMBOL', '}')
        return DictExpr(items, line=start.line, col=start.col)


# ============================================================================
# 类型检查
# ============================================================================


# ============================================================================
# 静态检查
# ============================================================================

class CheckError(Exception):
    def __init__(self, message, line=0, col=0):
        self.message = message
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {message}")
        else:
            super().__init__(message)


class Checker:
    def __init__(self):
        # 每层作用域: {name: {type, annotated, is_const}}
        self.scope_stack = [{}]
        # 函数签名: name -> (param_types, defaults_count, return_type)
        self.function_signatures = {}
        # 当前正在检查的函数的返回值类型
        self.current_return_type = None
        # break/continue 检查
        self.loop_depth = 0
        # return 检查（支持嵌套函数）
        self.in_function = 0
        # goto 检查
        self.labels = set()

    # ---------- 作用域 ----------

    def push_scope(self):
        self.scope_stack.append({})

    def pop_scope(self):
        self.scope_stack.pop()

    def current_scope(self):
        return self.scope_stack[-1]

    def lookup(self, name):
        for scope in reversed(self.scope_stack):
            if name in scope:
                return scope[name]
        return None

    def declare(self, name, type_name, annotated=False, is_const=False, node=None):
        scope = self.current_scope()
        if name in scope:
            line = node.line if node else 0
            col = node.col if node else 0
            raise CheckError(f"变量 '{name}' 重复声明", line=line, col=col)
        scope[name] = {
            'type': type_name,
            'annotated': annotated,
            'is_const': is_const,
        }

    def compatible(self, expected, actual):
        if expected == "int" and actual == "float":
            return True
        if expected == "float" and actual == "int":
            return True
        if expected is None or actual is None:
            return True
        if expected == 'any' or actual == 'any':
            return True
        if expected == actual:
            return True
        e_base = expected.split('[')[0].strip().split()[0]
        a_base = actual.split('[')[0].strip().split()[0]
        return e_base == a_base

    # ---------- 入口 ----------

    def check(self, program):
        self._collect_labels(program.body)
        for stmt in program.body:
            self.check_statement(stmt)

    def _collect_labels(self, stmts):
        for s in stmts:
            if isinstance(s, LabelStmt):
                self.labels.add(s.name)
            elif isinstance(s, IfStmt):
                self._collect_labels(s.body)
                for _, eb in s.elifs:
                    self._collect_labels(eb)
                self._collect_labels(s.else_body)
            elif isinstance(s, (ForStmt, WhileStmt)):
                self._collect_labels(s.body)
            elif isinstance(s, TryStmt):
                self._collect_labels(s.body)
                for ec in s.excepts:
                    self._collect_labels(ec['body'])
                if s.else_body:
                    self._collect_labels(s.else_body)
                if s.finally_body:
                    self._collect_labels(s.finally_body)

    # ---------- 语句检查 ----------

    def check_statement(self, stmt):
        if isinstance(stmt, ExprStmt):
            self.check_expr(stmt.expr)

        elif isinstance(stmt, DefineStmt):
            self.check_define(stmt)

        elif isinstance(stmt, FuncDefStmt):
            self.check_function_def(stmt)

        elif isinstance(stmt, ClassDefStmt):
            self.check_class_def(stmt)

        elif isinstance(stmt, IfStmt):
            self.check_expr(stmt.condition)
            self.push_scope()
            for s in stmt.body:
                self.check_statement(s)
            self.pop_scope()
            for ec, eb in stmt.elifs:
                self.check_expr(ec)
                self.push_scope()
                for s in eb:
                    self.check_statement(s)
                self.pop_scope()
            self.push_scope()
            for s in stmt.else_body:
                self.check_statement(s)
            self.pop_scope()

        elif isinstance(stmt, ForStmt):
            self.check_for(stmt)

        elif isinstance(stmt, WhileStmt):
            self.check_expr(stmt.condition)
            self.push_scope()
            self.loop_depth += 1
            for s in stmt.body:
                self.check_statement(s)
            self.loop_depth -= 1
            self.pop_scope()

        elif isinstance(stmt, ReturnStmt):
            if self.in_function == 0:
                raise CheckError(
                    "'return' 必须在函数内使用",
                    line=stmt.line, col=stmt.col)
            value_type = self.check_expr(stmt.value) if stmt.value else None
            if self.current_return_type and value_type:
                if not self.compatible(self.current_return_type, value_type):
                    raise CheckError(
                        f"返回值类型错误: 期望 {self.current_return_type}，"
                        f"但得到 {value_type}",
                        line=stmt.line, col=stmt.col)

        elif isinstance(stmt, BreakStmt):
            if self.loop_depth == 0:
                raise CheckError(
                    "'break' 必须在循环内使用",
                    line=stmt.line, col=stmt.col)

        elif isinstance(stmt, ContinueStmt):
            if self.loop_depth == 0:
                raise CheckError(
                    "'continue' 必须在循环内使用",
                    line=stmt.line, col=stmt.col)

        elif isinstance(stmt, GotoStmt):
            if stmt.label not in self.labels:
                raise CheckError(
                    f"goto 目标标签不存在: '{stmt.label}'",
                    line=stmt.line, col=stmt.col)

        elif isinstance(stmt, LabelStmt):
            pass  # 已预扫描

        elif isinstance(stmt, TryStmt):
            self.push_scope()
            for s in stmt.body:
                self.check_statement(s)
            self.pop_scope()
            for ec in stmt.excepts:
                self.push_scope()
                if ec['name']:
                    self.declare(ec['name'], None, node=stmt)
                for s in ec['body']:
                    self.check_statement(s)
                self.pop_scope()
            if stmt.else_body:
                self.push_scope()
                for s in stmt.else_body:
                    self.check_statement(s)
                self.pop_scope()
            if stmt.finally_body:
                self.push_scope()
                for s in stmt.finally_body:
                    self.check_statement(s)
                self.pop_scope()

        elif isinstance(stmt, RaiseStmt):
            self.check_expr(stmt.exception)

        elif isinstance(stmt, (ImportStmt, WithStmt, MatchStmt, UsingStmt,
                               DecoratorStmt)):
            # 尚未实现，跳过检查
            pass

    # ---------- 定义检查 ----------

    def check_define(self, stmt):
        # ref 必须绑定到已声明的变量
        if stmt.is_ref:
            if not isinstance(stmt.value, Variable):
                raise CheckError(
                    "ref 必须绑定到变量",
                    line=stmt.line, col=stmt.col)
            target = self.lookup(stmt.value.name)
            if target is None:
                raise CheckError(
                    f"ref 目标变量未声明: '{stmt.value.name}'",
                    line=stmt.line, col=stmt.col)
            self.declare(stmt.name, target['type'], annotated=True,
                         node=stmt)
            if target['is_const']:
                raise CheckError(
                    f"不能 ref 常量 '{stmt.value.name}'",
                    line=stmt.line, col=stmt.col)
            return

        value_type = self.check_expr(stmt.value) if stmt.value else None

        if stmt.type_name:
            base = stmt.type_name.split('[')[0].strip().split()[0]
            if value_type and not self.compatible(base, value_type):
                raise CheckError(
                    f"类型错误: 变量 '{stmt.name}' 注解为 {stmt.type_name}，"
                    f"但赋值表达式类型为 {value_type}",
                    line=stmt.line, col=stmt.col)
            self.declare(stmt.name, stmt.type_name, annotated=True,
                         is_const=stmt.is_const, node=stmt)
        else:
            self.declare(stmt.name, value_type, annotated=False,
                         is_const=stmt.is_const, node=stmt)

    # ---------- 函数 / 方法检查 ----------

    def check_function_def(self, stmt):
        param_types = [p.get('type') for p in stmt.params]
        param_names = [p['name'] for p in stmt.params]
        defaults_count = sum(
            1 for p in stmt.params if p.get('default') is not None)
        self.function_signatures[stmt.name] = (
            param_types, param_names, defaults_count, stmt.return_type)

        self.push_scope()
        for p in stmt.params:
            self.declare(p['name'], p.get('type'),
                         annotated=bool(p.get('type')), node=stmt)

        old_return = self.current_return_type
        self.current_return_type = stmt.return_type
        self.in_function += 1

        self._check_block(stmt.body)

        self.in_function -= 1
        self.current_return_type = old_return
        self.pop_scope()

    def check_class_def(self, stmt):
        for s in stmt.body:
            if isinstance(s, FuncDefStmt):
                self.check_method_def(s)
            else:
                self.check_statement(s)

    def _check_block(self, stmts):
        """检查一个 exec_block 内的语句，label 作用域限于本 block"""
        old_labels = self.labels
        self.labels = set()
        for s in stmts:
            if isinstance(s, LabelStmt):
                self.labels.add(s.name)

        for s in stmts:
            self.check_statement(s)

        self.labels = old_labels

    def check_method_def(self, method_stmt):
        param_types = [p.get('type') for p in method_stmt.params]
        defaults_count = sum(
            1 for p in method_stmt.params if p.get('default') is not None)

        self.push_scope()
        self.declare('self', None, node=method_stmt)
        for p in method_stmt.params:
            if p['name'] == 'self':
                continue
            self.declare(p['name'], p.get('type'),
                         annotated=bool(p.get('type')), node=method_stmt)

        old_return = self.current_return_type
        self.current_return_type = method_stmt.return_type
        self.in_function += 1

        self._check_block(method_stmt.body)   # ← 改为 _check_block

        self.in_function -= 1
        self.current_return_type = old_return
        self.pop_scope()

    # ---------- 循环检查 ----------

    def check_for(self, stmt):
        if stmt.count is not None:
            self.check_expr(stmt.count)
        elif stmt.range_expr is not None:
            self.check_expr(stmt.range_expr.start)
            self.check_expr(stmt.range_expr.end)
            if stmt.range_expr.step:
                self.check_expr(stmt.range_expr.step)
        else:
            self.check_expr(stmt.iterable)

        self.push_scope()
        if stmt.variable:
            self.declare(stmt.variable, None, node=stmt)
        self.loop_depth += 1
        for s in stmt.body:
            self.check_statement(s)
        self.loop_depth -= 1
        self.pop_scope()

    # ---------- 表达式检查 ----------

    def check_expr(self, expr):
        if expr is None:
            return None

        if isinstance(expr, CodeLiteral):
            # 尝试解析，只报语法错误（不报未定义变量）
            try:
                tokens = split_token(expr.source)
                parser = Parser(tokens)
                parser.parse()
            except (LexerError, ParseError) as e:
                raise CheckError(
                    f"code 字符串语法错误: {e}",
                    line=expr.line, col=expr.col)
            return 'code'
        if isinstance(expr, Literal):
            return self._infer(expr.value)

        if isinstance(expr, Variable):
            # 先查变量作用域
            info = self.lookup(expr.name)
            if info is not None:
                return info['type']
            # 再查函数签名（函数名可以作为值传递）
            if expr.name in self.function_signatures:
                return 'function'
            raise CheckError(
                f"未定义的变量: '{expr.name}'",
                line=expr.line, col=expr.col)

        if isinstance(expr, Binary):
            lt = self.check_expr(expr.left)
            rt = self.check_expr(expr.right)
            if expr.op in ('+', '-', '*', '/', '//', '%', '**'):
                if lt in ('int', 'float', 'double') and rt in ('int', 'float', 'double'):
                    if 'double' in (lt, rt):
                        return 'double'
                    if 'float' in (lt, rt):
                        return 'float'
                    return 'int'
                if expr.op == '+' and lt == 'str' and rt == 'str':
                    return 'str'
            if expr.op in ('==', '=', '!=', '<', '>', '<=', '>=', 'and', 'or'):
                return 'bool'
            return None

        if isinstance(expr, Unary):
            return self.check_expr(expr.right)

        if isinstance(expr, Assign):
            vt = self.check_expr(expr.value)
            if isinstance(expr.name, Variable):
                info = self.lookup(expr.name.name)
                if info is None:
                    raise CheckError(
                        f"未定义的变量: '{expr.name.name}'",
                        line=expr.line, col=expr.col)
                if info['is_const']:
                    raise CheckError(
                        f"不能重新赋值常量 '{expr.name.name}'",
                        line=expr.line, col=expr.col)
                if info['annotated'] and vt and not self.compatible(info['type'], vt):
                    raise CheckError(
                        f"类型错误: 变量 '{expr.name.name}' 注解为 {info['type']}，"
                        f"但赋值表达式类型为 {vt}",
                        line=expr.line, col=expr.col)
                if not info['annotated']:
                    info['type'] = vt
            elif isinstance(expr.name, Attribute):
                self.check_expr(expr.name.obj)
            return vt

        if isinstance(expr, Call):
            for a in expr.args:
                self.check_expr(a)
            for _, v in expr.kwargs:
                self.check_expr(v)
            if isinstance(expr.func, Variable):
                sig = self.function_signatures.get(expr.func.name)
                if sig:
                    ptypes, pnames, defaults_count, rtype = sig
                    required = len(ptypes) - defaults_count
                    total_supplied = len(expr.args) + len(expr.kwargs)
                    if total_supplied < required:
                        raise CheckError(
                            f"调用 '{expr.func.name}' 参数不足: "
                            f"至少需要 {required} 个，但给了 {total_supplied} 个",
                            line=expr.line, col=expr.col)
                    if total_supplied > len(ptypes):
                        raise CheckError(
                            f"调用 '{expr.func.name}' 参数过多: "
                            f"最多 {len(ptypes)} 个，但给了 {total_supplied} 个",
                            line=expr.line, col=expr.col)
                    # 位置参数类型检查
                    for i, a in enumerate(expr.args):
                        if i < len(ptypes) and ptypes[i]:
                            at = self.check_expr(a)
                            if not self.compatible(ptypes[i], at):
                                raise CheckError(
                                    f"调用 '{expr.func.name}' 第 {i+1} 个参数: "
                                    f"期望 {ptypes[i]}，得到 {at}",
                                    line=expr.line, col=expr.col)
                    # 关键字参数类型检查
                    for key, val_node in expr.kwargs:
                        if key in pnames:
                            idx = pnames.index(key)
                            if ptypes[idx]:
                                vt = self.check_expr(val_node)
                                if not self.compatible(ptypes[idx], vt):
                                    raise CheckError(
                                        f"调用 '{expr.func.name}' 关键字参数 '{key}': "
                                        f"期望 {ptypes[idx]}，得到 {vt}",
                                        line=expr.line, col=expr.col)
                        else:
                            raise CheckError(
                                f"调用 '{expr.func.name}' 未知关键字参数: '{key}'",
                                line=expr.line, col=expr.col)
                    return rtype
            return None
        if isinstance(expr, Attribute):
            self.check_expr(expr.obj)
            return None

        if isinstance(expr, IfExpr):
            self.check_expr(expr.condition)
            t1 = self.check_expr(expr.then_expr)
            t2 = self.check_expr(expr.else_expr)
            return t1 or t2

        if isinstance(expr, ListExpr):
            for e in expr.elements:
                self.check_expr(e)
            return 'list'

        if isinstance(expr, DictExpr):
            for k, v in expr.items:
                self.check_expr(k)
                self.check_expr(v)
            return 'dict'

        if isinstance(expr, RangeExpr):
            self.check_expr(expr.start)
            self.check_expr(expr.end)
            if expr.step:
                self.check_expr(expr.step)
            return 'range'

        if isinstance(expr, Subscript):
            self.check_expr(expr.obj)
            self.check_expr(expr.index)
            return None

        if isinstance(expr, Swap):
            li = self.lookup(expr.left)
            ri = self.lookup(expr.right)
            if li is None:
                raise CheckError(
                    f"交换操作: 变量 '{expr.left}' 未声明",
                    line=expr.line, col=expr.col)
            if ri is None:
                raise CheckError(
                    f"交换操作: 变量 '{expr.right}' 未声明",
                    line=expr.line, col=expr.col)
            return None

        return None

    @staticmethod
    def _infer(value):
        if isinstance(value, bool):
            return 'bool'
        if isinstance(value, int):
            return 'int'
        if isinstance(value, float):
            return 'float'
        if isinstance(value, str):
            return 'str'
        if isinstance(value, list):
            return 'list'
        if isinstance(value, dict):
            return 'dict'
        if value is None:
            return 'none'
        return None

# ============================================================================
# 运行时
# ============================================================================


class Cell:
    __slots__ = ('value', 'is_const')

    def __init__(self, value=None, is_const=False):
        self.value = value
        self.is_const = is_const


class EclException(Exception):
    def __init__(self, exc_type, message, cause=None, line=0, col=0):
        self.exc_type = exc_type
        self.message = message
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {exc_type}: {message}")
        else:
            super().__init__(f"{exc_type}: {message}")


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class EclInstance:
    def __init__(self, cls):
        self.cls = cls
        self.attrs = {}

    def __repr__(self):
        return f"<{self.cls.name} object>"


class ConstChangingError(EclException):
    pass


# ============================================================================
# Compiler
# ============================================================================
class Compiler:
    """AST -> 三地址码 IR"""

    def __init__(self):
        self.code = []
        self.temp_counter = 0
        self.label_counter = 0
        self.break_label = None
        self.continue_label = None
        self.exception_table = []

    # ---------- 工具 ----------

    def new_temp(self):
        self.temp_counter += 1
        return f"t{self.temp_counter}"

    def new_label(self):
        self.label_counter += 1
        return f"L{self.label_counter}"

    def emit(self, *instr):
        self.code.append(instr)

    def emit_label(self, name):
        self.code.append(('label', name))

    # ---------- 入口 ----------

    def compile_program(self, program):
        for stmt in program.body:
            self.compile_stmt(stmt)
        self.emit('halt')
        return self.code, self.exception_table

    # ---------- 语句 ----------

    def compile_stmt(self, stmt):
        if isinstance(stmt, ExprStmt):
            self.compile_expr(stmt.expr)
            return

        if isinstance(stmt, DefineStmt):
            return self.compile_define(stmt)

        if isinstance(stmt, FuncDefStmt):
            return self.compile_func_def(stmt)

        if isinstance(stmt, ClassDefStmt):
            return self.compile_class_def(stmt)

        if isinstance(stmt, IfStmt):
            return self.compile_if(stmt)

        if isinstance(stmt, WhileStmt):
            return self.compile_while(stmt)

        if isinstance(stmt, ForStmt):
            return self.compile_for(stmt)

        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                src = self.compile_expr(stmt.value)
                self.emit('return', src)
            else:
                self.emit('return_none')
            return

        if isinstance(stmt, BreakStmt):
            if self.break_label is None:
                raise CompileError("'break' 必须在循环内使用", stmt)
            self.emit('goto', self.break_label)
            return

        if isinstance(stmt, ContinueStmt):
            if self.continue_label is None:
                raise CompileError("'continue' 必须在循环内使用", stmt)
            self.emit('goto', self.continue_label)
            return

        if isinstance(stmt, GotoStmt):
            self.emit('goto', f"label_{stmt.label}")
            return

        if isinstance(stmt, LabelStmt):
            self.emit_label(f"label_{stmt.name}")
            return

        if isinstance(stmt, TryStmt):
            return self.compile_try(stmt)

        if isinstance(stmt, RaiseStmt):
            src = self.compile_expr(stmt.exception)
            self.emit('raise', src)
            return

        if isinstance(stmt, MatchStmt):
            raise NotImplementedError("match 尚未实现")

        raise NotImplementedError(f"未实现的语句: {type(stmt).__name__}")

    # ---------- 定义 ----------

    def compile_define(self, stmt):
        if stmt.is_ref:
            if isinstance(stmt.value, Variable):
                self.emit('ref', stmt.name, stmt.value.name)
            else:
                raise CompileError("ref 必须绑定到变量", stmt)
            return
        if stmt.value is not None:
            src = self.compile_expr(stmt.value)
        else:
            src = self.new_temp()
            self.emit('const', src, None)
        self.emit('store', stmt.name, src)

    # ---------- 函数 ----------

    def compile_func_def(self, stmt):
        sub = Compiler()
        for s in stmt.body:
            sub.compile_stmt(s)
        sub.emit('return_null')
        sub.emit('halt')
        defaults = {}
        for p in stmt.params:
            if p.get('default') is not None:
                if isinstance(p['default'], Literal):
                    defaults[p['name']] = p['default'].value
                else:
                    defaults[p['name']] = p['default']
        self.emit('func', stmt.name, sub.code, stmt.params,
                  stmt.varargs, stmt.kwargs, stmt.return_type, defaults)

    # ---------- 类 ----------

    def compile_class_def(self, stmt):
        methods = {}
        for s in stmt.body:
            if isinstance(s, FuncDefStmt):
                sub = Compiler()
                for body_s in s.body:
                    sub.compile_stmt(body_s)
                sub.emit('return_null')
                sub.emit('halt')
                defaults = {}
                for p in s.params:
                    if p.get('default') is not None:
                        if isinstance(p['default'], Literal):
                            defaults[p['name']] = p['default'].value
                        else:
                            defaults[p['name']] = p['default']
                methods[s.name] = (sub.code, s.params, s.varargs,
                                   s.kwargs, s.return_type, defaults)
        self.emit('class', stmt.name, stmt.bases, methods)

    # ---------- if ----------

    def compile_if(self, stmt):
        end_label = self.new_label()

        cond = self.compile_expr(stmt.condition)
        next_label = self.new_label()
        self.emit('if_not_goto', cond, next_label)

        for s in stmt.body:
            self.compile_stmt(s)
        self.emit('goto', end_label)
        self.emit_label(next_label)

        for ec, eb in stmt.elifs:
            cond = self.compile_expr(ec)
            next_label = self.new_label()
            self.emit('if_not_goto', cond, next_label)
            for s in eb:
                self.compile_stmt(s)
            self.emit('goto', end_label)
            self.emit_label(next_label)

        if stmt.else_body:
            for s in stmt.else_body:
                self.compile_stmt(s)

        self.emit_label(end_label)

    # ---------- while ----------

    def compile_while(self, stmt):
        start = self.new_label()
        end = self.new_label()
        self.emit_label(start)
        cond = self.compile_expr(stmt.condition)
        self.emit('if_not_goto', cond, end)

        old_break, old_continue = self.break_label, self.continue_label
        self.break_label = end
        self.continue_label = start

        for s in stmt.body:
            self.compile_stmt(s)

        self.break_label, self.continue_label = old_break, old_continue
        self.emit('goto', start)
        self.emit_label(end)

    # ---------- for ----------

    def compile_for(self, stmt):
        start = self.new_label()
        end = self.new_label()
        continue_label = self.new_label()

        old_break, old_continue = self.break_label, self.continue_label
        self.break_label = end
        self.continue_label = continue_label

        if stmt.count is not None:
            count_src = self.compile_expr(stmt.count)
            iter_tmp = self.new_temp()
            self.emit('const', iter_tmp, 0)
            self.emit_label(start)
            cmp_tmp = self.new_temp()
            self.emit('lt', cmp_tmp, iter_tmp, count_src)
            self.emit('if_not_goto', cmp_tmp, end)
            for s in stmt.body:
                self.compile_stmt(s)
            self.emit_label(continue_label)
            one = self.new_temp()
            self.emit('const', one, 1)
            next_tmp = self.new_temp()
            self.emit('add', next_tmp, iter_tmp, one)
            self.emit('assign', iter_tmp, next_tmp)
            self.emit('goto', start)
            self.emit_label(end)

        elif stmt.range_expr is not None:
            r = stmt.range_expr
            start_src = self.compile_expr(r.start)
            end_src = self.compile_expr(r.end)
            step_src = self.compile_expr(r.step) if r.step else None
            if step_src is None:
                step_src = self.new_temp()
                self.emit('const', step_src, 1)
            iter_tmp = self.new_temp()
            self.emit('assign', iter_tmp, start_src)
            self.emit_label(start)
            cmp_tmp = self.new_temp()
            op = 'le' if r.inclusive else 'lt'
            self.emit(op, cmp_tmp, iter_tmp, end_src)
            self.emit('if_not_goto', cmp_tmp, end)
            self.emit('store', stmt.variable, iter_tmp)
            for s in stmt.body:
                self.compile_stmt(s)
            self.emit_label(continue_label)
            next_tmp = self.new_temp()
            self.emit('add', next_tmp, iter_tmp, step_src)
            self.emit('assign', iter_tmp, next_tmp)
            self.emit('goto', start)
            self.emit_label(end)

        else:
            iterable_src = self.compile_expr(stmt.iterable)
            idx_tmp = self.new_temp()
            self.emit('const', idx_tmp, 0)
            self.emit_label(start)
            len_tmp = self.new_temp()
            self.emit('var', len_tmp, 'len')
            len_result = self.new_temp()
            self.emit('call', len_result, len_tmp, [iterable_src], {})
            cmp_tmp = self.new_temp()
            self.emit('lt', cmp_tmp, idx_tmp, len_result)
            self.emit('if_not_goto', cmp_tmp, end)
            item_tmp = self.new_temp()
            self.emit('get_item', item_tmp, iterable_src, idx_tmp)
            self.emit('store', stmt.variable, item_tmp)
            for s in stmt.body:
                self.compile_stmt(s)
            self.emit_label(continue_label)
            one = self.new_temp()
            self.emit('const', one, 1)
            next_tmp = self.new_temp()
            self.emit('add', next_tmp, idx_tmp, one)
            self.emit('assign', idx_tmp, next_tmp)
            self.emit('goto', start)
            self.emit_label(end)

        self.break_label, self.continue_label = old_break, old_continue

    # ---------- try ----------

    def compile_try(self, stmt):
        try_start = len(self.code)
        for s in stmt.body:
            self.compile_stmt(s)
        try_end = len(self.code)

        end_label = self.new_label()
        else_label = self.new_label() if stmt.else_body else end_label

        self.emit('goto', else_label)

        for ec in stmt.excepts:
            handler_pc = len(self.code)
            self.exception_table.append({
                'try_start': try_start,
                'try_end': try_end,
                'handler_pc': handler_pc,
                'exc_type': ec['type'],
                'exc_name': ec['name'],
            })
            for s in ec['body']:
                self.compile_stmt(s)
            self.emit('goto', end_label)

        if stmt.else_body:
            self.emit_label(else_label)
            for s in stmt.else_body:
                self.compile_stmt(s)

        self.emit_label(end_label)

        if stmt.finally_body:
            for s in stmt.finally_body:
                self.compile_stmt(s)

    # ---------- 表达式 ----------

    def compile_expr(self, expr):
        if isinstance(expr, Literal):
            t = self.new_temp()
            self.emit('const', t, expr.value)
            return t

        if isinstance(expr, Variable):
            t = self.new_temp()
            self.emit('var', t, expr.name)
            return t

        if isinstance(expr, Binary):
            lt = self.compile_expr(expr.left)
            rt = self.compile_expr(expr.right)
            t = self.new_temp()
            op = expr.op
            if op == '+':
                self.emit('add', t, lt, rt)
            elif op == '-':
                self.emit('sub', t, lt, rt)
            elif op == '*':
                self.emit('mul', t, lt, rt)
            elif op == '/':
                self.emit('div', t, lt, rt)
            elif op == '//':
                self.emit('floordiv', t, lt, rt)
            elif op == '%':
                self.emit('mod', t, lt, rt)
            elif op == '**':
                self.emit('pow', t, lt, rt)
            elif op in ('=', '=='):
                self.emit('eq', t, lt, rt)
            elif op == '!=':
                self.emit('ne', t, lt, rt)
            elif op == '<':
                self.emit('lt', t, lt, rt)
            elif op == '>':
                self.emit('gt', t, lt, rt)
            elif op == '<=':
                self.emit('le', t, lt, rt)
            elif op == '>=':
                self.emit('ge', t, lt, rt)
            elif op == '|':
                self.emit('bor', t, lt, rt)
            elif op == '&':
                self.emit('band', t, lt, rt)
            elif op == '^':
                self.emit('xor', t, lt, rt)
            elif op == '<<':
                self.emit('lshift', t, lt, rt)
            elif op == '>>':
                self.emit('rshift', t, lt, rt)
            elif op == 'and':
                self.emit('and', t, lt, rt)
            elif op == 'or':
                self.emit('or', t, lt, rt)
            else:
                raise CompileError(f"未知二元运算符: {op}", expr)
            return t

        if isinstance(expr, Unary):
            src = self.compile_expr(expr.right)
            t = self.new_temp()
            if expr.op == '-':
                self.emit('neg', t, src)
            elif expr.op == '~':
                self.emit('invert', t, src)
            elif expr.op in ('!', 'not'):
                self.emit('not', t, src)
            else:
                raise CompileError(f"未知一元运算符: {expr.op}", expr)
            return t

        if isinstance(expr, Assign):
            val = self.compile_expr(expr.value)
            if isinstance(expr.name, Variable):
                self.emit('store', expr.name.name, val)
            elif isinstance(expr.name, Attribute):
                obj = self.compile_expr(expr.name.obj)
                self.emit('set_attr', obj, expr.name.attr, val)
            return val

        if isinstance(expr, Call):
            func = self.compile_expr(expr.func)
            args = [self.compile_expr(a) for a in expr.args]
            kwargs = {k: self.compile_expr(v) for k, v in expr.kwargs}
            t = self.new_temp()
            self.emit('call', t, func, args, kwargs)
            return t

        if isinstance(expr, Attribute):
            obj = self.compile_expr(expr.obj)
            t = self.new_temp()
            self.emit('get_attr', t, obj, expr.attr)
            return t

        if isinstance(expr, IfExpr):
            cond = self.compile_expr(expr.condition)
            t = self.new_temp()
            else_label = self.new_label()
            end_label = self.new_label()
            self.emit('if_not_goto', cond, else_label)
            then_src = self.compile_expr(expr.then_expr)
            self.emit('assign', t, then_src)
            self.emit('goto', end_label)
            self.emit_label(else_label)
            else_src = self.compile_expr(expr.else_expr)
            self.emit('assign', t, else_src)
            self.emit_label(end_label)
            return t

        if isinstance(expr, ListExpr):
            t = self.new_temp()
            self.emit('new_list', t)
            for e in expr.elements:
                e_src = self.compile_expr(e)
                self.emit('list_append', t, e_src)
            return t

        if isinstance(expr, DictExpr):
            t = self.new_temp()
            self.emit('new_dict', t)
            for k, v in expr.items:
                k_src = self.compile_expr(k)
                v_src = self.compile_expr(v)
                self.emit('dict_set', t, k_src, v_src)
            return t

        if isinstance(expr, Subscript):
            obj = self.compile_expr(expr.obj)
            idx = self.compile_expr(expr.index)
            t = self.new_temp()
            self.emit('get_item', t, obj, idx)
            return t

        if isinstance(expr, RangeExpr):
            start = self.compile_expr(expr.start)
            end = self.compile_expr(expr.end)
            step = self.compile_expr(expr.step) if expr.step else None
            t = self.new_temp()
            self.emit('new_range', t, start, end, expr.inclusive, step)
            return t

        if isinstance(expr, CodeLiteral):
            t = self.new_temp()
            self.emit('new_code', t, expr.source)
            return t

        if isinstance(expr, Swap):
            lt = self.new_temp()
            self.emit('var', lt, expr.left)
            rt = self.new_temp()
            self.emit('var', rt, expr.right)
            self.emit('store', expr.left, rt)
            self.emit('store', expr.right, lt)
            return lt

        raise NotImplementedError(f"未实现的表达式: {type(expr).__name__}")


class CompileError(Exception):
    def __init__(self, message, node=None):
        self.message = message
        self.node = node
        if node and hasattr(node, 'line'):
            super().__init__(f"[行 {node.line}, 列 {node.col}] {message}")
        else:
            super().__init__(message)


# ============================================================================
# IR 版函数 / 类
# ============================================================================

class EclFunctionIR:
    def __init__(self, name, code, params, varargs, kwargs,
                 ret_type, interpreter, defaults=None):
        self.name = name
        self.code = code
        self.params = params
        self.varargs = varargs
        self.kwargs = kwargs
        self.ret_type = ret_type
        self.interpreter = interpreter
        self.defaults = defaults or {}

    def __call__(self, *args, **kwargs):
        return self.interpreter.call_function_ir(self, args, kwargs)

    def __repr__(self):
        return f"<function {self.name}>"


class EclClassIR:
    def __init__(self, name, bases, methods, interpreter):
        self.name = name
        self.bases = bases
        # name -> (code, params, varargs, kwargs, ret_type, defaults)
        self.methods = methods
        self.interpreter = interpreter

    def __call__(self, *args, **kwargs):
        instance = EclInstance(self)
        instance.attrs['__class__'] = self
        init = self.methods.get('__init__')
        if init:
            self.interpreter.call_method_ir(init, instance, args, kwargs)
        return instance

    def __repr__(self):
        return f"<class {self.name}>"


class VM:
    def __init__(self, code, exception_table, scope, interpreter):
        self.code = code
        self.exception_table = exception_table
        self.scope = scope
        self.interpreter = interpreter
        self.temps = {}
        self.pc = 0
        self.labels = {}
        for i, op in enumerate(code):
            if op[0] == 'label':
                self.labels[op[1]] = i + 1

    def run(self):
        while self.pc < len(self.code):
            try:
                op = self.code[self.pc]
                self.pc += 1
                self.exec_op(op)
            except ReturnSignal:
                raise
            except EclException as e:
                if not self.handle_exception(e):
                    raise

    def handle_exception(self, e):
        for entry in sorted(self.exception_table,
                            key=lambda x: x['try_start'], reverse=True):
            if entry['try_start'] <= self.pc <= entry['try_end']:
                if entry['exc_type'] is None or entry['exc_type'] == e.exc_type:
                    if entry['exc_name']:
                        self.scope[entry['exc_name']] = Cell(e)
                    self.pc = entry['handler_pc']
                    return True
        return False

    def lookup_cell(self, name, for_write=False):
        for scope in [self.scope, self.interpreter.globals]:
            if name in scope:
                cell = scope[name]
                if for_write and cell.is_const:
                    self.interpreter.error(
                        f"不能重新赋值常量 '{name}'", None, 'ConstChangingError')
                return cell
        self.interpreter.error(f"未定义的变量: '{name}'", None, 'NameError')

    def exec_op(self, op):
        kind = op[0]

        if kind == 'const':
            _, dest, value = op
            self.temps[dest] = value

        elif kind == 'var':
            _, dest, name = op
            cell = self.lookup_cell(name)
            self.temps[dest] = cell.value

        elif kind == 'store':
            _, name, src = op
            val = self.temps[src]
            found = False
            for scope in [self.scope, self.interpreter.globals]:
                if name in scope:
                    cell = scope[name]
                    if cell.is_const:
                        self.interpreter.error(
                            f"不能重新赋值常量 '{name}'", None, 'ConstChangingError')
                    cell.value = val
                    found = True
                    break
            if not found:
                self.scope[name] = Cell(val)

        elif kind == 'ref':
            _, name, src_name = op
            cell = self.lookup_cell(src_name)
            self.scope[name] = cell

        elif kind == 'assign':
            _, dest, src = op
            self.temps[dest] = self.temps[src]

        # ---------- 原生运算 ----------
        elif kind == 'add':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            b = self.temps[src2]
            if type(a) is int and type(b) is int:
                self.temps[dest] = a + b
            elif type(a) is str and type(b) is str:
                self.temps[dest] = a + b
            elif type(a) is float and type(b) is float:
                self.temps[dest] = a + b
            else:
                self.interpreter.error(
                    f"不支持 + : {type(a).__name__} + {type(b).__name__}",
                    None, 'TypeError')

        elif kind == 'sub':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            b = self.temps[src2]
            self.temps[dest] = a - b

        elif kind == 'mul':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            b = self.temps[src2]
            self.temps[dest] = a * b

        elif kind == 'div':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            b = self.temps[src2]
            if b == 0:
                self.interpreter.error("除零错误", None, 'ZeroDivisionError')
            self.temps[dest] = a / b

        elif kind == 'floordiv':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            b = self.temps[src2]
            if b == 0:
                self.interpreter.error("除零错误", None, 'ZeroDivisionError')
            self.temps[dest] = a // b

        elif kind == 'mod':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            b = self.temps[src2]
            if b == 0:
                self.interpreter.error("除零错误", None, 'ZeroDivisionError')
            self.temps[dest] = a % b

        elif kind == 'pow':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] ** self.temps[src2]

        elif kind == 'eq':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] == self.temps[src2]

        elif kind == 'ne':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] != self.temps[src2]

        elif kind == 'lt':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] < self.temps[src2]

        elif kind == 'gt':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] > self.temps[src2]

        elif kind == 'le':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] <= self.temps[src2]

        elif kind == 'ge':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] >= self.temps[src2]

        elif kind == 'bor':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] | self.temps[src2]

        elif kind == 'band':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] & self.temps[src2]

        elif kind == 'xor':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] ^ self.temps[src2]

        elif kind == 'lshift':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] << self.temps[src2]

        elif kind == 'rshift':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] >> self.temps[src2]

        elif kind == 'and':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            if not self.interpreter._truthy(a):
                self.temps[dest] = a
            else:
                self.temps[dest] = self.temps[src2]

        elif kind == 'or':
            _, dest, src1, src2 = op
            a = self.temps[src1]
            if self.interpreter._truthy(a):
                self.temps[dest] = a
            else:
                self.temps[dest] = self.temps[src2]

        elif kind == 'neg':
            _, dest, src = op
            a = self.temps[src]
            if isinstance(a, EclInstance):
                method = a.cls.methods.get('__neg__')
                if method:
                    self.temps[dest] = self.interpreter.call_method_ir(
                        method, a, [], {})
                    return
            self.temps[dest] = -a

        elif kind == 'invert':
            _, dest, src = op
            a = self.temps[src]
            if isinstance(a, EclInstance):
                method = a.cls.methods.get('__invert__')
                if method:
                    self.temps[dest] = self.interpreter.call_method_ir(
                        method, a, [], {})
                    return
            self.temps[dest] = ~a

        elif kind == 'not':
            _, dest, src = op
            self.temps[dest] = not self.interpreter._truthy(self.temps[src])

        # ---------- 控制流 ----------
        elif kind == 'goto':
            _, label = op
            self.pc = self.labels[label]

        elif kind == 'if_goto':
            _, src, label = op
            if self.interpreter._truthy(self.temps[src]):
                self.pc = self.labels[label]

        elif kind == 'if_not_goto':
            _, src, label = op
            if not self.interpreter._truthy(self.temps[src]):
                self.pc = self.labels[label]

        elif kind == 'label':
            pass

        # ---------- 函数 ----------
        elif kind == 'call':
            _, dest, func_src, args, kwargs = op
            func = self.temps[func_src]
            arg_vals = [self.temps[a] for a in args]
            kwarg_vals = {k: self.temps[v] for k, v in kwargs.items()}
            self.temps[dest] = self.interpreter.call_value(
                func, arg_vals, kwarg_vals)

        elif kind == 'return':
            _, src = op
            raise ReturnSignal(self.temps[src])

        elif kind == 'return_none':
            raise ReturnSignal(None)

        elif kind == 'return_null':
            raise ReturnSignal(NULL)

        # ---------- 数据结构 ----------
        elif kind == 'new_list':
            _, dest = op
            self.temps[dest] = []

        elif kind == 'list_append':
            _, dest, src = op
            self.temps[dest].append(self.temps[src])

        elif kind == 'new_dict':
            _, dest = op
            self.temps[dest] = {}

        elif kind == 'dict_set':
            _, dest, key_src, val_src = op
            self.temps[dest][self.temps[key_src]] = self.temps[val_src]

        elif kind == 'new_range':
            _, dest, start, end, inclusive, step = op
            s = int(self.temps[start])
            e = int(self.temps[end])
            st = int(self.temps[step]) if step else 1
            stop = e + (1 if inclusive else 0)
            self.temps[dest] = list(range(s, stop, st))

        elif kind == 'get_item':
            _, dest, obj, idx = op
            try:
                self.temps[dest] = self.temps[obj][self.temps[idx]]
            except (IndexError, KeyError) as e:
                self.interpreter.error(f"下标访问错误: {e}", None, type(e).__name__)

        elif kind == 'set_item':
            _, obj, idx, src = op
            try:
                self.temps[obj][self.temps[idx]] = self.temps[src]
            except (IndexError, KeyError) as e:
                self.interpreter.error(f"下标赋值错误: {e}", None, type(e).__name__)

        elif kind == 'get_attr':
            _, dest, obj, name = op
            self.temps[dest] = self.interpreter.get_attr(self.temps[obj], name)

        elif kind == 'set_attr':
            _, obj, name, src = op
            self.interpreter.set_attr(self.temps[obj], name, self.temps[src])

        # ---------- 定义 ----------
        elif kind == 'func':
            _, name, sub_code, params, varargs, kwargs_name, ret_type, defaults = op
            fn = EclFunctionIR(name, sub_code, params, varargs, kwargs_name,
                               ret_type, self.interpreter, defaults)
            self.scope[name] = Cell(fn)

        elif kind == 'class':
            _, name, bases, methods = op
            cls = EclClassIR(name, bases, methods, self.interpreter)
            self.scope[name] = Cell(cls)

        elif kind == 'new_code':
            _, dest, source = op
            self.temps[dest] = CodeObject(source, self.scope, self.interpreter)

        # ---------- 异常 ----------
        elif kind == 'raise':
            _, src = op
            exc = self.temps[src]
            if isinstance(exc, EclException):
                raise exc
            if hasattr(exc, 'exc_type'):
                msg = getattr(exc, 'message', str(exc))
                raise EclException(exc.exc_type, msg)
            raise EclException('Exception', str(exc))

        # ---------- 结束 ----------
        elif kind == 'halt':
            self.pc = len(self.code)

        else:
            raise EclException('RuntimeError', f"未知指令: {kind}")

# ============================================================================
# Interpreter
# ============================================================================


class Interpreter:
    def __init__(self):
        self.globals = {}
        self._init_builtins()

    def _init_builtins(self):
        self.globals['print'] = Cell(self._builtin_print)
        self.globals['input'] = Cell(self._builtin_input)
        self.globals['type'] = Cell(self._builtin_type)
        self.globals['len'] = Cell(self._builtin_len)
        self.globals['str'] = Cell(self._builtin_str)
        self.globals['int'] = Cell(self._builtin_int)
        self.globals['float'] = Cell(self._builtin_float)
        self.globals['bool'] = Cell(self._builtin_bool)
        self.globals['range'] = Cell(self._builtin_range)
        self.globals['abs'] = Cell(abs)
        self.globals['max'] = Cell(max)
        self.globals['min'] = Cell(min)
        self.globals['sum'] = Cell(sum)
        for ename in ('Exception', 'ValueError', 'TypeError',
                      'IndexError', 'KeyError', 'ZeroDivisionError',
                      'RuntimeError', 'NameError'):
            self.globals[ename] = Cell(self._make_exception_class(ename))

    @staticmethod
    def _make_exception_class(name):
        class _Exc:
            exc_type = name

            def __init__(self, msg=""):
                self.message = str(msg)

            def __repr__(self):
                return f"{name}({self.message!r})"

            def __str__(self):
                return self.message
        return _Exc

    def _builtin_print(self, *args):
        out = []
        for a in args:
            if a is None:
                out.append("none")
            elif a is NULL:
                out.append("null")
            elif isinstance(a, EclInstance):
                method_stmt = a.cls.methods.get('__str__')
                if method_stmt is not None:
                    result = self.call_method_ir(method_stmt, a, [], {})
                    if result is None:
                        out.append("none")
                    elif result is NULL:
                        out.append("null")
                    else:
                        out.append(str(result))
                else:
                    out.append(repr(a))
            else:
                out.append(str(a))
        print(*out)
        return None

    def _builtin_input(self, prompt=""):
        return input(str(prompt))

    def _builtin_type(self, obj):
        if obj is None:
            return 'none'
        if obj is NULL:
            return 'null'
        if isinstance(obj, EclInstance):
            return obj.cls.name
        return type(obj).__name__

    def _builtin_len(self, obj):
        return len(obj)

    def _builtin_str(self, obj):
        if obj is None:
            return "none"
        elif obj is NULL:
            return "null"
        elif isinstance(obj, EclInstance):
            method_stmt = obj.cls.methods.get('__str__')
            if method_stmt is not None:
                result = self.call_method_ir(method_stmt, obj, [], {})
                if result is None:
                    return "none"
                elif result is NULL:
                    return "null"
                else:
                    return str(result)
            return repr(obj)
        return str(obj)

    def _builtin_int(self, obj):
        return int(obj)

    def _builtin_float(self, obj):
        return float(obj)

    def _builtin_bool(self, obj):
        return bool(obj)

    def _builtin_range(self, *args):
        return list(range(*[int(a) for a in args]))

    def error(self, msg, node=None, exc_type='RuntimeError'):
        if node is not None and hasattr(node, 'line'):
            raise EclException(exc_type, msg, line=node.line, col=node.col)
        raise EclException(exc_type, msg)

    @staticmethod
    def _truthy(v):
        if v is NULL:
            return False
        return bool(v)

    def convert_type(self, value, type_name, node=None):
        if type_name is None or type_name == 'any':
            return value
        if value is NULL:
            return NULL
        base = type_name.split('[')[0].strip().split()[0]
        mapping = {
            'int': int, 'float': float, 'double': float,
            'str': str, 'bool': bool,
        }
        if base in mapping:
            try:
                return mapping[base](value)
            except (ValueError, TypeError):
                self.error(f"无法将 {type(value).__name__} 转换为 {type_name}",
                           node, 'TypeError')
        return value

    def apply_binary(self, op, a, b):
        magic = self.try_magic_method(a, b, op)
        if magic is not _NO_MAGIC:
            return magic
        try:
            if op == '+':
                return a + b
            if op == '-':
                return a - b
            if op == '*':
                return a * b
            if op == '/':
                if b == 0:
                    self.error("除零错误", None, 'ZeroDivisionError')
                return a / b
            if op == '//':
                if b == 0:
                    self.error("除零错误", None, 'ZeroDivisionError')
                return a // b
            if op == '%':
                if b == 0:
                    self.error("除零错误", None, 'ZeroDivisionError')
                return a % b
            if op == '**':
                return a ** b
            if op in ('=', '=='):
                return a == b
            if op == '!=':
                return a != b
            if op == '<':
                return a < b
            if op == '>':
                return a > b
            if op == '<=':
                return a <= b
            if op == '>=':
                return a >= b
            if op == '|':
                return a | b
            if op == '&':
                return a & b
            if op == '^':
                return a ^ b
            if op == '<<':
                return a << b
            if op == '>>':
                return a >> b
        except EclException:
            raise
        except TypeError as e:
            self.error(f"类型错误: {e}", None, 'TypeError')
        except ZeroDivisionError as e:
            self.error(f"除零错误: {e}", None, 'ZeroDivisionError')
        except Exception as e:
            self.error(f"运算错误: {e}", None, type(e).__name__)
        self.error(f"未知二元运算符: {op}", None)

    def apply_unary(self, op, a):
        if op == '-':
            if isinstance(a, EclInstance):
                method = a.cls.methods.get('__neg__')
                if method:
                    return self.call_method_ir(method, a, [], {})
            return -a
        if op == '~':
            if isinstance(a, EclInstance):
                method = a.cls.methods.get('__invert__')
                if method:
                    return self.call_method_ir(method, a, [], {})
            return ~a
        if op in ('!', 'not'):
            return not self._truthy(a)
        self.error(f"未知一元运算符: {op}", None)

    def try_magic_method(self, left, right, op):
        method_name = MAGIC_METHODS.get(op)
        if method_name is None:
            return _NO_MAGIC
        if isinstance(left, (EclInstance, EclClassIR)):
            result = self.call_magic(left, method_name, [right])
            if result is not _NO_MAGIC and result is not NULL:
                return result
        if isinstance(right, (EclInstance, EclClassIR)):
            reverse_name = REVERSE_METHODS.get(op)
            if reverse_name is not None:
                result = self.call_magic(right, reverse_name, [left])
                if result is not _NO_MAGIC and result is not NULL:
                    return result
        return _NO_MAGIC

    def call_magic(self, obj, method_name, args):
        if isinstance(obj, EclInstance):
            method_stmt = obj.cls.methods.get(method_name)
            if method_stmt is not None:
                return self.call_method_ir(method_stmt, obj, args, {})
            if method_name in obj.attrs:
                fn = obj.attrs[method_name]
                if callable(fn):
                    return fn(*args)
            return _NO_MAGIC
        if isinstance(obj, EclClassIR):
            method_stmt = obj.methods.get(method_name)
            if method_stmt is not None:
                if len(method_stmt) == 6:
                    code, params, varargs, kwargs, ret, defaults = method_stmt
                else:
                    code, params, varargs, kwargs, ret = method_stmt
                    defaults = {}
                fn = EclFunctionIR(method_name, code, params, varargs,
                                   kwargs, ret, self, defaults)
                return self.call_function_ir(fn, args, {})
            return _NO_MAGIC
        return _NO_MAGIC

    def get_attr(self, obj, name):
        if isinstance(obj, CodeObject):
            if name == 'run':
                return obj.run
            self.error(f"code 对象没有属性 '{name}'", None, 'AttributeError')
        if isinstance(obj, GlobalView):
            if name == 'keys':
                return obj.keys
            if name == 'get':
                return lambda k, default=None: obj.cells[k].value if k in obj.cells else default
            if name == 'has':
                return lambda k: k in obj.cells
            if name in obj.cells:
                return obj.cells[name].value
            self.error(f"global 对象没有变量 '{name}'", None, 'AttributeError')
        if isinstance(obj, EclInstance):
            if name in obj.attrs:
                return obj.attrs[name]
            if name in obj.cls.methods:
                method_stmt = obj.cls.methods[name]
                return lambda *a, **kw: self.call_method_ir(method_stmt, obj, a, kw)
            self.error(f"对象 '{obj.cls.name}' 没有属性 '{name}'",
                       None, 'AttributeError')
        if isinstance(obj, EclClassIR):
            if name in obj.methods:
                method_stmt = obj.methods[name]
                if len(method_stmt) == 6:
                    code, params, varargs, kwargs, ret, defaults = method_stmt
                else:
                    code, params, varargs, kwargs, ret = method_stmt
                    defaults = {}
                fn = EclFunctionIR(name, code, params, varargs,
                                   kwargs, ret, self, defaults)
                return lambda *a, **kw: self.call_function_ir(fn, a, kw)
            self.error(f"类 '{obj.name}' 没有属性 '{name}'", None, 'AttributeError')
        try:
            return getattr(obj, name)
        except AttributeError:
            self.error(f"对象没有属性 '{name}'", None, 'AttributeError')

    def set_attr(self, obj, name, val):
        if isinstance(obj, GlobalView):
            obj.set(name, val)
            return
        if isinstance(obj, EclInstance):
            obj.attrs[name] = val
            return
        try:
            setattr(obj, name, val)
        except AttributeError:
            self.error(f"对象不支持属性赋值: {name}", None, 'AttributeError')

    def call_value(self, func, args, kwargs):
        if isinstance(func, EclInstance):
            method = func.cls.methods.get('__call__')
            if method is not None:
                return self.call_method_ir(method, func, args, kwargs)
            self.error("对象不可调用（没有 __call__）", None, 'TypeError')
        if not callable(func):
            self.error(f"对象不可调用: {func!r}", None, 'TypeError')
        try:
            return func(*args, **kwargs)
        except EclException:
            raise
        except TypeError as e:
            self.error(f"调用参数错误: {e}", None, 'TypeError')
        except Exception as e:
            self.error(f"调用错误: {e}", None, type(e).__name__)

    def call_function_ir(self, fn, args, kwargs, self_instance=None):
        scope = {}
        if self_instance is not None:
            scope['self'] = Cell(self_instance)

        params = fn.params
        for i, p in enumerate(params):
            pname = p['name']
            if i < len(args):
                val = args[i]
            elif pname in kwargs:
                val = kwargs[pname]
            elif pname in fn.defaults:
                val = fn.defaults[pname]
            else:
                self.error(f"函数 '{fn.name}' 缺少参数 '{pname}'", None, 'TypeError')
            if p.get('type'):
                val = self.convert_type(val, p['type'])
            scope[pname] = Cell(val)

        vm = VM(fn.code, [], scope, self)
        try:
            vm.run()
        except ReturnSignal as r:
            ret = r.value
        else:
            ret = NULL

        if fn.ret_type and ret is not None and ret is not NULL:
            ret = self.convert_type(ret, fn.ret_type)
        return ret

    def call_method_ir(self, method_stmt, instance, args, kwargs):
        if isinstance(method_stmt, tuple):
            if len(method_stmt) == 6:
                code, params, varargs, kwargs_name, ret, defaults = method_stmt
            else:
                code, params, varargs, kwargs_name, ret = method_stmt
                defaults = {}
            fn = EclFunctionIR('__method__', code, params, varargs,
                               kwargs_name, ret, self, defaults)
            return self.call_function_ir(fn, (instance,) + tuple(args), kwargs)
        self.error("call_method_ir 不支持 AST 版方法", None)

    def interpret(self, program):
        compiler = Compiler()
        code, exception_table = compiler.compile_program(program)
        print(code)
        return
        vm = VM(code, exception_table, self.globals, self)
        try:
            vm.run()
        except ReturnSignal:
            pass
# ============================================================================
# 顶层入口
# ============================================================================


def run_ecl(code, verbose=False, without_check=False):
    """完整执行 ECL 代码：词法 -> 语法 -> 类型检查 -> 执行"""
    try:
        tokens = split_token(code)
    except LexerError as e:
        print(f"词法错误: {e}", file=sys.stderr)
        return None

    try:
        parser = Parser(tokens)
        program = parser.parse()
    except ParseError as e:
        import traceback
        traceback.print_exc()
        print(f"语法错误: {e}", file=sys.stderr)
        return None

    try:
        checker = Checker()
        if not without_check:
            checker.check(program)
    except CheckError as e:
        print(f"静态检查错误: {e}", file=sys.stderr)
        return None

    interp = Interpreter()
    try:
        interp.interpret(program)
    except EclException as e:
        print(f"运行时错误: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"内部错误: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    if verbose:
        print("执行完成", file=sys.stderr)
    return interp


# ============================================================================
# 测试
# ============================================================================

if __name__ == '__main__':
    import argparse
    import pathlib

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--input',
        type=pathlib.Path,
        help='输入文件路径（例如 code.ecl）'  # 这里就是 help
    )
    parser.add_argument(
        '--without-check',
        action='store_true',
        help='是否静态检查'  # 或更准确地写：跳过静态检查
    )
    args = parser.parse_args()
    if args.input:
        with args.input.open('r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = ""
    run_ecl(content, without_check=args.without_check)
