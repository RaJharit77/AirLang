# list

Utilitaires sur les listes de nombres (écrits en AirLang).
Import : `import list`
Les méthodes de base (`xs.map(...)`, `xs.sort()`, `xs.length()`...) n'ont pas besoin d'import.

> Généré par `tools/airdoc.rb` depuis `stdlib/list.air` — ne pas modifier à la main.

## `range`

```air
fun range(from: Int, to: Int) -> List[Int]
```

Liste des entiers de `from` (inclus) à `to` (exclu).

```air
list.range(1, 4)  # => [1, 2, 3]
```

## `sum`

```air
fun sum(xs: List[Int]) -> Int
```

Somme d'une liste d'entiers (0 si elle est vide).

```air
list.sum([1, 2, 3])  # => 6
```

## `sum_float`

```air
fun sum_float(xs: List[Float]) -> Float
```

Somme d'une liste de flottants (0.0 si elle est vide).

```air
list.sum_float([1.5, 2.5])  # => 4.0
```

## `max_int`

```air
fun max_int(xs: List[Int]) -> Int?
```

Plus grand entier de la liste, ou null si elle est vide.

```air
list.max_int([3, 9, 2])  # => 9
```

## `min_int`

```air
fun min_int(xs: List[Int]) -> Int?
```

Plus petit entier de la liste, ou null si elle est vide.

```air
list.min_int([3, 9, 2])  # => 2
```

## `average`

```air
fun average(xs: List[Float]) -> Float?
```

Moyenne d'une liste de flottants, ou null si elle est vide.

```air
list.average([1.0, 2.0, 6.0])  # => 3.0
```
