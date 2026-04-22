"""
S-SIZE (SSZ) AST nodes — extended for the real IKEMEN engine constructs.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Any


class Node:
    pass


# ── Types ──────────────────────────────────────────────────────────────────

@dataclass
class PrimType(Node):
    name: str; line: int = 0

@dataclass
class RefType(Node):
    base: "Node"; read_only: bool = False; line: int = 0

@dataclass
class ListType(Node):
    base: "Node"; line: int = 0

@dataclass
class NestedListType(Node):
    """%%Type — nested appendable list"""
    base: "Node"; line: int = 0

@dataclass
class ClassType(Node):
    name: str; targ: Optional[str] = None; line: int = 0

@dataclass
class EnumType(Node):
    name: str; line: int = 0

@dataclass
class SigType(Node):
    ret_type: "Node"; arg_types: List["Node"]; line: int = 0

@dataclass
class FuncPtrType(Node):
    sig: SigType; line: int = 0

@dataclass
class AnonFuncPtrType(Node):
    sig: SigType; line: int = 0

@dataclass
class AliasType(Node):
    name: str; line: int = 0

@dataclass
class ScopedType(Node):
    """namespace.Type  used in type expressions"""
    parts: List[str]; line: int = 0


# ── Expressions ────────────────────────────────────────────────────────────

@dataclass
class IntLiteral(Node):
    value: int; line: int = 0

@dataclass
class FloatLiteral(Node):
    value: float; line: int = 0

@dataclass
class StringLiteral(Node):
    value: str; line: int = 0

@dataclass
class BoolLiteral(Node):
    value: bool; line: int = 0

@dataclass
class Identifier(Node):
    name: str; line: int = 0

@dataclass
class ScopeAccess(Node):
    """Type::Member  or  Namespace::Const"""
    scope: "Node"; member: str; line: int = 0

@dataclass
class MemberAccess(Node):
    """obj.field  —  requires public;  obj is None for backtick"""
    obj: Optional["Node"]; field: str; line: int = 0

@dataclass
class DirectFieldAccess(Node):
    """obj~field  —  any-visibility direct field access"""
    obj: "Node"; field: str; line: int = 0

@dataclass
class IndexAccess(Node):
    obj: "Node"; index: "Node"; line: int = 0

@dataclass
class RangeExpr(Node):
    start: "Node"; end: "Node"; exclusive: bool = False; line: int = 0

@dataclass
class CastExpr(Node):
    target_type: "Node"; expr: "Node"; line: int = 0

@dataclass
class ToStrExpr(Node):
    expr: "Node"; line: int = 0

@dataclass
class DerefExpr(Node):
    """expr<>  —  dereference (get first element of reference)"""
    expr: "Node"; line: int = 0

@dataclass
class ResultCapture(Node):
    """expr=>var  —  evaluate expr, store result in var, value is var"""
    expr: "Node"; var: str; line: int = 0

@dataclass
class PipeLeft(Node):
    """f()<, x  —  call f with x as last argument (right-to-left pipe)"""
    func_expr: "Node"; arg: "Node"; line: int = 0

@dataclass
class UnaryOp(Node):
    op: str; operand: "Node"; prefix: bool = True; line: int = 0

@dataclass
class BinaryOp(Node):
    op: str; left: "Node"; right: "Node"; line: int = 0

@dataclass
class TernaryOp(Node):
    cond: "Node"; then_expr: "Node"; else_expr: "Node"; line: int = 0

@dataclass
class Assign(Node):
    op: str; target: "Node"; value: "Node"; line: int = 0

@dataclass
class ConcatAssign(Node):
    target: "Node"; value: "Node"; line: int = 0

@dataclass
class FuncCall(Node):
    callee: "Node"; args: List["Node"]; ctx: Optional[str] = None; line: int = 0

@dataclass
class FuncPtrCall(Node):
    fp: "Node"; args: List["Node"]; line: int = 0

@dataclass
class AnonFuncLiteral(Node):
    ret_type: "Node"; params: List["Param"]; body: List["Node"]; line: int = 0

@dataclass
class NewExpr(Node):
    obj: "Node"; size: "Node"; bracket: bool = False; line: int = 0

@dataclass
class DotExpr(Node):
    """Leading-dot global: .varname"""
    name: str; line: int = 0

@dataclass
class ConstEval(Node):
    """<consteval>(var=, expr)"""
    var: str; expr: "Node"; line: int = 0

@dataclass
class WaitExpr(Node):
    """<wait>(var)"""
    vars: List["Node"]; line: int = 0


# ── Parameters ────────────────────────────────────────────────────────────

@dataclass
class Param:
    type_node: "Node"; name: str; out: bool = False; line: int = 0


# ── Statements / Declarations ─────────────────────────────────────────────

@dataclass
class VarDecl(Node):
    type_node: "Node"; names: List[str]; inits: List[Optional["Node"]]
    is_const: bool = False; is_public: bool = False; line: int = 0

@dataclass
class FuncDecl(Node):
    ret_type: "Node"; name: str; params: List[Param]; body: List["Node"]
    is_public: bool = False; template_ret: Optional[str] = None; line: int = 0

@dataclass
class ClassDecl(Node):
    name: str; targ: Optional[str]; members: List["Node"]; line: int = 0

@dataclass
class EnumDecl(Node):
    name: str; members: List[str]; line: int = 0

@dataclass
class TypeAlias(Node):
    alias: str; target: "Node"; line: int = 0

@dataclass
class LibImport(Node):
    alias: str; path: str; system: bool = False; line: int = 0

@dataclass
class LibsImport(Node):
    path: str; system: bool = False; line: int = 0

@dataclass
class ExprStmt(Node):
    expr: "Node"; line: int = 0

@dataclass
class Block(Node):
    stmts: List["Node"]; line: int = 0

@dataclass
class ReturnStmt(Node):
    value: Optional["Node"]; line: int = 0

@dataclass
class BreakStmt(Node):
    levels: int = 1; target: Optional[str] = None; line: int = 0

@dataclass
class ContinueStmt(Node):
    line: int = 0

@dataclass
class ElseJump(Node):
    line: int = 0

@dataclass
class IfStmt(Node):
    cond: "Node"; then_body: "Node"; line: int = 0

@dataclass
class SwitchCase:
    values: List["Node"]; body: List["Node"]; fallthrough: bool = False

@dataclass
class SwitchStmt(Node):
    expr: "Node"; cases: List[SwitchCase]; line: int = 0

@dataclass
class LoopStmt(Node):
    init_stmts: List["Node"]; pre_check: bool
    body_stmts: List["Node"]; cont_stmts: List["Node"]
    condition: Optional["Node"]; line: int = 0

@dataclass
class BranchCond:
    label: Optional[str]; cond: "Node"; body: List["Node"]

@dataclass
class BranchDiff:
    label: str; body: List["Node"]

@dataclass
class BranchStmt(Node):
    conds: List[BranchCond]; comm: List["Node"]
    diffs: List[BranchDiff]; else_: List["Node"]; line: int = 0

@dataclass
class LockStmt(Node):
    vars: List["Node"]; body: List["Node"]; line: int = 0

@dataclass
class WaitStmt(Node):
    vars: List["Node"]; line: int = 0

@dataclass
class BlockBreak(Node):
    stmts: List["Node"]; after_break: List["Node"]; line: int = 0

@dataclass
class ThreadDecl(Node):
    func_name: str; var_name: str; args: List["Node"]; line: int = 0

@dataclass
class FuncPtrDecl(Node):
    fp_type: FuncPtrType; name: str
    init: Optional["Node"] = None; line: int = 0

@dataclass
class MethodPtrDecl(Node):
    fp_type: FuncPtrType; name: str
    init: Optional["Node"] = None; line: int = 0

@dataclass
class AnonFuncPtrDecl(Node):
    name: str; init: "Node"; line: int = 0

@dataclass
class Program(Node):
    stmts: List["Node"]; line: int = 0
