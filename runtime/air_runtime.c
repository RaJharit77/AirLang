#define _GNU_SOURCE
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

/* Longueur en caractères Unicode (pas en octets) : on ignore les octets de continuation UTF-8. */
int64_t air_str_length(AirStr s) {
    int64_t n = 0;
    for (size_t i = 0; i < s.len; i++)
        if (((unsigned char)s.data[i] & 0xC0) != 0x80) n++;
    return n;
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

/* ── Erreurs d'exécution ─────────────────────────────────────────────────────── */

void air_runtime_error(const char* fmt, ...) {
    fflush(stdout);
    fprintf(stderr, "\nErreur d'exécution : ");
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, "\n");
    exit(1);
}

/* ── Petit tampon de texte (utilisé par l'affichage des listes et des maps) ───── */

typedef struct { char* data; size_t len, cap; } AirBuf;

static void buf_add(AirBuf* b, const char* s, size_t n) {
    if (b->len + n + 1 > b->cap) {
        size_t nc = b->cap ? b->cap * 2 : 64;
        while (nc < b->len + n + 1) nc *= 2;
        b->data = (char*)air_realloc(b->data, nc);
        b->cap = nc;
    }
    memcpy(b->data + b->len, s, n);
    b->len += n;
    b->data[b->len] = '\0';
}
static void buf_str(AirBuf* b, AirStr s) { buf_add(b, s.data ? s.data : "", s.len); }
static void buf_cstr(AirBuf* b, const char* s) { buf_add(b, s, strlen(s)); }

/* Texte d'un élément selon son genre (les chaînes sont entre guillemets). */
static void buf_elem(AirBuf* b, int kind, const void* p) {
    switch (kind) {
        case AIR_K_INT:    buf_str(b, air_int_to_str(*(const int64_t*)p)); break;
        case AIR_K_FLOAT:  buf_str(b, air_float_to_str(*(const double*)p)); break;
        case AIR_K_BOOL:   buf_str(b, air_bool_to_str(*(const bool*)p)); break;
        case AIR_K_STRING: buf_cstr(b, "\""); buf_str(b, *(const AirStr*)p); buf_cstr(b, "\""); break;
        default:           buf_cstr(b, "<objet>"); break;
    }
}

/* ── Strings : découpage ────────────────────────────────────────────────────── */

AirList* air_str_split(AirStr s, AirStr delim) {
    AirList* result = air_list_new(sizeof(AirStr));
    if (delim.len == 0 || s.len == 0) {
        AirStr whole = air_str_copy(s);
        air_list_push(result, &whole);
        return result;
    }
    const char* start = s.data;
    const char* end   = s.data + s.len;
    const char* p;
    while ((p = (const char*)memmem(start, (size_t)(end - start), delim.data, delim.len))) {
        AirStr part = air_str_n(start, (size_t)(p - start));
        air_list_push(result, &part);
        start = p + delim.len;
    }
    AirStr last = air_str_n(start, (size_t)(end - start));
    air_list_push(result, &last);
    return result;
}

/* ── Listes (éléments stockés par valeur, tableau contigu) ──────────────────── */

AirList* air_list_new(size_t elem_size) {
    AirList* l = (AirList*)air_alloc(sizeof(AirList));
    l->elem_size = elem_size;
    return l;
}

static void list_reserve(AirList* l, size_t need) {
    if (need <= l->cap) return;
    size_t nc = l->cap ? l->cap * 2 : 8;
    while (nc < need) nc *= 2;
    l->data = (char*)air_realloc(l->data, nc * l->elem_size);
    l->cap = nc;
}

AirList* air_list_from(const void* items, size_t n, size_t elem_size) {
    AirList* l = air_list_new(elem_size);
    list_reserve(l, n);
    if (n) memcpy(l->data, items, n * elem_size);
    l->len = n;
    return l;
}

void air_list_push(AirList* l, const void* item) {
    list_reserve(l, l->len + 1);
    memcpy(l->data + l->len * l->elem_size, item, l->elem_size);
    l->len++;
}

void* air_list_at(AirList* l, int64_t i) {
    if (i < 0 || (uint64_t)i >= l->len)
        air_runtime_error("indice %lld hors limites : la liste contient %zu élément(s)",
                          (long long)i, l->len);
    return l->data + (size_t)i * l->elem_size;
}

void* air_list_first_ptr(AirList* l) {
    if (l->len == 0) air_runtime_error("first() sur une liste vide");
    return l->data;
}

void* air_list_last_ptr(AirList* l) {
    if (l->len == 0) air_runtime_error("last() sur une liste vide");
    return l->data + (l->len - 1) * l->elem_size;
}

void air_list_pop_into(AirList* l, void* out) {
    if (l->len == 0) air_runtime_error("pop() sur une liste vide");
    l->len--;
    memcpy(out, l->data + l->len * l->elem_size, l->elem_size);
}

void air_list_remove_at_into(AirList* l, int64_t i, void* out) {
    if (i < 0 || (uint64_t)i >= l->len)
        air_runtime_error("remove_at(%lld) hors limites : la liste contient %zu élément(s)",
                          (long long)i, l->len);
    char* at = l->data + (size_t)i * l->elem_size;
    memcpy(out, at, l->elem_size);
    memmove(at, at + l->elem_size, (l->len - (size_t)i - 1) * l->elem_size);
    l->len--;
}

void air_list_clear(AirList* l) { l->len = 0; }

int64_t air_list_length(AirList* l) { return (int64_t)l->len; }

AirList* air_list_reversed(AirList* l) {
    AirList* r = air_list_new(l->elem_size);
    list_reserve(r, l->len);
    for (size_t i = 0; i < l->len; i++)
        memcpy(r->data + i * l->elem_size, l->data + (l->len - 1 - i) * l->elem_size, l->elem_size);
    r->len = l->len;
    return r;
}

static int cmp_int(const void* a, const void* b) {
    int64_t x = *(const int64_t*)a, y = *(const int64_t*)b;
    return (x > y) - (x < y);
}
static int cmp_float(const void* a, const void* b) {
    double x = *(const double*)a, y = *(const double*)b;
    return (x > y) - (x < y);
}
static int cmp_string(const void* a, const void* b) {
    const AirStr* x = (const AirStr*)a; const AirStr* y = (const AirStr*)b;
    size_t n = x->len < y->len ? x->len : y->len;
    int c = n ? memcmp(x->data, y->data, n) : 0;
    if (c) return c;
    return (x->len > y->len) - (x->len < y->len);
}

AirList* air_list_sorted(AirList* l, int kind) {
    AirList* r = air_list_from(l->data, l->len, l->elem_size);
    int (*cmp)(const void*, const void*) = NULL;
    switch (kind) {
        case AIR_K_INT:    cmp = cmp_int; break;
        case AIR_K_FLOAT:  cmp = cmp_float; break;
        case AIR_K_STRING: cmp = cmp_string; break;
        default: air_runtime_error("sort() n'est pas supporté pour ce type d'éléments");
    }
    if (r->len > 1) qsort(r->data, r->len, r->elem_size, cmp);
    return r;
}

static bool elem_eq(int kind, size_t size, const void* a, const void* b) {
    switch (kind) {
        case AIR_K_INT:    return *(const int64_t*)a == *(const int64_t*)b;
        case AIR_K_FLOAT:  return *(const double*)a == *(const double*)b;
        case AIR_K_BOOL:   return *(const bool*)a == *(const bool*)b;
        case AIR_K_STRING: return air_str_eq(*(const AirStr*)a, *(const AirStr*)b);
        default:           return memcmp(a, b, size) == 0;     /* identité (pointeurs) */
    }
}

int64_t air_list_index_of(AirList* l, const void* item, int kind) {
    for (size_t i = 0; i < l->len; i++)
        if (elem_eq(kind, l->elem_size, l->data + i * l->elem_size, item)) return (int64_t)i;
    return -1;
}

AirStr air_list_join(AirList* l, AirStr sep) {
    AirBuf b = {0};
    for (size_t i = 0; i < l->len; i++) {
        if (i) buf_str(&b, sep);
        buf_str(&b, *(AirStr*)(l->data + i * l->elem_size));
    }
    if (!b.data) return air_str("");
    return (AirStr){b.data, b.len};
}

AirStr air_list_to_str(AirList* l, int kind) {
    AirBuf b = {0};
    buf_cstr(&b, "[");
    for (size_t i = 0; i < l->len; i++) {
        if (i) buf_cstr(&b, ", ");
        buf_elem(&b, kind, l->data + i * l->elem_size);
    }
    buf_cstr(&b, "]");
    return (AirStr){b.data, b.len};
}

void air_list_free(AirList* l) {
    if (!l) return;
    air_free(l->data);
    air_free(l);
}

/* ── Maps (clés String, valeurs par valeur, ordre d'insertion conservé) ─────── */

static size_t map_hash(AirStr key) {
    size_t h = 1469598103934665603ULL;               /* FNV-1a */
    for (size_t i = 0; i < key.len; i++) h = (h ^ (unsigned char)key.data[i]) * 1099511628211ULL;
    return h;
}

AirMap* air_map_new(size_t value_size) {
    AirMap* m = (AirMap*)air_alloc(sizeof(AirMap));
    m->value_size   = value_size;
    m->bucket_count = 16;
    m->buckets      = (AirMapEntry**)air_alloc(sizeof(AirMapEntry*) * m->bucket_count);
    return m;
}

static void map_rehash(AirMap* m) {
    size_t nb = m->bucket_count * 2;
    AirMapEntry** nbk = (AirMapEntry**)air_alloc(sizeof(AirMapEntry*) * nb);
    for (size_t i = 0; i < m->len; i++) {
        AirMapEntry* e = m->order[i];
        size_t b = e->hash % nb;
        e->next = nbk[b];
        nbk[b] = e;
    }
    air_free(m->buckets);
    m->buckets = nbk;
    m->bucket_count = nb;
}

void* air_map_find(AirMap* m, AirStr key) {
    size_t h = map_hash(key);
    for (AirMapEntry* e = m->buckets[h % m->bucket_count]; e; e = e->next)
        if (e->hash == h && air_str_eq(e->key, key)) return (void*)(e + 1);
    return NULL;
}

void* air_map_get_ptr(AirMap* m, AirStr key) {
    void* p = air_map_find(m, key);
    if (!p) air_runtime_error("clé \"%.*s\" introuvable dans la map (utilisez has() ou get_or())",
                              (int)key.len, key.data ? key.data : "");
    return p;
}

void* air_map_slot(AirMap* m, AirStr key) {
    void* p = air_map_find(m, key);
    if (p) return p;
    if (m->len + 1 > m->bucket_count * 2) map_rehash(m);
    AirMapEntry* e = (AirMapEntry*)air_alloc(sizeof(AirMapEntry) + m->value_size);
    e->key  = air_str_copy(key);
    e->hash = map_hash(key);
    size_t b = e->hash % m->bucket_count;
    e->next = m->buckets[b];
    m->buckets[b] = e;
    if (m->len + 1 > m->order_cap) {
        m->order_cap = m->order_cap ? m->order_cap * 2 : 8;
        m->order = (AirMapEntry**)air_realloc(m->order, sizeof(AirMapEntry*) * m->order_cap);
    }
    m->order[m->len++] = e;
    return (void*)(e + 1);
}

AirMap* air_map_from(const AirStr* keys, const void* values, size_t n, size_t value_size) {
    AirMap* m = air_map_new(value_size);
    for (size_t i = 0; i < n; i++)
        memcpy(air_map_slot(m, keys[i]), (const char*)values + i * value_size, value_size);
    return m;
}

bool air_map_has(AirMap* m, AirStr key) { return air_map_find(m, key) != NULL; }

void air_map_delete(AirMap* m, AirStr key) {
    size_t h = map_hash(key);
    AirMapEntry** p = &m->buckets[h % m->bucket_count];
    while (*p) {
        AirMapEntry* e = *p;
        if (e->hash == h && air_str_eq(e->key, key)) {
            *p = e->next;
            for (size_t i = 0; i < m->len; i++) {
                if (m->order[i] == e) {
                    memmove(&m->order[i], &m->order[i + 1], (m->len - i - 1) * sizeof(AirMapEntry*));
                    break;
                }
            }
            m->len--;
            air_str_free(&e->key);
            air_free(e);
            return;
        }
        p = &e->next;
    }
}

void air_map_clear(AirMap* m) {
    while (m->len) air_map_delete(m, m->order[m->len - 1]->key);
}

int64_t air_map_length(AirMap* m) { return (int64_t)m->len; }

AirList* air_map_keys(AirMap* m) {
    AirList* l = air_list_new(sizeof(AirStr));
    for (size_t i = 0; i < m->len; i++) air_list_push(l, &m->order[i]->key);
    return l;
}

AirList* air_map_values(AirMap* m) {
    AirList* l = air_list_new(m->value_size);
    for (size_t i = 0; i < m->len; i++) air_list_push(l, (void*)(m->order[i] + 1));
    return l;
}

AirStr air_map_to_str(AirMap* m, int kind) {
    AirBuf b = {0};
    buf_cstr(&b, "{");
    for (size_t i = 0; i < m->len; i++) {
        if (i) buf_cstr(&b, ", ");
        buf_cstr(&b, "\""); buf_str(&b, m->order[i]->key); buf_cstr(&b, "\": ");
        buf_elem(&b, kind, (void*)(m->order[i] + 1));
    }
    buf_cstr(&b, "}");
    return (AirStr){b.data, b.len};
}

void air_map_free(AirMap* m) {
    if (!m) return;
    for (size_t i = 0; i < m->len; i++) { air_str_free(&m->order[i]->key); air_free(m->order[i]); }
    air_free(m->order);
    air_free(m->buckets);
    air_free(m);
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


/* ── Conversions (v0.2) ─────────────────────────────────────────────────────── */

AirStr air_bool_to_str(bool b) {
    return b ? AIR_STR_LIT("true") : AIR_STR_LIT("false");
}

int64_t air_str_to_int(AirStr s) {
    char* end = NULL;
    long long v = strtoll(s.data ? s.data : "", &end, 10);
    if (!s.data || s.len == 0 || *end != '\0') {
        fprintf(stderr, "\nErreur d'exécution : \"%s\" n'est pas un entier\n", s.data ? s.data : "");
        exit(1);
    }
    return (int64_t)v;
}

double air_str_to_float(AirStr s) {
    char* end = NULL;
    double v = strtod(s.data ? s.data : "", &end);
    if (!s.data || s.len == 0 || *end != '\0') {
        fprintf(stderr, "\nErreur d'exécution : \"%s\" n'est pas un nombre\n", s.data ? s.data : "");
        exit(1);
    }
    return v;
}
