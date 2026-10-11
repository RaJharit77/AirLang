# AirLang — Audit de l'existant et roadmap vers 1.0.0

Audit réalisé sur le dépôt `RaJharit77/AirLang` (branche `main`, commit `c11f3bc`), avec exécution réelle des tests et du pipeline. Python 3.13, gcc 13.3.

## 1. Résumé

| Étage | État | Verdict |
|---|---|---|
| Lexer (339 l.) | Fonctionne, testé | Bon socle. Un seul vrai défaut : `@` non reconnu |
| Parser (693 l.) | Fonctionne sur `hello` et `todo` | Bon socle, manques de syntaxe |
| AST (318 l.) | Complet pour la v0.1 | Pas de slot pour les types calculés |
| Type checker (579 l.) | Existe, **jamais appelé** | À corriger et à brancher |
| Codegen C (663 l.) | **Ne compile pas `hello.air`** | Plus gros chantier |
| Runtime C + stdlib C | Partiel | Fonctions déclarées non implémentées |
| CLI `airc.py` | Lexer seulement | Pipeline non branché |
| Tests | 107 tests : **101 OK, 6 KO** | Les 6 échecs sont tous des tests e2e du codegen |
| Docs | Une spec (v0.1), copiée 3 fois | README vide |

Le front-end (lexer + parser) est sain. Tout ce qui est après l'AST est à reprendre. **Aucun programme `.air` ne s'exécute aujourd'hui de bout en bout.**

## 2. Architecture actuelle

```
airc.py (racine) == compiler/airc.py   (doublons identiques)
compiler/  lexer.py → parser.py → ast_nodes.py → type_checker.py → codegen_c.py ; errors.py
runtime/   air_runtime.{h,c}, air_stdlib.c
stdlib/    io.air, string.air, math.air, list.air   (wrappers @native)
examples/  hello.air, todo.air, calculator.air
tests/     test_lexer.py, test_parser.py, test_codegen.py
docs/      spec.md = spec_model.md = spec_v_1_0.md   (md5 identiques)
airfmt     formatter (script Python sans extension)
project.air  manifeste (TOML-like, non lu par aucun code)
```

Le choix fondamental est bon et cohérent avec votre philosophie : **transpilation vers C + compilation par gcc**, sans VM. C'est ce qu'il faut garder.

## 3. Langage actuel (d'après le parser et la spec)

- Variables : `x = 1`, `x: Int = 1`, `const`, types optionnels `T?`
- Types : `Int Float Bool String Char Null List[T] Map[K,V] Result[T]`
- Contrôle : `if / else if / else / end`, `unless`, `while`, `for x in`, `for i, x in`, `match`, ranges `0..10`
- Fonctions : `fun`, paramètres typés, valeurs par défaut, lambdas `fun(x) => …`
- OOP : `blueprint`, `extends`, `trait`, `implements`, `Nom.new(champ: v)`
- Erreurs : `Result`, `Ok/Err`, `?`, `try/catch`
- Modules : `import`, `export`
- Mots réservés : voir spec §13

## 4. Problèmes détectés (priorisés)

### P0 — Bloquants (rien ne tourne tant qu'ils ne sont pas réglés)

| # | Problème | Pourquoi c'est grave | Correction |
|---|---|---|---|
| 1 | `airc` n'appelle ni parser, ni checker, ni codegen | Pas de compilateur utilisable | Brancher le pipeline complet + gcc |
| 2 | Le codegen devine les types (`_infer_c_type`, `name[0].isupper()` pour trouver un blueprint) | `"Bonjour, " + name` génère `air_int_to_str(AirStr)` → **hello.air ne compile pas** | Le checker annote chaque nœud avec son type ; le codegen lit ce type |
| 3 | `AirVal = void*` pour les listes/maps | Une `AirStr` ou un `double` ne tient pas dans un `void*` (`todo.air` : erreur gcc) | Représentation uniforme (voir §6) |
| 4 | `Blueprint_new` : prototype et usage incohérents (struct par valeur vs pointeur, arguments par défaut ignorés, appel de méthode sans préfixe `hello(g)`) | Les blueprints ne compilent pas | Blueprints = pointeurs alloués, méthodes `Type_methode(self, …)`, résolues via le type statique |
| 5 | `TypeChecker.check()` retourne un `ErrorCollector` non itérable | Le checker plante dès qu'on l'utilise | Corriger l'API de retour |
| 6 | `calculator.air` utilise `@native`, `break`, `continue`, patterns `Ok(v)` : le lexer rejette `@` | L'exemple phare ne se parse pas | Compléter lexer + parser (voir P1) |

### P1 — Importants

| # | Problème | Correction |
|---|---|---|
| 7 | `errors.py` redéfinit `TypeError` et `NameError` (masque les builtins) ; deux `LexerError` (lexer.py et errors.py) | Hiérarchie unique `AirError` + sous-classes `LexError`, `ParseError`, `TypeCheckError`, `CodegenError` |
| 8 | Imports plats (`from lexer import …`) : `compiler` n'est pas un package | `compiler/__init__.py`, imports relatifs, tests via `pip install -e .` |
| 9 | Les `NEWLINE` sont supprimés par le parser | `return` sans valeur suivi d'une ligne est lu comme `return x`. Les garder comme tokens significatifs |
| 10 | Type checker : `Int` non compatible avec `Float`, `Any` non assignable | Faux positifs partout. Règle : widening `Int→Float` explicite, `Any` bidirectionnel en mode dynamique |
| 11 | Pas de vérification du nombre d'arguments ni des champs requis dans `.new()` | Erreurs C incompréhensibles au lieu d'erreurs AirLang |
| 12 | Runtime : `air_list_sort`, `air_map_keys`, `air_map_values`, `air_map_free` déclarés, non implémentés ; `@native` de `list.air` ne correspondent pas aux noms de `air_stdlib.c` ; `memmem` sans `_GNU_SOURCE` | Aligner noms et implémentations, ajouter un test de liaison stdlib |
| 13 | Statements top-level émis au niveau fichier C | Invalide en C. Les mettre dans `main` (ou une fonction `__air_init`) |
| 14 | Lambdas, `try/catch`, maps littérales, traits : pas de code généré | Voir roadmap v0.4 |

### P2 — Qualité et hygiène

| # | Problème | Correction |
|---|---|---|
| 15 | `spec.md` triplée, README vide, spec de 612 lignes qui mélange spec et roadmap | Une seule spec, README réel, roadmap séparée |
| 16 | `airfmt` à base de regex : touche l'intérieur des commentaires, casse `-1`, `1..5`, `if … then … end` | Refaire à partir des tokens |
| 17 | `project.air` jamais lu | Soit implémenter (`air build`), soit le retirer jusqu'à ce qu'il serve |
| 18 | Extension `.a` acceptée par la CLI mais absente de la spec | Supprimer, `.air` uniquement |
| 19 | Pas de CI, pas de packaging, pas de `.gitignore` vérifié | GitHub Actions + `pyproject.toml` |
| 20 | Pas de tests de messages d'erreur (golden tests) | À ajouter avec la v0.2 |

## 5. Décision d'architecture : interpréteur, VM ou compilateur ?

| Option | Pour | Contre |
|---|---|---|
| Interpréteur d'AST | Le plus simple, REPL gratuit | Lent, ne tient pas la promesse « léger / natif » |
| VM bytecode | Portable, bon REPL | Un runtime + un jeu d'instructions à concevoir et maintenir |
| **Transpilation vers C + gcc/clang** (existant) | Performance native, déjà commencé, runtime minimal, interop C directe | Dépend d'un compilateur C installé ; messages d'erreur C à masquer |

**Recommandation : garder la transpilation C.** C'est la seule option qui réalise votre promesse « compilation native, pas de VM ». Pour `air repl` et l'expérience « ça marche tout de suite », on pourra plus tard ajouter un petit interpréteur d'AST. Ce n'est pas nécessaire pour 1.0.

Pipeline cible :

```
.air → Lexer → Parser → AST → Résolution de noms + Type checker (AST annoté)
     → [IR simple, optionnel] → Codegen C → gcc/clang + runtime → binaire
```

Je n'ajouterais **pas** d'IR avant la 1.0 : l'AST annoté suffit, et chaque couche supplémentaire est un coût de maintenance.

## 6. Décision sur la représentation des valeurs (le point technique central)

| Option | Principe | Verdict |
|---|---|---|
| A. `void*` partout (actuel) | Tout est un pointeur | Impossible pour `double`/`String` par valeur ; boxing généralisé lent |
| B. Valeur taguée `AirValue {tag, union}` | Un type unique pour le dynamique | Simple, mais lent et sans sécurité statique |
| **C. Types C natifs + collections génériques par monomorphisation** | `List[Int]` → `AirList_Int`, `List[String]` → `AirList_String` ; `Int→int64_t`, `Float→double`, `String→AirStr`, blueprint→`T*` | Rapide, typé, cohérent avec un checker qui annote |

**Recommandation : C**, avec `Any` implémenté en option B (valeur taguée) seulement pour le mode dynamique de la spec §6.

Mémoire pour 1.0 : **comptage de références simple pour strings, listes, maps et blueprints**. C'est le plus petit modèle correct. Une promesse « borrow-lite » (spec §1) n'est pas tenable à ce stade : je recommande de la retirer de la spec 1.0 et de la remettre en question plus tard.

## 7. Rôle de chaque langage

| Langage | Rôle | Pourquoi |
|---|---|---|
| **Python** | Compilateur jusqu'à la 1.0 | Vitesse d'itération. Réécrire en Rust maintenant ralentirait la stabilisation |
| **C** | Runtime + cible de génération | Pas de choix |
| **Rust** | Après la 1.0 : outil `air` (CLI unifiée, fmt, test, paquets) puis éventuellement compilateur auto-hébergé | Binaire unique facile à distribuer |

Je ne propose **aucun C++**. La spec évoque Go comme option : à retirer pour garder une histoire cohérente.

## 8. Roadmap vers 1.0.0

Priorité : **correction → architecture → simplicité → tests → ergonomie → performance → fonctionnalités**.

### Phase 1 — Stabilisation de la base (v0.2) — « hello.air compile et tourne »
- Package `compiler/` + `pyproject.toml`, hiérarchie d'erreurs unique, suppression des doublons
- CLI branchée : `air check | build | run | --tokens | --ast | --emit-c`
- Le checker annote les types sur l'AST ; codegen typé pour : Int, Float, Bool, String, fonctions, if/while/for, print
- Erreurs au format cible (ligne, colonne, extrait, `help:`), avec golden tests
- CI GitHub Actions
- **Critère de sortie :** `hello.air` compile et s'exécute ; 0 test en échec

### Phase 2 — Langage utilisable (v0.3 → v0.4)
- v0.3 : blueprints (champs, `.new()`, méthodes, héritage), listes et maps typées, `break`/`continue`, `then` sur une ligne, garder les `NEWLINE`
- v0.4 : lambdas + fermetures, `Result`/`Ok`/`Err`/`?`, `match` (valeur + patterns), `try/catch`, traits
- **Critère de sortie :** `todo.air` et `calculator.air` compilent et tournent

### Phase 3 — Langage exploitable (v0.5 → v0.6)
- Modules/`import`/`export` résolus (fichiers locaux + stdlib), `@native` aligné sur le runtime
- Stdlib : `io`, `string`, `list`, `map`, `math`, `os`, `time`, `json`, chacune testée
- `airfmt` basé sur les tokens, `air test`, `air repl` (si simple)
- Documentation : guide, référence stdlib, erreurs courantes
- Mise en place de la politique de compatibilité

### Phase 4 — Maturité (v0.7 → v0.9)
- Gel progressif de la syntaxe, RFC courtes pour tout changement
- Fuzzing du lexer/parser, tests de non-régression des erreurs
- Benchmarks (boucles, strings, listes) et options `-O2`
- Sécurité du runtime : bornes, overflow, fuites (valgrind/ASan en CI)
- Coloration syntaxique VS Code, `project.air` fonctionnel
- Décision sur les features avancées (async, FFI C) : **uniquement si utilisées par un vrai programme exemple**, sinon repoussées en 1.x

### Phase 5 — Release 1.0.0
- Spécification figée, documentation complète, exemples, `CHANGELOG`
- Binaires/installation en une commande, release candidate (`1.0.0-rc1`), puis `1.0.0`
- Versioning sémantique

## 9. Décisions à valider avec vous

1. **Rester sur la transpilation C** (recommandé) — oui/non ?
2. **Valeurs typées natives + monomorphisation** (§6, option C) — oui/non ?
3. **Mémoire : comptage de références** pour la 1.0, et retirer « borrow-lite » de la spec ?
4. **Python pour le compilateur jusqu'à 1.0, Rust après** — d'accord ?
5. **Concurrence/async et FFI** hors du périmètre 1.0 ?
6. **Compatibilité :** `+` entre String et Int (`"Itération " + i`) est utilisé dans vos exemples mais contredit « pas de coercition » de la spec. Je propose de garder `"texte" + entier` interdit et d'ajouter une interpolation `"Itération {i}"`. Cela casse vos exemples (à migrer) mais cadre avec la philosophie. Alternative : conversion implicite vers String uniquement pour `+` avec une String.
