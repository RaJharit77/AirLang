# string

Manipulation de chaînes de caractères.
Import : `import string`

> Généré par `tools/airdoc.rb` depuis `stdlib/string.air` — ne pas modifier à la main.

## `split`

```air
fun split(s: String, sep: String) -> List[String]
```

Découpe une chaîne selon un séparateur.

```air
parts = string.split("a,b,c", ",")  # => ["a", "b", "c"]
```

## `join`

```air
fun join(parts: List[String], sep: String) -> String
```

Assemble une liste de chaînes avec un séparateur.

```air
string.join(["a", "b", "c"], ", ")  # => "a, b, c"
```

## `trim`

```air
fun trim(s: String) -> String
```

Supprime les espaces en début et fin de chaîne.

```air
string.trim("  bonjour  ")  # => "bonjour"
```

## `trim_left`

```air
fun trim_left(s: String) -> String
```

Supprime les espaces uniquement en début de chaîne.

## `trim_right`

```air
fun trim_right(s: String) -> String
```

Supprime les espaces uniquement en fin de chaîne.

## `replace`

```air
fun replace(s: String, old: String, new: String) -> String
```

Remplace toutes les occurrences de old par new.

```air
string.replace("bonjour monde", "monde", "Alice")
```

## `contains`

```air
fun contains(s: String, sub: String) -> Bool
```

Vérifie si une chaîne contient une sous-chaîne.

```air
string.contains("bonjour", "jour")  # => true
```

## `starts_with`

```air
fun starts_with(s: String, prefix: String) -> Bool
```

Vérifie si une chaîne commence par un préfixe.

```air
string.starts_with("bonjour", "bon")  # => true
```

## `ends_with`

```air
fun ends_with(s: String, suffix: String) -> Bool
```

Vérifie si une chaîne se termine par un suffixe.

```air
string.ends_with("fichier.air", ".air")  # => true
```

## `upper`

```air
fun upper(s: String) -> String
```

Convertit une chaîne en majuscules.

```air
string.upper("bonjour")  # => "BONJOUR"
```

## `lower`

```air
fun lower(s: String) -> String
```

Convertit une chaîne en minuscules.

```air
string.lower("BONJOUR")  # => "bonjour"
```

## `index_of`

```air
fun index_of(s: String, sub: String) -> Int
```

Retourne la position de la première occurrence d'une sous-chaîne (-1 si absente).

```air
string.index_of("bonjour", "jour")  # => 3
```

## `repeat`

```air
fun repeat(s: String, n: Int) -> String
```

Répète une chaîne n fois.

```air
string.repeat("ab", 3)  # => "ababab"
```

## `reverse`

```air
fun reverse(s: String) -> String
```

Inverse une chaîne.

```air
string.reverse("AirLang")  # => "gnaLriA"
```

## `slice`

```air
fun slice(s: String, start: Int, end: Int) -> String
```

Extrait une sous-chaîne entre les positions start (inclus) et end (exclus).

```air
string.slice("bonjour", 0, 3)  # => "bon"
```

## `length`

```air
fun length(s: String) -> Int
```

Retourne la longueur d'une chaîne en octets.

## `to_int`

```air
fun to_int(s: String) -> Int
```

Convertit une chaîne en entier.

```air
string.to_int("42")  # => 42
```

## `to_float`

```air
fun to_float(s: String) -> Float
```

Convertit une chaîne en flottant.

```air
string.to_float("3.14")  # => 3.14
```
