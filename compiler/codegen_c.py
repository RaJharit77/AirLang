"""
AirLang — codegen_c.py
Génère du code C depuis l'AST AirLang.
Le C produit est ensuite compilé par GCC/Clang via subprocess.
"""

from __future__ import annotations
from typing import List, Optional, Set
from ast_nodes import *


# ── Générateur principal ───────────────────────────────────────────────────────

class CCodegen:

    def __init__(self):
        self.output:       List[str]        = []
        self.indent:       int              = 0
        self.blueprints:   Set[str]         = set()
        self._tmp_counter: int              = 0
        # Stack de scopes : chaque scope est un dict nom → (c_type, bp_name|None)
        self._scopes:      List[dict]       = [{}]
        # Table globale varname → blueprint_name pour le method dispatch
        self._var_blueprint: dict           = {}

    # ── Scope management ───────────────────────────────────────────────────────

    def _scope_push(self):
        self._scopes.append({})

    def _scope_pop(self):
        self._scopes.pop()

    def _is_declared(self, name: str) -> bool:
        for s in reversed(self._scopes):
            if name in s:
                return True
        return False

    def _declare(self, name: str, ctype: str = "AirVal", bp: str = None):
        self._scopes[-1][name] = (ctype, bp)
        if bp:
            self._var_blueprint[name] = bp

    def _get_ctype(self, name: str) -> str:
        for s in reversed(self._scopes):
            if name in s:
                return s[name][0]
        return "AirVal"

    # ── Utilitaires ────────────────────────────────────────────────────────────

    def fresh_tmp(self) -> str:
        self._tmp_counter += 1
        return f"_air_tmp_{self._tmp_counter}"

    def emit(self, line: str = ""):
        pad = "    " * self.indent
        self.output.append(pad + line)

    def emit_raw(self, text: str):
        self.output.append(text)

    def indented(self):
        class _Ctx:
            def __enter__(ctx):
                self.indent += 1
                self._scope_push()
            def __exit__(ctx, *a):
                self.indent -= 1
                self._scope_pop()
        return _Ctx()

    def generate(self, program: Program) -> str:
        self.output          = []
        self._scopes         = [{}]
        self._var_blueprint  = {}
        self._emit_header()
        # Passe 1 : forward declarations pour blueprints
        for stmt in program.statements:
            if isinstance(stmt, BlueprintDecl):
                self._forward_blueprint(stmt)
        # Passe 2 : forward declarations pour fonctions
        for stmt in program.statements:
            if isinstance(stmt, (FunDecl, ExportDecl)):
                node = stmt.declaration if isinstance(stmt, ExportDecl) else stmt
                if isinstance(node, FunDecl) and node.name != "main":
                    ret    = self._air_type_to_c(node.return_type)
                    params = self._gen_params(node.params)
                    self.emit(f"{ret} {node.name}({params});")
        # Passe 3 : générer tout le code
        for stmt in program.statements:
            self.gen_stmt(stmt)
        return "\n".join(self.output)

    # ── En-tête ────────────────────────────────────────────────────────────────

    def _emit_header(self):
        self.emit_raw("""\
/* ============================================================
 * Généré automatiquement par AirLang Compiler v0.1
 * Ne pas modifier manuellement.
 * ============================================================ */

#include "air_runtime.h"
""")

    # ── Forward declarations ───────────────────────────────────────────────────

    def _forward_blueprint(self, node: BlueprintDecl):
        self.emit(f"typedef struct {node.name} {node.name};")

    # ── Statements ─────────────────────────────────────────────────────────────

    def gen_stmt(self, node: Node):
        if isinstance(node, VarDecl):
            self._gen_var_decl(node)
        elif isinstance(node, Assign):
            self._gen_assign(node)
        elif isinstance(node, FunDecl):
            self._gen_fun_decl(node)
        elif isinstance(node, BlueprintDecl):
            self._gen_blueprint(node)
        elif isinstance(node, IfStmt):
            self._gen_if(node)
        elif isinstance(node, UnlessStmt):
            self._gen_unless(node)
        elif isinstance(node, WhileStmt):
            self._gen_while(node)
        elif isinstance(node, ForStmt):
            self._gen_for(node)
        elif isinstance(node, MatchStmt):
            self._gen_match(node)
        elif isinstance(node, TryCatch):
            self._gen_try_catch(node)
        elif isinstance(node, Return):
            self._gen_return(node)
        elif isinstance(node, ExprStmt):
            # Ignorer l'appel top-level "main()" — main() est le point d'entrée C
            if isinstance(node.expr, Call):
                callee = node.expr.callee
                if isinstance(callee, Identifier) and callee.name == "main":
                    return
            expr = self.gen_expr(node.expr)
            self.emit(f"{expr};")
        elif isinstance(node, ExportDecl):
            self.gen_stmt(node.declaration)
        elif isinstance(node, ImportDecl):
            pass   # Modules inclus via air_runtime.h
        elif isinstance(node, TraitDecl):
            pass   # Les traits ne produisent pas de code C

    def _gen_var_decl(self, node: VarDecl):
        """VarDecl explicite (const MAX = 1, age: Int = 30)."""
        ctype = self._air_type_to_c(node.type_ann)
        val   = self.gen_expr(node.value) if node.value else self._default_value(ctype)
        const = "const " if node.is_const else ""
        self._declare(node.name)
        self.emit(f"{const}{ctype} {node.name} = {val};")

    def _gen_assign(self, node: Assign):
        """Assignation : première occurrence → déclaration C, sinon simple assignation."""
        value = self.gen_expr(node.value)
        if isinstance(node.target, Identifier):
            name = node.target.name
            if not self._is_declared(name) and node.op == "=":
                # Première assignation → on déduit le type C et on déclare
                ctype = self._infer_c_type(node.value)
                self._declare(name)
                self.emit(f"{ctype} {name} = {value};")
            else:
                self.emit(f"{name} {node.op} {value};")
        else:
            target = self.gen_expr(node.target)
            self.emit(f"{target} {node.op} {value};")

    def _infer_c_type(self, node: Node) -> str:
        """Déduit le type C d'une expression pour la déclaration."""
        if isinstance(node, IntLiteral):    return "int64_t"
        if isinstance(node, FloatLiteral):  return "double"
        if isinstance(node, BoolLiteral):   return "int"
        if isinstance(node, StringLiteral): return "AirStr"
        if isinstance(node, NullLiteral):   return "AirVal"
        if isinstance(node, ListLiteral):   return "AirList*"
        if isinstance(node, MapLiteral):    return "AirMap*"
        if isinstance(node, NewInstance):   return node.blueprint + "*"
        if isinstance(node, BinaryOp):
            if node.op in ("+", "-", "*", "/", "%"):
                lt = self._infer_c_type(node.left)
                rt = self._infer_c_type(node.right)
                if lt == "double" or rt == "double": return "double"
                if lt == "AirStr" or rt == "AirStr": return "AirStr"
                if lt == "int64_t" and rt == "int64_t": return "int64_t"
            if node.op in ("==", "!=", "<", ">", "<=", ">=", "and", "or"): return "int"
        if isinstance(node, Call):
            # Fonctions built-in connues
            if isinstance(node.callee, Identifier):
                known = {"add": "int64_t", "double": "int64_t"}
                return known.get(node.callee.name, "AirVal")
        return "AirVal"   # Fallback générique

    def _gen_fun_decl(self, node: FunDecl):
        ret    = "int" if node.name == "main" else self._air_type_to_c(node.return_type)
        params = "void" if node.name == "main" else self._gen_params(node.params)
        self.emit("")
        self.emit(f"{ret} {node.name}({params}) {{")
        with self.indented():
            # Enregistrer les paramètres comme déjà déclarés dans ce scope
            for p in node.params:
                self._declare(p.name)
            for stmt in node.body:
                self.gen_stmt(stmt)
            if node.name == "main":
                self.emit("return 0;")
        self.emit("}")

    def _gen_blueprint(self, node: BlueprintDecl):
        self.blueprints.add(node.name)
        self.emit("")
        self.emit(f"/* Blueprint: {node.name} */")
        self.emit(f"struct {node.name} {{")
        with self.indented():
            for f in node.fields:
                ctype = self._air_type_to_c(f.type_ann)
                self.emit(f"{ctype} {f.name};")
        self.emit("};")

        # Constructeur : Blueprint_new(field1, field2, ...)
        if node.fields:
            fields_params = ", ".join(
                f"{self._air_type_to_c(f.type_ann)} {f.name}" for f in node.fields
            )
        else:
            fields_params = "void"
        self.emit("")
        self.emit(f"{node.name} {node.name}_new({fields_params}) {{")
        with self.indented():
            self.emit(f"{node.name} _inst;")
            for f in node.fields:
                self.emit(f"_inst.{f.name} = {f.name};")
            self.emit("return _inst;")
        self.emit("}")

        # Méthodes : Blueprint_method(Blueprint* self, ...)
        for method in node.methods:
            params_str = ", ".join(
                [f"{node.name}* self"] +
                [f"{self._air_type_to_c(p.type_ann)} {p.name}" for p in method.params]
            )
            ret = self._air_type_to_c(method.return_type)
            self.emit("")
            self.emit(f"{ret} {node.name}_{method.name}({params_str}) {{")
            with self.indented():
                # Les champs sont accessibles via self->field
                for f in node.fields:
                    ctype = self._air_type_to_c(f.type_ann)
                    self._declare(f.name)
                    self.emit(f"#define {f.name} (self->{f.name})")
                for stmt in method.body:
                    self.gen_stmt(stmt)
                for f in node.fields:
                    self.emit(f"#undef {f.name}")
            self.emit("}")

    def _gen_if(self, node: IfStmt):
        cond = self.gen_expr(node.condition)
        self.emit(f"if ({cond}) {{")
        with self.indented():
            for s in node.then_body:
                self.gen_stmt(s)
        for elif_cond, elif_body in node.elif_clauses:
            ec = self.gen_expr(elif_cond)
            self.emit(f"}} else if ({ec}) {{")
            with self.indented():
                for s in elif_body:
                    self.gen_stmt(s)
        if node.else_body:
            self.emit("} else {")
            with self.indented():
                for s in node.else_body:
                    self.gen_stmt(s)
        self.emit("}")

    def _gen_unless(self, node: UnlessStmt):
        cond = self.gen_expr(node.condition)
        self.emit(f"if (!({cond})) {{")
        with self.indented():
            for s in node.body:
                self.gen_stmt(s)
        self.emit("}")

    def _gen_while(self, node: WhileStmt):
        cond = self.gen_expr(node.condition)
        self.emit(f"while ({cond}) {{")
        with self.indented():
            for s in node.body:
                self.gen_stmt(s)
        self.emit("}")

    def _gen_for(self, node: ForStmt):
        if isinstance(node.iterable, RangeLiteral):
            start = self.gen_expr(node.iterable.start)
            end   = self.gen_expr(node.iterable.end)
            self.emit(f"for (int64_t {node.var} = {start}; {node.var} < {end}; {node.var}++) {{")
            with self.indented():
                self._declare(node.var)
                for s in node.body:
                    self.gen_stmt(s)
            self.emit("}")
        else:
            # for var in list
            iterable = self.gen_expr(node.iterable)
            tmp_i    = self.fresh_tmp()
            tmp_list = self.fresh_tmp()
            self.emit(f"AirList* {tmp_list} = {iterable};")
            self.emit(f"for (int64_t {tmp_i} = 0; {tmp_i} < {tmp_list}->len; {tmp_i}++) {{")
            with self.indented():
                self._declare(node.var)
                self.emit(f"AirVal {node.var} = {tmp_list}->items[{tmp_i}];")
                if node.index_var:
                    self._declare(node.index_var)
                    self.emit(f"int64_t {node.index_var} = {tmp_i};")
                for s in node.body:
                    self.gen_stmt(s)
            self.emit("}")

    def _gen_match(self, node: MatchStmt):
        subject = self.gen_expr(node.subject)
        tmp     = self.fresh_tmp()
        # Déterminer le type du sujet pour les comparaisons
        is_str  = isinstance(node.subject, (StringLiteral, MemberAccess, Identifier))
        self.emit(f"AirVal {tmp} = (AirVal)({subject});")
        first = True
        for pattern, action in node.cases:
            if isinstance(pattern, Identifier) and pattern.name == "_":
                self.emit("} else {" if not first else "{")
            else:
                pat = self.gen_expr(pattern)
                if isinstance(pattern, StringLiteral):
                    cmp = f"air_str_eq(*(AirStr*){tmp}, {pat})"
                else:
                    cmp = f"air_eq({tmp}, (AirVal)({pat}))"
                kw = "if" if first else "} else if"
                self.emit(f"{kw} ({cmp}) {{")
            with self.indented():
                self.gen_stmt(action)
            first = False
        self.emit("}")

    def _gen_try_catch(self, node: TryCatch):
        self.emit("{  /* try */")
        with self.indented():
            for s in node.try_body:
                self.gen_stmt(s)
        err_type = node.error_type.name if node.error_type else "AirError"
        self.emit(f"}}  /* catch {node.error_var}: {err_type} — TODO setjmp */")

    def _gen_return(self, node: Return):
        if node.value:
            val = self.gen_expr(node.value)
            self.emit(f"return {val};")
        else:
            self.emit("return;")

    # ── Expressions ────────────────────────────────────────────────────────────

    def gen_expr(self, node: Node) -> str:
        if node is None:
            return "NULL"

        if isinstance(node, IntLiteral):
            return str(node.value)

        if isinstance(node, FloatLiteral):
            s = str(node.value)
            return s if "." in s else s + ".0"

        if isinstance(node, StringLiteral):
            escaped = (node.value
                       .replace("\\", "\\\\")
                       .replace('"', '\\"')
                       .replace("\n", "\\n")
                       .replace("\t", "\\t"))
            return f'air_str("{escaped}")'

        if isinstance(node, BoolLiteral):
            return "1" if node.value else "0"

        if isinstance(node, NullLiteral):
            return "NULL"

        if isinstance(node, Identifier):
            return node.name

        if isinstance(node, BinaryOp):
            l  = self.gen_expr(node.left)
            r  = self.gen_expr(node.right)
            op_map = {"and": "&&", "or": "||"}
            op = op_map.get(node.op, node.op)
            if node.op == "+":
                # Toujours utiliser air_concat si l'un des termes peut être AirStr
                l_str = isinstance(node.left,  (StringLiteral, MemberAccess)) or \
                        (isinstance(node.left,  Identifier) and
                         self._infer_c_type(node.left) == "AirStr")
                r_str = isinstance(node.right, (StringLiteral, MemberAccess)) or \
                        (isinstance(node.right, Identifier) and
                         self._infer_c_type(node.right) == "AirStr")
                if l_str or r_str or isinstance(node.left, StringLiteral) or isinstance(node.right, StringLiteral):
                    return f"air_concat({l}, {r})"
                # Numériques : arithmétique C classique
                return f"({l} {op} {r})"
            if node.op == "==":
                if isinstance(node.left, StringLiteral) or isinstance(node.right, StringLiteral):
                    return f"air_str_eq({l}, {r})"
            return f"({l} {op} {r})"

        if isinstance(node, UnaryOp):
            operand = self.gen_expr(node.operand)
            if node.op == "not":
                return f"(!{operand})"
            return f"({node.op}{operand})"

        if isinstance(node, MemberAccess):
            obj = self.gen_expr(node.obj)
            # Si obj est un blueprint (pointeur) → ->
            if isinstance(node.obj, Identifier):
                name = node.obj.name
                # On ne peut pas savoir à coup sûr sans type-checker, on utilise . (struct par valeur)
                return f"{obj}.{node.member}"
            return f"{obj}.{node.member}"

        if isinstance(node, IndexAccess):
            obj   = self.gen_expr(node.obj)
            index = self.gen_expr(node.index)
            return f"air_list_get({obj}, {index})"

        if isinstance(node, NewInstance):
            args = ", ".join(self.gen_expr(v) for _, v in node.kwargs)
            if not args:
                return f"{node.blueprint}_new()"
            return f"{node.blueprint}_new({args})"

        if isinstance(node, Call):
            # Noms AirLang qui peuvent entrer en conflit avec des mots-clés C
            C_RESERVED = {"double", "float", "int", "long", "short", "char",
                          "void", "struct", "union", "enum", "return", "if",
                          "else", "for", "while", "do", "switch", "case",
                          "break", "continue", "goto", "typedef", "extern",
                          "static", "register", "auto", "sizeof", "const",
                          "volatile", "unsigned", "signed", "inline"}
            raw_callee  = self.gen_expr(node.callee)
            safe_callee = f"_air_{raw_callee}" if raw_callee in C_RESERVED else raw_callee
            args   = [self.gen_expr(a) for a in node.args]
            args  += [self.gen_expr(v) for _, v in node.kwargs]

            # Fonctions built-in
            if raw_callee == "print":
                if not args:
                    return 'air_print(air_str(""))'
                arg = args[0]
                src_node = node.args[0] if node.args else (node.kwargs[0][1] if node.kwargs else None)
                if src_node is not None:
                    if isinstance(src_node, IntLiteral):
                        return f"air_print_int({arg})"
                    if isinstance(src_node, FloatLiteral):
                        return f"air_print_float({arg})"
                    if isinstance(src_node, BoolLiteral):
                        return f"air_print_bool({arg})"
                    # Identifiants ou expressions → utiliser air_int_to_str (approximation)
                    return f"air_print(air_int_to_str({arg}))"
                return f"air_print({arg})"

            return f"{safe_callee}({', '.join(args)})"

        if isinstance(node, MethodCall):
            obj  = self.gen_expr(node.obj)
            args = [self.gen_expr(a) for a in node.args]
            args += [self.gen_expr(v) for _, v in node.kwargs]
            a0   = args[0] if args else "NULL"

            # Méthodes built-in de liste
            list_methods = {
                "append": lambda: f"air_list_append({obj}, (AirVal)({a0}))",
                "length": lambda: f"air_list_length({obj})",
                "map":    lambda: f"air_list_map({obj}, {a0})",
                "filter": lambda: f"air_list_filter({obj}, {a0})",
                "join":   lambda: f"air_list_join({obj}, {a0})",
                "pop":    lambda: f"air_list_get({obj}, (int64_t)({obj})->len - 1)",
            }
            # Méthodes built-in de string
            str_methods = {
                "split":      lambda: f"air_str_split({obj}, {a0})",
                "trim":       lambda: f"air_str_trim({obj})",
                "upper":      lambda: f"air_str_upper({obj})",
                "lower":      lambda: f"air_str_lower({obj})",
                "replace":    lambda: f"air_str_replace({obj}, {args[0] if args else '""'}, {args[1] if len(args)>1 else '""'})",
                "contains":   lambda: f"air_str_contains({obj}, {a0})",
                "length":     lambda: f"air_str_length({obj})",
                "starts_with":lambda: f"air_string_starts_with({obj}, {a0})",
                "ends_with":  lambda: f"air_string_ends_with({obj}, {a0})",
            }
            if node.method in list_methods:
                return list_methods[node.method]()
            if node.method in str_methods:
                return str_methods[node.method]()

            # Blueprint method → Blueprint_method(&obj, args...)
            args_str = ", ".join([f"&{obj}"] + args)
            # Chercher le nom du blueprint dans les blueprints déclarés
            bp_prefix = self._find_blueprint_for(node.obj)
            if bp_prefix:
                return f"{bp_prefix}_{node.method}({args_str})"
            return f"{node.method}({', '.join([obj] + args)})"

        if isinstance(node, Lambda):
            # Lambdas : génère un commentaire placeholder (Semaine 3+)
            body = self.gen_expr(node.body)
            return f"/* lambda => {body} */"

        if isinstance(node, IfExpression):
            cond = self.gen_expr(node.condition)
            t    = self.gen_expr(node.then_value)
            e    = self.gen_expr(node.else_value)
            return f"(({cond}) ? {t} : {e})"

        if isinstance(node, ErrorPropagate):
            expr = self.gen_expr(node.expr)
            return f"air_unwrap({expr})"

        if isinstance(node, ListLiteral):
            if not node.elements:
                return "air_list_empty()"
            elems = ", ".join(f"(AirVal)({self.gen_expr(e)})" for e in node.elements)
            return f"air_list_of({len(node.elements)}, {elems})"

        if isinstance(node, RangeLiteral):
            s = self.gen_expr(node.start)
            e = self.gen_expr(node.end)
            return f"/* range {s}..{e} */"

        if isinstance(node, MapLiteral):
            tmp = self.fresh_tmp()
            # Pour une Map littérale on génère plusieurs statements → ici on retourne juste le nom
            # (Les maps littérales complexes seraient traitées comme VarDecl dans _gen_assign)
            return "air_map_empty()"

        return "/* unknown_expr */"

    def _find_blueprint_for(self, obj_node: Node) -> Optional[str]:
        """Tente de trouver le nom du blueprint pour un objet (heuristique)."""
        # Si c'est un identifiant, on cherche dans les blueprints connus
        if isinstance(obj_node, Identifier):
            name = obj_node.name
            # Cherche dans les blueprints déclarés un match par convention de nommage
            for bp in self.blueprints:
                if bp.lower() in name.lower() or name[0].isupper():
                    return bp
        return None

    # ── Helpers de types ───────────────────────────────────────────────────────

    def _air_type_to_c(self, ann) -> str:
        if ann is None:
            return "AirVal"
        name = ann.name if hasattr(ann, "name") else str(ann)
        mapping = {
            "Int":    "int64_t",
            "Float":  "double",
            "Bool":   "int",
            "String": "AirStr",
            "Char":   "char",
            "Void":   "void",
            "Any":    "AirVal",
            "List":   "AirList*",
            "Map":    "AirMap*",
            "Result": "AirResult",
            "Fun":    "AirVal",
        }
        return mapping.get(name, name)

    def _gen_params(self, params: list) -> str:
        if not params:
            return "void"
        return ", ".join(
            f"{self._air_type_to_c(p.type_ann)} {p.name}"
            for p in params
        )

    def _default_value(self, ctype: str) -> str:
        defaults = {
            "int64_t":  "0",
            "double":   "0.0",
            "int":      "0",
            "AirStr":   'air_str("")',
            "AirVal":   "NULL",
            "AirList*": "air_list_empty()",
            "AirMap*":  "air_map_empty()",
            "AirResult":"(AirResult){0}",
        }
        return defaults.get(ctype, "NULL")


# ── Compilation via GCC ────────────────────────────────────────────────────────

import subprocess
import os
import tempfile


def compile_to_binary(c_source: str, output_path: str,
                      runtime_dir: str = "runtime") -> bool:
    """Écrit le C dans un fichier temp et invoque GCC."""
    with tempfile.NamedTemporaryFile(suffix=".c", mode="w",
                                    delete=False, encoding="utf-8") as f:
        f.write(c_source)
        c_file = f.name

    runtime_c = os.path.join(runtime_dir, "air_runtime.c")
    stdlib_c  = os.path.join(runtime_dir, "air_stdlib.c")
    sources   = [c_file, runtime_c]
    if os.path.exists(stdlib_c):
        sources.append(stdlib_c)

    cmd = ["gcc", "-O0", "-o", output_path, f"-I{runtime_dir}"] + sources + ["-lm"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"✘ Erreur GCC :\n{result.stderr}")
            return False
        return True
    except FileNotFoundError:
        print("✘ GCC introuvable. Installez GCC : sudo apt install gcc")
        return False
    finally:
        os.unlink(c_file)


# ── Test rapide ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from parser import parse_source

    sample = """
fun add(a: Int, b: Int) -> Int
    return a + b
end

fun main()
    x = 10
    y = 32
    result = add(x, y)
    print(result)
end

main()
"""
    ast  = parse_source(sample)
    gen  = CCodegen()
    code = gen.generate(ast)
    print(code)
