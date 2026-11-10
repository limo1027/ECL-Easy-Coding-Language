from token_parse import split_token, LexerError
from class_and_vars import *
from errors import ParseError


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
        if nxt and nxt.type in ('IDENTIFIER', 'TYPE'):
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
        if nxt and nxt.type in ('IDENTIFIER', 'TYPE'):
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
                if nxt and nxt.type in ('IDENTIFIER', 'TYPE'):
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
            if nxt and nxt.type in ('IDENTIFIER', 'TYPE'):
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
            if isinstance(left, (Variable, Attribute, Subscript)):
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
