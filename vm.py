from errors import EclException, LexerError, ReturnSignal
from class_and_vars import NULL, Cell, EclInstance, Program, EclFunction, EclClass
from token_parse import split_token
from ast_parse import Parser, ParseError


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
        from compiler import Compiler
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

        if kind == 'method_func':
            return

        elif kind == 'try':
            except_label = op[1]
            finally_label = op[2]

            try:
                # 手动接管执行
                while self.pc < len(self.code):
                    cur_op = self.code[self.pc]

                    # 遇到 except 块，说明完美结束，跳到 finally 的标签
                    if cur_op[0] == 'label' and cur_op[1] == except_label:
                        self.pc = self.labels[finally_label]
                        return

                    # 遇到 finally 块，直接结束
                    if cur_op[0] == 'label' and cur_op[1] == finally_label:
                        return

                    self.pc += 1
                    self.exec_op(cur_op)
            except EclException:
                # 捕获到异常，直接跳到 except 的标签处
                self.pc = self.labels[except_label]
                return

        elif kind == 'end_try':
            except_label = op[1]
            finally_label = op[2]
            # 正常结束，跳到 finally 的标签
            self.pc = self.labels[finally_label]
            return

        elif kind == 'except':
            # ★ 删掉跳转逻辑，让程序自然往下执行！
            return

        elif kind == 'finally':
            # ★ 什么都不做，自然往下执行
            return

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
            self.temps[dest] = self.temps[src1] - self.temps[src2]
        elif kind == 'mul':
            _, dest, src1, src2 = op
            self.temps[dest] = self.temps[src1] * self.temps[src2]
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
        elif kind == 'neg':
            _, dest, src = op
            self.temps[dest] = -self.temps[src]
        elif kind == 'invert':
            _, dest, src = op
            self.temps[dest] = ~self.temps[src]
        elif kind == 'not':
            _, dest, src = op
            self.temps[dest] = not self.interpreter._truthy(self.temps[src])

        elif kind == 'new_code_var':
            _, dest, src = op
            src_val = self.temps[src]
            if isinstance(src_val, str):
                self.temps[dest] = CodeObject(
                    src_val, self.scope, self.interpreter)
            else:
                self.interpreter.error(
                    f"code() 的参数必须是 str，得到 {type(src_val).__name__}",
                    None, 'TypeError')

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
        elif kind == 'jz':
            _, src, label = op
            if not self.interpreter._truthy(self.temps[src]):
                self.pc = self.labels[label]
        elif kind == 'jnz':
            _, src, label = op
            if self.interpreter._truthy(self.temps[src]):
                self.pc = self.labels[label]
        elif kind == 'label':
            pass

        elif kind == 'call':
            _, dest, func_src, args, kwargs = op
            func = self.temps[func_src]
            arg_vals = [self.temps[a] for a in args]
            kwarg_vals = {k: self.temps[v] for k, v in kwargs.items()}
            self.temps[dest] = self.interpreter.call_value(
                func, arg_vals, kwarg_vals)

        # ---------- 内置函数 ----------
        elif kind == 'print':
            _, dest, args = op
            out = []
            for a in args:
                v = self.temps[a]
                if v is None:
                    out.append("none")
                elif v is NULL:
                    out.append("null")
                elif isinstance(v, EclInstance):
                    method = v.cls.methods.get('__str__')
                    if method:
                        r = self.interpreter.call_method_ir(method, v, [], {})
                        out.append("none" if r is None else (
                            "null" if r is NULL else str(r)))
                    else:
                        out.append(repr(v))
                else:
                    out.append(str(v))
            print(' '.join(out))
            self.temps[dest] = None

        elif kind == 'str':
            _, dest, args = op
            if args:
                self.temps[dest] = self.interpreter._builtin_str(
                    self.temps[args[0]])
            else:
                self.temps[dest] = ""

        elif kind == 'len':
            _, dest, args = op
            if args:
                self.temps[dest] = self.interpreter._builtin_len(
                    self.temps[args[0]])
            else:
                self.temps[dest] = 0

        elif kind == 'int':
            _, dest, args = op
            if args:
                self.temps[dest] = self.interpreter._builtin_int(
                    self.temps[args[0]])
            else:
                self.temps[dest] = 0

        elif kind == 'float':
            _, dest, args = op
            if args:
                self.temps[dest] = self.interpreter._builtin_float(
                    self.temps[args[0]])
            else:
                self.temps[dest] = 0.0

        elif kind == 'bool':
            _, dest, args = op
            if args:
                self.temps[dest] = self.interpreter._builtin_bool(
                    self.temps[args[0]])
            else:
                self.temps[dest] = False

        elif kind == 'type':
            _, dest, args = op
            if args:
                self.temps[dest] = self.interpreter._builtin_type(
                    self.temps[args[0]])
            else:
                self.temps[dest] = "none"

        elif kind == 'range':
            _, dest, args = op
            vals = [self.temps[a] for a in args]
            self.temps[dest] = self.interpreter._builtin_range(*vals)

        elif kind == 'return':
            _, src = op
            raise ReturnSignal(self.temps[src])
        elif kind == 'return_none':
            raise ReturnSignal(None)
        elif kind == 'return_null':
            raise ReturnSignal(NULL)

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

        elif kind == 'func':
            _, name, sub_code, params, varargs, kwargs_name, ret_type, defaults = op
            fn = EclFunction(name, sub_code, params, varargs, kwargs_name,
                             ret_type, self.interpreter, defaults)
            self.scope[name] = Cell(fn)

        elif kind == 'class':
            _, name, bases, methods = op
            cls = EclClass(name, bases, methods, self.interpreter)
            self.scope[name] = Cell(cls)

        elif kind == 'new_code':
            _, dest, source = op
            self.temps[dest] = CodeObject(source, self.scope, self.interpreter)

        elif kind == 'raise':
            _, src = op
            exc = self.temps[src]
            if isinstance(exc, EclException):
                raise exc
            if hasattr(exc, 'exc_type'):
                msg = getattr(exc, 'message', str(exc))
                raise EclException(exc.exc_type, msg)
            raise EclException('Exception', str(exc))

        elif kind == 'halt':
            self.pc = len(self.code)

        else:
            raise EclException('RuntimeError', f"未知指令: {kind}")
