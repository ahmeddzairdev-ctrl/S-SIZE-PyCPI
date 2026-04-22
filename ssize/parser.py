"""
S-SIZE (SSZ) Recursive-Descent Parser — faithful to the real IKEMEN engine.

New constructs handled vs original:
  <,        pipe-left operator
  ...       exclusive range
  ::        scope resolution
  <>        dereference
  <>=       dereference-assign
  =>        result capture
  ~field    direct field access
  %%Type    nested list type
  0dN       double/decimal literal (handled in lexer)
  const     compile-time constants
  <consteval>(var=, expr)
  <wait>(vars)
  break, break[, label]  multi-level break
"""
from __future__ import annotations
from typing import List, Optional, Any

from .lexer  import Token, TT, TYPE_NAMES
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, msg: str, token: Token):
        super().__init__(
            f"ParseError at {token.line}:{token.col}: {msg}"
            f" (got {token.type.name} {token.value!r})")
        self.token = token


TYPE_STARTS = {
    TT.T_BYTES, TT.T_UBYTE, TT.T_SHORT, TT.T_USHORT,
    TT.T_INT,   TT.T_UINT,  TT.T_LONG,  TT.T_ULONG,
    TT.T_FLOAT, TT.T_DOUBLE, TT.T_CHAR, TT.T_INDEX,
    TT.T_BOOL,  TT.T_VOID,
    TT.CARET, TT.PERCENT, TT.PERCENTPERCENT,
    TT.AMP, TT.PIPE, TT.DOLLAR, TT.TILDE,
    TT.KW_REF, TT.KW_LIST,
}


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos    = 0

    # ── navigation ──────────────────────────────────────────────────────────

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else self.tokens[-1]

    def check(self, *types: TT) -> bool:
        return self.peek().type in types

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        if t.type != TT.EOF: self.pos += 1
        return t

    def expect(self, tt: TT, msg: str = "") -> Token:
        if self.peek().type == tt: return self.advance()
        raise ParseError(msg or f"Expected {tt.name}", self.peek())

    def match(self, *types: TT) -> Optional[Token]:
        if self.peek().type in types: return self.advance()
        return None

    def error(self, msg: str) -> ParseError:
        return ParseError(msg, self.peek())

    def line(self) -> int:
        return self.peek().line

    def _is_alias(self, name: str) -> bool:
        return name.endswith("_t")

    def _looks_func(self, offset: int = 0) -> bool:
        p0 = self.peek(offset)
        if p0.type not in TYPE_STARTS and not (p0.type == TT.IDENT and self._is_alias(p0.value)):
            return False
        p1 = self.peek(offset + 1)
        if p1.type != TT.IDENT: return False
        return self.peek(offset + 2).type == TT.LPAREN

    # ── top-level ────────────────────────────────────────────────────────────

    def parse(self) -> Program:
        stmts: List[Node] = []
        while not self.check(TT.EOF):
            before = self.pos
            try:
                stmts.append(self.parse_top_level())
            except ParseError as e:
                while not self.check(TT.SEMICOLON, TT.RBRACE, TT.EOF):
                    self.advance()
                self.match(TT.SEMICOLON)
            # Guard: always make progress
            if self.pos == before:
                self.advance()
        return Program(stmts=stmts, line=0)

    def parse_top_level(self) -> Node:
        t = self.peek()

        if t.type == TT.KW_LIB:   return self.parse_lib_import()
        if t.type == TT.KW_LIBS:  return self.parse_libs_import()
        if t.type == TT.KW_TYPE:  return self.parse_type_alias()

        if t.type == TT.KW_PUBLIC:
            self.advance()
            return self.parse_top_level_public()

        # &ClassName
        if t.type == TT.AMP and self.peek(1).type == TT.IDENT:
            return self.parse_class_decl()

        # |EnumName
        if t.type == TT.PIPE and self.peek(1).type == TT.IDENT:
            return self.parse_enum_decl()

        # / RetType name(…)  public func
        if t.type == TT.SLASH and self._looks_func(1):
            return self.parse_func_decl(public=True)

        # .. name(…) RetType
        if t.type == TT.DOTDOT and self.peek(1).type == TT.IDENT:
            return self.parse_func_decl_alt()

        # func / method pointer
        if t.type == TT.KW_FUNC:   return self.parse_func_ptr_decl()
        if t.type == TT.KW_METHOD: return self.parse_method_ptr_decl()

        # anon func ptr  ~$sig name = …
        if t.type == TT.TILDE: return self.parse_anon_fp_decl()

        # const declaration
        if t.type == TT.KW_CONST:
            return self.parse_const_decl()

        # Type-starting declaration or expression
        if t.type in TYPE_STARTS or (t.type == TT.IDENT and self._is_alias(t.value)):
            return self.parse_decl_or_func()

        # ClassName varname; — class instantiation (IDENT IDENT)
        if t.type == TT.IDENT and self.peek(1).type == TT.IDENT:
            return self.parse_decl_or_func()

        return self.parse_stmt()

    def parse_top_level_public(self) -> Node:
        """After consuming 'public' at top level."""
        t = self.peek()
        if t.type == TT.AMP and self.peek(1).type == TT.IDENT:
            node = self.parse_class_decl()
            return node
        if t.type == TT.PIPE and self.peek(1).type == TT.IDENT:
            return self.parse_enum_decl()
        if t.type == TT.DOTDOT:
            return self.parse_func_decl_alt(is_public=True)
        if t.type == TT.SLASH and self._looks_func(1):
            return self.parse_func_decl(public=True)
        if t.type == TT.KW_FUNC:
            return self.parse_func_ptr_decl()
        if t.type in TYPE_STARTS or (t.type == TT.IDENT):
            node = self.parse_decl_or_func()
            if isinstance(node, (VarDecl, FuncDecl)):
                node.is_public = True
            return node
        raise self.error("Expected declaration after 'public'")

    # ── library imports ──────────────────────────────────────────────────────

    def parse_lib_import(self) -> LibImport:
        ln = self.line()
        self.expect(TT.KW_LIB)
        alias = self.expect(TT.IDENT).value
        self.expect(TT.ASSIGN)
        system = self.check(TT.LT)
        if system:
            self.advance()   # <
            path = self._read_until_gt()
        else:
            path = self.expect(TT.STRING_LIT).value
        self.match(TT.SEMICOLON)
        return LibImport(alias=alias, path=path, system=system, line=ln)

    def parse_libs_import(self) -> LibsImport:
        ln = self.line()
        self.expect(TT.KW_LIBS)
        self.expect(TT.ASSIGN)
        system = self.check(TT.LT)
        if system:
            self.advance()
            path = self._read_until_gt()
        else:
            path = self.expect(TT.STRING_LIT).value
        self.match(TT.SEMICOLON)
        return LibsImport(path=path, system=system, line=ln)

    def _read_until_gt(self) -> str:
        parts = []
        while not self.check(TT.GT, TT.EOF):
            parts.append(str(self.advance().value))
        self.match(TT.GT)
        return "".join(parts)

    # ── declarations ────────────────────────────────────────────────────────

    def parse_type_alias(self) -> TypeAlias:
        ln = self.line(); self.expect(TT.KW_TYPE)
        alias = self.expect(TT.IDENT).value
        self.expect(TT.ASSIGN)
        target = self.parse_type_expr()
        self.match(TT.SEMICOLON)
        return TypeAlias(alias=alias, target=target, line=ln)

    def parse_const_decl(self) -> VarDecl:
        ln = self.line(); self.expect(TT.KW_CONST)
        type_node = self.parse_type_expr()
        name = self.expect(TT.IDENT).value
        self.expect(TT.ASSIGN)
        init = self.parse_assign_expr()
        self.match(TT.SEMICOLON)
        return VarDecl(type_node=type_node, names=[name], inits=[init],
                       is_const=True, line=ln)

    def parse_class_decl(self, public: bool = False) -> ClassDecl:
        ln = self.line(); self.expect(TT.AMP)
        name = self.expect(TT.IDENT).value
        targ: Optional[str] = None
        if self.match(TT.LT):
            targ = self.expect(TT.IDENT).value; self.expect(TT.GT)
        self.expect(TT.LBRACE)
        members: List[Node] = []
        while not self.check(TT.RBRACE, TT.EOF):
            try:
                members.append(self.parse_class_member())
            except ParseError:
                while not self.check(TT.SEMICOLON, TT.RBRACE, TT.EOF):
                    self.advance()
                self.match(TT.SEMICOLON)
        self.expect(TT.RBRACE)
        return ClassDecl(name=name, targ=targ, members=members, line=ln)

    def parse_class_member(self) -> Node:
        ln = self.line()
        is_public = bool(self.match(TT.KW_PUBLIC))
        t = self.peek()

        if t.type == TT.KW_NEW:   return self.parse_constructor(is_public)
        if t.type == TT.KW_METHOD:return self.parse_method_ptr_decl()
        if t.type == TT.KW_FUNC:  return self.parse_func_ptr_decl()
        if t.type == TT.KW_TYPE:  return self.parse_type_alias()
        if t.type == TT.KW_CONST: return self.parse_const_decl()

        if t.type == TT.DOTDOT:
            return self.parse_func_decl_alt(is_public=is_public)
        if t.type == TT.SLASH and self._looks_func(1):
            return self.parse_func_decl(public=True)
        if t.type == TT.TILDE:
            return self.parse_anon_fp_decl()

        node = self.parse_decl_or_func()
        if isinstance(node, (VarDecl, FuncDecl)):
            node.is_public = is_public
        return node

    def parse_constructor(self, is_public: bool = False) -> FuncDecl:
        ln = self.line(); self.expect(TT.KW_NEW)
        self.expect(TT.LPAREN)
        params = self.parse_param_list()
        self.expect(TT.RPAREN)
        body = self.parse_block_body()
        return FuncDecl(ret_type=PrimType("void", ln), name="new",
                        params=params, body=body, is_public=is_public, line=ln)

    def parse_enum_decl(self) -> EnumDecl:
        ln = self.line(); self.expect(TT.PIPE)
        name = self.expect(TT.IDENT).value
        self.expect(TT.LBRACE)
        members: List[str] = []
        while not self.check(TT.RBRACE, TT.EOF):
            members.append(self.expect(TT.IDENT).value)
            self.match(TT.COMMA)
        self.expect(TT.RBRACE)
        return EnumDecl(name=name, members=members, line=ln)

    def parse_func_ptr_decl(self) -> FuncPtrDecl:
        ln = self.line(); self.expect(TT.KW_FUNC)
        sig = self.parse_sig_type()
        name = self.expect(TT.IDENT).value
        init = None
        if self.match(TT.ASSIGN): init = self.parse_expr()
        self.match(TT.SEMICOLON)
        return FuncPtrDecl(fp_type=FuncPtrType(sig=sig, line=ln), name=name,
                           init=init, line=ln)

    def parse_method_ptr_decl(self) -> MethodPtrDecl:
        ln = self.line(); self.expect(TT.KW_METHOD)
        sig = self.parse_sig_type()
        name = self.expect(TT.IDENT).value
        init = None
        if self.match(TT.ASSIGN): init = self.parse_expr()
        self.match(TT.SEMICOLON)
        return MethodPtrDecl(fp_type=FuncPtrType(sig=sig, line=ln), name=name,
                             init=init, line=ln)

    def parse_anon_fp_decl(self) -> AnonFuncPtrDecl:
        ln = self.line(); self.expect(TT.TILDE)
        sig = self.parse_sig_type()
        name = self.expect(TT.IDENT).value
        self.expect(TT.ASSIGN)
        init = self.parse_expr()
        self.match(TT.SEMICOLON)
        return AnonFuncPtrDecl(name=name, init=init, line=ln)

    def parse_decl_or_func(self) -> Node:
        ln = self.line()
        star = self.match(TT.STAR)  # * forward-decl in templates
        type_node = self.parse_type_expr()
        if not self.check(TT.IDENT):
            raise self.error("Expected identifier after type")
        name = self.advance().value
        tparam: Optional[str] = None
        if self.match(TT.LT):
            tparam = self.expect(TT.IDENT).value; self.expect(TT.GT)
        if self.check(TT.LPAREN):
            return self.parse_func_body(type_node, name, ln, tparam)
        return self.parse_var_tail(type_node, name, ln)

    def parse_func_decl(self, public: bool = False) -> FuncDecl:
        ln = self.line()
        if self.match(TT.SLASH): public = True
        type_node = self.parse_type_expr()
        name = self.expect(TT.IDENT).value
        tparam: Optional[str] = None
        if self.match(TT.LT):
            tparam = self.expect(TT.IDENT).value; self.expect(TT.GT)
        return self.parse_func_body(type_node, name, ln, tparam, public)

    def parse_func_decl_alt(self, is_public: bool = False) -> FuncDecl:
        """.. name(params) RetType { body }"""
        ln = self.line(); self.expect(TT.DOTDOT)
        name = self.expect(TT.IDENT).value
        tparam: Optional[str] = None
        if self.match(TT.LT):
            tparam = self.expect(TT.IDENT).value; self.expect(TT.GT)
        self.expect(TT.LPAREN)
        params = self.parse_param_list()
        self.expect(TT.RPAREN)
        ret_type = self.parse_type_expr()
        body = self.parse_block_body()
        return FuncDecl(ret_type=ret_type, name=name, params=params, body=body,
                        is_public=is_public, template_ret=tparam, line=ln)

    def parse_func_body(self, ret_type: Node, name: str, ln: int,
                        tparam=None, public: bool = False) -> FuncDecl:
        self.expect(TT.LPAREN)
        params = self.parse_param_list()
        self.expect(TT.RPAREN)
        body = self.parse_block_body()
        return FuncDecl(ret_type=ret_type, name=name, params=params, body=body,
                        is_public=public, template_ret=tparam, line=ln)

    def parse_param_list(self) -> List[Param]:
        params: List[Param] = []
        while not self.check(TT.RPAREN, TT.EOF):
            ln = self.line()
            ptype = self.parse_type_expr()
            pname = self.expect(TT.IDENT).value
            out = bool(self.match(TT.ASSIGN))  # trailing = means out/ref param
            params.append(Param(type_node=ptype, name=pname, out=out, line=ln))
            self.match(TT.COMMA)
        return params

    def parse_var_tail(self, type_node: Node, first_name: str, ln: int) -> VarDecl:
        names = [first_name]
        inits: List[Optional[Node]] = [None]

        if self.match(TT.ASSIGN):
            inits[0] = self.parse_assign_expr()
        elif self.check(TT.DOT) and self.peek(1).type == TT.KW_NEW:
            inits[0] = self._parse_chained_new(first_name, ln)

        while self.match(TT.COMMA):
            nm = self.expect(TT.IDENT).value
            names.append(nm)
            inits.append(self.parse_assign_expr() if self.match(TT.ASSIGN) else None)

        self.match(TT.SEMICOLON)
        return VarDecl(type_node=type_node, names=names, inits=inits, line=ln)

    def _parse_chained_new(self, var_name: str, ln: int) -> Node:
        self.advance()  # .
        self.advance()  # new
        if self.check(TT.LPAREN):
            self.advance(); sz = self.parse_expr(); self.expect(TT.RPAREN)
            node: Node = NewExpr(obj=Identifier(var_name, ln), size=sz,
                                 bracket=False, line=ln)
        elif self.check(TT.LBRACKET):
            self.advance(); sz = self.parse_expr(); self.expect(TT.RBRACKET)
            node = NewExpr(obj=Identifier(var_name, ln), size=sz,
                           bracket=True, line=ln)
            if self.match(TT.ASSIGN):
                rhs = self.parse_expr()
                node = Assign("=", node, rhs, ln)
        else:
            raise self.error("Expected ( or [ after .new")
        return node

    # ── type expressions ─────────────────────────────────────────────────────

    def parse_type_expr(self) -> Node:
        ln = self.line(); t = self.peek()

        if t.type == TT.CARET:
            self.advance(); ro = bool(self.match(TT.SLASH))
            return RefType(base=self.parse_type_expr(), read_only=ro, line=ln)

        if t.type == TT.PERCENTPERCENT:
            self.advance()
            return NestedListType(base=self.parse_type_expr(), line=ln)

        if t.type == TT.PERCENT:
            self.advance()
            return ListType(base=self.parse_type_expr(), line=ln)

        if t.type == TT.AMP:
            self.advance()
            # &.Namespace.ClassName or &ClassName
            name = self._parse_dotted_name()
            targ = None
            if self.match(TT.LT):
                targ = self._parse_dotted_name(); self.expect(TT.GT)
            return ClassType(name=name, targ=targ, line=ln)

        if t.type == TT.PIPE:
            self.advance()
            name = self._parse_dotted_name()
            return EnumType(name=name, line=ln)

        if t.type == TT.DOLLAR:
            return self.parse_sig_type()

        if t.type == TT.TILDE:
            self.advance(); sig = self.parse_sig_type()
            return AnonFuncPtrType(sig=sig, line=ln)

        if t.type in (TT.KW_REF, TT.KW_LIST):
            self.advance(); return PrimType(name=t.value, line=ln)

        if t.type in TYPE_NAMES:
            self.advance(); return PrimType(name=TYPE_NAMES[t.type], line=ln)

        if t.type == TT.IDENT:
            self.advance(); return AliasType(name=t.value, line=ln)

        raise self.error(f"Expected type, got {t.type.name}")

    def _parse_dotted_name(self) -> str:
        """Parse  .namespace.Name  or  Name  as a dotted string."""
        parts = []
        # optional leading dot (global namespace)
        if self.check(TT.DOT): self.advance()
        if self.check(TT.IDENT):
            parts.append(self.advance().value)
            while self.check(TT.DOT) and self.peek(1).type == TT.IDENT:
                self.advance(); parts.append(self.advance().value)
        return ".".join(parts) if parts else ""

    def parse_sig_type(self) -> SigType:
        ln = self.line(); self.expect(TT.DOLLAR)
        ret_type = self.parse_type_expr()
        self.expect(TT.LPAREN)
        arg_types: List[Node] = []
        while not self.check(TT.RPAREN, TT.EOF):
            arg_types.append(self.parse_type_expr())
            self.match(TT.COMMA)
        self.expect(TT.RPAREN)
        return SigType(ret_type=ret_type, arg_types=arg_types, line=ln)

    # ── statements ───────────────────────────────────────────────────────────

    def parse_block_body(self) -> List[Node]:
        self.expect(TT.LBRACE)
        stmts: List[Node] = []
        while not self.check(TT.RBRACE, TT.EOF):
            before = self.pos
            try:
                stmts.append(self.parse_stmt())
            except ParseError:
                while not self.check(TT.SEMICOLON, TT.RBRACE, TT.EOF):
                    self.advance()
                self.match(TT.SEMICOLON)
            # Guard: if nothing was consumed, force-advance to prevent infinite loop
            if self.pos == before:
                self.advance()
        self.expect(TT.RBRACE)
        return stmts

    def parse_stmt(self) -> Node:
        ln = self.line(); t = self.peek()

        if t.type == TT.KW_RET:
            self.advance()
            val = None if self.check(TT.SEMICOLON) else self.parse_expr()
            self.match(TT.SEMICOLON)
            return ReturnStmt(value=val, line=ln)

        if t.type == TT.KW_BREAK:
            return self.parse_break_stmt()

        if t.type == TT.KW_CONTINUE:
            self.advance(); self.match(TT.SEMICOLON)
            return ContinueStmt(line=ln)

        if t.type == TT.KW_ELSE and self.peek(1).type == TT.SEMICOLON:
            self.advance(); self.advance(); return ElseJump(line=ln)

        if t.type == TT.KW_IF:     return self.parse_if_stmt()
        if t.type == TT.KW_SWITCH: return self.parse_switch_stmt()
        if t.type == TT.KW_LOOP:   return self.parse_loop_stmt()
        if t.type == TT.KW_BRANCH: return self.parse_branch_stmt()
        if t.type == TT.KW_LOCK:   return self.parse_lock_stmt()

        if t.type in (TT.KW_WAIT, TT.WAIT_L):
            return self.parse_wait_stmt()

        if t.type == TT.KW_THREAD: return self.parse_thread_decl()
        if t.type == TT.KW_FUNC:   return self.parse_func_ptr_decl()
        if t.type == TT.KW_METHOD: return self.parse_method_ptr_decl()
        if t.type == TT.KW_CONST:  return self.parse_const_decl()
        if t.type == TT.KW_TYPE:   return self.parse_type_alias()
        if t.type == TT.KW_LIB:    return self.parse_lib_import()
        if t.type == TT.KW_LIBS:   return self.parse_libs_import()
        if t.type == TT.TILDE:     return self.parse_anon_fp_decl()

        if t.type == TT.LBRACE:    return self.parse_block_or_break()

        if t.type in TYPE_STARTS or (t.type == TT.IDENT and self._is_alias(t.value)):
            return self.parse_decl_or_func()
        if t.type == TT.IDENT and self.peek(1).type == TT.IDENT:
            return self.parse_decl_or_func()

        expr = self.parse_expr()
        self.match(TT.SEMICOLON)
        return ExprStmt(expr=expr, line=ln)

    def parse_break_stmt(self) -> BreakStmt:
        ln = self.line(); self.advance()  # break
        levels = 1
        target: Optional[str] = None
        # break, break[, label];
        while self.match(TT.COMMA):
            nxt = self.peek()
            if nxt.type == TT.KW_BREAK:
                self.advance(); levels += 1
            elif nxt.type == TT.IDENT or nxt.type in (TT.KW_DO,):
                target = self.advance().value; break
            else:
                break
        self.match(TT.SEMICOLON)
        return BreakStmt(levels=levels, target=target, line=ln)

    def parse_if_stmt(self) -> IfStmt:
        ln = self.line(); self.expect(TT.KW_IF)
        self.expect(TT.LPAREN); cond = self.parse_expr(); self.expect(TT.RPAREN)
        body: Node = (Block(stmts=self.parse_block_body(), line=ln)
                      if self.check(TT.LBRACE) else self.parse_stmt())
        return IfStmt(cond=cond, then_body=body, line=ln)

    def parse_switch_stmt(self) -> SwitchStmt:
        ln = self.line(); self.expect(TT.KW_SWITCH)
        self.expect(TT.LPAREN); expr = self.parse_expr(); self.expect(TT.RPAREN)
        self.expect(TT.LBRACE)
        cases: List[SwitchCase] = []
        while not self.check(TT.RBRACE, TT.EOF):
            cases.append(self.parse_switch_case())
        self.expect(TT.RBRACE)
        return SwitchStmt(expr=expr, cases=cases, line=ln)

    def parse_switch_case(self) -> SwitchCase:
        values: List[Node] = []
        if self.check(TT.KW_CASE):
            self.advance()
            values.append(self.parse_expr())
            while self.match(TT.COMMA): values.append(self.parse_expr())
        elif self.check(TT.KW_DEFAULT):
            self.advance()
        self.expect(TT.COLON)
        fallthrough = bool(self.match(TT.ARROW_L))
        body: List[Node] = []
        while not self.check(TT.KW_CASE, TT.KW_DEFAULT, TT.RBRACE, TT.EOF):
            body.append(self.parse_stmt())
        return SwitchCase(values=values, body=body, fallthrough=fallthrough)

    def parse_loop_stmt(self) -> LoopStmt:
        ln = self.line(); self.expect(TT.KW_LOOP)
        self.expect(TT.LBRACE)
        init_stmts: List[Node] = []; pre_check = False
        body_stmts: List[Node] = []; cont_stmts: List[Node] = []
        condition: Optional[Node] = None
        phase = "init"
        while not self.check(TT.RBRACE, TT.EOF):
            t = self.peek()
            if t.type == TT.KW_WHILE and self.peek(1).type == TT.SEMICOLON:
                self.advance(); self.advance(); pre_check = True; phase = "body"; continue
            if t.type == TT.KW_WHILE:
                self.advance(); condition = self.parse_expr(); self.expect(TT.COLON)
                # Parse any "post-condition" statements between while cond: and }
                # These execute when the loop exits (condition became false)
                phase = "post"; continue
            if t.type == TT.KW_DO and self.peek(1).type == TT.COLON:
                self.advance(); self.advance(); phase = "body"; continue
            if t.type == TT.KW_CONTINUE and self.peek(1).type == TT.COLON:
                self.advance(); self.advance(); phase = "cont"; continue
            before_stmt = self.pos
            try:
                s = self.parse_stmt()
                dest = "post_exit" if phase == "post" else phase
                {"init": init_stmts, "body": body_stmts, "cont": cont_stmts,
                 "post_exit": cont_stmts}[dest].append(s)
            except ParseError:
                while not self.check(TT.SEMICOLON, TT.RBRACE, TT.KW_WHILE,
                                     TT.KW_DO, TT.KW_CONTINUE, TT.EOF):
                    self.advance()
                self.match(TT.SEMICOLON)
            if self.pos == before_stmt:
                self.advance()
        self.expect(TT.RBRACE)
        return LoopStmt(init_stmts=init_stmts, pre_check=pre_check,
                        body_stmts=body_stmts, cont_stmts=cont_stmts,
                        condition=condition, line=ln)

    def parse_branch_stmt(self) -> BranchStmt:
        ln = self.line(); self.expect(TT.KW_BRANCH)
        # optional { var_decl ; } before {
        inits: List[Node] = []
        if self.check(TT.LBRACE) and self._peek_branch_block():
            pass
        self.expect(TT.LBRACE)
        conds: List[BranchCond] = []; comm: List[Node] = []
        diffs: List[BranchDiff] = []; else_: List[Node] = []
        section = "cond"

        while not self.check(TT.RBRACE, TT.EOF):
            t = self.peek()
            if t.type == TT.KW_COND:
                self.advance()
                label = None
                if self.match(TT.LT):
                    label = self.expect(TT.IDENT).value; self.expect(TT.GT)
                cond_expr = self.parse_expr(); self.expect(TT.COLON)
                body: List[Node] = []
                while not self.check(TT.KW_COND, TT.KW_COMM, TT.KW_DIFF,
                                     TT.KW_ELSE, TT.RBRACE, TT.KW_WHILE, TT.EOF) and                       not (self.peek().type == TT.KW_BREAK and self.peek(1).type == TT.COLON):
                    try:
                        body.append(self.parse_stmt())
                    except ParseError:
                        while not self.check(TT.SEMICOLON, TT.RBRACE, TT.KW_COND,
                                             TT.KW_COMM, TT.KW_DIFF, TT.KW_ELSE,
                                             TT.KW_WHILE, TT.EOF):
                            self.advance()
                        self.match(TT.SEMICOLON)
                conds.append(BranchCond(label=label, cond=cond_expr, body=body))
            elif t.type == TT.KW_COMM:
                self.advance(); self.expect(TT.COLON); section = "comm"
            elif t.type == TT.KW_DIFF:
                self.advance(); self.expect(TT.LT)
                lbl = self.expect(TT.IDENT).value; self.expect(TT.GT)
                self.expect(TT.COLON)
                dbody: List[Node] = []
                while not self.check(TT.KW_DIFF, TT.KW_ELSE, TT.KW_COMM,
                                     TT.RBRACE, TT.EOF) and                       not (self.peek().type == TT.KW_BREAK and self.peek(1).type == TT.COLON):
                    try:
                        dbody.append(self.parse_stmt())
                    except ParseError:
                        while not self.check(TT.SEMICOLON, TT.RBRACE, TT.KW_DIFF,
                                             TT.KW_ELSE, TT.KW_COMM, TT.EOF):
                            self.advance()
                        self.match(TT.SEMICOLON)
                diffs.append(BranchDiff(label=lbl, body=dbody))
            elif t.type == TT.KW_ELSE:
                self.advance(); self.expect(TT.COLON); section = "else"
            elif t.type == TT.KW_BREAK and self.peek(1).type == TT.COLON:
                # break: inside branch = labeled block break section (like a comm)
                self.advance(); self.advance()  # consume break :
                section = "break_comm"
            else:
                try:
                    s = self.parse_stmt()
                    if section in ("comm", "break_comm"): comm.append(s)
                    elif section == "else": else_.append(s)
                except ParseError:
                    while not self.check(TT.SEMICOLON, TT.RBRACE, TT.KW_COND,
                                         TT.KW_COMM, TT.KW_DIFF, TT.KW_ELSE, TT.EOF):
                        self.advance()
                    self.match(TT.SEMICOLON)
        self.expect(TT.RBRACE)
        return BranchStmt(conds=conds, comm=comm, diffs=diffs, else_=else_, line=ln)

    def _peek_branch_block(self) -> bool:
        """Heuristic: is the next { a branch block or an init block?"""
        return True  # always treat as branch block

    def parse_lock_stmt(self) -> LockStmt:
        ln = self.line(); self.expect(TT.KW_LOCK)
        self.expect(TT.LPAREN)
        vars_ = [self.parse_expr()]
        while self.match(TT.COMMA): vars_.append(self.parse_expr())
        self.expect(TT.RPAREN)
        body = self.parse_block_body()
        return LockStmt(vars=vars_, body=body, line=ln)

    def parse_wait_stmt(self) -> WaitStmt:
        ln = self.line()
        self.match(TT.KW_WAIT); self.match(TT.WAIT_L)
        self.expect(TT.LPAREN)
        vars_ = [self.parse_expr()]
        while self.match(TT.COMMA): vars_.append(self.parse_expr())
        self.expect(TT.RPAREN)
        self.match(TT.SEMICOLON)
        return WaitStmt(vars=vars_, line=ln)

    def parse_thread_decl(self) -> ThreadDecl:
        ln = self.line(); self.expect(TT.KW_THREAD)
        self.expect(TT.BANG)
        func_name = self.expect(TT.IDENT).value
        self.expect(TT.QUESTION)
        var_name = self.expect(TT.IDENT).value
        self.expect(TT.DOTDOT)
        self.expect(TT.LPAREN); args = self.parse_arg_list(); self.expect(TT.RPAREN)
        self.match(TT.SEMICOLON)
        return ThreadDecl(func_name=func_name, var_name=var_name, args=args, line=ln)

    def parse_block_or_break(self) -> Node:
        ln = self.line(); self.expect(TT.LBRACE)
        stmts: List[Node] = []; after: List[Node] = []; in_after = False
        while not self.check(TT.RBRACE, TT.EOF):
            t = self.peek()
            if t.type == TT.KW_BREAK and self.peek(1).type == TT.COLON:
                self.advance(); self.advance(); in_after = True; continue
            s = self.parse_stmt()
            (after if in_after else stmts).append(s)
        self.expect(TT.RBRACE)
        return BlockBreak(stmts=stmts, after_break=after, line=ln) if after \
               else Block(stmts=stmts, line=ln)

    # ── expressions ─────────────────────────────────────────────────────────

    def parse_expr(self) -> Node:
        return self.parse_assign_expr()

    def parse_assign_expr(self) -> Node:
        ln = self.line(); left = self.parse_ternary()
        assign_map = {
            TT.ASSIGN: "=", TT.PLUS_ASSIGN: "+=", TT.MINUS_ASSIGN: "-=",
            TT.STAR_ASSIGN: "*=", TT.SLASH_ASSIGN: "/=",
            TT.PERCENT_ASSIGN: "%=", TT.STARSTAR_ASSIGN: "**=",
            TT.LSHIFT_ASSIGN: "<<=", TT.RSHIFT_ASSIGN: ">>=",
            TT.AND_ASSIGN: "&=", TT.XOR_ASSIGN: "^=",
        }
        if self.peek().type in assign_map:
            op = assign_map[self.advance().type]
            return Assign(op=op, target=left, value=self.parse_assign_expr(), line=ln)
        if self.check(TT.DOT_ASSIGN):
            self.advance()
            return ConcatAssign(target=left, value=self.parse_assign_expr(), line=ln)
        if self.check(TT.DOLLAR):
            self.advance()
            return BinaryOp("$", left, self.parse_assign_expr(), ln)
        # result capture: expr=>var
        if self.check(TT.FAT_ARROW):
            self.advance()
            var = self.expect(TT.IDENT).value
            return ResultCapture(expr=left, var=var, line=ln)
        return left

    def parse_ternary(self) -> Node:
        ln = self.line(); cond = self.parse_or()
        if self.match(TT.QUESTION):
            then_e = self.parse_expr(); self.expect(TT.COLON)
            return TernaryOp(cond=cond, then_expr=then_e,
                             else_expr=self.parse_ternary(), line=ln)
        return cond

    def parse_or(self) -> Node:
        return self._left({TT.PIPE: "|", TT.PIPEPIPE: "||"}, self.parse_and)

    def parse_and(self) -> Node:
        ln = self.line(); left = self.parse_compare()
        while self.check(TT.AMPAMP):
            self.advance(); left = BinaryOp("&&", left, self.parse_compare(), ln)
        return left

    def parse_compare(self) -> Node:
        return self._left({TT.EQ:"==",TT.NEQ:"!=",TT.LT:"<",TT.LTE:"<=",
                           TT.GT:">",TT.GTE:">="}, self.parse_bitwise)

    def parse_bitwise(self) -> Node:
        return self._left({TT.AMP:"&",TT.CARET:"^"}, self.parse_shift)

    def parse_shift(self) -> Node:
        return self._left({TT.LSHIFT:"<<",TT.RSHIFT:">>"}, self.parse_add)

    def parse_add(self) -> Node:
        return self._left({TT.PLUS:"+",TT.MINUS:"-"}, self.parse_mul)

    def parse_mul(self) -> Node:
        return self._left({TT.STAR:"*",TT.SLASH:"/",TT.PERCENT:"%"},
                          self.parse_pow)

    def parse_pow(self) -> Node:
        ln = self.line(); base = self.parse_pipe()
        if self.check(TT.STARSTAR):
            self.advance()
            return BinaryOp("**", base, self.parse_pow(), ln)
        return base

    def parse_pipe(self) -> Node:
        """Handle  <,  pipe chain:  f()<, g()<, x  =  f(g(x))"""
        ln = self.line(); node = self.parse_prefix()
        while self.check(TT.PIPE_LEFT):
            self.advance()
            arg = self.parse_prefix()
            node = PipeLeft(func_expr=node, arg=arg, line=ln)
        return node

    def _left(self, ops: dict, sub) -> Node:
        ln = self.line(); left = sub()
        while self.peek().type in ops:
            op = ops[self.advance().type]
            left = BinaryOp(op, left, sub(), ln)
        return left

    def parse_prefix(self) -> Node:
        ln = self.line(); t = self.peek()

        if t.type == TT.TOSTR:
            self.advance(); return ToStrExpr(expr=self.parse_prefix(), line=ln)

        # <consteval>(var=, expr)
        if t.type == TT.CONSTEVAL_L:
            self.advance(); self.expect(TT.LPAREN)
            var = self.expect(TT.IDENT).value; self.expect(TT.ASSIGN)
            expr = self.parse_expr()
            self.expect(TT.RPAREN)
            return ConstEval(var=var, expr=expr, line=ln)

        # <wait>(vars)
        if t.type == TT.WAIT_L:
            self.advance(); self.expect(TT.LPAREN)
            vars_ = [self.parse_expr()]
            while self.match(TT.COMMA): vars_.append(self.parse_expr())
            self.expect(TT.RPAREN)
            return WaitExpr(vars=vars_, line=ln)

        # (type) cast  vs  (expr)
        if t.type == TT.LPAREN:
            if self._is_cast():
                saved = self.pos
                try:
                    self.advance()
                    cast_t = self.parse_type_expr()
                    self.expect(TT.RPAREN)
                    return CastExpr(target_type=cast_t,
                                    expr=self.parse_prefix(), line=ln)
                except ParseError:
                    self.pos = saved

        unary_pre = {TT.PLUS:"+", TT.MINUS:"-", TT.BANG:"!",
                     TT.HASH:"#", TT.PLUSPLUS:"++", TT.MINUSMINUS:"--",
                     TT.BANGBANG:"!!"}
        if t.type in unary_pre:
            op = unary_pre[self.advance().type]
            return UnaryOp(op=op, operand=self.parse_prefix(), prefix=True, line=ln)

        # backtick member var
        if t.type == TT.BACKTICK:
            self.advance()
            name = self.expect(TT.IDENT).value
            return MemberAccess(obj=None, field=name, line=ln)

        # .varname  global access
        if t.type == TT.DOT and self.peek(1).type == TT.IDENT:
            self.advance(); name = self.advance().value
            return self.parse_postfix(DotExpr(name=name, line=ln))

        return self.parse_postfix(self.parse_primary())

    def _is_cast(self) -> bool:
        """Is the ( followed by a type and ) ?"""
        p1 = self.peek(1)
        return p1.type in TYPE_STARTS or (p1.type == TT.IDENT and self._is_alias(p1.value))

    def parse_postfix(self, node: Node) -> Node:
        ln = self.line()
        while True:
            t = self.peek()

            # Postfix ++ -- !!
            if t.type == TT.PLUSPLUS:
                self.advance(); node = UnaryOp("++", node, False, ln)
            elif t.type == TT.MINUSMINUS:
                self.advance(); node = UnaryOp("--", node, False, ln)
            elif t.type == TT.BANGBANG:
                self.advance(); node = UnaryOp("!!", node, False, ln)

            # <>= dereference-assign
            elif t.type == TT.DEREF_ASSIGN:
                self.advance()
                rhs = self.parse_expr()
                node = Assign("=", DerefExpr(node, ln), rhs, ln)

            # <> dereference
            elif t.type == TT.DEREF:
                self.advance(); node = DerefExpr(node, ln)

            # ~field  direct field access
            elif t.type == TT.TILDE_ACC:
                self.advance()
                field = self.expect(TT.IDENT).value
                # check for template arg !type?
                if self.check(TT.BANG):
                    self.advance()
                    _targ = self._read_template_arg()
                if self.check(TT.LPAREN):
                    self.advance(); args = self.parse_arg_list(); self.expect(TT.RPAREN)
                    callee = DirectFieldAccess(node, field, ln)
                    node = FuncCall(callee=callee, args=args, line=ln)
                else:
                    node = DirectFieldAccess(node, field, ln)

            # .new(n) / .new[n]
            elif t.type == TT.DOT and self.peek(1).type == TT.KW_NEW:
                self.advance(); self.advance()
                if self.check(TT.LPAREN):
                    self.advance(); sz = self.parse_expr(); self.expect(TT.RPAREN)
                    node = NewExpr(node, sz, False, ln)
                elif self.check(TT.LBRACKET):
                    self.advance(); sz = self.parse_expr(); self.expect(TT.RBRACKET)
                    node = NewExpr(node, sz, True, ln)
                    if self.match(TT.ASSIGN):
                        node = Assign("=", node, self.parse_expr(), ln)

            # .field  member access
            elif t.type == TT.DOT and self.peek(1).type in (
                    TT.IDENT, TT.KW_TYPEID, TT.KW_TYPESIZE, TT.KW_CAST, TT.KW_NEW):
                self.advance(); field_tok = self.advance(); field = str(field_tok.value)
                # !type? template call
                ctx = None
                if self.check(TT.BANG):
                    self.advance(); ctx = self._read_template_arg()
                if self.check(TT.LPAREN):
                    self.advance(); args = self.parse_arg_list(); self.expect(TT.RPAREN)
                    node = FuncCall(MemberAccess(node, field, ln), args, ctx, ln)
                elif self.check(TT.DOTDOT) and not self.check(TT.DOTDOTDOT):
                    # method-call thread-style
                    self.advance(); self.expect(TT.LPAREN)
                    args = self.parse_arg_list(); self.expect(TT.RPAREN)
                    node = FuncCall(MemberAccess(node, field, ln), args, ctx, ln)
                else:
                    node = MemberAccess(node, field, ln)

            # arr[idx] or arr[start..end] or arr[start...end]
            elif t.type == TT.LBRACKET:
                self.advance(); idx = self.parse_expr()
                if self.check(TT.DOTDOTDOT):
                    self.advance(); end = self.parse_expr()
                    idx = RangeExpr(idx, end, exclusive=True, line=ln)
                elif self.check(TT.DOTDOT):
                    self.advance(); end = self.parse_expr()
                    idx = RangeExpr(idx, end, exclusive=False, line=ln)
                self.expect(TT.RBRACKET)
                node = IndexAccess(node, idx, ln)

            # ::  scope resolution
            elif t.type == TT.COLONCOLON:
                self.advance(); member = self.expect(TT.IDENT).value
                node = ScopeAccess(scope=node, member=member, line=ln)

            # (:args:) function pointer call
            elif t.type == TT.FCALL_L:
                self.advance(); args = self.parse_arg_list(TT.FCALL_R)
                self.expect(TT.FCALL_R)
                node = FuncPtrCall(node, args, ln)

            # regular (args) call
            elif t.type == TT.LPAREN:
                self.advance(); args = self.parse_arg_list(); self.expect(TT.RPAREN)
                node = FuncCall(node, args, None, ln)

            # => result capture
            elif t.type == TT.FAT_ARROW:
                self.advance(); var = self.expect(TT.IDENT).value
                node = ResultCapture(expr=node, var=var, line=ln)

            else:
                break
        return node

    def _read_template_arg(self) -> Optional[str]:
        """Consume  TypeName?  or  .namespace.TypeName?  or  self?  returning name."""
        parts = []
        if self.check(TT.DOT): self.advance()
        # Accept IDENT, KW_SELF, or any keyword used as a type name
        while self.peek().type in (TT.IDENT, TT.KW_SELF, TT.KW_REF, TT.KW_LIST,
                                   TT.T_INT, TT.T_LONG, TT.T_FLOAT, TT.T_DOUBLE,
                                   TT.T_BOOL, TT.T_CHAR, TT.T_VOID, TT.T_INDEX,
                                   TT.T_SHORT, TT.T_USHORT, TT.T_UINT, TT.T_ULONG,
                                   TT.T_BYTES, TT.T_UBYTE):
            parts.append(str(self.advance().value))
            if self.check(TT.DOT): self.advance()
            else: break
        if self.check(TT.QUESTION): self.advance()
        return ".".join(parts) if parts else None

    def parse_primary(self) -> Node:
        ln = self.line(); t = self.peek()

        if t.type == TT.INT_LIT:    self.advance(); return IntLiteral(t.value, ln)
        if t.type == TT.FLOAT_LIT:  self.advance(); return FloatLiteral(t.value, ln)
        if t.type == TT.STRING_LIT: self.advance(); return StringLiteral(t.value, ln)
        if t.type == TT.CHAR_LIT:   self.advance(); return StringLiteral(t.value, ln)
        if t.type == TT.KW_TRUE:    self.advance(); return BoolLiteral(True, ln)
        if t.type == TT.KW_FALSE:   self.advance(); return BoolLiteral(False, ln)
        if t.type == TT.KW_SELF:    self.advance(); return Identifier("self", ln)
        if t.type in (TT.KW_TYPEID, TT.KW_TYPESIZE):
            self.advance(); return Identifier(t.value, ln)

        if t.type == TT.IDENT:
            self.advance()
            node: Node = Identifier(t.value, ln)
            # !ctx?(args)  — method/function call with template arg
            if self.check(TT.BANG):
                self.advance(); ctx = self._read_template_arg()
                if self.check(TT.LPAREN):
                    self.advance(); args = self.parse_arg_list()
                    self.expect(TT.RPAREN)
                    return FuncCall(node, args, ctx, ln)
            return node

        if t.type == TT.LPAREN:
            self.advance(); e = self.parse_expr(); self.expect(TT.RPAREN)
            return e

        # Anonymous function literal  [RetType(params){ body }]
        if t.type == TT.LBRACKET:
            return self.parse_anon_func_literal()

        raise self.error(f"Expected expression, got {t.type.name} {t.value!r}")

    def parse_anon_func_literal(self) -> AnonFuncLiteral:
        ln = self.line(); self.expect(TT.LBRACKET)
        ret_type = self.parse_type_expr()
        self.expect(TT.LPAREN); params = self.parse_param_list()
        self.expect(TT.RPAREN); body = self.parse_block_body()
        self.expect(TT.RBRACKET)
        return AnonFuncLiteral(ret_type=ret_type, params=params, body=body, line=ln)

    def parse_arg_list(self, end: TT = TT.RPAREN) -> List[Node]:
        args: List[Node] = []
        while not self.check(end, TT.EOF):
            args.append(self.parse_expr()); self.match(TT.COMMA)
        return args
