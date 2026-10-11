# AirLang

> Simple comme respirer. Léger comme l'air.

AirLang est un langage lisible, à typage progressif, qui se compile en C puis en binaire natif (gcc).
Fichiers sources : `.air`. État actuel : **v0.2 (pré-stable)**.

## Utilisation

```bash
python3 -m compiler run examples/hello.air     # compile et exécute
python3 -m compiler check examples/hello.air   # analyse sans compiler
python3 -m compiler build examples/hello.air   # produit un binaire
```

Prérequis : Python 3.10+, gcc. Tests : `python3 -m pytest`.

## Exemple

```air
fun main()
    name = "Monde"
    print("Bonjour, {name} !")
end
main()
```

AirLang ne convertit jamais implicitement : `"n=" + 1` est une erreur, utilisez `"n={x}"`.

## Documentation

- [Spécification](docs/spec.md)
- [Audit et feuille de route vers 1.0](ROADMAP.md)

## Ce qui fonctionne en v0.2

Variables, fonctions, `if`/`while`/`for`, blueprints, chaînes interpolées, erreurs avec ligne, colonne et aide.
Listes, maps, lambdas, `Result`, `match`, `try/catch` et modules arrivent en v0.3 à v0.5.
