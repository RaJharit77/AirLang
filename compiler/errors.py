"""
AirLang — errors.py
Hiérarchie d'erreurs unique et rendu lisible (ligne, colonne, extrait, aide).

Format produit :

    Erreur de nom : variable inconnue `username`
      --> main.air:8:7
       |
     8 | print(username)
       |       ^^^^^^^^
       |
       = aide : déclarez la variable avant de l'utiliser
"""

from __future__ import annotations

import difflib
from typing import Iterator, List, Optional

RESET  = "\033[0m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


class AirError(Exception):
    """Erreur de base AirLang avec position, extrait de code et aide."""

    default_label = "Erreur"

    def __init__(
        self,
        message:  str,
        line:     int = 0,
        column:   int = 0,
        filename: str = "<source>",
        source:   Optional[str] = None,
        hint:     Optional[str] = None,
        label:    Optional[str] = None,
        length:   int = 1,
    ):
        self.message  = message
        self.line     = line
        self.column   = column
        self.filename = filename
        self.source   = source
        self.hint     = hint
        self.label    = label or self.default_label
        self.length   = max(1, length)
        super().__init__(message)

    def format(self, color: bool = False) -> str:
        r    = RESET  if color else ""
        bold = BOLD   if color else ""
        red  = RED    if color else ""
        yel  = YELLOW if color else ""
        cyan = CYAN   if color else ""
        dim  = DIM    if color else ""

        out = [f"{bold}{red}{self.label}{r}{bold} : {self.message}{r}"]

        gutter = len(str(self.line)) if self.line > 0 else 1
        pad = " " * gutter
        if self.line > 0:
            out.append(f"{pad}{cyan}-->{r} {self.filename}:{self.line}:{self.column}")

        src_lines = self.source.splitlines() if self.source else []
        has_excerpt = 0 < self.line <= len(src_lines)

        if has_excerpt:
            text = src_lines[self.line - 1]
            out.append(f"{dim}{pad} |{r}")
            out.append(f"{dim}{self.line} |{r} {text}")
            if self.column > 0:
                lead = "".join("\t" if c == "\t" else " " for c in text[: self.column - 1])
                out.append(f"{dim}{pad} |{r} {lead}{cyan}{'^' * self.length}{r}")
            if self.hint:
                out.append(f"{dim}{pad} |{r}")
        if self.hint:
            out.append(f"{dim}{pad} ={r} {yel}aide :{r} {self.hint}")

        return "\n".join(out)

    def __str__(self) -> str:
        return self.format(color=False)


class LexerError(AirError):
    default_label = "Erreur lexicale"


class ParseError(AirError):
    default_label = "Erreur de syntaxe"


class AirTypeError(AirError):
    """Erreur de typage (ne masque pas le TypeError de Python)."""
    default_label = "Erreur de type"


class AirNameError(AirError):
    """Erreur de nom (ne masque pas le NameError de Python)."""
    default_label = "Erreur de nom"


class CodegenError(AirError):
    default_label = "Erreur de génération"


class AirIOError(AirError):
    default_label = "Erreur"


# ── Suggestions ───────────────────────────────────────────────────────────────

def did_you_mean(name: str, candidates) -> List[str]:
    """Noms proches de `name` (distance d'édition), pour « vouliez-vous dire »."""
    return difflib.get_close_matches(name, list(candidates), n=3, cutoff=0.6)


# ── Constructeurs de messages ─────────────────────────────────────────────────

def _positioned(fn):
    """Accepte `column=` comme alias de `col=` pour passer **node_position."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kw):
        if "column" in kw:
            kw["col"] = kw.pop("column")
        return fn(*args, **kw)
    return wrapper

@_positioned
def err_unexpected_char(ch: str, line: int = 0, col: int = 0, **kw) -> LexerError:
    return LexerError(
        f"caractère inattendu `{ch}`", line, col,
        hint=f"`{ch}` n'est pas valide en AirLang ; supprimez-le ou placez-le dans une chaîne",
        **kw,
    )

@_positioned
def err_unterminated_string(line: int = 0, col: int = 0, **kw) -> LexerError:
    return LexerError(
        "chaîne de caractères non fermée", line, col,
        hint='ajoutez un guillemet fermant " à la fin de la chaîne',
        **kw,
    )

@_positioned
def err_expected_token(expected: str, got: str, line: int = 0, col: int = 0, **kw) -> ParseError:
    hint = kw.pop("hint", None) or "vérifiez la syntaxe à cet endroit"
    return ParseError(
        f"`{expected}` attendu, mais `{got}` trouvé", line, col,
        hint=hint, **{"length": max(1, len(got)), **kw},
    )

@_positioned
def err_expected_end(construct: str, line: int = 0, col: int = 0, **kw) -> ParseError:
    return ParseError(
        f"mot-clé `end` manquant pour fermer le bloc `{construct}`", line, col,
        hint=f"ajoutez `end` après le corps du bloc `{construct}`", **kw,
    )

@_positioned
def err_undefined_var(name: str, line: int = 0, col: int = 0,
                      suggestions: List[str] = None, **kw) -> AirNameError:
    hint = "déclarez la variable avant de l'utiliser"
    if suggestions:
        hint = "vouliez-vous dire " + " ou ".join(f"`{s}`" for s in suggestions) + " ?"
    return AirNameError(f"variable inconnue `{name}`", line, col,
                        hint=hint, **{"length": len(name), **kw})

@_positioned
def err_undefined_fun(name: str, line: int = 0, col: int = 0,
                      suggestions: List[str] = None, **kw) -> AirNameError:
    hint = f"définissez `fun {name}(...)` avant de l'appeler"
    if suggestions:
        hint = "vouliez-vous dire " + " ou ".join(f"`{s}`" for s in suggestions) + " ?"
    return AirNameError(f"fonction inconnue `{name}`", line, col,
                        hint=hint, **{"length": len(name), **kw})

@_positioned
def err_undefined_blueprint(name: str, line: int = 0, col: int = 0, **kw) -> AirNameError:
    return AirNameError(f"blueprint inconnu `{name}`", line, col,
                        hint=f"déclarez `blueprint {name}` avant de l'utiliser",
                        **{"length": len(name), **kw})

@_positioned
def err_type_mismatch(expected: str, got: str, line: int = 0, col: int = 0, **kw) -> AirTypeError:
    hint = kw.pop("hint", None) or f"fournissez une valeur de type `{expected}` ou corrigez l'annotation"
    return AirTypeError(f"type incompatible : `{expected}` attendu, `{got}` reçu",
                        line, col, hint=hint, **kw)

@_positioned
def err_wrong_arg_count(fun: str, expected: int, got: int, line: int = 0, col: int = 0, **kw) -> AirTypeError:
    return AirTypeError(
        f"`{fun}` attend {expected} argument(s), mais {got} fourni(s)", line, col,
        hint=f"vérifiez la signature de `{fun}`", **{"length": len(fun), **kw})

@_positioned
def err_null_access(name: str, line: int = 0, col: int = 0, **kw) -> AirTypeError:
    return AirTypeError(
        f"accès potentiel à une valeur nulle : `{name}`", line, col,
        hint=f"vérifiez que `{name}` n'est pas null (ex : if {name} != null)",
        **{"length": len(name), **kw})

@_positioned
def err_missing_return(fun: str, line: int = 0, col: int = 0, **kw) -> AirTypeError:
    return AirTypeError(
        f"la fonction `{fun}` doit retourner une valeur, mais un chemin n'a pas de `return`",
        line, col, hint=f"ajoutez `return <valeur>` à la fin de `{fun}`", **kw)

@_positioned
def err_trait_not_implemented(blueprint: str, trait: str, method: str,
                              line: int = 0, col: int = 0, **kw) -> AirTypeError:
    return AirTypeError(
        f"`{blueprint}` implémente `{trait}` mais la méthode `{method}` est manquante",
        line, col, hint=f"ajoutez `fun {method}(...)` dans `blueprint {blueprint}`", **kw)


# ── Collecteur d'erreurs ──────────────────────────────────────────────────────

class ErrorCollector:
    """Accumule les erreurs pour les afficher toutes d'un coup."""

    def __init__(self):
        self.errors: List[AirError] = []

    def add(self, err: AirError):
        self.errors.append(err)

    def has_errors(self) -> bool:
        return bool(self.errors)

    def __iter__(self) -> Iterator[AirError]:
        return iter(self.errors)

    def __len__(self) -> int:
        return len(self.errors)

    def __bool__(self) -> bool:
        return bool(self.errors)

    def report(self, file=None, color: bool = False) -> None:
        import sys
        file = file or sys.stderr
        for err in self.errors:
            print(err.format(color=color), file=file)
            print(file=file)
        n = len(self.errors)
        if n:
            print(f"{n} erreur{'s' if n > 1 else ''} — compilation interrompue.", file=file)
