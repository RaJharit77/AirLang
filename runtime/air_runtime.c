/*
 * air_runtime.c — Implémentation du runtime AirLang v0.1
 */

#include "air_runtime.h"
#include <stdarg.h>
#include <ctype.h>
#include <time.h>

/* ── Mémoire ─────────────────────────────────────────────────────────────────── */

void* air_alloc(size_t size) {
    void* p = calloc(1, size);
    if (!p) { air_panic("Mémoire insuffisante (air_alloc)"); }
    return p;
}

void* air_realloc(void* ptr, size_t size) {
    void* p = realloc(ptr, size);
    if (!p) { air_panic("Mémoire insuffisante (air_realloc)"); }
    return p;
}

void air_free(void* ptr) {
    if (ptr) free(ptr);
}

/* ── Strings ─────────────────────────────────────────────────────────────────── */

AirStr air_str(const char* s) {
    if (!s) return (AirStr){NULL, 0};
    size_t n = strlen(s);
    char*  d = (char*)air_alloc(n + 1);
    memcpy(d, s, n + 1);
    return (AirStr){d, n};
}

AirStr air_str_n(const char* s, size_t n) {
    char* d = (char*)air_alloc(n + 1);
    memcpy(d, s, n);
    d[n] = '\0';
    return (AirStr){d, n};
}

AirStr air_str_copy(AirStr s) {
    return air_str_n(s.data, s.len);
}

void air_str_free(AirStr* s) {
    air_free(s->data);
    s->data = NULL;
    s->len  = 0;
}

bool air_str_eq(AirStr a, AirStr b) {
    return a.len == b.len && memcmp(a.data, b.data, a.len) == 0;
}

AirStr air_str_concat(AirStr a, AirStr b) {
    size_t n = a.len + b.len;
    char*  d = (char*)air_alloc(n + 1);
    memcpy(d, a.data, a.len);
    memcpy(d + a.len, b.data, b.len);
    d[n] = '\0';
    return (AirStr){d, n};
}

AirStr air_int_to_str(int64_t n) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%ld", (long)n);
    return air_str(buf);
}

AirStr air_float_to_str(double f) {
    char buf[64];
    snprintf(buf, sizeof(buf), "%g", f);
    return air_str(buf);
}

/* Concaténation intelligente utilisée par l'opérateur + */
AirStr air_concat(AirStr a, AirStr b) {
    return air_str_concat(a, b);
}

int64_t air_str_length(AirStr s) {
    return (int64_t)s.len;
}

AirStr air_str_upper(AirStr s) {
    AirStr r = air_str_copy(s);
    for (size_t i = 0; i < r.len; i++) r.data[i] = (char)toupper((unsigned char)r.data[i]);
    return r;
}

AirStr air_str_lower(AirStr s) {
    AirStr r = air_str_copy(s);
    for (size_t i = 0; i < r.len; i++) r.data[i] = (char)tolower((unsigned char)r.data[i]);
    return r;
}

AirStr air_str_trim(AirStr s) {
    size_t start = 0, end = s.len;
    while (start < end && isspace((unsigned char)s.data[start])) start++;
    while (end > start && isspace((unsigned char)s.data[end-1])) end--;
    return air_str_n(s.data + start, end - start);
}

bool air_str_contains(AirStr haystack, AirStr needle) {
    if (needle.len == 0) return true;
    if (needle.len > haystack.len) return false;
    return memmem(haystack.data, haystack.len, needle.data, needle.len) != NULL;
}

AirStr air_str_replace(AirStr s, AirStr from, AirStr to) {
    if (from.len == 0 || !air_str_contains(s, from)) return air_str_copy(s);
    /* Compter les occurrences */
    size_t count = 0;
    char* p = s.data;
    while ((p = memmem(p, s.len - (p - s.data), from.data, from.len))) {
        count++;
        p += from.len;
    }
    size_t new_len = s.len + count * (to.len - from.len);
    char* buf = (char*)air_alloc(new_len + 1);
    char* src = s.data;
    char* dst = buf;
    while ((p = memmem(src, s.len - (src - s.data), from.data, from.len))) {
        size_t pre = p - src;
        memcpy(dst, src, pre); dst += pre;
        memcpy(dst, to.data, to.len); dst += to.len;
        src = p + from.len;
    }
    size_t rest = s.len - (src - s.data);
    memcpy(dst, src, rest);
    buf[new_len] = '\0';
    return (AirStr){buf, new_len};
}

AirList* air_str_split(AirStr s, AirStr delim) {
    AirList* result = air_list_empty();
    if (delim.len == 0) {
        air_list_append(result, (AirVal)air_alloc(sizeof(AirStr)));
        *(AirStr*)result->items[0] = air_str_copy(s);
        return result;
    }
    char* start = s.data;
    char* end   = s.data + s.len;
    char* p;
    while ((p = memmem(start, end - start, delim.data, delim.len))) {
        AirStr* part = (AirStr*)air_alloc(sizeof(AirStr));
        *part = air_str_n(start, p - start);
        air_list_append(result, (AirVal)part);
        start = p + delim.len;
    }
    AirStr* last = (AirStr*)air_alloc(sizeof(AirStr));
    *last = air_str_n(start, end - start);
    air_list_append(result, (AirVal)last);
    return result;
}

/* ── Listes ─────────────────────────────────────────────────────────────────── */

AirList* air_list_empty(void) {
    AirList* l = (AirList*)air_alloc(sizeof(AirList));
    l->cap  = 8;
    l->len  = 0;
    l->items = (AirVal*)air_alloc(sizeof(AirVal) * l->cap);
    return l;
}

AirList* air_list_of(size_t n, ...) {
    AirList* l = air_list_empty();
    va_list ap;
    va_start(ap, n);
    for (size_t i = 0; i < n; i++) {
        air_list_append(l, va_arg(ap, AirVal));
    }
    va_end(ap);
    return l;
}

void air_list_append(AirList* list, AirVal item) {
    if (list->len >= list->cap) {
        list->cap  *= 2;
        list->items = (AirVal*)air_realloc(list->items, sizeof(AirVal) * list->cap);
    }
    list->items[list->len++] = item;
}

AirVal air_list_get(AirList* list, int64_t index) {
    if (index < 0) index = (int64_t)list->len + index;
    if (index < 0 || (size_t)index >= list->len) {
        air_panic("Index hors limites (air_list_get)");
    }
    return list->items[index];
}

void air_list_set(AirList* list, int64_t index, AirVal item) {
    if (index < 0 || (size_t)index >= list->len) {
        air_panic("Index hors limites (air_list_set)");
    }
    list->items[index] = item;
}

int64_t air_list_length(AirList* list) {
    return list ? (int64_t)list->len : 0;
}

AirList* air_list_map(AirList* list, AirVal (*fn)(AirVal)) {
    AirList* result = air_list_empty();
    for (size_t i = 0; i < list->len; i++) {
        air_list_append(result, fn(list->items[i]));
    }
    return result;
}

AirList* air_list_filter(AirList* list, bool (*fn)(AirVal)) {
    AirList* result = air_list_empty();
    for (size_t i = 0; i < list->len; i++) {
        if (fn(list->items[i])) {
            air_list_append(result, list->items[i]);
        }
    }
    return result;
}

AirVal air_list_reduce(AirList* list, AirVal init, AirVal (*fn)(AirVal, AirVal)) {
    AirVal acc = init;
    for (size_t i = 0; i < list->len; i++) {
        acc = fn(acc, list->items[i]);
    }
    return acc;
}

AirStr air_list_join(AirList* list, AirStr sep) {
    if (list->len == 0) return air_str("");
    AirStr result = *(AirStr*)list->items[0];
    for (size_t i = 1; i < list->len; i++) {
        AirStr tmp = air_str_concat(result, sep);
        result = air_str_concat(tmp, *(AirStr*)list->items[i]);
    }
    return result;
}

void air_list_free(AirList* list) {
    if (!list) return;
    air_free(list->items);
    air_free(list);
}

/* ── Maps ───────────────────────────────────────────────────────────────────── */

#define AIR_MAP_BUCKETS 64

static size_t _air_hash(AirStr key) {
    size_t h = 5381;
    for (size_t i = 0; i < key.len; i++) {
        h = ((h << 5) + h) + (unsigned char)key.data[i];
    }
    return h % AIR_MAP_BUCKETS;
}

AirMap* air_map_empty(void) {
    AirMap* m = (AirMap*)air_alloc(sizeof(AirMap));
    m->bucket_count = AIR_MAP_BUCKETS;
    m->buckets = (AirMapEntry**)air_alloc(sizeof(AirMapEntry*) * AIR_MAP_BUCKETS);
    m->len = 0;
    return m;
}

void air_map_set(AirMap* m, AirStr key, AirVal value) {
    size_t h = _air_hash(key);
    AirMapEntry* e = m->buckets[h];
    while (e) {
        if (air_str_eq(e->key, key)) { e->value = value; return; }
        e = e->next;
    }
    AirMapEntry* ne = (AirMapEntry*)air_alloc(sizeof(AirMapEntry));
    ne->key   = air_str_copy(key);
    ne->value = value;
    ne->next  = m->buckets[h];
    m->buckets[h] = ne;
    m->len++;
}

AirVal air_map_get(AirMap* m, AirStr key) {
    size_t h = _air_hash(key);
    AirMapEntry* e = m->buckets[h];
    while (e) {
        if (air_str_eq(e->key, key)) return e->value;
        e = e->next;
    }
    return NULL;
}

bool air_map_has(AirMap* m, AirStr key) {
    return air_map_get(m, key) != NULL;
}

void air_map_delete(AirMap* m, AirStr key) {
    size_t h = _air_hash(key);
    AirMapEntry** p = &m->buckets[h];
    while (*p) {
        if (air_str_eq((*p)->key, key)) {
            AirMapEntry* del = *p;
            *p = del->next;
            air_str_free(&del->key);
            air_free(del);
            m->len--;
            return;
        }
        p = &(*p)->next;
    }
}

int64_t air_map_length(AirMap* m) {
    return (int64_t)m->len;
}

/* ── Result ─────────────────────────────────────────────────────────────────── */

AirResult air_ok(AirVal value) {
    return (AirResult){true, value};
}

AirResult air_err(const char* message) {
    AirStr* s = (AirStr*)air_alloc(sizeof(AirStr));
    *s = air_str(message);
    return (AirResult){false, (AirVal)s};
}

bool air_is_ok(AirResult r) {
    return r.is_ok;
}

AirVal air_unwrap(AirResult r) {
    if (!r.is_ok) {
        AirStr* msg = (AirStr*)r.value;
        fprintf(stderr, "✘ AirLang Unwrap sur Err : %s\n",
                msg ? msg->data : "erreur inconnue");
        exit(1);
    }
    return r.value;
}

/* ── I/O ─────────────────────────────────────────────────────────────────────── */

void air_print(AirStr s) {
    if (s.data) printf("%s\n", s.data);
    else printf("\n");
}

void air_print_int(int64_t n) {
    printf("%ld\n", (long)n);
}

void air_print_float(double f) {
    printf("%g\n", f);
}

void air_print_bool(bool b) {
    printf("%s\n", b ? "true" : "false");
}

AirStr air_input(AirStr prompt) {
    if (prompt.data) printf("%s", prompt.data);
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) return air_str("");
    size_t n = strlen(buf);
    if (n > 0 && buf[n-1] == '\n') buf[--n] = '\0';
    return air_str_n(buf, n);
}

AirResult air_file_read(AirStr path) {
    FILE* f = fopen(path.data, "r");
    if (!f) return air_err("Impossible d'ouvrir le fichier");
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char* buf = (char*)air_alloc(size + 1);
    fread(buf, 1, size, f);
    buf[size] = '\0';
    fclose(f);
    AirStr* s = (AirStr*)air_alloc(sizeof(AirStr));
    *s = (AirStr){buf, (size_t)size};
    return air_ok((AirVal)s);
}

AirResult air_file_write(AirStr path, AirStr content) {
    FILE* f = fopen(path.data, "w");
    if (!f) return air_err("Impossible d'écrire le fichier");
    fwrite(content.data, 1, content.len, f);
    fclose(f);
    return air_ok(NULL);
}

AirResult air_file_append(AirStr path, AirStr content) {
    FILE* f = fopen(path.data, "a");
    if (!f) return air_err("Impossible d'ouvrir le fichier en écriture");
    fwrite(content.data, 1, content.len, f);
    fclose(f);
    return air_ok(NULL);
}

bool air_file_exists(AirStr path) {
    FILE* f = fopen(path.data, "r");
    if (f) { fclose(f); return true; }
    return false;
}

/* ── Mathématiques ───────────────────────────────────────────────────────────── */

int64_t air_abs_int(int64_t n)   { return n < 0 ? -n : n; }
double  air_abs_float(double f)  { return f < 0.0 ? -f : f; }
double  air_pow(double b, double e) { return pow(b, e); }
double  air_sqrt(double n)       { return sqrt(n); }
int64_t air_floor(double n)      { return (int64_t)floor(n); }
int64_t air_ceil(double n)       { return (int64_t)ceil(n); }
int64_t air_round(double n)      { return (int64_t)round(n); }

double air_random(void) {
    static bool seeded = false;
    if (!seeded) { srand((unsigned)time(NULL)); seeded = true; }
    return (double)rand() / ((double)RAND_MAX + 1.0);
}

/* ── Égalité générique ─────────────────────────────────────────────────────── */

bool air_eq(AirVal a, AirVal b) {
    return a == b;   /* Par défaut : égalité de pointeur / valeur entière */
}
