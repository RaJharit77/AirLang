#define _GNU_SOURCE
/*
 * air_runtime.c — Implémentation du runtime AirLang v0.1
 */

#include "air_runtime.h"
#include <stdarg.h>
#include <ctype.h>
#include <errno.h>
#include <setjmp.h>
#include <time.h>

/* ── Mémoire : ramasse-miettes conservatif (marquage + balayage) ─────────────────
 *
 * Toutes les allocations du programme passent par air_alloc / air_alloc_atomic / air_realloc.
 * Chaque bloc a un petit en-tête (taille, index dans la table) et est inscrit dans une table.
 * Quand assez d'octets ont été alloués depuis la dernière collecte, on :
 *   1. trie la table par adresse ;
 *   2. marque les blocs atteignables depuis les racines : pile C (registres compris) et
 *      données globales (.data/.bss) — tout mot qui ressemble à une adresse DANS un bloc compte,
 *      même une adresse intérieure ;
 *   3. libère les blocs non marqués.
 * Aucune modification du code généré n'est nécessaire (variables, listes, maps, fermetures,
 * optionnels, try/catch, cycles). Un « faux positif » (un entier qui ressemble à une adresse)
 * ne fait que retarder une libération, jamais en provoquer une trop tôt.
 * Le GC n'est actif que si air_gc_init() a été appelé (le main généré le fait) ; hors Linux
 * il reste désactivé et le programme se comporte comme avant (mémoire rendue à la fin).
 * Variables d'environnement : AIR_GC_STATS=1 (bilan sur stderr), AIR_GC_STRESS=N (collecte tous
 * les N allocations, pour les tests), AIR_GC=0 (désactive).
 */

typedef struct { size_t size; size_t index; } AirBlockHdr;      /* 16 octets : charge utile alignée sur 16 */
typedef struct { char* base; size_t size; uint8_t mark; uint8_t atomic; } AirBlock;

#if defined(__linux__) && (defined(__GNUC__) || defined(__clang__))
#  define AIR_GC_AVAILABLE 1
extern char __data_start[] __attribute__((weak));
extern char _end[] __attribute__((weak));
#else
#  define AIR_GC_AVAILABLE 0
#endif

static AirBlock* gc_blocks = NULL;
static size_t    gc_count = 0, gc_cap = 0;
static char*     gc_stack_base = NULL;
static int       gc_enabled = 0, gc_stats_on = 0;
static size_t    gc_since = 0, gc_threshold = 8u << 20, gc_live = 0;
static size_t    gc_stress = 0, gc_stress_tick = 0;
static size_t    gc_collections = 0, gc_total_alloc = 0, gc_total_freed = 0, gc_peak = 0, gc_n_alloc = 0;
static int       gc_running = 0;

#ifdef __SANITIZE_ADDRESS__
/* ASan place par défaut les variables locales dans une « fausse pile » sur le tas, que le GC ne parcourt pas :
 * on la désactive pour les exécutables compilés avec -fsanitize=address. */
const char* __asan_default_options(void) { return "detect_stack_use_after_return=0"; }
#endif

static void gc_report(void) {
    fprintf(stderr, "[air-gc] collectes=%zu allocations=%zu octets_alloués=%zu octets_libérés=%zu "
                    "pic_vivant=%zu vivant_final=%zu\n",
            gc_collections, gc_n_alloc, gc_total_alloc, gc_total_freed, gc_peak, gc_live);
}

void air_gc_init(void* stack_base) {
#if AIR_GC_AVAILABLE
    const char* off = getenv("AIR_GC");
    if (off && off[0] == '0') return;
    gc_stack_base = (char*)stack_base;
    gc_enabled = (__data_start != NULL && _end != NULL);
    const char* st = getenv("AIR_GC_STRESS");
    if (st && atol(st) > 0) gc_stress = (size_t)atol(st);
    const char* th = getenv("AIR_GC_THRESHOLD");
    if (th && atol(th) > 0) gc_threshold = (size_t)atol(th);
    const char* stats = getenv("AIR_GC_STATS");
    if (stats && stats[0] == '1') { gc_stats_on = 1; atexit(gc_report); }
#else
    (void)stack_base;
#endif
}

#if AIR_GC_AVAILABLE
static int gc_cmp(const void* a, const void* b) {
    const AirBlock* x = (const AirBlock*)a; const AirBlock* y = (const AirBlock*)b;
    return (x->base > y->base) - (x->base < y->base);
}

/* Retourne l'index du bloc dont la charge utile contient `w` (une adresse juste après la fin compte aussi). */
static long gc_find(uintptr_t w, uintptr_t lo, uintptr_t hi) {
    if (w < lo || w >= hi) return -1;
    size_t a = 0, b = gc_count;                     /* dernier bloc dont la charge utile commence avant (ou à) w */
    while (a < b) {
        size_t m = (a + b) / 2;
        if ((uintptr_t)gc_blocks[m].base + sizeof(AirBlockHdr) <= w) a = m + 1; else b = m;
    }
    if (a == 0) return -1;
    AirBlock* blk = &gc_blocks[a - 1];
    uintptr_t start = (uintptr_t)blk->base + sizeof(AirBlockHdr);
    return (w <= start + blk->size) ? (long)(a - 1) : -1;
}

typedef struct { size_t* items; size_t n, cap; } GcStack;
static void gc_push(GcStack* st, size_t i) {
    if (st->n == st->cap) {
        st->cap = st->cap ? st->cap * 2 : 1024;
        st->items = (size_t*)realloc(st->items, st->cap * sizeof(size_t));
        if (!st->items) air_panic("Mémoire insuffisante (GC)");
    }
    st->items[st->n++] = i;
}

__attribute__((no_sanitize_address, no_sanitize("undefined")))
static void gc_scan_range(const char* from, const char* to, GcStack* st, uintptr_t lo, uintptr_t hi) {
    uintptr_t a = ((uintptr_t)from + 7) & ~(uintptr_t)7;
    for (const uintptr_t* p = (const uintptr_t*)a; (const char*)(p + 1) <= to; p++) {
        long i = gc_find(*p, lo, hi);
        if (i >= 0 && !gc_blocks[i].mark) {
            gc_blocks[i].mark = 1;
            if (!gc_blocks[i].atomic) gc_push(st, (size_t)i);
        }
    }
}

__attribute__((noinline, no_sanitize_address, no_sanitize("undefined")))
static void gc_collect_inner(void) {
    jmp_buf regs;                                   /* force les registres sur la pile */
    __builtin_unwind_init();
    setjmp(regs);
    char marker = 0;
    const char* sp = (const char*)((uintptr_t)(&marker < (char*)&regs ? &marker : (char*)&regs));

    qsort(gc_blocks, gc_count, sizeof(AirBlock), gc_cmp);
    for (size_t i = 0; i < gc_count; i++) {
        gc_blocks[i].mark = 0;
        ((AirBlockHdr*)gc_blocks[i].base)->index = i;
    }
    uintptr_t lo = (uintptr_t)gc_blocks[0].base + sizeof(AirBlockHdr);
    uintptr_t hi = (uintptr_t)gc_blocks[gc_count - 1].base + sizeof(AirBlockHdr) + gc_blocks[gc_count - 1].size + 1;

    GcStack st = {NULL, 0, 0};
    gc_scan_range(sp, gc_stack_base + 256, &st, lo, hi);       /* pile (+ marge pour le cadre de main) */
    gc_scan_range(__data_start, _end, &st, lo, hi);            /* globales */
    while (st.n) {
        AirBlock* b = &gc_blocks[st.items[--st.n]];
        gc_scan_range(b->base + sizeof(AirBlockHdr), b->base + sizeof(AirBlockHdr) + b->size, &st, lo, hi);
    }
    free(st.items);

    size_t keep = 0, freed = 0, live = 0;
    for (size_t i = 0; i < gc_count; i++) {
        if (gc_blocks[i].mark) {
            gc_blocks[keep] = gc_blocks[i];
            ((AirBlockHdr*)gc_blocks[keep].base)->index = keep;
            live += gc_blocks[keep].size;
            keep++;
        } else {
            freed += gc_blocks[i].size;
            free(gc_blocks[i].base);
        }
    }
    gc_count = keep;
    gc_total_freed += freed;
    gc_live = live;
}
#endif

void air_gc_collect(void) {
#if AIR_GC_AVAILABLE
    if (!gc_enabled || gc_running || gc_count == 0) return;
    gc_running = 1;
    gc_collect_inner();
    gc_collections++;
    gc_since = 0;
    gc_threshold = gc_live > (8u << 20) ? gc_live : (8u << 20);
    gc_running = 0;
#endif
}

static void* gc_alloc(size_t size, int atomic) {
    if (gc_enabled && !gc_running) {
        if (gc_stress) { if (++gc_stress_tick >= gc_stress) { gc_stress_tick = 0; air_gc_collect(); } }
        else if (gc_since >= gc_threshold) air_gc_collect();
    }
    char* base = (char*)calloc(1, sizeof(AirBlockHdr) + size + 1);
    if (!base) { air_gc_collect(); base = (char*)calloc(1, sizeof(AirBlockHdr) + size + 1); }
    if (!base) { air_panic("Mémoire insuffisante (air_alloc)"); }
    ((AirBlockHdr*)base)->size = size;
    if (gc_enabled) {
        if (gc_count == gc_cap) {
            gc_cap = gc_cap ? gc_cap * 2 : 4096;
            gc_blocks = (AirBlock*)realloc(gc_blocks, gc_cap * sizeof(AirBlock));
            if (!gc_blocks) air_panic("Mémoire insuffisante (table du GC)");
        }
        ((AirBlockHdr*)base)->index = gc_count;
        gc_blocks[gc_count++] = (AirBlock){base, size, 0, (uint8_t)atomic};
        gc_since += size; gc_total_alloc += size; gc_n_alloc++;
        gc_live += size;
        if (gc_live > gc_peak) gc_peak = gc_live;
    }
    return base + sizeof(AirBlockHdr);
}

void* air_alloc(size_t size)        { return gc_alloc(size, 0); }
void* air_alloc_atomic(size_t size) { return gc_alloc(size, 1); }   /* données sans pointeurs (texte) */

void* air_realloc(void* ptr, size_t size) {
    void* p = gc_alloc(size, 0);
    if (ptr) {
        size_t old = ((AirBlockHdr*)((char*)ptr - sizeof(AirBlockHdr)))->size;
        memcpy(p, ptr, old < size ? old : size);
    }
    return p;                       /* l'ancien bloc devient un déchet : le GC le récupère */
}

void air_free(void* ptr) {
    (void)ptr;                      /* libération explicite inutile : le GC s'en charge */
}

/* ── Strings ─────────────────────────────────────────────────────────────────── */

AirStr air_str(const char* s) {
    if (!s) return (AirStr){NULL, 0};
    size_t n = strlen(s);
    char*  d = (char*)air_alloc_atomic(n + 1);
    memcpy(d, s, n + 1);
    return (AirStr){d, n};
}

AirStr air_str_n(const char* s, size_t n) {
    char* d = (char*)air_alloc_atomic(n + 1);
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
    char*  d = (char*)air_alloc_atomic(n + 1);
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

/* Représentation la plus courte qui se relit EXACTEMENT (1.0 → "1.0", 0.1 → "0.1",
 * 1234567.5 → "1234567.5"). Les entiers gardent ".0" pour rester reconnaissables comme Float. */
AirStr air_float_to_str(double f) {
    char buf[64];
    if (f != f)  return air_str("nan");
    if (f == 1.0 / 0.0)  return air_str("inf");
    if (f == -1.0 / 0.0) return air_str("-inf");
    for (int prec = 1; prec <= 17; prec++) {
        snprintf(buf, sizeof(buf), "%.*g", prec, f);
        if (strtod(buf, NULL) == f) {
            double a = f < 0 ? -f : f;
            if (strpbrk(buf, "eE") && (a == 0.0 || (a >= 1e-4 && a < 1e15))) {
                /* notation décimale : on cherche le plus petit nombre de décimales exact */
                for (int d = 0; d <= 20; d++) {
                    snprintf(buf, sizeof(buf), "%.*f", d, f);
                    if (strtod(buf, NULL) == f) break;
                }
            }
            break;
        }
    }
    if (!strpbrk(buf, ".eE")) strncat(buf, ".0", sizeof(buf) - strlen(buf) - 1);
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
    char* buf = (char*)air_alloc_atomic(new_len + 1);
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

AirTryFrame* air_try_top = NULL;
AirStr air_last_error = {(char*)"", 0};

void air_fail(AirStr message) {
    if (air_try_top) {                         /* un `try` est actif : on saute vers son `catch` */
        char* copy = (char*)air_alloc_atomic(message.len + 1);      /* le message doit survivre à la pile abandonnée */
        if (message.len) memcpy(copy, message.data, message.len);
        copy[message.len] = '\0';
        air_last_error = (AirStr){copy, message.len};
        AirTryFrame* f = air_try_top;
        air_try_top = f->prev;
        longjmp(f->jb, 1);
    }
    fflush(stdout);
    fprintf(stderr, "\nErreur d'exécution : %.*s\n", (int)message.len, message.data ? message.data : "");
    exit(1);
}

void air_runtime_error(const char* fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    air_fail(air_str(buf));
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
        air_runtime_error("unwrap() sur une erreur : %s", msg ? msg->data : "erreur inconnue");
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
    char* buf = (char*)air_alloc_atomic(size + 1);
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
    if (!s.data || s.len == 0 || *end != '\0')
        air_runtime_error("\"%s\" n'est pas un entier", s.data ? s.data : "");
    return (int64_t)v;
}

double air_str_to_float(AirStr s) {
    char* end = NULL;
    double v = strtod(s.data ? s.data : "", &end);
    if (!s.data || s.len == 0 || *end != '\0')
        air_runtime_error("\"%s\" n'est pas un nombre", s.data ? s.data : "");
    return v;
}


/* ── Conversions optionnelles, découpage et comparaison de chaînes ─────────────── */

/* Copie `s` sans espaces de bord dans `buf` (NUL-terminé) ; retourne false si trop long ou vide. */
static bool air_trimmed_copy(AirStr s, char* buf, size_t cap) {
    size_t a = 0, b = s.len;
    while (a < b && isspace((unsigned char)s.data[a])) a++;
    while (b > a && isspace((unsigned char)s.data[b - 1])) b--;
    if (b == a || b - a >= cap) return false;
    memcpy(buf, s.data + a, b - a);
    buf[b - a] = '\0';
    return true;
}

AirOpt_Int air_str_parse_int(AirStr s) {
    char buf[64], *end = NULL;
    AirOpt_Int r = {false, 0};
    if (!s.data || !air_trimmed_copy(s, buf, sizeof buf)) return r;
    errno = 0;
    long long v = strtoll(buf, &end, 10);
    if (*end != '\0' || errno == ERANGE) return r;
    r.has = true; r.v = (int64_t)v;
    return r;
}

AirOpt_Float air_str_parse_float(AirStr s) {
    char buf[64], *end = NULL;
    AirOpt_Float r = {false, 0.0};
    if (!s.data || !air_trimmed_copy(s, buf, sizeof buf)) return r;
    errno = 0;
    double v = strtod(buf, &end);
    if (*end != '\0' || errno == ERANGE) return r;
    r.has = true; r.v = v;
    return r;
}

/* Sous-chaîne [start, end) ; les bornes sont ramenées dans [0, longueur]. */
AirStr air_str_slice(AirStr s, int64_t start, int64_t end) {
    if (start < 0) start = 0;
    if (end > (int64_t)s.len) end = (int64_t)s.len;
    if (start >= end) return AIR_STR_LIT("");
    return air_str_n(s.data + start, (size_t)(end - start));
}

int air_str_cmp(AirStr a, AirStr b) {
    size_t n = a.len < b.len ? a.len : b.len;
    int c = n ? memcmp(a.data, b.data, n) : 0;
    if (c) return c;
    return a.len < b.len ? -1 : (a.len > b.len ? 1 : 0);
}


/* ── assert / exit ─────────────────────────────────────────────────────────────── */

void air_assert(bool cond, AirStr message, int64_t line) {
    if (cond) return;
    char buf[64];
    snprintf(buf, sizeof buf, " (ligne %lld)", (long long)line);
    air_fail(air_concat(message, air_str(buf)));
}

void air_assert_eq_fail(AirStr expected, AirStr got, int64_t line) {
    char buf[64];
    snprintf(buf, sizeof buf, " (ligne %lld)", (long long)line);
    AirStr m = air_concat(air_concat(air_str("assert_eq : le premier vaut "), expected),
                          air_concat(air_str(", le second vaut "), got));
    air_fail(air_concat(m, air_str(buf)));
}

void air_exit(int64_t code) {
    fflush(stdout);
    exit((int)code);
}
