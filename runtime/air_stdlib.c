/*
 * air_stdlib.c — Bibliothèque Standard AirLang v0.1
 * Implémentation C des modules : io, string, list, math, map, time, os, json
 * Inclus automatiquement lors de la compilation d'un programme AirLang.
 * Zéro dépendance externe — uniquement la libc standard.
 */

#include "air_runtime.h"
#include <stdarg.h>
#include <ctype.h>
#include <time.h>
#include <sys/stat.h>
#include <dirent.h>
#include <errno.h>

#ifdef _WIN32
  #include <windows.h>
  #include <process.h>
  #define AIR_PATH_SEP "\\"
#else
  #include <unistd.h>
  #define AIR_PATH_SEP "/"
#endif


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : io
 * Fonctions : read, write, append, exists, delete, lines, print, println
 * ═══════════════════════════════════════════════════════════════════════════ */

/* io.read(path) -> String
 * Lit un fichier entier et retourne son contenu. */
AirString air_io_read(AirString path) {
    char* cpath = air_str_to_cstr(path);
    FILE* f = fopen(cpath, "rb");
    if (!f) {
        air_free(cpath);
        AIR_PANIC("io.read : impossible d'ouvrir '%s' : %s", cpath, strerror(errno));
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char* buf = (char*)air_alloc(size + 1);
    fread(buf, 1, size, f);
    buf[size] = '\0';
    fclose(f);
    air_free(cpath);
    AirString result = air_str_from_buf(buf, size);
    air_free(buf);
    return result;
}

/* io.write(path, content) -> Bool
 * Écrit (ou écrase) un fichier. Retourne true si succès. */
bool air_io_write(AirString path, AirString content) {
    char* cpath   = air_str_to_cstr(path);
    char* ccontent = air_str_to_cstr(content);
    FILE* f = fopen(cpath, "wb");
    bool ok = false;
    if (f) {
        fwrite(ccontent, 1, content.length, f);
        fclose(f);
        ok = true;
    }
    air_free(cpath);
    air_free(ccontent);
    return ok;
}

/* io.append(path, content) -> Bool
 * Ajoute du contenu à la fin d'un fichier. */
bool air_io_append(AirString path, AirString content) {
    char* cpath    = air_str_to_cstr(path);
    char* ccontent = air_str_to_cstr(content);
    FILE* f = fopen(cpath, "ab");
    bool ok = false;
    if (f) {
        fwrite(ccontent, 1, content.length, f);
        fclose(f);
        ok = true;
    }
    air_free(cpath);
    air_free(ccontent);
    return ok;
}

/* io.exists(path) -> Bool */
bool air_io_exists(AirString path) {
    char* cpath = air_str_to_cstr(path);
    struct stat st;
    bool exists = (stat(cpath, &st) == 0);
    air_free(cpath);
    return exists;
}

/* io.delete(path) -> Bool */
bool air_io_delete(AirString path) {
    char* cpath = air_str_to_cstr(path);
    bool ok = (remove(cpath) == 0);
    air_free(cpath);
    return ok;
}

/* io.lines(path) -> List[String]
 * Retourne les lignes d'un fichier sous forme de liste. */
AirList* air_io_lines(AirString path) {
    AirString content = air_io_read(path);
    return air_str_split(content, air_str_new("\n"));
}

/* io.print(value)  — variante sans saut de ligne */
void air_io_print(AirString s) {
    fwrite(s.data, 1, s.length, stdout);
}

/* io.println(value)  — avec saut de ligne */
void air_io_println(AirString s) {
    fwrite(s.data, 1, s.length, stdout);
    putchar('\n');
}

/* io.input(prompt) -> String
 * Affiche un prompt et lit une ligne depuis stdin. */
AirString air_io_input(AirString prompt) {
    fwrite(prompt.data, 1, prompt.length, stdout);
    fflush(stdout);
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) {
        return air_str_new("");
    }
    size_t len = strlen(buf);
    if (len > 0 && buf[len-1] == '\n') buf[--len] = '\0';
    return air_str_from_buf(buf, len);
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : string
 * Fonctions : split, join, trim, replace, contains, upper, lower,
 *             starts_with, ends_with, index_of, repeat, reverse, pad_left, pad_right
 * ═══════════════════════════════════════════════════════════════════════════ */

/* string.split(s, sep) -> List[String] */
AirList* air_string_split(AirString s, AirString sep) {
    return air_str_split(s, sep);
}

/* string.join(list, sep) -> String */
AirString air_string_join(AirList* parts, AirString sep) {
    if (!parts || parts->length == 0) return air_str_new("");
    size_t total_len = 0;
    for (int64_t i = 0; i < parts->length; i++) {
        AirString* item = (AirString*)parts->items[i];
        total_len += item->length;
        if (i < parts->length - 1) total_len += sep.length;
    }
    char* buf = (char*)air_alloc(total_len + 1);
    size_t pos = 0;
    for (int64_t i = 0; i < parts->length; i++) {
        AirString* item = (AirString*)parts->items[i];
        memcpy(buf + pos, item->data, item->length);
        pos += item->length;
        if (i < parts->length - 1) {
            memcpy(buf + pos, sep.data, sep.length);
            pos += sep.length;
        }
    }
    buf[pos] = '\0';
    AirString result = air_str_from_buf(buf, total_len);
    air_free(buf);
    return result;
}

/* string.trim(s) -> String */
AirString air_string_trim(AirString s) {
    const char* start = s.data;
    const char* end   = s.data + s.length;
    while (start < end && isspace((unsigned char)*start)) start++;
    while (end > start && isspace((unsigned char)*(end-1))) end--;
    return air_str_from_buf(start, (size_t)(end - start));
}

/* string.trim_left(s) -> String */
AirString air_string_trim_left(AirString s) {
    const char* start = s.data;
    const char* end   = s.data + s.length;
    while (start < end && isspace((unsigned char)*start)) start++;
    return air_str_from_buf(start, (size_t)(end - start));
}

/* string.trim_right(s) -> String */
AirString air_string_trim_right(AirString s) {
    const char* start = s.data;
    const char* end   = s.data + s.length;
    while (end > start && isspace((unsigned char)*(end-1))) end--;
    return air_str_from_buf(start, (size_t)(end - start));
}

/* string.replace(s, old, new) -> String */
AirString air_string_replace(AirString s, AirString old, AirString new_s) {
    if (old.length == 0) return s;
    /* Compte les occurrences */
    int count = 0;
    const char* p = s.data;
    const char* end = s.data + s.length;
    while (p + old.length <= end) {
        if (memcmp(p, old.data, old.length) == 0) { count++; p += old.length; }
        else p++;
    }
    if (count == 0) return s;
    size_t new_len = s.length + (size_t)count * (new_s.length - old.length);
    char* buf = (char*)air_alloc(new_len + 1);
    char* out = buf;
    p = s.data;
    while (p < end) {
        if (p + old.length <= end && memcmp(p, old.data, old.length) == 0) {
            memcpy(out, new_s.data, new_s.length);
            out += new_s.length;
            p   += old.length;
        } else {
            *out++ = *p++;
        }
    }
    *out = '\0';
    AirString result = air_str_from_buf(buf, new_len);
    air_free(buf);
    return result;
}

/* string.contains(s, sub) -> Bool */
bool air_string_contains(AirString s, AirString sub) {
    if (sub.length == 0) return true;
    if (sub.length > s.length) return false;
    const char* end = s.data + s.length - sub.length;
    for (const char* p = s.data; p <= end; p++) {
        if (memcmp(p, sub.data, sub.length) == 0) return true;
    }
    return false;
}

/* string.starts_with(s, prefix) -> Bool */
bool air_string_starts_with(AirString s, AirString prefix) {
    if (prefix.length > s.length) return false;
    return memcmp(s.data, prefix.data, prefix.length) == 0;
}

/* string.ends_with(s, suffix) -> Bool */
bool air_string_ends_with(AirString s, AirString suffix) {
    if (suffix.length > s.length) return false;
    return memcmp(s.data + s.length - suffix.length, suffix.data, suffix.length) == 0;
}

/* string.upper(s) -> String */
AirString air_string_upper(AirString s) {
    char* buf = (char*)air_alloc(s.length + 1);
    for (size_t i = 0; i < s.length; i++)
        buf[i] = (char)toupper((unsigned char)s.data[i]);
    buf[s.length] = '\0';
    AirString result = air_str_from_buf(buf, s.length);
    air_free(buf);
    return result;
}

/* string.lower(s) -> String */
AirString air_string_lower(AirString s) {
    char* buf = (char*)air_alloc(s.length + 1);
    for (size_t i = 0; i < s.length; i++)
        buf[i] = (char)tolower((unsigned char)s.data[i]);
    buf[s.length] = '\0';
    AirString result = air_str_from_buf(buf, s.length);
    air_free(buf);
    return result;
}

/* string.index_of(s, sub) -> Int  (-1 si absent) */
int64_t air_string_index_of(AirString s, AirString sub) {
    if (sub.length == 0) return 0;
    if (sub.length > s.length) return -1;
    const char* end = s.data + s.length - sub.length;
    for (const char* p = s.data; p <= end; p++) {
        if (memcmp(p, sub.data, sub.length) == 0)
            return (int64_t)(p - s.data);
    }
    return -1;
}

/* string.repeat(s, n) -> String */
AirString air_string_repeat(AirString s, int64_t n) {
    if (n <= 0 || s.length == 0) return air_str_new("");
    size_t total = s.length * (size_t)n;
    char* buf = (char*)air_alloc(total + 1);
    for (int64_t i = 0; i < n; i++)
        memcpy(buf + i * s.length, s.data, s.length);
    buf[total] = '\0';
    AirString result = air_str_from_buf(buf, total);
    air_free(buf);
    return result;
}

/* string.reverse(s) -> String */
AirString air_string_reverse(AirString s) {
    char* buf = (char*)air_alloc(s.length + 1);
    for (size_t i = 0; i < s.length; i++)
        buf[i] = s.data[s.length - 1 - i];
    buf[s.length] = '\0';
    AirString result = air_str_from_buf(buf, s.length);
    air_free(buf);
    return result;
}

/* string.slice(s, start, end) -> String */
AirString air_string_slice(AirString s, int64_t start, int64_t end_idx) {
    if (start < 0) start = 0;
    if (end_idx < 0 || (size_t)end_idx > s.length) end_idx = (int64_t)s.length;
    if (start >= end_idx) return air_str_new("");
    return air_str_from_buf(s.data + start, (size_t)(end_idx - start));
}

/* string.length(s) -> Int */
int64_t air_string_length(AirString s) {
    return (int64_t)s.length;
}

/* string.to_int(s) -> Int */
int64_t air_string_to_int(AirString s) {
    char* cstr = air_str_to_cstr(s);
    int64_t result = (int64_t)strtoll(cstr, NULL, 10);
    air_free(cstr);
    return result;
}

/* string.to_float(s) -> Float */
double air_string_to_float(AirString s) {
    char* cstr = air_str_to_cstr(s);
    double result = strtod(cstr, NULL);
    air_free(cstr);
    return result;
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : list
 * Fonctions : map, filter, reduce, sort, unique, flatten,
 *             append, prepend, pop, length, get, set, contains, index_of, reverse
 * ═══════════════════════════════════════════════════════════════════════════ */

/* list.length(lst) -> Int */
int64_t air_list_length(AirList* lst) {
    return lst ? lst->length : 0;
}

/* list.get(lst, i) -> Any */
void* air_list_get(AirList* lst, int64_t i) {
    if (!lst) AIR_PANIC("list.get : liste null");
    if (i < 0) i += lst->length;
    if (i < 0 || i >= lst->length)
        AIR_PANIC("list.get : index %lld hors limite [0, %lld)", (long long)i, (long long)lst->length);
    return lst->items[i];
}

/* list.set(lst, i, value) */
void air_list_set(AirList* lst, int64_t i, void* value) {
    if (!lst) AIR_PANIC("list.set : liste null");
    if (i < 0) i += lst->length;
    if (i < 0 || i >= lst->length)
        AIR_PANIC("list.set : index %lld hors limite [0, %lld)", (long long)i, (long long)lst->length);
    lst->items[i] = value;
}

/* list.append(lst, item) */
void air_list_append(AirList* lst, void* item) {
    if (!lst) AIR_PANIC("list.append : liste null");
    air_list_push(lst, item);
}

/* list.prepend(lst, item) */
void air_list_prepend(AirList* lst, void* item) {
    if (!lst) AIR_PANIC("list.prepend : liste null");
    air_list_push(lst, NULL);                   /* Agrandit d'une case */
    memmove(&lst->items[1], &lst->items[0],
            (size_t)(lst->length - 1) * sizeof(void*));
    lst->items[0] = item;
}

/* list.pop(lst) -> Any  (supprime et retourne le dernier élément) */
void* air_list_pop(AirList* lst) {
    if (!lst || lst->length == 0) AIR_PANIC("list.pop : liste vide");
    return lst->items[--lst->length];
}

/* list.pop_front(lst) -> Any */
void* air_list_pop_front(AirList* lst) {
    if (!lst || lst->length == 0) AIR_PANIC("list.pop_front : liste vide");
    void* item = lst->items[0];
    memmove(&lst->items[0], &lst->items[1],
            (size_t)(lst->length - 1) * sizeof(void*));
    lst->length--;
    return item;
}

/* list.contains(lst, item, eq_fn) -> Bool
 * eq_fn : fonction de comparaison (int)(void*, void*) retournant 1 si égaux */
bool air_list_contains(AirList* lst, void* item, int (*eq_fn)(void*, void*)) {
    if (!lst) return false;
    for (int64_t i = 0; i < lst->length; i++) {
        if (eq_fn(lst->items[i], item)) return true;
    }
    return false;
}

/* list.index_of(lst, item, eq_fn) -> Int  (-1 si absent) */
int64_t air_list_index_of(AirList* lst, void* item, int (*eq_fn)(void*, void*)) {
    if (!lst) return -1;
    for (int64_t i = 0; i < lst->length; i++) {
        if (eq_fn(lst->items[i], item)) return i;
    }
    return -1;
}

/* list.reverse(lst) -> List (nouvelle liste) */
AirList* air_list_reverse(AirList* lst) {
    AirList* result = air_list_new();
    if (!lst) return result;
    for (int64_t i = lst->length - 1; i >= 0; i--)
        air_list_push(result, lst->items[i]);
    return result;
}

/* list.slice(lst, start, end) -> List (nouvelle liste) */
AirList* air_list_slice(AirList* lst, int64_t start, int64_t end_idx) {
    AirList* result = air_list_new();
    if (!lst) return result;
    if (start < 0) start = 0;
    if (end_idx < 0 || end_idx > lst->length) end_idx = lst->length;
    for (int64_t i = start; i < end_idx; i++)
        air_list_push(result, lst->items[i]);
    return result;
}

/* list.map(lst, fn) -> List
 * fn : void* (*)(void*)  */
AirList* air_list_map(AirList* lst, void* (*fn)(void*)) {
    AirList* result = air_list_new();
    if (!lst) return result;
    for (int64_t i = 0; i < lst->length; i++)
        air_list_push(result, fn(lst->items[i]));
    return result;
}

/* list.filter(lst, fn) -> List
 * fn : bool (*)(void*)  */
AirList* air_list_filter(AirList* lst, bool (*fn)(void*)) {
    AirList* result = air_list_new();
    if (!lst) return result;
    for (int64_t i = 0; i < lst->length; i++) {
        if (fn(lst->items[i]))
            air_list_push(result, lst->items[i]);
    }
    return result;
}

/* list.reduce(lst, initial, fn) -> Any
 * fn : void* (*)(void* acc, void* item)  */
void* air_list_reduce(AirList* lst, void* initial, void* (*fn)(void*, void*)) {
    void* acc = initial;
    if (!lst) return acc;
    for (int64_t i = 0; i < lst->length; i++)
        acc = fn(acc, lst->items[i]);
    return acc;
}

/* list.sort(lst, cmp_fn)  — tri in-place
 * cmp_fn : int (*)(void*, void*)  retourne <0, 0, >0  */
void air_list_sort(AirList* lst, int (*cmp_fn)(const void*, const void*)) {
    if (!lst || lst->length < 2) return;
    qsort(lst->items, (size_t)lst->length, sizeof(void*), cmp_fn);
}

/* list.unique(lst, eq_fn) -> List (nouvelle liste sans doublons) */
AirList* air_list_unique(AirList* lst, int (*eq_fn)(void*, void*)) {
    AirList* result = air_list_new();
    if (!lst) return result;
    for (int64_t i = 0; i < lst->length; i++) {
        bool found = false;
        for (int64_t j = 0; j < result->length; j++) {
            if (eq_fn(lst->items[i], result->items[j])) { found = true; break; }
        }
        if (!found) air_list_push(result, lst->items[i]);
    }
    return result;
}

/* list.flatten(lst) -> List
 * Aplatit une liste de listes en une liste simple. */
AirList* air_list_flatten(AirList* lst) {
    AirList* result = air_list_new();
    if (!lst) return result;
    for (int64_t i = 0; i < lst->length; i++) {
        AirList* inner = (AirList*)lst->items[i];
        if (inner) {
            for (int64_t j = 0; j < inner->length; j++)
                air_list_push(result, inner->items[j]);
        }
    }
    return result;
}

/* list.concat(a, b) -> List (nouvelle liste) */
AirList* air_list_concat(AirList* a, AirList* b) {
    AirList* result = air_list_new();
    if (a) for (int64_t i = 0; i < a->length; i++) air_list_push(result, a->items[i]);
    if (b) for (int64_t i = 0; i < b->length; i++) air_list_push(result, b->items[i]);
    return result;
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : math
 * Fonctions : abs, pow, sqrt, floor, ceil, round, min, max, clamp,
 *             random, random_int, pi, e
 * ═══════════════════════════════════════════════════════════════════════════ */

/* Constantes */
const double AIR_MATH_PI = 3.14159265358979323846;
const double AIR_MATH_E  = 2.71828182845904523536;

double air_math_abs(double x)           { return fabs(x); }
double air_math_pow(double b, double e) { return pow(b, e); }
double air_math_sqrt(double x)          { return sqrt(x); }
double air_math_floor(double x)         { return floor(x); }
double air_math_ceil(double x)          { return ceil(x); }
double air_math_round(double x)         { return round(x); }
double air_math_log(double x)           { return log(x); }
double air_math_log2(double x)          { return log2(x); }
double air_math_log10(double x)         { return log10(x); }
double air_math_sin(double x)           { return sin(x); }
double air_math_cos(double x)           { return cos(x); }
double air_math_tan(double x)           { return tan(x); }
double air_math_atan2(double y, double x){ return atan2(y, x); }

double air_math_min(double a, double b) { return a < b ? a : b; }
double air_math_max(double a, double b) { return a > b ? a : b; }

double air_math_clamp(double v, double lo, double hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* math.random() -> Float dans [0.0, 1.0) */
double air_math_random(void) {
    static bool seeded = false;
    if (!seeded) { srand((unsigned)time(NULL)); seeded = true; }
    return (double)rand() / ((double)RAND_MAX + 1.0);
}

/* math.random_int(min, max) -> Int dans [min, max] */
int64_t air_math_random_int(int64_t lo, int64_t hi) {
    if (lo > hi) { int64_t tmp = lo; lo = hi; hi = tmp; }
    double r = air_math_random();
    return lo + (int64_t)(r * (double)(hi - lo + 1));
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : map  (table de hachage simple, clés String)
 * Fonctions : new, set, get, has, delete, keys, values, length, merge
 * ═══════════════════════════════════════════════════════════════════════════ */

/* Voir air_runtime.h pour la définition de AirMap / AirMapEntry.
 * Les fonctions air_map_* sont déclarées dans air_runtime.c ;
 * on expose ici les wrappers avec noms stdlib. */

AirMap* air_map_stdlib_new(void)                          { return air_map_new(); }
void    air_map_stdlib_set(AirMap* m, AirString k, void* v){ air_map_set(m, k, v); }
void*   air_map_stdlib_get(AirMap* m, AirString k)         { return air_map_get(m, k); }
bool    air_map_stdlib_has(AirMap* m, AirString k)         { return air_map_has(m, k); }
bool    air_map_stdlib_delete(AirMap* m, AirString k)      { return air_map_delete(m, k); }
int64_t air_map_stdlib_length(AirMap* m)                   { return air_map_length(m); }

AirList* air_map_stdlib_keys(AirMap* m) {
    AirList* lst = air_list_new();
    if (!m) return lst;
    for (int i = 0; i < m->capacity; i++) {
        if (m->entries[i].occupied) {
            AirString* k = (AirString*)air_alloc(sizeof(AirString));
            *k = m->entries[i].key;
            air_list_push(lst, k);
        }
    }
    return lst;
}

AirList* air_map_stdlib_values(AirMap* m) {
    AirList* lst = air_list_new();
    if (!m) return lst;
    for (int i = 0; i < m->capacity; i++) {
        if (m->entries[i].occupied)
            air_list_push(lst, m->entries[i].value);
    }
    return lst;
}

AirMap* air_map_stdlib_merge(AirMap* a, AirMap* b) {
    AirMap* result = air_map_new();
    if (a) for (int i = 0; i < a->capacity; i++)
        if (a->entries[i].occupied) air_map_set(result, a->entries[i].key, a->entries[i].value);
    if (b) for (int i = 0; i < b->capacity; i++)
        if (b->entries[i].occupied) air_map_set(result, b->entries[i].key, b->entries[i].value);
    return result;
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : time
 * Fonctions : now, sleep, format (ISO 8601 basique)
 * ═══════════════════════════════════════════════════════════════════════════ */

/* time.now() -> Int  (timestamp Unix en secondes) */
int64_t air_time_now(void) {
    return (int64_t)time(NULL);
}

/* time.sleep(ms)  — pause en millisecondes */
void air_time_sleep(int64_t ms) {
#ifdef _WIN32
    Sleep((DWORD)ms);
#else
    struct timespec ts;
    ts.tv_sec  = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
#endif
}

/* time.format(timestamp) -> String  (ISO 8601 : "YYYY-MM-DD HH:MM:SS") */
AirString air_time_format(int64_t ts) {
    time_t t = (time_t)ts;
    struct tm* tm_info = localtime(&t);
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", tm_info);
    return air_str_new(buf);
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : os
 * Fonctions : args, env, exit, exec, cwd
 * ═══════════════════════════════════════════════════════════════════════════ */

/* Variables globales pour les arguments CLI (initialisées dans main) */
static int    _air_argc = 0;
static char** _air_argv = NULL;

void air_os_init(int argc, char** argv) {
    _air_argc = argc;
    _air_argv = argv;
}

/* os.args() -> List[String] */
AirList* air_os_args(void) {
    AirList* lst = air_list_new();
    for (int i = 0; i < _air_argc; i++) {
        AirString* s = (AirString*)air_alloc(sizeof(AirString));
        *s = air_str_new(_air_argv[i]);
        air_list_push(lst, s);
    }
    return lst;
}

/* os.env(name) -> String? */
AirString air_os_env(AirString name) {
    char* cname = air_str_to_cstr(name);
    const char* val = getenv(cname);
    air_free(cname);
    return val ? air_str_new(val) : air_str_new("");
}

/* os.exit(code) */
void air_os_exit(int64_t code) {
    exit((int)code);
}

/* os.cwd() -> String */
AirString air_os_cwd(void) {
    char buf[4096];
#ifdef _WIN32
    GetCurrentDirectoryA(sizeof(buf), buf);
#else
    if (!getcwd(buf, sizeof(buf))) buf[0] = '\0';
#endif
    return air_str_new(buf);
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : json
 * Fonctions : stringify (basique), parse (basique — retourne une AirMap)
 * Note : implémentation légère, ne couvre pas tous les cas JSON.
 *        Pour une utilisation en production, utiliser une lib externe.
 * ═══════════════════════════════════════════════════════════════════════════ */

/* json.stringify(value) -> String
 * Convertit un AirString en JSON (ajoute les guillemets et échappe). */
AirString air_json_stringify_string(AirString s) {
    /* Estimation de la taille avec échappements */
    char* buf = (char*)air_alloc(s.length * 2 + 4);
    char* out = buf;
    *out++ = '"';
    for (size_t i = 0; i < s.length; i++) {
        unsigned char c = (unsigned char)s.data[i];
        switch (c) {
            case '"':  *out++ = '\\'; *out++ = '"';  break;
            case '\\': *out++ = '\\'; *out++ = '\\'; break;
            case '\n': *out++ = '\\'; *out++ = 'n';  break;
            case '\r': *out++ = '\\'; *out++ = 'r';  break;
            case '\t': *out++ = '\\'; *out++ = 't';  break;
            default:
                if (c < 0x20) {
                    out += sprintf(out, "\\u%04x", c);
                } else {
                    *out++ = (char)c;
                }
        }
    }
    *out++ = '"';
    *out   = '\0';
    AirString result = air_str_from_buf(buf, (size_t)(out - buf));
    air_free(buf);
    return result;
}

/* json.int_to_string(n) -> String */
AirString air_json_int_to_string(int64_t n) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%lld", (long long)n);
    return air_str_new(buf);
}

/* json.float_to_string(f) -> String */
AirString air_json_float_to_string(double f) {
    char buf[64];
    snprintf(buf, sizeof(buf), "%g", f);
    return air_str_new(buf);
}
