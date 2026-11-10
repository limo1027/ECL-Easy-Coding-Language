#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECL (Easy Control Language) 解释器完整实现
包含：词法分析、语法解析、类型检查、解释执行
"""

import sys
from token_parse import split_token
from ast_parse import Parser
from class_and_vars import NULL
from checker import Checker, CheckError
from compiler import Compiler
from errors import EclException, LexerError, ParseError
from interpreter import Interpreter
from asm import AsmGenerator


def run_ecl(code, without_check=False):
    """完整执行 ECL 代码：词法 -> 语法 -> 类型检查 -> 编译 -> VM执行"""
    # 1. 词法分析
    try:
        tokens = split_token(code)
    except LexerError as e:
        print(f"词法错误: {e}", file=sys.stderr)
        return None

    # 2. 语法分析
    try:
        parser = Parser(tokens)
        program = parser.parse()
    except ParseError as e:
        import traceback
        traceback.print_exc()
        print(f"语法错误: {e}", file=sys.stderr)
        return None

    # 3. 静态检查
    try:
        checker = Checker()
        if not without_check:
            checker.check(program)
    except CheckError as e:
        print(f"静态检查错误: {e}", file=sys.stderr)
        return None

    # 4. 编译为字节码 (IR)
    compiler = Compiler(aot_mode=False)
    code_ir, exception_table = compiler.compile_program(program)

    # 5. 实例化解释器并执行
    interp = Interpreter()
    try:
        # ★ 调用 Interpreter 的纯执行接口，把 VM 跑起来
        interp.run_bytecode(
            code_ir, exception_table)
    except EclException as e:
        print(f"运行时错误: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"内部错误: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    # 如果是 REPL，返回最后的求值结果
    return interp


if __name__ == '__main__':
    import argparse
    import pathlib
    import subprocess
    import sys

    def format_repl_value(v):
        if v is NULL:
            return "null"
        if v is None:
            return "none"
        if isinstance(v, bool):
            return "True" if v else "False"
        return str(v)

    parser = argparse.ArgumentParser(
        prog='ecl',
        description='ECL (Easy Control Language) 解释器 / AOT 编译器',
    )
    parser.add_argument(
        'source',
        nargs='?',
        type=pathlib.Path,
        help='输入 .ecl 文件路径（省略则进入交互式 REPL）',
    )
    parser.add_argument(
        '-c', '--code',
        type=str,
        default=None,
        help='直接执行一段 ECL 代码（与 source 互斥）',
    )
    parser.add_argument(
        '--without-check',
        action='store_true',
        help='跳过静态检查',
    )
    parser.add_argument(
        '--compile',
        action='store_true',
        help='编译到汇编 / 可执行文件',
    )
    parser.add_argument(
        '--target',
        choices=['asm', 'exe'],
        default='asm',
        help='目标：asm（只生成 .asm）/ exe（生成 .exe）',
    )
    parser.add_argument(
        '-o', '--output',
        type=pathlib.Path,
        help='输出文件（.asm / .exe）',
    )
    parser.add_argument(
        '--msvc-bin',
        type=pathlib.Path,
        default=pathlib.Path(
            r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.40.33807\bin\Hostx64\x64'),
        help='MSVC 工具链目录（ml64.exe / cl.exe / link.exe）',
    )
    parser.add_argument(
        '--no-crt',
        action='store_true',
        help='无 CRT 链接（极小体积，需要 runtime.c 是无 CRT 版）',
    )
    args = parser.parse_args()

    # ---------- 取源码 ----------
    if args.code is not None and args.source is not None:
        print("错误：-c/--code 和 source 不能同时指定", file=sys.stderr)
        sys.exit(2)

    if args.code is not None:
        content = args.code
        input_path = None
    elif args.source is not None:
        if not args.source.exists():
            print(f"错误：文件不存在: {args.source}", file=sys.stderr)
            sys.exit(1)
        content = args.source.read_text(encoding='utf-8')
        input_path = args.source
    else:
        content = None
        input_path = None

    # ---------- 交互式 REPL ----------
    if content is None:
        interp = Interpreter()
        print("ECL 交互式解释器（输入 exit 或 Ctrl-D 退出；空行执行块）")
        buffer = []

        def repl_exec(src):
            tokens = split_token(src)
            p = Parser(tokens)
            program = p.parse()
            if not args.without_check:
                Checker().check(program)
            result = interp.interpret(program)
            if result is not None and result is not NULL:
                print(format_repl_value(result))

        def block_depth(buf):
            depth = 0
            for b in buf:
                s = b.strip()
                if not s or s.startswith('#'):
                    continue
                first = s.split()[0] if s.split() else ''
                if first in ('def', 'if', 'for', 'while', 'class',
                             'try', 'with', 'match', 'using'):
                    depth += 1
                elif first == 'end':
                    depth -= 1
            return depth

        BLOCK_KEYWORDS = ('def', 'if', 'for', 'while', 'class',
                          'try', 'with', 'match', 'using', 'end',
                          'else', 'elif', 'except', 'finally', 'case')

        while True:
            prompt = ">>> " if not buffer else "... "
            try:
                line = input(prompt)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            stripped = line.strip()

            if not buffer and stripped in ('exit', 'quit', 'exit()', 'quit()'):
                break

            if not stripped:
                if buffer:
                    d = block_depth(buffer)
                    if d > 0:
                        buffer.extend(['end'] * d)
                    try:
                        repl_exec("\n".join(buffer))
                    except LexerError as e:
                        print(f"词法错误: {e}", file=sys.stderr)
                    except ParseError as e:
                        print(f"语法错误: {e}", file=sys.stderr)
                    except CheckError as e:
                        print(f"静态检查错误: {e}", file=sys.stderr)
                    except EclException as e:
                        print(f"运行时错误: {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"内部错误: {type(e).__name__}: {e}",
                              file=sys.stderr)
                    buffer.clear()
                continue

            buffer.append(line)

            # 单行非块语句直接执行，不等待空行
            if len(buffer) == 1 and not stripped.endswith(':'):
                first = stripped.split()[0] if stripped.split() else ''
                if first not in BLOCK_KEYWORDS:
                    try:
                        repl_exec(stripped)
                    except LexerError as e:
                        print(f"词法错误: {e}", file=sys.stderr)
                    except ParseError as e:
                        print(f"语法错误: {e}", file=sys.stderr)
                    except CheckError as e:
                        print(f"静态检查错误: {e}", file=sys.stderr)
                    except EclException as e:
                        print(f"运行时错误: {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"内部错误: {type(e).__name__}: {e}",
                              file=sys.stderr)
                    buffer.clear()
                    continue
        sys.exit(0)

    # ---------- 编译模式 ----------
    if args.compile:
        try:
            tokens = split_token(content)
        except LexerError as e:
            print(f"词法错误: {e}", file=sys.stderr)
            sys.exit(1)

        try:
            p = Parser(tokens)
            program = p.parse()
        except ParseError as e:
            print(f"语法错误: {e}", file=sys.stderr)
            sys.exit(1)

        try:
            checker = Checker()
            if not args.without_check:
                checker.check(program)
        except CheckError as e:
            print(f"静态检查错误: {e}", file=sys.stderr)
            sys.exit(1)

        compiler = Compiler(aot_mode=True)
        ir, exception_table = compiler.compile_program(program)

        gen = AsmGenerator(ir)
        asm = gen.generate()

        if args.output:
            asm_file = args.output.with_suffix('.asm')
        elif input_path is not None:
            asm_file = input_path.with_suffix('.asm')
        else:
            asm_file = pathlib.Path('a.asm')
        asm_file.parent.mkdir(parents=True, exist_ok=True)
        asm_file.write_text(asm, encoding='utf-8')
        print(f"生成汇编: {asm_file}")

        if args.target == 'asm':
            sys.exit(0)

        obj_file = asm_file.with_suffix('.obj')
        ml64 = args.msvc_bin / 'ml64.exe'
        cl = args.msvc_bin / 'cl.exe'
        link = args.msvc_bin / 'link.exe'

        if not ml64.exists():
            print(f"找不到 ml64.exe: {ml64}", file=sys.stderr)
            sys.exit(1)

        # 1. 汇编用户代码
        subprocess.run(
            [str(ml64), '/c', f'/Fo{obj_file}', str(asm_file)],
            check=True)

        # 2. 汇编 setjmp.asm
        setjmp_asm = pathlib.Path(__file__).parent / 'setjmp.asm'
        setjmp_obj = pathlib.Path(__file__).parent / 'setjmp.obj'
        if not setjmp_asm.exists():
            print(f"找不到 setjmp.asm: {setjmp_asm}", file=sys.stderr)
            sys.exit(1)

        need_build_setjmp = (
            not setjmp_obj.exists()
            or setjmp_asm.stat().st_mtime > setjmp_obj.stat().st_mtime
        )
        if need_build_setjmp:
            subprocess.run(
                [str(ml64), '/c', f'/Fo{setjmp_obj}', str(setjmp_asm)],
                check=True)

        # 3. 编译 runtime.c
        runtime_c = pathlib.Path(__file__).parent / 'runtime.c'
        runtime_obj = pathlib.Path(__file__).parent / 'runtime.obj'
        need_rebuild = (
            not runtime_obj.exists()
            or runtime_c.stat().st_mtime > runtime_obj.stat().st_mtime
        )
        if need_rebuild:
            if args.no_crt:
                subprocess.run([str(cl), '/c', '/O1', '/GS-', '/nologo', "/Zl", '/utf-8',
                                str(runtime_c), f'/Fo{runtime_obj}'], check=True)
            else:
                subprocess.run([str(cl), '/c', '/O2', '/nologo', '/utf-8',
                                str(runtime_c), f'/Fo{runtime_obj}'], check=True)

        if args.output:
            exe_file = args.output.with_suffix('.exe')
        elif input_path is not None:
            exe_file = input_path.with_suffix('.exe')
        else:
            exe_file = pathlib.Path('a.exe')
        exe_file.parent.mkdir(parents=True, exist_ok=True)

        # 4. 链接 (加入 setjmp.obj)
        if args.no_crt:
            link_args = [
                str(link),
                str(obj_file),
                str(runtime_obj),
                str(setjmp_obj),        # ★ 加入 setjmp.obj
                f'/OUT:{exe_file}',
                '/SUBSYSTEM:CONSOLE',
                '/NODEFAULTLIB',
                '/ENTRY:startup',
                '/DEBUG:NONE',
                '/OPT:REF',
                '/OPT:ICF',
                'kernel32.lib',
            ]
        else:
            link_args = [
                str(link),
                str(obj_file),
                str(runtime_obj),
                str(setjmp_obj),        # ★ 加入 setjmp.obj
                f'/OUT:{exe_file}',
                '/SUBSYSTEM:CONSOLE',
            ]

        subprocess.run(link_args, check=True)
        print(f"生成可执行文件: {exe_file}")
        sys.exit(0)

    # ---------- 解释模式 ----------
    run_ecl(content, without_check=args.without_check)
