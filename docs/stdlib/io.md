# io

Entrées/Sorties fichiers et console.
Import : `import io`

> Généré par `tools/airdoc.rb` depuis `stdlib/io.air` — ne pas modifier à la main.

## `read`

```air
fun read(path: String) -> String
```

Lit un fichier entier et retourne son contenu.

```air
content = io.read("config.json")
```

## `write`

```air
fun write(path: String, content: String) -> Bool
```

Écrit (ou écrase) un fichier. Retourne true si succès.

```air
io.write("output.txt", "Bonjour")
```

## `append`

```air
fun append(path: String, content: String) -> Bool
```

Ajoute du contenu à la fin d'un fichier sans l'écraser.

```air
io.append("log.txt", "nouvelle ligne\n")
```

## `exists`

```air
fun exists(path: String) -> Bool
```

Vérifie si un fichier ou dossier existe.

```air
if io.exists("data.csv") then ... end
```

## `delete`

```air
fun delete(path: String) -> Bool
```

Supprime un fichier. Retourne true si succès.

```air
io.delete("temp.txt")
```

## `lines`

```air
fun lines(path: String) -> List[String]
```

Retourne le contenu d'un fichier sous forme de liste de lignes.

```air
for line in io.lines("data.txt") ... end
```

## `print`

```air
fun print(value: String)
```

Affiche une valeur sur la sortie standard (sans saut de ligne).

## `println`

```air
fun println(value: String)
```

Affiche une valeur avec saut de ligne.

## `input`

```air
fun input(prompt: String) -> String
```

Affiche un prompt et lit une ligne depuis le clavier.

```air
name = io.input("Ton nom : ")
```
