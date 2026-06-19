"""
AirLang — type_checker.py
Vérification de types, inférence, et résolution des noms.
Parcourt l'AST avec le pattern Visitor.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any

from ast_nodes import *
from errors import (
    ErrorCollector, TypeError, NameError,
    err_undefined_var, err_undefined_fun, err_undefined_blueprint,
    err_type_mismatch, err_wrong_arg_count, err_null_access,
    err_missing_return, err_trait_not_implemented,
)


# ── Types AirLang (représentation interne) ────────────────────────────────────

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

    def __str__(self):
        s = self.name
        if self.params:
            s += "[" + ", ".join(str(p) for p in self.params) + "]"
        if self.optional:
            s += "?"
        return s

    def is_compatible_with(self, other: "AirType") -> bool:
        """Vérifie si self est assignable à other."""
        if other.name == "Any":
            return True
        if self.name == "Null" and other.optional:
            return True
        if self.optional and not other.optional:
            return False
        return self.name == other.name and self.params == other.params


# Types primitifs prédéfinis
T_INT    = AirType("Int")
T_FLOAT  = AirType("Float")
T_BOOL   = AirType("Bool")
T_STRING = AirType("String")
T_NULL   = AirType("Null")
T_VOID   = AirType("Void")
T_ANY    = AirType("Any")


def ann_to_type(ann: Optional[TypeAnnotation]) -> AirType:
    """Convertit une TypeAnnotation AST en AirType."""
    if ann is None:
        return T_ANY
    params = [ann_to_type(p) for p in ann.params]
    t = AirType(ann.name, params, ann.optional)
    return t


# ── Table des symboles (scope) ─────────────────────────────────────────────────

class Scope:
    def __init__(self, parent: Optional["Scope"] = None, name: str = "<global>"):
        self.parent:    Optional[Scope]     = parent
        self.name:      str                 = name
        self.vars:      Dict[str, AirType]  = {}
        self.funs:      Dict[str, "FunInfo"] = {}
        self.blueprints: Dict[str, "BlueprintInfo"] = {}
        self.traits:    Dict[str, "TraitInfo"] = {}

    def define_var(self, name: str, t: AirType):
        self.vars[name] = t

    def resolve_var(self, name: str) -> Optional[AirType]:
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.resolve_var(name)
        return None

    def define_fun(self, name: str, info: "FunInfo"):
        self.funs[name] = info

    def resolve_fun(self, name: str) -> Optional["FunInfo"]:
        if name in self.funs:
            return self.funs[name]
        if self.parent:
            return self.parent.resolve_fun(name)
        return None

    def define_blueprint(self, name: str, info: "BlueprintInfo"):
        self.blueprints[name] = info

    def resolve_blueprint(self, name: str) -> Optional["BlueprintInfo"]:
        if name in self.blueprints:
            return self.blueprints[name]
        if self.parent:
            return self.parent.resolve_blueprint(name)
        return None

    def child(self, name: str = "") -> "Scope":
        return Scope(parent=self, name=name)


class FunInfo:
    def __init__(self, params: List[tuple], return_type: AirType):
        self.params:      List[tuple] = params   # List[(name, AirType)]
        self.return_type: AirType     = return_type


class BlueprintInfo:
    def __init__(self, fields: Dict[str, AirType], methods: Dict[str, FunInfo],
                 extends: Optional[str] = None, implements: List[str] = None):
        self.fields:     Dict[str, AirType]   = fields
        self.methods:    Dict[str, FunInfo]    = methods
        self.extends:    Optional[str]         = extends
        self.implements: List[str]             = implements or []


class TraitInfo:
    def __init__(self, methods: Dict[str, FunInfo]):
        self.methods: Dict[str, FunInfo] = methods


# ── Type Checker ──────────────────────────────────────────────────────────────

class TypeChecker:

    # Fonctions built-in reconnues
    BUILTINS = {
        "print":  FunInfo([("value", T_ANY)], T_VOID),
        "len":    FunInfo([("x", T_ANY)], T_INT),
        "range":  FunInfo([("start", T_INT), ("end", T_INT)], AirType("List", [T_INT])),
        "str":    FunInfo([("x", T_ANY)], T_STRING),
        "int":    FunInfo([("x", T_ANY)], T_INT),
        "float":  FunInfo([("x", T_ANY)], T_FLOAT),
        "Ok":     FunInfo([("value", T_ANY)], AirType("Result", [T_ANY])),
        "Err":    FunInfo([("msg", T_STRING)], AirType("Result", [T_ANY])),
    }

    def __init__(self, source: str = "", filename: str = "<source>"):
        self.source   = source
        self.filename = filename
        self.errors   = ErrorCollector()
        self.scope    = Scope()
        self._current_fun_return: Optional[AirType] = None

        # Enregistrer les builtins
        for name, info in self.BUILTINS.items():
            self.scope.define_fun(name, info)

    def _kw(self, node: Node) -> dict:
        return {"line": node.line, "column": node.column,
                "source": self.source, "filename": self.filename}

    def err(self, e):
        self.errors.add(e)

    def check(self, program: Program):
        # Passe 1 : enregistrer toutes les déclarations (blueprints, funs) avant de vérifier les corps
        self._hoist(program.statements)
        # Passe 2 : vérifier chaque statement
        for stmt in program.statements:
            self.check_stmt(stmt)
        return self.errors

    # ── Hoisting ────────────────────────────────────────────────────────────────

    def _hoist(self, stmts: List[Node]):
        for node in stmts:
            if isinstance(node, FunDecl):
                params = [(p.name, ann_to_type(p.type_ann)) for p in node.params]
                ret    = ann_to_type(node.return_type)
                self.scope.define_fun(node.name, FunInfo(params, ret))
            elif isinstance(node, BlueprintDecl):
                self._hoist_blueprint(node)
            elif isinstance(node, TraitDecl):
                self._hoist_trait(node)
            elif isinstance(node, ExportDecl):
                self._hoist([node.declaration])

    def _hoist_blueprint(self, node: BlueprintDecl):
        fields  = {f.name: ann_to_type(f.type_ann) for f in node.fields}
        methods = {}
        for m in node.methods:
            params = [(p.name, ann_to_type(p.type_ann)) for p in m.params]
            ret    = ann_to_type(m.return_type)
            methods[m.name] = FunInfo(params, ret)
        info = BlueprintInfo(fields, methods, node.extends, node.implements)
        self.scope.define_blueprint(node.name, info)

    def _hoist_trait(self, node: TraitDecl):
        methods = {}
        for m in node.methods:
            params = [(p.name, ann_to_type(p.type_ann)) for p in m.params]
            ret    = ann_to_type(m.return_type)
            methods[m.name] = FunInfo(params, ret)
        self.scope.define_blueprint(node.name, TraitInfo(methods))

    # ── Statements ──────────────────────────────────────────────────────────────

    def check_stmt(self, node: Node):
        if isinstance(node, VarDecl):
            self._check_var_decl(node)
        elif isinstance(node, Assign):
            self._check_assign(node)
        elif isinstance(node, FunDecl):
            self._check_fun_decl(node)
        elif isinstance(node, BlueprintDecl):
            self._check_blueprint(node)
        elif isinstance(node, IfStmt):
            self._check_if(node)
        elif isinstance(node, UnlessStmt):
            self._check_unless(node)
        elif isinstance(node, WhileStmt):
            self._check_while(node)
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
        elif isinstance(node, ImportDecl):
            pass   # résolution de modules = Semaine 2+
        elif isinstance(node, TraitDecl):
            pass   # déjà hoisted

    def _check_var_decl(self, node: VarDecl):
        val_type = self.infer(node.value) if node.value else T_ANY
        ann_type = ann_to_type(node.type_ann) if node.type_ann else None

        if ann_type and node.value and not val_type.is_compatible_with(ann_type):
            self.err(err_type_mismatch(str(ann_type), str(val_type), **self._kw(node)))

        declared = ann_type or val_type
        self.scope.define_var(node.name, declared)

    def _check_assign(self, node: Assign):
        val_type = self.infer(node.value)
        if isinstance(node.target, Identifier):
            existing = self.scope.resolve_var(node.target.name)
            if existing and not val_type.is_compatible_with(existing):
                self.err(err_type_mismatch(str(existing), str(val_type), **self._kw(node)))
            elif not existing:
                # Nouvelle variable implicite
                self.scope.define_var(node.target.name, val_type)

    def _check_fun_decl(self, node: FunDecl):
        inner = self.scope.child(node.name)
        for p in node.params:
            inner.define_var(p.name, ann_to_type(p.type_ann))
        prev_ret              = self._current_fun_return
        self._current_fun_return = ann_to_type(node.return_type)
        outer_scope           = self.scope
        self.scope            = inner
        for stmt in node.body:
            self.check_stmt(stmt)
        self.scope               = outer_scope
        self._current_fun_return = prev_ret

    def _check_blueprint(self, node: BlueprintDecl):
        bp_info = self.scope.resolve_blueprint(node.name)

        # Vérifier les traits implémentés
        for trait_name in node.implements:
            trait = self.scope.resolve_blueprint(trait_name)
            if isinstance(trait, TraitInfo):
                for mname, minfo in trait.methods.items():
                    if mname not in bp_info.methods:
                        self.err(err_trait_not_implemented(
                            node.name, trait_name, mname, **self._kw(node)))

        # Vérifier les méthodes
        for method in node.methods:
            inner = self.scope.child(f"{node.name}.{method.name}")
            # Accès aux champs via 'self' implicite (on les injecte dans le scope)
            for fname, ftype in bp_info.fields.items():
                inner.define_var(fname, ftype)
            for p in method.params:
                inner.define_var(p.name, ann_to_type(p.type_ann))
            prev_ret              = self._current_fun_return
            self._current_fun_return = ann_to_type(method.return_type)
            outer_scope           = self.scope
            self.scope            = inner
            for stmt in method.body:
                self.check_stmt(stmt)
            self.scope               = outer_scope
            self._current_fun_return = prev_ret

    def _check_if(self, node: IfStmt):
        cond_type = self.infer(node.condition)
        inner = self.scope.child("if")
        outer = self.scope
        self.scope = inner
        for s in node.then_body:
            self.check_stmt(s)
        for cond, body in node.elif_clauses:
            self.infer(cond)
            for s in body:
                self.check_stmt(s)
        for s in node.else_body:
            self.check_stmt(s)
        self.scope = outer

    def _check_unless(self, node: UnlessStmt):
        self.infer(node.condition)
        inner = self.scope.child("unless")
        outer = self.scope
        self.scope = inner
        for s in node.body:
            self.check_stmt(s)
        self.scope = outer

    def _check_while(self, node: WhileStmt):
        self.infer(node.condition)
        inner = self.scope.child("while")
        outer = self.scope
        self.scope = inner
        for s in node.body:
            self.check_stmt(s)
        self.scope = outer

    def _check_for(self, node: ForStmt):
        iter_type = self.infer(node.iterable)
        inner     = self.scope.child("for")
        outer     = self.scope
        self.scope = inner
        # Inférer le type de l'élément itéré
        if iter_type.name == "List" and iter_type.params:
            elem_type = iter_type.params[0]
        elif iter_type.name == "Range":
            elem_type = T_INT
        else:
            elem_type = T_ANY
        inner.define_var(node.var, elem_type)
        if node.index_var:
            inner.define_var(node.index_var, T_INT)
        for s in node.body:
            self.check_stmt(s)
        self.scope = outer

    def _check_match(self, node: MatchStmt):
        self.infer(node.subject)
        for pattern, action in node.cases:
            self.infer(pattern)
            self.check_stmt(action)

    def _check_try_catch(self, node: TryCatch):
        inner = self.scope.child("try")
        outer = self.scope
        self.scope = inner
        for s in node.try_body:
            self.check_stmt(s)
        if node.error_var:
            inner.define_var(node.error_var, ann_to_type(node.error_type) or AirType("Error"))
        for s in node.catch_body:
            self.check_stmt(s)
        self.scope = outer

    def _check_return(self, node: Return):
        ret_type = self.infer(node.value) if node.value else T_VOID
        if (self._current_fun_return and
                self._current_fun_return.name not in ("Void", "Any") and
                not ret_type.is_compatible_with(self._current_fun_return)):
            self.err(err_type_mismatch(
                str(self._current_fun_return), str(ret_type), **self._kw(node)))

    # ── Inférence de types ────────────────────────────────────────────────────

    def infer(self, node: Node) -> AirType:
        if node is None:
            return T_ANY

        if isinstance(node, IntLiteral):    return T_INT
        if isinstance(node, FloatLiteral):  return T_FLOAT
        if isinstance(node, StringLiteral): return T_STRING
        if isinstance(node, BoolLiteral):   return T_BOOL
        if isinstance(node, NullLiteral):   return T_NULL

        if isinstance(node, ListLiteral):
            if node.elements:
                elem = self.infer(node.elements[0])
                return AirType("List", [elem])
            return AirType("List", [T_ANY])

        if isinstance(node, MapLiteral):
            if node.pairs:
                kt = self.infer(node.pairs[0][0])
                vt = self.infer(node.pairs[0][1])
                return AirType("Map", [kt, vt])
            return AirType("Map", [T_ANY, T_ANY])

        if isinstance(node, RangeLiteral):
            return AirType("Range", [T_INT])

        if isinstance(node, Identifier):
            if node.name == "_":
                return T_ANY
            t = self.scope.resolve_var(node.name)
            if t is None:
                # Tenter de suggérer des noms proches
                suggestions = [v for v in self.scope.vars if abs(len(v) - len(node.name)) <= 2]
                kw = self._kw(node)
                self.err(err_undefined_var(node.name, kw["line"], kw["column"],
                                           suggestions=suggestions,
                                           source=kw["source"], filename=kw["filename"]))
                return T_ANY
            return t

        if isinstance(node, BinaryOp):
            return self._infer_binary(node)

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
            if obj_t.name == "List" and obj_t.params:
                return obj_t.params[0]
            if obj_t.name == "Map" and len(obj_t.params) >= 2:
                return obj_t.params[1]
            return T_ANY

        if isinstance(node, Lambda):
            inner = self.scope.child("lambda")
            outer = self.scope
            self.scope = inner
            for p in node.params:
                inner.define_var(p.name, ann_to_type(p.type_ann))
            ret = self.infer(node.body)
            self.scope = outer
            return AirType("Fun", [ret])

        if isinstance(node, IfExpression):
            self.infer(node.condition)
            t1 = self.infer(node.then_value)
            t2 = self.infer(node.else_value)
            return t1 if t1 == t2 else T_ANY

        if isinstance(node, ErrorPropagate):
            inner = self.infer(node.expr)
            if inner.name == "Result" and inner.params:
                return inner.params[0]
            return inner

        if isinstance(node, ExprStmt):
            return self.infer(node.expr)

        return T_ANY

    def _infer_binary(self, node: BinaryOp) -> AirType:
        lt = self.infer(node.left)
        rt = self.infer(node.right)
        op = node.op

        if op in ("+", "-", "*", "/", "%"):
            if lt == T_FLOAT or rt == T_FLOAT:
                return T_FLOAT
            if lt == T_INT and rt == T_INT:
                return T_INT
            if op == "+" and (lt == T_STRING or rt == T_STRING):
                return T_STRING
            return T_ANY

        if op in ("==", "!=", "<", ">", "<=", ">=", "and", "or"):
            return T_BOOL

        return T_ANY

    def _infer_unary(self, node: UnaryOp) -> AirType:
        t = self.infer(node.operand)
        if node.op == "not":
            return T_BOOL
        if node.op == "-":
            return t if t in (T_INT, T_FLOAT) else T_ANY
        return T_ANY

    def _infer_call(self, node: Call) -> AirType:
        if isinstance(node.callee, Identifier):
            name = node.callee.name
            info = self.scope.resolve_fun(name)
            if info is None:
                self.err(err_undefined_fun(name, **self._kw(node)))
                return T_ANY
            # Vérifier le nombre d'arguments
            n_req = sum(1 for _, _ in info.params)
            n_got = len(node.args) + len(node.kwargs)
            # (On accepte Any pour les builtins variadiques)
            return info.return_type
        return T_ANY

    def _infer_method_call(self, node: MethodCall) -> AirType:
        obj_type = self.infer(node.obj)
        # Méthodes de liste built-in
        if obj_type.name == "List":
            list_methods = {
                "map":    AirType("List", [T_ANY]),
                "filter": AirType("List", obj_type.params),
                "reduce": T_ANY,
                "append": T_VOID,
                "length": T_INT,
                "sort":   AirType("List", obj_type.params),
                "unique": AirType("List", obj_type.params),
                "join":   T_STRING,
                "first":  obj_type.params[0] if obj_type.params else T_ANY,
                "last":   obj_type.params[0] if obj_type.params else T_ANY,
            }
            return list_methods.get(node.method, T_ANY)
        # Méthodes de string built-in
        if obj_type.name == "String":
            str_methods = {
                "split":    AirType("List", [T_STRING]),
                "trim":     T_STRING,
                "upper":    T_STRING,
                "lower":    T_STRING,
                "replace":  T_STRING,
                "contains": T_BOOL,
                "length":   T_INT,
            }
            return str_methods.get(node.method, T_ANY)
        # Blueprint method
        bp = self.scope.resolve_blueprint(obj_type.name)
        if isinstance(bp, BlueprintInfo):
            method = bp.methods.get(node.method)
            if method:
                return method.return_type
        return T_ANY

    def _infer_new(self, node: NewInstance) -> AirType:
        bp = self.scope.resolve_blueprint(node.blueprint)
        if bp is None:
            self.err(err_undefined_blueprint(node.blueprint, **self._kw(node)))
            return T_ANY
        # Vérifier les champs requis
        if isinstance(bp, BlueprintInfo):
            for fname, ftype in bp.fields.items():
                provided = dict(node.kwargs)
                if fname not in provided and not ftype.optional:
                    pass  # Champ manquant → on pourrait avertir ici
        return AirType(node.blueprint)

    def _infer_member(self, node: MemberAccess) -> AirType:
        obj_type = self.infer(node.obj)
        bp = self.scope.resolve_blueprint(obj_type.name)
        if isinstance(bp, BlueprintInfo):
            return bp.fields.get(node.member, T_ANY)
        return T_ANY
