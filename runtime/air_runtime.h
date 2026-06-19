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

typedef struct AirList {
    AirVal*  items;
    size_t   len;
    size_t   cap;
    size_t   item_size;
} AirList;

/* ── Maps (table de hachage simple) ────────────────────────────────────────── */

typedef struct AirMapEntry {
    AirStr           key;
    AirVal           value;
    struct AirMapEntry* next;
} AirMapEntry;

typedef struct AirMap {
    AirMapEntry** buckets;
    size_t        bucket_count;
    size_t        len;
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

/* ── Listes ─────────────────────────────────────────────────────────────────── */

AirList* air_list_empty(void);
AirList* air_list_of(size_t n, ...);  /* air_list_of(3, val1, val2, val3) */
void     air_list_append(AirList* list, AirVal item);
AirVal   air_list_get(AirList* list, int64_t index);
void     air_list_set(AirList* list, int64_t index, AirVal item);
int64_t  air_list_length(AirList* list);
AirList* air_list_map(AirList* list, AirVal (*fn)(AirVal));
AirList* air_list_filter(AirList* list, bool (*fn)(AirVal));
AirVal   air_list_reduce(AirList* list, AirVal init, AirVal (*fn)(AirVal, AirVal));
AirList* air_list_sort(AirList* list, int (*cmp)(AirVal, AirVal));
AirStr   air_list_join(AirList* list, AirStr sep);
void     air_list_free(AirList* list);

/* ── Maps ───────────────────────────────────────────────────────────────────── */

AirMap*  air_map_empty(void);
void     air_map_set(AirMap* map, AirStr key, AirVal value);
AirVal   air_map_get(AirMap* map, AirStr key);
bool     air_map_has(AirMap* map, AirStr key);
void     air_map_delete(AirMap* map, AirStr key);
int64_t  air_map_length(AirMap* map);
AirList* air_map_keys(AirMap* map);
AirList* air_map_values(AirMap* map);
void     air_map_free(AirMap* map);

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
    fprintf(stderr, "\n✘ AirLang Panic : %s\n  ligne %s:%d\n", msg, __FILE__, __LINE__); \
    exit(1); \
} while(0)

/* ── Mémoire ─────────────────────────────────────────────────────────────────── */

void* air_alloc(size_t size);
void* air_realloc(void* ptr, size_t size);
void  air_free(void* ptr);

#endif /* AIR_RUNTIME_H */
