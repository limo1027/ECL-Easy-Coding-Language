from class_and_vars import *


class CompileError(Exception):
    def __init__(self, message, node=None):
        self.message = message
        self.node = node
        if node and hasattr(node, 'line'):
            super().__init__(f"[行 {node.line}, 列 {node.col}] {message}")
        else:
            super().__init__(message)


class Compiler:
    """AST -> 三地址码 IR"""

    BUILTIN_CALLS = {'print', 'str', 'len',
                     'int', 'float', 'bool', 'type', 'range'}

    def __init__(self, parent=None, aot_mode=False):
        self._parent = parent
        if parent is not None:
            self.aot_mode = parent.aot_mode
            self.var_types = dict(parent.var_types)
            self.func_sigs = parent.func_sigs
        else:
            self.aot_mode = aot_mode
            self.var_types = {}
            self.func_sigs = {}
        self.code = []
        self.exception_table = []
        self.temp_counter = 0
        self.label_counter = 0
        self.break_label = None
        self.continue_label = None
        self.temp_type = {}
        self.int_mode = False
        self._int_func_name = None
        self.last_expr_temp = None

    # ---------- 工具 ----------

    def _root(self):
        c = self
        while c._parent is not None:
            c = c._parent
        return c

    def new_temp(self, type_name=None):
        root = self._root()
        root.temp_counter += 1
        t = f"t{root.temp_counter}"
        if type_name is not None:
            root.temp_type[t] = type_name
        return t

    def new_label(self):
        root = self._root()
        root.label_counter += 1
        return f"L{root.label_counter}"

    def set_type(self, t, type_name):
        self._root().temp_type[t] = type_name

    def get_type(self, t):
        return self._root().temp_type.get(t)

    def emit(self, *instr):
        self.code.append(instr)

    def emit_label(self, name):
        self.code.append(('label', name))

    # ---------- 入口 ----------

    def compile_program(self, program):
        for stmt in program.body:
            if isinstance(stmt, FuncDefStmt):
                self.func_sigs[stmt.name] = (
                    [p.get('type') for p in stmt.params],
                    stmt.return_type,
                )
        self.last_expr_temp = None
        for stmt in program.body:
            if isinstance(stmt, ExprStmt):
                t = self.compile_expr(stmt.expr)
                self.last_expr_temp = t
            else:
                self.compile_stmt(stmt)
        self.emit('halt')
        return self.code, self.exception_table

    # ---------- 语句 ----------

    def compile_stmt(self, stmt):
        if self.int_mode:
            return self.compile_stmt_int(stmt)

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

    def compile_stmt_int(self, stmt):
        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                src = self.compile_expr_int(stmt.value)
                self.emit('int_ret', src)
            else:
                self.emit('int_ret_zero')
            return
        if isinstance(stmt, DefineStmt):
            if stmt.value is not None:
                src = self.compile_expr_int(stmt.value)
            else:
                src = ('imm', 0)
            self.emit('int_store_var', stmt.name, src)
            return
        if isinstance(stmt, IfStmt):
            end_label = self.new_label()
            cond = self.compile_expr_int(stmt.condition)
            next_label = self.new_label()
            self.emit('int_jz', cond, next_label)
            for s in stmt.body:
                self.compile_stmt_int(s)
            self.emit('goto', end_label)
            self.emit_label(next_label)
            for ec, eb in stmt.elifs:
                cond = self.compile_expr_int(ec)
                next_label = self.new_label()
                self.emit('int_jz', cond, next_label)
                for s in eb:
                    self.compile_stmt_int(s)
                self.emit('goto', end_label)
                self.emit_label(next_label)
            if stmt.else_body:
                for s in stmt.else_body:
                    self.compile_stmt_int(s)
            self.emit_label(end_label)
            return
        if isinstance(stmt, WhileStmt):
            start_label = self.new_label()
            end_label = self.new_label()
            self.emit_label(start_label)
            cond = self.compile_expr_int(stmt.condition)
            self.emit('int_jz', cond, end_label)
            for s in stmt.body:
                self.compile_stmt_int(s)
            self.emit('goto', start_label)
            self.emit_label(end_label)
            return
        if isinstance(stmt, ExprStmt):
            self.compile_expr_int(stmt.expr)
            return
        raise NotImplementedError(f"int_mode 不支持的语句: {type(stmt).__name__}")

    # ---------- 定义 ----------

    def compile_define(self, stmt):
        if stmt.is_ref:
            if isinstance(stmt.value, Variable):
                self.emit('ref', stmt.name, stmt.value.name)
                if stmt.value.name in self.var_types:
                    self.var_types[stmt.name] = self.var_types[stmt.value.name]
            else:
                raise CompileError("ref 必须绑定到变量", stmt)
            return
        if stmt.value is not None:
            src = self.compile_expr(stmt.value)
        else:
            src = self.new_temp('none')
            self.emit('const', src, None)
        if stmt.type_name:
            base = stmt.type_name.split('[')[0].strip().split()[0]
            self.var_types[stmt.name] = base
        elif self.get_type(src):
            self.var_types[stmt.name] = self.get_type(src)
        self.emit('store', stmt.name, src)

    # ---------- 函数 ----------

    def compile_func_def(self, stmt):
        sub = Compiler(parent=self)
        for p in stmt.params:
            if p.get('type'):
                sub.var_types[p['name']] = p['type']

        is_int_func = self.aot_mode and self._is_int_func(stmt)
        if is_int_func:
            sub.int_mode = True
            sub._int_func_name = stmt.name
            old_break = self.break_label
            old_continue = self.continue_label
            self.break_label = None
            self.continue_label = None
            for s in stmt.body:
                sub.compile_stmt_int(s)
            self.break_label = old_break
            self.continue_label = old_continue
            sub.emit('int_ret_zero')
            sub.emit('halt')
            self.emit('func_int', stmt.name, sub.code, stmt.params,
                      stmt.return_type)
            return

        old_break = self.break_label
        old_continue = self.continue_label
        self.break_label = None
        self.continue_label = None
        for s in stmt.body:
            sub.compile_stmt(s)
        self.break_label = old_break
        self.continue_label = old_continue
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

    def _is_int_func(self, stmt):
        if stmt.varargs or stmt.kwargs:
            return False
        if len(stmt.params) > 4:
            return False
        if stmt.return_type != 'int':
            return False
        for p in stmt.params:
            if p.get('type') != 'int':
                return False
        return self._body_is_int_only(stmt.body, stmt.name)

    def _body_is_int_only(self, stmts, fname):
        for s in stmts:
            if isinstance(s, ReturnStmt):
                if s.value is None:
                    return False
                if not self._expr_is_int_only(s.value, fname):
                    return False
            elif isinstance(s, DefineStmt):
                if s.type_name is None:
                    return False
                base = s.type_name.split('[')[0].strip().split()[0]
                if base != 'int':
                    return False
                if s.value is not None and not self._expr_is_int_only(s.value, fname):
                    return False
            elif isinstance(s, IfStmt):
                if not self._expr_is_int_only(s.condition, fname):
                    return False
                if not self._body_is_int_only(s.body, fname):
                    return False
                for ec, eb in s.elifs:
                    if not self._expr_is_int_only(ec, fname):
                        return False
                    if not self._body_is_int_only(eb, fname):
                        return False
                if not self._body_is_int_only(s.else_body, fname):
                    return False
            elif isinstance(s, WhileStmt):
                if not self._expr_is_int_only(s.condition, fname):
                    return False
                if not self._body_is_int_only(s.body, fname):
                    return False
            elif isinstance(s, ExprStmt):
                if not self._expr_is_int_only(s.expr, fname):
                    return False
            else:
                return False
        return True

    def _expr_is_int_only(self, expr, fname):
        if isinstance(expr, Literal):
            return isinstance(expr.value, int) and not isinstance(expr.value, bool)
        if isinstance(expr, Variable):
            return True
        if isinstance(expr, Binary):
            if expr.op not in ('+', '-', '*', '<', '>', '<=', '>=', '==', '!=', 'and', 'or'):
                return False
            return (self._expr_is_int_only(expr.left, fname) and
                    self._expr_is_int_only(expr.right, fname))
        if isinstance(expr, Unary):
            return expr.op in ('-', 'not') and self._expr_is_int_only(expr.right, fname)
        if isinstance(expr, IfExpr):
            return (self._expr_is_int_only(expr.condition, fname) and
                    self._expr_is_int_only(expr.then_expr, fname) and
                    self._expr_is_int_only(expr.else_expr, fname))
        if isinstance(expr, Assign):
            return (isinstance(expr.name, Variable) and
                    self._expr_is_int_only(expr.value, fname))
        if isinstance(expr, Call):
            if isinstance(expr.func, Variable) and expr.func.name == fname:
                return all(self._expr_is_int_only(a, fname) for a in expr.args)
            return False
        return False

    # ---------- 类 ----------

    def compile_class_def(self, stmt):
        methods = {}
        for s in stmt.body:
            if isinstance(s, FuncDefStmt):
                sub = Compiler(parent=self)
                # ★ 方法参数前插入 self
                method_params = [
                    {'name': 'self', 'type': None, 'default': None}] + s.params
                sub.var_types['self'] = None
                for p in s.params:
                    if p.get('type'):
                        sub.var_types[p['name']] = p['type']
                old_break = self.break_label
                old_continue = self.continue_label
                self.break_label = None
                self.continue_label = None
                for body_s in s.body:
                    sub.compile_stmt(body_s)
                self.break_label = old_break
                self.continue_label = old_continue
                sub.emit('return_null')
                sub.emit('halt')
                defaults = {}
                for p in s.params:
                    if p.get('default') is not None:
                        if isinstance(p['default'], Literal):
                            defaults[p['name']] = p['default'].value
                        else:
                            defaults[p['name']] = p['default']
                methods[s.name] = (sub.code, method_params, s.varargs,
                                   s.kwargs, s.return_type, defaults)
                self.emit('method_func', stmt.name, s.name, sub.code,
                          method_params, s.varargs, s.kwargs, s.return_type, defaults)
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
            iter_tmp = self.new_temp('int')
            self.emit('const', iter_tmp, 0)
            self.emit_label(start)
            cmp_tmp = self.new_temp('bool')
            self.emit('lt', cmp_tmp, iter_tmp, count_src)
            self.emit('if_not_goto', cmp_tmp, end)
            for s in stmt.body:
                self.compile_stmt(s)
            self.emit_label(continue_label)
            one = self.new_temp('int')
            self.emit('const', one, 1)
            next_tmp = self.new_temp('int')
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
                step_src = self.new_temp('int')
                self.emit('const', step_src, 1)
            iter_tmp = self.new_temp('int')
            self.emit('assign', iter_tmp, start_src)
            self.emit_label(start)
            cmp_tmp = self.new_temp('bool')
            op = 'le' if r.inclusive else 'lt'
            self.emit(op, cmp_tmp, iter_tmp, end_src)
            self.emit('if_not_goto', cmp_tmp, end)
            self.emit('store', stmt.variable, iter_tmp)
            for s in stmt.body:
                self.compile_stmt(s)
            self.emit_label(continue_label)
            next_tmp = self.new_temp('int')
            self.emit('add', next_tmp, iter_tmp, step_src)
            self.emit('assign', iter_tmp, next_tmp)
            self.emit('goto', start)
            self.emit_label(end)

        else:
            iterable_src = self.compile_expr(stmt.iterable)
            idx_tmp = self.new_temp('int')
            self.emit('const', idx_tmp, 0)
            self.emit_label(start)
            len_tmp = self.new_temp()
            self.emit('var', len_tmp, 'len')
            len_result = self.new_temp('int')
            self.emit('call', len_result, len_tmp, [iterable_src], {})
            cmp_tmp = self.new_temp('bool')
            self.emit('lt', cmp_tmp, idx_tmp, len_result)
            self.emit('if_not_goto', cmp_tmp, end)
            item_tmp = self.new_temp()
            self.emit('get_item', item_tmp, iterable_src, idx_tmp)
            self.emit('store', stmt.variable, item_tmp)
            for s in stmt.body:
                self.compile_stmt(s)
            self.emit_label(continue_label)
            one = self.new_temp('int')
            self.emit('const', one, 1)
            next_tmp = self.new_temp('int')
            self.emit('add', next_tmp, idx_tmp, one)
            self.emit('assign', idx_tmp, next_tmp)
            self.emit('goto', start)
            self.emit_label(end)

        self.break_label, self.continue_label = old_break, old_continue

    # ---------- try ----------

    def compile_try(self, stmt):
        except_label = self.new_label()
        finally_label = self.new_label()

        # 1. 尝试块开始
        self.emit('try', except_label, finally_label)
        for s in stmt.body:
            self.compile_stmt(s)
        self.emit('end_try', except_label, finally_label)

        # ★ 关键修复：发出真实的 except 标签
        self.emit_label(except_label)
        self.emit('except', except_label, finally_label)

        # 2. except 块代码
        for ec in stmt.excepts:
            for s in ec['body']:
                self.compile_stmt(s)

        # ★ 关键修复：发出真实的 finally 标签
        self.emit_label(finally_label)
        self.emit('finally', finally_label)

        # 3. finally 块代码
        if stmt.finally_body:
            for s in stmt.finally_body:
                self.compile_stmt(s)

    # ---------- 二元运算 ----------

    @staticmethod
    def _infer_binop_type(op, lt_type, rt_type):
        numeric = {'int', 'float', 'double'}
        if op in ('+', '-', '*', '/', '//', '%', '**'):
            if lt_type == 'int' and rt_type == 'int':
                return 'int'
            if lt_type in numeric and rt_type in numeric:
                return 'float'
            if op == '+' and lt_type == 'str' and rt_type == 'str':
                return 'str'
            return None
        if op in ('==', '=', '!=', '<', '>', '<=', '>=', 'and', 'or'):
            return 'bool'
        if op in ('|', '&', '^', '<<', '>>'):
            if lt_type == 'int' and rt_type == 'int':
                return 'int'
            return None
        return None

    @staticmethod
    def _can_inline(lt_type, rt_type):
        builtin = {'int', 'float', 'double', 'str', 'bool'}
        return lt_type in builtin and rt_type in builtin

    def compile_binary(self, expr):
        op = expr.op
        lt = self.compile_expr(expr.left)
        rt = self.compile_expr(expr.right)

        if op == 'and':
            t = self.new_temp('bool')
            end_label = self.new_label()
            end2 = self.new_label()
            self.emit('jz', lt, end_label)
            self.emit('assign', t, rt)
            self.emit('goto', end2)
            self.emit_label(end_label)
            self.emit('assign', t, lt)
            self.emit_label(end2)
            return t

        if op == 'or':
            t = self.new_temp('bool')
            end_label = self.new_label()
            end2 = self.new_label()
            self.emit('jnz', lt, end_label)
            self.emit('assign', t, rt)
            self.emit('goto', end2)
            self.emit_label(end_label)
            self.emit('assign', t, lt)
            self.emit_label(end2)
            return t

        lt_type = self.get_type(lt)
        rt_type = self.get_type(rt)
        result_type = self._infer_binop_type(op, lt_type, rt_type)

        method_map = {
            '+': ('__add__', '__radd__', 'add'),
            '-': ('__sub__', '__rsub__', 'sub'),
            '*': ('__mul__', '__rmul__', 'mul'),
            '/': ('__truediv__', '__rtruediv__', 'div'),
            '//': ('__floordiv__', '__rfloordiv__', 'floordiv'),
            '%': ('__mod__', '__rmod__', 'mod'),
            '**': ('__pow__', '__rpow__', 'pow'),
            '=': ('__eq__', '__eq__', 'eq'),
            '==': ('__eq__', '__eq__', 'eq'),
            '!=': ('__ne__', '__ne__', 'ne'),
            '<': ('__lt__', '__gt__', 'lt'),
            '>': ('__gt__', '__lt__', 'gt'),
            '<=': ('__le__', '__ge__', 'le'),
            '>=': ('__ge__', '__le__', 'ge'),
            '|': ('__bor__', '__ror__', 'bor'),
            '&': ('__band__', '__rand__', 'band'),
            '^': ('__xor__', '__rxor__', 'xor'),
            '<<': ('__lshift__', '__rlshift__', 'lshift'),
            '>>': ('__rshift__', '__rrshift__', 'rshift'),
        }
        if op not in method_map:
            raise CompileError(f"未知二元运算符: {op}", expr)
        m, rm, native = method_map[op]
        return self._compile_binary_with_magic(lt, rt, m, rm, native,
                                               lt_type, rt_type, result_type)

    def _compile_binary_with_magic(self, lt, rt, method, reverse_method,
                                   native_op, lt_type, rt_type, result_type):
        if self._can_inline(lt_type, rt_type):
            t = self.new_temp(result_type)
            self.emit(native_op, t, lt, rt)
            return t

        t = self.new_temp(result_type)
        end_label = self.new_label()

        m = self.new_temp()
        self.emit('get_attr', m, lt, method)
        no_m = self.new_label()
        self.emit('jz', m, no_m)
        r = self.new_temp()
        self.emit('call', r, m, [rt], {})
        self.emit('assign', t, r)
        self.emit('jnz', r, end_label)
        self.emit_label(no_m)

        rm = self.new_temp()
        self.emit('get_attr', rm, rt, reverse_method)
        no_rm = self.new_label()
        self.emit('jz', rm, no_rm)
        r2 = self.new_temp()
        self.emit('call', r2, rm, [lt], {})
        self.emit('assign', t, r2)
        self.emit('jnz', r2, end_label)
        self.emit_label(no_rm)

        self.emit(native_op, t, lt, rt)
        self.emit_label(end_label)
        return t

    # ---------- 表达式（Value 版） ----------

    def compile_expr(self, expr):
        if isinstance(expr, Literal):
            v = expr.value
            t = self.new_temp(self._infer_literal_type(v))
            self.emit('const', t, v)
            return t

        if isinstance(expr, Variable):
            vt = self.var_types.get(expr.name)
            t = self.new_temp(vt)
            self.emit('var', t, expr.name)
            return t

        if isinstance(expr, Binary):
            return self.compile_binary(expr)

        if isinstance(expr, Unary):
            src = self.compile_expr(expr.right)
            src_type = self.get_type(src)
            t = self.new_temp(src_type)
            if expr.op == '-':
                m = self.new_temp()
                self.emit('get_attr', m, src, '__neg__')
                no_m = self.new_label()
                self.emit('jz', m, no_m)
                r = self.new_temp()
                self.emit('call', r, m, [], {})
                self.emit('assign', t, r)
                end_label = self.new_label()
                self.emit('jnz', r, end_label)
                self.emit_label(no_m)
                self.emit('neg', t, src)
                self.emit_label(end_label)
            elif expr.op == '~':
                m = self.new_temp()
                self.emit('get_attr', m, src, '__invert__')
                no_m = self.new_label()
                self.emit('jz', m, no_m)
                r = self.new_temp()
                self.emit('call', r, m, [], {})
                self.emit('assign', t, r)
                end_label = self.new_label()
                self.emit('jnz', r, end_label)
                self.emit_label(no_m)
                self.emit('invert', t, src)
                self.emit_label(end_label)
            elif expr.op in ('!', 'not'):
                self.emit('not', t, src)
            else:
                raise CompileError(f"未知一元运算符: {expr.op}", expr)
            return t

        if isinstance(expr, Assign):
            val = self.compile_expr(expr.value)
            val_type = self.get_type(val)
            if isinstance(expr.name, Variable):
                self.emit('store', expr.name.name, val)
                if val_type:
                    self.var_types[expr.name.name] = val_type
            elif isinstance(expr.name, Attribute):
                obj = self.compile_expr(expr.name.obj)
                self.emit('set_attr', obj, expr.name.attr, val)
            elif isinstance(expr.name, Subscript):
                obj_src = self.compile_expr(expr.name.obj)
                idx_src = self.compile_expr(expr.name.index)
                self.emit('set_item', obj_src, idx_src, val)
            return val

        if isinstance(expr, Call):
            if (isinstance(expr.func, Variable)
                    and expr.func.name == 'code'
                    and len(expr.args) == 1
                    and isinstance(expr.args[0], Literal)
                    and isinstance(expr.args[0].value, str)):
                src = expr.args[0].value
                t = self.new_temp('code')
                self.emit('new_code', t, src)
                return t
            if (isinstance(expr.func, Variable)
                    and expr.func.name == 'code'
                    and len(expr.args) == 1
                    and not (isinstance(expr.args[0], Literal)
                             and isinstance(expr.args[0].value, str))):
                arg = self.compile_expr(expr.args[0])
                t = self.new_temp('code')
                self.emit('new_code_var', t, arg)
                return t
            if isinstance(expr.func, Variable) and expr.func.name in self.BUILTIN_CALLS:
                args = [self.compile_expr(a) for a in expr.args]
                ret_type = {
                    'print': 'none', 'str': 'str', 'len': 'int',
                    'int': 'int', 'float': 'float', 'bool': 'bool',
                    'type': 'str', 'range': 'list',
                }.get(expr.func.name)
                t = self.new_temp(ret_type)
                self.emit(expr.func.name, t, args)
                return t
            func = self.compile_expr(expr.func)
            args = [self.compile_expr(a) for a in expr.args]
            kwargs = {k: self.compile_expr(v) for k, v in expr.kwargs}
            ret_type = None
            if isinstance(expr.func, Variable):
                sig = self.func_sigs.get(expr.func.name)
                if sig:
                    ret_type = sig[1]
            t = self.new_temp(ret_type)
            self.emit('call', t, func, args, kwargs)
            return t

        if isinstance(expr, Attribute):
            obj = self.compile_expr(expr.obj)
            t = self.new_temp(None)
            self.emit('get_attr', t, obj, expr.attr)
            return t

        if isinstance(expr, IfExpr):
            cond = self.compile_expr(expr.condition)
            t = self.new_temp(None)
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
            t = self.new_temp('list')
            self.emit('new_list', t)
            for e in expr.elements:
                e_src = self.compile_expr(e)
                self.emit('list_append', t, e_src)
            return t

        if isinstance(expr, DictExpr):
            t = self.new_temp('dict')
            self.emit('new_dict', t)
            for k, v in expr.items:
                k_src = self.compile_expr(k)
                v_src = self.compile_expr(v)
                self.emit('dict_set', t, k_src, v_src)
            return t

        if isinstance(expr, Subscript):
            obj = self.compile_expr(expr.obj)
            idx = self.compile_expr(expr.index)
            t = self.new_temp(None)
            self.emit('get_item', t, obj, idx)
            return t

        if isinstance(expr, RangeExpr):
            start = self.compile_expr(expr.start)
            end = self.compile_expr(expr.end)
            step = self.compile_expr(expr.step) if expr.step else None
            t = self.new_temp('list')
            self.emit('new_range', t, start, end, expr.inclusive, step)
            return t

        if isinstance(expr, CodeLiteral):
            t = self.new_temp('code')
            self.emit('new_code', t, expr.source)
            return t

        if isinstance(expr, Swap):
            lt = self.new_temp(None)
            self.emit('var', lt, expr.left)
            rt = self.new_temp(None)
            self.emit('var', rt, expr.right)
            self.emit('store', expr.left, rt)
            self.emit('store', expr.right, lt)
            return lt

        raise NotImplementedError(f"未实现的表达式: {type(expr).__name__}")

    @staticmethod
    def _infer_literal_type(value):
        if isinstance(value, bool):
            return 'bool'
        if isinstance(value, int):
            return 'int'
        if isinstance(value, float):
            return 'float'
        if isinstance(value, str):
            return 'str'
        if value is None:
            return 'none'
        return None

    # ---------- 表达式（int 特化） ----------

    def compile_expr_int(self, expr):
        if isinstance(expr, Literal):
            if isinstance(expr.value, bool):
                return ('imm', int(expr.value))
            return ('imm', expr.value)

        if isinstance(expr, Variable):
            return ('reg', expr.name)

        if isinstance(expr, Binary):
            op = expr.op
            if op in ('+', '-', '*', '<', '>', '<=', '>=', '==', '!='):
                lt = self.compile_expr_int(expr.left)
                rt = self.compile_expr_int(expr.right)
                t = self.new_temp('int')
                int_op = {
                    '+': 'int_add', '-': 'int_sub', '*': 'int_mul',
                    '<': 'int_lt', '>': 'int_gt', '<=': 'int_le',
                    '>=': 'int_ge', '==': 'int_eq', '!=': 'int_ne',
                }[op]
                self.emit(int_op, t, lt, rt)
                return ('tmp', t)
            if op == 'and':
                lt = self.compile_expr_int(expr.left)
                rt = self.compile_expr_int(expr.right)
                t = self.new_temp('int')
                self.emit('int_and', t, lt, rt)
                return ('tmp', t)
            if op == 'or':
                lt = self.compile_expr_int(expr.left)
                rt = self.compile_expr_int(expr.right)
                t = self.new_temp('int')
                self.emit('int_or', t, lt, rt)
                return ('tmp', t)
            raise CompileError(f"int_mode 不支持的二元运算符: {op}", expr)

        if isinstance(expr, Unary):
            src = self.compile_expr_int(expr.right)
            t = self.new_temp('int')
            if expr.op == '-':
                self.emit('int_neg', t, src)
            elif expr.op == 'not':
                self.emit('int_not', t, src)
            else:
                raise CompileError(f"int_mode 不支持的一元运算符: {expr.op}", expr)
            return ('tmp', t)

        if isinstance(expr, IfExpr):
            cond = self.compile_expr_int(expr.condition)
            t = self.new_temp('int')
            else_label = self.new_label()
            end_label = self.new_label()
            self.emit('int_jz', cond, else_label)
            then_src = self.compile_expr_int(expr.then_expr)
            self.emit('int_assign', t, then_src)
            self.emit('goto', end_label)
            self.emit_label(else_label)
            else_src = self.compile_expr_int(expr.else_expr)
            self.emit('int_assign', t, else_src)
            self.emit_label(end_label)
            return ('tmp', t)

        if isinstance(expr, Assign):
            val = self.compile_expr_int(expr.value)
            if isinstance(expr.name, Variable):
                self.emit('int_store_var', expr.name.name, val)
            return val

        if isinstance(expr, Call):
            if isinstance(expr.func, Variable):
                fname = expr.func.name
                if fname == self._int_func_name:
                    args = [self.compile_expr_int(a) for a in expr.args]
                    t = self.new_temp('int')
                    self.emit('int_call', t, fname, args)
                    return ('tmp', t)
            raise CompileError(
                "int_mode 不支持的调用（只支持递归调用自身）", expr)

        raise CompileError(f"int_mode 不支持的表达式: {type(expr).__name__}", expr)
