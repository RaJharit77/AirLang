"""
AirLang — parser.py
Parser par descente récursive : transforme une liste de tokens en AST.
"""

from __future__ import annotations
from typing import List, Optional

from lexer import Token, TokenType, Lexer
from ast_nodes import *
from errors import ParseError, err_expected_token, err_expected_end


class Parser:
    def __init__(self, tokens: List[Token], source: str = "", filename: str = "<source>"):
        # Filtre les NEWLINEs pour simplifier le parsing
        self.tokens   = [t for t in tokens if t.type != TokenType.NEWLINE]
        self.pos      = 0
        self.source   = source
        self.filename = filename

    # ── Utilitaires ────────────────────────────────────────────────────────────

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else self.tokens[-1]

    def current(self) -> Token:
        return self.peek(0)

    def at(self, *types: TokenType) -> bool:
        return self.current().type in types

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def expect(self, ttype: TokenType, hint: str = "") -> Token:
        tok = self.current()
        if tok.type != ttype:
            raise err_expected_token(
                ttype.name, tok.value or tok.type.name,
                tok.line, tok.column,
                source=self.source, filename=self.filename,
                hint=hint or None,
            )
        return self.advance()

    def expect_end(self, construct: str) -> Token:
        tok = self.current()
        if tok.type != TokenType.END:
            raise err_expected_end(construct, tok.line, tok.column,
                                   source=self.source, filename=self.filename)
        return self.advance()

    def match(self, *types: TokenType) -> Optional[Token]:
        if self.current().type in types:
            return self.advance()
        return None

    def _pos(self) -> dict:
        t = self.current()
        return {"line": t.line, "column": t.column}

    # ── Point d'entrée ─────────────────────────────────────────────────────────

    def parse(self) -> Program:
        stmts = []
        while not self.at(TokenType.EOF):
            stmts.append(self.parse_statement())
        return Program(statements=stmts, **self._pos())

    # ── Statements ─────────────────────────────────────────────────────────────

    def parse_statement(self) -> Node:
        tok = self.current()

        if tok.type == TokenType.IMPORT:
            return self.parse_import()
        if tok.type == TokenType.EXPORT:
            return self.parse_export()
        if tok.type == TokenType.FUN:
            return self.parse_fun_decl()
        if tok.type == TokenType.BLUEPRINT:
            return self.parse_blueprint()
        if tok.type == TokenType.TRAIT:
            return self.parse_trait()
        if tok.type == TokenType.CONST:
            return self.parse_const()
        if tok.type == TokenType.IF:
            return self.parse_if_stmt()
        if tok.type == TokenType.UNLESS:
            return self.parse_unless()
        if tok.type == TokenType.WHILE:
            return self.parse_while()
        if tok.type == TokenType.FOR:
            return self.parse_for()
        if tok.type == TokenType.MATCH:
            return self.parse_match()
        if tok.type == TokenType.TRY:
            return self.parse_try_catch()
        if tok.type == TokenType.RETURN:
            return self.parse_return()

        return self.parse_assign_or_expr()

    def parse_block(self, stop_tokens: tuple) -> List[Node]:
        """Parse des statements jusqu'à rencontrer un token stop."""
        body = []
        while not self.at(*stop_tokens, TokenType.EOF):
            body.append(self.parse_statement())
        return body

    # ── Import / Export ────────────────────────────────────────────────────────

    def parse_import(self) -> ImportDecl:
        pos = self._pos()
        self.advance()  # import
        # Le chemin peut être un identifiant (import io) ou une chaîne (import "./utils")
        tok = self.current()
        if tok.type == TokenType.STRING:
            path = self.advance().value
        elif tok.type == TokenType.IDENT:
            # Assemble les segments : net.http  =>  "net.http"
            parts = [self.advance().value]
            while self.at(TokenType.DOT):
                self.advance()  # .
                parts.append(self.expect(TokenType.IDENT).value)
            path = ".".join(parts)
        else:
            raise err_expected_token("nom de module ou chemin", tok.value,
                                     tok.line, tok.column,
                                     source=self.source, filename=self.filename)
        alias = None
        if self.match(TokenType.AS):
            alias = self.expect(TokenType.IDENT).value
        return ImportDecl(path=path, alias=alias, **pos)

    def parse_export(self) -> ExportDecl:
        pos = self._pos()
        self.advance()  # export
        decl = self.parse_statement()
        if hasattr(decl, "is_export"):
            decl.is_export = True
        return ExportDecl(declaration=decl, **pos)

    # ── Déclaration de fonction ────────────────────────────────────────────────

    def parse_fun_decl(self, decorators: List[str] = None) -> FunDecl:
        pos = self._pos()
        self.advance()  # fun
        name = self.expect(TokenType.IDENT).value
        params = self.parse_params()
        return_type = None
        if self.match(TokenType.ARROW):
            return_type = self.parse_type_annotation()
        body = self.parse_block((TokenType.END,))
        self.expect_end("fun")
        return FunDecl(name=name, params=params, return_type=return_type,
                       body=body, decorators=decorators or [], **pos)

    def parse_params(self) -> List[Param]:
        self.expect(TokenType.LPAREN)
        params = []
        while not self.at(TokenType.RPAREN, TokenType.EOF):
            p = self._parse_single_param()
            params.append(p)
            if not self.match(TokenType.COMMA):
                break
        self.expect(TokenType.RPAREN)
        return params

    def _parse_single_param(self) -> Param:
        pos  = self._pos()
        name = self.expect(TokenType.IDENT).value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_annotation()
        default = None
        if self.match(TokenType.ASSIGN):
            default = self.parse_expression()
        return Param(name=name, type_ann=type_ann, default=default, **pos)

    # ── Blueprint ──────────────────────────────────────────────────────────────

    def parse_blueprint(self) -> BlueprintDecl:
        pos = self._pos()
        self.advance()  # blueprint
        name = self.expect(TokenType.IDENT).value
        extends = None
        if self.match(TokenType.EXTENDS):
            extends = self.expect(TokenType.IDENT).value
        implements = []
        if self.match(TokenType.IMPLEMENTS):
            implements.append(self.expect(TokenType.IDENT).value)
            while self.match(TokenType.COMMA):
                implements.append(self.expect(TokenType.IDENT).value)

        fields, methods = [], []
        while not self.at(TokenType.END, TokenType.EOF):
            if self.at(TokenType.FUN):
                methods.append(self.parse_fun_decl())
            else:
                fields.append(self.parse_field())

        self.expect_end("blueprint")
        return BlueprintDecl(name=name, extends=extends, implements=implements,
                             fields=fields, methods=methods, **pos)

    def parse_field(self) -> Field:
        pos  = self._pos()
        name = self.expect(TokenType.IDENT).value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_annotation()
        default = None
        if self.match(TokenType.ASSIGN):
            default = self.parse_expression()
        return Field(name=name, type_ann=type_ann, default=default, **pos)

    # ── Trait ──────────────────────────────────────────────────────────────────

    def parse_trait(self) -> TraitDecl:
        pos = self._pos()
        self.advance()  # trait
        name    = self.expect(TokenType.IDENT).value
        methods = []
        while not self.at(TokenType.END, TokenType.EOF):
            if self.at(TokenType.FUN):
                methods.append(self.parse_fun_decl())
        self.expect_end("trait")
        return TraitDecl(name=name, methods=methods, **pos)

    # ── Constante ──────────────────────────────────────────────────────────────

    def parse_const(self) -> VarDecl:
        pos = self._pos()
        self.advance()  # const
        name = self.expect(TokenType.IDENT).value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_annotation()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expression()
        return VarDecl(name=name, type_ann=type_ann, value=value, is_const=True, **pos)

    # ── Structures de contrôle ─────────────────────────────────────────────────

    def parse_if_stmt(self) -> IfStmt:
        pos = self._pos()
        self.advance()  # if
        cond = self.parse_expression()
        then_body = self.parse_block((TokenType.ELSE, TokenType.END))
        elif_clauses, else_body = [], []

        while self.at(TokenType.ELSE):
            self.advance()  # else
            if self.at(TokenType.IF):
                self.advance()  # if
                elif_cond = self.parse_expression()
                elif_body = self.parse_block((TokenType.ELSE, TokenType.END))
                elif_clauses.append((elif_cond, elif_body))
            else:
                else_body = self.parse_block((TokenType.END,))
                break

        self.expect_end("if")
        return IfStmt(condition=cond, then_body=then_body,
                      elif_clauses=elif_clauses, else_body=else_body, **pos)

    def parse_unless(self) -> UnlessStmt:
        pos = self._pos()
        self.advance()  # unless
        cond = self.parse_expression()
        body = self.parse_block((TokenType.END,))
        self.expect_end("unless")
        return UnlessStmt(condition=cond, body=body, **pos)

    def parse_while(self) -> WhileStmt:
        pos = self._pos()
        self.advance()  # while
        cond = self.parse_expression()
        body = self.parse_block((TokenType.END,))
        self.expect_end("while")
        return WhileStmt(condition=cond, body=body, **pos)

    def parse_for(self) -> ForStmt:
        pos = self._pos()
        self.advance()  # for
        first = self.expect(TokenType.IDENT).value
        index_var, var = None, first
        if self.match(TokenType.COMMA):
            index_var = first
            var = self.expect(TokenType.IDENT).value
        self.expect(TokenType.IN)
        iterable = self.parse_expression()
        body = self.parse_block((TokenType.END,))
        self.expect_end("for")
        return ForStmt(var=var, index_var=index_var, iterable=iterable, body=body, **pos)

    def parse_match(self) -> MatchStmt:
        pos = self._pos()
        self.advance()  # match
        subject = self.parse_expression()
        cases   = []
        while not self.at(TokenType.END, TokenType.EOF):
            pattern = self.parse_expression()
            self.expect(TokenType.FAT_ARROW)
            action  = self.parse_statement()
            cases.append((pattern, action))
        self.expect_end("match")
        return MatchStmt(subject=subject, cases=cases, **pos)

    def parse_try_catch(self) -> TryCatch:
        pos = self._pos()
        self.advance()  # try
        try_body   = self.parse_block((TokenType.CATCH,))
        self.expect(TokenType.CATCH)
        error_var  = self.expect(TokenType.IDENT).value
        error_type = None
        if self.match(TokenType.COLON):
            error_type = self.parse_type_annotation()
        catch_body = self.parse_block((TokenType.END,))
        self.expect_end("try")
        return TryCatch(try_body=try_body, error_var=error_var,
                        error_type=error_type, catch_body=catch_body, **pos)

    def parse_return(self) -> Return:
        pos = self._pos()
        self.advance()  # return
        value = None
        if not self.at(TokenType.END, TokenType.ELSE, TokenType.EOF,
                       TokenType.FUN, TokenType.BLUEPRINT):
            value = self.parse_expression()
        return Return(value=value, **pos)

    # ── Assignation ou expression ──────────────────────────────────────────────

    def parse_assign_or_expr(self) -> Node:
        pos = self._pos()

        # Déclaration typée : "name: Type = value"  ou  "name: Type? = value"
        # Pattern : IDENT COLON ...type... ASSIGN expr
        if (self.at(TokenType.IDENT) and
                self.peek(1).type == TokenType.COLON):
            name_tok = self.advance()   # IDENT
            self.advance()              # COLON
            type_ann = self.parse_type_annotation()
            if self.at(TokenType.ASSIGN):
                self.advance()          # =
                value = self.parse_expression()
                return VarDecl(name=name_tok.value, type_ann=type_ann,
                               value=value, **pos)
            # name: Type sans valeur (champ de blueprint hors blueprint → rare)
            return VarDecl(name=name_tok.value, type_ann=type_ann,
                           value=None, **pos)

        expr = self.parse_expression()

        assign_ops = {
            TokenType.ASSIGN:   "=",
            TokenType.PLUS_EQ:  "+=",
            TokenType.MINUS_EQ: "-=",
            TokenType.STAR_EQ:  "*=",
            TokenType.SLASH_EQ: "/=",
        }
        if self.current().type in assign_ops:
            op    = assign_ops[self.advance().type]
            value = self.parse_expression()
            return Assign(target=expr, op=op, value=value, **pos)

        return ExprStmt(expr=expr, **pos)

    # ── Annotations de type ────────────────────────────────────────────────────

    def parse_type_annotation(self) -> TypeAnnotation:
        pos  = self._pos()
        name = self.expect(TokenType.IDENT).value
        params = []
        if self.match(TokenType.LBRACKET):
            params.append(self.parse_type_annotation())
            while self.match(TokenType.COMMA):
                params.append(self.parse_type_annotation())
            self.expect(TokenType.RBRACKET)
        optional = bool(self.match(TokenType.QUESTION))
        return TypeAnnotation(name=name, params=params, optional=optional, **pos)

    # ── Expressions (ordre de précédence croissant) ────────────────────────────

    def parse_expression(self) -> Node:
        return self.parse_or()

    def parse_or(self) -> Node:
        pos  = self._pos()
        left = self.parse_and()
        while self.at(TokenType.OR):
            op    = self.advance().value
            right = self.parse_and()
            left  = BinaryOp(left=left, op=op, right=right, **pos)
        return left

    def parse_and(self) -> Node:
        pos  = self._pos()
        left = self.parse_not()
        while self.at(TokenType.AND):
            op    = self.advance().value
            right = self.parse_not()
            left  = BinaryOp(left=left, op=op, right=right, **pos)
        return left

    def parse_not(self) -> Node:
        pos = self._pos()
        if self.at(TokenType.NOT):
            op      = self.advance().value
            operand = self.parse_not()
            return UnaryOp(op=op, operand=operand, **pos)
        return self.parse_comparison()

    def parse_comparison(self) -> Node:
        pos  = self._pos()
        left = self.parse_range()
        cmp_ops = (TokenType.EQ, TokenType.NEQ, TokenType.LT,
                   TokenType.GT, TokenType.LTE, TokenType.GTE)
        while self.at(*cmp_ops):
            op    = self.advance().value
            right = self.parse_range()
            left  = BinaryOp(left=left, op=op, right=right, **pos)
        return left

    def parse_range(self) -> Node:
        pos   = self._pos()
        start = self.parse_additive()
        if self.match(TokenType.DOTDOT):
            end = self.parse_additive()
            return RangeLiteral(start=start, end=end, **pos)
        return start

    def parse_additive(self) -> Node:
        pos  = self._pos()
        left = self.parse_multiplicative()
        while self.at(TokenType.PLUS, TokenType.MINUS):
            op    = self.advance().value
            right = self.parse_multiplicative()
            left  = BinaryOp(left=left, op=op, right=right, **pos)
        return left

    def parse_multiplicative(self) -> Node:
        pos  = self._pos()
        left = self.parse_unary()
        while self.at(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op    = self.advance().value
            right = self.parse_unary()
            left  = BinaryOp(left=left, op=op, right=right, **pos)
        return left

    def parse_unary(self) -> Node:
        pos = self._pos()
        if self.at(TokenType.MINUS):
            op      = self.advance().value
            operand = self.parse_unary()
            return UnaryOp(op=op, operand=operand, **pos)
        return self.parse_postfix()

    def parse_postfix(self) -> Node:
        """Gère .member, .method(...), [index], ?, enchaînement."""
        pos  = self._pos()
        expr = self.parse_primary()

        while True:
            if self.at(TokenType.DOT):
                self.advance()
                member = self.expect(TokenType.IDENT).value
                if self.at(TokenType.LPAREN):
                    args, kwargs = self.parse_call_args()
                    expr = MethodCall(obj=expr, method=member, args=args, kwargs=kwargs, **pos)
                else:
                    expr = MemberAccess(obj=expr, member=member, **pos)
            elif self.at(TokenType.LBRACKET):
                self.advance()
                index = self.parse_expression()
                self.expect(TokenType.RBRACKET)
                expr = IndexAccess(obj=expr, index=index, **pos)
            elif self.at(TokenType.QUESTION):
                self.advance()
                expr = ErrorPropagate(expr=expr, **pos)
            else:
                break

        return expr

    def parse_primary(self) -> Node:
        pos = self._pos()
        tok = self.current()

        # Littéraux
        if tok.type == TokenType.INT:
            self.advance()
            return IntLiteral(value=int(tok.value), **pos)

        if tok.type == TokenType.FLOAT:
            self.advance()
            return FloatLiteral(value=float(tok.value), **pos)

        if tok.type == TokenType.STRING:
            self.advance()
            return StringLiteral(value=tok.value, **pos)

        if tok.type == TokenType.BOOL:
            self.advance()
            return BoolLiteral(value=(tok.value == "true"), **pos)

        if tok.type == TokenType.NULL:
            self.advance()
            return NullLiteral(**pos)

        # Liste littérale
        if tok.type == TokenType.LBRACKET:
            return self.parse_list_literal()

        # Map littérale
        if tok.type == TokenType.LBRACE:
            return self.parse_map_literal()

        # Lambda : fun(params) => expr
        if tok.type == TokenType.FUN:
            return self.parse_lambda()

        # If expression inline : if cond then a else b end
        if tok.type == TokenType.IF:
            return self.parse_if_expression()

        # Parenthèses
        if tok.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr

        # Wildcard
        if tok.type == TokenType.IDENT and tok.value == "_":
            self.advance()
            return Identifier(name="_", **pos)

        # Identifiant, appel de fonction, ou Blueprint.new()
        if tok.type == TokenType.IDENT:
            self.advance()
            name = tok.value

            # Blueprint.new(...)
            if self.at(TokenType.DOT) and self.peek(1).type == TokenType.NEW:
                self.advance()  # .
                self.advance()  # new
                self.expect(TokenType.LPAREN)
                kwargs = self.parse_kwargs()
                self.expect(TokenType.RPAREN)
                return NewInstance(blueprint=name, kwargs=kwargs, **pos)

            # Appel de fonction : name(args)
            if self.at(TokenType.LPAREN):
                args, kwargs = self.parse_call_args()
                return Call(callee=Identifier(name=name, **pos), args=args, kwargs=kwargs, **pos)

            return Identifier(name=name, **pos)

        raise ParseError(
            f"Expression inattendue : {tok.value!r}",
            tok.line, tok.column,
            source=self.source, filename=self.filename,
            hint="Vérifiez la syntaxe de votre expression.",
        )

    # ── Helpers pour listes, maps, lambdas ────────────────────────────────────

    def parse_list_literal(self) -> ListLiteral:
        pos = self._pos()
        self.advance()  # [
        elements = []
        while not self.at(TokenType.RBRACKET, TokenType.EOF):
            elements.append(self.parse_expression())
            if not self.match(TokenType.COMMA):
                break
        self.expect(TokenType.RBRACKET)
        return ListLiteral(elements=elements, **pos)

    def parse_map_literal(self) -> MapLiteral:
        pos = self._pos()
        self.advance()  # {
        pairs = []
        while not self.at(TokenType.RBRACE, TokenType.EOF):
            key = self.parse_expression()
            self.expect(TokenType.COLON)
            val = self.parse_expression()
            pairs.append((key, val))
            if not self.match(TokenType.COMMA):
                break
        self.expect(TokenType.RBRACE)
        return MapLiteral(pairs=pairs, **pos)

    def parse_lambda(self) -> Lambda:
        pos = self._pos()
        self.advance()  # fun
        params = self.parse_params()
        self.expect(TokenType.FAT_ARROW)
        body = self.parse_expression()
        return Lambda(params=params, body=body, **pos)

    def parse_if_expression(self) -> IfExpression:
        pos = self._pos()
        self.advance()  # if
        cond = self.parse_expression()
        self.expect(TokenType.THEN)
        then_val = self.parse_expression()
        self.expect(TokenType.ELSE)
        else_val = self.parse_expression()
        self.expect_end("if")
        return IfExpression(condition=cond, then_value=then_val, else_value=else_val, **pos)

    def parse_call_args(self) -> tuple:
        """Retourne (args, kwargs). Détecte name: val pour les kwargs."""
        self.expect(TokenType.LPAREN)
        args, kwargs = [], []
        while not self.at(TokenType.RPAREN, TokenType.EOF):
            # Test si c'est un kwarg : ident COLON expr
            if (self.at(TokenType.IDENT) and self.peek(1).type == TokenType.COLON):
                name = self.advance().value
                self.advance()  # :
                val  = self.parse_expression()
                kwargs.append((name, val))
            else:
                args.append(self.parse_expression())
            if not self.match(TokenType.COMMA):
                break
        self.expect(TokenType.RPAREN)
        return args, kwargs

    def parse_kwargs(self) -> List[tuple]:
        """Parse uniquement les arguments nommés (pour .new())."""
        kwargs = []
        while not self.at(TokenType.RPAREN, TokenType.EOF):
            name = self.expect(TokenType.IDENT).value
            self.expect(TokenType.COLON)
            val  = self.parse_expression()
            kwargs.append((name, val))
            if not self.match(TokenType.COMMA):
                break
        return kwargs


# ── Fonction utilitaire ───────────────────────────────────────────────────────

def parse_source(source: str, filename: str = "<source>") -> Program:
    from lexer import Lexer
    tokens  = Lexer(source, filename).tokenize()
    parser  = Parser(tokens, source=source, filename=filename)
    return parser.parse()


# ── Test rapide ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from ast_nodes import pretty

    sample = """
import io

blueprint Person
    name: String
    age:  Int = 0

    fun greet()
        print("Bonjour, " + name)
    end

    fun is_adult() -> Bool
        return age >= 18
    end
end

fun main()
    alice = Person.new(name: "Alice", age: 25)
    alice.greet()
    if alice.is_adult()
        print("Adulte")
    end
end

main()
"""
    ast = parse_source(sample, "test.air")
    print(pretty(ast))
