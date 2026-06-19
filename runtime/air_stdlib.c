/*
 * air_stdlib.c — Bibliothèque Standard AirLang v0.1
 * Alignée avec air_runtime.h : types AirStr (data/len), AirList*, AirMap*.
 * Zéro dépendance externe — uniquement la libc standard.
 */

#include "air_runtime.h"
#include <stdarg.h>
#include <ctype.h>
#include <time.h>
#include <errno.h>
#include <sys/stat.h>

#ifdef _WIN32
  #include <windows.h>
  #define AIR_SLEEP(ms) Sleep((DWORD)(ms))
#else
  #include <unistd.h>
  #define AIR_SLEEP(ms) usleep((useconds_t)((ms)*1000))
#endif


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : io  (wrappeurs autour des fonctions air_file_* du runtime)
 * ═══════════════════════════════════════════════════════════════════════════ */

AirResult air_io_read(AirStr path)   { return air_file_read(path);  }
AirResult air_io_write(AirStr path, AirStr content) { return air_file_write(path, content); }
AirResult air_io_append(AirStr path, AirStr content){ return air_file_append(path, content); }
bool      air_io_exists(AirStr path) { return air_file_exists(path); }

bool air_io_delete(AirStr path) {
    return remove(path.data) == 0;
}

AirList* air_io_lines(AirStr path) {
    AirResult r = air_file_read(path);
    if (!r.is_ok) return air_list_empty();
    AirStr content = *(AirStr*)r.value;
    return air_str_split(content, air_str("\n"));
}

void air_io_print(AirStr s)   { fwrite(s.data, 1, s.len, stdout); }
void air_io_println(AirStr s) { fwrite(s.data, 1, s.len, stdout); putchar('\n'); }
AirStr air_io_input(AirStr prompt) { return air_input(prompt); }


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : string  (wrappeurs + fonctions supplémentaires)
 * ═══════════════════════════════════════════════════════════════════════════ */

AirList* air_string_split(AirStr s, AirStr sep)          { return air_str_split(s, sep); }
AirStr   air_string_trim(AirStr s)                       { return air_str_trim(s); }
AirStr   air_string_upper(AirStr s)                      { return air_str_upper(s); }
AirStr   air_string_lower(AirStr s)                      { return air_str_lower(s); }
bool     air_string_contains(AirStr s, AirStr sub)       { return air_str_contains(s, sub); }
AirStr   air_string_replace(AirStr s, AirStr o, AirStr n){ return air_str_replace(s, o, n); }
int64_t  air_string_length(AirStr s)                     { return air_str_length(s); }

AirStr air_string_join(AirList* parts, AirStr sep) {
    return air_list_join(parts, sep);
}

AirStr air_string_trim_left(AirStr s) {
    size_t start = 0;
    while (start < s.len && isspace((unsigned char)s.data[start])) start++;
    return air_str_n(s.data + start, s.len - start);
}

AirStr air_string_trim_right(AirStr s) {
    size_t end = s.len;
    while (end > 0 && isspace((unsigned char)s.data[end-1])) end--;
    return air_str_n(s.data, end);
}

bool air_string_starts_with(AirStr s, AirStr prefix) {
    if (prefix.len > s.len) return false;
    return memcmp(s.data, prefix.data, prefix.len) == 0;
}

bool air_string_ends_with(AirStr s, AirStr suffix) {
    if (suffix.len > s.len) return false;
    return memcmp(s.data + s.len - suffix.len, suffix.data, suffix.len) == 0;
}

int64_t air_string_index_of(AirStr s, AirStr sub) {
    if (sub.len == 0) return 0;
    if (sub.len > s.len) return -1;
    for (size_t i = 0; i <= s.len - sub.len; i++) {
        if (memcmp(s.data + i, sub.data, sub.len) == 0)
            return (int64_t)i;
    }
    return -1;
}

AirStr air_string_repeat(AirStr s, int64_t n) {
    if (n <= 0 || s.len == 0) return air_str("");
    size_t total = s.len * (size_t)n;
    char* buf = (char*)air_alloc(total + 1);
    for (int64_t i = 0; i < n; i++) memcpy(buf + i * s.len, s.data, s.len);
    buf[total] = '\0';
    AirStr result = air_str_n(buf, total);
    air_free(buf);
    return result;
}

AirStr air_string_reverse(AirStr s) {
    char* buf = (char*)air_alloc(s.len + 1);
    for (size_t i = 0; i < s.len; i++) buf[i] = s.data[s.len - 1 - i];
    buf[s.len] = '\0';
    AirStr result = air_str_n(buf, s.len);
    air_free(buf);
    return result;
}

AirStr air_string_slice(AirStr s, int64_t start, int64_t end_idx) {
    if (start < 0) start = 0;
    if (end_idx < 0 || (size_t)end_idx > s.len) end_idx = (int64_t)s.len;
    if (start >= end_idx) return air_str("");
    return air_str_n(s.data + start, (size_t)(end_idx - start));
}

int64_t air_string_to_int(AirStr s)   { return (int64_t)strtoll(s.data, NULL, 10); }
double  air_string_to_float(AirStr s) { return strtod(s.data, NULL); }


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : list  (wrappeurs autour des fonctions air_list_* du runtime)
 * ═══════════════════════════════════════════════════════════════════════════ */

int64_t air_list_length_stdlib(AirList* l) { return air_list_length(l); }
AirVal  air_list_get_stdlib(AirList* l, int64_t i) { return air_list_get(l, i); }
void    air_list_set_stdlib(AirList* l, int64_t i, AirVal v) { air_list_set(l, i, v); }
void    air_list_append_stdlib(AirList* l, AirVal v) { air_list_append(l, v); }

void air_list_prepend_stdlib(AirList* l, AirVal item) {
    if (!l) return;
    air_list_append(l, NULL);
    memmove(&l->items[1], &l->items[0], (l->len - 1) * sizeof(AirVal));
    l->items[0] = item;
}

AirVal air_list_pop_stdlib(AirList* l) {
    if (!l || l->len == 0) { air_panic("list.pop : liste vide"); }
    return l->items[--l->len];
}

AirList* air_list_reverse_stdlib(AirList* l) {
    AirList* result = air_list_empty();
    if (!l) return result;
    for (int64_t i = l->len - 1; i >= 0; i--) air_list_append(result, l->items[i]);
    return result;
}

AirList* air_list_slice_stdlib(AirList* l, int64_t start, int64_t end_idx) {
    AirList* result = air_list_empty();
    if (!l) return result;
    if (start < 0) start = 0;
    if (end_idx < 0 || (size_t)end_idx > l->len) end_idx = (int64_t)l->len;
    for (int64_t i = start; i < end_idx; i++) air_list_append(result, l->items[i]);
    return result;
}

AirList* air_list_concat_stdlib(AirList* a, AirList* b) {
    AirList* result = air_list_empty();
    if (a) for (size_t i = 0; i < a->len; i++) air_list_append(result, a->items[i]);
    if (b) for (size_t i = 0; i < b->len; i++) air_list_append(result, b->items[i]);
    return result;
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : math  (wrappeurs autour des fonctions air_* du runtime)
 * ═══════════════════════════════════════════════════════════════════════════ */

double  air_math_abs(double x)            { return x < 0 ? -x : x; }
double  air_math_pow(double b, double e)  { return air_pow(b, e);   }
double  air_math_sqrt(double x)           { return air_sqrt(x);     }
double  air_math_floor(double x)          { return (double)air_floor(x); }
double  air_math_ceil(double x)           { return (double)air_ceil(x);  }
double  air_math_round(double x)          { return (double)air_round(x); }
double  air_math_min(double a, double b)  { return a < b ? a : b;   }
double  air_math_max(double a, double b)  { return a > b ? a : b;   }
double  air_math_random(void)             { return air_random();     }

double air_math_clamp(double v, double lo, double hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

int64_t air_math_random_int(int64_t lo, int64_t hi) {
    if (lo > hi) { int64_t t = lo; lo = hi; hi = t; }
    return lo + (int64_t)(air_random() * (double)(hi - lo + 1));
}

double air_math_log(double x)  { return log(x);   }
double air_math_log2(double x) { return log2(x);  }
double air_math_log10(double x){ return log10(x); }
double air_math_sin(double x)  { return sin(x);   }
double air_math_cos(double x)  { return cos(x);   }
double air_math_tan(double x)  { return tan(x);   }
double air_math_atan2(double y, double x) { return atan2(y, x); }


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : time
 * ═══════════════════════════════════════════════════════════════════════════ */

int64_t air_time_now(void)  { return (int64_t)time(NULL); }
void    air_time_sleep(int64_t ms) { AIR_SLEEP(ms); }

AirStr air_time_format(int64_t ts) {
    time_t t = (time_t)ts;
    struct tm* ti = localtime(&t);
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", ti);
    return air_str(buf);
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : os
 * ═══════════════════════════════════════════════════════════════════════════ */

static int    _air_argc = 0;
static char** _air_argv = NULL;

void air_os_init(int argc, char** argv) { _air_argc = argc; _air_argv = argv; }

AirList* air_os_args(void) {
    AirList* lst = air_list_empty();
    for (int i = 0; i < _air_argc; i++) {
        AirStr* s = (AirStr*)air_alloc(sizeof(AirStr));
        *s = air_str(_air_argv[i]);
        air_list_append(lst, (AirVal)s);
    }
    return lst;
}

AirStr air_os_env(AirStr name) {
    const char* val = getenv(name.data);
    return val ? air_str(val) : air_str("");
}

void air_os_exit(int64_t code) { exit((int)code); }

AirStr air_os_cwd(void) {
    char buf[4096];
#ifdef _WIN32
    GetCurrentDirectoryA(sizeof(buf), buf);
#else
    if (!getcwd(buf, sizeof(buf))) buf[0] = '\0';
#endif
    return air_str(buf);
}


/* ═══════════════════════════════════════════════════════════════════════════
 * MODULE : json  (stringify basique)
 * ═══════════════════════════════════════════════════════════════════════════ */

AirStr air_json_stringify_string(AirStr s) {
    char* buf = (char*)air_alloc(s.len * 2 + 4);
    char* out = buf;
    *out++ = '"';
    for (size_t i = 0; i < s.len; i++) {
        unsigned char c = (unsigned char)s.data[i];
        switch (c) {
            case '"':  *out++ = '\\'; *out++ = '"';  break;
            case '\\': *out++ = '\\'; *out++ = '\\'; break;
            case '\n': *out++ = '\\'; *out++ = 'n';  break;
            case '\r': *out++ = '\\'; *out++ = 'r';  break;
            case '\t': *out++ = '\\'; *out++ = 't';  break;
            default:
                if (c < 0x20) { out += sprintf(out, "\\u%04x", c); }
                else *out++ = (char)c;
        }
    }
    *out++ = '"'; *out = '\0';
    AirStr result = air_str_n(buf, (size_t)(out - buf));
    air_free(buf);
    return result;
}

AirStr air_json_int_to_string(int64_t n) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%lld", (long long)n);
    return air_str(buf);
}

AirStr air_json_float_to_string(double f) {
    char buf[64];
    snprintf(buf, sizeof(buf), "%g", f);
    return air_str(buf);
}
