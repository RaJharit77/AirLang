# Journal des changements

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
