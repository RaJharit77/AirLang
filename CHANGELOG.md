# Journal des changements

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
