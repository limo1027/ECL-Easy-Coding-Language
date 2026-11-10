from class_and_vars import *
from ast_parse import ParseError, Parser
from token_parse import split_token, LexerError
from errors import CheckError


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
