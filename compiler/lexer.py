"""
AirLang Lexer — Semaine 1
Tokenise le code source .air en liste de tokens.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional

from .errors import LexerError, err_unexpected_char, err_unterminated_string


class TokenType(Enum):
    # Littéraux
    INT        = auto()
    FLOAT      = auto()
    STRING     = auto()
    BOOL       = auto()
    NULL       = auto()

    # Identifiants & mots-clés
    IDENT      = auto()
    FUN        = auto()
    BLUEPRINT  = auto()
    TRAIT      = auto()
    EXTENDS    = auto()
    IMPLEMENTS = auto()
    IMPORT     = auto()
    EXPORT     = auto()
    RETURN     = auto()
    BREAK      = auto()
    CONTINUE   = auto()
    IF         = auto()
    ELSE       = auto()
    UNLESS     = auto()
    FOR        = auto()
    WHILE      = auto()
    IN         = auto()
    MATCH      = auto()
    END        = auto()
    CONST      = auto()
    NEW        = auto()
    THEN       = auto()
    AT         = auto()
    TRY        = auto()
    CATCH      = auto()
    AND        = auto()
    OR         = auto()
    NOT        = auto()
    AS         = auto()

    # Opérateurs
    PLUS       = auto()   # +
    MINUS      = auto()   # -
    STAR       = auto()   # *
    SLASH      = auto()   # /
    PERCENT    = auto()   # %
    EQ         = auto()   # ==
    NEQ        = auto()   # !=
    LT         = auto()   # <
    GT         = auto()   # >
    LTE        = auto()   # <=
    GTE        = auto()   # >=
    ASSIGN     = auto()   # =
    PLUS_EQ    = auto()   # +=
    MINUS_EQ   = auto()   # -=
    STAR_EQ    = auto()   # *=
    SLASH_EQ   = auto()   # /=
    ARROW      = auto()   # ->
    FAT_ARROW  = auto()   # =>
    QUESTION   = auto()   # ?
    DOT        = auto()   # .
    DOTDOT     = auto()   # ..
    COLON      = auto()   # :
    COMMA      = auto()   # ,
    HASH       = auto()   # # (commentaire)

    # Groupement
    LPAREN     = auto()   # (
    RPAREN     = auto()   # )
    LBRACKET   = auto()   # [
    RBRACKET   = auto()   # ]
    LBRACE     = auto()   # {
    RBRACE     = auto()   # }

    # Spéciaux
    NEWLINE    = auto()
    EOF        = auto()


KEYWORDS = {
    "fun":        TokenType.FUN,
    "blueprint":  TokenType.BLUEPRINT,
    "trait":      TokenType.TRAIT,
    "extends":    TokenType.EXTENDS,
    "implements": TokenType.IMPLEMENTS,
    "import":     TokenType.IMPORT,
    "export":     TokenType.EXPORT,
    "return":     TokenType.RETURN,
    "break":      TokenType.BREAK,
    "continue":   TokenType.CONTINUE,
    "if":         TokenType.IF,
    "else":       TokenType.ELSE,
    "unless":     TokenType.UNLESS,
    "for":        TokenType.FOR,
    "while":      TokenType.WHILE,
    "in":         TokenType.IN,
    "match":      TokenType.MATCH,
    "end":        TokenType.END,
    "const":      TokenType.CONST,
    "new":        TokenType.NEW,
    "then":       TokenType.THEN,
    "try":        TokenType.TRY,
    "catch":      TokenType.CATCH,
    "and":        TokenType.AND,
    "or":         TokenType.OR,
    "not":        TokenType.NOT,
    "as":         TokenType.AS,
    "true":       TokenType.BOOL,
    "false":      TokenType.BOOL,
    "null":       TokenType.NULL,
}


@dataclass
class Token:
    type:   TokenType
    value:  str
    line:   int
    column: int
    # Pour les chaînes interpolées : liste de str (texte) et de tuples
    # (source_expr, ligne, colonne) pour les expressions `{...}`. None sinon.
    parts:  Optional[list] = None

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.column})"


class Lexer:
    def __init__(self, source: str, filename: str = "<source>"):
        self.source   = source
        self.filename = filename
        self.pos      = 0
        self.line     = 1
        self.column   = 1
        self.tokens: List[Token] = []

    def error(self, msg: str, line: int = None, column: int = None, **kw) -> LexerError:
        return LexerError(msg, line or self.line, column or self.column,
                          filename=self.filename, source=self.source, **kw)

    def peek(self, offset: int = 0) -> Optional[str]:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else None

    def advance(self) -> str:
        ch = self.source[self.pos]
        self.pos    += 1
        self.column += 1
        if ch == "\n":
            self.line  += 1
            self.column = 1
        return ch

    def match(self, expected: str) -> bool:
        if self.peek() == expected:
            self.advance()
            return True
        return False

    def skip_whitespace(self):
        while self.peek() in (" ", "\t", "\r"):
            self.advance()

    def read_string(self) -> Token:
        """Lit une chaîne. `{expr}` déclenche l'interpolation ; `\\{` donne un `{` littéral."""
        start_line, start_col = self.line, self.column
        self.advance()  # consume opening "
        parts: list = []
        buf: list = []
        escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\",
                   "{": "{", "}": "}", "0": "\0"}
        while self.peek() is not None and self.peek() != '"':
            if self.peek() == "\n":
                break
            ch = self.advance()
            if ch == "\\":
                if self.peek() is None:
                    break
                esc = self.advance()
                buf.append(escapes.get(esc, "\\" + esc))
            elif ch == "{":
                expr_line, expr_col = self.line, self.column
                depth, expr = 1, []
                while self.peek() is not None and self.peek() not in ('"', "\n"):
                    c = self.advance()
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    expr.append(c)
                if depth != 0:
                    raise self.error("interpolation `{...}` non fermée", start_line, start_col,
                                     hint="fermez l'expression avec `}` (ou écrivez `\\{` pour une accolade littérale)")
                src = "".join(expr)
                if not src.strip():
                    raise self.error("interpolation vide `{}`", expr_line, expr_col - 1,
                                     hint="placez une expression entre les accolades, ex : \"{nom}\"")
                if buf:
                    parts.append("".join(buf))
                    buf = []
                parts.append((src, expr_line, expr_col))
            else:
                buf.append(ch)
        if self.peek() != '"':
            raise err_unterminated_string(start_line, start_col,
                                          filename=self.filename, source=self.source)
        self.advance()  # consume closing "
        if not parts:
            return Token(TokenType.STRING, "".join(buf), start_line, start_col)
        if buf:
            parts.append("".join(buf))
        return Token(TokenType.STRING, "", start_line, start_col, parts=parts)

    def read_number(self) -> Token:
        start_line, start_col = self.line, self.column
        buf = []
        is_float = False
        while self.peek() and self.peek().isdigit():
            buf.append(self.advance())
        if self.peek() == "." and (self.peek(1) or "").isdigit():
            is_float = True
            buf.append(self.advance())  # .
            while self.peek() and self.peek().isdigit():
                buf.append(self.advance())
        value = "".join(buf)
        ttype = TokenType.FLOAT if is_float else TokenType.INT
        return Token(ttype, value, start_line, start_col)

    def read_ident(self) -> Token:
        start_line, start_col = self.line, self.column
        buf = []
        while self.peek() and (self.peek().isalnum() or self.peek() == "_"):
            buf.append(self.advance())
        word  = "".join(buf)
        ttype = KEYWORDS.get(word, TokenType.IDENT)
        return Token(ttype, word, start_line, start_col)

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.source):
            self.skip_whitespace()
            ch = self.peek()
            if ch is None:
                break

            start_line, start_col = self.line, self.column

            # Commentaires
            if ch == "#":
                while self.peek() and self.peek() != "\n":
                    self.advance()
                continue

            # Saut de ligne
            if ch == "\n":
                self.tokens.append(Token(TokenType.NEWLINE, "\\n", start_line, start_col))
                self.advance()
                continue

            # Chaîne
            if ch == '"':
                self.tokens.append(self.read_string())
                continue

            # Nombre
            if ch.isdigit():
                self.tokens.append(self.read_number())
                continue

            # Identifiant / mot-clé
            if ch.isalpha() or ch == "_":
                self.tokens.append(self.read_ident())
                continue

            # Opérateurs multi-caractères
            self.advance()
            if ch == "=" and self.match("="):
                self.tokens.append(Token(TokenType.EQ, "==", start_line, start_col))
            elif ch == "=" and self.match(">"):
                self.tokens.append(Token(TokenType.FAT_ARROW, "=>", start_line, start_col))
            elif ch == "=":
                self.tokens.append(Token(TokenType.ASSIGN, "=", start_line, start_col))
            elif ch == "!" and self.match("="):
                self.tokens.append(Token(TokenType.NEQ, "!=", start_line, start_col))
            elif ch == "<" and self.match("="):
                self.tokens.append(Token(TokenType.LTE, "<=", start_line, start_col))
            elif ch == "<":
                self.tokens.append(Token(TokenType.LT, "<", start_line, start_col))
            elif ch == ">" and self.match("="):
                self.tokens.append(Token(TokenType.GTE, ">=", start_line, start_col))
            elif ch == ">":
                self.tokens.append(Token(TokenType.GT, ">", start_line, start_col))
            elif ch == "-" and self.match(">"):
                self.tokens.append(Token(TokenType.ARROW, "->", start_line, start_col))
            elif ch == "-" and self.match("="):
                self.tokens.append(Token(TokenType.MINUS_EQ, "-=", start_line, start_col))
            elif ch == "-":
                self.tokens.append(Token(TokenType.MINUS, "-", start_line, start_col))
            elif ch == "+" and self.match("="):
                self.tokens.append(Token(TokenType.PLUS_EQ, "+=", start_line, start_col))
            elif ch == "+":
                self.tokens.append(Token(TokenType.PLUS, "+", start_line, start_col))
            elif ch == "*" and self.match("="):
                self.tokens.append(Token(TokenType.STAR_EQ, "*=", start_line, start_col))
            elif ch == "*":
                self.tokens.append(Token(TokenType.STAR, "*", start_line, start_col))
            elif ch == "/" and self.match("="):
                self.tokens.append(Token(TokenType.SLASH_EQ, "/=", start_line, start_col))
            elif ch == "/":
                self.tokens.append(Token(TokenType.SLASH, "/", start_line, start_col))
            elif ch == "." and self.match("."):
                self.tokens.append(Token(TokenType.DOTDOT, "..", start_line, start_col))
            elif ch == ".":
                self.tokens.append(Token(TokenType.DOT, ".", start_line, start_col))
            elif ch == "%":
                self.tokens.append(Token(TokenType.PERCENT, "%", start_line, start_col))
            elif ch == "@":
                self.tokens.append(Token(TokenType.AT, "@", start_line, start_col))
            elif ch == "?":
                self.tokens.append(Token(TokenType.QUESTION, "?", start_line, start_col))
            elif ch == ":":
                self.tokens.append(Token(TokenType.COLON, ":", start_line, start_col))
            elif ch == ",":
                self.tokens.append(Token(TokenType.COMMA, ",", start_line, start_col))
            elif ch == "(":
                self.tokens.append(Token(TokenType.LPAREN, "(", start_line, start_col))
            elif ch == ")":
                self.tokens.append(Token(TokenType.RPAREN, ")", start_line, start_col))
            elif ch == "[":
                self.tokens.append(Token(TokenType.LBRACKET, "[", start_line, start_col))
            elif ch == "]":
                self.tokens.append(Token(TokenType.RBRACKET, "]", start_line, start_col))
            elif ch == "{":
                self.tokens.append(Token(TokenType.LBRACE, "{", start_line, start_col))
            elif ch == "}":
                self.tokens.append(Token(TokenType.RBRACE, "}", start_line, start_col))
            else:
                raise err_unexpected_char(ch, start_line, start_col,
                                          filename=self.filename, source=self.source)

        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens


# ── Test rapide ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = """
fun greet(name: String) -> String
    return "Bonjour, " + name
end

blueprint Person
    name: String
    age:  Int = 0

    fun birthday()
        age += 1
    end
end

alice = Person.new(name: "Alice", age: 25)
alice.birthday()
print(alice.name)
"""
    lexer  = Lexer(sample, "test.air")
    tokens = lexer.tokenize()
    for tok in tokens:
        if tok.type != TokenType.NEWLINE:
            print(tok)
