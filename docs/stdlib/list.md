# list

Manipulation de listes.
Import : `import list  (ou utiliser les méthodes directement sur la liste)`

> Généré par `tools/airdoc.rb` depuis `stdlib/list.air` — ne pas modifier à la main.

## `length`

```air
fun length(lst: List[Any]) -> Int
```

Retourne le nombre d'éléments d'une liste.

```air
list.length([1, 2, 3])  # => 3
```

## `get`

```air
fun get(lst: List[Any], i: Int) -> Any
```

Retourne l'élément à l'index i (supporte les index négatifs : -1 = dernier).

```air
list.get(items, 0)
```

## `set`

```air
fun set(lst: List[Any], i: Int, value: Any)
```

Modifie l'élément à l'index i.

```air
list.set(items, 0, "nouveau")
```

## `append`

```air
fun append(lst: List[Any], item: Any)
```

Ajoute un élément à la fin de la liste.

```air
list.append(items, "Alice")
```

## `prepend`

```air
fun prepend(lst: List[Any], item: Any)
```

Insère un élément au début de la liste.

```air
list.prepend(items, "premier")
```

## `pop`

```air
fun pop(lst: List[Any]) -> Any
```

Supprime et retourne le dernier élément.

```air
last = list.pop(items)
```

## `pop_front`

```air
fun pop_front(lst: List[Any]) -> Any
```

Supprime et retourne le premier élément.

```air
first = list.pop_front(items)
```

## `map`

```air
fun map(lst: List[Any], fn: Fun) -> List[Any]
```

Retourne une nouvelle liste avec chaque élément transformé par fn.

```air
doubled = list.map(numbers, fun(x) => x * 2)
```

## `filter`

```air
fun filter(lst: List[Any], fn: Fun) -> List[Any]
```

Retourne une nouvelle liste avec uniquement les éléments où fn retourne true.

```air
evens = list.filter(numbers, fun(x) => x % 2 == 0)
```

## `reduce`

```air
fun reduce(lst: List[Any], initial: Any, fn: Fun) -> Any
```

Réduit la liste à une valeur unique via fn(accumulateur, élément).

```air
total = list.reduce(numbers, 0, fun(acc, x) => acc + x)
```

## `sort`

```air
fun sort(lst: List[Any], cmp_fn: Fun)
```

Trie la liste en place selon une fonction de comparaison.

```air
list.sort(names, fun(a, b) => a < b)
```

## `unique`

```air
fun unique(lst: List[Any]) -> List[Any]
```

Retourne une nouvelle liste sans doublons.

```air
unique_names = list.unique(names)
```

## `flatten`

```air
fun flatten(lst: List[List[Any]]) -> List[Any]
```

Aplatit une liste de listes en une liste simple.

```air
list.flatten([[1, 2], [3, 4]])  # => [1, 2, 3, 4]
```

## `reverse`

```air
fun reverse(lst: List[Any]) -> List[Any]
```

Retourne une nouvelle liste avec les éléments en ordre inverse.

```air
list.reverse([1, 2, 3])  # => [3, 2, 1]
```

## `slice`

```air
fun slice(lst: List[Any], start: Int, end: Int) -> List[Any]
```

Retourne une sous-liste entre start (inclus) et end (exclus).

```air
list.slice(items, 1, 3)
```

## `concat`

```air
fun concat(a: List[Any], b: List[Any]) -> List[Any]
```

Concatène deux listes en une nouvelle liste.

```air
all = list.concat(list_a, list_b)
```

## `contains`

```air
fun contains(lst: List[Any], item: Any) -> Bool
```

Vérifie si un élément est présent dans la liste.

```air
list.contains(names, "Alice")
```

## `index_of`

```air
fun index_of(lst: List[Any], item: Any) -> Int
```

Retourne l'index du premier élément égal à item (-1 si absent).

```air
i = list.index_of(names, "Bob")
```
