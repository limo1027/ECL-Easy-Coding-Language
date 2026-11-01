#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECL (Easy Control Language) 解释器完整实现
包含：词法分析、语法解析、类型检查、解释执行
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Union
import sys

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
        value = []
        while i < n:
            ch = current()
            if ch == '\\':
                advance()
                if i >= n:
                    raise LexerError("反斜杠后缺少转义字符", line, col)
                esc = current()
                mapping = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\',
                           '"': '"', "'": "'", '0': '\0'}
                value.append(mapping.get(esc, '\\' + esc))
                advance()
            elif ch == quote:
                advance()
                return ''.join(value), start_line, start_col
            elif ch == '\n':
                raise LexerError("字符串未闭合（遇到换行）", start_line, start_col)
            else:
                value.append(ch)
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

        if ch in '"\'':
            value, sl, sc = read_string(ch)
            tokens.append(Token('STRING', value, sl, sc))
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
        # code 自己的 globals（独立作用域）
        code_globals = {}
        # 父作用域：定义时的 scope（闭包）
        parent_scope = dict(self.scope)
        # 合并父作用域到 code_globals（浅拷贝，Cell 共享）
        for k, v in parent_scope.items():
            code_globals[k] = v
        # 再合并 interpreter.globals（如果 scope 里没有）
        for k, v in self.interpreter.globals.items():
            if k not in code_globals:
                code_globals[k] = v

        self.interpreter.exec_block(stmts, code_globals)

        # 返回新增的变量（排除父作用域和全局的）
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
                     'none': None, 'null': None}[tok.value]
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
        self.error(f"意外的 token: {tok.type} {tok.value!r}", tok)

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

class CheckError(Exception):
    def __init__(self, message, line=0, col=0):
        self.message = message
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {message}")
        else:
            super().__init__(message)


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
        self.cause = cause
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {exc_type}: {message}")
        else:
            super().__init__(f"{exc_type}: {message}")


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


class GotoSignal(Exception):
    def __init__(self, label):
        self.label = label


class EclFunction:
    def __init__(self, stmt, closure, interpreter):
        self.stmt = stmt
        self.closure = closure
        self.interpreter = interpreter

    def __call__(self, *args, **kwargs):
        return self.interpreter.call_function(self, args, kwargs)


class EclClass:
    def __init__(self, name, stmt, closure, interpreter):
        self.name = name
        self.stmt = stmt
        self.closure = closure
        self.interpreter = interpreter
        self.methods = {}
        self.attrs = {}
        # 先提取方法
        for s in stmt.body:
            if isinstance(s, FuncDefStmt):
                self.methods[s.name] = s

    def __call__(self, *args, **kwargs):
        instance = EclInstance(self)
        instance.attrs['__class__'] = self
        init = self.methods.get('__init__')
        if init:
            self.interpreter.call_method(init, instance, args, kwargs)
        return instance

    def __repr__(self):
        return f"<class {self.name}>"


class EclInstance:
    def __init__(self, cls):
        self.cls = cls
        self.attrs = {}

    def __repr__(self):
        return f"<{self.cls.name} object>"


class ConstChangingError(EclException):
    pass


class Interpreter:
    def __init__(self):
        self.globals = {}
        self.functions = {}
        self.classes = {}
        self._in_function = False
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
        # 异常类
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
        print(*[('none' if a is None else a) for a in args])
        return None

    def _builtin_input(self, prompt=""):
        return input(str(prompt))

    def _builtin_type(self, obj):
        return type(obj).__name__

    def _builtin_len(self, obj):
        return len(obj)

    def _builtin_str(self, obj):
        return str(obj)

    def _builtin_int(self, obj):
        return int(obj)

    def _builtin_float(self, obj):
        return float(obj)

    def _builtin_bool(self, obj):
        return bool(obj)

    def _builtin_range(self, *args):
        return list(range(*[int(a) for a in args]))

    # ---------- 错误定位 ----------

    def error(self, msg, node=None, exc_type='RuntimeError'):
        if node is not None and hasattr(node, 'line') and hasattr(node, 'col'):
            raise EclException(exc_type, msg, line=node.line, col=node.col)
        raise EclException(exc_type, msg)

    # ---------- 作用域 ----------
    def lookup_cell(self, name, node=None, scope_stack=None, for_write=False):
        if scope_stack is None:
            scope_stack = [self.globals]
        for scope in scope_stack:
            if name in scope:
                cell = scope[name]
                if for_write and cell.is_const:
                    self.error(
                        f"不能重新赋值常量 '{name}'",
                        node, 'ConstChangingError')
                return cell
        self.error(f"未定义的变量: '{name}'", node, 'NameError')

    def lookup_value(self, name, node=None, scope_stack=None):
        cell = self.lookup_cell(name, node, scope_stack)
        return cell.value

    # ---------- 执行入口 ----------

    def interpret(self, program, scope=None):
        if scope is None:
            scope = self.globals
        try:
            self.exec_block(program.body, scope)
        except ReturnSignal:
            pass

    def exec_block(self, stmts, scope, parent_labels=None):
        labels = dict(parent_labels) if parent_labels else {}
        local_labels = set()
        for i, s in enumerate(stmts):
            if isinstance(s, LabelStmt):
                labels[s.name] = i
                local_labels.add(s.name)

        pc = 0
        while pc < len(stmts):
            stmt = stmts[pc]
            try:
                result_pc = self.exec_statement(stmt, scope, labels, pc)
                if isinstance(result_pc, int) and result_pc != pc:
                    pc = result_pc
                    continue
            except GotoSignal as g:
                if g.label in local_labels:
                    pc = labels[g.label] + 1
                    continue
                # 不在当前 block，向上抛
                raise
            pc += 1

    def exec_statement(self, stmt, scope, labels, pc):
        try:
            return self._exec_statement(stmt, scope, labels, pc)
        except EclException:
            raise
        except ReturnSignal:
            raise
        except BreakSignal:
            raise
        except ContinueSignal:
            raise
        except GotoSignal:
            raise
        except Exception as e:
            self.error(str(e), stmt, type(e).__name__)

    def _exec_statement(self, stmt, scope, labels, pc):
        if isinstance(stmt, ExprStmt):
            self.eval_expr(stmt.expr, scope)
            return None

        if isinstance(stmt, DefineStmt):
            return self.exec_define(stmt, scope)

        if isinstance(stmt, FuncDefStmt):
            fn = EclFunction(stmt, scope, self)
            scope[stmt.name] = Cell(fn)
            return None

        if isinstance(stmt, ClassDefStmt):
            cls = EclClass(stmt.name, stmt, scope, self)
            scope[stmt.name] = Cell(cls)
            return None

        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                val = self.eval_expr(stmt.value, scope)
            else:
                val = None
            raise ReturnSignal(val)

        if isinstance(stmt, IfStmt):
            if self._truthy(self.eval_expr(stmt.condition, scope)):
                self.exec_block(stmt.body, scope)
                return None
            for ec, eb in stmt.elifs:
                if self._truthy(self.eval_expr(ec, scope)):
                    self.exec_block(eb, scope)
                    return None
            if stmt.else_body:
                self.exec_block(stmt.else_body, scope)
            return None

        if isinstance(stmt, WhileStmt):
            while self._truthy(self.eval_expr(stmt.condition, scope)):
                try:
                    self.exec_block(stmt.body, scope)
                except BreakSignal:
                    break
                except ContinueSignal:
                    continue
            return None

        if isinstance(stmt, ForStmt):
            return self.exec_for(stmt, scope)

        if isinstance(stmt, BreakStmt):
            raise BreakSignal()

        if isinstance(stmt, ContinueStmt):
            raise ContinueSignal()

        if isinstance(stmt, GotoStmt):
            raise GotoSignal(stmt.label)

        if isinstance(stmt, LabelStmt):
            return None

        if isinstance(stmt, RaiseStmt):
            exc_val = self.eval_expr(stmt.exception, scope)
            if hasattr(exc_val, 'exc_type'):
                exc_type = exc_val.exc_type
                msg = getattr(exc_val, 'message', str(exc_val))
            elif isinstance(exc_val, dict):
                exc_type = exc_val.get('__class__', 'Exception')
                msg = exc_val.get('message', str(exc_val))
            else:
                exc_type = type(exc_val).__name__
                msg = str(exc_val)
            raise EclException(exc_type, msg, line=stmt.line, col=stmt.col)

        if isinstance(stmt, TryStmt):
            return self.exec_try(stmt, scope)

        if isinstance(stmt, (ImportStmt, WithStmt, MatchStmt, UsingStmt,
                             DecoratorStmt)):
            self.error(f"语句 {type(stmt).__name__} 尚未实现",
                       stmt, 'NotImplementedError')

        self.error(f"未知语句类型: {type(stmt).__name__}", stmt)

    def exec_define(self, stmt, scope):
        if stmt.is_ref:
            if stmt.value is None:
                scope[stmt.name] = Cell(None, is_const=stmt.is_const)
                return None
            if isinstance(stmt.value, Variable):
                cell = self.lookup_cell(
                    stmt.value.name, stmt.value, [scope, self.globals])
                scope[stmt.name] = cell
            else:
                self.error("ref 必须绑定到变量", stmt)
            return None

        if stmt.value is None:
            scope[stmt.name] = Cell(
                None, is_const=stmt.is_const)   # ← 加 is_const
            return None

        val = self.eval_expr(stmt.value, scope)
        if stmt.type_name:
            val = self.convert_type(val, stmt.type_name, stmt)
        scope[stmt.name] = Cell(
            val, is_const=stmt.is_const)        # ← 加 is_const
        return None

    def exec_for(self, stmt, scope):
        if stmt.count is not None:
            n = int(self.eval_expr(stmt.count, scope))
            iterable = range(n)
            var = None
        elif stmt.range_expr is not None:
            r = stmt.range_expr
            start = int(self.eval_expr(r.start, scope))
            end = int(self.eval_expr(r.end, scope))
            step = int(self.eval_expr(r.step, scope)) if r.step else 1
            stop = end + (1 if r.inclusive else 0)
            iterable = range(start, stop, step)
            var = stmt.variable
        else:
            iterable = self.eval_expr(stmt.iterable, scope)
            var = stmt.variable

        for item in iterable:
            if var:
                scope[var] = Cell(item)
            try:
                self.exec_block(stmt.body, scope)
            except BreakSignal:
                break
            except ContinueSignal:
                continue
        return None

    def exec_try(self, stmt, scope):
        try:
            self.exec_block(stmt.body, scope)
        except EclException as e:
            handled = False
            for ec in stmt.excepts:
                et = ec['type']
                if et is None or et == e.exc_type or et == 'Exception':
                    if ec['name']:
                        scope[ec['name']] = Cell(e)
                    self.exec_block(ec['body'], scope)
                    handled = True
                    break
            if not handled:
                raise
        else:
            if stmt.else_body:
                self.exec_block(stmt.else_body, scope)
        finally:
            if stmt.finally_body:
                self.exec_block(stmt.finally_body, scope)

    def call_function(self, fn, args, kwargs, self_instance=None):
        stmt = fn.stmt
        local = dict(fn.closure)
        if self_instance is not None:
            local['self'] = Cell(self_instance)

        # 绑定参数
        params = stmt.params
        defaults = stmt.defaults
        for i, p in enumerate(params):
            pname = p['name']
            if i < len(args):
                val = args[i]
            elif pname in kwargs:
                val = kwargs[pname]
            elif pname in defaults:
                val = self.eval_expr(defaults[pname], fn.closure)
            else:
                self.error(f"函数 '{stmt.name}' 缺少参数 '{pname}'",
                           stmt, 'TypeError')
            if p.get('type'):
                val = self.convert_type(val, p['type'], stmt)
            local[pname] = Cell(val)

        if stmt.varargs:
            rest = list(args[len(params):])
            local[stmt.varargs] = Cell(rest)
        if stmt.kwargs:
            extra = {k: v for k, v in kwargs.items() if k not in
                     {p['name'] for p in params}}
            local[stmt.kwargs] = Cell(extra)

        try:
            self.exec_block(stmt.body, local)
        except ReturnSignal as r:
            ret = r.value
        else:
            ret = None

        if stmt.return_type and ret is not None:
            ret = self.convert_type(ret, stmt.return_type, stmt)
        return ret

    def call_method(self, method_stmt, instance, args, kwargs):
        fn = EclFunction(method_stmt, {**self.globals}, self)
        new_args = (instance,) + tuple(args)
        return self.call_function(fn, new_args, kwargs)

    def call_function_with_self(self, fn, args, kwargs, instance):
        stmt = fn.stmt
        local = dict(fn.closure)
        local['self'] = Cell(instance)

        params = stmt.params
        defaults = stmt.defaults
        for i, p in enumerate(params):
            pname = p['name']
            if i < len(args):
                val = args[i]
            elif pname in kwargs:
                val = kwargs[pname]
            elif pname in defaults:
                val = self.eval_expr(defaults[pname], fn.closure)
            else:
                self.error(f"函数 '{stmt.name}' 缺少参数 '{pname}'",
                           stmt, 'TypeError')
            if p.get('type'):
                val = self.convert_type(val, p['type'], stmt)
            local[pname] = Cell(val)

        if stmt.varargs:
            rest = list(args[len(params):])
            local[stmt.varargs] = Cell(rest)
        if stmt.kwargs:
            extra = {k: v for k, v in kwargs.items() if k not in
                     {p['name'] for p in params}}
            local[stmt.kwargs] = Cell(extra)

        try:
            self.exec_block(stmt.body, local)
        except ReturnSignal as r:
            ret = r.value
        else:
            ret = None

        if stmt.return_type and ret is not None:
            ret = self.convert_type(ret, stmt.return_type, stmt)
        return ret

    def convert_type(self, value, type_name, node=None):
        if type_name is None or type_name == 'any':
            return value
        base = type_name.split('[')[0].strip().split()[0]
        mapping = {
            'int': int,
            'float': float,
            'double': float,
            'str': str,
            'bool': bool,
        }
        if base in mapping:
            try:
                return mapping[base](value)
            except (ValueError, TypeError):
                self.error(f"无法将 {type(value).__name__} 转换为 {type_name}",
                           node, 'TypeError')
        return value

    @staticmethod
    def _truthy(v):
        return bool(v)

    # ---------- 表达式求值 ----------

    def eval_expr(self, expr, scope):
        try:
            return self._eval_expr(expr, scope)
        except EclException:
            raise
        except Exception as e:
            self.error(str(e), expr, type(e).__name__)

    def _eval_expr(self, expr, scope):
        if isinstance(expr, CodeLiteral):
            return CodeObject(expr.source, scope, self,
                              line=expr.line, col=expr.col)
        if isinstance(expr, Literal):
            return expr.value

        if isinstance(expr, Variable):
            return self.lookup_value(expr.name, expr, [scope, self.globals])

        if isinstance(expr, Binary):
            return self.eval_binary(expr, scope)

        if isinstance(expr, Unary):
            v = self.eval_expr(expr.right, scope)
            if expr.op == '-':
                return -v
            if expr.op == '~':
                return ~v
            if expr.op == '!':
                return not v
            if expr.op == 'not':
                return not v
            self.error(f"未知一元运算符: {expr.op}", expr)

        if isinstance(expr, Assign):
            val = self.eval_expr(expr.value, scope)
            target = expr.name

            if isinstance(target, Variable):
                cell = self.lookup_cell(
                    target.name, expr, [scope, self.globals], for_write=True)
                cell.value = val

            elif isinstance(target, Attribute):
                obj = self.eval_expr(target.obj, scope)
                if isinstance(target, Attribute):
                    obj = self.eval_expr(target.obj, scope)
                    if isinstance(target.obj, Variable) and target.obj.name == 'global':
                        # global.x <- val
                        cell = self.lookup_cell(
                            target.attr, expr, [self.globals])
                        cell.value = val
                    if isinstance(obj, GlobalView):
                        obj.set(target.attr, val)
                    elif isinstance(obj, EclInstance):
                        obj.attrs[target.attr] = val
                    else:
                        try:
                            setattr(obj, target.attr, val)
                        except AttributeError:
                            self.error(
                                f"对象不支持属性赋值: {target.attr}", expr, 'AttributeError')
                if isinstance(obj, EclInstance):
                    obj.attrs[target.attr] = val
                else:
                    try:
                        setattr(obj, target.attr, val)
                    except AttributeError:
                        self.error(
                            f"对象不支持属性赋值: {target.attr}", expr, 'AttributeError')
            return val

        if isinstance(expr, Swap):
            lc = self.lookup_cell(
                expr.left, expr, [scope, self.globals], for_write=True)
            rc = self.lookup_cell(
                expr.right, expr, [scope, self.globals], for_write=True)
            lc.value, rc.value = rc.value, lc.value
            return None

        if isinstance(expr, Call):
            return self.eval_call(expr, scope)

        if isinstance(expr, Attribute):
            return self.eval_attribute(expr, scope)

        if isinstance(expr, IfExpr):
            if self._truthy(self.eval_expr(expr.condition, scope)):
                return self.eval_expr(expr.then_expr, scope)
            return self.eval_expr(expr.else_expr, scope)

        if isinstance(expr, ListExpr):
            return [self.eval_expr(e, scope) for e in expr.elements]

        if isinstance(expr, DictExpr):
            return {self.eval_expr(k, scope): self.eval_expr(v, scope)
                    for k, v in expr.items}

        if isinstance(expr, Subscript):
            obj = self.eval_expr(expr.obj, scope)
            idx = self.eval_expr(expr.index, scope)
            try:
                return obj[idx]
            except (IndexError, KeyError) as e:
                self.error(f"下标访问错误: {e}", expr, type(e).__name__)
            except TypeError as e:
                self.error(f"类型不支持下标访问: {e}", expr, 'TypeError')

        if isinstance(expr, RangeExpr):
            start = int(self.eval_expr(expr.start, scope))
            end = int(self.eval_expr(expr.end, scope))
            step = int(self.eval_expr(expr.step, scope)) if expr.step else 1
            stop = end + (1 if expr.inclusive else 0)
            return list(range(start, stop, step))

        self.error(f"未知表达式类型: {type(expr).__name__}", expr)

    def eval_binary(self, expr, scope):
        op = expr.op

        # 短路求值
        if op == 'and':
            left = self.eval_expr(expr.left, scope)
            if not self._truthy(left):
                return left
            return self.eval_expr(expr.right, scope)
        if op == 'or':
            left = self.eval_expr(expr.left, scope)
            if self._truthy(left):
                return left
            return self.eval_expr(expr.right, scope)

        left = self.eval_expr(expr.left, scope)
        right = self.eval_expr(expr.right, scope)

        try:
            if op == '+':
                return left + right
            if op == '-':
                return left - right
            if op == '*':
                return left * right
            if op == '/':
                if right == 0:
                    self.error("除零错误", expr, 'ZeroDivisionError')
                return left / right
            if op == '//':
                if right == 0:
                    self.error("除零错误", expr, 'ZeroDivisionError')
                return left // right
            if op == '%':
                if right == 0:
                    self.error("除零错误", expr, 'ZeroDivisionError')
                return left % right
            if op == '**':
                return left ** right
            if op in ('=', '=='):
                return left == right
            if op == '!=':
                return left != right
            if op == '<':
                return left < right
            if op == '>':
                return left > right
            if op == '<=':
                return left <= right
            if op == '>=':
                return left >= right
            if op == '|':
                return left | right
            if op == '&':
                return left & right
            if op == '^':
                return left ^ right
            if op == '<<':
                return left << right
            if op == '>>':
                return left >> right
        except EclException:
            raise                      # ★ 关键：不要被下面的 except Exception 吞掉
        except TypeError as e:
            self.error(f"类型错误: {e}", expr, 'TypeError')
        except ZeroDivisionError as e:
            self.error(f"除零错误: {e}", expr, 'ZeroDivisionError')
        except Exception as e:
            self.error(f"运算错误: {e}", expr, type(e).__name__)

        self.error(f"未知二元运算符: {op}", expr)

    def eval_call(self, expr, scope):
        func = self.eval_expr(expr.func, scope)
        args = [self.eval_expr(a, scope) for a in expr.args]
        kwargs = {k: self.eval_expr(v, scope) for k, v in expr.kwargs}

        if not callable(func):
            self.error(f"对象不可调用: {func!r}", expr, 'TypeError')

        try:
            return func(*args, **kwargs)
        except EclException:
            raise
        except TypeError as e:
            self.error(f"调用参数错误: {e}", expr, 'TypeError')
        except Exception as e:
            self.error(f"调用错误: {e}", expr, type(e).__name__)

    def eval_attribute(self, expr, scope):
        obj = self.eval_expr(expr.obj, scope)
        if isinstance(obj, CodeObject):
            if expr.attr == 'run':
                return obj.run
            self.error(f"code 对象没有属性 '{expr.attr}'", expr, 'AttributeError')
        if isinstance(expr.obj, Variable) and expr.obj.name == 'global':
            # 读取 global.x
            cell = self.lookup_cell(expr.attr, expr, [self.globals])
            return cell.value
        if isinstance(obj, GlobalView):
            if expr.attr == 'keys':
                return obj.keys
            if expr.attr == 'get':
                return lambda name, default=None: obj.cells[name].value if name in obj.cells else default
            if expr.attr == 'has':
                return lambda name: name in obj.cells
            if expr.attr in obj.cells:
                return obj.cells[expr.attr].value
            self.error(f"global 对象没有变量 '{expr.attr}'", expr, 'AttributeError')
        if isinstance(obj, EclInstance):
            if expr.attr in obj.attrs:
                return obj.attrs[expr.attr]
            if expr.attr in obj.cls.methods:
                method_stmt = obj.cls.methods[expr.attr]
                return lambda *a, **kw: self.call_method(method_stmt, obj, a, kw)
            self.error(f"对象 '{obj.cls.name}' 没有属性 '{expr.attr}'",
                       expr, 'AttributeError')

        if isinstance(obj, EclClass):
            if expr.attr in obj.methods:
                method_stmt = obj.methods[expr.attr]
                return lambda *a, **kw: self.call_function(
                    EclFunction(method_stmt, {**self.globals}, self), a, kw)
            self.error(f"类 '{obj.name}' 没有属性 '{expr.attr}'",
                       expr, 'AttributeError')

        try:
            return getattr(obj, expr.attr)
        except AttributeError:
            self.error(f"对象没有属性 '{expr.attr}'", expr, 'AttributeError')


# ============================================================================
# 顶层入口
# ============================================================================
def run_ecl(code, verbose=False):
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
        # checker.check(program)
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
    args = parser.parse_args()
    if args.input:
        with args.input.open('r', encoding='utf-8') as f:
            content = f.read()
    run_ecl(content)
