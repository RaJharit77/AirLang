# Gestion de la mémoire — état et plan (v0.6)

## État actuel

Le runtime alloue (`air_alloc`, `air_realloc`) et **ne libère jamais** : la mémoire est rendue à la
fin du processus. C'est correct pour des programmes courts, mais une boucle qui crée beaucoup de
chaînes, listes ou objets consomme de la mémoire sans limite. Ce n'est pas acceptable pour une 1.0.

## Pourquoi ce n'est pas fait en v0.6

Le comptage de références touche tout le générateur de code : chaque copie de valeur, chaque
sortie de portée, chaque `return`, `break`, `continue`, `?` et chaque `longjmp` de `try/catch`
doit retenir ou relâcher. Le mélanger à d'autres changements rendrait les bugs impossibles à isoler.
Il a donc son propre palier (v0.7), avec les garde-fous ci-dessous.

## Plan v0.7

1. **Valeurs concernées** : `AirStr` (données allouées), `AirList*`, `AirMap*`, `bp_X*`, environnements
   de fermetures. Les littéraux de chaîne restent statiques (compteur « immortel »).
2. **En-tête commun** `{ int32_t rc; }` en tête de chaque objet ; `air_retain(p)` / `air_release(p)`.
   La libération d'une liste/map/objet relâche ses éléments/champs (fonction de destruction par type).
3. **Règles de génération** : une variable locale possède une référence, relâchée en fin de portée ;
   un appel qui renvoie une valeur renvoie une référence « possédée » ; une affectation relâche l'ancienne
   valeur ; un champ ou un élément de liste possède sa référence.
4. **Sorties anticipées** : `return`, `break`, `continue` et `?` relâchent les variables des portées quittées ;
   `try/catch` enregistre dans son cadre la profondeur de la pile de relâchement (comme pour les volatiles).
5. **Cycles** : le comptage ne les libère pas. Choix pour la 1.0 : documenter la limite (un cycle fuit)
   et fournir un champ `weak` plus tard, plutôt que d'ajouter un ramasse-miettes.
6. **Vérification** : mode `AIR_MEM_DEBUG` qui compte allocations/libérations et échoue si elles diffèrent
   en fin de programme ; tous les `tests/programs/*` doivent finir à zéro fuite ; ASan avec `detect_leaks=1`.

## Ce que fait déjà `make sanitize`

ASan/UBSan détectent les accès invalides et comportements indéfinis ; la détection de fuites est
volontairement désactivée tant que la libération n'existe pas.
