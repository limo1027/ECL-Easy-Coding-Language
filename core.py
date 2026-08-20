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


@dataclass
class Expr:
    pass


@dataclass
class Literal(Expr):
    value: Any


@dataclass
class Variable(Expr):
    name: str


@dataclass
class Binary(Expr):
    left: Expr
    op: str
    right: Expr


@dataclass
class Unary(Expr):
    op: str
    right: Expr


@dataclass
class Assign(Expr):
    name: Union[str, 'Attribute']
    value: Expr
    is_ref: bool = False


@dataclass
class Swap(Expr):
    left: str
    right: str


@dataclass
class Call(Expr):
    func: Expr
    args: List[Expr]
    kwargs: List[tuple]


@dataclass
class Attribute(Expr):
    obj: Expr
    attr: str


@dataclass
class IfExpr(Expr):
    condition: Expr
    then_expr: Expr
    else_expr: Expr


@dataclass
class ListExpr(Expr):
    elements: List[Expr]
    fixed_length: Optional[int] = None


@dataclass
class DictExpr(Expr):
    items: List[tuple]


@dataclass
class SetExpr(Expr):
    elements: List[Expr]


@dataclass
class TupleExpr(Expr):
    elements: List[Expr]


@dataclass
class RangeExpr(Expr):
    start: Expr
    end: Expr
    step: Optional[Expr]
    inclusive: bool


@dataclass
class CodeBlock(Expr):
    body: List['Stmt']


@dataclass
class LambdaExpr(Expr):
    params: List[str]
    body: Expr


@dataclass
class Stmt:
    pass


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class Subscript(Expr):
    obj: Expr
    index: Expr


@dataclass
class DefineStmt(Stmt):
    name: str
    type_name: Optional[str]
    value: Optional[Expr]
    is_ref: bool = False
    is_const: bool = False


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


@dataclass
class ClassDefStmt(Stmt):
    name: str
    bases: List[str]
    body: List[Stmt]


@dataclass
class IfStmt(Stmt):
    condition: Expr
    body: List[Stmt]
    elifs: List[tuple]
    else_body: List[Stmt]


@dataclass
class ForStmt(Stmt):
    variable: Optional[str]
    iterable: Optional[Expr]
    range_expr: Optional[RangeExpr]
    count: Optional[Expr]
    body: List[Stmt]


@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: List[Stmt]


@dataclass
class BreakStmt(Stmt):
    pass


@dataclass
class ContinueStmt(Stmt):
    pass


@dataclass
class ReturnStmt(Stmt):
    value: Optional[Expr]


@dataclass
class GotoStmt(Stmt):
    label: str


@dataclass
class LabelStmt(Stmt):
    name: str


@dataclass
class ImportStmt(Stmt):
    module: str
    alias: Optional[str]
    names: List[tuple]


@dataclass
class TryStmt(Stmt):
    body: List[Stmt]
    excepts: List[dict]
    else_body: Optional[List[Stmt]]
    finally_body: Optional[List[Stmt]]


@dataclass
class RaiseStmt(Stmt):
    exception: Expr


@dataclass
class WithStmt(Stmt):
    items: List[tuple]
    body: List[Stmt]


@dataclass
class MatchStmt(Stmt):
    value: Expr
    cases: List[dict]


@dataclass
class UsingStmt(Stmt):
    name: str
    body: List[Stmt]


@dataclass
class DecoratorStmt(Stmt):
    target: str
    name: str
    body: List[Stmt]


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
        # 跳过当前行所有字符（包括注释内容和三个斜杠）
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

    def expect(self, type_, value=None):
        tok = self.current()

        if not tok or tok.type != type_ or (value is not None and tok.value != value):
            print(
                f"缺少 token: \"{value}\" 在第{tok.line}行, 第{tok.col}列", file=sys.stderr)
            sys.exit(1)
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
        # ---- 定义 types 集合（必须在开头） ----
        types = {'int', 'str', 'float', 'double', 'bool', 'boolean', 'list',
                 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'}

        if not tok:
            return None

        if tok.type == 'KEYWORD' and tok.value == 'end':
            return None

        # ---- 类型声明（包括 list[6] float 格式） ----
        if tok.value in types:
            base_type = self.advance().value
            type_params = []

            # 解析 [n] 部分
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

            # 解析元素类型（如 float）
            elem_type = None
            builtin_types = {'int', 'str', 'float', 'double', 'bool', 'boolean',
                             'list', 'dict', 'set', 'tuple', 'bytes', 'code', 'function', 'any'}
            tok2 = self.current()
            if tok2.type == 'TYPE' or (tok2.type == 'IDENTIFIER' and tok2.value in builtin_types):
                elem_type = self.advance().value

            # 解析变量名
            name = self.expect('IDENTIFIER')

            # 解析赋值
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

            return DefineStmt(name.value, full_type, value, is_ref=False, is_const=False)

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
            if self.match('SYMBOL', ':'):
                return ReturnStmt(None)
            return ReturnStmt(self.parse_expr())
        if tok.value == 'break':
            self.advance()
            return BreakStmt()
        if tok.value == 'continue':
            self.advance()
            return ContinueStmt()
        if tok.value == 'goto':
            self.advance()
            label = self.expect('IDENTIFIER')
            return GotoStmt(label.value)
        if tok.value == 'label':
            self.advance()
            name = self.expect('IDENTIFIER')
            self.expect('SYMBOL', ':')
            return LabelStmt(name.value)
        if tok.value == 'import':
            return self.parse_import()
        if tok.value == 'from':
            return self.parse_from()
        if tok.value == 'try':
            return self.parse_try()
        if tok.value == 'raise':
            self.advance()
            return RaiseStmt(self.parse_expr())
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

        # ---- 单行函数检测 ----
        if tok.type == 'IDENTIFIER' and self.peek() and self.peek().value == '(':
            saved = self.pos
            name = self.advance().value
            self.expect('SYMBOL', '(')

            args = []
            while not self.match('SYMBOL', ')'):
                args.append(self.parse_expr())
                if self.match('SYMBOL', ','):
                    self.advance()
            self.expect('SYMBOL', ')')

            if self.match('SYMBOL', '<-'):
                self.advance()
                body_expr = self.parse_expr()
                is_func_def = True
                params = []
                for arg in args:
                    if isinstance(arg, Variable):
                        params.append(
                            {'name': arg.name, 'type': None, 'default': None})
                    else:
                        is_func_def = False
                        break
                if is_func_def:
                    return FuncDefStmt(
                        name=name,
                        params=params,
                        varargs=None,
                        varargs_type=None,
                        kwargs=None,
                        kwargs_type=None,
                        defaults={},
                        body=[ExprStmt(body_expr)],
                        is_single_line=True
                    )
                self.pos = saved
                return self.parse_expression_statement()

            self.pos = saved
            return self.parse_expression_statement()

        # ---- 装饰器 ----
        if tok.type == 'SYMBOL' and tok.value == '@':
            return self.parse_decorator()

        # ---- 表达式语句（兜底） ----
        return self.parse_expression_statement()

    def parse_expression_statement(self):
        return ExprStmt(self.parse_expr())

    def parse_function(self):
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

            # 处理 **kwargs（必须在 * 之前）
            if self.match('SYMBOL', '**'):
                self.advance()
                kwargs = self.expect('IDENTIFIER').value
                break

            # 处理 *args
            if self.match('SYMBOL', '*'):
                self.advance()

                varargs = self.expect('IDENTIFIER').value
                if self.match('SYMBOL', ','):
                    self.advance()
                continue  # 不再尝试解析普通参数

            pname = self.expect('IDENTIFIER').value

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
            is_single_line=False
        )

    def parse_class(self):
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

        return ClassDefStmt(name.value, bases, body)

    def parse_if(self):
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
        return IfStmt(cond, body, elifs, else_body)

    def parse_for(self):
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

        return ForStmt(variable, iterable, range_expr, count, body)

    def parse_while(self):
        self.expect('KEYWORD', 'while')
        cond = self.parse_expr()
        self.expect('SYMBOL', ':')

        body = []
        while not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        self.expect('KEYWORD', 'end')

        return WhileStmt(cond, body)

    def parse_range(self):
        start = self.parse_expr()
        inclusive = False

        if self.match('SYMBOL', '..='):
            self.advance()
            inclusive = True
        elif self.match('SYMBOL', '..'):
            self.advance()
        else:
            raise Exception("期望 '..' 或 '..='")

        end = self.parse_expr()
        step = None

        if self.match('SYMBOL', '+'):
            self.advance()
            step = self.parse_expr()

        return RangeExpr(start, end, step, inclusive)

    def parse_import(self):
        self.expect('KEYWORD', 'import')
        module = self.expect('IDENTIFIER').value
        alias = None
        if self.match('KEYWORD', 'as'):
            self.advance()
            alias = self.expect('IDENTIFIER').value
        return ImportStmt(module, alias, [])

    def parse_from(self):
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

        return ImportStmt(module, None, names)

    def parse_try(self):
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
        return TryStmt(body, excepts, else_body, finally_body)

    def parse_with(self):
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
        return WithStmt(items, body)

    def parse_match(self):
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
        return MatchStmt(value, cases)

    def parse_using(self):
        self.expect('KEYWORD', 'using')
        name = self.expect('IDENTIFIER').value
        self.expect('SYMBOL', ';')
        body = []
        while not self.match('KEYWORD', 'using') and not self.match('KEYWORD', 'end'):
            stmt = self.parse_statement()
            if stmt:
                body.append(stmt)
        return UsingStmt(name, body)

    def parse_define(self, is_ref=False, is_const=False):
        if is_ref:
            self.expect('KEYWORD', 'ref')
            name = self.expect('IDENTIFIER')
            self.expect('SYMBOL', '<-')
            value = self.parse_expr()
            return DefineStmt(name.value, None, value, is_ref=True, is_const=False)

        kw = self.advance().value
        type_name = None

        # 先检查 TYPE，再检查 IDENTIFIER（值是内置类型名）
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
            is_const=(kw == 'const')
        )

    def parse_decorator(self):
        self.expect('SYMBOL', '@')
        decorator = self.expect('IDENTIFIER').value
        name = None
        if self.match('SYMBOL', '.'):
            self.advance()
            name = self.expect('IDENTIFIER').value
        func = self.parse_function()
        return DecoratorStmt(decorator, name, func)

    # ---------- 表达式解析 ----------
    def parse_expr(self):
        node = self.parse_assignment()

        # 检测 if 三元表达式
        if self.match('KEYWORD', 'if'):
            # 偷看后面：如果是 `if` 后面跟着条件表达式，然后有 `:`，则是 if 语句，不是三元
            saved = self.pos
            self.advance()  # 吃掉 if
            try:
                self.parse_expr()  # 尝试解析条件
                if self.match('SYMBOL', ':'):
                    # 这是 if 语句，回退
                    self.pos = saved
                    return node
            except:
                pass
            self.pos = saved

            # 真正的三元表达式
            self.advance()
            condition = self.parse_expr()
            self.expect('KEYWORD', 'else')
            else_expr = self.parse_expr()
            return IfExpr(condition, node, else_expr)

        return node

    def parse_assignment(self):
        left = self.parse_or_expr()

        if self.match('SYMBOL', '<-'):
            self.advance()
            right = self.parse_expr()
            if isinstance(left, Variable):
                return Assign(left.name, right, is_ref=False)
            raise Exception("赋值左侧必须是变量")

        if self.match('SYMBOL', '<->'):
            self.advance()
            right = self.parse_expr()
            if isinstance(left, Variable) and isinstance(right, Variable):
                return Swap(left.name, right.name)
            raise Exception("交换操作需要两个变量")

        return left

    def parse_or_expr(self):
        left = self.parse_and_expr()
        while self.match('KEYWORD', 'or'):
            op = self.advance().value
            right = self.parse_and_expr()
            left = Binary(left, op, right)
        return left

    def parse_and_expr(self):
        left = self.parse_compare_expr()
        while self.match('KEYWORD', 'and'):
            op = self.advance().value
            right = self.parse_compare_expr()
            left = Binary(left, op, right)
        return left

    def parse_compare_expr(self):
        left = self.parse_add_expr()
        ops = {'==', '!=', '<', '>', '<=', '>='}
        while self.match('SYMBOL') and self.current().value in ops:
            op = self.advance().value
            right = self.parse_add_expr()
            left = Binary(left, op, right)
        return left

    def parse_add_expr(self):
        left = self.parse_mul_expr()
        while self.match('SYMBOL') and self.current().value in ('+', '-'):
            op = self.advance().value
            right = self.parse_mul_expr()
            left = Binary(left, op, right)
        return left

    def parse_mul_expr(self):
        left = self.parse_pow_expr()
        while self.match('SYMBOL') and self.current().value in ('*', '/', '//', '%'):
            op = self.advance().value
            right = self.parse_pow_expr()
            left = Binary(left, op, right)
        return left

    def parse_pow_expr(self):
        left = self.parse_unary_expr()
        if self.match('SYMBOL', '**'):
            self.advance()
            right = self.parse_unary_expr()
            return Binary(left, '**', right)
        return left

    def parse_unary_expr(self):
        if self.match('SYMBOL') and self.current().value in ('-', '~'):
            op = self.advance().value
            right = self.parse_unary_expr()
            return Unary(op, right)
        if self.match('KEYWORD', 'not'):
            op = self.advance().value
            right = self.parse_unary_expr()
            return Unary(op, right)
        return self.parse_primary()

    def parse_primary(self):
        tok = self.current()

        if tok.type in ('INT', 'FLOAT', 'DOUBLE', 'STRING'):
            self.advance()
            node = Literal(tok.value)
            if self.match('SYMBOL', '.'):
                self.advance()
                attr = self.expect('IDENTIFIER').value
                node = Attribute(node, attr)
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
            return Literal(None)

        raise Exception(f"意外的 token: {tok.type} '{tok.value}'")

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
                    value = self.parse_expr()
                    kwargs.append((key, value))
                else:
                    args.append(self.parse_expr())
                if self.match('SYMBOL', ','):
                    self.advance()
            self.expect('SYMBOL', ')')
            node = Call(Variable(name), args, kwargs)
            return self._parse_subscript_chain(node)

        # 属性访问
        if self.match('SYMBOL', '.'):
            self.advance()
            attr = self.expect('IDENTIFIER').value
            node = Attribute(Variable(name), attr)
            return self._parse_subscript_chain(node)

        node = Variable(name)
        return self._parse_subscript_chain(node)

    def _parse_subscript_chain(self, node):
        """解析连续下标访问，如 a[1][2]"""
        while self.match('SYMBOL', '['):
            self.advance()
            index = self.parse_expr()
            self.expect('SYMBOL', ']')
            node = Subscript(node, index)
        return node

    def parse_list(self):
        self.expect('SYMBOL', '[')
        elements = []
        if not self.match('SYMBOL', ']'):
            while True:
                elements.append(self.parse_expr())
                if not self.match('SYMBOL', ','):
                    break
                self.advance()
        self.expect('SYMBOL', ']')
        return ListExpr(elements)

    def parse_dict(self):
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
        return DictExpr(items)


class EclError(Exception):
    pass


class TypeCheckError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class TypeChecker:
    def __init__(self):
        self.scope_stack = [{}]  # {name: {'type': str, 'annotated': bool}}
        self.function_signatures = {}  # 函数名 -> [参数类型列表]

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
        # 提取基础类型
        if '[' in expected:
            expected = expected.split('[')[0].strip()
        expected = expected.split()[0]
        return expected == actual

    # ---------- 入口 ----------
    def check(self, program):
        for stmt in program.body:
            self.check_statement(stmt)

    # ---------- 语句 ----------
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

    # ---------- 变量定义 ----------
    def check_define(self, stmt):
        value_type = self.check_expr(stmt.value) if stmt.value else None
        if stmt.type_name:
            # 解析复合类型，如 "list[6] float"
            base_type, elem_type, length = self._parse_type(stmt.type_name)
            print(base_type, elem_type, length)
            # 1. 检查基础类型是否匹配
            if not self.check_type_compatible(base_type, value_type):
                raise TypeCheckError(
                    f"类型错误: 变量 '{stmt.name}' 注解为 {stmt.type_name}，"
                    f"但赋值表达式类型为 {value_type}"
                )

            # 2. 如果是列表且指定了元素类型或长度，检查列表内容
            if base_type == 'list' and isinstance(stmt.value, ListExpr):
                elements = stmt.value.elements
                if length is not None and len(elements) != length:
                    raise TypeCheckError(
                        f"类型错误: 列表 '{stmt.name}' 期望长度为 {length}，"
                        f"但实际长度为 {len(elements)}"
                    )
                if elem_type:
                    for i, elem in enumerate(elements):
                        elem_type_name = self.check_expr(elem)
                        if not self.check_type_compatible(elem_type, elem_type_name):
                            raise TypeCheckError(
                                f"类型错误: 列表 '{stmt.name}' 第 {i} 个元素期望 {elem_type}，"
                                f"但得到 {elem_type_name}"
                            )

            self.declare(stmt.name, stmt.type_name, annotated=True)
        else:
            self.declare(stmt.name, None, annotated=False)

    def _parse_type(self, type_name):
        """解析复合类型，返回 (base_type, elem_type, length)"""
        # 例如 "list[6] float" -> ("list", "float", 6)
        # 例如 "list[float]" -> ("list", "float", None)
        # 例如 "int" -> ("int", None, None)
        base_type = type_name
        elem_type = None
        length = None

        # 找到第一个 [ 的位置
        bracket_pos = type_name.find('[')
        if bracket_pos != -1:
            base_type = type_name[:bracket_pos].strip()
            # 找到对应的 ]
            end_pos = type_name.find(']', bracket_pos)
            if end_pos != -1:
                inner = type_name[bracket_pos + 1:end_pos].strip()
                # 判断是长度（数字）还是元素类型（字符串）
                length = int(inner)
                # 检查后面是否还有元素类型（如 "list[6] float"）
                after = type_name[end_pos + 1:].strip()
                if after:
                    elem_type = after
        elif any(base_type.startswith(i) for i in ["list", "tuple", "dict"]):
            after = type_name[4:].strip()
            if after:
                elem_type = after
            base_type = base_type.strip().split()[0]
        else:
            base_type = type_name
        return base_type, elem_type, length

    # ---------- 函数 ----------

    def check_function_def(self, stmt):
        param_types = [p.get('type') for p in stmt.params]
        self.function_signatures[stmt.name] = param_types

        self.push_scope()
        for p in stmt.params:
            if p.get('type'):
                self.declare(p['name'], p['type'], annotated=True)
            else:
                self.declare(p['name'], None, annotated=False)

        for s in stmt.body:
            self.check_statement(s)

        self.pop_scope()

    # ---------- 类 ----------
    def check_class_def(self, stmt):
        self.push_scope()
        for s in stmt.body:
            self.check_statement(s)
        self.pop_scope()

    # ---------- 控制流 ----------
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

    # ---------- 表达式 ----------
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
                        f"但赋值表达式类型为 {value_type}"
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
                    param_types = self.function_signatures[func_name]
                    for i, arg in enumerate(expr.args):
                        if i < len(param_types) and param_types[i] is not None:
                            arg_type = self.check_expr(arg)
                            if not self.check_type_compatible(param_types[i], arg_type):
                                raise TypeCheckError(
                                    f"类型错误: 调用函数 '{func_name}' 时，"
                                    f"第 {i+1} 个参数期望 {param_types[i]}，"
                                    f"但得到 {arg_type}"
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
    def __init__(self, exc_type, message, cause=None):
        self.exc_type = exc_type
        self.message = message
        self.cause = cause
        super().__init__(message)

    def __str__(self):
        if self.cause:
            return f"{self.exc_type}: {self.message} (from {self.cause})"
        return f"{self.exc_type}: {self.message}"


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
            raise EclException('NameError', f"标签 '{label_name}' 未定义")
        self.current_pc = self.labels[label_name]
        return None

    def eval_define(self, stmt):
        if stmt.is_ref:
            if not isinstance(stmt.value, Variable):
                raise EclException('TypeError', "ref 右侧必须是一个变量")
            target_name = stmt.value.name
            cell = self._get_cell(target_name)
            if cell is None:
                raise EclException('NameError', f"变量 '{target_name}' 未定义")
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
            raise EclException('Exception', exc)
        if isinstance(exc, dict):
            if '__class__' in exc:
                exc_type = exc['__class__']
                exc_msg = exc.get('message', str(exc))
                raise EclException(exc_type, exc_msg)
            else:
                raise EclException('Exception', str(exc))
        if isinstance(exc, EclException):
            raise exc
        raise EclException('Exception', str(exc))

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
                raise EclException('NameError', f"未定义的变量: {expr.name}")
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

        raise EclException('TypeError', f"未知表达式类型: {type(expr)}")

    def eval_subscript(self, expr):
        obj = self.eval_expr(expr.obj)
        index = self.eval_expr(expr.index)
        try:
            return obj[index]
        except IndexError:
            print(
                'IndexError: ', f"索引 {index} 超出 {len(obj) - 1} 的范围", file=sys.stderr)
            sys.exit(1)
        except TypeError:
            raise EclException('TypeError', f"对象不支持下标访问")

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
            raise EclException('NameError', f"未定义的变量: {expr.left}")
        if right_cell is None:
            raise EclException('NameError', f"未定义的变量: {expr.right}")
        left_cell.value, right_cell.value = right_cell.value, left_cell.value
        return None

    def eval_binary(self, expr):
        left = self.eval_expr(expr.left)
        right = self.eval_expr(expr.right)
        op = expr.op

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

        raise EclException('TypeError', f"未知运算符: {op}")

    def eval_unary(self, expr):
        right = self.eval_expr(expr.right)
        op = expr.op

        if op == '-':
            return -right
        if op == 'not':
            return not right
        if op == '~':
            return ~right

        raise EclException('TypeError', f"未知一元运算符: {op}")

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

            for i, param in enumerate(func.params):
                if i < len(arg_values):
                    self.scope[param['name']] = Cell(arg_values[i])
                elif param['default'] is not None:
                    self.scope[param['name']] = Cell(
                        self.eval_expr(param['default']))
                else:
                    raise EclException('TypeError', f"缺少参数: {param['name']}")

            if func.varargs:
                start = len(func.params)
                self.scope[func.varargs] = Cell(arg_values[start:])

            if func.kwargs:
                self.scope[func.kwargs] = Cell(kw_values)

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

        raise EclException('TypeError', f"无法调用: {func}")

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

            for i, param in enumerate(init_func.params):
                if param['name'] == 'self':
                    continue
                if i - 1 < len(expr.args):
                    value = self.eval_expr(expr.args[i - 1])
                    self.scope[param['name']] = Cell(value)
                elif param['default'] is not None:
                    self.scope[param['name']] = Cell(
                        self.eval_expr(param['default']))
                else:
                    raise EclException('TypeError', f"缺少参数: {param['name']}")

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
            raise EclException('AttributeError', f"属性不存在: {attr}")

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

        raise EclException('AttributeError', f"无法访问属性: {attr}")

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

        for i, param in enumerate(method.params):
            if param['name'] == 'self':
                continue
            if i - 1 < len(args):
                value = self.eval_expr(args[i - 1])
                self.scope[param['name']] = Cell(value)
            elif param['default'] is not None:
                self.scope[param['name']] = Cell(
                    self.eval_expr(param['default']))
            else:
                raise EclException('TypeError', f"缺少参数: {param['name']}")

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
    code = '''int x <- 42
/// 打招呼, name是string类型, *ohters是其他的东西, str类型
def greet(str name, str *others, **kwargs):
    print("hello, " + name)
    for i in others:
        print(i)
    end
end
f(x) <- 1 if x < 1 else x * f(x - 1)
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
list float f <- [1.2, 3.4, 1.0]
print(m[2])
num1 <- 100
num2 <- 200
num1 <-> num2
print(num2, num1)
'''
    run_ecl(code)
