"""
AirLang — ast_nodes.py
Définitions de tous les nœuds de l'Arbre Syntaxique Abstrait (AST).
Chaque nœud correspond à une construction du langage AirLang.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Any


# ── Nœud de base ─────────────────────────────────────────────────────────────

@dataclass
class Node:
    """Nœud de base — tous les nœuds AST héritent de celui-ci."""
    line:   int = 0
    column: int = 0

    def accept(self, visitor):
        """Appelle visitor.visit_<NomClasse>(self)."""
        method = "visit_" + type(self).__name__
        return getattr(visitor, method)(self)


# ── Programme ─────────────────────────────────────────────────────────────────

@dataclass
class Program(Node):
    """Racine de l'AST — liste de toutes les déclarations du fichier."""
    statements: List[Node] = field(default_factory=list)


# ── Littéraux ─────────────────────────────────────────────────────────────────

@dataclass
class IntLiteral(Node):
    value: int = 0

@dataclass
class FloatLiteral(Node):
    value: float = 0.0

@dataclass
class StringLiteral(Node):
    value: str = ""

@dataclass
class BoolLiteral(Node):
    value: bool = False

@dataclass
class NullLiteral(Node):
    pass

@dataclass
class ListLiteral(Node):
    """[expr, expr, ...]"""
    elements: List[Node] = field(default_factory=list)

@dataclass
class MapLiteral(Node):
    """{"key": expr, ...}"""
    pairs: List[tuple] = field(default_factory=list)   # List[(Node, Node)]

@dataclass
class RangeLiteral(Node):
    """start..end"""
    start: Node = None
    end:   Node = None


# ── Identifiants et accès ─────────────────────────────────────────────────────

@dataclass
class Identifier(Node):
    """Nom de variable ou fonction."""
    name: str = ""

@dataclass
class MemberAccess(Node):
    """obj.field"""
    obj:    Node = None
    member: str  = ""

@dataclass
class IndexAccess(Node):
    """obj[index]"""
    obj:   Node = None
    index: Node = None


# ── Expressions ───────────────────────────────────────────────────────────────

@dataclass
class BinaryOp(Node):
    """left op right  (ex: a + b, x == y)"""
    left:  Node = None
    op:    str  = ""
    right: Node = None

@dataclass
class UnaryOp(Node):
    """op operand  (ex: not x, -y)"""
    op:      str  = ""
    operand: Node = None

@dataclass
class Call(Node):
    """func(arg1, arg2, ...)"""
    callee: Node       = None
    args:   List[Node] = field(default_factory=list)
    # Arguments nommés : name: value  (pour .new())
    kwargs: List[tuple] = field(default_factory=list)  # List[(str, Node)]

@dataclass
class MethodCall(Node):
    """obj.method(args...)"""
    obj:    Node        = None
    method: str         = ""
    args:   List[Node]  = field(default_factory=list)
    kwargs: List[tuple] = field(default_factory=list)

@dataclass
class NewInstance(Node):
    """Blueprint.new(field: val, ...)"""
    blueprint: str          = ""
    kwargs:    List[tuple]  = field(default_factory=list)  # List[(str, Node)]

@dataclass
class Lambda(Node):
    """fun(params) => expr"""
    params: List[Param]  = field(default_factory=list)
    body:   Node         = None   # Peut être une expression ou un Block

@dataclass
class IfExpression(Node):
    """if cond then a else b end  (expression inline)"""
    condition:   Node = None
    then_value:  Node = None
    else_value:  Node = None

@dataclass
class ErrorPropagate(Node):
    """expr?  — propage l'erreur Result[T]"""
    expr: Node = None


# ── Annotations de type ───────────────────────────────────────────────────────

@dataclass
class TypeAnnotation(Node):
    """String, Int, List[String], Map[String, Int], T?, Result[T]"""
    name:       str              = ""
    params:     List[TypeAnnotation] = field(default_factory=list)
    optional:   bool             = False   # T?


# ── Déclarations ──────────────────────────────────────────────────────────────

@dataclass
class VarDecl(Node):
    """name = expr  ou  name: Type = expr"""
    name:        str                    = ""
    type_ann:    Optional[TypeAnnotation] = None
    value:       Optional[Node]           = None
    is_const:    bool                   = False

@dataclass
class Param(Node):
    """Paramètre d'une fonction : name: Type = default"""
    name:      str                    = ""
    type_ann:  Optional[TypeAnnotation] = None
    default:   Optional[Node]           = None

@dataclass
class FunDecl(Node):
    """fun name(params) -> ReturnType\n    body\nend"""
    name:        str                    = ""
    params:      List[Param]            = field(default_factory=list)
    return_type: Optional[TypeAnnotation] = None
    body:        List[Node]             = field(default_factory=list)
    is_export:   bool                   = False
    decorators:  List[str]              = field(default_factory=list)   # @strict, etc.

@dataclass
class Field(Node):
    """Champ d'un blueprint : name: Type = default"""
    name:      str                    = ""
    type_ann:  Optional[TypeAnnotation] = None
    default:   Optional[Node]           = None

@dataclass
class BlueprintDecl(Node):
    """blueprint Name [extends Parent] [implements Trait, ...]\n    fields + methods\nend"""
    name:        str         = ""
    extends:     Optional[str] = None
    implements:  List[str]   = field(default_factory=list)
    fields:      List[Field] = field(default_factory=list)
    methods:     List[FunDecl] = field(default_factory=list)
    is_export:   bool        = False

@dataclass
class TraitDecl(Node):
    """trait Name\n    fun signatures\nend"""
    name:      str           = ""
    methods:   List[FunDecl] = field(default_factory=list)
    is_export: bool          = False

@dataclass
class ImportDecl(Node):
    """import path [as alias]"""
    path:  str           = ""
    alias: Optional[str] = None

@dataclass
class ExportDecl(Node):
    """export <declaration>"""
    declaration: Node = None


# ── Statements ────────────────────────────────────────────────────────────────

@dataclass
class Block(Node):
    """Séquence de statements (corps de fun, if, for, etc.)"""
    statements: List[Node] = field(default_factory=list)

@dataclass
class Assign(Node):
    """target = expr  ou  target += expr, etc."""
    target: Node = None
    op:     str  = "="     # =, +=, -=, *=, /=
    value:  Node = None

@dataclass
class Return(Node):
    value: Optional[Node] = None

@dataclass
class IfStmt(Node):
    """if cond\n    body\n[else if ...]\n[else\n    body]\nend"""
    condition:   Node          = None
    then_body:   List[Node]    = field(default_factory=list)
    elif_clauses: List[tuple]  = field(default_factory=list)  # List[(cond, List[Node])]
    else_body:   List[Node]    = field(default_factory=list)

@dataclass
class UnlessStmt(Node):
    """unless cond\n    body\nend"""
    condition: Node       = None
    body:      List[Node] = field(default_factory=list)

@dataclass
class WhileStmt(Node):
    """while cond\n    body\nend"""
    condition: Node       = None
    body:      List[Node] = field(default_factory=list)

@dataclass
class ForStmt(Node):
    """for [index,] var in iterable\n    body\nend"""
    var:       str        = ""
    index_var: Optional[str] = None   # for i, user in users
    iterable:  Node       = None
    body:      List[Node] = field(default_factory=list)

@dataclass
class MatchStmt(Node):
    """match expr\n    pattern => stmt\n    _ => stmt\nend"""
    subject: Node          = None
    cases:   List[tuple]   = field(default_factory=list)  # List[(pattern_Node, Node)]

@dataclass
class TryCatch(Node):
    """try\n    body\ncatch err: Type\n    handler\nend"""
    try_body:    List[Node] = field(default_factory=list)
    error_var:   str        = ""
    error_type:  Optional[TypeAnnotation] = None
    catch_body:  List[Node] = field(default_factory=list)

@dataclass
class ExprStmt(Node):
    """Une expression utilisée comme statement (ex: appel de fonction)."""
    expr: Node = None


# ── Utilitaire debug ──────────────────────────────────────────────────────────

def _indent(text: str, n: int = 2) -> str:
    pad = " " * n
    return "\n".join(pad + line for line in text.splitlines())

def pretty(node: Any, depth: int = 0) -> str:
    """Affichage lisible de l'AST pour le debug."""
    pad = "  " * depth
    if node is None:
        return f"{pad}None"
    if isinstance(node, list):
        if not node:
            return f"{pad}[]"
        items = "\n".join(pretty(n, depth + 1) for n in node)
        return f"{pad}[\n{items}\n{pad}]"
    if isinstance(node, tuple):
        parts = ", ".join(pretty(x, 0) for x in node)
        return f"{pad}({parts})"
    if isinstance(node, Node):
        cls  = type(node).__name__
        flds = {k: v for k, v in node.__dict__.items()
                if k not in ("line", "column") and v not in (None, [], {})}
        if not flds:
            return f"{pad}{cls}()"
        lines = [f"{pad}{cls}"]
        for k, v in flds.items():
            rendered = pretty(v, depth + 1)
            lines.append(f"{pad}  {k}:\n{rendered}")
        return "\n".join(lines)
    return f"{pad}{node!r}"
