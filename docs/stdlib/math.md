# math

Fonctions mathématiques.
Import : `import math`

> Généré par `tools/airdoc.rb` depuis `stdlib/math.air` — ne pas modifier à la main.

## `abs`

```air
fun abs(x: Float) -> Float
```

Valeur absolue d'un nombre.

```air
math.abs(-5.0)  # => 5.0
```

## `pow`

```air
fun pow(base: Float, exp: Float) -> Float
```

x élevé à la puissance e.

```air
math.pow(2.0, 10.0)  # => 1024.0
```

## `sqrt`

```air
fun sqrt(x: Float) -> Float
```

Racine carrée.

```air
math.sqrt(16.0)  # => 4.0
```

## `floor`

```air
fun floor(x: Float) -> Float
```

Arrondi vers le bas (plancher).

```air
math.floor(3.7)  # => 3.0
```

## `ceil`

```air
fun ceil(x: Float) -> Float
```

Arrondi vers le haut (plafond).

```air
math.ceil(3.2)  # => 4.0
```

## `round`

```air
fun round(x: Float) -> Float
```

Arrondi au plus proche.

```air
math.round(3.5)  # => 4.0
```

## `log`

```air
fun log(x: Float) -> Float
```

Logarithme naturel (base e).

## `log2`

```air
fun log2(x: Float) -> Float
```

Logarithme en base 2.

## `log10`

```air
fun log10(x: Float) -> Float
```

Logarithme en base 10.

## `sin`

```air
fun sin(x: Float) -> Float
```

Sinus (en radians).

## `cos`

```air
fun cos(x: Float) -> Float
```

Cosinus (en radians).

## `tan`

```air
fun tan(x: Float) -> Float
```

Tangente (en radians).

## `atan2`

```air
fun atan2(y: Float, x: Float) -> Float
```

Arctangente2 (angle entre l'axe x et le point (x, y)).

## `min`

```air
fun min(a: Float, b: Float) -> Float
```

Retourne le plus petit des deux nombres.

```air
math.min(3.0, 7.0)  # => 3.0
```

## `max`

```air
fun max(a: Float, b: Float) -> Float
```

Retourne le plus grand des deux nombres.

```air
math.max(3.0, 7.0)  # => 7.0
```

## `clamp`

```air
fun clamp(value: Float, lo: Float, hi: Float) -> Float
```

Limite une valeur dans un intervalle [lo, hi].

```air
math.clamp(150.0, 0.0, 100.0)  # => 100.0
```

## `random`

```air
fun random() -> Float
```

Nombre aléatoire entre 0.0 (inclus) et 1.0 (exclus).

```air
dice = math.random()
```

## `random_int`

```air
fun random_int(min: Int, max: Int) -> Int
```

Entier aléatoire dans l'intervalle [min, max] (inclus).

```air
d6 = math.random_int(1, 6)
```

## `to_rad`

```air
fun to_rad(degrees: Float) -> Float
```

Convertit des degrés en radians.

```air
math.to_rad(180.0)  # => 3.14159...
```

## `to_deg`

```air
fun to_deg(radians: Float) -> Float
```

Convertit des radians en degrés.

```air
math.to_deg(math.PI)  # => 180.0
```

## `is_even`

```air
fun is_even(n: Int) -> Bool
```

Vérifie si un entier est pair.

## `is_odd`

```air
fun is_odd(n: Int) -> Bool
```

Vérifie si un entier est impair.

## `gcd`

```air
fun gcd(a: Int, b: Int) -> Int
```

Calcule le plus grand commun diviseur (algorithme d'Euclide).

## `lcm`

```air
fun lcm(a: Int, b: Int) -> Int
```

Calcule le plus petit commun multiple.

## `is_prime`

```air
fun is_prime(n: Int) -> Bool
```

Vérifie si un entier est un nombre premier.
