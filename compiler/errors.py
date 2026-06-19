"""
AirLang — errors.py
Messages d'erreur rédigés pour des humains, avec contexte et suggestions.
"""

from __future__ import annotations
from typing import Optional, List


RESET  = "\033[0m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


class AirError(Exception):
    """Erreur de base AirLang avec position et suggestion."""

    def __init__(
        self,
        message:    str,
        line:       int = 0,
        column:     int = 0,
        filename:   str = "<source>",
        source:     Optional[str] = None,
        hint:       Optional[str] = None,
        label:      str = "Erreur",
    ):
        self.message  = message
        self.line     = line
        self.column   = column
        self.filename = filename
        self.source   = source      # Texte source complet (pour afficher la ligne)
        self.hint     = hint        # Suggestion de correction
        self.label    = label
        super().__init__(self.format())

    def format(self, color: bool = True) -> str:
        r = RESET if color else ""
        b = BOLD  if color else ""
        red  = RED    if color else ""
        yel  = YELLOW if color else ""
        cyan = CYAN   if color else ""
        dim  = DIM    if color else ""

        lines = []

        # En-tête
        loc = f"{self.filename}:{self.line}:{self.column}"
        lines.append(f"{b}{red}✘ {self.label}{r} [{dim}{loc}{r}]")
        lines.append(f"  {b}{self.message}{r}")

        # Extrait du code source
        if self.source and self.line > 0:
            src_lines = self.source.splitlines()
            if 0 < self.line <= len(src_lines):
                src_line = src_lines[self.line - 1]
                lines.append("")
                lines.append(f"  {dim}{self.line:>4} │{r}  {src_line}")
                if self.column > 0:
                    pointer = " " * (self.column - 1) + "^"
                    lines.append(f"       {cyan}{pointer}{r}")

        # Suggestion
        if self.hint:
            lines.append("")
            lines.append(f"  {yel}💡 Suggestion :{r} {self.hint}")

        return "\n".join(lines)

    def __str__(self):
        return self.format()


class LexerError(AirError):
    def __init__(self, message, line=0, column=0, **kw):
        super().__init__(message, line, column, label="Erreur Lexer", **kw)


class ParseError(AirError):
    def __init__(self, message, line=0, column=0, **kw):
        super().__init__(message, line, column, label="Erreur Syntaxe", **kw)


class TypeError(AirError):
    def __init__(self, message, line=0, column=0, **kw):
        super().__init__(message, line, column, label="Erreur de Type", **kw)


class NameError(AirError):
    def __init__(self, message, line=0, column=0, **kw):
        super().__init__(message, line, column, label="Erreur de Nom", **kw)


class CodegenError(AirError):
    def __init__(self, message, line=0, column=0, **kw):
        super().__init__(message, line, column, label="Erreur Génération", **kw)


# ── Messages d'erreur prédéfinis ──────────────────────────────────────────────

def err_unexpected_char(ch: str, line: int, col: int, **kw) -> LexerError:
    return LexerError(
        f"Caractère inattendu : {ch!r}",
        line, col,
        hint=f"Le caractère '{ch}' n'est pas valide en AirLang. Vérifiez votre éditeur.",
        **kw,
    )

def err_unterminated_string(line: int, col: int, **kw) -> LexerError:
    return LexerError(
        "Chaîne de caractères non fermée",
        line, col,
        hint='Ajoutez un guillemet fermant " à la fin de votre chaîne.',
        **kw,
    )

def err_expected_token(expected: str, got: str, line: int, col: int, **kw) -> ParseError:
    # Retirer 'hint' de kw si déjà présent pour éviter le doublon
    kw.pop("hint", None)
    return ParseError(
        f"Attendu {expected!r}, mais trouvé {got!r}",
        line, col,
        hint=f"Vérifiez la syntaxe autour de la ligne {line}.",
        **kw,
    )

def err_expected_end(construct: str, line: int, col: int, **kw) -> ParseError:
    return ParseError(
        f"Mot-clé 'end' manquant pour fermer le bloc '{construct}'",
        line, col,
        hint=f"Ajoutez 'end' après le corps du {construct}.",
        **kw,
    )

def err_undefined_var(name: str, line: int, col: int, suggestions: List[str] = None, **kw) -> NameError:
    hint = f"La variable '{name}' n'a pas été déclarée."
    if suggestions:
        hint += f" Vouliez-vous dire : {', '.join(suggestions)} ?"
    return NameError(
        f"Variable inconnue : '{name}'",
        line, col,
        hint=hint,
        **kw,
    )

def err_undefined_fun(name: str, line: int, col: int, **kw) -> NameError:
    return NameError(
        f"Fonction inconnue : '{name}'",
        line, col,
        hint=f"Vérifiez que '{name}' est bien définie avant son utilisation.",
        **kw,
    )

def err_undefined_blueprint(name: str, line: int, col: int, **kw) -> NameError:
    return NameError(
        f"Blueprint inconnu : '{name}'",
        line, col,
        hint=f"Déclarez 'blueprint {name}' avant de l'utiliser.",
        **kw,
    )

def err_type_mismatch(expected: str, got: str, line: int, col: int, **kw) -> TypeError:
    return TypeError(
        f"Type incompatible : attendu {expected!r}, reçu {got!r}",
        line, col,
        hint=f"Convertissez la valeur vers le type {expected!r} ou corrigez l'annotation.",
        **kw,
    )

def err_wrong_arg_count(fun: str, expected: int, got: int, line: int, col: int, **kw) -> TypeError:
    return TypeError(
        f"'{fun}' attend {expected} argument(s), mais {got} ont été fournis",
        line, col,
        hint=f"Vérifiez la signature de '{fun}'.",
        **kw,
    )

def err_null_access(name: str, line: int, col: int, **kw) -> TypeError:
    return TypeError(
        f"Accès potentiel à une valeur nulle : '{name}'",
        line, col,
        hint=f"Vérifiez que '{name}' n'est pas null avant d'y accéder (ex: if {name} != null).",
        **kw,
    )

def err_missing_return(fun: str, line: int, col: int, **kw) -> TypeError:
    return TypeError(
        f"La fonction '{fun}' devrait retourner une valeur mais aucun 'return' n'a été trouvé",
        line, col,
        hint=f"Ajoutez 'return <valeur>' à la fin de '{fun}'.",
        **kw,
    )

def err_trait_not_implemented(blueprint: str, trait: str, method: str, line: int, col: int, **kw) -> TypeError:
    return TypeError(
        f"'{blueprint}' implémente '{trait}' mais la méthode '{method}' est manquante",
        line, col,
        hint=f"Ajoutez 'fun {method}(...)' dans le blueprint '{blueprint}'.",
        **kw,
    )


# ── Collecteur d'erreurs (pour afficher toutes les erreurs d'un coup) ─────────

class ErrorCollector:
    """Accumule les erreurs et les affiche toutes à la fin."""

    def __init__(self):
        self.errors: List[AirError] = []

    def add(self, err: AirError):
        self.errors.append(err)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def report(self):
        if not self.errors:
            return
        print(f"\n{BOLD}{RED}✘ {len(self.errors)} erreur(s) trouvée(s) :{RESET}\n")
        for err in self.errors:
            print(err.format())
            print()

    def raise_if_any(self):
        if self.has_errors():
            self.report()
            raise SystemExit(1)
