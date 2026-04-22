"""
S-SIZE (SSZ) Tree-walk Interpreter — faithful to the real IKEMEN engine.

New constructs handled:
  ScopeAccess    Type::Member / Namespace::Const
  DirectFieldAccess  obj~field (any visibility)
  DerefExpr      obj<>  first element of a reference
  ResultCapture  expr=>var
  PipeLeft       f()<, x  = f(x)
  ConstEval      <consteval>(var=, expr)
  NestedListType %%Type
  RangeExpr      exclusive=True  (...)
  BreakStmt      multi-level levels>1
  const          compile-time constants
"""
from __future__ import annotations
import math
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Dict

from .ast_nodes import *
from .runtime import (
    Environment, SSZArray, SSZList, SSZObject, SSZEnum,
    SSZFunction, SSZAnonFunc, SSZModule,
    ReturnSignal, BreakSignal, ContinueSignal, ElseJumpSignal,
    explicit_cast, ssz_tostr, default_value, type_coerce,
    FLOAT_TYPES, INT_TYPES,
)


class SSZError(Exception):
    pass


class MultiBreak(Exception):
    """Carries multi-level break information."""
    def __init__(self, levels: int, target: Optional[str] = None):
        self.levels = levels; self.target = target


class Interpreter:
    def __init__(self, source_dir: str = ".", lib_dirs: Optional[List[str]] = None):
        self.source_dir = source_dir
        self.lib_dirs   = lib_dirs or []
        self.global_env = Environment()
        self.classes:  Dict[str, ClassDecl] = {}
        self.enums:    Dict[str, Dict[str, int]] = {}
        self.aliases:  Dict[str, str] = {}
        self.consts:   Dict[str, Any] = {}
        self._setup_builtins()

    # ── builtins ─────────────────────────────────────────────────────────────

    def _get_self(self, env) -> Any:
        """Return 'self' from the current scope, or None if not in a class method."""
        e = env
        while e is not None:
            if "self" in e._vars:
                return e._vars["self"]
            e = e.parent
        return None

    def _setup_builtins(self) -> None:
        g = self.global_env
        g.define("print", lambda *a: print(*a))

    # ── entry point ──────────────────────────────────────────────────────────

    def run(self, program: Program, env: Optional[Environment] = None) -> None:
        env = env or self.global_env
        _debug = os.environ.get("SSZ_DEBUG")
        for stmt in program.stmts:
            try:
                self.exec(stmt, env)
            except ReturnSignal:
                break  # ret at module level = early exit from file
            except (BreakSignal, ContinueSignal):
                break  # misplaced break/continue at module level
            except Exception as e:
                if _debug:
                    import sys as _sys
                    print(f"[ssz:debug] top-level stmt crashed: "
                          f"{type(e).__name__}: {e}  "
                          f"(line {getattr(stmt, 'line', '?')})", file=_sys.stderr)
                    import traceback as _tb
                    _tb.print_exc(file=_sys.stderr)
                # In non-debug mode, top-level crashes still propagate so
                # ikemen.py can catch and report them
                else:
                    raise

    # ── statements ───────────────────────────────────────────────────────────

    def exec(self, node: Node, env: Environment) -> Any:
        name = type(node).__name__

        if name == "Program":
            for s in node.stmts: self.exec(s, env)

        elif name == "LibImport":   self._do_lib_import(node, env)
        elif name == "LibsImport":  self._do_libs_import(node, env)
        elif name == "TypeAlias":   self.aliases[node.alias] = node.alias
        elif name == "VarDecl":     self._do_var_decl(node, env)
        elif name == "FuncDecl":    self._do_func_decl(node, env)

        elif name == "ClassDecl":
            self.classes[node.name] = node
            env.define(node.name, self._make_class_callable(node, env))

        elif name == "EnumDecl":
            members = {m: i for i, m in enumerate(node.members)}
            self.enums[node.name] = members
            ns: Dict[str, Any] = {}
            for m, i in members.items():
                ns[m] = SSZEnum(node.name, m, i)
            env.define(node.name, ns)

        elif name in ("FuncPtrDecl", "MethodPtrDecl", "AnonFuncPtrDecl"):
            init_val = self.eval(node.init, env) if node.init else None
            env.define(node.name, init_val)

        elif name == "ExprStmt":
            try:
                self.eval(node.expr, env)
            except Exception as _e:
                if os.environ.get("SSZ_DEBUG"):
                    import sys as _sys
                    print(f"[ssz:debug] ExprStmt swallowed: {type(_e).__name__}: {_e}  "
                          f"(line {getattr(node, 'line', '?')})", file=_sys.stderr)
        elif name == "ReturnStmt":
            raise ReturnSignal(self.eval(node.value, env) if node.value else None)

        elif name == "BreakStmt":
            if node.levels <= 1:
                raise BreakSignal()
            raise MultiBreak(node.levels - 1, node.target)

        elif name == "ContinueStmt": raise ContinueSignal()
        elif name == "ElseJump":     raise ElseJumpSignal()

        elif name == "Block":
            child = env.child()
            for s in node.stmts: self.exec(s, child)

        elif name == "BlockBreak":
            child = env.child(); broke = False
            try:
                for s in node.stmts: self.exec(s, child)
            except (BreakSignal, MultiBreak):
                broke = True
            for s in node.after_break: self.exec(s, child)

        elif name == "IfStmt":
            if self._truthy(self.eval(node.cond, env)):
                self.exec(node.then_body, env.child())

        elif name == "SwitchStmt":  self._do_switch(node, env)
        elif name == "LoopStmt":    self._do_loop(node, env)
        elif name == "BranchStmt":  self._do_branch(node, env)

        elif name in ("LockStmt",):
            child = env.child()
            for s in node.body: self.exec(s, child)

        elif name == "WaitStmt":    pass  # synchronous — no-op

        elif name == "ThreadDecl":
            fn   = env.get(node.func_name)
            args = [self.eval(a, env) for a in node.args]
            self._call_function(fn, args, env)
            env.define(node.var_name, None)

        else:
            raise SSZError(f"Unknown statement node: {name}")

    # ── expressions ──────────────────────────────────────────────────────────

    def eval(self, node: Node, env: Environment) -> Any:
        name = type(node).__name__

        if name == "IntLiteral":    return node.value
        if name == "FloatLiteral":  return node.value
        if name == "StringLiteral": return node.value
        if name == "BoolLiteral":   return node.value

        if name == "Identifier":
            try:    return env.get(node.name)
            except (NameError, KeyError): return None

        if name == "DotExpr":
            return env.get_global(node.name)

        if name == "ScopeAccess":
            return self._do_scope_access(node, env)

        if name == "MemberAccess":
            return self._do_member_access(node, env)

        if name == "DirectFieldAccess":
            return self._do_direct_field(node, env)

        if name == "DerefExpr":
            val = self.eval(node.expr, env)
            return self._deref(val)

        if name == "ResultCapture":
            val = self.eval(node.expr, env)
            env.set(node.var, val)
            return val

        if name == "PipeLeft":
            return self._do_pipe_left(node, env)

        if name == "IndexAccess":
            return self._do_index_access(node, env)

        if name == "RangeExpr":
            start = self.eval(node.start, env)
            end   = self.eval(node.end,   env)
            return (int(start), int(end), node.exclusive)

        if name == "CastExpr":
            return self._do_cast(node, env)

        if name == "ToStrExpr":
            return ssz_tostr(self.eval(node.expr, env))

        if name == "UnaryOp":
            return self._do_unary(node, env)

        if name == "BinaryOp":
            return self._do_binary(node, env)

        if name == "TernaryOp":
            cond = self.eval(node.cond, env)
            return self.eval(node.then_expr if self._truthy(cond)
                             else node.else_expr, env)

        if name == "Assign":
            return self._do_assign(node, env)

        if name == "ConcatAssign":
            arr = self.eval(node.target, env)
            val = self.eval(node.value,  env)
            if isinstance(arr, SSZList):
                if isinstance(val, (SSZArray, SSZList)):
                    for item in val.data: arr.append_val(item)
                else:
                    arr.append_val(val)
            elif isinstance(arr, str):
                new_val = arr + ssz_tostr(val)
                self._assign_target(node.target, new_val, env)
            return arr

        if name == "FuncCall":
            return self._do_func_call(node, env)

        if name == "FuncPtrCall":
            fp   = self.eval(node.fp, env)
            args = [self.eval(a, env) for a in node.args]
            return self._call_function(fp, args, env)

        if name == "AnonFuncLiteral":
            return SSZAnonFunc(
                params=node.params, body=node.body, env=env,
                capture=dict(env._vars))

        if name == "NewExpr":
            return self._do_new_expr(node, env)

        if name == "ConstEval":
            # Runtime approximation: evaluate expression, store in var
            try:
                val = self.eval(node.expr, env)
                env.define(node.var, val)
                return val is not None
            except Exception:
                return False

        if name == "WaitExpr":
            return None  # synchronous — no-op

        raise SSZError(f"Unknown expression node: {name}")

    # ── scope resolution  Type::Member ──────────────────────────────────────

    def _do_scope_access(self, node: ScopeAccess, env: Environment) -> Any:
        scope_val = self.eval(node.scope, env)
        if isinstance(scope_val, dict):
            return scope_val.get(node.member)
        # Enum name as string
        if isinstance(node.scope, Identifier):
            ename = node.scope.name
            if ename in self.enums:
                members = self.enums[ename]
                if node.member in members:
                    return SSZEnum(ename, node.member, members[node.member])
        # Const table
        key = f"{scope_val}.{node.member}" if scope_val else node.member
        if key in self.consts:
            return self.consts[key]
        return None

    # ── member access ────────────────────────────────────────────────────────

    def _do_member_access(self, node: MemberAccess, env: Environment) -> Any:
        if node.obj is None:
            # backtick: member of self
            self_obj = self._get_self(env)
            if isinstance(self_obj, SSZObject):
                return self_obj.fields.get(node.field)
            return None
        obj = self.eval(node.obj, env)
        return self._get_field(obj, node.field, env)

    def _do_direct_field(self, node: DirectFieldAccess, env: Environment) -> Any:
        obj = self.eval(node.obj, env)
        return self._get_field(obj, node.field, env)

    def _get_field(self, obj: Any, field: str, env: Environment) -> Any:
        if isinstance(obj, SSZModule):
            return obj.get(field)
        if isinstance(obj, SSZObject):
            return obj.fields.get(field)
        if isinstance(obj, dict):
            return obj.get(field)
        if isinstance(obj, (SSZArray, SSZList)):
            if field in ("typeid", "typesize", "length"):
                return len(obj.data)
        return None

    # ── dereference ──────────────────────────────────────────────────────────

    def _deref(self, val: Any) -> Any:
        if isinstance(val, (SSZArray, SSZList)):
            return val.data[0] if val.data else None
        if isinstance(val, list):
            return val[0] if val else None
        return val

    # ── pipe-left ────────────────────────────────────────────────────────────

    def _do_pipe_left(self, node: PipeLeft, env: Environment) -> Any:
        """
        f()<, x  →  call f with x as its (sole/last) argument.
        The func_expr should be either a FuncCall with no args,
        or a member access resolving to a callable.
        """
        arg_val = self.eval(node.arg, env)
        fn_node = node.func_expr

        # f()<, x  means the call already set up is missing its last arg
        if isinstance(fn_node, FuncCall):
            # Re-evaluate callee, prepend arg
            args = [self.eval(a, env) for a in fn_node.args] + [arg_val]
            fn = self._resolve_callee(fn_node.callee, env)
            if callable(fn) and not isinstance(fn, (SSZFunction, SSZAnonFunc)):
                return fn(*args)
            return self._call_function(fn, args, env)

        if isinstance(fn_node, MemberAccess):
            obj = self.eval(fn_node.obj, env) if fn_node.obj else self._get_self(env)
            method = self._get_field(obj, fn_node.field, env)
            return self._call_method(method, obj, [arg_val], env)

        # Fallback: treat as regular call with one arg
        fn = self.eval(fn_node, env)
        return self._call_function(fn, [arg_val], env)

    def _resolve_callee(self, callee: Node, env: Environment) -> Any:
        if isinstance(callee, MemberAccess):
            obj = self.eval(callee.obj, env) if callee.obj else self._get_self(env)
            return self._get_field(obj, callee.field, env)
        return self.eval(callee, env)

    # ── index access ─────────────────────────────────────────────────────────

    def _do_index_access(self, node: IndexAccess, env: Environment) -> Any:
        obj = self.eval(node.obj, env)
        idx = self.eval(node.index, env)
        if isinstance(idx, tuple):
            start, end, exclusive = idx
            if isinstance(obj, (SSZArray, SSZList)):
                sl = obj.data[start:end] if exclusive else obj.data[start:end+1]
                return SSZArray(obj.elem_type, sl)
            if isinstance(obj, str):
                return obj[start:end] if exclusive else obj[start:end+1]
        if isinstance(obj, (SSZArray, SSZList)):
            return obj.data[int(idx)]
        if isinstance(obj, str):
            return obj[int(idx)]
        if isinstance(obj, list):
            return obj[int(idx)]
        return None

    # ── cast ─────────────────────────────────────────────────────────────────

    def _do_cast(self, node: CastExpr, env: Environment) -> Any:
        val = self.eval(node.expr, env)
        dst = self._resolve_type_name(node.target_type)
        # None evaluates to zero/default — never crash on unresolved globals
        if val is None:
            src = "void"
        else:
            src = ("bool"   if isinstance(val, bool)  else
                   "long"   if isinstance(val, int)   else
                   "double" if isinstance(val, float) else
                   "char"   if isinstance(val, str)   else "void")
        return explicit_cast(val, src, dst)

    # ── unary ────────────────────────────────────────────────────────────────

    def _do_unary(self, node: UnaryOp, env: Environment) -> Any:
        if node.prefix:
            if node.op == "+": return self._coerce_num(self.eval(node.operand, env))
            if node.op == "-": return -self._coerce_num(self.eval(node.operand, env))
            if node.op == "!":
                v = self.eval(node.operand, env)
                if v is None: return True
                return not v if isinstance(v, bool) else ~int(v)
            if node.op == "#":
                v = self.eval(node.operand, env)
                if v is None: return 0
                if isinstance(v, (SSZArray, SSZList)): return len(v.data)
                if isinstance(v, str): return len(v)
                return abs(v)
            if node.op == "++":
                v = self._coerce_num(self.eval(node.operand, env))
                self._assign_target(node.operand, v + 1, env); return v + 1
            if node.op == "--":
                v = self._coerce_num(self.eval(node.operand, env))
                self._assign_target(node.operand, v - 1, env); return v - 1
            if node.op == "!!":
                v = self.eval(node.operand, env)
                nv = not bool(v); self._assign_target(node.operand, nv, env); return nv
        else:
            v = self._coerce_num(self.eval(node.operand, env))
            if node.op == "++":
                self._assign_target(node.operand, v + 1, env); return v
            if node.op == "--":
                self._assign_target(node.operand, v - 1, env); return v
            if node.op == "!!":
                nv = not bool(v); self._assign_target(node.operand, nv, env); return v
        raise SSZError(f"Unknown unary op: {node.op}")

    # ── binary ───────────────────────────────────────────────────────────────

    def _coerce_num(self, v: Any) -> Any:
        """Coerce None → 0 so arithmetic never crashes on unresolved identifiers."""
        if v is None:
            return 0
        return v

    def _do_binary(self, node: BinaryOp, env: Environment) -> Any:
        if node.op == "&&":
            return self._truthy(self.eval(node.left, env)) and \
                   self._truthy(self.eval(node.right, env))
        L = self._coerce_num(self.eval(node.left, env))
        R = self._coerce_num(self.eval(node.right, env))
        op = node.op
        if op == "+":
            if isinstance(L, str) or isinstance(R, str): return str(L) + str(R)
            return L + R
        if op == "-":  return L - R
        if op == "*":  return L * R
        if op == "/":
            if isinstance(L, int) and isinstance(R, int) and R != 0:
                return int(L / R)
            return L / R if R != 0 else 0
        if op == "%":  return L % R if R != 0 else 0
        if op == "**": return L ** R
        if op == "<<": return int(L) << int(R)
        if op == ">>": return int(L) >> int(R)
        if op == "&":  return (L & R) if not isinstance(L, bool) else (L and R)
        if op == "^":  return (int(L) ^ int(R)) if not isinstance(L, bool) else (L != R)
        if op == "|":  return int(L) | int(R)
        if op == "||":
            return bool(L) or bool(R)
        if op in ("==", "!="): 
            eq = L == R
            return eq if op == "==" else not eq
        if op == "<":  return L < R
        if op == "<=": return L <= R
        if op == ">":  return L > R
        if op == ">=": return L >= R
        if op == "$":  return R
        raise SSZError(f"Unknown binary op: {op!r}")

    # ── assignment ───────────────────────────────────────────────────────────

    def _do_assign(self, node: Assign, env: Environment) -> Any:
        val = self.eval(node.value, env)
        if node.op != "=":
            cur = self.eval(node.target, env)
            val = self._apply_op(node.op[:-1], cur, val)
        self._assign_target(node.target, val, env)
        return val

    def _apply_op(self, op: str, L: Any, R: Any) -> Any:
        if L is None: L = 0
        if R is None: R = 0
        ops = {"+": lambda a,b: a+b, "-": lambda a,b: a-b,
               "*": lambda a,b: a*b, "/": lambda a,b: int(a/b) if isinstance(a,int) and isinstance(b,int) else a/b,
               "%": lambda a,b: a%b, "**": lambda a,b: a**b,
               "<<": lambda a,b: int(a)<<int(b), ">>": lambda a,b: int(a)>>int(b),
               "&": lambda a,b: int(a)&int(b), "^": lambda a,b: int(a)^int(b)}
        return ops[op](L, R) if op in ops else L

    def _assign_target(self, target: Node, value: Any, env: Environment) -> None:
        name = type(target).__name__
        if name == "Identifier":
            try:    env.set(target.name, value)
            except NameError: env.define(target.name, value)
        elif name == "DotExpr":
            env.set_global(target.name, value)
        elif name in ("MemberAccess", "DirectFieldAccess"):
            obj = (self._get_self(env) if getattr(target, "obj", None) is None
                   else self.eval(target.obj, env))
            if isinstance(obj, SSZObject):
                obj.fields[target.field] = value
            elif isinstance(obj, SSZModule):
                obj.env.define(target.field, value)
            elif isinstance(obj, dict):
                obj[target.field] = value
        elif name == "IndexAccess":
            obj = self.eval(target.obj, env)
            idx = self.eval(target.index, env)
            if isinstance(obj, (SSZArray, SSZList)): obj.data[int(idx)] = value
            elif isinstance(obj, list): obj[int(idx)] = value
        elif name == "DerefExpr":
            inner = self.eval(target.expr, env)
            if isinstance(inner, (SSZArray, SSZList)) and inner.data:
                inner.data[0] = value
        elif name == "NewExpr":
            inner = self.eval(target.obj, env)
            if isinstance(inner, (SSZArray, SSZList)):
                inner.data = [value] * len(inner.data)
        elif name == "ScopeAccess":
            pass  # consts are read-only

    # ── function calls ───────────────────────────────────────────────────────

    def _do_func_call(self, node: FuncCall, env: Environment) -> Any:
        args = []
        for a in node.args:
            try:
                args.append(self.eval(a, env))
            except Exception:
                args.append(None)  # IgnoreMostErrors
        if isinstance(node.callee, (MemberAccess, DirectFieldAccess)):
            ma = node.callee
            obj = (self._get_self(env) if getattr(ma, "obj", None) is None
                   else self.eval(ma.obj, env))
            method = self._get_field(obj, ma.field, env)
            if method is None and isinstance(obj, SSZModule):
                method = obj.get(ma.field)
            return self._call_method(method, obj, args, env)
        fn = self.eval(node.callee, env)
        return self._call_function(fn, args, env)

    def _call_method(self, method: Any, obj: Any, args: List[Any], env: Environment) -> Any:
        if callable(method) and not isinstance(method, (SSZFunction, SSZAnonFunc)):
            return method(*args)
        if isinstance(method, (SSZFunction, SSZAnonFunc)):
            call_env = method.env.child()
            call_env.define("self", obj)
            for param, arg in zip(method.params, args):
                call_env.define(param.name, arg)
            if isinstance(method, SSZAnonFunc):
                for k, v in method.capture.items(): call_env.define(k, v)
            return self._exec_body(method.body, call_env)
        return None

    def _call_function(self, fn: Any, args: List[Any], env: Environment) -> Any:
        if fn is None: return None  # IgnoreMostErrors: unresolved call → None
        if callable(fn) and not isinstance(fn, (SSZFunction, SSZAnonFunc)):
            return fn(*args)
        if isinstance(fn, (SSZFunction, SSZAnonFunc)):
            call_env = fn.env.child()
            for param, arg in zip(fn.params, args):
                call_env.define(param.name, arg)
            if isinstance(fn, SSZAnonFunc):
                for k, v in fn.capture.items(): call_env.define(k, v)
            return self._exec_body(fn.body, call_env)
        return None  # IgnoreMostErrors: non-callable → None

    def _exec_body(self, body: List[Node], env: Environment) -> Any:
        try:
            for stmt in body: self.exec(stmt, env)
        except ReturnSignal as rs:
            return rs.value
        return None

    # ── variable declaration ─────────────────────────────────────────────────

    def _do_var_decl(self, node: VarDecl, env: Environment) -> None:
        type_name = self._resolve_type_name(node.type_node)
        for nm, init_expr in zip(node.names, node.inits):
            # Pre-allocate reference/list types
            if type_name.startswith("^"):
                val: Any = SSZArray(type_name[1:], [])
            elif type_name.startswith("%"):
                val = SSZList(type_name[1:], [])
            elif type_name == "string":
                val = ""
            else:
                val = default_value(type_name)
            env.define(nm, val)

            if init_expr is not None:
                computed = self.eval(init_expr, env)
                if isinstance(computed, bool): pass
                elif type_name in INT_TYPES and isinstance(computed, float):
                    computed = int(computed)
                elif type_name in FLOAT_TYPES and isinstance(computed, int):
                    computed = float(computed)
                env.set(nm, computed)

            if node.is_const:
                self.consts[nm] = env.get(nm)

    def _resolve_type_name(self, type_node: Node) -> str:
        name = type(type_node).__name__
        if name == "PrimType":    return type_node.name
        if name == "AliasType":
            if type_node.name == "string": return "string"
            return self.aliases.get(type_node.name, type_node.name)
        if name == "ClassType":   return f"&{type_node.name}"
        if name == "EnumType":    return f"|{type_node.name}"
        if name == "RefType":     return f"^{self._resolve_type_name(type_node.base)}"
        if name == "ListType":    return f"%{self._resolve_type_name(type_node.base)}"
        if name == "NestedListType": return f"%%{self._resolve_type_name(type_node.base)}"
        if name == "SigType":     return "$func"
        return "void"

    # ── function declaration ─────────────────────────────────────────────────

    def _do_func_decl(self, node: FuncDecl, env: Environment) -> None:
        fn = SSZFunction(
            name=node.name, params=node.params, body=node.body, env=env,
            ret_type_name=self._resolve_type_name(node.ret_type))
        env.define(node.name, fn)

    # ── class ────────────────────────────────────────────────────────────────

    def _make_class_callable(self, decl: ClassDecl, defining_env: Environment):
        def construct(*args):
            obj = SSZObject(decl.name)
            obj_env = defining_env.child()
            obj_env.define("self", obj)
            # First pass: fields and methods
            for member in decl.members:
                if isinstance(member, VarDecl):
                    tname = self._resolve_type_name(member.type_node)
                    for nm, init in zip(member.names, member.inits):
                        v = self.eval(init, obj_env) if init else default_value(tname)
                        obj.fields[nm] = v
                elif isinstance(member, FuncDecl):
                    fn = SSZFunction(
                        name=member.name, params=member.params, body=member.body,
                        env=obj_env,
                        ret_type_name=self._resolve_type_name(member.ret_type))
                    obj.fields[member.name] = fn
                elif isinstance(member, (TypeAlias, EnumDecl, ClassDecl)):
                    self.exec(member, obj_env)
            # Constructor
            ctor = obj.fields.get("new")
            if ctor and isinstance(ctor, SSZFunction):
                call_env = obj_env.child()
                call_env.define("self", obj)
                for param, arg in zip(ctor.params, args):
                    call_env.define(param.name, arg)
                try:
                    self._exec_body(ctor.body, call_env)
                except ReturnSignal:
                    pass
            return obj
        return construct

    # ── library imports ──────────────────────────────────────────────────────

    def _do_lib_import(self, node: LibImport, env: Environment) -> None:
        mod = self._load_library(node.path, node.system)
        env.define(node.alias, mod)

    def _do_libs_import(self, node: LibsImport, env: Environment) -> None:
        mod = self._load_library(node.path, node.system)
        if isinstance(mod, SSZModule):
            for k, v in mod.env._vars.items():
                env.define(k, v)

    def _load_library(self, path: str, system: bool = False) -> Any:
        # Normalise separators
        norm_path = path.replace("\\", "/")
        # Remove .ssz extension for stub lookup
        stub_name = norm_path[:-4] if norm_path.endswith(".ssz") else norm_path
        # Strip leading ./ but preserve ../ for relative paths
        stub_key  = stub_name.lstrip("./")
        name_only = Path(stub_name).name

        # 1. Try Python stub (e.g. alpha/sdlplugin, string, math)
        stub = self._load_python_stub(stub_key)
        if stub is not None:
            return stub

        # 2. Try .ssz file on disk
        #    Handle both relative paths (../save/config.ssz) and plain names
        search_dirs = [self.source_dir] + self.lib_dirs
        for d in search_dirs:
            # Try the path as-is (handles ../save/config.ssz relative to source_dir)
            candidate = (Path(d) / norm_path).resolve()
            if candidate.exists():
                return self._load_ssz_file(str(candidate), name_only)
            # Try plain filename in search dir
            candidate2 = Path(d) / Path(norm_path).name
            if candidate2.exists():
                return self._load_ssz_file(str(candidate2), name_only)

        # 3. Return empty stub — engine runs in lenient mode
        mod_env = Environment(global_env=self.global_env)
        return SSZModule(name_only, mod_env)

    def _load_python_stub(self, name: str) -> Optional[SSZModule]:
        """
        Load a Python stdlib stub.
        name may be a path like 'alpha/sdlplugin' — maps to
        ssize/stdlib/alpha/sdlplugin.py
        """
        stub_dir  = Path(__file__).parent / "stdlib"
        # Normalise: alpha/sdlplugin → alpha/sdlplugin
        norm = name.replace("\\", "/").replace(".ssz", "")
        stub_file = stub_dir / (norm + ".py")

        if not stub_file.exists():
            # Try just the basename
            base = Path(norm).name
            stub_file = stub_dir / (base + ".py")
            if not stub_file.exists():
                return None

        # Build a unique module name
        module_key = norm.replace("/", ".").replace("\\", ".")
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"ssize.stdlib.{module_key}", stub_file)
        mod  = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            import sys
            print(f"[ssz] Warning: error loading stub '{stub_file}': {e}",
                  file=sys.stderr)
            mod_env = Environment(global_env=self.global_env)
            return SSZModule(norm, mod_env)

        mod_env = Environment(global_env=self.global_env)
        if hasattr(mod, "register"):
            mod.register(mod_env, self)
        # If this module exposes a "State" constructor (Lua bridge),
        # wrap it to auto-inject _IKEMEN_ROOT into every created LuaState
        if "State" in mod_env._vars:
            orig_ctor = mod_env._vars["State"]
            interp_ref = self
            def _lua_state_ctor(*args, _ctor=orig_ctor, _interp=interp_ref):
                obj = _ctor(*args)
                if obj is not None and hasattr(obj, "setIkemenRoot"):
                    root = (_interp.global_env.get_global("_IKEMEN_ROOT")
                            or _interp.source_dir)
                    obj.setIkemenRoot(str(root))
                return obj
            mod_env._vars["State"] = _lua_state_ctor
        return SSZModule(norm, mod_env)

    def _load_ssz_file(self, filepath: str, name: str) -> SSZModule:
        from .lexer  import Lexer
        from .parser import Parser
        source  = Path(filepath).read_text(encoding="utf-8-sig")
        tokens  = Lexer(source, filepath).tokenize()
        program = Parser(tokens).parse()
        mod_env = Environment(global_env=self.global_env)
        sub = Interpreter(source_dir=str(Path(filepath).parent),
                          lib_dirs=self.lib_dirs)
        sub.global_env = self.global_env
        sub.classes = self.classes; sub.enums = self.enums
        sub.aliases = self.aliases; sub.consts = self.consts
        try:
            sub.run(program, mod_env)
        except ReturnSignal:
            pass  # ret at module top-level is normal in some ssz files
        except (BreakSignal, ContinueSignal):
            pass  # misplaced control flow at module level
        return SSZModule(name, mod_env)

    def _inject_root_into_lua(self, lua_state) -> None:
        """Give a LuaState knowledge of the IKEMEN root directory."""
        root = self.global_env.get_global("_IKEMEN_ROOT") or self.source_dir
        if hasattr(lua_state, "setIkemenRoot"):
            lua_state.setIkemenRoot(str(root))

    # ── .new() expression ────────────────────────────────────────────────────

    def _do_new_expr(self, node: NewExpr, env: Environment) -> Any:
        obj  = self.eval(node.obj, env)
        size = int(self.eval(node.size, env))
        if isinstance(obj, (SSZArray, SSZList)):
            if node.bracket:
                if size < 0:
                    for _ in range(abs(size)): obj.data.append(None)
                else:
                    if size < len(obj.data): obj.data = obj.data[:size]
                    else: obj.data += [None] * (size - len(obj.data))
            else:
                obj.data = [None] * max(0, size)
            return obj
        return obj

    # ── control flow ─────────────────────────────────────────────────────────

    def _do_switch(self, node: SwitchStmt, env: Environment) -> None:
        val = self.eval(node.expr, env)
        pending_ft = False
        for case in node.cases:
            matched = pending_ft or (not case.values) or \
                      any(self.eval(cv, env) == val for cv in case.values)
            if matched:
                child = env.child()
                try:
                    for s in case.body: self.exec(s, child)
                except (BreakSignal, MultiBreak): return
                pending_ft = case.fallthrough

    def _do_loop(self, node: LoopStmt, env: Environment) -> None:
        loop_env = env.child()
        for s in node.init_stmts: self.exec(s, loop_env)

        def cond_ok() -> bool:
            return True if node.condition is None else \
                   self._truthy(self.eval(node.condition, loop_env))

        if node.pre_check and not cond_ok(): return

        while True:
            body_env = loop_env.child()
            try:
                for s in node.body_stmts: self.exec(s, body_env)
            except BreakSignal: return
            except MultiBreak as mb:
                if mb.levels > 1: raise MultiBreak(mb.levels - 1, mb.target)
                return
            except ContinueSignal: pass
            try:
                for s in node.cont_stmts: self.exec(s, loop_env)
            except (BreakSignal, MultiBreak): return
            if not cond_ok(): return

    def _do_branch(self, node: BranchStmt, env: Environment) -> None:
        matched_label: Optional[str] = None; executed = False
        for bc in node.conds:
            if self._truthy(self.eval(bc.cond, env)):
                matched_label = bc.label; executed = True
                child = env.child()
                try:
                    for s in bc.body: self.exec(s, child)
                except (BreakSignal, MultiBreak): return
                except ElseJumpSignal: pass
                break
        if executed and node.comm:
            child = env.child()
            try:
                for s in node.comm: self.exec(s, child)
            except (BreakSignal, MultiBreak): return
        for diff in node.diffs:
            if diff.label == matched_label:
                child = env.child()
                try:
                    for s in diff.body: self.exec(s, child)
                except (BreakSignal, MultiBreak): return
        if not executed and node.else_:
            child = env.child()
            try:
                for s in node.else_: self.exec(s, child)
            except (BreakSignal, MultiBreak): return

    # ── utility ──────────────────────────────────────────────────────────────

    def _truthy(self, val: Any) -> bool:
        if val is None: return False
        if isinstance(val, bool): return val
        if isinstance(val, (int, float)): return val != 0
        if isinstance(val, str): return len(val) > 0
        if isinstance(val, (SSZArray, SSZList)): return len(val.data) > 0
        return True
