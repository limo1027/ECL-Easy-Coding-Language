from class_and_vars import EclInstance, Cell, NULL, _NO_MAGIC, MAGIC_METHODS, REVERSE_METHODS, EclClass, EclFunction
from vm import CodeObject, GlobalView, VM
from compiler import Compiler
from errors import EclException, ReturnSignal


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
        if v is NotImplemented:
            return False
        if v is None:
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
        if isinstance(left, (EclInstance, EclClass)):
            result = self.call_magic(left, method_name, [right])
            if result is not _NO_MAGIC and result is not NULL:
                return result
        if isinstance(right, (EclInstance, EclClass)):
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
        if isinstance(obj, EclClass):
            method_stmt = obj.methods.get(method_name)
            if method_stmt is not None:
                if len(method_stmt) == 6:
                    code, params, varargs, kwargs, ret, defaults = method_stmt
                else:
                    code, params, varargs, kwargs, ret = method_stmt
                    defaults = {}
                fn = EclFunction(method_name, code, params, varargs,
                                 kwargs, ret, self, defaults)
                return self.call_function_ir(fn, args, {})
            return _NO_MAGIC
        return _NO_MAGIC

    def get_attr(self, obj, name):
        # ---------- CodeObject ----------
        if isinstance(obj, CodeObject):
            if name == 'run':
                return obj.run
            self.error(f"code 对象没有属性 '{name}'", None, 'AttributeError')

        # ---------- GlobalView ----------
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

        # ---------- EclInstance ----------
        if isinstance(obj, EclInstance):
            if name in obj.attrs:
                return obj.attrs[name]
            if name in obj.cls.methods:
                method_stmt = obj.cls.methods[name]
                return lambda *a, **kw: self.call_method_ir(method_stmt, obj, a, kw)
            # 魔法方法没有，返回 NULL（让 jz 跳到 no_m，试反向 / 原生）
            if name.startswith('__') and name.endswith('__'):
                return NULL
            self.error(f"对象 '{obj.cls.name}' 没有属性 '{name}'",
                       None, 'AttributeError')

        # ---------- EclClass ----------
        if isinstance(obj, EclClass):
            if name in obj.methods:
                method_stmt = obj.methods[name]
                if len(method_stmt) == 6:
                    code, params, varargs, kwargs, ret, defaults = method_stmt
                else:
                    code, params, varargs, kwargs, ret = method_stmt
                    defaults = {}
                fn = EclFunction(name, code, params, varargs,
                                 kwargs, ret, self, defaults)
                return lambda *a, **kw: self.call_function_ir(fn, a, kw)
            if name.startswith('__') and name.endswith('__'):
                return NULL
            self.error(f"类 '{obj.name}' 没有属性 '{name}'", None, 'AttributeError')

        # ---------- 原生类型 ----------
        # ECL 用 __div__ / __rdiv__，Python 3 用 __truediv__ / __rtruediv__
        DIV_MAP = {
            '__div__': '__truediv__',
            '__rdiv__': '__rtruediv__',
        }

        try:
            return getattr(obj, name)
        except AttributeError:
            if name in DIV_MAP:
                try:
                    return getattr(obj, DIV_MAP[name])
                except AttributeError:
                    return NULL
            if name.startswith('__') and name.endswith('__'):
                return NULL
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
            fn = EclFunction('__method__', code, params, varargs,
                             kwargs_name, ret, self, defaults)
            return self.call_function_ir(fn, (instance,) + tuple(args), kwargs)
        self.error("call_method_ir 不支持 AST 版方法", None)

    def run_bytecode(self, code, exception_table):
        """纯粹的 IR 执行入口"""
        vm = VM(code, exception_table, self.globals, self)
        try:
            vm.run()
        except ReturnSignal:
            pass
        return None
