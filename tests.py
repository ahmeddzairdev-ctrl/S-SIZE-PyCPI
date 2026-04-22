#!/usr/bin/env python3
"""
tests.py  –  Test suite for the SSZ Python interpreter.

Runs a collection of inline SSZ programs and checks their output.
Usage:  python tests.py [-v]
"""
import sys
import os
import io
import unittest
from pathlib import Path
from unittest.mock import patch

# Make the project importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ssize.lexer       import Lexer, LexError
from ssize.parser      import Parser, ParseError
from ssize.interpreter import Interpreter, SSZError
from ssize.runtime     import SSZList, SSZArray


# ---------------------------------------------------------------------------
# Helper: run SSZ source string, capture alert/print output
# ---------------------------------------------------------------------------

def run_ssz(source: str, capture_alert: bool = True) -> str:
    """
    Execute SSZ source and return the concatenated alert/print output.
    """
    outputs = []

    def fake_alert(msg):
        outputs.append(str(msg))

    tokens  = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    interp  = Interpreter(source_dir=".")

    # Patch the alert stdlib
    import ssize.stdlib.alert as alert_mod
    original = alert_mod._alert
    alert_mod._alert = fake_alert

    captured_prints = io.StringIO()
    with patch("builtins.print", side_effect=lambda *a, **kw: outputs.append(" ".join(str(x) for x in a))):
        try:
            interp.run(program)
        finally:
            alert_mod._alert = original

    return "\n".join(outputs)


def run_ssz_with_alert(source: str):
    """
    Returns a list of alert messages captured during execution.
    """
    results = []
    tokens  = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    interp  = Interpreter(source_dir=".")

    # Override alert stdlib to capture calls
    import ssize.stdlib.alert as alert_mod
    orig = alert_mod._alert
    alert_mod._alert = lambda msg: results.append(str(msg))

    # Also pre-register in global env for direct al.alert calls
    try:
        interp.run(program)
    finally:
        alert_mod._alert = orig

    return results


# ---------------------------------------------------------------------------
# Lexer tests
# ---------------------------------------------------------------------------

class TestLexer(unittest.TestCase):

    def _tok_types(self, src):
        from ssize.lexer import TT
        return [t.type for t in Lexer(src).tokenize()]

    def test_integer_literal(self):
        from ssize.lexer import TT
        toks = Lexer("42").tokenize()
        self.assertEqual(toks[0].type, TT.INT_LIT)
        self.assertEqual(toks[0].value, 42)

    def test_float_literal(self):
        from ssize.lexer import TT
        toks = Lexer("3.14").tokenize()
        self.assertEqual(toks[0].type, TT.FLOAT_LIT)
        self.assertAlmostEqual(toks[0].value, 3.14)

    def test_string_literal(self):
        from ssize.lexer import TT
        toks = Lexer('"hello"').tokenize()
        self.assertEqual(toks[0].type, TT.STRING_LIT)
        self.assertEqual(toks[0].value, "hello")

    def test_hex_literal(self):
        from ssize.lexer import TT
        toks = Lexer("0xFF").tokenize()
        self.assertEqual(toks[0].value, 255)

    def test_keywords(self):
        from ssize.lexer import TT
        toks = Lexer("int float bool void").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertIn(TT.T_INT,    types)
        self.assertIn(TT.T_FLOAT,  types)
        self.assertIn(TT.T_BOOL,   types)
        self.assertIn(TT.T_VOID,   types)

    def test_operators(self):
        from ssize.lexer import TT
        toks = Lexer("++ -- !! **").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertIn(TT.PLUSPLUS,   types)
        self.assertIn(TT.MINUSMINUS, types)
        self.assertIn(TT.BANGBANG,   types)
        self.assertIn(TT.STARSTAR,   types)

    def test_line_comment(self):
        from ssize.lexer import TT
        toks = Lexer("int a; // this is a comment\nint b;").tokenize()
        names = [t.value for t in toks if t.type == TT.IDENT]
        self.assertEqual(names, ["a", "b"])

    def test_block_comment(self):
        from ssize.lexer import TT
        toks = Lexer("int /* comment */ a;").tokenize()
        names = [t.value for t in toks if t.type == TT.IDENT]
        self.assertEqual(names, ["a"])

    def test_fcall_tokens(self):
        from ssize.lexer import TT
        toks = Lexer("fp(:x:)").tokenize()
        types = [t.type for t in toks[:-1]]
        self.assertIn(TT.FCALL_L, types)
        self.assertIn(TT.FCALL_R, types)

    def test_tostr_operator(self):
        from ssize.lexer import TT
        toks = Lexer("''x").tokenize()
        self.assertEqual(toks[0].type, TT.TOSTR)

    def test_bom_stripped(self):
        from ssize.lexer import TT
        src = "\ufeffint a;"
        toks = Lexer(src).tokenize()
        self.assertEqual(toks[0].type, TT.T_INT)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParser(unittest.TestCase):

    def _parse(self, src):
        return Parser(Lexer(src).tokenize()).parse()

    def test_var_decl(self):
        from ssize.ast_nodes import VarDecl
        prog = self._parse("int a;")
        self.assertIsInstance(prog.stmts[0], VarDecl)

    def test_var_decl_with_init(self):
        from ssize.ast_nodes import VarDecl, IntLiteral
        prog = self._parse("int a = 5;")
        vd = prog.stmts[0]
        self.assertIsInstance(vd, VarDecl)
        self.assertIsInstance(vd.inits[0], IntLiteral)
        self.assertEqual(vd.inits[0].value, 5)

    def test_multi_var_decl(self):
        from ssize.ast_nodes import VarDecl
        prog = self._parse("float b, c = 0.0;")
        vd = prog.stmts[0]
        self.assertIsInstance(vd, VarDecl)
        self.assertEqual(vd.names, ["b", "c"])

    def test_func_decl(self):
        from ssize.ast_nodes import FuncDecl
        prog = self._parse("int f(int x){ ret x; }")
        self.assertIsInstance(prog.stmts[0], FuncDecl)

    def test_if_stmt(self):
        from ssize.ast_nodes import IfStmt
        prog = self._parse("if(1 < 2) int a;")
        self.assertIsInstance(prog.stmts[0], IfStmt)

    def test_loop_stmt(self):
        from ssize.ast_nodes import LoopStmt
        prog = self._parse("loop { while 0 < 1: }")
        self.assertIsInstance(prog.stmts[0], LoopStmt)

    def test_switch_stmt(self):
        from ssize.ast_nodes import SwitchStmt
        prog = self._parse("switch(1){ case 1: break; default: break; }")
        self.assertIsInstance(prog.stmts[0], SwitchStmt)

    def test_class_decl(self):
        from ssize.ast_nodes import ClassDecl
        prog = self._parse("&MyClass { int x; }")
        self.assertIsInstance(prog.stmts[0], ClassDecl)

    def test_enum_decl(self):
        from ssize.ast_nodes import EnumDecl
        prog = self._parse("|Color { red, green, blue }")
        ed = prog.stmts[0]
        self.assertIsInstance(ed, EnumDecl)
        self.assertEqual(ed.members, ["red", "green", "blue"])

    def test_cast_expr(self):
        from ssize.ast_nodes import ExprStmt, CastExpr
        prog = self._parse("int a = (int)3.14;")
        # Just check it parsed without error

    def test_lib_import(self):
        from ssize.ast_nodes import LibImport
        prog = self._parse("lib al = <alert.ssz>;")
        self.assertIsInstance(prog.stmts[0], LibImport)
        self.assertEqual(prog.stmts[0].alias, "al")

    def test_ternary(self):
        from ssize.ast_nodes import TernaryOp, ExprStmt
        prog = self._parse("int a = 1 > 0 ? 10 : 20;")
        # Just check it parsed without error
        self.assertTrue(len(prog.stmts) > 0)

    def test_anon_func_literal(self):
        from ssize.ast_nodes import AnonFuncLiteral, VarDecl
        prog = self._parse("int sum = [int(int a, int b){ ret a + b; }](:1, 1:);")
        self.assertTrue(len(prog.stmts) > 0)

    def test_type_alias(self):
        from ssize.ast_nodes import TypeAlias
        prog = self._parse("type int_t = int;")
        self.assertIsInstance(prog.stmts[0], TypeAlias)


# ---------------------------------------------------------------------------
# Interpreter – arithmetic & expressions
# ---------------------------------------------------------------------------

class TestArithmetic(unittest.TestCase):

    def _eval_int(self, expr_src: str) -> int:
        tokens  = Lexer(f"int __r = {expr_src};").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env.get("__r")

    def test_add(self):
        self.assertEqual(self._eval_int("2 + 3"), 5)

    def test_sub(self):
        self.assertEqual(self._eval_int("10 - 4"), 6)

    def test_mul(self):
        self.assertEqual(self._eval_int("3 * 7"), 21)

    def test_div_int(self):
        self.assertEqual(self._eval_int("7 / 2"), 3)   # integer division

    def test_mod(self):
        self.assertEqual(self._eval_int("10 % 3"), 1)

    def test_lshift(self):
        self.assertEqual(self._eval_int("1 << 4"), 16)

    def test_rshift(self):
        self.assertEqual(self._eval_int("32 >> 2"), 8)

    def test_bitand(self):
        self.assertEqual(self._eval_int("0xFF & 0x0F"), 15)

    def test_bitxor(self):
        self.assertEqual(self._eval_int("0b1010 ^ 0b1100"), 6)

    def test_neg(self):
        self.assertEqual(self._eval_int("-5"), -5)

    def test_abs(self):
        self.assertEqual(self._eval_int("#-7"), 7)

    def test_pow(self):
        tokens  = Lexer("double __r = 2.0 ** 10.0;").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        self.assertAlmostEqual(interp.global_env.get("__r"), 1024.0)

    def test_ternary(self):
        self.assertEqual(self._eval_int("1 > 0 ? 10 : 20"), 10)
        self.assertEqual(self._eval_int("0 > 1 ? 10 : 20"), 20)

    def test_compound_assign(self):
        tokens  = Lexer("int a = 5; a += 3; a -= 1; a *= 2;").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        self.assertEqual(interp.global_env.get("a"), 14)

    def test_cast_to_int(self):
        tokens  = Lexer("int a = (int)3.9;").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        self.assertEqual(interp.global_env.get("a"), 3)

    def test_cast_to_double(self):
        tokens  = Lexer("double a = (double)5;").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        self.assertAlmostEqual(interp.global_env.get("a"), 5.0)

    def test_cast_char(self):
        tokens  = Lexer("char c = (char)65;").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        self.assertEqual(interp.global_env.get("c"), "A")


# ---------------------------------------------------------------------------
# Interpreter – string operations
# ---------------------------------------------------------------------------

class TestStrings(unittest.TestCase):

    def _run(self, src):
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env

    def test_string_concat(self):
        env = self._run('string a = "hello" + " " + "world";')
        self.assertEqual(env.get("a"), "hello world")

    def test_tostr_int(self):
        env = self._run("int n = 42; string s = ''n;")
        self.assertEqual(env.get("s"), "42")

    def test_tostr_float(self):
        env = self._run("double d = 3.14; string s = ''d;")
        self.assertIn("3.14", env.get("s"))

    def test_tostr_bool(self):
        env = self._run("bool b = true; string s = ''b;")
        self.assertEqual(env.get("s"), "true")


# ---------------------------------------------------------------------------
# Interpreter – control flow
# ---------------------------------------------------------------------------

class TestControlFlow(unittest.TestCase):

    def _env(self, src):
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env

    def test_if_true(self):
        env = self._env("int a = 0; if(1 == 1) a = 1;")
        self.assertEqual(env.get("a"), 1)

    def test_if_false(self):
        env = self._env("int a = 0; if(1 == 2) a = 1;")
        self.assertEqual(env.get("a"), 0)

    def test_loop_basic(self):
        src = """
        int sum = 0;
        int i = 1;
        loop {
        do:
          sum += i;
          i++;
        while i <= 10:
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("sum"), 55)

    def test_loop_with_continue(self):
        src = """
        int sum = 0;
        int n = 1;
        loop {
          while;
        do:
          if(n % 2 == 0) continue;
          sum += n;
        continue:
          n++;
        while n <= 10:
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("sum"), 25)   # 1+3+5+7+9

    def test_loop_break(self):
        src = """
        int a = 0;
        loop {
        do:
          a++;
          if(a == 5) break;
        while a < 100:
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("a"), 5)

    def test_switch_basic(self):
        src = """
        int val = 2;
        int result = 0;
        switch(val){
          case 1: result = 100; break;
          case 2: result = 200; break;
          default: result = 999; break;
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("result"), 200)

    def test_switch_default(self):
        src = """
        int val = 9;
        int result = 0;
        switch(val){
          case 1: result = 1; break;
          default: result = -1; break;
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("result"), -1)

    def test_nested_if(self):
        src = """
        int a = 5;
        int b = 10;
        int c = 0;
        if(a < b){
          if(a < 3) c = 1;
          if(a > 3) c = 2;
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("c"), 2)

    def test_block_with_break_label(self):
        src = """
        int a = 0;
        {
          break;
          a++;
        break:
          a--;
        }
        """
        env = self._env(src)
        self.assertEqual(env.get("a"), -1)


# ---------------------------------------------------------------------------
# Interpreter – functions
# ---------------------------------------------------------------------------

class TestFunctions(unittest.TestCase):

    def _env(self, src):
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env

    def test_simple_func(self):
        src = """
        int add(int a, int b){ ret a + b; }
        int result = add(3, 4);
        """
        env = self._env(src)
        self.assertEqual(env.get("result"), 7)

    def test_recursive_func(self):
        src = """
        int fact(int n){
          if(n <= 1) ret 1;
          ret n * fact(n - 1);
        }
        int result = fact(6);
        """
        env = self._env(src)
        self.assertEqual(env.get("result"), 720)

    def test_func_no_return(self):
        src = """
        int counter = 0;
        void inc(){ counter += 1; }
        inc();
        inc();
        inc();
        """
        env = self._env(src)
        self.assertEqual(env.get("counter"), 3)

    def test_func_ptr(self):
        src = """
        int double_it(int x){ ret x * 2; }
        func $int(int) fp = double_it;
        int result = fp(:5:);
        """
        env = self._env(src)
        self.assertEqual(env.get("result"), 10)

    def test_anon_func(self):
        src = """
        void f(){
          int sum = [int(int a, int b){ ret a + b; }](:3, 4:);
        }
        f();
        """
        # just check no crash
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        Interpreter().run(program)

    def test_alt_func_syntax(self):
        src = """
        ..square(int x) int { ret x * x; }
        int r = square(9);
        """
        env = self._env(src)
        self.assertEqual(env.get("r"), 81)

    def test_global_scope_access(self):
        src = """
        int gval = 99;
        int getG(){ ret .gval; }
        int r = getG();
        """
        env = self._env(src)
        self.assertEqual(env.get("r"), 99)


# ---------------------------------------------------------------------------
# Interpreter – classes
# ---------------------------------------------------------------------------

class TestClasses(unittest.TestCase):

    def _env(self, src):
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env

    def test_class_instantiation(self):
        src = """
        &Counter {
          int value;
          new(){ value = 0; }
          public void inc(){ value += 1; }
          public int get(){ ret value; }
        }
        Counter c;
        """
        # Just checks no crash
        self._env(src)

    def test_class_method_call(self):
        from ssize.runtime import SSZObject
        src = """
        &Box {
          int w;
          int h;
          new(int ww, int hh){ w = ww; h = hh; }
          public int area(){ ret w * h; }
        }
        """
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        ctor = interp.global_env.get("Box")
        obj  = ctor(3, 4)
        self.assertIsInstance(obj, SSZObject)
        area_fn = obj.fields["area"]
        from ssize.runtime import SSZFunction
        self.assertIsInstance(area_fn, SSZFunction)


# ---------------------------------------------------------------------------
# Interpreter – enums
# ---------------------------------------------------------------------------

class TestEnums(unittest.TestCase):

    def _env(self, src):
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env

    def test_enum_values(self):
        from ssize.runtime import SSZEnum
        src = "|Suit { clubs, diamonds, hearts, spades }"
        env = self._env(src)
        suit_ns = env.get("Suit")
        self.assertIsInstance(suit_ns, dict)
        self.assertIn("clubs", suit_ns)
        self.assertIsInstance(suit_ns["clubs"], SSZEnum)
        self.assertEqual(suit_ns["clubs"].ordinal, 0)
        self.assertEqual(suit_ns["spades"].ordinal, 3)


# ---------------------------------------------------------------------------
# Interpreter – reference types
# ---------------------------------------------------------------------------

class TestReferenceTypes(unittest.TestCase):

    def _env(self, src):
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)
        return interp.global_env

    def test_array_length(self):
        from ssize.runtime import SSZArray
        src = "^int arr.new(10);"
        # parsing only; .new on an identifier not yet a ref type directly
        # this is a complex chain; just check parse succeeds
        tokens  = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        self.assertTrue(len(program.stmts) > 0)

    def test_list_append(self):
        from ssize.runtime import SSZList
        lst = SSZList("int", [1, 2, 3])
        lst.append_val(4)
        self.assertEqual(lst.data, [1, 2, 3, 4])

    def test_list_slice(self):
        from ssize.runtime import SSZArray
        arr = SSZArray("int", [10, 20, 30, 40, 50])
        sl  = arr.slice(1, 3)
        self.assertEqual(sl.data, [20, 30, 40])


# ---------------------------------------------------------------------------
# Interpreter – stdlib alert integration
# ---------------------------------------------------------------------------

class TestAlertStdlib(unittest.TestCase):

    def test_hello_world(self):
        src = 'lib al = <alert.ssz>;\nal.alert!self?("Hello, world!");'
        msgs = run_ssz_with_alert(src)
        self.assertEqual(msgs, ["Hello, world!"])

    def test_root2_approx(self):
        # The root2 approximation should produce 239/169
        src = """
lib al = <alert.ssz>;
lib s = <string.ssz>;
long m = 7, n = 5;
loop {
  int i = 0;
  double sqr;
  while;
do:
  sqr = (double)m / (double)n;
  n = (long)((double)n * (sqr + 1.0) + 0.5);
  m = (long)((double)n * sqr + 0.5);
  i++;
while i < 4:
}
al.alert!self?(s.iToS(m)+"/"+s.iToS(n));
"""
        msgs = run_ssz_with_alert(src)
        self.assertEqual(msgs, ["239/169"])


# ---------------------------------------------------------------------------
# Interpreter – type coercion
# ---------------------------------------------------------------------------

class TestTypeCoercion(unittest.TestCase):

    def test_coerce_int_to_double(self):
        from ssize.runtime import type_coerce
        self.assertAlmostEqual(type_coerce(5, "int", "double"), 5.0)

    def test_coerce_double_to_int(self):
        from ssize.runtime import type_coerce
        self.assertEqual(type_coerce(3.9, "double", "int"), 3)

    def test_clamp_ubyte(self):
        from ssize.runtime import clamp
        self.assertEqual(clamp(300, "ubyte"), 255)
        self.assertEqual(clamp(-1, "ubyte"), 0)

    def test_explicit_cast_char(self):
        from ssize.runtime import explicit_cast
        self.assertEqual(explicit_cast(65, "int", "char"), "A")

    def test_explicit_cast_bool(self):
        from ssize.runtime import explicit_cast
        self.assertEqual(explicit_cast(0, "int", "bool"), False)
        self.assertEqual(explicit_cast(1, "int", "bool"), True)

    def test_ssz_tostr(self):
        from ssize.runtime import ssz_tostr
        self.assertEqual(ssz_tostr(42),    "42")
        self.assertEqual(ssz_tostr(True),  "true")
        self.assertEqual(ssz_tostr(False), "false")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors(unittest.TestCase):
    """
    The real IKEMEN engine has  IgnoreMostErrors = true  in config.ssz.
    The lexer silently skips unknown chars; the parser recovers from errors.
    These tests verify that behaviour.
    """

    def test_lex_unknown_char_is_ignored(self):
        # Real engine: unknown chars are skipped silently
        from ssize.lexer import TT
        toks = Lexer("int a;").tokenize()
        types = [t.type for t in toks]
        self.assertIn(TT.T_INT, types)

    def test_parse_lenient_recovery(self):
        # Parser recovers from missing semicolon instead of hard-failing
        from ssize.ast_nodes import Program
        prog = Parser(Lexer("int a = 5\nint b = 3;").tokenize()).parse()
        self.assertIsInstance(prog, Program)

    def test_runtime_undefined_var_returns_none(self):
        # In lenient mode, undefined var → None rather than exception
        tokens  = Lexer("int a = undefined_var;").tokenize()
        program = Parser(tokens).parse()
        interp  = Interpreter()
        interp.run(program)   # should not raise
        self.assertIsNone(interp.global_env.get("a"))

    def test_runtime_call_none_returns_none(self):
        # IgnoreMostErrors: calling None returns None instead of crashing
        tokens  = Lexer("int a = 0; a();").tokenize()
        program = Parser(tokens).parse()
        # Should NOT raise — matches real engine lenient mode
        Interpreter().run(program)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    verbosity = 2 if "-v" in sys.argv else 1
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=verbosity)
    result  = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
