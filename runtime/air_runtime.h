/*
 * air_runtime.h — AirLang Runtime Minimal v0.1
 * Inclus automatiquement dans tout programme compilé AirLang.
 * Zéro dépendance externe, uniquement la libc standard.
 */

#ifndef AIR_RUNTIME_H
#define AIR_RUNTIME_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ── Types de base ──────────────────────────────────────────────────────────── */

/* String AirLang : pointeur + longueur (UTF-8, null-terminated) */
typedef struct {
    char*  data;
    size_t len;
} AirStr;

/* Valeur générique (Any) */
typedef void* AirVal;

/* Résultat typé : Ok ou Err */
typedef struct {
    bool    is_ok;
    AirVal  value;     /* Ok: valeur, Err: message d'erreur (AirStr*) */
} AirResult;

/* ── Listes dynamiques ───────────────────────────────────────────────────────── */

/* Les éléments sont stockés PAR VALEUR dans un tableau contigu (elem_size octets chacun) :
 * List[Int] → int64_t, List[Float] → double, List[String] → AirStr, List[Blueprint] → pointeurs. */
typedef struct AirList {
    char*    data;
    size_t   len;
    size_t   cap;
    size_t   elem_size;
} AirList;

/* Genre d'un élément : sert à comparer (contains, sort) et à afficher (print). */
enum { AIR_K_INT = 0, AIR_K_FLOAT = 1, AIR_K_BOOL = 2, AIR_K_STRING = 3, AIR_K_OBJ = 4 };

/* ── Maps (table de hachage simple) ────────────────────────────────────────── */

/* Map[String, V] : clés String, valeurs par valeur (value_size octets), ordre d'insertion conservé.
 * La valeur est stockée juste après l'entrée en mémoire. */
typedef struct AirMapEntry {
    AirStr              key;
    size_t              hash;
    struct AirMapEntry* next;
} AirMapEntry;

typedef struct AirMap {
    AirMapEntry** buckets;
    size_t        bucket_count;
    AirMapEntry** order;        /* entrées dans l'ordre d'insertion */
    size_t        order_cap;
    size_t        len;
    size_t        value_size;
} AirMap;

/* ── Erreurs ────────────────────────────────────────────────────────────────── */

typedef struct {
    AirStr  message;
    int     code;
} AirError;

/* ── Constructeurs de strings ─────────────────────────────────────────────── */

AirStr  air_str(const char* s);
AirStr  air_str_n(const char* s, size_t n);
AirStr  air_str_copy(AirStr s);
void    air_str_free(AirStr* s);
bool    air_str_eq(AirStr a, AirStr b);
AirStr  air_str_concat(AirStr a, AirStr b);
AirStr  air_str_upper(AirStr s);
AirStr  air_str_lower(AirStr s);
AirStr  air_str_trim(AirStr s);
bool    air_str_contains(AirStr haystack, AirStr needle);
AirStr  air_str_replace(AirStr s, AirStr from, AirStr to);
AirList* air_str_split(AirStr s, AirStr delim);
int64_t air_str_length(AirStr s);

/* Conversion : concaténation intelligente (Int → String, Float → String) */
AirStr  air_concat(AirStr a, AirStr b);
AirStr  air_int_to_str(int64_t n);
AirStr  air_float_to_str(double f);
AirStr  air_bool_to_str(bool b);
int64_t air_str_to_int(AirStr s);     /* panic si la chaîne n'est pas un entier */
double  air_str_to_float(AirStr s);   /* panic si la chaîne n'est pas un nombre */
bool    air_string_starts_with(AirStr s, AirStr prefix);
bool    air_string_ends_with(AirStr s, AirStr suffix);

/* Littéral de chaîne : pas d'allocation (stockage statique, ne jamais libérer) */
#define AIR_STR_LIT(s) ((AirStr){ (char*)(s), sizeof(s) - 1 })

/* Division/modulo entiers avec garde division par zéro */
static inline int64_t air_idiv(int64_t a, int64_t b) {
    if (b == 0) { fflush(stdout); fprintf(stderr, "\nErreur d'exécution : division par zéro\n"); exit(1); }
    return a / b;
}
static inline int64_t air_imod(int64_t a, int64_t b) {
    if (b == 0) { fflush(stdout); fprintf(stderr, "\nErreur d'exécution : modulo par zéro\n"); exit(1); }
    return a % b;
}

/* ── Erreurs d'exécution ────────────────────────────────────────────────────── */

/* Affiche « Erreur d'exécution : ... » sur stderr puis quitte avec le code 1. */
void air_runtime_error(const char* fmt, ...) __attribute__((noreturn, format(printf, 1, 2)));

/* ── Listes ─────────────────────────────────────────────────────────────────── */

AirList* air_list_new(size_t elem_size);
AirList* air_list_from(const void* items, size_t n, size_t elem_size);
void     air_list_push(AirList* l, const void* item);
void*    air_list_at(AirList* l, int64_t index);           /* vérifie les bornes */
void*    air_list_first_ptr(AirList* l);
void*    air_list_last_ptr(AirList* l);
void     air_list_pop_into(AirList* l, void* out);
void     air_list_remove_at_into(AirList* l, int64_t index, void* out);
void     air_list_clear(AirList* l);
int64_t  air_list_length(AirList* l);
AirList* air_list_reversed(AirList* l);                    /* nouvelle liste */
AirList* air_list_sorted(AirList* l, int kind);            /* nouvelle liste */
int64_t  air_list_index_of(AirList* l, const void* item, int kind);   /* -1 si absent */
AirStr   air_list_join(AirList* l, AirStr sep);            /* List[String] */
AirStr   air_list_to_str(AirList* l, int kind);
void     air_list_free(AirList* l);

/* Accès typés (T = type C de l'élément). `AIR_LIST_AT` est une lvalue : l[i] = v fonctionne. */
#define AIR_LIST_AT(T, l, i)        (*(T*)air_list_at((l), (i)))
#define AIR_LIST_FIRST(T, l)        (*(T*)air_list_first_ptr(l))
#define AIR_LIST_LAST(T, l)         (*(T*)air_list_last_ptr(l))
#define AIR_LIST_PUSH(T, l, v)      do { T _air_pv = (v); air_list_push((l), &_air_pv); } while (0)
#define AIR_LIST_POP(T, l)          ({ T _air_o; air_list_pop_into((l), &_air_o); _air_o; })
#define AIR_LIST_REMOVE_AT(T, l, i) ({ T _air_o; air_list_remove_at_into((l), (i), &_air_o); _air_o; })
#define AIR_LIST_INDEX_OF(T, l, v, k) ({ T _air_cv = (v); air_list_index_of((l), &_air_cv, (k)); })
#define AIR_LIST_CONTAINS(T, l, v, k) (AIR_LIST_INDEX_OF(T, l, v, k) >= 0)

/* ── Maps ───────────────────────────────────────────────────────────────────── */

AirMap*  air_map_new(size_t value_size);
AirMap*  air_map_from(const AirStr* keys, const void* values, size_t n, size_t value_size);
void*    air_map_find(AirMap* m, AirStr key);              /* NULL si absente */
void*    air_map_get_ptr(AirMap* m, AirStr key);           /* erreur d'exécution si absente */
void*    air_map_slot(AirMap* m, AirStr key);              /* crée l'entrée (à zéro) si absente */
bool     air_map_has(AirMap* m, AirStr key);
void     air_map_delete(AirMap* m, AirStr key);
void     air_map_clear(AirMap* m);
int64_t  air_map_length(AirMap* m);
AirList* air_map_keys(AirMap* m);                          /* List[String] */
AirList* air_map_values(AirMap* m);
AirStr   air_map_to_str(AirMap* m, int value_kind);
void     air_map_free(AirMap* m);

#define AIR_MAP_AT(T, m, k)          (*(T*)air_map_get_ptr((m), (k)))
#define AIR_MAP_SLOT(T, m, k)        (*(T*)air_map_slot((m), (k)))
#define AIR_MAP_GET_OR(T, m, k, d)   ({ T* _air_mp = (T*)air_map_find((m), (k)); _air_mp ? *_air_mp : (d); })

/* ── Result ──────────────────────────────────────────────────────────────────── */

AirResult air_ok(AirVal value);
AirResult air_err(const char* message);
bool      air_is_ok(AirResult r);
AirVal    air_unwrap(AirResult r);   /* Panic si Err */

/* ── I/O ─────────────────────────────────────────────────────────────────────── */

void    air_print(AirStr s);
void    air_print_int(int64_t n);
void    air_print_float(double f);
void    air_print_bool(bool b);
AirStr  air_input(AirStr prompt);
AirResult air_file_read(AirStr path);
AirResult air_file_write(AirStr path, AirStr content);
AirResult air_file_append(AirStr path, AirStr content);
bool    air_file_exists(AirStr path);

/* ── Mathématiques ───────────────────────────────────────────────────────────── */

int64_t air_abs_int(int64_t n);
double  air_abs_float(double f);
double  air_pow(double base, double exp);
double  air_sqrt(double n);
int64_t air_floor(double n);
int64_t air_ceil(double n);
int64_t air_round(double n);
double  air_random(void);   /* [0.0, 1.0) */

/* ── Égalité générique ─────────────────────────────────────────────────────── */

bool air_eq(AirVal a, AirVal b);

/* ── Macros utilitaires ─────────────────────────────────────────────────────── */

/* Range : for i in 0..10 */
#define AIR_FOREACH(list, var) \
    for (size_t _i_##var = 0, _done_##var = 0; _i_##var < (list)->len && !_done_##var; _i_##var++)

/* Try/Catch léger (via setjmp — Semaine 3) */
#define AIR_TRY        /* placeholder */
#define AIR_CATCH(T,e) if (0) /* placeholder */

/* Unwrap Result ou panic */
#define AIR_TRY_UNWRAP(r) (air_is_ok(r) ? air_unwrap(r) : (air_panic(#r), NULL))

/* Panic */
#define air_panic(msg) do { \
    fflush(stdout); fprintf(stderr, "\n✘ AirLang Panic : %s\n  ligne %s:%d\n", msg, __FILE__, __LINE__); \
    exit(1); \
} while(0)

/* ── Mémoire ─────────────────────────────────────────────────────────────────── */

void* air_alloc(size_t size);
void* air_realloc(void* ptr, size_t size);
void  air_free(void* ptr);

#endif /* AIR_RUNTIME_H */
