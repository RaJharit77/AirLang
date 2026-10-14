"""
AirLang — codegen_c.py
Génère du C à partir de l'AST ANNOTÉ par le type checker.

Principe : le générateur ne devine jamais un type. Chaque expression porte son
type (`node.ty`), chaque identifiant sa portée (`node.kind`), chaque appel ses
arguments ordonnés (`node.resolved`). Une construction pas encore supportée
produit une CodegenError claire (ligne, colonne, version prévue) au lieu d'un
C invalide.

Représentation (v0.3) :
    List[T] → AirList* (éléments stockés par valeur)   Map[String, V] → AirMap*
    Int → int64_t     Float → double    Bool → bool    String → AirStr
    blueprint Nom → bp_Nom*  (alloué par bp_Nom_new, jamais libéré avant le comptage de références)
Nommage C : variables v_x, champs f_x, fonctions air_fn_x, méthodes bp_B_m_x.
"""

from __future__ import annotations

from typing import List, Optional

from .ast_nodes import *
from .errors import CodegenError
from .type_checker import AirType, T_INT, T_FLOAT, T_BOOL, T_STRING


def c_string_literal(value: str) -> str:
    """Littéral C sûr pour une chaîne Python (UTF-8, échappements octaux)."""
    out = []
    for b in value.encode("utf-8"):
        ch = chr(b)
        if ch == "\\":   out.append("\\\\")
        elif ch == '"':  out.append('\\"')
        elif ch == "\n": out.append("\\n")
        elif ch == "\t": out.append("\\t")
        elif ch == "\r": out.append("\\r")
        elif ch == "?":  out.append("\\?")      # évite les trigraphes
        elif 32 <= b < 127: out.append(ch)
        else:            out.append(f"\\{b:03o}")
    return '"' + "".join(out) + '"'


class CCodegen:

    def __init__(self, source: str = "", filename: str = "<source>"):
        self.source   = source
        self.filename = filename
        self.output: List[str] = []
        self.indent = 0
        self._tmp = 0
        self._blueprints: dict = {}
        self._cur_ret: Optional[AirType] = None
        self._cur_bp: Optional[str] = None

    # ── Utilitaires ─────────────────────────────────────────────────────────

    def emit(self, line: str = ""):
        self.output.append(("    " * self.indent + line) if line else "")

    def fresh(self, prefix: str = "_air_t") -> str:
        self._tmp += 1
        return f"{prefix}{self._tmp}"

    def unsupported(self, node: Node, what: str, version: str = "v0.3"):
        raise CodegenError(
            f"{what} n'est pas encore supporté par le compilateur",
            node.line, node.column, filename=self.filename, source=self.source,
            hint=f"prévu en {version} ; voir la feuille de route (ROADMAP.md)")

    def ctype(self, t: Optional[AirType], node: Node, what: str = "") -> str:
        if t is None or t.name == "Any":
            raise CodegenError(
                f"type indéterminé{(' pour ' + what) if what else ''}",
                node.line, node.column, filename=self.filename, source=self.source,
                hint="ajoutez une annotation de type, ex : `x: Int`")
        if t.optional and t.name not in self._blueprints:
            self.unsupported(node, f"le type optionnel `{t}`", "v0.4")
        simple = {"Int": "int64_t", "Float": "double", "Bool": "bool",
                  "String": "AirStr", "Void": "void"}
        if t.name in simple:
            return simple[t.name]
        if t.name in self._blueprints:
            return f"bp_{t.name}*"
        if t.name == "List" and t.params:
            self.ctype(t.params[0], node, what)      # valide le type des éléments
            return "AirList*"
        if t.name == "Map" and len(t.params) == 2:
            if t.params[0].name != "String":
                self.unsupported(node, f"une map dont les clés sont de type `{t.params[0]}`"
                                       " (seules les clés `String` existent)", "v0.5")
            self.ctype(t.params[1], node, what)
            return "AirMap*"
        self.unsupported(node, f"le type `{t}`", "v0.4 (Result, Fun)")

    @staticmethod
    def kind(t: AirType) -> str:
        """Genre d'élément du runtime (comparaison, tri, affichage)."""
        return {"Int": "AIR_K_INT", "Float": "AIR_K_FLOAT", "Bool": "AIR_K_BOOL",
                "String": "AIR_K_STRING"}.get(t.name, "AIR_K_OBJ")

    @staticmethod
    def v(name: str) -> str:
        return f"v_{name}"

    # ── Ordre d'évaluation : toujours de gauche à droite ─────────────────────
    # En C, l'ordre d'évaluation des arguments n'est pas défini. AirLang garantit
    # gauche → droite : dès qu'une expression a plusieurs opérandes dont un peut avoir
    # un effet de bord (appel, `.new`), on les évalue dans l'ordre dans des temporaires.

    def _impure(self, node) -> bool:
        if isinstance(node, (Call, MethodCall, NewInstance)):
            return True
        if isinstance(node, Node):
            return any(self._impure(v) for v in vars(node).values())
        if isinstance(node, (list, tuple)):
            return any(self._impure(v) for v in node)
        return False

    def _hoist(self, operands):
        """operands : [(nœud ou None, code, type C)]. Retourne (préfixe, codes)."""
        if len(operands) < 2 or not any(n is not None and self._impure(n) for n, _, _ in operands):
            return "", [c for _, c, _ in operands]
        decls, names = [], []
        for _, code, ct in operands:
            t = self.fresh("_air_a")
            decls.append(f"{ct} {t} = {code};")
            names.append(t)
        return " ".join(decls) + " ", names

    @staticmethod
    def _wrap(prefix: str, code: str) -> str:
        return f"({{ {prefix}{code}; }})" if prefix else code

    def _arg_operands(self, node):
        """Les arguments résolus d'un appel, déjà convertis vers le type du paramètre."""
        return [(a, self._coerce_code(self.expr(a), a.ty, pt), self.ctype(pt, a))
                for a, pt in zip(node.resolved, node.param_types)]

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def generate(self, program: Program) -> str:
        self.output, self.indent, self._tmp = [], 0, 0
        self._blueprints = {}

        funs, bps, toplevel = [], [], []
        for st in program.statements:
            d = st.declaration if isinstance(st, ExportDecl) else st
            if isinstance(d, FunDecl):
                funs.append(d)
            elif isinstance(d, BlueprintDecl):
                bps.append(d)
                self._blueprints[d.name] = d
            elif isinstance(d, (TraitDecl, ImportDecl)):
                continue
            else:
                toplevel.append(d)

        self.emit("/* Généré par AirLang (airc) — ne pas modifier à la main. */")
        self.emit('#include "air_runtime.h"')
        self.emit()

        for bp in bps:
            self.emit(f"typedef struct bp_{bp.name} bp_{bp.name};")
        for bp in bps:
            self._check_overrides(bp)
            self._vt_struct(bp)
        for bp in bps:
            self._struct(bp)

        # prototypes
        for bp in bps:
            self.emit(self._ctor_sig(bp) + ";")
            for m in bp.methods:
                self.emit(self._method_sig(bp, m) + ";")
        for f in funs:
            self.emit(self._fun_sig(f) + ";")
        self.emit()
        for bp in bps:
            self._vt_instance(bp)
        self.emit()

        # globales
        for st in toplevel:
            if isinstance(st, VarDecl) or (isinstance(st, Assign) and getattr(st, "declares", False)
                                           and isinstance(st.target, Identifier)):
                name = st.name if isinstance(st, VarDecl) else st.target.name
                t = st.var_type if isinstance(st, VarDecl) else st.target_type
                self.emit(f"static {self.ctype(t, st, f'la variable `{name}`')} {self.v(name)};")
        self.emit()

        for bp in bps:
            self._ctor(bp)
            for m in bp.methods:
                self._method(bp, m)
        for f in funs:
            self._function(f)

        self.emit("int main(void) {")
        self.indent += 1
        for st in toplevel:
            self.stmt(st, top=True)
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        return "\n".join(self.output) + "\n"

    # ── Blueprints (héritage par table virtuelle) ─────────────────────────────

    def chain(self, name: str) -> List[str]:
        """Racine → feuille : ex. ['Person', 'Employee']."""
        out, cur = [], name
        while cur and cur in self._blueprints and cur not in out:
            out.append(cur)
            cur = self._blueprints[cur].extends
        return list(reversed(out))

    def all_fields(self, name: str) -> list:
        """Champs aplatis, parent d'abord (même ordre que le type checker)."""
        seen = {}
        for c in self.chain(name):
            for f in self._blueprints[c].fields:
                seen[f.name] = f
        return list(seen.values())

    def virtuals(self, name: str) -> dict:
        """nom de méthode -> (classe qui l'introduit, FunDecl d'origine), dans l'ordre."""
        seen = {}
        for c in self.chain(name):
            for m in self._blueprints[c].methods:
                seen.setdefault(m.name, (c, m))
        return seen

    def impl_of(self, name: str, method: str):
        """Classe la plus proche de `name` (feuille → racine) qui définit `method`."""
        for c in reversed(self.chain(name)):
            for m in self._blueprints[c].methods:
                if m.name == method:
                    return c, m
        return None

    def _check_overrides(self, bp: BlueprintDecl):
        virt = self.virtuals(bp.name)
        for m in bp.methods:
            ic, im = virt[m.name]
            if ic == bp.name:
                continue
            same = (len(m.params) == len(im.params)
                    and self.ctype(m.ret_ty, m) == self.ctype(im.ret_ty, im)
                    and all(self.ctype(a.ty, a) == self.ctype(b.ty, b)
                            for a, b in zip(m.params, im.params)))
            if not same:
                raise CodegenError(
                    f"la méthode `{m.name}` de `{bp.name}` n'a pas la même signature que celle de `{ic}`",
                    m.line, m.column, filename=self.filename, source=self.source,
                    hint="une méthode redéfinie doit garder les mêmes paramètres et le même type de retour",
                    length=len(m.name))

    def _vt_fn_type(self, ic: str, im: FunDecl) -> str:
        return f"{self.ctype(im.ret_ty, im)} (*)({self._params(im.params, f'bp_{ic}* self')})"

    def _vt_struct(self, bp: BlueprintDecl):
        self.emit(f"typedef struct bp_{bp.name}_vt {{")
        self.indent += 1
        virt = self.virtuals(bp.name)
        if not virt:
            self.emit("char _air_unused;")
        for name, (ic, im) in virt.items():
            ret = self.ctype(im.ret_ty, im)
            self.emit(f"{ret} (*m_{name})({self._params(im.params, f'bp_{ic}* self')});")
        self.indent -= 1
        self.emit(f"}} bp_{bp.name}_vt;")
        self.emit()

    def _vt_instance(self, bp: BlueprintDecl):
        virt = self.virtuals(bp.name)
        self.emit(f"static const bp_{bp.name}_vt bp_{bp.name}_vtable = {{")
        self.indent += 1
        if not virt:
            self.emit("0")
        for name, (ic, im) in virt.items():
            impl, _ = self.impl_of(bp.name, name)
            self.emit(f".m_{name} = ({self._vt_fn_type(ic, im)})bp_{impl}_m_{name},")
        self.indent -= 1
        self.emit("};")

    def _struct(self, bp: BlueprintDecl):
        self.emit(f"struct bp_{bp.name} {{")
        self.indent += 1
        self.emit(f"const bp_{bp.name}_vt* vt;")
        for f in self.all_fields(bp.name):
            self.emit(f"{self.ctype(f.ty, f, f'le champ `{f.name}`')} f_{f.name};")
        self.indent -= 1
        self.emit("};")
        self.emit()

    def _ctor_sig(self, bp: BlueprintDecl) -> str:
        params = ", ".join(f"{self.ctype(f.ty, f)} {self.v(f.name)}"
                           for f in self.all_fields(bp.name)) or "void"
        return f"bp_{bp.name}* bp_{bp.name}_new({params})"

    def _ctor(self, bp: BlueprintDecl):
        self.emit(self._ctor_sig(bp) + " {")
        self.indent += 1
        self.emit(f"bp_{bp.name}* self = (bp_{bp.name}*)air_alloc(sizeof(bp_{bp.name}));")
        self.emit(f"self->vt = &bp_{bp.name}_vtable;")
        for f in self.all_fields(bp.name):
            self.emit(f"self->f_{f.name} = {self.v(f.name)};")
        self.emit("return self;")
        self.indent -= 1
        self.emit("}")
        self.emit()

    def _params(self, params, extra: Optional[str] = None) -> str:
        items = [extra] if extra else []
        for p in params:
            if p.ty is None or p.ty.name == "Any":
                raise CodegenError(
                    f"le paramètre `{p.name}` n'a pas de type",
                    p.line, p.column, filename=self.filename, source=self.source,
                    hint=f"annotez-le, ex : `{p.name}: Int`", length=len(p.name))
            items.append(f"{self.ctype(p.ty, p)} {self.v(p.name)}")
        return ", ".join(items) or "void"

    def _method_sig(self, bp: BlueprintDecl, m: FunDecl) -> str:
        ret = self.ctype(m.ret_ty, m)
        return f"{ret} bp_{bp.name}_m_{m.name}({self._params(m.params, f'bp_{bp.name}* self')})"

    def _method(self, bp: BlueprintDecl, m: FunDecl):
        prev, self._cur_bp = self._cur_bp, bp.name
        self.emit(self._method_sig(bp, m) + " {")
        self._body(m)
        self.emit("}")
        self.emit()
        self._cur_bp = prev

    # ── Fonctions ─────────────────────────────────────────────────────────────

    def _fun_sig(self, f: FunDecl) -> str:
        return f"{self.ctype(f.ret_ty, f)} air_fn_{f.name}({self._params(f.params)})"

    def _function(self, f: FunDecl):
        self.emit(self._fun_sig(f) + " {")
        self._body(f)
        self.emit("}")
        self.emit()

    def _body(self, f: FunDecl):
        prev, self._cur_ret = self._cur_ret, f.ret_ty
        self.indent += 1
        for s in f.body:
            self.stmt(s)
        self.indent -= 1
        self._cur_ret = prev

    # ── Statements ────────────────────────────────────────────────────────────

    def block(self, stmts: List[Node]):
        self.indent += 1
        for s in stmts:
            self.stmt(s)
        self.indent -= 1

    def stmt(self, node: Node, top: bool = False):
        if isinstance(node, VarDecl):
            t = node.var_type
            ct = self.ctype(t, node, f"la variable `{node.name}`")
            if node.value is not None:
                val = self.coerce(node.value, t)
            else:
                val = self._default(t, node)
            if node.kind == "global":
                self.emit(f"{self.v(node.name)} = {val};")
            else:
                self.emit(f"{'const ' if node.is_const else ''}{ct} {self.v(node.name)} = {val};")
        elif isinstance(node, Assign):
            self._assign(node)
        elif isinstance(node, IfStmt):
            self.emit(f"if ({self.expr(node.condition)}) {{")
            self.block(node.then_body)
            for cond, body in node.elif_clauses:
                self.emit(f"}} else if ({self.expr(cond)}) {{")
                self.block(body)
            if node.else_body:
                self.emit("} else {")
                self.block(node.else_body)
            self.emit("}")
        elif isinstance(node, UnlessStmt):
            self.emit(f"if (!({self.expr(node.condition)})) {{")
            self.block(node.body)
            self.emit("}")
        elif isinstance(node, WhileStmt):
            self.emit(f"while ({self.expr(node.condition)}) {{")
            self.block(node.body)
            self.emit("}")
        elif isinstance(node, ForStmt):
            self._for(node)
        elif isinstance(node, MatchStmt):
            self._match(node)
        elif isinstance(node, Return):
            if node.value is None:
                self.emit("return;")
            else:
                self.emit(f"return {self.coerce(node.value, self._cur_ret)};")
        elif isinstance(node, ExprStmt):
            code = self.expr(node.expr)
            if isinstance(node.expr, (Call, MethodCall)):
                self.emit(f"{code};")
            else:
                self.emit(f"(void)({code});")
        elif isinstance(node, Break):
            self.emit("break;")
        elif isinstance(node, Continue):
            self.emit("continue;")
        elif isinstance(node, TryCatch):
            self.unsupported(node, "`try`/`catch`", "v0.4")
        elif isinstance(node, (FunDecl, BlueprintDecl)):
            self.unsupported(node, "une déclaration imbriquée dans un bloc", "v0.3")
        elif isinstance(node, (ImportDecl, TraitDecl)):
            pass
        elif isinstance(node, ExportDecl):
            self.stmt(node.declaration, top)
        else:
            self.unsupported(node, f"l'instruction `{type(node).__name__}`")

    def _default(self, t: AirType, node: Node) -> str:
        if t.name == "Int":    return "0"
        if t.name == "Float":  return "0.0"
        if t.name == "Bool":   return "false"
        if t.name == "String": return 'AIR_STR_LIT("")'
        if t.name in self._blueprints: return "NULL"
        if t.name == "List":
            return f"air_list_new(sizeof({self.ctype(t.params[0], node)}))"
        if t.name == "Map":
            self.ctype(t, node)
            return f"air_map_new(sizeof({self.ctype(t.params[1], node)}))"
        self.unsupported(node, f"la valeur par défaut du type `{t}`")

    def _assign(self, node: Assign):
        tgt = node.target
        if isinstance(tgt, IndexAccess):
            return self._assign_index(node)
        target_code = self.expr(tgt) if not node.declares else self.v(tgt.name)
        t = node.target_type
        if node.op == "=":
            val = self.coerce(node.value, t)
        else:
            val = self._coerce_code(
                self._binary(node.op[:-1], target_code, tgt.ty if tgt.ty else t,
                             self.expr(node.value), node.value.ty, node),
                self._result_type(node.op[:-1], t, node.value.ty), t)
        if node.declares and tgt.kind != "global":
            self.emit(f"{self.ctype(t, node, f'la variable `{tgt.name}`')} {target_code} = {val};")
        else:
            self.emit(f"{target_code} = {val};")

    def _assign_index(self, node: Assign):
        tgt = node.target
        ot = tgt.obj.ty
        is_list = ot.name == "List"
        et = ot.params[0] if is_list else ot.params[1]
        ct = self.ctype(ot, node) and self.ctype(et, node)
        obj, idx = self.expr(tgt.obj), self.expr(tgt.index)
        ptr, val = self.fresh("_air_p"), self.fresh("_air_v")
        if is_list:
            getptr = f"({ct}*)air_list_at({obj}, {idx})"
        elif node.op == "=":
            getptr = f"({ct}*)air_map_slot({obj}, {idx})"      # crée la clé si absente
        else:
            getptr = f"({ct}*)air_map_get_ptr({obj}, {idx})"   # erreur si la clé est absente
        self.emit("{")
        self.indent += 1
        if node.op == "=":
            self.emit(f"{ct} {val} = {self.coerce(node.value, et)};")
            self.emit(f"{ct}* {ptr} = {getptr};")
            self.emit(f"*{ptr} = {val};")
        else:
            vct = self.ctype(node.value.ty, node.value)
            self.emit(f"{vct} {val} = {self.expr(node.value)};")
            self.emit(f"{ct}* {ptr} = {getptr};")
            op = node.op[:-1]
            code = self._binary(op, f"(*{ptr})", et, val, node.value.ty, node)
            self.emit(f"*{ptr} = {self._coerce_code(code, self._result_type(op, et, node.value.ty), et)};")
        self.indent -= 1
        self.emit("}")

    def _for(self, node: ForStmt):
        it = node.iterable
        if not isinstance(it, RangeLiteral):
            return self._for_collection(node)
        i, end = self.fresh("_air_i"), self.fresh("_air_end")
        self.emit("{")
        self.indent += 1
        self.emit(f"int64_t {end} = {self.expr(it.end)};")
        self.emit(f"for (int64_t {i} = {self.expr(it.start)}; {i} < {end}; {i}++) {{")
        self.indent += 1
        self.emit(f"int64_t {self.v(node.var)} = {i};")
        if node.index_var:
            self.emit(f"int64_t {self.v(node.index_var)} = {i} - {self.expr(it.start)};")
        for s in node.body:
            self.stmt(s)
        self.indent -= 1
        self.emit("}")
        self.indent -= 1
        self.emit("}")

    def _for_collection(self, node: ForStmt):
        t = node.iterable.ty
        lst, i = self.fresh("_air_l"), self.fresh("_air_i")
        if t.name == "List":
            src, free = self.expr(node.iterable), False
        elif t.name == "Map":
            self.ctype(t, node)
            src, free = f"air_map_keys({self.expr(node.iterable)})", True   # on parcourt les clés
        else:
            self.unsupported(node, f"le parcours d'une valeur de type `{t}`")
        et = node.var_type
        ct = self.ctype(et, node, f"la variable `{node.var}`")
        self.emit("{")
        self.indent += 1
        self.emit(f"AirList* {lst} = {src};")
        self.emit(f"for (int64_t {i} = 0; {i} < air_list_length({lst}); {i}++) {{")
        self.indent += 1
        self.emit(f"{ct} {self.v(node.var)} = AIR_LIST_AT({ct}, {lst}, {i});")
        if node.index_var:
            self.emit(f"int64_t {self.v(node.index_var)} = {i};")
        for s in node.body:
            self.stmt(s)
        self.indent -= 1
        self.emit("}")
        if free:
            self.emit(f"air_list_free({lst});")
        self.indent -= 1
        self.emit("}")

    def _match(self, node: MatchStmt):
        st = node.subject.ty
        if st is None or st.name not in ("Int", "String", "Bool"):
            self.unsupported(node, f"`match` sur une valeur de type `{st}`", "v0.4")
        tmp = self.fresh("_air_m")
        self.emit("{")
        self.indent += 1
        self.emit(f"{self.ctype(st, node)} {tmp} = {self.expr(node.subject)};")
        first = True
        for pattern, action in node.cases:
            if isinstance(pattern, Identifier) and pattern.name == "_":
                self.emit("{" if first else "} else {")
            elif isinstance(pattern, (IntLiteral, StringLiteral, BoolLiteral)):
                cond = self._equals(tmp, st, self.expr(pattern), pattern.ty)
                self.emit(("if (" if first else "} else if (") + cond + ") {")
            else:
                self.unsupported(pattern, "ce motif de `match`", "v0.4")
            first = False
            self.indent += 1
            self.stmt(action)
            self.indent -= 1
        if node.cases:
            self.emit("}")
        self.indent -= 1
        self.emit("}")

    # ── Expressions ───────────────────────────────────────────────────────────

    def coerce(self, node: Node, target: Optional[AirType]) -> str:
        return self._coerce_code(self.expr(node), node.ty, target)

    def _coerce_code(self, code: str, src: Optional[AirType], dst: Optional[AirType]) -> str:
        if src is not None and dst is not None:
            if src.name == "Int" and dst.name == "Float":
                return f"((double)({code}))"
            if (src.name != dst.name and src.name in self._blueprints
                    and dst.name in self._blueprints):
                return f"((bp_{dst.name}*)({code}))"      # enfant → parent
        return code

    def to_str(self, node: Node) -> str:
        """Code C qui convertit `node` en AirStr (selon son type statique)."""
        code, t = self.expr(node), node.ty
        if t is None:
            self.unsupported(node, "une valeur sans type")
        if t.name == "String": return code
        if t.name == "Int":    return f"air_int_to_str({code})"
        if t.name == "Float":  return f"air_float_to_str({code})"
        if t.name == "Bool":   return f"air_bool_to_str({code})"
        if t.name == "List" and t.params:
            self.ctype(t, node)
            return f"air_list_to_str({code}, {self.kind(t.params[0])})"
        if t.name == "Map" and len(t.params) == 2:
            self.ctype(t, node)
            return f"air_map_to_str({code}, {self.kind(t.params[1])})"
        self.unsupported(node, f"l'affichage d'une valeur de type `{t}`", "v0.4")

    def expr(self, node: Node) -> str:
        if isinstance(node, IntLiteral):
            return f"INT64_C({node.value})" if abs(node.value) > 2**31 - 1 else str(node.value)
        if isinstance(node, FloatLiteral):
            s = repr(float(node.value))
            return s if any(c in s for c in ".eEn") else s + ".0"
        if isinstance(node, StringLiteral):
            return f"AIR_STR_LIT({c_string_literal(node.value)})"
        if isinstance(node, BoolLiteral):
            return "true" if node.value else "false"
        if isinstance(node, NullLiteral):
            return "NULL"
        if isinstance(node, InterpolatedString):
            return self._interp(node)
        if isinstance(node, Identifier):
            return f"self->f_{node.name}" if getattr(node, "kind", None) == "field" else self.v(node.name)
        if isinstance(node, BinaryOp):
            lt, rt = node.left.ty, node.right.ty
            if node.op in ("and", "or") or lt is None or rt is None or "Any" in (lt.name, rt.name):
                return self._binary(node.op, self.expr(node.left), lt,
                                    self.expr(node.right), rt, node)      # court-circuit : pas de hoisting
            pre, (l, r) = self._hoist([(node.left, self.expr(node.left), self.ctype(lt, node.left)),
                                       (node.right, self.expr(node.right), self.ctype(rt, node.right))])
            return self._wrap(pre, self._binary(node.op, l, lt, r, rt, node))
        if isinstance(node, UnaryOp):
            c = self.expr(node.operand)
            return f"(!{c})" if node.op == "not" else f"(-{c})"
        if isinstance(node, MemberAccess):
            return f"({self.expr(node.obj)})->f_{node.member}"
        if isinstance(node, NewInstance):
            pre, args = self._hoist([(v, self._coerce_code(self.expr(v), v.ty, ft), self.ctype(ft, v))
                                     for (_, v), ft in zip(node.resolved, node.field_types)])
            return self._wrap(pre, f"bp_{node.blueprint}_new({', '.join(args)})")
        if isinstance(node, Call):
            return self._call(node)
        if isinstance(node, MethodCall):
            return self._method_call(node)
        if isinstance(node, IfExpression):
            t = node.ty
            return (f"(({self.expr(node.condition)}) ? {self.coerce(node.then_value, t)}"
                    f" : {self.coerce(node.else_value, t)})")
        if isinstance(node, ListLiteral):
            return self._list_literal(node)
        if isinstance(node, MapLiteral):
            return self._map_literal(node)
        if isinstance(node, IndexAccess):
            ot = node.obj.ty
            pre, (o, i) = self._hoist([(node.obj, self.expr(node.obj), self.ctype(ot, node)),
                                       (node.index, self.expr(node.index),
                                        "int64_t" if ot.name == "List" else "AirStr")])
            if ot.name == "List":
                return self._wrap(pre, f"AIR_LIST_AT({self.ctype(ot.params[0], node)}, {o}, {i})")
            return self._wrap(pre, f"AIR_MAP_AT({self.ctype(ot.params[1], node)}, {o}, {i})")
        if isinstance(node, Lambda):
            self.unsupported(node, "les fonctions anonymes", "v0.4")
        if isinstance(node, ErrorPropagate):
            self.unsupported(node, "l'opérateur `?`", "v0.4")
        if isinstance(node, RangeLiteral):
            self.unsupported(node, "un intervalle en dehors d'un `for`", "v0.3")
        self.unsupported(node, f"l'expression `{type(node).__name__}`")

    def _list_literal(self, node: ListLiteral) -> str:
        et = node.ty.params[0]
        ct = self.ctype(et, node, "les éléments de la liste")
        if not node.elements:
            return f"air_list_new(sizeof({ct}))"
        pre, vals = self._hoist([(e, self.coerce(e, et), ct) for e in node.elements])
        items = ", ".join(vals)
        return self._wrap(pre, f"air_list_from(({ct}[]){{{items}}}, {len(node.elements)}, sizeof({ct}))")

    def _map_literal(self, node: MapLiteral) -> str:
        self.ctype(node.ty, node, "la map")
        vt = node.ty.params[1]
        ct = self.ctype(vt, node, "les valeurs de la map")
        if not node.pairs:
            return f"air_map_new(sizeof({ct}))"
        ops = []
        for k, v in node.pairs:                       # clé puis valeur, paire après paire
            ops.append((k, self.expr(k), "AirStr"))
            ops.append((v, self.coerce(v, vt), ct))
        pre, codes = self._hoist(ops)
        keys, vals = ", ".join(codes[0::2]), ", ".join(codes[1::2])
        return self._wrap(pre, f"air_map_from((AirStr[]){{{keys}}}, ({ct}[]){{{vals}}}, "
                               f"{len(node.pairs)}, sizeof({ct}))")

    def _interp(self, node: InterpolatedString) -> str:
        ops = []
        for p in node.parts:
            if isinstance(p, str):
                ops.append((None, f"AIR_STR_LIT({c_string_literal(p)})", "AirStr"))
            else:
                ops.append((p, self.to_str(p), "AirStr"))
        pre, pieces = self._hoist(ops)
        code = pieces[0]
        for nxt in pieces[1:]:
            code = f"air_concat({code}, {nxt})"
        return self._wrap(pre, code)

    # opérateurs ---------------------------------------------------------------

    def _equals(self, l: str, lt: AirType, r: str, rt: AirType) -> str:
        if lt.name == "String" and rt.name == "String":
            return f"air_str_eq({l}, {r})"
        return f"({l} == {r})"

    @staticmethod
    def _result_type(op: str, lt: AirType, rt: AirType) -> AirType:
        if op in ("+", "-", "*", "/", "%"):
            if lt.name == "String":
                return T_STRING
            return T_FLOAT if "Float" in (lt.name, rt.name) else T_INT
        return T_BOOL

    def _binary(self, op: str, l: str, lt: AirType, r: str, rt: AirType, node: Node) -> str:
        if lt is None or rt is None or "Any" in (lt.name, rt.name):
            self.unsupported(node, "une opération sur un type indéterminé", "v0.4 (Any)")
        if op == "and": return f"({l} && {r})"
        if op == "or":  return f"({l} || {r})"
        if op in ("==", "!="):
            if lt.name == "Int" and rt.name == "Float":
                l = f"((double)({l}))"
            elif lt.name == "Float" and rt.name == "Int":
                r = f"((double)({r}))"
            eq = self._equals(l, lt, r, rt)
            return eq if op == "==" else f"(!{eq})"
        if lt.name == "String" and rt.name == "String" and op == "+":
            return f"air_concat({l}, {r})"
        is_float = "Float" in (lt.name, rt.name)
        if is_float:
            if lt.name == "Int": l = f"((double)({l}))"
            if rt.name == "Int": r = f"((double)({r}))"
            if op == "%":
                return f"fmod({l}, {r})"
        elif op == "/":
            return f"air_idiv({l}, {r})"
        elif op == "%":
            return f"air_imod({l}, {r})"
        return f"({l} {op} {r})"

    # appels --------------------------------------------------------------------

    def _args(self, node) -> List[str]:
        return [self._coerce_code(self.expr(a), a.ty, pt)
                for a, pt in zip(node.resolved, node.param_types)]

    def _call(self, node: Call) -> str:
        if not isinstance(node.callee, Identifier):
            self.unsupported(node, "l'appel d'une expression", "v0.4")
        name = node.callee.name
        b = getattr(node, "builtin", None)
        if b == "print":
            if not node.args:
                return 'air_print(AIR_STR_LIT(""))'
            pre, parts = self._hoist([(a, self.to_str(a), "AirStr") for a in node.args])
            code = parts[0]
            for p in parts[1:]:
                code = f"air_concat(air_concat({code}, AIR_STR_LIT(\" \")), {p})"
            return self._wrap(pre, f"air_print({code})")
        if b == "str":
            return self.to_str(node.args[0])
        if b in ("int", "float", "len"):
            a, t = node.args[0], node.args[0].ty
            c = self.expr(a)
            if b == "len":
                if t.name == "String":
                    return f"air_str_length({c})"
                if t.name == "List": return f"air_list_length({c})"
                if t.name == "Map":  return f"air_map_length({c})"
                self.unsupported(node, f"`len` sur `{t}`")
            if b == "int":
                if t.name == "String": return f"air_str_to_int({c})"
                if t.name in ("Int", "Float", "Bool"): return f"((int64_t)({c}))"
            if b == "float":
                if t.name == "String": return f"air_str_to_float({c})"
                if t.name in ("Int", "Float", "Bool"): return f"((double)({c}))"
            self.unsupported(node, f"`{b}` sur `{t}`")
        if b in ("Ok", "Err"):
            self.unsupported(node, f"`{b}(...)` et le type `Result`", "v0.4")
        pre, args = self._hoist(self._arg_operands(node))
        owner = getattr(node, "self_method", None)
        if owner:
            ic = self.virtuals(self._cur_bp)[name][0]
            return self._wrap(pre, f"((bp_{ic}*)self)->vt->m_{name}({', '.join([f'(bp_{ic}*)self'] + args)})")
        return self._wrap(pre, f"air_fn_{name}({', '.join(args)})")

    _STR_METHODS = {
        "length": "air_str_length", "upper": "air_str_upper", "lower": "air_str_lower",
        "trim": "air_str_trim", "contains": "air_str_contains",
        "starts_with": "air_string_starts_with", "ends_with": "air_string_ends_with",
        "replace": "air_str_replace", "split": "air_str_split",
    }

    def _method_call(self, node: MethodCall) -> str:
        owner = getattr(node, "owner", None)
        ops = [(node.obj, self.expr(node.obj), self.ctype(node.obj.ty, node.obj))] + self._arg_operands(node)
        pre, codes = self._hoist(ops)
        obj, args = codes[0], codes[1:]
        if owner == "String":
            fn = self._STR_METHODS.get(node.method)
            if fn is None:
                self.unsupported(node, f"`String.{node.method}`")
            return self._wrap(pre, f"{fn}({', '.join([obj] + args)})")
        if owner == "List":
            return self._wrap(pre, self._list_method(node, obj, args))
        if owner == "Map":
            return self._wrap(pre, self._map_method(node, obj, args))
        if owner and owner in self._blueprints:
            st = node.obj.ty.name
            ic = self.virtuals(st)[node.method][0]      # classe qui introduit la méthode
            o = self.fresh("_air_o")
            return self._wrap(pre, f"({{ bp_{ic}* {o} = (bp_{ic}*)({obj}); "
                                   f"{o}->vt->m_{node.method}({', '.join([o] + args)}); }})")
        self.unsupported(node, f"la méthode `{node.method}` sur ce type", "v0.4")

    def _list_method(self, node: MethodCall, obj: str, a: List[str]) -> str:
        et = node.obj.ty.params[0]
        ct, k = self.ctype(et, node), self.kind(et)
        m = node.method
        table = {
            "append":    lambda: f"AIR_LIST_PUSH({ct}, {obj}, {a[0]})",
            "length":    lambda: f"air_list_length({obj})",
            "pop":       lambda: f"AIR_LIST_POP({ct}, {obj})",
            "first":     lambda: f"AIR_LIST_FIRST({ct}, {obj})",
            "last":      lambda: f"AIR_LIST_LAST({ct}, {obj})",
            "contains":  lambda: f"AIR_LIST_CONTAINS({ct}, {obj}, {a[0]}, {k})",
            "index_of":  lambda: f"AIR_LIST_INDEX_OF({ct}, {obj}, {a[0]}, {k})",
            "remove_at": lambda: f"AIR_LIST_REMOVE_AT({ct}, {obj}, {a[0]})",
            "clear":     lambda: f"air_list_clear({obj})",
            "reverse":   lambda: f"air_list_reversed({obj})",
            "sort":      lambda: f"air_list_sorted({obj}, {k})",
            "join":      lambda: f"air_list_join({obj}, {a[0]})",
        }
        if m not in table:
            self.unsupported(node, f"`List.{m}`")
        return table[m]()

    def _map_method(self, node: MethodCall, obj: str, a: List[str]) -> str:
        self.ctype(node.obj.ty, node)
        ct = self.ctype(node.obj.ty.params[1], node)
        m = node.method
        table = {
            "length": lambda: f"air_map_length({obj})",
            "has":    lambda: f"air_map_has({obj}, {a[0]})",
            "get_or": lambda: f"AIR_MAP_GET_OR({ct}, {obj}, {a[0]}, {a[1]})",
            "keys":   lambda: f"air_map_keys({obj})",
            "values": lambda: f"air_map_values({obj})",
            "delete": lambda: f"air_map_delete({obj}, {a[0]})",
            "clear":  lambda: f"air_map_clear({obj})",
        }
        if m not in table:
            self.unsupported(node, f"`Map.{m}`")
        return table[m]()
