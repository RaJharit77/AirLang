# AirLang

> Simple comme respirer. Léger comme l'air.

AirLang est un langage lisible, à typage progressif, qui se compile en C puis en binaire natif.
Fichiers sources : `.air`. État actuel : **v0.3 (pré-stable, pas encore la 1.0)**.

## Installation

Prérequis : Python 3.10+ et gcc (ou clang). Rust et Ruby sont **facultatifs** (outils).

```bash
git clone https://github.com/RaJharit77/AirLang.git && cd AirLang
cd tools/air && cargo build --release && cd ../..     # facultatif : la CLI `air` (Rust)
export PATH="$PWD/tools/air/target/release:$PATH"
```

## Utilisation

```bash
air run examples/hello.air        # compile et exécute
air check examples/hello.air      # analyse sans compiler
air build examples/hello.air      # produit un binaire
air fmt examples                  # formate (aligne les champs de blueprint)
air fmt --check examples          # vérifie le format (utile en CI)
```

Sans Rust : `python3 -m compiler run|check|build fichier.air` fait la même chose (sauf `fmt`).

## Un exemple

```air
blueprint Person
    name: String

    fun describe()
        print("Je m'appelle {name}")
    end
end

blueprint Student extends Person
    grades: List[Int]

    fun describe()
        print("{name} a {len(grades)} notes")
    end
end

fun main()
    people: List[Person] = [Person.new(name: "Ana"), Student.new(name: "Ben", grades: [12, 15])]
    for p in people
        p.describe()
    end
end
main()
```

AirLang ne convertit jamais implicitement : `"n=" + 1` est une erreur, utilisez `"n={x}"`.

## Ce qui fonctionne en v0.3

Variables, fonctions, `if` / `unless` / `while` / `for`, `break` / `continue`, `if … then … end` sur une ligne,
chaînes interpolées, **listes et maps typées** (littéraux, indices, méthodes, parcours),
blueprints avec **héritage et redéfinition de méthodes**, erreurs claires (ligne, colonne, extrait, aide).

## Ce qui n'est pas encore là (voir [ROADMAP.md](ROADMAP.md))

- v0.4 : lambdas, `Result` / `Ok` / `Err` / `?`, `match` avec motifs, `try/catch`, traits.
  → `examples/todo.air` et `examples/calculator.air` ne compilent pas encore.
- v0.5 : modules (`import` / `export`), `@native`, bibliothèque standard utilisable.
- Pas encore de libération de la mémoire (comptage de références prévu) : les programmes longs consomment de la mémoire.
- `Int / Int` est une division entière (comme en C) ; `float(x) / y` pour une division décimale.

## Outils

| Outil | Langage | Rôle |
|---|---|---|
| compilateur (`compiler/`) | Python | lexer → parser → type checker → génération de C |
| runtime (`runtime/`) | C | chaînes, listes, maps, erreurs d'exécution |
| `air` (`tools/air/`) | Rust | CLI unique, formateur `air fmt` basé sur les tokens |
| `airdoc` (`tools/airdoc.rb`) | Ruby | génère `docs/stdlib/*.md` depuis les commentaires `##` |

`make help` liste les raccourcis (`make test`, `make docs`, `make fmt`, `make sanitize`).

## Documentation

- [Spécification](docs/spec.md) · [Référence de la stdlib](docs/stdlib/) (disponible à partir de la v0.5)
- [Audit et feuille de route vers 1.0](ROADMAP.md) · [Journal des changements](CHANGELOG.md)
