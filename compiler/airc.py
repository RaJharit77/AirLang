#!/usr/bin/env python3
"""
airc — AirLang Compiler CLI
Usage:
    airc <file.air>           Compile et exécute
    airc <file.air> --ast     Affiche l'AST
    airc <file.air> --tokens  Affiche les tokens
    airc <file.air> --check   Vérifie sans compiler
"""

import sys
import os
from lexer import Lexer, LexerError


BANNER = """
╔═══════════════════════════════════╗
║   AirLang Compiler v0.1           ║
║   Simple comme respirer. ✈        ║
╚═══════════════════════════════════╝
"""


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(BANNER)
        print(__doc__)
        return

    filename = args[0]
    flags    = set(args[1:])

    if not os.path.exists(filename):
        print(f"✘ Fichier introuvable : {filename}")
        sys.exit(1)

    if not filename.endswith((".air", ".a")):
        print(f"⚠ Attention : l'extension devrait être .air ou .a (reçu : {filename})")

    with open(filename, "r", encoding="utf-8") as f:
        source = f.read()

    print(f"→ Lecture de {filename} ({len(source)} caractères)")

    # ── Lexer ────────────────────────────────────────────────────────────────
    try:
        lexer  = Lexer(source, filename)
        tokens = lexer.tokenize()
    except LexerError as e:
        print(f"\n✘ {e}")
        sys.exit(1)

    if "--tokens" in flags:
        print(f"\n── Tokens ({len(tokens)}) ──────────────────────────────")
        from lexer import TokenType
        for tok in tokens:
            if tok.type not in (TokenType.NEWLINE, TokenType.EOF):
                print(f"  {tok}")
        return

    print(f"✓ Lexer : {len(tokens)} tokens générés")

    # ── Parser (Semaine 2) ───────────────────────────────────────────────────
    if "--ast" in flags:
        print("\n⚠ Parser non encore implémenté (Semaine 2)")
        return

    # ── Type Checker (Semaine 2) ─────────────────────────────────────────────
    if "--check" in flags:
        print("\n⚠ Type Checker non encore implémenté (Semaine 2)")
        return

    # ── Code Generator (Semaine 3) ───────────────────────────────────────────
    print("\n⚠ Génération de code non encore implémentée (Semaine 3)")
    print("   Pour l'instant, utilisez --tokens pour voir le résultat du Lexer.")


if __name__ == "__main__":
    main()
