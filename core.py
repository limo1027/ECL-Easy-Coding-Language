from dataclasses import dataclass
from typing import List, Optional, Any, Union
import sys


class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type, value, line, col):
        self.type = type
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type}, {repr(self.value)}, {self.line}, {self.col})"


class LexerError(Exception):
    def __init__(self, message, line, col):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"[行 {line}, 列 {col}] {message}")


# 基类不作为 dataclass，仅作为类型标记
class Expr:
    pass


class Stmt:
    pass


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
    name: Union[str, 'Attribute']
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
class SetExpr(Expr):
    elements: List[Expr]
    line: int = 0
    col: int = 0


@dataclass
class TupleExpr(Expr):
    elements: List[Expr]
    line: int = 0
    col: int = 0


@dataclass
class RangeExpr(Expr):
    start: Expr
    end: Expr
    step: Optional[Expr]
    inclusive: bool
    line: int = 0
    col: int = 0


@dataclass
class CodeBlock(Expr):
    body: List['Stmt']
    line: int = 0
    col: int = 0


@dataclass
class LambdaExpr(Expr):
    params: List[str]
    body: Expr
    line: int = 0
    col: int = 0


@dataclass
class ExprStmt(Stmt):
    expr: Expr
    line: int = 0
    col: int = 0


@dataclass
class Subscript(Expr):
    obj: Expr
    index: Expr
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
    # [{'name': str, 'type': Optional[str], 'default': Optional[Expr]}]
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
class BreakStmt(Stmt):
    line: int = 0
    col: int = 0


@dataclass
class ContinueStmt(Stmt):
    line: int = 0
    col: int = 0


@dataclass
class ReturnStmt(Stmt):
    value: Optional[Expr]
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
    name: str
    body: List[Stmt]
    line: int = 0
    col: int = 0


@dataclass
class Program:
    body: List[Stmt]


def split_token(code):
    tokens = []
    i = 0
    n = len(code)
    line = 1
    col = 1

    keywords = {
        'def', 'end', 'if', 'elif', 'else', 'for', 'while', 'continue',
        'break', 'return', 'class', 'import', 'from', 'as', 'try', 'except',
        'finally', 'raise', 'global', 'last', 'using', 'ref', 'define',
        'with', 'match', 'case', 'goto', 'label', 'public', 'private',
        'const', 'True', 'False', 'null', 'none', 'any', 'in',
    }

    operators = {
        '**=', '//=', '..=', '+=', '-=', '*=', '/=', '%=', '**',
        '//', '..', '==', '!=', '<=', '>=', '->', '<-', '<->',
        '+', '-', '*', '/', '%', '=', '<', '>', '!',
        '|', '&', '^', '~', '<<', '>>',
        '(', ')', '[', ']', '{', '}', '.', ',', ':', ';', '@',
    }

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
        while i < n and current() != '\n':
            advance()
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
                ch = current()
                if ch == 'n':
                    value.append('\n')
                elif ch == 't':
                    value.append('\t')
                elif ch == 'r':
                    value.append('\r')
                elif ch == '"' or ch == "'" or ch == '\\':
                    value.append(ch)
                else:
                    value.append('\\' + ch)
                advance()
            elif ch == quote:
                advance()
                return ''.join(value), start_line, start_col
            else:
                value.append(ch)
                advance()
        raise LexerError("字符串未闭合", start_line, start_col)

    def read_number():
        start_i, start_col = i, col
        is_float = False
        is_double = False
        is_binary = is_octal = is_hex = False

        if current() == '0':
            if peek() in ('b', 'B'):
                is_binary = True
                advance()
                advance()
            elif peek() in ('o', 'O'):
                is_octal = True
                advance()
                advance()
            elif peek() in ('x', 'X'):
                is_hex = True
                advance()
                advance()

        while i < n:
            ch = current()
            if is_binary:
                if ch in '01_':
                    advance()
                else:
                    break
            elif is_octal:
                if ch in '01234567_':
                    advance()
                else:
                    break
            elif is_hex:
                if ch in '0123456789abcdefABCDEF_':
                    advance()
                else:
                    break
            else:
                if ch.isdigit() or ch == '_':
                    advance()
                elif ch == '.' and not is_float and peek().isdigit():
                    is_float = True
                    advance()
                elif ch in 'eE':
                    is_float = True
                    advance()
                    if current() in '+-':
                        advance()
                elif ch in 'dD':
                    is_double = True
                    is_float = True
                    advance()
                    break
                else:
                    break

        raw = code[start_i:i].replace('_', '')
        if is_binary:
            return ('INT', int(raw[2:], 2), start_col)
        elif is_octal:
            return ('INT', int(raw[2:], 8), start_col)
        elif is_hex:
            return ('INT', int(raw[2:], 16), start_col)
        elif is_float:
            if is_double:
                clean = raw.rstrip('dD')
                return ('DOUBLE', float(clean), start_col)
            return ('FLOAT', float(raw), start_col)
        else:
            return ('INT', int(raw), start_col)

    def read_identifier():
        start_i, start_col = i, col
        while i < n and (current().isalnum() or current() == '_'):
            advance()
        value = code[start_i:i]
        if value in keywords:
            return ('KEYWORD', value, start_col)
        return ('IDENTIFIER', value, start_col)

    while i < n:
        ch = current()

        if ch == '\t':
            advance()
            col += 3
            continue
        if ch == " ":
            advance()
            continue
        if ch == '\n':
            advance_line()
            continue
        if ch == '\r':
            advance()
            continue

        if ch == '#':
            advance_line()
            continue

        if ch == '/' and peek() == '/' and peek(2) == '/':
            advance_line()
            continue

        if ch == '/' and peek() == '*':
            advance()
            advance()
            while i < n:
                if current() == '*' and peek() == '/':
                    advance()
                    advance()
                    break
                if current() == '\n':
                    advance_line()
                    line += 1
                else:
                    advance()
            continue

        if ch in "\"'":
            value, start_line, start_col = read_string(ch)
            tokens.append(Token('STRING', value, start_line, start_col))
            continue

        if ch.isdigit() or (ch == '.' and peek().isdigit()):
            typ, value, start_col = read_number()
            tokens.append(Token(typ, value, line, start_col))
            continue

        if ch.isalpha() or ch == '_':
            typ, value, start_col = read_identifier()
            tokens.append(Token(typ, value, line, start_col))
            continue

        matched = False
        for op in sorted(operators, key=len, reverse=True):
            if code[i:i+len(op)] == op:
                tokens.append(Token('SYMBOL', op, line, col))
                for _ in range(len(op)):
                    advance()
                matched = True
                break
        if matched:
            continue

        raise LexerError(f"未知字符: '{ch}'", line, col)

    tokens.append(Token('EOF', 'EOF', line, col))
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.n = len(tokens)

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
        if tok:
            raise SyntaxError(f"[行 {tok.line}, 列 {tok.col}] {msg}")
        else:
            raise SyntaxError(msg)

    def expect(self, type_, value=None):
        tok = self.current()
        if not tok or tok.type != type_ or (value is not None and tok.value != value):
            self.error(f"期望 '{value}'", tok)
        return self.advance()

    def match(self, type_, value=None):
        tok = self.current()
        return tok and tok.type == type_ and (value is None or tok.value == value)

    def parse(self):
        stmts = []
        while not self.match('EOF'):
            stmt = self.parse_statement()
            if stmt:
                stmts.append(stmt)
        return Program(stmts)

    def parse_statement(self):
        tok = self.current()
        types = {'int', 'str', 'float', 'double', 'bool', 'boolean', 'list',
                 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'}

        if not tok:
            return None

        if tok.type == 'KEYWORD' and tok.value == 'end':
            return None

        # ---- 类型声明 ----
        if tok.value in types:
            base_type = self.advance().value
            type_params = []
            if self.match('SYMBOL', '['):
                self.advance()
                if self.match('INT'):
                    param = self.advance().value
                elif self.match('TYPE'):
                    param = self.advance().value
                else:
                    param = self.parse_expr()
                type_params.append(param)
                self.expect('SYMBOL', ']')

            elem_type = None
            builtin_types = {'int', 'str', 'float', 'double', 'bool', 'boolean',
                             'list', 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'}
            tok2 = self.current()
            if tok2.type == 'TYPE' or (tok2.type == 'IDENTIFIER' and tok2.value in builtin_types):
                elem_type = self.advance().value

            name = self.expect('IDENTIFIER')
            if self.match('SYMBOL', '<-'):
                self.advance()
                value = self.parse_expr()
            else:
                value = None

            full_type = base_type
            for p in type_params:
                full_type += f'[{p}]'
            if elem_type:
                full_type += ' ' + elem_type

            return DefineStmt(name.value, full_type, value, is_ref=False, is_const=False,
                              line=tok.line, col=tok.col)

        # ---- 关键字语句 ----
        if tok.value == 'if':
            return self.parse_if()
        if tok.value == 'for':
            return self.parse_for()
        if tok.value == 'while':
            return self.parse_while()
        if tok.value == 'def':
            return self.parse_function()
        if tok.value == 'class':
            return self.parse_class()
        if tok.value == 'return':
            self.advance()
            val = self.parse_expr() if not self.match('SYMBOL', ':') else None
            return ReturnStmt(val, line=tok.line, col=tok.col)
        if tok.value == 'break':
            self.advance()
            return BreakStmt(line=tok.line, col=tok.col)
        if tok.value == 'continue':
            self.advance()
            return ContinueStmt(line=tok.line, col=tok.col)
        if tok.value == 'goto':
            self.advance()
            label = self.expect('IDENTIFIER')
            return GotoStmt(label.value, line=tok.line, col=tok.col)
        if tok.value == 'label':
            self.advance()
            name = self.expect('IDENTIFIER')
            self.expect('SYMBOL', ':')
            return LabelStmt(name.value, line=tok.line, col=tok.col)
        if tok.value == 'import':
            return self.parse_import()
        if tok.value == 'from':
            return self.parse_from()
        if tok.value == 'try':
            return self.parse_try()
        if tok.value == 'raise':
            self.advance()
            exc = self.parse_expr()
            return RaiseStmt(exc, line=tok.line, col=tok.col)
        if tok.value == 'with':
            return self.parse_with()
        if tok.value == 'match':
            return self.parse_match()
        if tok.value == 'using':
            return self.parse_using()
        if tok.value == 'ref':
            return self.parse_define(is_ref=True)
        if tok.value == 'define':
            return self.parse_define()
        if tok.value == 'const':
            return self.parse_define(is_const=True)

        # ---- 单行函数检测（支持类型注解和默认值） ----
        if tok.type == 'IDENTIFIER' and self.peek() and self.peek().value == '(':
            saved = self.pos
            name = self.advance().value
            self.expect('SYMBOL', '(')

            params = []
            defaults = {}
            builtin_types = {'int', 'str', 'float', 'double', 'bool', 'boolean',
                             'list', 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'}
            while not self.match('SYMBOL', ')'):
                # 保存当前参数解析位置
                param_saved = self.pos
                ptype = None
                # 检查类型注解
                if self.match('IDENTIFIER') and self.current().value in builtin_types:
                    ptype = self.advance().value
                # 期望参数名（标识符）
                if not self.match('IDENTIFIER'):
                    # 不是标识符，说明不是函数定义，回退
                    self.pos = saved
                    return self.parse_expression_statement()
                pname = self.advance().value
                default = None
                if self.match('SYMBOL', '='):
                    self.advance()
                    default = self.parse_expr()
                    defaults[pname] = default
                params.append(
                    {'name': pname, 'type': ptype, 'default': default})
                if self.match('SYMBOL', ','):
                    self.advance()
            self.expect('SYMBOL', ')')

            return_type = None
            if self.match('SYMBOL', '->'):
                self.advance()
                typetok = self.current()
                if typetok.type in ('IDENTIFIER', 'TYPE', 'KEYWORD'):
                    return_type = self.advance().value
                else:
                    self.error("期望返回值类型", typetok)

            if self.match('SYMBOL', '<-'):
                self.advance()
                body_expr = self.parse_expr()
                node = FuncDefStmt(
                    name=name,
                    params=params,
                    varargs=None,
                    varargs_type=None,
                    kwargs=None,
                    kwargs_type=None,
                    defaults=defaults,
                    body=[ExprStmt(body_expr)],
                    is_single_line=True,
                    return_type=return_type,
                    line=tok.line,
                    col=tok.col
                )
                return node
            else:
                # 不是函数定义，回退
                self.pos = saved
                return self.parse_expression_statement()

        # ---- 装饰器 ----
        if tok.type == 'SYMBOL' and tok.value == '@':
            return self.parse_decorator()

        # ---- 表达式语句 ----
        return self.parse_expression_statement()

    def parse_expression_statement(self):
        expr = self.parse_expr()
        return ExprStmt(expr, line=expr.line, col=expr.col)

    def parse_function(self):
        start = self.current()
        self.expect('KEYWORD', 'def')
        name = self.expect('IDENTIFIER')
        self.expect('SYMBOL', '(')

        builtin_types = {
            'int', 'str', 'float', 'double', 'bool', 'boolean',
            'list', 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'
        }

        params = []
        varargs = None
        varargs_type = None
        kwargs = None
        kwargs_type = None
        defaults = {}

        while not self.match('SYMBOL', ')'):
            ptype = None
            pname = None
            tok = self.current()
            if tok.type == 'IDENTIFIER' and tok.value in builtin_types:
                ptype = self.advance().value

            if self.match('SYMBOL', '**'):
                self.advance()
                kwargs = self.expect('IDENTIFIER').value
                break

            if self.match('SYMBOL', '*'):
                self.advance()
                varargs = self.expect('IDENTIFIER').value
                if self.match('SYMBOL', ','):
                    self.advance()
                continue

            pname = self.expect('IDENTIFIER').value
            default = None
            if self.match('SYMBOL', '='):
                self.advance()
                default = self.parse_expr()
                defaults[pname] = default

            params.append({'name': pname, 'type': ptype, 'default': default})

            if self.match('SYMBOL', ','):
                self.advance()

        self.expect('SYMBOL', ')')

        return_type = None
        if self.match('SYMBOL', '->'):
            self.advance()
            typetok = self.current()
            if typetok.type in ('IDENTIFIER', 'TYPE', 'KEYWORD'):
                return_type = self.advance().value
            else:
                self.error("期望返回值类型", typetok)

        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
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
            col=start.col
        )

    def parse_class(self):
        start = self.current()
        self.expect('KEYWORD', 'class')
        name = self.expect('IDENTIFIER')

        bases = []
        if self.match('SYMBOL', '('):
            self.advance()
            while not self.match('SYMBOL', ')'):
                base = self.expect('IDENTIFIER')
                bases.append(base.value)
                if self.match('SYMBOL', ','):
                    self.advance()
            self.expect('SYMBOL', ')')

        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        self.expect('KEYWORD', 'end')

        return ClassDefStmt(name.value, bases, body, line=start.line, col=start.col)

    def parse_if(self):
        start = self.current()
        self.expect('KEYWORD', 'if')
        cond = self.parse_expr()
        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'elif') and not self.match('KEYWORD', 'else'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)

        elifs = []
        while self.match('KEYWORD', 'elif'):
            self.advance()
            econd = self.parse_expr()
            self.expect('SYMBOL', ':')
            ebody = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'elif') and not self.match('KEYWORD', 'else'):
                stmt = self.parse_statement()
                if stmt:
                    ebody.append(stmt)
            elifs.append((econd, ebody))

        else_body = []
        if self.match('KEYWORD', 'else'):
            self.advance()
            self.expect('SYMBOL', ':')
            while not self.match('KEYWORD', 'end'):
                stmt = self.parse_statement()
                if stmt:
                    else_body.append(stmt)
        self.expect('KEYWORD', 'end')

        return IfStmt(cond, body, elifs, else_body, line=start.line, col=start.col)

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

            if self.match('IDENTIFIER') or self.match('TYPE'):
                iterable = self.parse_expr()
            else:
                range_expr = self.parse_range()

        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        self.expect('KEYWORD', 'end')

        return ForStmt(variable, iterable, range_expr, count, body, line=start.line, col=start.col)

    def parse_while(self):
        start = self.current()
        self.expect('KEYWORD', 'while')
        cond = self.parse_expr()
        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        self.expect('KEYWORD', 'end')

        return WhileStmt(cond, body, line=start.line, col=start.col)

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

        return RangeExpr(left, right, step, inclusive, line=start.line, col=start.col)

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
        while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'except') and not self.match('KEYWORD', 'else') and not self.match('KEYWORD', 'finally'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)

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
            exc_body = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'except') and not self.match('KEYWORD', 'else') and not self.match('KEYWORD', 'finally'):
                stmt = self.parse_statement()
                if stmt:
                    exc_body.append(stmt)
            excepts.append(
                {'type': exc_type, 'name': exc_name, 'body': exc_body})
            if self.match('KEYWORD', 'end'):
                break

        else_body = None
        if self.match('KEYWORD', 'else'):
            self.advance()
            self.expect('SYMBOL', ':')
            else_body = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'finally'):
                stmt = self.parse_statement()
                if stmt:
                    else_body.append(stmt)

        finally_body = None
        if self.match('KEYWORD', 'finally'):
            self.advance()
            self.expect('SYMBOL', ':')
            finally_body = []
            while not self.match('KEYWORD', 'end'):
                stmt = self.parse_statement()
                if stmt:
                    finally_body.append(stmt)

        self.expect('KEYWORD', 'end')
        return TryStmt(body, excepts, else_body, finally_body, line=start.line, col=start.col)

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
        while not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        self.expect('KEYWORD', 'end')
        return WithStmt(items, body, line=start.line, col=start.col)

    def parse_match(self):
        start = self.current()
        self.expect('KEYWORD', 'match')
        value = self.parse_expr()
        self.expect('SYMBOL', ':')

        cases = []
        while not self.match('KEYWORD', 'end'):
            self.expect('KEYWORD', 'case')
            pattern = self.parse_expr()
            self.expect('SYMBOL', ':')
            case_body = []
            while not self.match('KEYWORD', 'end') and not self.match('KEYWORD', 'case'):
                stmt = self.parse_statement()
                if stmt:
                    case_body.append(stmt)
            cases.append({'pattern': pattern, 'body': case_body})
        self.expect('KEYWORD', 'end')
        return MatchStmt(value, cases, line=start.line, col=start.col)

    def parse_using(self):
        start = self.current()
        self.expect('KEYWORD', 'using')
        name = self.expect('IDENTIFIER').value
        self.expect('SYMBOL', ';')
        body = []
        while not self.match('KEYWORD', 'using') and not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        return UsingStmt(name, body, line=start.line, col=start.col)

    def parse_define(self, is_ref=False, is_const=False):
        start = self.current()
        if is_ref:
            self.expect('KEYWORD', 'ref')
            name = self.expect('IDENTIFIER')
            self.expect('SYMBOL', '<-')
            value = self.parse_expr()
            return DefineStmt(name.value, None, value, is_ref=True, is_const=False,
                              line=start.line, col=start.col)

        kw = self.advance().value
        type_name = None
        tok = self.current()
        builtin_types = {'int', 'str', 'float', 'double', 'bool', 'boolean',
                         'list', 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'}
        if tok.type == 'TYPE' or (tok.type == 'IDENTIFIER' and tok.value in builtin_types):
            type_name = self.advance().value

        name = self.expect('IDENTIFIER')

        if self.match('SYMBOL', '<-'):
            self.advance()
            value = self.parse_expr()
        else:
            value = None

        return DefineStmt(
            name=name.value,
            type_name=type_name,
            value=value,
            is_ref=False,
            is_const=(kw == 'const'),
            line=start.line,
            col=start.col
        )

    def parse_decorator(self):
        start = self.current()
        self.expect('SYMBOL', '@')
        decorator = self.expect('IDENTIFIER').value
        name = None
        if self.match('SYMBOL', '.'):
            self.advance()
            name = self.expect('IDENTIFIER').value
        func = self.parse_function()
        return DecoratorStmt(decorator, name, func.body, line=start.line, col=start.col)

    # ---------- 表达式解析 ----------
    def parse_expr(self):
        node = self.parse_assignment()

        if self.match('KEYWORD', 'if'):
            saved = self.pos
            self.advance()
            try:
                self.parse_expr()
                if self.match('SYMBOL', ':'):
                    self.pos = saved
                    return node
            except:
                pass
            self.pos = saved

            self.advance()
            condition = self.parse_expr()
            self.expect('KEYWORD', 'else')
            else_expr = self.parse_expr()
            return IfExpr(condition, node, else_expr, line=condition.line, col=condition.col)

        return node

    def parse_assignment(self):
        left = self.parse_or_expr()

        if self.match('SYMBOL', '<-'):
            op_tok = self.advance()
            right = self.parse_expr()
            if isinstance(left, Variable):
                return Assign(left.name, right, is_ref=False, line=op_tok.line, col=op_tok.col)
            self.error("赋值左侧必须是变量", op_tok)

        if self.match('SYMBOL', '<->'):
            op_tok = self.advance()
            right = self.parse_expr()
            if isinstance(left, Variable) and isinstance(right, Variable):
                return Swap(left.name, right.name, line=op_tok.line, col=op_tok.col)
            self.error("交换操作需要两个变量", op_tok)

        return left

    def parse_or_expr(self):
        left = self.parse_and_expr()
        while self.match('KEYWORD', 'or'):
            op_tok = self.advance()
            right = self.parse_and_expr()
            left = Binary(left, op_tok.value, right,
                          line=op_tok.line, col=op_tok.col)
        return left

    def parse_and_expr(self):
        left = self.parse_compare_expr()
        while self.match('KEYWORD', 'and'):
            op_tok = self.advance()
            right = self.parse_compare_expr()
            left = Binary(left, op_tok.value, right,
                          line=op_tok.line, col=op_tok.col)
        return left

    def parse_compare_expr(self):
        left = self.parse_add_expr()
        ops = {'==', '!=', '<', '>', '<=', '>='}
        while self.match('SYMBOL') and self.current().value in ops:
            op_tok = self.advance()
            right = self.parse_add_expr()
            left = Binary(left, op_tok.value, right,
                          line=op_tok.line, col=op_tok.col)
        return left

    def parse_add_expr(self):
        left = self.parse_mul_expr()
        while self.match('SYMBOL') and self.current().value in ('+', '-'):
            op_tok = self.advance()
            right = self.parse_mul_expr()
            left = Binary(left, op_tok.value, right,
                          line=op_tok.line, col=op_tok.col)
        return left

    def parse_mul_expr(self):
        left = self.parse_pow_expr()
        while self.match('SYMBOL') and self.current().value in ('*', '/', '//', '%'):
            op_tok = self.advance()
            right = self.parse_pow_expr()
            left = Binary(left, op_tok.value, right,
                          line=op_tok.line, col=op_tok.col)
        return left

    def parse_pow_expr(self):
        left = self.parse_unary_expr()
        if self.match('SYMBOL', '**'):
            op_tok = self.advance()
            right = self.parse_unary_expr()
            return Binary(left, '**', right, line=op_tok.line, col=op_tok.col)
        return left

    def parse_unary_expr(self):
        if self.match('SYMBOL') and self.current().value in ('-', '~'):
            op_tok = self.advance()
            right = self.parse_unary_expr()
            return Unary(op_tok.value, right, line=op_tok.line, col=op_tok.col)
        if self.match('KEYWORD', 'not'):
            op_tok = self.advance()
            right = self.parse_unary_expr()
            return Unary(op_tok.value, right, line=op_tok.line, col=op_tok.col)
        return self.parse_primary()

    def parse_primary(self):
        tok = self.current()

        if tok.type in ('INT', 'FLOAT', 'DOUBLE', 'STRING'):
            self.advance()
            node = Literal(tok.value, line=tok.line, col=tok.col)
            if self.match('SYMBOL', '.'):
                dot = self.advance()
                attr = self.expect('IDENTIFIER')
                return Attribute(node, attr.value, line=dot.line, col=dot.col)
            return node

        if tok.type == 'SYMBOL' and tok.value == '(':
            self.advance()
            expr = self.parse_expr()
            self.expect('SYMBOL', ')')
            return expr

        if tok.type == 'SYMBOL' and tok.value == '[':
            return self.parse_list()

        if tok.type == 'SYMBOL' and tok.value == '{':
            return self.parse_dict()

        if tok.type in ('IDENTIFIER', 'TYPE'):
            return self.parse_identifier_or_call()

        if tok.type == 'KEYWORD' and tok.value == 'none':
            self.advance()
            return Literal(None, line=tok.line, col=tok.col)

        self.error(f"意外的 token: {tok.type} '{tok.value}'", tok)

    def parse_identifier_or_call(self):
        tok = self.advance()
        name = tok.value

        if self.match('SYMBOL', '('):
            lparen = self.advance()
            args = []
            kwargs = []
            while not self.match('SYMBOL', ')'):
                if self.match('IDENTIFIER') and self.peek() and self.peek().value == '=':
                    key = self.advance().value
                    self.expect('SYMBOL', '=')
                    value = self.parse_expr()
                    kwargs.append((key, value))
                else:
                    args.append(self.parse_expr())
                if self.match('SYMBOL', ','):
                    self.advance()
            self.expect('SYMBOL', ')')
            func = Variable(name, line=tok.line, col=tok.col)
            node = Call(func, args, kwargs, line=lparen.line, col=lparen.col)
            return self._parse_subscript_chain(node)

        if self.match('SYMBOL', '.'):
            dot = self.advance()
            attr = self.expect('IDENTIFIER')
            obj = Variable(name, line=tok.line, col=tok.col)
            node = Attribute(obj, attr.value, line=dot.line, col=dot.col)
            return self._parse_subscript_chain(node)

        node = Variable(name, line=tok.line, col=tok.col)
        return self._parse_subscript_chain(node)

    def _parse_subscript_chain(self, node):
        while self.match('SYMBOL', '['):
            lb = self.advance()
            index = self.parse_expr()
            self.expect('SYMBOL', ']')
            node = Subscript(node, index, line=lb.line, col=lb.col)
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
        self.expect('SYMBOL', '}')
        return DictExpr(items, line=start.line, col=start.col)


class EclError(Exception):
    pass


class TypeCheckError(Exception):
    def __init__(self, message, line=0, col=0):
        self.message = message
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {message}")
        else:
            super().__init__(message)


class TypeChecker:
    def __init__(self):
        self.scope_stack = [{}]
        self.function_signatures = {}

    def push_scope(self):
        self.scope_stack.append({})

    def pop_scope(self):
        self.scope_stack.pop()

    def current_scope(self):
        return self.scope_stack[-1]

    def lookup(self, name):
        for scope in reversed(self.scope_stack):
            if name in scope:
                return scope[name]['type'], scope[name]['annotated']
        return None, False

    def declare(self, name, type_name, annotated=False):
        self.current_scope()[name] = {
            'type': type_name, 'annotated': annotated}

    def check_type_compatible(self, expected, actual):
        if expected is None or actual is None:
            return True
        if expected == 'any':
            return True
        if '[' in expected:
            expected = expected.split('[')[0].strip()
        expected = expected.split()[0]
        return expected == actual

    def check(self, program):
        for stmt in program.body:
            self.check_statement(stmt)

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
            self.check_if(stmt)
        elif isinstance(stmt, ForStmt):
            self.check_for(stmt)
        elif isinstance(stmt, WhileStmt):
            self.check_while(stmt)
        elif isinstance(stmt, ReturnStmt):
            if stmt.value:
                self.check_expr(stmt.value)
        elif isinstance(stmt, Assign):
            self.check_expr(stmt)
        elif isinstance(stmt, (BreakStmt, ContinueStmt, LabelStmt, GotoStmt,
                               ImportStmt, TryStmt, RaiseStmt, WithStmt,
                               MatchStmt, UsingStmt, DecoratorStmt)):
            pass

    def check_define(self, stmt):
        value_type = self.check_expr(stmt.value) if stmt.value else None
        if stmt.type_name:
            base_type, elem_type, length = self._parse_type(stmt.type_name)
            if not self.check_type_compatible(base_type, value_type):
                raise TypeCheckError(
                    f"类型错误: 变量 '{stmt.name}' 注解为 {stmt.type_name}，"
                    f"但赋值表达式类型为 {value_type}",
                    line=stmt.line, col=stmt.col
                )

            if base_type == 'list' and isinstance(stmt.value, ListExpr):
                elements = stmt.value.elements
                if length is not None and len(elements) != length:
                    raise TypeCheckError(
                        f"类型错误: 列表 '{stmt.name}' 期望长度为 {length}，"
                        f"但实际长度为 {len(elements)}",
                        line=stmt.line, col=stmt.col
                    )
                if elem_type:
                    for i, elem in enumerate(elements):
                        elem_type_name = self.check_expr(elem)
                        if not self.check_type_compatible(elem_type, elem_type_name):
                            raise TypeCheckError(
                                f"类型错误: 列表 '{stmt.name}' 第 {i} 个元素期望 {elem_type}，"
                                f"但得到 {elem_type_name}",
                                line=stmt.line, col=stmt.col
                            )

            self.declare(stmt.name, stmt.type_name, annotated=True)
        else:
            self.declare(stmt.name, None, annotated=False)

    def _parse_type(self, type_name):
        base_type = type_name
        elem_type = None
        length = None

        bracket_pos = type_name.find('[')
        if bracket_pos != -1:
            base_type = type_name[:bracket_pos].strip()
            end_pos = type_name.find(']', bracket_pos)
            if end_pos != -1:
                inner = type_name[bracket_pos + 1:end_pos].strip()
                try:
                    length = int(inner)
                except ValueError:
                    elem_type = inner
                after = type_name[end_pos + 1:].strip()
                if after:
                    elem_type = after
        elif any(base_type.startswith(i) for i in ["list", "tuple", "dict"]):
            after = base_type[4:].strip()
            if after:
                elem_type = after
            base_type = base_type.strip().split()[0]
        else:
            base_type = type_name
        return base_type, elem_type, length

    def check_function_def(self, stmt):
        param_types = [p.get('type') for p in stmt.params]
        self.function_signatures[stmt.name] = (param_types, stmt.return_type)

        self.push_scope()
        for p in stmt.params:
            if p.get('type'):
                self.declare(p['name'], p['type'], annotated=True)
            else:
                self.declare(p['name'], None, annotated=False)

        for s in stmt.body:
            self.check_statement(s)

        self.pop_scope()

    def check_class_def(self, stmt):
        self.push_scope()
        for s in stmt.body:
            self.check_statement(s)
        self.pop_scope()

    def check_if(self, stmt):
        self.check_expr(stmt.condition)
        self.push_scope()
        for s in stmt.body:
            self.check_statement(s)
        self.pop_scope()

        for econd, ebody in stmt.elifs:
            self.push_scope()
            self.check_expr(econd)
            for s in ebody:
                self.check_statement(s)
            self.pop_scope()

        self.push_scope()
        for s in stmt.else_body:
            self.check_statement(s)
        self.pop_scope()

    def check_for(self, stmt):
        if stmt.iterable:
            self.check_expr(stmt.iterable)
        elif stmt.range_expr:
            self.check_expr(stmt.range_expr.start)
            self.check_expr(stmt.range_expr.end)
            if stmt.range_expr.step:
                self.check_expr(stmt.range_expr.step)
        elif stmt.count:
            self.check_expr(stmt.count)

        self.push_scope()
        if stmt.variable:
            self.declare(stmt.variable, None, annotated=False)
        for s in stmt.body:
            self.check_statement(s)
        self.pop_scope()

    def check_while(self, stmt):
        self.check_expr(stmt.condition)
        self.push_scope()
        for s in stmt.body:
            self.check_statement(s)
        self.pop_scope()

    def check_expr(self, expr):
        if expr is None:
            return None

        if isinstance(expr, Literal):
            return self._infer_type(expr.value)

        if isinstance(expr, Variable):
            var_type, annotated = self.lookup(expr.name)
            return var_type

        if isinstance(expr, Binary):
            left_type = self.check_expr(expr.left)
            right_type = self.check_expr(expr.right)
            if left_type and right_type:
                if left_type in ('int', 'float', 'double') and right_type in ('int', 'float', 'double'):
                    return left_type
                if left_type == 'str' and right_type == 'str' and expr.op == '+':
                    return 'str'
            return None

        if isinstance(expr, Unary):
            return self.check_expr(expr.right)

        if isinstance(expr, Assign):
            value_type = self.check_expr(expr.value)
            var_type, annotated = self.lookup(expr.name)
            if annotated and value_type:
                if not self.check_type_compatible(var_type, value_type):
                    raise TypeCheckError(
                        f"类型错误: 变量 '{expr.name}' 注解为 {var_type}，"
                        f"但赋值表达式类型为 {value_type}",
                        line=expr.line, col=expr.col
                    )
            self.current_scope()[expr.name] = {
                'type': value_type, 'annotated': annotated}
            return value_type

        if isinstance(expr, Call):
            for arg in expr.args:
                self.check_expr(arg)

            if isinstance(expr.func, Variable):
                func_name = expr.func.name
                if func_name in self.function_signatures:
                    param_types, ret_type = self.function_signatures[func_name]
                    for i, arg in enumerate(expr.args):
                        if i < len(param_types) and param_types[i] is not None:
                            arg_type = self.check_expr(arg)
                            if not self.check_type_compatible(param_types[i], arg_type):
                                raise TypeCheckError(
                                    f"类型错误: 调用函数 '{func_name}' 时，"
                                    f"第 {i+1} 个参数期望 {param_types[i]}，"
                                    f"但得到 {arg_type}",
                                    line=expr.line, col=expr.col
                                )
            return 'any'

        if isinstance(expr, Attribute):
            self.check_expr(expr.obj)
            return None

        if isinstance(expr, IfExpr):
            self.check_expr(expr.condition)
            then_type = self.check_expr(expr.then_expr)
            else_type = self.check_expr(expr.else_expr)
            return then_type or else_type

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

        return None

    def _infer_type(self, value):
        if isinstance(value, int):
            return 'int'
        if isinstance(value, float):
            return 'float'
        if isinstance(value, str):
            return 'str'
        if isinstance(value, bool):
            return 'bool'
        if isinstance(value, list):
            return 'list'
        if isinstance(value, dict):
            return 'dict'
        if value is None:
            return 'none'
        return None


class Cell:
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value


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

    def __str__(self):
        return super().__str__()


class Interpreter:
    def __init__(self):
        self.globals = {}
        self.scope = self.globals
        self.functions = {}
        self.classes = {}
        self.loop_break = False
        self.loop_continue = False
        self.return_value = None
        self._in_function = False

        self.labels = {}
        self.current_stmts = []
        self.current_pc = 0
        self.in_loop = False

        self.type_map = {
            'int': int,
            'str': str,
            'float': float,
            'double': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'bytes': bytes,
        }

        self.globals['Exception'] = Cell(
            self._make_exception_class('Exception'))
        self.globals['ValueError'] = Cell(
            self._make_exception_class('ValueError'))
        self.globals['TypeError'] = Cell(
            self._make_exception_class('TypeError'))
        self.globals['IndexError'] = Cell(
            self._make_exception_class('IndexError'))
        self.globals['KeyError'] = Cell(self._make_exception_class('KeyError'))
        self.globals['ZeroDivisionError'] = Cell(
            self._make_exception_class('ZeroDivisionError'))

        self._init_builtins()

    def _make_exception_class(self, name):
        def factory(msg=""):
            return {'__class__': name, 'message': str(msg)}
        return factory

    def _init_builtins(self):
        self.globals['print'] = Cell(self._builtin_print)
        self.globals['input'] = Cell(self._builtin_input)
        self.globals['type'] = Cell(self._builtin_type)
        self.globals['len'] = Cell(self._builtin_len)
        self.globals['str'] = Cell(self._builtin_str)
        self.globals['int'] = Cell(self._builtin_int)
        self.globals['float'] = Cell(self._builtin_float)
        self.globals['bool'] = Cell(self._builtin_bool)

    def convert_type(self, value, target_type):
        if target_type is None or target_type == 'any':
            return value
        if target_type not in self.type_map:
            return value
        try:
            return self.type_map[target_type](value)
        except (ValueError, TypeError):
            raise EclException(
                'TypeError', f"无法将 {type(value).__name__} 转换为 {target_type}")

    def _builtin_print(self, *args):
        for arg in args:
            if arg is None:
                print("none", end=" ")
            else:
                print(arg, end=" ")
        print()
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

    def interpret(self, program):
        self.current_stmts = program.body
        self.current_pc = 0
        self._collect_labels(self.current_stmts)

        while self.current_pc < len(self.current_stmts):
            stmt = self.current_stmts[self.current_pc]
            self.current_pc += 1
            self.eval_statement(stmt)
            if self.return_value is not None:
                break

    def _collect_labels(self, stmts, offset=0):
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, LabelStmt):
                self.labels[stmt.name] = i + offset

    def error(self, msg, node=None, exc_type='RuntimeError'):
        if node and hasattr(node, 'line') and hasattr(node, 'col'):
            raise EclException(exc_type, msg, line=node.line, col=node.col)
        else:
            raise EclException(exc_type, msg)

    def eval_statement(self, stmt):
        if isinstance(stmt, ExprStmt):
            return self.eval_expr(stmt.expr)
        if isinstance(stmt, DefineStmt):
            return self.eval_define(stmt)
        if isinstance(stmt, FuncDefStmt):
            return self.eval_function_def(stmt)
        if isinstance(stmt, ClassDefStmt):
            return self.eval_class_def(stmt)
        if isinstance(stmt, IfStmt):
            return self.eval_if(stmt)
        if isinstance(stmt, ForStmt):
            return self.eval_for(stmt)
        if isinstance(stmt, WhileStmt):
            return self.eval_while(stmt)
        if isinstance(stmt, ReturnStmt):
            return self.eval_return(stmt)
        if isinstance(stmt, BreakStmt):
            self.loop_break = True
            return None
        if isinstance(stmt, ContinueStmt):
            self.loop_continue = True
            return None
        if isinstance(stmt, GotoStmt):
            return self.eval_goto(stmt)
        if isinstance(stmt, LabelStmt):
            return None
        if isinstance(stmt, TryStmt):
            return self.eval_try(stmt)
        if isinstance(stmt, RaiseStmt):
            return self.eval_raise(stmt)

        if isinstance(stmt, ImportStmt):
            raise NotImplementedError("import 尚未实现")
        if isinstance(stmt, WithStmt):
            raise NotImplementedError("with 尚未实现")
        if isinstance(stmt, MatchStmt):
            raise NotImplementedError("match 尚未实现")
        if isinstance(stmt, UsingStmt):
            raise NotImplementedError("using 尚未实现")
        if isinstance(stmt, DecoratorStmt):
            raise NotImplementedError("decorator 尚未实现")

        return None

    def eval_goto(self, stmt):
        label_name = stmt.label
        if label_name not in self.labels:
            self.error(f"标签 '{label_name}' 未定义", stmt, 'NameError')
        self.current_pc = self.labels[label_name]
        return None

    def eval_define(self, stmt):
        if stmt.is_ref:
            if not isinstance(stmt.value, Variable):
                self.error("ref 右侧必须是一个变量", stmt, 'TypeError')
            target_name = stmt.value.name
            cell = self._get_cell(target_name)
            if cell is None:
                self.error(f"变量 '{target_name}' 未定义", stmt, 'NameError')
            self.scope[stmt.name] = cell
            return None
        else:
            value = self.eval_expr(stmt.value)
            if stmt.type_name:
                value = self.convert_type(value, stmt.type_name)
            self.scope[stmt.name] = Cell(value)
            return None

    def _get_cell(self, name):
        if name in self.scope:
            return self.scope[name]
        if name in self.globals:
            return self.globals[name]
        return None

    def eval_function_def(self, stmt):
        self.functions[stmt.name] = stmt
        self.scope[stmt.name] = Cell(stmt)
        return None

    def eval_class_def(self, stmt):
        self.classes[stmt.name] = stmt
        self.scope[stmt.name] = Cell(stmt)
        return None

    def eval_if(self, stmt):
        cond = self.eval_expr(stmt.condition)
        if self._is_truthy(cond):
            for s in stmt.body:
                self.eval_statement(s)
                if self.return_value is not None or self.loop_break or self.loop_continue:
                    return
            return

        for econd, ebody in stmt.elifs:
            if self._is_truthy(self.eval_expr(econd)):
                for s in ebody:
                    self.eval_statement(s)
                    if self.return_value is not None or self.loop_break or self.loop_continue:
                        return
                return

        for s in stmt.else_body:
            self.eval_statement(s)
            if self.return_value is not None or self.loop_break or self.loop_continue:
                return

    def eval_for(self, stmt):
        old_in_loop = self.in_loop
        self.in_loop = True

        if stmt.count is not None:
            count = self.eval_expr(stmt.count)
            for _ in range(int(count)):
                for s in stmt.body:
                    self.eval_statement(s)
                    if self.loop_break:
                        self.loop_break = False
                        self.in_loop = old_in_loop
                        return
                    if self.loop_continue:
                        self.loop_continue = False
                        break
                    if self.return_value is not None:
                        self.in_loop = old_in_loop
                        return
            self.in_loop = old_in_loop
            return

        if stmt.range_expr is not None:
            range_expr = stmt.range_expr
            start = self.eval_expr(range_expr.start)
            end = self.eval_expr(range_expr.end)
            step = self.eval_expr(range_expr.step) if range_expr.step else 1
            if range_expr.inclusive:
                end = end + 1

            for i in range(int(start), int(end), int(step)):
                self.scope[stmt.variable] = Cell(i)
                for s in stmt.body:
                    self.eval_statement(s)
                    if self.loop_break:
                        self.loop_break = False
                        self.in_loop = old_in_loop
                        return
                    if self.loop_continue:
                        self.loop_continue = False
                        break
                    if self.return_value is not None:
                        self.in_loop = old_in_loop
                        return
            self.in_loop = old_in_loop
            return

        if stmt.iterable is not None:
            iterable = self.eval_expr(stmt.iterable)
            for item in iterable:
                self.scope[stmt.variable] = Cell(item)
                for s in stmt.body:
                    self.eval_statement(s)
                    if self.loop_break:
                        self.loop_break = False
                        self.in_loop = old_in_loop
                        return
                    if self.loop_continue:
                        self.loop_continue = False
                        break
                    if self.return_value is not None:
                        self.in_loop = old_in_loop
                        return
            self.in_loop = old_in_loop

    def eval_while(self, stmt):
        old_in_loop = self.in_loop
        self.in_loop = True

        while self._is_truthy(self.eval_expr(stmt.condition)):
            for s in stmt.body:
                self.eval_statement(s)
                if self.loop_break:
                    self.loop_break = False
                    self.in_loop = old_in_loop
                    return
                if self.loop_continue:
                    self.loop_continue = False
                    break
                if self.return_value is not None:
                    self.in_loop = old_in_loop
                    return

        self.in_loop = old_in_loop

    def eval_return(self, stmt):
        if stmt.value is not None:
            self.return_value = self.eval_expr(stmt.value)
        else:
            self.return_value = None
        return None

    def eval_raise(self, stmt):
        exc = self.eval_expr(stmt.exception)
        if isinstance(exc, str):
            raise EclException('Exception', exc, line=stmt.line, col=stmt.col)
        if isinstance(exc, dict):
            if '__class__' in exc:
                exc_type = exc['__class__']
                exc_msg = exc.get('message', str(exc))
                raise EclException(exc_type, exc_msg,
                                   line=stmt.line, col=stmt.col)
            else:
                raise EclException('Exception', str(
                    exc), line=stmt.line, col=stmt.col)
        if isinstance(exc, EclException):
            raise exc
        raise EclException('Exception', str(exc), line=stmt.line, col=stmt.col)

    def eval_try(self, stmt):
        try:
            for s in stmt.body:
                self.eval_statement(s)
                if self.return_value is not None:
                    return
        except EclException as e:
            for exc in stmt.excepts:
                if exc['type'] is None or exc['type'] == e.exc_type:
                    if exc['name']:
                        self.scope[exc['name']] = Cell(e)
                    for s in exc['body']:
                        self.eval_statement(s)
                    break
            else:
                raise
        except Exception as e:
            for exc in stmt.excepts:
                if exc['type'] is None or exc['type'] == type(e).__name__:
                    if exc['name']:
                        self.scope[exc['name']] = Cell(e)
                    for s in exc['body']:
                        self.eval_statement(s)
                    break
            else:
                raise
        else:
            if stmt.else_body:
                for s in stmt.else_body:
                    self.eval_statement(s)
        finally:
            if stmt.finally_body:
                for s in stmt.finally_body:
                    self.eval_statement(s)

    def eval_expr(self, expr):
        if expr is None:
            return None

        if isinstance(expr, Literal):
            return expr.value
        if isinstance(expr, Variable):
            cell = self._get_cell(expr.name)
            if cell is None:
                self.error(f"未定义的变量: {expr.name}", expr, 'NameError')
            return cell.value
        if isinstance(expr, Binary):
            return self.eval_binary(expr)
        if isinstance(expr, Unary):
            return self.eval_unary(expr)
        if isinstance(expr, Assign):
            return self.eval_assign(expr)
        if isinstance(expr, Swap):
            return self.eval_swap(expr)
        if isinstance(expr, Call):
            return self.eval_call(expr)
        if isinstance(expr, Attribute):
            return self.eval_attribute(expr)
        if isinstance(expr, ListExpr):
            return self.eval_list(expr)
        if isinstance(expr, DictExpr):
            return self.eval_dict(expr)
        if isinstance(expr, RangeExpr):
            return self.eval_range(expr)
        if isinstance(expr, IfExpr):
            return self.eval_if_expr(expr)
        if isinstance(expr, Subscript):
            return self.eval_subscript(expr)

        self.error(f"未知表达式类型: {type(expr)}", expr, 'TypeError')

    def eval_subscript(self, expr):
        obj = self.eval_expr(expr.obj)
        index = self.eval_expr(expr.index)
        try:
            return obj[index]
        except IndexError:
            self.error(f"索引 {index} 超出范围", expr, 'IndexError')
        except TypeError:
            self.error("对象不支持下标访问", expr, 'TypeError')

    def eval_assign(self, expr):
        value = self.eval_expr(expr.value)
        cell = self._get_cell(expr.name)
        if cell is None:
            self.scope[expr.name] = Cell(value)
        else:
            cell.value = value
        return value

    def eval_swap(self, expr):
        left_cell = self._get_cell(expr.left)
        right_cell = self._get_cell(expr.right)
        if left_cell is None:
            self.error(f"未定义的变量: {expr.left}", expr, 'NameError')
        if right_cell is None:
            self.error(f"未定义的变量: {expr.right}", expr, 'NameError')
        left_cell.value, right_cell.value = right_cell.value, left_cell.value
        return None

    def eval_binary(self, expr):
        left = self.eval_expr(expr.left)
        right = self.eval_expr(expr.right)
        op = expr.op

        try:
            if op == '+':
                return left + right
            if op == '-':
                return left - right
            if op == '*':
                return left * right
            if op == '/':
                return left / right
            if op == '//':
                return left // right
            if op == '%':
                return left % right
            if op == '**':
                return left ** right
            if op == 'or':
                return left or right
            if op == 'and':
                return left and right
            if op == '==':
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
        except Exception as e:
            self.error(str(e), expr, 'RuntimeError')

        self.error(f"未知运算符: {op}", expr, 'TypeError')

    def eval_unary(self, expr):
        right = self.eval_expr(expr.right)
        op = expr.op

        try:
            if op == '-':
                return -right
            if op == 'not':
                return not right
            if op == '~':
                return ~right
        except Exception as e:
            self.error(str(e), expr, 'RuntimeError')

        self.error(f"未知一元运算符: {op}", expr, 'TypeError')

    def eval_call(self, expr):
        func = self.eval_expr(expr.func)

        if callable(func):
            args = [self.eval_expr(arg) for arg in expr.args]
            kwargs = {k: self.eval_expr(v) for k, v in expr.kwargs}
            return func(*args, **kwargs)

        if isinstance(func, FuncDefStmt):
            arg_values = [self.eval_expr(arg) for arg in expr.args]
            kw_values = {k: self.eval_expr(v) for k, v in expr.kwargs}

            old_scope = self.scope
            old_stmts = self.current_stmts
            old_pc = self.current_pc
            old_labels = self.labels

            self.scope = {}
            self._in_function = True
            self.return_value = None

            # 构建参数名到值的映射
            param_names = [p['name'] for p in func.params]
            # 先按位置填充
            assigned = {}
            for i, name in enumerate(param_names):
                if i < len(arg_values):
                    assigned[name] = arg_values[i]
            # 关键字参数覆盖
            for key, val in kw_values.items():
                if key in param_names:
                    assigned[key] = val
                else:
                    # 如果函数有 **kwargs 则接收
                    if func.kwargs:
                        if func.kwargs not in assigned:
                            assigned[func.kwargs] = {}
                        assigned[func.kwargs][key] = val
                    else:
                        self.error(f"未知关键字参数: {key}", expr, 'TypeError')

            # 检查是否缺少参数
            for param in func.params:
                name = param['name']
                if name not in assigned:
                    # 检查是否有默认值
                    if param['default'] is not None:
                        assigned[name] = self.eval_expr(param['default'])
                    else:
                        self.error(f"缺少参数: {name}", expr, 'TypeError')

            # 填充 *args
            if func.varargs:
                start = len(func.params)
                assigned[func.varargs] = arg_values[start:]

            # 填充 **kwargs（剩余的）
            if func.kwargs and func.kwargs not in assigned:
                assigned[func.kwargs] = {}

            # 将 assigned 放入作用域
            for name, val in assigned.items():
                self.scope[name] = Cell(val)

            self.current_stmts = func.body
            self.current_pc = 0
            self.labels = {}
            self._collect_labels(self.current_stmts)

            last_expr_value = None
            while self.current_pc < len(self.current_stmts):
                stmt = self.current_stmts[self.current_pc]
                self.current_pc += 1

                if isinstance(stmt, ReturnStmt):
                    self.return_value = self.eval_expr(
                        stmt.value) if stmt.value is not None else None
                    break
                elif isinstance(stmt, ExprStmt):
                    last_expr_value = self.eval_expr(stmt.expr)
                else:
                    self.eval_statement(stmt)
                    if self.return_value is not None:
                        break

            result = self.return_value if self.return_value is not None else last_expr_value

            self.return_value = None
            self._in_function = False
            self.scope = old_scope
            self.current_stmts = old_stmts
            self.current_pc = old_pc
            self.labels = old_labels

            return result

        if isinstance(func, ClassDefStmt):
            return self._instantiate_class(func, expr)

        self.error(f"无法调用: {func}", expr, 'TypeError')

    def _instantiate_class(self, class_stmt, expr):
        instance = {'__class__': class_stmt.name}

        init_func = None
        for stmt in class_stmt.body:
            if isinstance(stmt, FuncDefStmt) and stmt.name == '__init__':
                init_func = stmt
                break

        if init_func:
            old_scope = self.scope
            self.scope = {}
            self._in_function = True

            self.scope['self'] = Cell(instance)

            # 处理 __init__ 的参数（同样支持关键字）
            arg_values = [self.eval_expr(arg) for arg in expr.args]
            kw_values = {k: self.eval_expr(v) for k, v in expr.kwargs}
            param_names = [p['name']
                           for p in init_func.params if p['name'] != 'self']
            assigned = {}
            # 位置参数
            pos_idx = 0
            for p in init_func.params:
                if p['name'] == 'self':
                    continue
                if pos_idx < len(arg_values):
                    assigned[p['name']] = arg_values[pos_idx]
                    pos_idx += 1
            # 关键字覆盖
            for key, val in kw_values.items():
                if key in param_names:
                    assigned[key] = val
                elif init_func.kwargs:
                    if init_func.kwargs not in assigned:
                        assigned[init_func.kwargs] = {}
                    assigned[init_func.kwargs][key] = val
                else:
                    self.error(f"未知关键字参数: {key}", expr, 'TypeError')
            # 检查缺省
            for p in init_func.params:
                name = p['name']
                if name == 'self':
                    continue
                if name not in assigned:
                    if p['default'] is not None:
                        assigned[name] = self.eval_expr(p['default'])
                    else:
                        self.error(f"缺少参数: {name}", expr, 'TypeError')
            # 放入作用域
            for name, val in assigned.items():
                self.scope[name] = Cell(val)

            for stmt in init_func.body:
                self.eval_statement(stmt)
                if self.return_value is not None:
                    break

            self.return_value = None
            self._in_function = False
            self.scope = old_scope

        for stmt in class_stmt.body:
            if isinstance(stmt, FuncDefStmt) and stmt.name != '__init__':
                instance[stmt.name] = stmt

        return instance

    def eval_attribute(self, expr):
        obj = self.eval_expr(expr.obj)
        attr = expr.attr

        if isinstance(obj, dict):
            if attr in obj:
                return obj[attr]
            self.error(f"属性不存在: {attr}", expr, 'AttributeError')

        if isinstance(obj, str):
            if attr == 'join':
                return lambda *args: self._string_join(obj, args)
            if hasattr(obj, attr):
                return getattr(obj, attr)

        if isinstance(obj, list):
            if attr == 'append':
                return lambda x: obj.append(x)
            if attr == 'pop':
                return lambda: obj.pop()
            if attr == 'remove':
                return lambda x: obj.remove(x)
            if attr == 'clear':
                return lambda: obj.clear()

        if isinstance(obj, dict):
            if attr in obj:
                return obj[attr]
            if attr in obj:
                method = obj[attr]
                if isinstance(method, FuncDefStmt):
                    return lambda *args, **kwargs: self._call_method(obj, method, args, kwargs)

        self.error(f"无法访问属性: {attr}", expr, 'AttributeError')

    def _string_join(self, obj, args):
        if len(args) == 0:
            return obj
        sep = obj
        items = [self.eval_expr(arg) if not isinstance(
            arg, str) else arg for arg in args[0]]
        return sep.join(str(item) for item in items)

    def _call_method(self, instance, method, args, kwargs):
        old_scope = self.scope
        self.scope = {}
        self._in_function = True

        self.scope['self'] = Cell(instance)

        # 类似函数调用的参数绑定
        arg_values = [self.eval_expr(arg) for arg in args]
        kw_values = {k: self.eval_expr(v) for k, v in kwargs}
        param_names = [p['name'] for p in method.params if p['name'] != 'self']
        assigned = {}
        pos_idx = 0
        for p in method.params:
            if p['name'] == 'self':
                continue
            if pos_idx < len(arg_values):
                assigned[p['name']] = arg_values[pos_idx]
                pos_idx += 1
        for key, val in kw_values.items():
            if key in param_names:
                assigned[key] = val
            elif method.kwargs:
                if method.kwargs not in assigned:
                    assigned[method.kwargs] = {}
                assigned[method.kwargs][key] = val
            else:
                self.error(f"未知关键字参数: {key}", method, 'TypeError')
        for p in method.params:
            name = p['name']
            if name == 'self':
                continue
            if name not in assigned:
                if p['default'] is not None:
                    assigned[name] = self.eval_expr(p['default'])
                else:
                    self.error(f"缺少参数: {name}", method, 'TypeError')
        for name, val in assigned.items():
            self.scope[name] = Cell(val)

        for stmt in method.body:
            self.eval_statement(stmt)
            if self.return_value is not None:
                break

        result = self.return_value
        self.return_value = None
        self._in_function = False
        self.scope = old_scope
        return result

    def eval_list(self, expr):
        return [self.eval_expr(e) for e in expr.elements]

    def eval_dict(self, expr):
        return {self.eval_expr(k): self.eval_expr(v) for k, v in expr.items}

    def eval_range(self, expr):
        start = self.eval_expr(expr.start)
        end = self.eval_expr(expr.end)
        step = self.eval_expr(expr.step) if expr.step else 1
        if expr.inclusive:
            end = end + 1
        return range(int(start), int(end), int(step))

    def eval_if_expr(self, expr):
        if self._is_truthy(self.eval_expr(expr.condition)):
            return self.eval_expr(expr.then_expr)
        return self.eval_expr(expr.else_expr)

    def _is_truthy(self, value):
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, (str, list, dict, set, tuple)):
            return len(value) > 0
        return bool(value)


def run_ecl(code):
    tokens = split_token(code)
    parser = Parser(tokens)
    ast = parser.parse()

    try:
        checker = TypeChecker()
        checker.check(ast)
    except TypeCheckError as e:
        print(f"类型检查错误: {e.message}")
        sys.exit(1)

    interpreter = Interpreter()
    interpreter.interpret(ast)
    return interpreter


if __name__ == '__main__':
    code = '''
int x <- 42
/// 打招呼, name是string类型, *ohters是其他的东西, str类型
def greet(str name, str *others, **kwargs) -> void:
    print("hello, " + name)
    for i in others:
        print(i)
    end
end
f(int x) -> int <- 1 if x < 1 else x * f(x - 1)
if x > 0:
    print("positive")
else:
    print("negative")
end
for i in 1..=10:
    print(i)
end
str y <- "world"
label a:
print(1)
x <- x - 1
if x == 0:
    goto jump
else:
    print(x)
end
goto a
label jump:
print("Hello, " + y)
print(f(5))
print(greet("User", "a", "b"))
try:
    raise ValueError("报错啦")
except TypeError:
    print("Perfect")
except ValueError:
    print("成功拦截")
else:
    print("没有问题")
finally:
    print("I am last")
end
x <- 1
ref y <- x
ref z <- y    # 允许
z <- 2
print(x)      # 输出 2
print(y)      # 输出 2
list[5] int m <- [1, 2, 3, 4, 5]
list[5] pi <- [3.1, 4, 1, 5, 9]
ah <- ["a", "h"]
list float d <- [1.2, 3.4, 1.0]
print(m[2])
num1 <- 100
num2 <- 200
num1 <-> num2
print(num2, num1)
print(f(x=10))
'''
    run_ecl(code)
