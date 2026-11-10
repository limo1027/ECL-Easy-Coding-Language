from class_and_vars import KEYWORDS, OPERATORS
from errors import LexerError


class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type_, value, line, col):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, {self.line}, {self.col})"


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
