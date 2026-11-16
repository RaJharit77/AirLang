# string

Utilitaires sur les chaînes de caractères (écrits en AirLang).
Import : `import string`
Les méthodes de base (`s.trim()`, `s.split(",")`, `s.slice(a, b)`...) n'ont pas besoin d'import.

> Généré par `tools/airdoc.rb` depuis `stdlib/string.air` — ne pas modifier à la main.

## `is_empty`

```air
fun is_empty(s: String) -> Bool
```

Vrai si la chaîne est vide.

```air
string.is_empty("")  # => true
```

## `repeat`

```air
fun repeat(s: String, n: Int) -> String
```

Répète une chaîne `n` fois.

```air
string.repeat("ab", 3)  # => "ababab"
```

## `pad_left`

```air
fun pad_left(s: String, width: Int, fill: String) -> String
```

Complète à gauche avec `fill` (un caractère) jusqu'à `width` caractères.

```air
string.pad_left("7", 3, "0")  # => "007"
```

## `pad_right`

```air
fun pad_right(s: String, width: Int, fill: String) -> String
```

Complète à droite avec `fill` (un caractère) jusqu'à `width` caractères.

```air
string.pad_right("ab", 4, ".")  # => "ab.."
```

## `reverse`

```air
fun reverse(s: String) -> String
```

Inverse l'ordre des caractères.

```air
string.reverse("abc")  # => "cba"
```

## `capitalize`

```air
fun capitalize(s: String) -> String
```

Met la première lettre en majuscule.

```air
string.capitalize("air")  # => "Air"
```

## `count`

```air
fun count(s: String, part: String) -> Int
```

Compte les occurrences non chevauchantes de `part` (qui ne doit pas être vide).

```air
string.count("a,b,c", ",")  # => 2
```
