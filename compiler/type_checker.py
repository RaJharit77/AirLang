"""
AirLang — type_checker.py
Résolution des noms, vérification et inférence de types.

Le type checker ANNOTE l'AST : chaque expression reçoit `node.ty` (un AirType),
chaque identifiant `node.kind`, chaque appel ses arguments ordonnés
(`node.resolved`, valeurs par défaut incluses), etc. Le générateur de code C
lit ces annotations et ne devine jamais un type.

Règles principales (v0.2) :
  - Pas de coercition implicite, sauf l'élargissement Int → Float.
  - `"texte" + 3` est une erreur : utiliser l'interpolation `"texte {3}"`.
  - Les conditions (`if`, `while`, `unless`, `and`, `or`, `not`) exigent un Bool.
  - `Any` désactive la vérification pour la valeur concernée (typage progressif).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .ast_nodes import *
from .errors import (
    ErrorCollector, AirTypeError, AirNameError, did_you_mean,
    err_undefined_var, err_undefined_fun, err_undefined_blueprint,
    err_type_mismatch, err_wrong_arg_count, err_null_access,
    err_missing_return, err_trait_not_implemented,
)


# ── Types AirLang ─────────────────────────────────────────────────────────────

class AirType:
    """Représentation d'un type AirLang durant la vérification."""

    def __init__(self, name: str, params: List["AirType"] = None, optional: bool = False):
        self.name     = name
        self.params   = params or []
        self.optional = optional

    def __eq__(self, other):
        if not isinstance(other, AirType):
            return False
        return (self.name == other.name and
                self.params == other.params and
                self.optional == other.optional)

    def __hash__(self):
        return hash((self.name, tuple(self.params), self.optional))

    def __str__(self):
        s = self.name
        if self.params:
            s += "[" + ", ".join(str(p) for p in self.params) + "]"
        if self.optional:
            s += "?"
        return s

    __repr__ = __str__

    def non_optional(self) -> "AirType":
        return AirType(self.name, self.params, False)

    def is_compatible_with(self, other: "AirType") -> bool:
        """self est assignable à other (hors sous-typage des blueprints)."""
        if other.name == "Any" or self.name == "Any":
            return True
        if self.name == "Null":
            return other.optional or other.name == "Null"
        if self.optional and not other.optional:
            return False
        if self.name == "Int" and other.name == "Float":
            return True
        if self.name != other.name or len(self.params) != len(other.params):
            return False
        return all(a.is_compatible_with(b) for a, b in zip(self.params, other.params))


T_INT    = AirType("Int")
T_FLOAT  = AirType("Float")
T_BOOL   = AirType("Bool")
T_STRING = AirType("String")
T_NULL   = AirType("Null")
T_VOID   = AirType("Void")
T_ANY    = AirType("Any")

PRIMITIVES = {"Int", "Float", "Bool", "String", "Char", "Null", "Void", "Any",
              "List", "Map", "Result", "Fun", "Error"}


def is_numeric(t: AirType) -> bool:
    return t.name in ("Int", "Float") and not t.optional


# ── Table des symboles ────────────────────────────────────────────────────────

class Symbol:
    def __init__(self, type_: AirType, kind: str = "local", const: bool = False):
        self.type  = type_
        self.kind  = kind          # "local" | "global" | "field"
        self.const = const


class FunInfo:
    def __init__(self, params: List[tuple], return_type: Optional[AirType],
                 decl: Optional[FunDecl] = None, owner: Optional[str] = None):
        self.params:      List[tuple]        = params       # [(name, AirType)]
        self.return_type: Optional[AirType]  = return_type  # None = à inférer
        self.decl         = decl
        self.owner        = owner                           # nom du blueprint
        self.defaults:    Dict[str, Node]    = {}
        if decl is not None:
            for p in decl.params:
                if p.default is not None:
                    self.defaults[p.name] = p.default
        self.checked     = False
        self.in_progress = False


class BlueprintInfo:
    def __init__(self, name: str, fields: Dict[str, AirType], methods: Dict[str, FunInfo],
                 extends: Optional[str] = None, implements: List[str] = None,
                 defaults: Dict[str, Node] = None):
        self.name       = name
        self.fields     = fields
        self.methods    = methods
        self.extends    = extends
        self.implements = implements or []
        self.defaults   = defaults or {}


class TraitInfo:
    def __init__(self, methods: Dict[str, FunInfo]):
        self.methods = methods


class Scope:
    def __init__(self, parent: Optional["Scope"] = None, name: str = "<global>"):
        self.parent = parent
        self.name   = name
        self.syms:       Dict[str, Symbol]    = {}
        self.funs:       Dict[str, FunInfo]   = {}
        self.blueprints: Dict[str, object]    = {}
        self.lambda_node = None        # la Lambda qui possède cette portée (captures)

    # variables
    def define_var(self, name: str, t: AirType, kind: Optional[str] = None, const: bool = False):
        if kind is None:
            kind = "global" if self.parent is None else "local"
        self.syms[name] = Symbol(t, kind, const)

    def resolve_symbol(self, name: str) -> Optional[Symbol]:
        s = self
        while s:
            if name in s.syms:
                return s.syms[name]
            s = s.parent
        return None

    def resolve_var(self, name: str) -> Optional[AirType]:
        sym = self.resolve_symbol(name)
        return sym.type if sym else None

    def all_var_names(self) -> List[str]:
        names, s = [], self
        while s:
            names.extend(s.syms)
            s = s.parent
        return names

    # fonctions
    def define_fun(self, name: str, info: FunInfo):
        self.funs[name] = info

    def resolve_fun(self, name: str) -> Optional[FunInfo]:
        s = self
        while s:
            if name in s.funs:
                return s.funs[name]
            s = s.parent
        return None

    def all_fun_names(self) -> List[str]:
        names, s = [], self
        while s:
            names.extend(s.funs)
            s = s.parent
        return names

    # blueprints / traits
    def define_blueprint(self, name: str, info):
        self.blueprints[name] = info

    def resolve_blueprint(self, name: str):
        s = self
        while s:
            if name in s.blueprints:
                return s.blueprints[name]
            s = s.parent
        return None

    def child(self, name: str = "") -> "Scope":
        return Scope(parent=self, name=name)


# ── Méthodes intégrées ────────────────────────────────────────────────────────

STRING_METHODS = {
    "length":      ([], T_INT),
    "upper":       ([], T_STRING),
    "lower":       ([], T_STRING),
    "trim":        ([], T_STRING),
    "contains":    ([T_STRING], T_BOOL),
    "starts_with": ([T_STRING], T_BOOL),
    "ends_with":   ([T_STRING], T_BOOL),
    "replace":     ([T_STRING, T_STRING], T_STRING),
    "split":       ([T_STRING], AirType("List", [T_STRING])),
    "slice":       ([T_INT, T_INT], T_STRING),                     # slice(début, fin) : [début, fin[
    "to_int":      ([], AirType("Int", optional=True)),            # "42" -> 42, "abc" -> null
    "to_float":    ([], AirType("Float", optional=True)),
}


def list_methods(elem: AirType) -> dict:
    """Méthodes intégrées de List[elem] : nom -> (types des paramètres, type de retour)."""
    lst = AirType("List", [elem])
    m = {
        "append":   ([elem], T_VOID),     # ajoute à la fin (modifie la liste)
        "length":   ([], T_INT),
        "pop":      ([], elem),           # retire et retourne le dernier
        "first":    ([], elem),
        "last":     ([], elem),
        "contains": ([elem], T_BOOL),
        "index_of": ([elem], T_INT),      # -1 si absent
        "remove_at": ([T_INT], elem),     # retire et retourne l'élément à l'indice
        "clear":    ([], T_VOID),
        "reverse":  ([], lst),            # retourne une NOUVELLE liste (l'originale ne change pas)
        "sort":     ([], lst),            # idem : nouvelle liste triée
    }
    if elem.name == "String":
        m["join"] = ([T_STRING], T_STRING)
    return m


def map_methods(key: AirType, val: AirType) -> dict:
    return {
        "length": ([], T_INT),
        "has":    ([key], T_BOOL),
        "get_or": ([key, val], val),      # valeur, ou le défaut si la clé est absente
        "keys":   ([], AirType("List", [key])),
        "values": ([], AirType("List", [val])),
        "delete": ([key], T_VOID),
        "clear":  ([], T_VOID),
    }


# ── Type Checker ──────────────────────────────────────────────────────────────

class TypeChecker:

    # Fonctions intégrées (le contrôle d'arguments est spécifique, cf. _infer_builtin)
    BUILTINS = {"print", "len", "str", "int", "float", "Ok", "Err", "fail", "assert", "assert_eq", "exit"}

    def __init__(self, source: str = "", filename: str = "<source>"):
        self.source   = source
        self.filename = filename
        self.errors   = ErrorCollector()
        self.global_scope = Scope()
        self.scope        = self.global_scope
        self._fun_ctx: Optional[dict] = None     # contexte de la fonction courante
        self._current_bp: Optional[BlueprintInfo] = None
        self._infos: Dict[int, FunInfo] = {}     # id(FunDecl) -> FunInfo
        self._loop_depth = 0                     # nombre de boucles englobantes (break/continue)

    # ── Utilitaires ─────────────────────────────────────────────────────────

    def _kw(self, node: Node, length: Optional[int] = None) -> dict:
        if length is None:
            if isinstance(node, Identifier):
                length = len(node.name)
            elif isinstance(node, Call) and isinstance(node.callee, Identifier):
                length = len(node.callee.name)
            elif isinstance(node, BinaryOp):
                length = len(node.op)
            elif isinstance(node, (FunDecl, VarDecl, BlueprintDecl)):
                length = len(node.name)
            else:
                length = 1
        return {"line": node.line, "column": node.column,
                "source": self.source, "filename": self.filename, "length": length}

    def err(self, e):
        self.errors.add(e)

    def _type_err(self, node: Node, message: str, hint: str = None, length: int = None):
        self.err(AirTypeError(message, hint=hint, **self._kw(node, length)))

    def _resolve_type(self, ann: Optional[TypeAnnotation]) -> AirType:
        """Convertit une annotation en AirType et valide que le type existe."""
        if ann is None:
            return T_ANY
        if ann.name not in PRIMITIVES and self.global_scope.resolve_blueprint(ann.name) is None:
            near = did_you_mean(ann.name, list(PRIMITIVES) + list(self._all_blueprint_names()))
            self.err(AirNameError(
                f"type inconnu `{ann.name}`",
                hint=("vouliez-vous dire " + " ou ".join(f"`{n}`" for n in near) + " ?")
                     if near else f"déclarez `blueprint {ann.name}` ou utilisez un type existant",
                **self._kw(ann, len(ann.name))))
            return T_ANY
        params = [self._resolve_type(p) for p in ann.params]
        if ann.name == "List" and len(params) != 1:
            self._type_err(ann, "`List` attend un type d'élément", hint="écrivez par exemple `List[Int]`",
                           length=4)
            return T_ANY
        if ann.name == "Result":
            if len(params) != 1:
                self._type_err(ann, "`Result` attend un type de valeur", hint="écrivez par exemple `Result[Float]`",
                               length=6)
                return T_ANY
            if params[0].name in ("Void", "Any", "Null"):
                self._type_err(ann, f"`Result[{params[0]}]` n'est pas supporté",
                               hint="utilisez un type précis, ex : `Result[Bool]`", length=6)
                return T_ANY
        if ann.name == "Fun" and not params:
            self._type_err(ann, "`Fun` attend ses types", hint="écrivez par exemple `Fun[Int, Int]` "
                           "(paramètres puis type de retour)", length=3)
            return T_ANY
        if ann.name == "Map":
            if len(params) != 2:
                self._type_err(ann, "`Map` attend un type de clé et un type de valeur",
                               hint="écrivez par exemple `Map[String, Int]`", length=3)
                return T_ANY
            if params[0].name not in ("String", "Any"):
                self._type_err(ann, f"les clés d'une `Map` doivent être des `String`, pas `{params[0]}`",
                               hint="seules les clés `String` sont supportées pour l'instant", length=3)
                return T_ANY
        return AirType(ann.name, params, ann.optional)

    def _all_blueprint_names(self) -> List[str]:
        return list(self.global_scope.blueprints)

    # sous-typage nominal des blueprints
    def _bp_chain(self, name: str) -> List[str]:
        chain, cur = [], name
        while cur and cur not in chain:
            chain.append(cur)
            info = self.global_scope.resolve_blueprint(cur)
            cur = info.extends if isinstance(info, BlueprintInfo) else None
        return chain

    def assignable(self, src: AirType, dst: AirType) -> bool:
        if src.name == "Any" or dst.name == "Any":
            return True
        if src.name == "Null":
            return dst.optional or dst.name == "Null"
        if src.optional and not dst.optional:
            return False
        if src.name == "Int" and dst.name == "Float":
            return True
        if src.name != dst.name:
            info = self.global_scope.resolve_blueprint(src.name)
            if isinstance(info, BlueprintInfo):
                if dst.name in self._bp_chain(src.name):
                    return True
                for b in self._bp_chain(src.name):
                    bi = self.global_scope.resolve_blueprint(b)
                    if isinstance(bi, BlueprintInfo) and dst.name in bi.implements:
                        return True
            return False
        if len(src.params) != len(dst.params):
            return len(src.params) == 0 or len(dst.params) == 0
        # Les types paramétrés sont invariants : `List[Int]` n'est PAS une `List[Float]`
        # (les éléments ont une représentation mémoire différente).
        return all(self._same_type(a, b) for a, b in zip(src.params, dst.params))

    def _same_type(self, a: AirType, b: AirType) -> bool:
        if a.name == "Any" or b.name == "Any":
            return True
        return (a.name == b.name and a.optional == b.optional and len(a.params) == len(b.params)
                and all(self._same_type(x, y) for x, y in zip(a.params, b.params)))

    def _retype_literal(self, node: Node, expected: AirType) -> bool:
        """`x: List[Float] = [1, 2]` et `tasks: List[Task] = []` : un littéral de liste/map prend
        le type attendu, et chaque élément est vérifié (et converti) vers le type d'élément."""
        if expected.name == "List" and isinstance(node, ListLiteral) and expected.params \
                and expected.params[0].name != "Any":
            et = expected.params[0]
            for e in node.elements:
                if e.ty is None:
                    self.infer(e)
                self._expect(e, e.ty, et)
            node.ty = expected.non_optional()
            return True
        if expected.name == "Map" and isinstance(node, MapLiteral) and len(expected.params) == 2 \
                and expected.params[1].name != "Any":
            kt, vt = expected.params
            for k, v in node.pairs:
                for n in (k, v):
                    if n.ty is None:
                        self.infer(n)
                self._expect(k, k.ty, kt)
                self._expect(v, v.ty, vt)
            node.ty = expected.non_optional()
            return True
        return False

    def _has_any(self, t: AirType) -> bool:
        return t.name == "Any" or any(self._has_any(p) for p in t.params)

    def _merge(self, a: AirType, b: AirType) -> Optional[AirType]:
        """Type commun de deux branches (`if`/`match`) ; préfère le type le plus précis
        (`Result[Float]` plutôt que `Result[Any]`). None si incompatibles."""
        ha, hb = self._has_any(a), self._has_any(b)
        if ha and not hb and self.assignable(a, b):
            return b
        if hb and not ha and self.assignable(b, a):
            return a
        if self.assignable(a, b):
            return b
        if self.assignable(b, a):
            return a
        return None

    def _adopt(self, node: Node, target: Optional[AirType]):
        """Pousse un type `Result[T]` connu dans les `Ok(...)`/`Err(...)` (typés `Result[Any]` quand
        le contexte manquait) à travers `if` et `match` en expression."""
        if target is None or target.name != "Result" or not target.params or self._has_any(target):
            return
        cur = getattr(node, "ty", None)
        if isinstance(node, Call) and getattr(node, "builtin", None) in ("Ok", "Err"):
            if cur is not None and cur.name == "Result" and self._has_any(cur):
                node.ty = target
        elif isinstance(node, IfExpression):
            self._adopt(node.then_value, target)
            self._adopt(node.else_value, target)
            if cur is not None and self._has_any(cur):
                node.ty = target
        elif isinstance(node, MatchExpr):
            for _, v in node.cases:
                self._adopt(v, target)
            if cur is not None and self._has_any(cur):
                node.ty = target

    def _expect(self, node: Node, got: AirType, expected: AirType, hint: str = None):
        self._adopt(node, expected)
        if self._retype_literal(node, expected):
            return
        if not self.assignable(got, expected):
            kw = self._kw(node)
            if hint is None and got.optional and not expected.optional and got.name == expected.name:
                who = f"`{node.name}`" if isinstance(node, Identifier) else "cette valeur"
                hint = f"{who} peut être null : testez-la d'abord, ex : `if x == null ... end` ou `if x != null ... end`"
            self.err(err_type_mismatch(str(expected), str(got), hint=hint, **kw))

    def _expect_bool(self, node: Node, what: str):
        t = self.infer(node)
        if t.name not in ("Bool", "Any"):
            self._type_err(node, f"{what} doit être un Bool, mais c'est un `{t}`",
                           hint="utilisez une comparaison, ex : `x != 0` ou `x > 0`")

    # ── Point d'entrée ───────────────────────────────────────────────────────

    def check(self, program: Program) -> ErrorCollector:
        self._hoist(program.statements)
        # Passe 1 : instructions de premier niveau (définit les variables globales).
        # Passe 2 : corps des fonctions/blueprints, qui peuvent alors utiliser ces globales.
        deferred = []
        for stmt in program.statements:
            d = stmt.declaration if isinstance(stmt, ExportDecl) else stmt
            if isinstance(d, (FunDecl, BlueprintDecl)):
                deferred.append(stmt)
            else:
                self.check_stmt(stmt)
        for stmt in deferred:
            self.check_stmt(stmt)
        return self.errors

    # ── Hoisting (déclarations avant les corps) ──────────────────────────────

    def _hoist(self, stmts: List[Node]):
        # 1. noms de blueprints/traits (pour que les annotations de type résolvent)
        for node in stmts:
            d = node.declaration if isinstance(node, ExportDecl) else node
            if isinstance(d, BlueprintDecl):
                self.global_scope.define_blueprint(d.name, BlueprintInfo(d.name, {}, {}))
            elif isinstance(d, TraitDecl):
                self.global_scope.define_blueprint(d.name, TraitInfo({}))
        # 2. signatures
        for node in stmts:
            d = node.declaration if isinstance(node, ExportDecl) else node
            if isinstance(d, FunDecl):
                self._hoist_fun(d)
            elif isinstance(d, BlueprintDecl):
                self._hoist_blueprint(d)
            elif isinstance(d, TraitDecl):
                self._hoist_trait(d)

    def _make_info(self, node: FunDecl, owner: Optional[str] = None) -> FunInfo:
        params = []
        for p in node.params:
            t = self._resolve_type(p.type_ann)
            p.ty = t
            params.append((p.name, t))
        if node.return_type is not None:
            ret = self._resolve_type(node.return_type)
        elif self._returns_value(node.body):
            ret = None            # à inférer à partir des `return`
        else:
            ret = T_VOID
        info = FunInfo(params, ret, node, owner)
        self._infos[id(node)] = info
        return info

    def _hoist_fun(self, node: FunDecl):
        if self.global_scope.resolve_fun(node.name) is not None and node.name in self.global_scope.funs:
            self._type_err(node, f"la fonction `{node.name}` est déjà définie",
                           hint="renommez l'une des deux fonctions")
        self.global_scope.define_fun(node.name, self._make_info(node))

    def _hoist_blueprint(self, node: BlueprintDecl):
        info = self.global_scope.resolve_blueprint(node.name)
        if node.extends and self.global_scope.resolve_blueprint(node.extends) is None:
            self.err(err_undefined_blueprint(node.extends, **self._kw(node)))
        info.extends    = node.extends
        info.implements = list(node.implements)
        for f in node.fields:
            f.ty = self._resolve_type(f.type_ann)
            info.fields[f.name] = f.ty
            if f.default is not None:
                info.defaults[f.name] = f.default
        for m in node.methods:
            info.methods[m.name] = self._make_info(m, node.name)

    def _hoist_trait(self, node: TraitDecl):
        info = self.global_scope.resolve_blueprint(node.name)
        for m in node.methods:
            info.methods[m.name] = self._make_info(m, node.name)
            m.ret_ty = info.methods[m.name].return_type or T_VOID

    def _returns_value(self, stmts) -> bool:
        """Vrai si le corps contient un `return <expr>` (hors fonctions imbriquées)."""
        for s in stmts:
            if isinstance(s, Return) and s.value is not None:
                return True
            if isinstance(s, FunDecl):
                continue
            for body in self._sub_bodies(s):
                if self._returns_value(body):
                    return True
        return False

    @staticmethod
    def _sub_bodies(s: Node) -> List[List[Node]]:
        if isinstance(s, IfStmt):
            return [s.then_body] + [b for _, b in s.elif_clauses] + [s.else_body]
        if isinstance(s, (UnlessStmt, WhileStmt, ForStmt)):
            return [s.body]
        if isinstance(s, TryCatch):
            return [s.try_body, s.catch_body]
        if isinstance(s, MatchStmt):
            return [body for _, body in s.cases]
        return []

    # champs / méthodes avec héritage
    def all_fields(self, bp_name: str) -> Dict[str, AirType]:
        out: Dict[str, AirType] = {}
        for name in reversed(self._bp_chain(bp_name)):
            info = self.global_scope.resolve_blueprint(name)
            if isinstance(info, BlueprintInfo):
                out.update(info.fields)
        return out

    def all_defaults(self, bp_name: str) -> Dict[str, Node]:
        out: Dict[str, Node] = {}
        for name in reversed(self._bp_chain(bp_name)):
            info = self.global_scope.resolve_blueprint(name)
            if isinstance(info, BlueprintInfo):
                out.update(info.defaults)
        return out

    def find_method(self, bp_name: str, method: str) -> Optional[Tuple[str, FunInfo]]:
        for name in self._bp_chain(bp_name):
            info = self.global_scope.resolve_blueprint(name)
            if isinstance(info, BlueprintInfo) and method in info.methods:
                return name, info.methods[method]
        return None

    # ── Statements ────────────────────────────────────────────────────────────

    # ── Promotion après un test de nullité ───────────────────────────────────
    # `if x == null ... end` : dans la branche `x != null` (ou après une sortie anticipée),
    # `x` est traité comme non-null. Le codegen lit alors la valeur (`Identifier.narrow_from`).

    def _null_facts(self, cond: Node) -> tuple:
        """(noms non-null quand `cond` est vraie, noms non-null quand `cond` est fausse)."""
        if isinstance(cond, BinaryOp):
            if cond.op in ("==", "!="):
                a, b = cond.left, cond.right
                ident = (a if isinstance(a, Identifier) and isinstance(b, NullLiteral)
                         else b if isinstance(b, Identifier) and isinstance(a, NullLiteral) else None)
                if ident is not None:
                    return ({ident.name}, set()) if cond.op == "!=" else (set(), {ident.name})
            elif cond.op in ("and", "or"):
                lt, lf = self._null_facts(cond.left)
                rt, rf = self._null_facts(cond.right)
                return (lt | rt, lf & rf) if cond.op == "and" else (lt & rt, lf | rf)
        elif isinstance(cond, UnaryOp) and cond.op == "not":
            t, f = self._null_facts(cond.operand)
            return f, t
        return set(), set()

    def _narrow(self, names):
        """Dans la portée courante, `names` (variables optionnelles) deviennent non-null."""
        for name in names:
            sym = self.scope.resolve_symbol(name)
            if sym is not None and sym.type.optional and sym.kind != "field":
                ns = Symbol(AirType(sym.type.name, sym.type.params, False), sym.kind, sym.const)
                ns.narrow_from = getattr(sym, "narrow_from", None) or sym.type
                self.scope.syms[name] = ns

    def _always_exits(self, stmts: List[Node]) -> bool:
        """Vrai si l'exécution ne passe jamais après ce bloc (return, break, continue, fail)."""
        for st in stmts:
            if isinstance(st, (Return, Break, Continue)):
                return True
            if isinstance(st, ExprStmt) and isinstance(st.expr, Call) \
                    and getattr(st.expr, "builtin", None) in ("fail", "exit"):
                return True
            if isinstance(st, IfStmt) and st.else_body:
                branches = [st.then_body] + [b for _, b in st.elif_clauses] + [st.else_body]
                if all(self._always_exits(b) for b in branches):
                    return True
        return False

    def check_block(self, stmts: List[Node], name: str = "block", narrow=()):
        outer = self.scope
        self.scope = outer.child(name)
        self._narrow(narrow)
        self._check_stmts(stmts)
        self.scope = outer

    def _check_stmts(self, stmts: List[Node]):
        """Vérifie une suite d'instructions dans la portée courante, avec promotion après sortie anticipée."""
        for s in stmts:
            self.check_stmt(s)
            if isinstance(s, IfStmt):               # `if x == null ... return end` : la suite est non-null
                t_true, t_false = self._null_facts(s.condition)
                if not s.elif_clauses and self._always_exits(s.then_body) and not s.else_body:
                    self._narrow(t_false)
                elif not s.elif_clauses and s.else_body and self._always_exits(s.else_body) \
                        and not self._always_exits(s.then_body):
                    self._narrow(t_true)

    def _infer_narrowed(self, node: Node, names, expected=None) -> AirType:
        outer = self.scope
        self.scope = outer.child("test")
        self._narrow(names)
        t = self.infer(node, expected)
        self.scope = outer
        return t

    def check_stmt(self, node: Node):
        if isinstance(node, VarDecl):
            self._check_var_decl(node)
        elif isinstance(node, Assign):
            self._check_assign(node)
        elif isinstance(node, FunDecl):
            info = self._infos.get(id(node))
            if info is None:                       # fonction imbriquée
                info = self._make_info(node)
                self.scope.define_fun(node.name, info)
            self._check_fun(info)
        elif isinstance(node, BlueprintDecl):
            self._check_blueprint(node)
        elif isinstance(node, IfStmt):
            self._check_if(node)
        elif isinstance(node, UnlessStmt):
            self._expect_bool(node.condition, "la condition de `unless`")
            self.check_block(node.body, "unless")
        elif isinstance(node, WhileStmt):
            self._expect_bool(node.condition, "la condition de `while`")
            self._loop_depth += 1
            self.check_block(node.body, "while")
            self._loop_depth -= 1
        elif isinstance(node, (Break, Continue)):
            if self._loop_depth == 0:
                word = "break" if isinstance(node, Break) else "continue"
                self._type_err(node, f"`{word}` en dehors d'une boucle",
                               hint=f"`{word}` n'est valide que dans un `while` ou un `for`",
                               length=len(word))
        elif isinstance(node, ForStmt):
            self._check_for(node)
        elif isinstance(node, MatchStmt):
            self._check_match(node)
        elif isinstance(node, TryCatch):
            self._check_try_catch(node)
        elif isinstance(node, Return):
            self._check_return(node)
        elif isinstance(node, ExprStmt):
            self.infer(node.expr)
        elif isinstance(node, ExportDecl):
            self.check_stmt(node.declaration)
        # ImportDecl / TraitDecl : rien à vérifier en v0.2

    def _check_var_decl(self, node: VarDecl):
        ann = self._resolve_type(node.type_ann) if node.type_ann else None
        val = self.infer(node.value, ann) if node.value is not None else None
        if val is not None and val.name == "Void":
            self._type_err(node.value, "cette expression ne produit pas de valeur")
            val = T_ANY
        if ann is not None and val is not None:
            self._expect(node.value, val, ann)
        declared = ann or val or T_ANY
        if ann is None and self._untyped_collection(declared):
            self._type_err(node, f"impossible de déduire le type des éléments de `{node.name}`",
                           hint=f"annotez-le, ex : `{node.name}: List[Int] = []`", length=len(node.name))
        if declared.name == "Null" and ann is None:
            self._type_err(node, f"impossible de déduire le type de `{node.name}` à partir de `null`",
                           hint=f"annotez le type, ex : `{node.name}: String? = null`",
                           length=len(node.name))
            declared = T_ANY
        if node.name in self.scope.syms and self.scope.syms[node.name].kind != "field":
            self._type_err(node, f"la variable `{node.name}` est déjà déclarée dans ce bloc",
                           hint="supprimez la déclaration en double ou utilisez un autre nom",
                           length=len(node.name))
        self.scope.define_var(node.name, declared, const=node.is_const)
        node.var_type = declared
        node.kind = self.scope.syms[node.name].kind

    @staticmethod
    def _untyped_collection(t: AirType) -> bool:
        return t.name in ("List", "Map") and (not t.params or any(p.name == "Any" for p in t.params))

    def _check_assign(self, node: Assign):
        expected = None
        if isinstance(node.value, Lambda) and isinstance(node.target, Identifier):
            sym0 = self.scope.resolve_symbol(node.target.name)
            expected = sym0.type if sym0 else None
        val = self.infer(node.value, expected)
        if val.name == "Void":
            self._type_err(node.value, "cette expression ne produit pas de valeur")
            val = T_ANY
        node.declares = False
        t = node.target

        if isinstance(t, Identifier):
            sym = self.scope.resolve_symbol(t.name)
            if sym is None:
                if node.op != "=":
                    self.err(err_undefined_var(
                        t.name, t.line, t.column,
                        suggestions=did_you_mean(t.name, self.scope.all_var_names()),
                        source=self.source, filename=self.filename))
                    t.ty = T_ANY
                    return
                if val.name == "Null":
                    self._type_err(t, f"impossible de déduire le type de `{t.name}` à partir de `null`",
                                   hint=f"annotez le type, ex : `{t.name}: String? = null`")
                    val = T_ANY
                if self._untyped_collection(val):
                    self._type_err(t, f"impossible de déduire le type des éléments de `{t.name}`",
                                   hint=f"annotez-le, ex : `{t.name}: List[Int] = []`", length=len(t.name))
                self.scope.define_var(t.name, val)
                node.declares = True
                t.ty = val
                t.kind = self.scope.syms[t.name].kind
                node.target_type = val
                return
            if sym.const:
                self._type_err(t, f"impossible de modifier la constante `{t.name}`",
                               hint="déclarez-la sans `const` si elle doit changer")
            t.ty, t.kind = sym.type, sym.kind
            node.target_type = sym.type
            self._check_compound(node, sym.type, val)
        elif isinstance(t, MemberAccess):
            target_t = self.infer(t)
            node.target_type = target_t
            self._check_compound(node, target_t, val)
        elif isinstance(t, IndexAccess):
            target_t = self.infer(t)
            node.target_type = target_t
            self._check_compound(node, target_t, val)
        else:
            self._type_err(node.target, "cible d'affectation invalide")

    def _check_compound(self, node: Assign, target_t: AirType, val: AirType):
        if node.op == "=":
            self._expect(node.value, val, target_t)
            return
        op = node.op[:-1]
        res = self._binary_type(op, target_t, val, node)
        self._expect(node.value, res, target_t)

    # fonctions -----------------------------------------------------------------

    def _check_fun(self, info: FunInfo):
        node = info.decl
        if info.checked:
            return
        if info.in_progress:
            self._type_err(node, f"le type de retour de `{node.name}` ne peut pas être déduit (récursion)",
                           hint=f"annotez-le : `fun {node.name}(...) -> Int`", length=len(node.name))
            info.return_type = T_ANY
            return
        info.in_progress = True

        saved = (self.scope, self._fun_ctx, self._current_bp, self._loop_depth)
        self._loop_depth = 0
        bp = None
        if info.owner:
            b = self.global_scope.resolve_blueprint(info.owner)
            bp = b if isinstance(b, BlueprintInfo) else None
        self._current_bp = bp
        self.scope = self.global_scope.child(node.name)
        if bp is not None:
            for fname, ftype in self.all_fields(bp.name).items():
                self.scope.define_var(fname, ftype, kind="field")
        for p in node.params:
            self.scope.define_var(p.name, p.ty or T_ANY, kind="local")
            if p.default is not None:
                dt = self.infer(p.default)
                self._expect(p.default, dt, p.ty or T_ANY)

        ctx = {"declared": info.return_type, "returns": [], "name": node.name}
        self._fun_ctx = ctx
        self._check_stmts(node.body)

        # type de retour déduit
        if info.return_type is None:
            info.return_type = self._unify_returns(ctx, node)
        ret = info.return_type
        native = any(d.startswith("native:") for d in node.decorators)
        if not native and ret.name not in ("Void", "Any") and not self._always_returns(node.body):
            self.err(err_missing_return(node.name, **self._kw(node)))
        node.ret_ty = ret
        node.info = info

        self.scope, self._fun_ctx, self._current_bp, self._loop_depth = saved
        info.in_progress = False
        info.checked = True

    def _unify_returns(self, ctx: dict, node: FunDecl) -> AirType:
        types = [t for t, _ in ctx["returns"] if t.name != "Void"]
        if not types:
            return T_VOID
        result = types[0]
        for (t, n) in ctx["returns"][1:]:
            if self.assignable(t, result):
                continue
            if self.assignable(result, t):
                result = t
            else:
                self._type_err(n, f"`return` incohérent : `{t}` alors que les autres retournent `{result}`",
                               hint=f"annotez le type de retour de `{node.name}`")
        return result

    def _always_returns(self, stmts: List[Node]) -> bool:
        for s in stmts:
            if isinstance(s, Return):
                return True
            if isinstance(s, ExprStmt) and isinstance(s.expr, Call) \
                    and getattr(s.expr, "builtin", None) in ("fail", "exit"):
                return True                              # `fail(...)` / `exit(...)` ne reviennent jamais
            if isinstance(s, IfStmt) and s.else_body:
                branches = [s.then_body] + [b for _, b in s.elif_clauses] + [s.else_body]
                if all(self._always_returns(b) for b in branches):
                    return True
            if isinstance(s, TryCatch) and self._always_returns(s.try_body) and self._always_returns(s.catch_body):
                return True
            if isinstance(s, MatchStmt) and s.cases:
                pats = [p for p, _ in s.cases]
                total = (any(isinstance(p, Identifier) and p.name == "_" for p in pats)
                         or {p.kind for p in pats if isinstance(p, ResultPattern)} == {"Ok", "Err"})
                if total and all(self._always_returns(b) for _, b in s.cases):
                    return True
        return False

    def _ensure_checked(self, info: FunInfo):
        if info.return_type is None and info.decl is not None:
            self._check_fun(info)

    def _check_return(self, node: Return):
        ctx = self._fun_ctx
        if ctx is None:
            self._type_err(node, "`return` en dehors d'une fonction",
                           hint="`return` n'est valide que dans le corps d'une fonction", length=6)
            return
        t = self.infer(node.value, ctx["declared"]) if node.value is not None else T_VOID
        node.value_type = t
        declared = ctx["declared"]
        ctx["returns"].append((t, node))
        if declared is None:
            return
        if declared.name == "Void":
            if node.value is not None:
                self._type_err(node.value, f"`{ctx['name']}` ne retourne pas de valeur, mais un `return` en fournit une",
                               hint="supprimez la valeur ou ajoutez `-> Type` à la fonction")
        elif node.value is None:
            self._type_err(node, f"`return` sans valeur dans une fonction qui retourne `{declared}`",
                           hint=f"retournez une valeur de type `{declared}`", length=6)
        else:
            self._expect(node.value, t, declared)

    # blueprints ----------------------------------------------------------------

    def _check_blueprint(self, node: BlueprintDecl):
        info = self.global_scope.resolve_blueprint(node.name)
        if node.extends and len(self._bp_chain(node.name)) != len(set(self._bp_chain(node.name))):
            self._type_err(node, f"héritage circulaire pour `{node.name}`")
        for trait_name in node.implements:
            trait = self.global_scope.resolve_blueprint(trait_name)
            if not isinstance(trait, TraitInfo):
                self.err(err_undefined_blueprint(trait_name, **self._kw(node)))
                continue
            for mname in trait.methods:
                if self.find_method(node.name, mname) is None:
                    self.err(err_trait_not_implemented(node.name, trait_name, mname, **self._kw(node)))
        for f in node.fields:
            if f.default is not None:
                dt = self.infer(f.default)
                self._expect(f.default, dt, f.ty or T_ANY)
        for m in node.methods:
            self._check_fun(info.methods[m.name])

    # contrôle de flux ----------------------------------------------------------

    def _check_if(self, node: IfStmt):
        self._expect_bool(node.condition, "la condition de `if`")
        t_true, t_false = self._null_facts(node.condition)
        self.check_block(node.then_body, "if", t_true)
        for cond, body in node.elif_clauses:
            self._expect_bool(cond, "la condition de `else if`")
            et, ef = self._null_facts(cond)
            self.check_block(body, "else if", et | t_false)
            t_false = t_false | ef
        if node.else_body:
            self.check_block(node.else_body, "else", t_false)

    def _check_for(self, node: ForStmt):
        it = node.iterable
        if isinstance(it, RangeLiteral):
            st, et = self.infer(it.start), self.infer(it.end)
            for n, t in ((it.start, st), (it.end, et)):
                if t.name not in ("Int", "Any"):
                    self._type_err(n, f"les bornes d'un intervalle doivent être des Int, pas `{t}`")
            it.ty = AirType("Range", [T_INT])
            elem = T_INT
        else:
            t = self.infer(it)
            if t.name == "List" and t.params:
                elem = t.params[0]
            elif t.name == "Map" and len(t.params) == 2:
                elem = t.params[0]          # parcourir une map donne ses clés
            elif t == T_STRING:
                elem = T_STRING             # parcourir une chaîne donne ses caractères
            elif t.name == "Any":
                elem = T_ANY
            else:
                self._type_err(it, f"on ne peut pas parcourir une valeur de type `{t}`",
                               hint="parcourez une liste, une map ou un intervalle, ex : `for i in 0..10`")
                elem = T_ANY
        outer = self.scope
        self.scope = outer.child("for")
        self.scope.define_var(node.var, elem, kind="local")
        node.var_type = elem
        if node.index_var:
            self.scope.define_var(node.index_var, T_INT, kind="local")
        self._loop_depth += 1
        self._check_stmts(node.body)
        self._loop_depth -= 1
        self.scope = outer

    def _check_match(self, node: MatchStmt):
        subj = self.infer(node.subject)
        for pattern, body in node.cases:
            binds = self._check_pattern(pattern, subj)
            outer = self.scope
            self.scope = outer.child("match")
            for name, t in binds.items():
                self.scope.define_var(name, t, kind="local")
            for st in body:
                self.check_stmt(st)
            self.scope = outer
        self._check_exhaustive(node, subj, node.cases, as_value=False)

    def _check_try_catch(self, node: TryCatch):
        self.check_block(node.try_body, "try")
        outer = self.scope
        self.scope = outer.child("catch")
        if node.error_var:
            t = self._resolve_type(node.error_type) if node.error_type else AirType("Error")
            if t.name not in ("Error", "Any"):
                self._type_err(node.error_type, f"`catch` attend le type `Error`, pas `{t}`",
                               hint="écrivez `catch err` ou `catch err: Error`")
                t = AirType("Error")
            self.scope.define_var(node.error_var, t, kind="local")
        self._check_stmts(node.catch_body)
        self.scope = outer

    # ── Inférence ────────────────────────────────────────────────────────────

    def infer(self, node: Node, expected: Optional[AirType] = None) -> AirType:
        """Infère le type d'une expression et l'enregistre dans `node.ty`.
        `expected` (type `Fun[...]` attendu par le contexte) sert à typer les paramètres
        d'une fonction anonyme : `numbers.map(fun(x) => x * 2)`."""
        if node is None:
            return T_ANY
        if isinstance(node, (Lambda, Call, IfExpression, MatchExpr, ListLiteral)):
            node.expected = expected
        t = self._infer(node)
        node.ty = t
        return t

    def _infer(self, node: Node) -> AirType:
        if isinstance(node, IntLiteral):    return T_INT
        if isinstance(node, FloatLiteral):  return T_FLOAT
        if isinstance(node, StringLiteral): return T_STRING
        if isinstance(node, BoolLiteral):   return T_BOOL
        if isinstance(node, NullLiteral):   return T_NULL

        if isinstance(node, InterpolatedString):
            for part in node.parts:
                if isinstance(part, Node):
                    t = self.infer(part)
                    if t.name == "Void":
                        self._type_err(part, "cette expression ne produit pas de valeur à insérer")
            return T_STRING

        if isinstance(node, ListLiteral):
            exp = getattr(node, "expected", None)
            want = exp.params[0] if exp is not None and exp.name == "List" and exp.params else None
            return AirType("List", [self._unify_elements(node.elements, "liste", want)])

        if isinstance(node, MapLiteral):
            keys = [k for k, _ in node.pairs]
            vals = [v for _, v in node.pairs]
            return AirType("Map", [self._unify_elements(keys, "map"), self._unify_elements(vals, "map")])

        if isinstance(node, RangeLiteral):
            self.infer(node.start)
            self.infer(node.end)
            return AirType("Range", [T_INT])

        if isinstance(node, Identifier):
            return self._infer_identifier(node)
        if isinstance(node, BinaryOp):
            lt = self.infer(node.left)
            if node.op in ("and", "or"):
                t_true, t_false = self._null_facts(node.left)
                rt = self._infer_narrowed(node.right, t_true if node.op == "and" else t_false)
            else:
                rt = self.infer(node.right)
            return self._binary_type(node.op, lt, rt, node)
        if isinstance(node, UnaryOp):
            return self._infer_unary(node)
        if isinstance(node, Call):
            return self._infer_call(node)
        if isinstance(node, MethodCall):
            return self._infer_method_call(node)
        if isinstance(node, NewInstance):
            return self._infer_new(node)
        if isinstance(node, MemberAccess):
            return self._infer_member(node)

        if isinstance(node, IndexAccess):
            obj_t = self.infer(node.obj)
            it = self.infer(node.index)
            if obj_t.name == "List" and obj_t.params:
                if it.name not in ("Int", "Any"):
                    self._type_err(node.index, f"l'indice d'une liste doit être un `Int`, pas `{it}`")
                return obj_t.params[0]
            if obj_t.name == "Map" and len(obj_t.params) >= 2:
                if it.name not in ("String", "Any"):
                    self._type_err(node.index, f"la clé d'une map doit être une `String`, pas `{it}`")
                return obj_t.params[1]
            if obj_t.name != "Any":
                self._type_err(node, f"une valeur de type `{obj_t}` ne peut pas être indexée avec `[...]`",
                               hint="seules les listes et les maps peuvent être indexées")
            return T_ANY

        if isinstance(node, Lambda):
            return self._infer_lambda(node)

        if isinstance(node, IfExpression):
            self._expect_bool(node.condition, "la condition de `if`")
            exp = getattr(node, "expected", None)
            f_true, f_false = self._null_facts(node.condition)
            t1 = self._infer_narrowed(node.then_value, f_true, exp)
            t2 = self._infer_narrowed(node.else_value, f_false, exp)
            t = self._merge(t1, t2)
            if t is None:
                self._type_err(node.else_value, f"les deux branches ont des types différents : `{t1}` et `{t2}`")
                return T_ANY
            self._adopt(node.then_value, t)
            self._adopt(node.else_value, t)
            return t

        if isinstance(node, MatchExpr):
            return self._infer_match_expr(node)

        if isinstance(node, ErrorPropagate):
            return self._infer_propagate(node)

        if isinstance(node, ExprStmt):
            return self.infer(node.expr)
        return T_ANY

    def _infer_propagate(self, node: ErrorPropagate) -> AirType:
        """`expr?` : si `expr` est un Err, la fonction courante retourne cette erreur tout de suite."""
        inner = self.infer(node.expr)
        if inner.name == "Any":
            return T_ANY
        if inner.name != "Result" or not inner.params:
            self._type_err(node, f"l'opérateur `?` s'applique à un `Result`, pas à `{inner}`",
                           hint="`?` propage l'erreur d'un `Result[T]` et donne la valeur `T`")
            return inner
        ctx = self._fun_ctx
        in_lambda, s = False, self.scope
        while s is not None:
            in_lambda = in_lambda or s.lambda_node is not None
            s = s.parent
        decl = ctx["declared"] if ctx else None
        if in_lambda or decl is None or decl.name != "Result":
            self._type_err(node, "`?` n'est valide que dans une fonction qui retourne un `Result[...]`",
                           hint=("ajoutez `-> Result[Type]` à la fonction" if not in_lambda
                                 else "dans une fonction anonyme, utilisez `match` à la place"))
        else:
            node.fun_ret = decl
        return inner.params[0]

    def _check_pattern(self, pattern: Node, subj: AirType) -> Dict[str, AirType]:
        """Vérifie un motif de `match` ; retourne les variables qu'il lie (`Ok(v)` → v)."""
        if isinstance(pattern, Identifier) and pattern.name == "_":
            pattern.ty = T_ANY
            return {}
        if isinstance(pattern, ResultPattern):
            if subj.name == "Any":
                t = T_ANY
            elif subj.name != "Result" or not subj.params:
                self._type_err(pattern, f"le motif `{pattern.kind}(...)` ne s'applique qu'à un `Result`, "
                                        f"pas à `{subj}`", length=len(pattern.kind))
                return {}
            else:
                t = subj.params[0] if pattern.kind == "Ok" else T_STRING
            pattern.ty = t
            return {} if pattern.var == "_" else {pattern.var: t}
        pt = self.infer(pattern)
        if subj.name == "Result":
            self._type_err(pattern, "un `Result` se teste avec `Ok(valeur)` et `Err(message)`")
        elif (isinstance(pattern, (IntLiteral, FloatLiteral, StringLiteral, BoolLiteral))
                and not self.assignable(pt, subj) and not self.assignable(subj, pt)):
            self._type_err(pattern, f"ce motif est de type `{pt}` mais la valeur testée est de type `{subj}`")
        return {}

    def _check_exhaustive(self, node: Node, subj: AirType, cases: list, as_value: bool):
        pats = [p for p, _ in cases]
        if any(isinstance(p, Identifier) and p.name == "_" for p in pats):
            return
        if subj.name == "Result":
            kinds = {p.kind for p in pats if isinstance(p, ResultPattern)}
            for k in ("Ok", "Err"):
                if k not in kinds:
                    self._type_err(node, f"ce `match` ne couvre pas le cas `{k}(...)`",
                                   hint="ajoutez la branche manquante, ou `_ => ...` pour tous les autres cas",
                                   length=5)
                    return
        elif as_value and not (subj.name == "Bool" and {getattr(p, "value", None) for p in pats} == {True, False}):
            self._type_err(node, "un `match` utilisé comme valeur doit couvrir tous les cas",
                           hint="ajoutez une dernière branche `_ => ...`", length=5)

    def _infer_match_expr(self, node: MatchExpr) -> AirType:
        subj = self.infer(node.subject)
        exp = getattr(node, "expected", None)
        for pattern, value in node.cases:
            binds = self._check_pattern(pattern, subj)
            outer = self.scope
            self.scope = outer.child("match")
            for name, t in binds.items():
                self.scope.define_var(name, t, kind="local")
            self.infer(value, exp)
            self.scope = outer
        self._check_exhaustive(node, subj, node.cases, as_value=True)
        if not node.cases:
            self._type_err(node, "ce `match` n'a aucune branche", length=5)
            return T_ANY
        result = node.cases[0][1].ty
        for _, v in node.cases[1:]:
            merged = self._merge(result, v.ty)
            if merged is None:
                self._type_err(v, f"les branches du `match` ont des types différents : `{result}` et `{v.ty}`")
                return T_ANY
            result = merged
        for _, v in node.cases:
            self._adopt(v, result)
        return result

    def _infer_lambda(self, node: Lambda) -> AirType:
        """Fonction anonyme : type `Fun[P1, ..., Pn, R]` (le DERNIER paramètre de type est le retour).
        Les variables de l'extérieur utilisées dans le corps sont CAPTURÉES PAR VALEUR au moment
        où la fonction est créée (`node.captures`)."""
        exp = getattr(node, "expected", None)
        exp_params: List[AirType] = []
        exp_ret: Optional[AirType] = None
        if exp is not None and exp.name == "Fun" and exp.params:
            exp_params, exp_ret = exp.params[:-1], exp.params[-1]
            if len(exp_params) != len(node.params):
                self._type_err(node, f"cette fonction anonyme prend {len(node.params)} paramètre(s), "
                                     f"mais {len(exp_params)} sont attendus ici", length=3)
        node.captures, node.uses_self = {}, False
        outer = self.scope
        self.scope = outer.child("lambda")
        self.scope.lambda_node = node
        ptypes = []
        for i, p in enumerate(node.params):
            if p.type_ann is not None:
                p.ty = self._resolve_type(p.type_ann)
            elif i < len(exp_params):
                p.ty = exp_params[i]
            else:
                p.ty = T_ANY
                self._type_err(p, f"le type du paramètre `{p.name}` ne peut pas être déduit",
                               hint=f"annotez-le : `fun({p.name}: Int) => ...`", length=len(p.name))
            self.scope.define_var(p.name, p.ty, kind="local")
            ptypes.append(p.ty)
        ret = self.infer(node.body)
        self.scope = outer
        if exp_ret is not None and exp_ret.name not in ("Any", "Void") and self.assignable(ret, exp_ret):
            ret = exp_ret             # ex. un corps `Int` pour un retour attendu `Float`
        node.ret_ty = ret
        return AirType("Fun", ptypes + [ret])

    def _note_capture(self, name: str, sym: "Symbol"):
        """`name` est utilisé ici : si elle vient de l'extérieur d'une ou plusieurs lambdas,
        chaque lambda traversée la capture (un champ d'objet capture `self`)."""
        if sym.kind == "global":
            return
        s = self.scope
        while s is not None and name not in s.syms:
            if s.lambda_node is not None:
                if sym.kind == "field":
                    s.lambda_node.uses_self = True
                else:
                    s.lambda_node.captures.setdefault(name, getattr(sym, "narrow_from", None) or sym.type)
            s = s.parent

    def _note_self_use(self):
        s = self.scope
        while s is not None:
            if s.lambda_node is not None:
                s.lambda_node.uses_self = True
            s = s.parent

    def _common_ancestor(self, a: AirType, b: AirType) -> Optional[AirType]:
        """Premier ancêtre (blueprint) de `a` auquel `b` est aussi assignable, sinon None."""
        if isinstance(self.global_scope.resolve_blueprint(a.name), BlueprintInfo):
            for anc in self._bp_chain(a.name):
                cand = AirType(anc, [], a.optional)
                if self.assignable(b, cand) and self.assignable(a, cand):
                    return cand
        return None

    def _unify_elements(self, elems: List[Node], what: str, want: Optional[AirType] = None) -> AirType:
        if not elems:
            return want if want is not None and want.name != "Any" else T_ANY
        if want is not None and want.name != "Any":      # le contexte impose le type des éléments
            for e in elems:
                t = self.infer(e, want)
                self._expect(e, t, want, hint="les éléments de la liste doivent convenir au type annoncé")
            return want
        result = self.infer(elems[0])
        for e in elems[1:]:
            t = self.infer(e)
            if self.assignable(t, result):
                continue
            if self.assignable(result, t):
                result = t
                continue
            common = self._common_ancestor(result, t)
            if common is not None:                       # [carré, cercle] -> List[Forme]
                result = common
            else:
                self._type_err(e, f"élément de type `{t}` dans une {what} de `{result}`",
                               hint="tous les éléments doivent avoir le même type")
        return result

    def _infer_identifier(self, node: Identifier) -> AirType:
        if node.name == "_":
            return T_ANY
        sym = self.scope.resolve_symbol(node.name)
        if sym is None:
            finfo = self.scope.resolve_fun(node.name)
            if finfo is not None:                     # une fonction utilisée comme VALEUR
                self._ensure_checked(finfo)
                node.kind = "function"
                return AirType("Fun", [t for _, t in finfo.params] + [finfo.return_type or T_ANY])
            self.err(err_undefined_var(
                node.name, node.line, node.column,
                suggestions=did_you_mean(node.name, self.scope.all_var_names()),
                source=self.source, filename=self.filename))
            return T_ANY
        node.kind = sym.kind
        node.narrow_from = getattr(sym, "narrow_from", None)
        self._note_capture(node.name, sym)
        return sym.type

    # opérateurs ----------------------------------------------------------------

    def _binary_type(self, op: str, lt: AirType, rt: AirType, node: Node) -> AirType:
        if op not in ("==", "!=", "and", "or"):
            sides = ((node.left, lt), (node.right, rt)) if isinstance(node, BinaryOp) \
                else ((node.target, lt), (node.value, rt))           # `x += 1`
            for side, t in sides:
                if t.optional and t.name not in ("Any", "Null"):
                    who = f"`{side.name}`" if isinstance(side, Identifier) else "cette valeur"
                    self._type_err(side, f"{who} peut être null (`{t}`) : on ne peut pas l'utiliser ici",
                                   hint="testez-la d'abord : `if x == null ... end` (puis `return`, `continue`...)",
                                   length=len(side.name) if isinstance(side, Identifier) else 1)
                    return T_BOOL if op in ("<", ">", "<=", ">=") else T_ANY
        if lt.name == "Any" or rt.name == "Any":
            return T_BOOL if op in ("==", "!=", "<", ">", "<=", ">=", "and", "or") else T_ANY

        if op in ("+", "-", "*", "/", "%"):
            if is_numeric(lt) and is_numeric(rt):
                return T_FLOAT if T_FLOAT in (lt, rt) else T_INT
            if op == "+" and lt == T_STRING and rt == T_STRING:
                return T_STRING
            if op == "+" and (lt == T_STRING or rt == T_STRING):
                other = rt if lt == T_STRING else lt
                self._type_err(node,
                    f"impossible d'ajouter `String` et `{other}` : AirLang ne convertit pas implicitement",
                    hint='utilisez l\'interpolation, ex : "texte {valeur}"')
                return T_STRING
            self._type_err(node, f"l'opérateur `{op}` n'est pas défini pour `{lt}` et `{rt}`")
            return T_ANY

        if op in ("==", "!=", "<", ">", "<=", ">=") and "Fun" in (lt.name, rt.name):
            self._type_err(node, "on ne peut pas comparer des fonctions",
                           hint="comparez plutôt leurs résultats")
            return T_BOOL
        if op in ("==", "!="):
            ok = (self.assignable(lt, rt) or self.assignable(rt, lt))
            if not ok:
                self._type_err(node, f"impossible de comparer `{lt}` et `{rt}` avec `{op}`")
            return T_BOOL

        if op in ("<", ">", "<=", ">="):
            if not (is_numeric(lt) and is_numeric(rt)) and not (lt == T_STRING and rt == T_STRING):
                self._type_err(node, f"l'opérateur `{op}` attend des nombres (ou deux String), pas `{lt}` et `{rt}`")
            return T_BOOL

        if op in ("and", "or"):
            for t in (lt, rt):
                if t != T_BOOL:
                    self._type_err(node, f"`{op}` attend des Bool, mais reçoit `{t}`",
                                   hint="utilisez une comparaison pour obtenir un Bool")
                    break
            return T_BOOL
        return T_ANY

    def _infer_unary(self, node: UnaryOp) -> AirType:
        t = self.infer(node.operand)
        if node.op == "not":
            if t.name not in ("Bool", "Any"):
                self._type_err(node, f"`not` attend un Bool, pas `{t}`")
            return T_BOOL
        if node.op == "-":
            if t.name == "Any" or is_numeric(t):
                return t
            self._type_err(node, f"le signe `-` attend un nombre, pas `{t}`")
        return T_ANY

    # appels --------------------------------------------------------------------

    def _bind_args(self, label: str, info: FunInfo, node, args, kwargs) -> List[Node]:
        """Associe arguments positionnels et nommés aux paramètres ; applique les défauts."""
        params = info.params
        node.param_types = [t for _, t in params]
        resolved: Dict[str, Node] = {}
        if len(args) > len(params):
            self.err(err_wrong_arg_count(label, len(params), len(args) + len(kwargs), **self._kw(node)))
            for a in args:
                self.infer(a)
            for _, v in kwargs:
                self.infer(v)
            return []
        for (pname, _), a in zip(params, args):
            resolved[pname] = a
        names = [p for p, _ in params]
        for kname, v in kwargs:
            if kname not in names:
                self._type_err(v, f"`{label}` n'a pas de paramètre `{kname}`",
                               hint=("vouliez-vous dire " + " ou ".join(f"`{n}`" for n in did_you_mean(kname, names)) + " ?")
                                    if did_you_mean(kname, names) else f"paramètres : {', '.join(names) or '(aucun)'}",
                               length=len(kname))
                self.infer(v)
            elif kname in resolved:
                self._type_err(v, f"le paramètre `{kname}` est fourni deux fois", length=len(kname))
            else:
                resolved[kname] = v
        out: List[Node] = []
        for pname, ptype in params:
            if pname in resolved:
                a = resolved[pname]
                at = self.infer(a, ptype)
                if at.name == "Void":
                    self._type_err(a, "cette expression ne produit pas de valeur")
                else:
                    self._expect(a, at, ptype)
                out.append(a)
            elif pname in info.defaults:
                d = info.defaults[pname]
                if d.ty is None:
                    self.infer(d)
                out.append(d)
            else:
                self._type_err(node, f"argument `{pname}` manquant dans l'appel à `{label}`",
                               hint=f"fournissez `{pname}` (type `{ptype}`)")
                return []
        return out

    def _infer_fun_value_call(self, node: Call, ft: AirType, label: str) -> AirType:
        """Appel d'une valeur de type `Fun[P..., R]` (variable, paramètre, résultat d'appel)."""
        node.is_fun_call = True
        params, ret = ft.params[:-1], ft.params[-1]
        info = FunInfo([(f"arg{i}", t) for i, t in enumerate(params)], ret)
        node.resolved = self._bind_args(label, info, node, node.args, node.kwargs)
        return ret

    def _infer_call(self, node: Call) -> AirType:
        if not isinstance(node.callee, Identifier):
            ct = self.infer(node.callee)
            if ct.name == "Fun" and ct.params:
                return self._infer_fun_value_call(node, ct, "fonction")
            for a in node.args:
                self.infer(a)
            if ct.name != "Any":
                self._type_err(node, f"on ne peut pas appeler une valeur de type `{ct}`",
                               hint="seules les fonctions (`Fun[...]`) peuvent être appelées")
            return T_ANY
        name = node.callee.name
        sym = self.scope.resolve_symbol(name)
        if sym is not None and sym.type.name == "Fun" and sym.type.params:
            node.callee.ty, node.callee.kind = sym.type, sym.kind
            self._note_capture(name, sym)
            return self._infer_fun_value_call(node, sym.type, name)
        info = self.scope.resolve_fun(name)
        node.callee.ty = T_ANY

        if info is None and self._current_bp is not None:
            found = self.find_method(self._current_bp.name, name)
            if found:
                owner, minfo = found
                node.self_method = owner
                self._note_self_use()
                self._ensure_checked(minfo)
                node.resolved = self._bind_args(name, minfo, node, node.args, node.kwargs)
                return minfo.return_type or T_ANY

        if info is None and name in self.BUILTINS:
            return self._infer_builtin(name, node)

        if info is None:
            candidates = self.scope.all_fun_names() + list(self.BUILTINS)
            self.err(err_undefined_fun(name, node.line, node.column,
                                       suggestions=did_you_mean(name, candidates),
                                       source=self.source, filename=self.filename))
            for a in node.args:
                self.infer(a)
            return T_ANY

        self._ensure_checked(info)
        node.resolved = self._bind_args(name, info, node, node.args, node.kwargs)
        return info.return_type or T_ANY

    def _infer_ok_err(self, name: str, node: Call) -> AirType:
        """`Ok(v)` / `Err("message")` : le type vient du contexte (retour, annotation) ou de `v`."""
        node.builtin = name
        exp = getattr(node, "expected", None)
        exp_res = exp if (exp is not None and exp.name == "Result" and exp.params) else None
        if len(node.args) != 1 or node.kwargs:
            self.err(err_wrong_arg_count(name, 1, len(node.args) + len(node.kwargs), **self._kw(node)))
            for a in node.args:
                self.infer(a)
            return AirType("Result", [T_ANY])
        a = node.args[0]
        node.resolved = [a]
        if name == "Err":
            at = self.infer(a)
            self._expect(a, at, T_STRING, hint="le message d'une erreur est une String")
            return exp_res if exp_res is not None else AirType("Result", [T_ANY])
        want = exp_res.params[0] if exp_res is not None and exp_res.params[0].name != "Any" else None
        at = self.infer(a, want)
        if at.name in ("Void", "Null"):
            self._type_err(a, f"`Ok(...)` attend une valeur, pas `{at}`")
            return AirType("Result", [T_ANY])
        if want is not None:
            self._expect(a, at, want)
            return exp_res
        return AirType("Result", [at])

    def _infer_builtin(self, name: str, node: Call) -> AirType:
        if name in ("Ok", "Err"):
            return self._infer_ok_err(name, node)
        node.builtin = name
        for a in node.args:
            self.infer(a)
        for _, v in node.kwargs:
            self.infer(v)
        node.resolved = list(node.args)
        if name == "print":
            for a in node.args:
                if a.ty is not None and a.ty.name == "Void":
                    self._type_err(a, "cette expression ne produit pas de valeur à afficher")
            return T_VOID
        if name == "fail":
            if len(node.args) != 1:
                self.err(err_wrong_arg_count(name, 1, len(node.args), **self._kw(node)))
            else:
                self._expect(node.args[0], node.args[0].ty, T_STRING, hint="`fail(\"message\")` prend un message")
            return T_VOID
        if name == "exit":
            if len(node.args) != 1:
                self.err(err_wrong_arg_count(name, 1, len(node.args), **self._kw(node)))
            else:
                self._expect(node.args[0], node.args[0].ty, T_INT, hint="`exit(0)` prend un code de sortie entier")
            return T_VOID
        if name == "assert":
            if len(node.args) not in (1, 2):
                self.err(err_wrong_arg_count(name, 2, len(node.args), **self._kw(node)))
            else:
                self._expect(node.args[0], node.args[0].ty, T_BOOL, hint="`assert(condition, \"message\")`")
                if len(node.args) == 2:
                    self._expect(node.args[1], node.args[1].ty, T_STRING, hint="le message est une String")
            return T_VOID
        if name == "assert_eq":
            if len(node.args) != 2:
                self.err(err_wrong_arg_count(name, 2, len(node.args), **self._kw(node)))
            else:
                a, b = node.args
                ok = (a.ty == b.ty and a.ty.name in ("Int", "Float", "Bool", "String")) or \
                     ({a.ty.name, b.ty.name} == {"Int", "Float"})
                if not ok:
                    self._type_err(a, f"`assert_eq` compare deux valeurs de même type simple (Int, Float, Bool, String), pas `{a.ty}` et `{b.ty}`",
                                   hint="comparez les champs un par un, ou utilisez `assert(a == b)`")
            return T_VOID
        if name in ("len", "str", "int", "float"):
            if len(node.args) != 1:
                self.err(err_wrong_arg_count(name, 1, len(node.args), **self._kw(node)))
            elif name == "len" and node.args[0].ty.name not in ("String", "List", "Map", "Any"):
                self._type_err(node.args[0], f"`len` attend une String, une List ou une Map, pas `{node.args[0].ty}`")
            return {"len": T_INT, "str": T_STRING, "int": T_INT, "float": T_FLOAT}[name]
        return AirType("Result", [T_ANY])      # Ok / Err

    LIST_HOF = ("map", "filter", "reduce", "each", "any", "all")

    def _infer_list_hof(self, node: MethodCall, lst: AirType) -> AirType:
        """map / filter / reduce / each / any / all : le type de l'élément est connu, donc les
        paramètres d'une fonction anonyme sont déduits (`nums.map(fun(x) => x * 2)`)."""
        elem, m, args = lst.params[0], node.method, node.args
        node.owner = "List"
        want = 2 if m == "reduce" else 1
        if len(args) != want or node.kwargs:
            self.err(err_wrong_arg_count(m, want, len(args) + len(node.kwargs), **self._kw(node)))
            for a in args:
                self.infer(a)
            return T_ANY
        if m == "reduce":
            acc = self.infer(args[0])
            if acc.name in ("Null", "Any", "Void") or acc.optional:
                self._type_err(args[0], f"la valeur initiale de `reduce` doit avoir un type précis, pas `{acc}`")
                self.infer(args[1])
                return T_ANY
            want_t = AirType("Fun", [acc, elem, acc])
            ft = self.infer(args[1], want_t)
            self._expect(args[1], ft, want_t,
                         hint=f"la fonction reçoit (accumulateur: {acc}, élément: {elem}) et retourne {acc}")
            node.param_types, node.resolved = [acc, want_t], list(args)
            return acc
        exp_ret = {"map": T_ANY, "each": T_ANY}.get(m, T_BOOL)
        ft = self.infer(args[0], AirType("Fun", [elem, exp_ret]))
        if ft.name != "Fun" or len(ft.params) != 2:
            if ft.name != "Any":
                self._type_err(args[0], f"`{m}` attend une fonction à 1 paramètre, pas `{ft}`",
                               hint=f"ex : `{m}(fun(x) => ...)`")
            return T_ANY
        if not self.assignable(elem, ft.params[0]):
            self._type_err(args[0], f"cette fonction prend un `{ft.params[0]}`, mais les éléments sont des `{elem}`")
        ret = ft.params[-1]
        if m in ("filter", "any", "all") and ret.name not in ("Bool", "Any"):
            self._type_err(args[0], f"la fonction de `{m}` doit retourner un Bool, pas `{ret}`",
                           hint="utilisez une comparaison, ex : `fun(x) => x > 0`")
        node.param_types, node.resolved = [ft], [args[0]]
        if m == "map":
            if ret.name in ("Void", "Any"):
                self._type_err(args[0], "la fonction de `map` doit retourner une valeur")
                return T_ANY
            return AirType("List", [ret])
        return {"filter": lst, "each": T_VOID, "any": T_BOOL, "all": T_BOOL}[m]

    def _infer_method_call(self, node: MethodCall) -> AirType:
        obj_t = self.infer(node.obj)
        hof = obj_t.name == "List" and bool(obj_t.params) and node.method in self.LIST_HOF
        if not hof:
            for a in node.args:
                if not isinstance(a, Lambda):      # une lambda est typée selon son paramètre attendu
                    self.infer(a)
            for _, v in node.kwargs:
                if not isinstance(v, Lambda):
                    self.infer(v)
        if hof:
            return self._infer_list_hof(node, obj_t)

        if obj_t.optional and obj_t.name not in ("Any", "Null"):
            name = node.obj.name if isinstance(node.obj, Identifier) else "valeur"
            self.err(err_null_access(name, **self._kw(node.obj)))

        if obj_t.name == "Result" and obj_t.params:
            t = obj_t.params[0]
            table = {"is_ok": ([], T_BOOL), "is_err": ([], T_BOOL), "unwrap": ([], t),
                     "unwrap_or": ([t], t), "message": ([], T_STRING)}
            sig = table.get(node.method)
            if sig is None:
                self._type_err(node, f"`{obj_t}` n'a pas de méthode `{node.method}`",
                               hint="méthodes : " + ", ".join(table) + " ; ou utilisez `match` avec Ok/Err",
                               length=len(node.method))
                return T_ANY
            params, ret = sig
            node.owner = "Result"
            info = FunInfo([(f"arg{i}", pt) for i, pt in enumerate(params)], ret)
            node.resolved = self._bind_args(node.method, info, node, node.args, node.kwargs)
            return ret

        if obj_t.name == "String":
            sig = STRING_METHODS.get(node.method)
            if sig is None:
                self._type_err(node, f"`String` n'a pas de méthode `{node.method}`",
                               hint="méthodes : " + ", ".join(STRING_METHODS), length=len(node.method))
                return T_ANY
            params, ret = sig
            node.owner = "String"
            info = FunInfo([(f"arg{i}", t) for i, t in enumerate(params)], ret)
            node.resolved = self._bind_args(node.method, info, node, node.args, node.kwargs)
            return ret

        if obj_t.name in ("List", "Map") and obj_t.params:
            table = (list_methods(obj_t.params[0]) if obj_t.name == "List"
                     else map_methods(obj_t.params[0], obj_t.params[1]))
            sig = table.get(node.method)
            if sig is None:
                near = did_you_mean(node.method, list(table))
                extra = (" ; `join` n'existe que pour `List[String]`"
                         if node.method == "join" and obj_t.name == "List" else "")
                self._type_err(node, f"`{obj_t}` n'a pas de méthode `{node.method}`",
                               hint=("vouliez-vous dire " + " ou ".join(f"`{n}`" for n in near) + " ?"
                                     if near else "méthodes : " + ", ".join(table)) + extra,
                               length=len(node.method))
                return T_ANY
            params, ret = sig
            node.owner = obj_t.name
            if node.method == "sort" and obj_t.params[0].name not in ("Int", "Float", "String"):
                self._type_err(node, f"on ne peut trier que des `Int`, `Float` ou `String`, pas `{obj_t.params[0]}`",
                               length=4)
            info = FunInfo([(f"arg{i}", t) for i, t in enumerate(params)], ret)
            node.resolved = self._bind_args(node.method, info, node, node.args, node.kwargs)
            return ret

        info = self.global_scope.resolve_blueprint(obj_t.name)
        if isinstance(info, BlueprintInfo):
            found = self.find_method(obj_t.name, node.method)
            if found is None:
                methods = []
                for b in self._bp_chain(obj_t.name):
                    bi = self.global_scope.resolve_blueprint(b)
                    methods += list(bi.methods) if isinstance(bi, BlueprintInfo) else []
                near = did_you_mean(node.method, methods)
                self._type_err(node, f"`{obj_t.name}` n'a pas de méthode `{node.method}`",
                               hint=("vouliez-vous dire " + " ou ".join(f"`{n}`" for n in near) + " ?")
                                    if near else None, length=len(node.method))
                return T_ANY
            owner, minfo = found
            node.owner = owner
            self._ensure_checked(minfo)
            node.resolved = self._bind_args(node.method, minfo, node, node.args, node.kwargs)
            return minfo.return_type or T_ANY
        if isinstance(info, TraitInfo):
            minfo = info.methods.get(node.method)
            if minfo is None:
                self._type_err(node, f"le trait `{obj_t.name}` n'a pas de méthode `{node.method}`")
                return T_ANY
            node.owner = obj_t.name
            node.resolved = self._bind_args(node.method, minfo, node, node.args, node.kwargs)
            return minfo.return_type or T_VOID
        return T_ANY

    def _infer_new(self, node: NewInstance) -> AirType:
        info = self.global_scope.resolve_blueprint(node.blueprint)
        if not isinstance(info, BlueprintInfo):
            self.err(err_undefined_blueprint(node.blueprint, node.line, node.column,
                                             source=self.source, filename=self.filename))
            for _, v in node.kwargs:
                self.infer(v)
            return T_ANY
        fields   = self.all_fields(node.blueprint)
        defaults = self.all_defaults(node.blueprint)
        given: Dict[str, Node] = {}
        for fname, v in node.kwargs:
            vt = self.infer(v, fields.get(fname))
            if fname not in fields:
                near = did_you_mean(fname, fields)
                self._type_err(v, f"`{node.blueprint}` n'a pas de champ `{fname}`",
                               hint=("vouliez-vous dire " + " ou ".join(f"`{n}`" for n in near) + " ?")
                                    if near else f"champs : {', '.join(fields) or '(aucun)'}",
                               length=len(fname))
            elif fname in given:
                self._type_err(v, f"le champ `{fname}` est fourni deux fois", length=len(fname))
            else:
                self._expect(v, vt, fields[fname])
                given[fname] = v
        resolved: List[Tuple[str, Node]] = []
        for fname, ftype in fields.items():
            if fname in given:
                resolved.append((fname, given[fname]))
            elif fname in defaults:
                d = defaults[fname]
                if d.ty is None:
                    self.infer(d)
                resolved.append((fname, d))
            elif ftype.optional:
                n = NullLiteral(line=node.line, column=node.column)
                n.ty = T_NULL
                resolved.append((fname, n))
            else:
                self._type_err(node,
                    f"le champ `{fname}` de `{node.blueprint}` est requis",
                    hint=f"ajoutez `{fname}: ...` dans `{node.blueprint}.new(...)`",
                    length=len(node.blueprint))
        node.resolved = resolved
        node.field_types = [fields[n] for n, _ in resolved]
        return AirType(node.blueprint)

    def _infer_member(self, node: MemberAccess) -> AirType:
        obj_t = self.infer(node.obj)
        if obj_t.name == "Any":
            return T_ANY
        if obj_t.optional:
            name = node.obj.name if isinstance(node.obj, Identifier) else "valeur"
            self.err(err_null_access(name, **self._kw(node.obj)))
        info = self.global_scope.resolve_blueprint(obj_t.name)
        if isinstance(info, BlueprintInfo):
            fields = self.all_fields(obj_t.name)
            if node.member in fields:
                node.owner = obj_t.name
                return fields[node.member]
            near = did_you_mean(node.member, fields)
            self._type_err(node, f"`{obj_t.name}` n'a pas de champ `{node.member}`",
                           hint=("vouliez-vous dire " + " ou ".join(f"`{n}`" for n in near) + " ?")
                                if near else f"champs : {', '.join(fields) or '(aucun)'}",
                           length=len(node.member))
            return T_ANY
        if obj_t.name == "String" and node.member == "length":
            return T_INT
        if obj_t.name == "Error":
            if node.member != "message":
                self._type_err(node, f"`Error` n'a pas de champ `{node.member}`",
                               hint="le seul champ est `message`", length=len(node.member))
                return T_ANY
            node.owner = "Error"
            return T_STRING
        return T_ANY
