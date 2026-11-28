# Journal des changements

## 0.7.0

**Ajouts**
- **Mémoire récupérée automatiquement** : ramasse-miettes conservatif (marquage + balayage) dans le runtime.
  Libère aussi les cycles, ne change pas le code généré. Réglages : `AIR_GC=0`, `AIR_GC_STATS=1`,
  `AIR_GC_STRESS=N`, `AIR_GC_THRESHOLD`. Détails et limites : `docs/memory.md`.
- **Traits comme types de valeur** : `fun show(n: Named)`, `x: Named = Puppy.new()`, `List[Named]`, retours de
  type trait, trait exporté d'un module (`shapes.Named`). Dispatch dynamique (les redéfinitions des sous-classes
  sont respectées).
- `tests/programs/traits.air` ; `AIR_GC_STRESS=1 make sanitize`.

**Changement de plan (assumé)**
- Le comptage de références annoncé pour la v0.7 est remplacé par un ramasse-miettes : même résultat pour
  l'utilisateur (la mémoire est rendue), sans réécrire le générateur de code, et les cycles sont libérés.

**Changements incompatibles**
- Aucun changement de syntaxe. `air_free` est un no-op dans le runtime (le GC s'en charge).

**Limites connues**
- GC actif seulement sous Linux avec gcc/clang ; ailleurs le comportement est celui de la v0.6.
- Collecte non incrémentale (pause proportionnelle au tas vivant).
- Traits optionnels (`Named?`) : erreur claire ; pas de fonctions imbriquées ; pas de REPL ; modules à points absents.

## 0.6.0

**Ajouts**
- `assert(cond[, "msg"])`, `assert_eq(a, b)` (Int, Float, Bool, String) et `exit(code)`. Les assertions échouent avec une
  erreur rattrapable qui indique la ligne et, pour `assert_eq`, les deux valeurs.
- `air test <fichier|dossier>` : exécute les fonctions `test_*`, affiche ✔/✘ par test, code de sortie 1 en cas d'échec.
  `examples/tests/test_math.air` en est l'exemple.
- **Blueprints et traits exportables** depuis un module : `geo.Shape`, `geo.Shape.new(...)`, `extends geo.Shape`,
  héritage entre fichiers, mêmes contrôles `export` que pour les fonctions.
- Les messages d'erreur n'affichent plus les préfixes internes des modules (`Square`, pas `shapes_1__Square`).
- Littéraux de liste mixtes : `xs: List[Forme] = [carré, cercle]` et `[carré, cercle]` (ancêtre commun inféré).
- `docs/memory.md` : état et plan détaillé du comptage de références (v0.7).

**Corrections**
- Une fonction qui se termine par `fail(...)` ou `exit(...)` n'exige plus de `return` final (fausse erreur « chemin sans return »).

**Changements incompatibles**
- Les noms `assert`, `assert_eq` et `exit` sont désormais réservés comme fonctions intégrées.
- `[a, b]` avec deux sous-classes différentes est maintenant accepté (auparavant : erreur) ; une liste annotée
  vérifie chaque élément contre le type annoncé.

**Limites connues**
- La mémoire n'est toujours pas libérée (v0.7, voir `docs/memory.md`).
- Un trait ne peut pas encore servir de type de paramètre ou de variable (`fun f(x: Named)`) : erreur claire du compilateur.
- Les modules à points (`import net.http`) ne sont pas supportés ; pas de REPL.
- Les erreurs de types dans un module importé sont signalées avec le bon fichier, mais un module qui échoue à la
  génération de code (cas rares) peut citer la ligne du fichier principal.

## 0.5.0

**Ajouts**
- **Imports de fichiers** : `import "./utils/formatter"` et `import "./x" as y`, chemins relatifs au fichier importateur.
  Seules les déclarations `export` sont visibles (`n'est pas exporté par …` sinon) ; imports imbriqués et partagés
  (chargés une seule fois) ; détection des cycles (`a.air -> b.air -> a.air`).
- Chaque module est vérifié seul : une erreur de type dans `bad.air` est affichée avec le fichier et la ligne de `bad.air`.
- Modules standard `string` (`repeat pad_left pad_right reverse capitalize count is_empty`) et `list`
  (`range sum sum_float max_int min_int average`), écrits en AirLang.
- Un nom local (paramètre, variable, boucle, `catch`, motif) n'est jamais confondu avec un nom du module.
- `examples/modules/` : exemple multi-fichiers.

**Changements incompatibles**
- `stdlib/string.air` et `stdlib/list.air` sont réécrits (anciens `@native` pour un runtime de listes abandonné) ;
  les méthodes `s.split()`, `xs.map()`… restent des méthodes intégrées, sans import.
- `import x` avec `x` inconnu est une erreur (la liste des modules disponibles est donnée).

**Limites connues**
- Un module ne contient que des fonctions, constantes et imports ; blueprints/traits exportés : v0.6.
- La mémoire n'est toujours pas libérée : le comptage de références est repoussé à la v0.6 (changement trop profond pour un palier de modules).
- `import net.http` (modules à points) n'est pas supporté.

## 0.4.0

**Ajouts**
- Fonctions anonymes `fun(x) => …` et **fermetures** (capture par valeur), fonctions comme valeurs (`Fun[Int, Int]`),
  `f(1)(2)`, et méthodes de liste `map filter reduce each any all`.
- `Result[T]` avec `Ok(v)` / `Err(msg)`, opérateur `?` (propagation), `.is_ok() .is_err() .unwrap() .unwrap_or(d) .message`.
- `match` en instruction (bras à plusieurs instructions) et en expression, motifs `Ok(v)` / `Err(m)` / littéraux / `_`,
  vérification d'exhaustivité.
- `try` / `catch e` / `fail("msg")` : les erreurs d'exécution (division par zéro, index hors limites, `unwrap`, `io.read`…) sont rattrapables.
- Types optionnels `Int?` `Float?` `Bool?` `String?` + **promotion** après un test (`if x == null … return end`,
  `x != null and x > 3`).
- `String` : `slice(a, b)`, `to_int()`, `to_float()` (retournent `Int?` / `Float?`), comparaisons `< > <= >=`, `for ch in texte` (Unicode).
- Modules `import io` et `import math` (+ `math.PI`, `math.E`) ; `@native("symbole_c")` comme corps de fonction.
- `examples/calculator.air` et `examples/todo.air` compilent et s'exécutent ; `tests/programs/v04.air` passe sous ASan/UBSan.
- Messages d'erreur : indices pour optionnels non testés, lambdas sans type déductible, `catch` hors `Error`, module/fonction inconnus.

**Corrections**
- `print(1.0)` affichait `1` ; les flottants s'affichent en aller-retour exact (`1.0`, `0.1`, `180.0`).
- `io.read` échoue proprement (rattrapable) au lieu de renvoyer l'ancien `AirResult` incompatible.

**Changements incompatibles**
- `io.read` retourne `String` (et échoue si illisible) ; `io.write` / `io.append` retournent `Bool`.
- Les flottants s'affichent avec `.0` (`2.0 -1.0` dans `loops.expected`).
- `examples/calculator.air` migré : `"texte" + valeur` → interpolation `"texte {valeur}"`.

**Limites connues**
- Seuls `io` et `math` sont importables ; imports de fichiers et modules `string`/`list` : v0.5.
- `@native` seulement comme unique corps d'une fonction ; pas de fonctions imbriquées.
- Les fermetures capturent par valeur (une variable modifiée après la création n'est pas vue).
- La mémoire n'est toujours pas libérée (comptage de références prévu en v0.5) ; clés de map : `String` uniquement.

## 0.3.0

**Ajouts**
- Listes `List[T]` et maps `Map[String, V]` typées, stockées par valeur : littéraux, `xs[i]`, `xs[i] = v`, `m["k"] += 1`,
  `for x in xs`, `for i, x in xs`, `for k in map` ; méthodes `append length pop first last contains index_of remove_at clear reverse sort join`
  (liste) et `length has get_or keys values delete clear` (map) ; `String.split` ; `len(...)`, `print(...)` sur listes et maps.
- Héritage `extends` avec **appels virtuels** (table virtuelle par blueprint) : une méthode redéfinie est appelée même via une variable typée avec le parent.
- `break` / `continue` ; `if cond then … end` sur une ligne (le `then` est optionnel en multi-ligne).
- **Ordre d'évaluation garanti de gauche à droite** (`print(xs.pop(), xs)`), indépendant du compilateur C.
- `air` (Rust) : CLI unique + `air fmt` basé sur les tokens, qui ne change jamais les tokens et est idempotent.
- `tools/airdoc.rb` (Ruby) : référence de la stdlib générée depuis les commentaires `##`.
- Makefile, CI GitHub Actions (Python, Rust, Ruby, formatage, doc à jour, ASan + UBSan).

**Corrections**
- Boucle infinie du parseur sur un `trait` contenant une méthode sans corps (présente depuis la v0.1).
- Colonne d'erreur du lexer décalée de 1.
- `air_stdlib.c` utilisait encore l'ancienne représentation des listes et ne compilait plus avec le nouveau runtime.

**Changements incompatibles**
- Dans un `trait`, une signature `fun nom(...)` n'a ni corps ni `end` (comme dans la spec §3.3).
- `"texte" + entier` est une erreur : utilisez l'interpolation `"texte {x}"` (migré dans `examples/todo.air`).
- `@` est maintenant reconnu par le lexer ; le parseur répond « décorateurs pas encore supportés (v0.5) ».
- `airfmt` (script Python à regex) est obsolète : utilisez `air fmt`.

**Limites connues**
- La mémoire n'est jamais libérée (comptage de références prévu).
- Les clés de map sont uniquement des `String`.
- `Int / Int` est une division entière.
