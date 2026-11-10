class EclException(Exception):
    def __init__(self, exc_type, message, cause=None, line=0, col=0):
        self.exc_type = exc_type
        self.message = message
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {exc_type}: {message}")
        else:
            super().__init__(f"{exc_type}: {message}")


class CheckError(Exception):
    def __init__(self, message, line=0, col=0):
        self.message = message
        self.line = line
        self.col = col
        if line:
            super().__init__(f"[行 {line}, 列 {col}] {message}")
        else:
            super().__init__(message)


class ParseError(Exception):
    def __init__(self, message, line, col):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"[行 {line}, 列 {col}] {message}")


class LexerError(Exception):
    def __init__(self, message, line, col):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"[行 {line}, 列 {col}] {message}")


class ConstChangingError(EclException):
    pass


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value
