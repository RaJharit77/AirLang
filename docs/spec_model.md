# AirLang — Spécification du Langage v0.1

> *Simple comme respirer. Léger comme l'air.*

---

## 1. Philosophie AirLang

AirLang est construit autour de 5 principes fondateurs :

1. **Lisible avant tout** — le code se lit presque comme du français/anglais naturel
2. **Zéro magie cachée** — ce que tu vois est ce qui se passe
3. **Léger à compiler** — transpilation vers C, pas de VM, pas de runtime lourd
4. **OOP humain** — les objets sont des "blueprints" simples, l'héritage est optionnel
5. **Erreurs claires** — les messages d'erreur sont rédigés pour des humains, pas des compilateurs

### Problèmes résolus vs langages actuels

| Problème actuel | Solution AirLang |
|---|---|
| Python : lent, GIL, typage silencieux | Typage progressif explicite + compilation native |
| JavaScript : `undefined`, `this`, prototype hell | Pas de `this` implicite, pas de coercition, scopes clairs |
| Java : verbosité excessive | 10x moins de boilerplate, inférence de types |
| C/C++ : gestion mémoire dangereuse | Ownership simple (borrow-lite), pas de pointeurs nus |
| Go : manque d'expressivité OOP | OOP propre avec `blueprint` + `trait` |

---

## 2. Syntaxe de Base

### 2.1 Variables

```air
# Déclaration simple (type inféré)
name = "Alice"
age  = 30
score = 98.5

# Déclaration avec type explicite
name: String = "Alice"
age:  Int    = 30

# Constante (immuable)
const MAX_USERS = 1000
const PI: Float = 3.14159

# Variable nulle (optionnelle)
data: String? = null
```

### 2.2 Types de base

| Type AirLang | Description | Exemple |
|---|---|---|
| `Int` | Entier 64 bits | `42` |
| `Float` | Flottant 64 bits | `3.14` |
| `Bool` | Booléen | `true` / `false` |
| `String` | Chaîne UTF-8 | `"Bonjour"` |
| `Char` | Caractère unique | `'a'` |
| `Null` | Absence de valeur | `null` |
| `List[T]` | Liste typée | `[1, 2, 3]` |
| `Map[K, V]` | Dictionnaire | `{"a": 1}` |
| `T?` | Type optionnel | `String?` |

### 2.3 Structures de contrôle

```air
# If / else (pas de parenthèses requises)
if age >= 18
    print("Adulte")
else if age >= 13
    print("Adolescent")
else
    print("Enfant")
end

# Unless (syntaxe lisible négative)
unless connected
    print("Pas de connexion")
end

# While
while count < 10
    count = count + 1
end

# For classique
for i in 0..10
    print(i)
end

# For sur une liste
for user in users
    print(user.name)
end

# For avec index
for i, user in users
    print(i, user.name)
end

# Match (pattern matching simple)
match status
    "active"   => print("En ligne")
    "away"     => print("Absent")
    "offline"  => print("Hors ligne")
    _          => print("Inconnu")
end
```

### 2.4 Fonctions

```air
# Fonction simple
fun greet(name: String) -> String
    return "Bonjour, " + name
end

# Inférence du type de retour
fun add(a: Int, b: Int)
    return a + b
end

# Paramètres avec valeurs par défaut
fun connect(host: String, port: Int = 3000)
    # ...
end

# Fonction anonyme (lambda)
double = fun(x: Int) => x * 2

# Appel
result = double(5)   # => 10

# Fonctions d'ordre supérieur
numbers = [1, 2, 3, 4, 5]
doubled = numbers.map(fun(x) => x * 2)
evens   = numbers.filter(fun(x) => x % 2 == 0)
total   = numbers.reduce(0, fun(acc, x) => acc + x)
```

---

## 3. OOP — Blueprints et Traits

### 3.1 Blueprint (équivalent de classe)

```air
blueprint Person
    # Champs
    name: String
    age:  Int
    email: String? = null

    # Constructeur automatique via `new`
    # Person.new(name: "Alice", age: 30)

    # Méthode
    fun greet()
        print("Je m'appelle " + name)
    end

    fun birthday()
        age = age + 1
    end

    fun is_adult() -> Bool
        return age >= 18
    end
end
```

### 3.2 Héritage

```air
blueprint Employee extends Person
    company: String
    salary:  Float

    fun describe()
        print(name + " travaille chez " + company)
    end

    # Override
    fun greet()
        print("Employé : " + name + " @ " + company)
    end
end
```

### 3.3 Traits (interfaces légères)

```air
trait Printable
    fun to_string() -> String
end

trait Saveable
    fun save()
    fun load()
end

blueprint Report implements Printable, Saveable
    title: String
    content: String

    fun to_string() -> String
        return "[" + title + "] " + content
    end

    fun save()
        # écriture fichier...
    end

    fun load()
        # lecture fichier...
    end
end
```

### 3.4 Instanciation et usage

```air
# Création d'instance
alice = Person.new(name: "Alice", age: 25)
bob   = Employee.new(name: "Bob", age: 30, company: "AirCorp", salary: 3500.0)

# Accès aux champs
print(alice.name)
alice.birthday()

# Méthodes chainées
result = users
    .filter(fun(u) => u.is_adult())
    .map(fun(u) => u.name)
    .join(", ")
```

---

## 4. Gestion des Erreurs

```air
# Résultat typé : Ok ou Err
fun divide(a: Float, b: Float) -> Result[Float]
    if b == 0.0
        return Err("Division par zéro")
    end
    return Ok(a / b)
end

# Utilisation
result = divide(10.0, 2.0)

match result
    Ok(value) => print("Résultat : " + value)
    Err(msg)  => print("Erreur : " + msg)
end

# Propagation d'erreur avec ?
fun compute(x: Float) -> Result[Float]
    value = divide(x, 2.0)?   # Propage l'erreur si Err
    return Ok(value * 3.0)
end

# Try/catch pour les cas exceptionnels
try
    file = io.read("data.txt")
catch err: IOError
    print("Impossible de lire : " + err.message)
end
```

---

## 5. Modules et Imports

```air
# Import d'un module standard
import io
import math
import net.http as http

# Import d'un fichier local
import "./utils/formatter"
import "./models/user"    as User

# Usage
data = io.read("config.json")
response = http.get("https://api.example.com/data")
user = User.new(name: "Alice", age: 25)
```

### Structure d'un module

```air
# fichier: utils/formatter.air

# Exporter une fonction
export fun format_date(date: String) -> String
    # ...
end

# Exporter un blueprint
export blueprint Config
    debug: Bool = false
    max_connections: Int = 100
end
```

---

## 6. Typage Progressif (Gradual Typing)

AirLang supporte deux modes :

```air
# Mode dynamique (rapide à écrire, bon pour prototypage)
data = fetch_data()
result = process(data)

# Mode statique (production, sécurité, performance)
data: Map[String, Any] = fetch_data()
result: List[String]   = process(data)

# Annoter une fonction pour la rendre stricte
@strict
fun calculate(x: Float, y: Float) -> Float
    return x * y
end
```

---

## 7. Syntaxe Complète — Exemple Réel

```air
# Application de gestion d'utilisateurs
import io
import net.http as http

blueprint User
    id:    Int
    name:  String
    email: String
    active: Bool = true

    fun display()
        status = if active then "✓" else "✗" end
        print("[" + status + "] " + name + " <" + email + ">")
    end

    fun deactivate()
        active = false
    end
end

blueprint UserService
    users: List[User] = []

    fun add(user: User)
        users.append(user)
    end

    fun find_by_email(email: String) -> User?
        for user in users
            if user.email == email
                return user
            end
        end
        return null
    end

    fun active_users() -> List[User]
        return users.filter(fun(u) => u.active)
    end

    fun report()
        print("=== Rapport Utilisateurs ===")
        print("Total    : " + users.length())
        print("Actifs   : " + active_users().length())
        print("")
        for user in users
            user.display()
        end
    end
end

# Point d'entrée
fun main()
    service = UserService.new()

    service.add(User.new(id: 1, name: "Alice",   email: "alice@mail.com"))
    service.add(User.new(id: 2, name: "Bob",     email: "bob@mail.com"))
    service.add(User.new(id: 3, name: "Charlie", email: "charlie@mail.com"))

    bob = service.find_by_email("bob@mail.com")
    if bob != null
        bob.deactivate()
    end

    service.report()
end

main()
```

---

## 8. AirStd — Bibliothèque Standard

Tous les modules sont opt-in (zéro import automatique = zéro bloat).

| Module | Fonctions clés |
|---|---|
| `io` | `read`, `write`, `append`, `exists`, `delete` |
| `string` | `split`, `join`, `trim`, `replace`, `contains`, `upper`, `lower` |
| `list` | `map`, `filter`, `reduce`, `sort`, `unique`, `flatten` |
| `map` | `keys`, `values`, `merge`, `has`, `delete` |
| `math` | `abs`, `pow`, `sqrt`, `floor`, `ceil`, `round`, `random` |
| `net.http` | `get`, `post`, `put`, `delete`, `parse_json` |
| `time` | `now`, `format`, `parse`, `diff`, `sleep` |
| `os` | `args`, `env`, `exit`, `exec` |
| `json` | `parse`, `stringify` |

---

## 9. Roadmap — 4 Semaines

### Semaine 1 — Fondations (Compilateur Frontend)
**Objectif : lire et parser du code AirLang**

- [ ] Définir la grammaire formelle (EBNF ou PEG)
- [ ] Implémenter le Lexer (tokenisation)
  - Mots-clés : `fun`, `blueprint`, `trait`, `import`, `export`, `return`, `if`, `else`, `for`, `while`, `match`, `end`, `const`, `null`, `true`, `false`
  - Littéraux : String, Int, Float, Bool
  - Opérateurs : `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `not`
- [ ] Implémenter le Parser (AST)
  - Déclarations de variables
  - Définitions de fonctions
  - Structures de contrôle
  - Expressions
- [ ] Afficher l'AST en debug (JSON ou pretty-print)
- [ ] Tests unitaires du Lexer + Parser (20+ cas)

**Livrable S1 :** `airc file.air --ast` affiche l'arbre syntaxique

---

### Semaine 2 — Sémantique et Type Checker
**Objectif : valider le code et inférer les types**

- [ ] Table des symboles (scoping)
- [ ] Résolution des noms de variables et fonctions
- [ ] Inférence de types (règles basiques)
- [ ] Validation des types pour les opérations
- [ ] Support des blueprints dans le type checker
- [ ] Messages d'erreur humains (avec numéro de ligne et suggestion)
- [ ] Support des types optionnels (`T?`)
- [ ] Support de `Result[T]`

**Livrable S2 :** `airc file.air --check` valide le programme et liste les erreurs claires

---

### Semaine 3 — Génération de Code C
**Objectif : produire un exécutable réel**

- [ ] Générateur C depuis l'AST
  - Variables → déclarations C
  - Fonctions → fonctions C
  - Blueprints → structs C + fonctions préfixées
  - Listes → tableaux dynamiques simples (lib interne)
  - Maps → table de hachage simple (lib interne)
- [ ] AirRuntime minimal en C (allocations, strings, listes)
- [ ] Intégration GCC/Clang pour compilation finale
- [ ] Support de `io.print`, `io.read`
- [ ] Hello World qui compile et tourne ✓
- [ ] Programme UserService qui compile et tourne ✓

**Livrable S3 :** `airc file.air -o app && ./app` produit un binaire fonctionnel

---

### Semaine 4 — Tooling et Polissage
**Objectif : expérience développeur utilisable**

- [ ] REPL interactif (`air repl`)
- [ ] Formatter de code (`airfmt file.air`)
- [ ] Erreurs de compilation enrichies (contexte, suggestion)
- [ ] AirStd modules de base : `io`, `string`, `list`, `math`
- [ ] Documentation auto-générée depuis les commentaires `##`
- [ ] Package minimal : `project.air` (nom, version, dépendances locales)
- [ ] README + exemples de code
- [ ] 3 programmes exemples complets (todo-list, calculatrice, mini-serveur)

**Livrable S4 :** AirLang v0.1 utilisable, documenté, avec CLI complet

---

## 10. Stack Technique Recommandée

### Option A — Compilateur en Python (démarrage ultra-rapide)
- Python 3.11+ pour le compilateur
- `lark` ou `PLY` pour le parser
- Génération de C → compilation via subprocess GCC
- **Avantage :** très rapide à prototyper, facile à modifier
- **Inconvénient :** compilateur lent lui-même (acceptable en S1-S2)

### Option B — Compilateur en Go (production-ready)
- Go 1.22+ pour le compilateur
- Parser écrit à la main (recursive descent)
- Génération de C directement
- **Avantage :** binaire unique, rapide, facile à distribuer
- **Recommandé pour aller loin**

### Option C — Compilateur en Rust (performance max)
- Rust + `pest` ou `nom` pour le parsing
- **Avantage :** ultra-rapide, sécurité mémoire garantie
- **Inconvénient :** courbe d'apprentissage Rust

**Recommandation : commencer avec Python (S1-S2) puis migrer vers Go (S3-S4).**

---

## 11. Structure de Fichiers du Projet

```
airlang/
├── compiler/
│   ├── lexer.py          # Tokenisation
│   ├── parser.py         # Parsing → AST
│   ├── ast_nodes.py      # Définitions des nœuds AST
│   ├── type_checker.py   # Vérification de types
│   ├── codegen_c.py      # Génération de code C
│   └── errors.py         # Messages d'erreurs humains
├── runtime/
│   ├── air_runtime.h     # Runtime C minimal
│   ├── air_runtime.c     # Implémentation runtime
│   └── air_stdlib.c      # Bibliothèque standard de base
├── stdlib/
│   ├── io.air            # Module io (wrapper)
│   ├── string.air        # Module string
│   ├── list.air          # Module list
│   └── math.air          # Module math
├── examples/
│   ├── hello.air
│   ├── todo.air
│   └── calculator.air
├── tests/
│   ├── test_lexer.py
│   ├── test_parser.py
│   └── test_codegen.py
├── docs/
│   └── spec.md           # Ce document
├── airc                  # CLI compilateur (entry point)
├── airfmt                # Formatter
└── project.air           # Fichier projet AirLang
```

---

## 12. Commentaires et Documentation

```air
# Commentaire simple

## Documentation d'une fonction (générable automatiquement)
## Divise deux nombres flottants.
## Retourne une erreur si b vaut zéro.
fun divide(a: Float, b: Float) -> Result[Float]
    if b == 0.0
        return Err("Division par zéro")
    end
    return Ok(a / b)
end
```

---

## 13. Mots Réservés

```
air       and       as        blueprint   break     catch
const     continue  else      end         export    extends
false     for       fun       if          implements import
in        match     new       not         null      or
return    strict    then      trait       true      try
unless    while     _
```

---

## 14. Opérateurs

| Opérateur | Description |
|---|---|
| `+` `-` `*` `/` `%` | Arithmétiques |
| `==` `!=` `<` `>` `<=` `>=` | Comparaison |
| `and` `or` `not` | Logiques (pas `&&`, `||`, `!`) |
| `=` | Affectation |
| `+=` `-=` `*=` `/=` | Affectation composée |
| `..` | Range (ex: `0..10`) |
| `?` | Propagation d'erreur |
| `=>` | Lambda / match case |
| `->` | Type de retour |
| `:` | Annotation de type |

---

*AirLang v0.1 — Document de spécification*
*Créé le 2026-06-07*
