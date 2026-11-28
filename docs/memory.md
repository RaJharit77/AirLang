# Gestion de la mémoire (v0.7)

## Principe : ramasse-miettes conservatif

Depuis la v0.7, la mémoire des programmes AirLang est récupérée automatiquement. Le runtime
(`runtime/air_runtime.c`) contient un ramasse-miettes **conservatif à marquage et balayage** :

1. Toute allocation (`air_alloc`, `air_alloc_atomic`, `air_realloc`) reçoit un petit en-tête et est inscrite
   dans une table de blocs.
2. Quand plus de `max(8 Mo, mémoire vivante)` octets ont été alloués depuis la dernière collecte, le runtime
   trie la table par adresse, puis **marque** tout bloc atteignable depuis les racines :
   la pile C (registres inclus, via `__builtin_unwind_init` + `setjmp`) et les données globales (`.data`/`.bss`).
   Les blocs marqués sont parcourus mot par mot. Un mot qui ressemble à une adresse **dans** un bloc
   (adresse intérieure ou juste après la fin comprise) le garde en vie.
3. Les blocs non marqués sont libérés.

Le texte (données de chaînes) est alloué « atomique » : il n'est jamais parcouru.

## Pourquoi pas le comptage de références prévu au départ

Le plan v0.6 était un comptage de références. Il imposait de retenir/relâcher à chaque copie, sortie de
portée, `return`, `break`, `continue`, `?` et `longjmp` de `try/catch`, dans tout le générateur de code, et
il ne libère pas les cycles. Le ramasse-miettes conservatif :

- ne modifie **aucune ligne** du code généré (variables, listes, maps, fermetures, optionnels, `Result`) ;
- libère aussi les **cycles** ;
- ne peut pas libérer trop tôt tant que le C n'a pas de pointeur « caché » (le code généré n'en a pas). Un faux
  positif (un entier qui ressemble à une adresse) retarde seulement une libération.

Contrepartie : les pauses de collecte (marquage de tout le tas) et un peu de mémoire retenue à tort.

## Limites

- **Linux + gcc/clang uniquement** (racines globales via `__data_start`/`_end`). Ailleurs le GC reste inactif et
  le programme se comporte comme avant la v0.7 : la mémoire est rendue à la fin du processus.
- Mono-thread (AirLang n'a pas de threads).
- Pas de collecte incrémentale : une collecte parcourt tout le tas vivant.
- Les exécutables ASan utilisent `detect_stack_use_after_return=0` (la « fausse pile » d'ASan est sur le tas et
  masquerait des pointeurs au GC) ; c'est configuré dans le runtime via `__asan_default_options`.

## Réglages (variables d'environnement)

| Variable | Effet |
|---|---|
| `AIR_GC=0` | désactive le GC |
| `AIR_GC_STATS=1` | affiche sur stderr : collectes, allocations, octets alloués/libérés, pic, vivant final |
| `AIR_GC_STRESS=N` | collecte toutes les N allocations (`1` = à chaque allocation) — pour les tests |
| `AIR_GC_THRESHOLD=octets` | seuil de la première collecte |

## Vérification

- `tests/test_v07.py` : mémoire récupérée (> 50 % libérée, pic borné), cycles libérés, résultats identiques
  avec `AIR_GC_STRESS=1` pour fermetures, `try/catch`, `Result`/`match`, optionnels, maps, objets, et pour tous
  les `tests/programs/*.air`.
- `make sanitize` et `AIR_GC_STRESS=1 make sanitize` : ASan + UBSan, détectent une libération trop précoce.
- La suite complète a aussi été exécutée avec `AIR_GC_STRESS=1`.
