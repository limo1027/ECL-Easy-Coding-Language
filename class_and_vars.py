from dataclasses import dataclass
from typing import List, Optional, Any

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


class Cell:
    __slots__ = ('value', 'is_const')

    def __init__(self, value=None, is_const=False):
        self.value = value
        self.is_const = is_const


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


class EclInstance:
    def __init__(self, cls):
        self.cls = cls
        self.attrs = {}

    def __repr__(self):
        return f"<{self.cls.name} object>"


class EclFunction:
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


class EclClass:
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


NULL = NullValue()
_NO_MAGIC = object()
