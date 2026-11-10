// runtime.c — ECL 运行时库（支持异常处理）
// 编译: cl /c /O1 /GS- /Zl /nologo /utf-8 runtime.c
// 链接: link /NODEFAULTLIB /ENTRY:startup test.obj runtime.obj setjmp.obj kernel32.lib

#include <stdint.h>

typedef void* HANDLE;
typedef unsigned long DWORD;
typedef int BOOL;
typedef uint16_t wchar_t;

#define STD_OUTPUT_HANDLE ((DWORD)-11)
#define CP_UTF8  65001
#define CP_GBK   936

__declspec(dllimport) HANDLE __stdcall GetStdHandle(DWORD nStdHandle);
__declspec(dllimport) BOOL __stdcall WriteFile(HANDLE hFile, const void* lpBuffer, DWORD nNumberOfBytesToWrite, DWORD* lpNumberOfBytesWritten, void* lpOverlapped);
__declspec(dllimport) void __stdcall ExitProcess(DWORD uExitCode);
__declspec(dllimport) void* __stdcall VirtualAlloc(void* lpAddress, uint64_t dwSize, DWORD flAllocationType, DWORD flProtect);
__declspec(dllimport) int __stdcall MultiByteToWideChar(unsigned int CodePage, DWORD dwFlags, const char* lpMultiByteStr, int cbMultiByte, wchar_t* lpWideCharStr, int cchWideChar);
__declspec(dllimport) int __stdcall WideCharToMultiByte(unsigned int CodePage, DWORD dwFlags, const wchar_t* lpWideCharStr, int cchWideChar, char* lpMultiByteStr, int cbMultiByte, const char* lpDefaultChar, BOOL* lpUsedDefaultChar);

#define MEM_COMMIT 0x1000
#define MEM_RESERVE 0x2000
#define PAGE_READWRITE 0x04

int _fltused = 0;

// 手写 CRT 基础函数
void* memcpy(void* dst, const void* src, uint64_t n) {
    unsigned char* d = (unsigned char*)dst;
    const unsigned char* s = (const unsigned char*)src;
    while (n--) *d++ = *s++;
    return dst;
}
void* memset(void* dst, int c, uint64_t n) {
    unsigned char* d = (unsigned char*)dst;
    while (n--) *d++ = (unsigned char)c;
    return dst;
}
static int my_strcmp(const char* a, const char* b) {
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}
static char* my_strcpy(char* dst, const char* src) {
    char* d = dst;
    while ((*d++ = *src++)) {}
    return dst;
}
static int64_t my_strlen(const char* s) {
    int64_t n = 0;
    while (*s++) n++;
    return n;
}
static char* my_strdup(const char* s) {
    int64_t len = my_strlen(s);
    char* p = (char*)VirtualAlloc(0, len + 1, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!p) return 0;
    my_strcpy(p, s);
    return p;
}
static int itoa10(int64_t v, char* buf) {
    char tmp[32]; int n = 0, neg = 0;
    if (v < 0) { neg = 1; v = -v; }
    if (v == 0) tmp[n++] = '0';
    while (v > 0) { tmp[n++] = '0' + (v % 10); v /= 10; }
    int k = 0; if (neg) buf[k++] = '-';
    for (int i = n - 1; i >= 0; i--) buf[k++] = tmp[i];
    return k;
}
static char* my_itoa(int64_t v) {
    char buf[32]; int n = itoa10(v, buf); buf[n] = 0;
    return my_strdup(buf);
}
static int dtoa(double f, char* buf) {
    int n = 0, neg = 0;
    if (f < 0) { neg = 1; f = -f; }
    int64_t ip = (int64_t)f; double fp = f - (double)ip;
    if (neg) buf[n++] = '-';
    n += itoa10(ip, buf + n);
    if (fp > 1e-12) {
        buf[n++] = '.'; int digits = 6;
        for (int i = 0; i < digits; i++) {
            fp *= 10.0; int d = (int)fp; if (d > 9) d = 9;
            buf[n++] = '0' + d; fp -= d; if (fp < 1e-12) break;
        }
        while (n > 0 && buf[n - 1] == '0') n--;
        if (n > 0 && buf[n - 1] == '.') n++;
    } else { buf[n++] = '.'; buf[n++] = '0'; }
    return n;
}
static char* my_dtoa(double f) {
    char buf[64]; int n = dtoa(f, buf); buf[n] = 0;
    return my_strdup(buf);
}

// ============================================================
// 异常处理机制
// ============================================================
typedef struct {
    int64_t rbx, rbp, rdi, rsi, rsp, r12, r13, r14, r15, rip;
} jmp_buf_t;

int64_t runtime_setjmp(jmp_buf_t* env);
void runtime_longjmp(jmp_buf_t* env, int64_t val);

#define MAX_TRY_DEPTH 32
static jmp_buf_t* exception_stack[MAX_TRY_DEPTH];
static int exception_depth = 0;

static void write_str(const char* s, int64_t len) {
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE); DWORD written;
    WriteFile(h, s, (DWORD)len, &written, 0);
}

void runtime_raise_error(const char* msg) {
    if (exception_depth > 0) {
        exception_depth--;
        runtime_longjmp(exception_stack[exception_depth], 1);
    }
    write_str("Unhandled Exception: ", 21);
    write_str(msg, my_strlen(msg));
    write_str("\n", 1);
    ExitProcess(1);
}

void runtime_push_exception(jmp_buf_t* env) {
    if (exception_depth < MAX_TRY_DEPTH) {
        exception_stack[exception_depth++] = env;
    }
}

void runtime_pop_exception() {
    if (exception_depth > 0) exception_depth--;
}

// ============================================================
// Value 类型定义
// ============================================================
typedef enum {
    VAL_INT      = 0, VAL_FLOAT    = 1, VAL_STR      = 2, VAL_NULL     = 3,
    VAL_NONE     = 4, VAL_LIST     = 5, VAL_DICT     = 6, VAL_RANGE    = 7,
    VAL_CODE     = 8, VAL_FUNCTION = 9, VAL_CLASS    = 10, VAL_INSTANCE = 11,
    VAL_BOUND    = 12,
} ValTag;

typedef struct {
    int64_t tag;
    union {
        int64_t i; double  f; char*   s; void*   ptr;
    };
} Value;

// ============================================================
// 变量表
// ============================================================
#define HASH_SIZE 256
#define VALUE_POOL_SIZE 1048576
struct VarEntry { char* name; Value* val; struct VarEntry* next; };
static struct VarEntry* hash_table[HASH_SIZE];
static Value value_pool[VALUE_POOL_SIZE];
static int value_pool_count = 0;

static Value* alloc_value(void) {
    if (value_pool_count >= VALUE_POOL_SIZE) ExitProcess(1);
    return &value_pool[value_pool_count++];
}
static unsigned int hash_str(const char* s) {
    unsigned int h = 5381; while (*s) h = ((h << 5) + h) + (unsigned char)*s++;
    return h % HASH_SIZE;
}
Value* get_var(const char* name) {
    unsigned int h = hash_str(name);
    struct VarEntry* e = hash_table[h];
    while (e) { if (my_strcmp(e->name, name) == 0) return e->val; e = e->next; }
    struct VarEntry* ne = (struct VarEntry*)VirtualAlloc(0, sizeof(struct VarEntry), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    ne->name = my_strdup(name); ne->val = alloc_value();
    ne->val->tag = VAL_NONE; ne->val->i = 0;
    ne->next = hash_table[h]; hash_table[h] = ne;
    return ne->val;
}

// ============================================================
// 类 / 实例 / 容器结构
// ============================================================
typedef struct EclMethod { char* name; void* code; int nparams; struct EclMethod* next; } EclMethod;
typedef struct EclClass { char* name; EclMethod* methods; } EclClass;
typedef struct EclAttr { char* name; Value value; struct EclAttr* next; } EclAttr;
typedef struct EclInstance { EclClass* cls; EclAttr* attrs; } EclInstance;
typedef struct EclBoundMethod { EclInstance* self; EclMethod* m; } EclBoundMethod;
typedef void (*EclFuncPtr)(Value* result, Value** args, int argc);

typedef struct EclList { int64_t len, cap; Value* items; } EclList;
typedef struct EclDictEntry { Value key; Value val; struct EclDictEntry* next; } EclDictEntry;
typedef struct EclDict { int64_t size; EclDictEntry* head; } EclDict;

static EclList* list_new() {
    EclList* l = (EclList*)VirtualAlloc(0, sizeof(EclList), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    l->len = 0; l->cap = 0; l->items = 0; return l;
}
static void list_reserve(EclList* l, int64_t need) {
    if (need <= l->cap) return;
    int64_t nc = l->cap ? l->cap * 2 : 8;
    while (nc < need) nc *= 2;
    Value* ni = (Value*)VirtualAlloc(0, nc * sizeof(Value), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    for (int64_t i = 0; i < l->len; i++) ni[i] = l->items[i];
    l->items = ni; l->cap = nc;
}
static void list_push(EclList* l, Value v) { list_reserve(l, l->len + 1); l->items[l->len++] = v; }

static EclDict* dict_new() {
    EclDict* d = (EclDict*)VirtualAlloc(0, sizeof(EclDict), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    d->size = 0; d->head = 0; return d;
}
static int value_eq_raw(Value a, Value b) {
    if (a.tag != b.tag) return 0;
    switch (a.tag) {
        case VAL_INT: return a.i == b.i;
        case VAL_FLOAT: return a.f == b.f;
        case VAL_STR: return my_strcmp(a.s, b.s) == 0;
        case VAL_NULL: case VAL_NONE: return 1;
        default: return a.ptr == b.ptr;
    }
}
static EclDictEntry* dict_find(EclDict* d, Value key) {
    for (EclDictEntry* e = d->head; e; e = e->next) if (value_eq_raw(e->key, key)) return e;
    return 0;
}
static void dict_put(EclDict* d, Value key, Value val) {
    EclDictEntry* e = dict_find(d, key);
    if (e) { e->val = val; return; }
    e = (EclDictEntry*)VirtualAlloc(0, sizeof(EclDictEntry), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    e->key = key; e->val = val; e->next = d->head; d->head = e; d->size++;
}

static int is_dunder(const char* s) {
    int64_t n = my_strlen(s);
    return n >= 4 && s[0] == '_' && s[1] == '_' && s[n-1] == '_' && s[n-2] == '_';
}
static EclMethod* find_method(EclClass* cls, const char* name) {
    for (EclMethod* m = cls ? cls->methods : 0; m; m = m->next) if (my_strcmp(m->name, name) == 0) return m;
    return 0;
}
static EclAttr* find_attr(EclInstance* inst, const char* name) {
    for (EclAttr* a = inst->attrs; a; a = a->next) if (my_strcmp(a->name, name) == 0) return a;
    return 0;
}
static EclBoundMethod* make_bound(EclInstance* self, EclMethod* m) {
    EclBoundMethod* bm = (EclBoundMethod*)VirtualAlloc(0, sizeof(EclBoundMethod), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    bm->self = self; bm->m = m; return bm;
}

// ============================================================
// 输出打印
// ============================================================
static void write_utf8_as_gbk(const char* s, int64_t len) {
    if (len <= 0) return;
    int wlen = MultiByteToWideChar(CP_UTF8, 0, s, (int)len, 0, 0);
    if (wlen <= 0) { write_str(s, len); return; }
    wchar_t* wbuf = (wchar_t*)VirtualAlloc(0, (wlen + 1) * 2, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    MultiByteToWideChar(CP_UTF8, 0, s, (int)len, wbuf, wlen); wbuf[wlen] = 0;
    int glen = WideCharToMultiByte(CP_GBK, 0, wbuf, wlen, 0, 0, 0, 0);
    if (glen <= 0) { write_str(s, len); return; }
    char* gbuf = (char*)VirtualAlloc(0, glen, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    WideCharToMultiByte(CP_GBK, 0, wbuf, wlen, gbuf, glen, 0, 0);
    write_str(gbuf, glen);
}
static void print_value_inner(Value* v) {
    char buf[64]; int n = 0;
    switch (v->tag) {
        case VAL_INT: n = itoa10(v->i, buf); write_str(buf, n); break;
        case VAL_FLOAT: n = dtoa(v->f, buf); write_str(buf, n); break;
        case VAL_STR: write_utf8_as_gbk(v->s, my_strlen(v->s)); break;
        case VAL_NULL: write_str("null", 4); break;
        case VAL_NONE: write_str("none", 4); break;
        case VAL_FUNCTION: write_str("<function>", 10); break;
        case VAL_CLASS: {
            EclClass* c = (EclClass*)v->ptr;
            write_str("<class ", 7); write_str(c->name, my_strlen(c->name)); write_str(">", 1); break;
        }
        case VAL_INSTANCE: {
            EclInstance* inst = (EclInstance*)v->ptr;
            EclMethod* m = find_method(inst->cls, "__str__");
            if (m) {
                Value r; Value self; self.tag = VAL_INSTANCE; self.ptr = inst;
                Value* args[1]; args[0] = &self;
                ((EclFuncPtr)m->code)(&r, args, 1);
                print_value_inner(&r); return;
            }
            write_str("<", 1); write_str(inst->cls->name, my_strlen(inst->cls->name)); write_str(" object>", 8); break;
        }
        case VAL_BOUND: write_str("<bound method>", 14); break;
        case VAL_LIST: {
            EclList* l = (EclList*)v->ptr;
            write_str("[", 1);
            for (int64_t i = 0; i < l->len; i++) {
                if (i) write_str(", ", 2);
                print_value_inner(&l->items[i]);
            }
            write_str("]", 1); break;
        }
        case VAL_DICT: {
            EclDict* d = (EclDict*)v->ptr;
            write_str("{", 1); int first = 1;
            for (EclDictEntry* e = d->head; e; e = e->next) {
                if (!first) write_str(", ", 2); first = 0;
                print_value_inner(&e->key); write_str(": ", 2); print_value_inner(&e->val);
            }
            write_str("}", 1); break;
        }
        default: write_str("<value>", 7); break;
    }
}

void runtime_print(Value* v) { print_value_inner(v); write_str("\n", 1); }
void runtime_write(Value* v) { print_value_inner(v); }
void runtime_write_space(void) { write_str(" ", 1); }

int64_t runtime_truthy(Value* v) {
    switch (v->tag) {
        case VAL_INT: return v->i != 0;
        case VAL_FLOAT: return v->f != 0.0;
        case VAL_STR: return v->s && v->s[0] != '\0';
        case VAL_NULL: return 0; case VAL_NONE: return 0;
        case VAL_LIST: return ((EclList*)v->ptr)->len != 0;
        case VAL_DICT: return ((EclDict*)v->ptr)->size != 0;
        default: return 1;
    }
}

// ============================================================
// 运算与异常拦截
// ============================================================
void runtime_add(Value* result, Value* a, Value* b) {
    if (a->tag == VAL_INT && b->tag == VAL_INT) { result->tag = VAL_INT; result->i = a->i + b->i; }
    else if (a->tag == VAL_FLOAT && b->tag == VAL_FLOAT) { result->tag = VAL_FLOAT; result->f = a->f + b->f; }
    else if (a->tag == VAL_INT && b->tag == VAL_FLOAT) { result->tag = VAL_FLOAT; result->f = (double)a->i + b->f; }
    else if (a->tag == VAL_FLOAT && b->tag == VAL_INT) { result->tag = VAL_FLOAT; result->f = a->f + (double)b->i; }
    else if (a->tag == VAL_STR && b->tag == VAL_STR) {
        int64_t la = my_strlen(a->s), lb = my_strlen(b->s);
        char* p = (char*)VirtualAlloc(0, la + lb + 1, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        my_strcpy(p, a->s); my_strcpy(p + la, b->s);
        result->tag = VAL_STR; result->s = p;
    } else { result->tag = VAL_NONE; result->i = 0; }
}
void runtime_sub(Value* result, Value* a, Value* b) {
    if (a->tag == VAL_INT && b->tag == VAL_INT) { result->tag = VAL_INT; result->i = a->i - b->i; }
    else { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->tag = VAL_FLOAT; result->f = af - bf; }
}
void runtime_mul(Value* result, Value* a, Value* b) {
    if (a->tag == VAL_INT && b->tag == VAL_INT) { result->tag = VAL_INT; result->i = a->i * b->i; }
    else { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->tag = VAL_FLOAT; result->f = af * bf; }
}
void runtime_div(Value* result, Value* a, Value* b) {
    if (b->tag == VAL_INT && b->i == 0) runtime_raise_error("ZeroDivisionError");
    if (b->tag == VAL_FLOAT && b->f == 0.0) runtime_raise_error("ZeroDivisionError");
    if (a->tag == VAL_INT && b->tag == VAL_INT) { result->tag = VAL_FLOAT; result->f = (double)a->i / (double)b->i; }
    else { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->tag = VAL_FLOAT; result->f = af / bf; }
}
void runtime_floordiv(Value* result, Value* a, Value* b) {
    if (b->tag == VAL_INT && b->i == 0) runtime_raise_error("ZeroDivisionError");
    if (b->tag == VAL_FLOAT && b->f == 0.0) runtime_raise_error("ZeroDivisionError");
    if (a->tag == VAL_INT && b->tag == VAL_INT) { result->tag = VAL_INT; result->i = a->i / b->i; }
    else { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; double q = af / bf; int64_t iq = (int64_t)q; if ((double)iq > q) iq--; result->tag = VAL_FLOAT; result->f = (double)iq; }
}
void runtime_mod(Value* result, Value* a, Value* b) {
    if (b->tag == VAL_INT && b->i == 0) runtime_raise_error("ZeroDivisionError");
    if (b->tag == VAL_FLOAT && b->f == 0.0) runtime_raise_error("ZeroDivisionError");
    if (a->tag == VAL_INT && b->tag == VAL_INT) { result->tag = VAL_INT; result->i = a->i % b->i; }
    else { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->tag = VAL_FLOAT; result->f = af - bf * (double)((int64_t)(af / bf)); }
}
void runtime_pow(Value* result, Value* a, Value* b) {
    if (a->tag == VAL_FLOAT || b->tag == VAL_FLOAT) {
        double base = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double exp = (b->tag == VAL_FLOAT) ? b->f : (double)b->i;
        int64_t iexp = (int64_t)exp; double r = 1.0; int neg = iexp < 0; if (neg) iexp = -iexp;
        while (iexp > 0) { if (iexp & 1) r *= base; base *= base; iexp >>= 1; }
        result->tag = VAL_FLOAT; result->f = neg ? 1.0 / r : r; return;
    }
    int64_t base = a->i, exp = b->i, r = 1; while (exp > 0) { if (exp & 1) r *= base; base *= base; exp >>= 1; }
    result->tag = VAL_INT; result->i = r;
}
void runtime_eq(Value* result, Value* a, Value* b) {
    int eq = 0;
    if (a->tag == VAL_INT && b->tag == VAL_INT) eq = a->i == b->i;
    else if (a->tag == VAL_FLOAT || b->tag == VAL_FLOAT) { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; eq = af == bf; }
    else if (a->tag == b->tag) {
        switch (a->tag) {
            case VAL_STR: eq = my_strcmp(a->s, b->s) == 0; break;
            case VAL_NULL: eq = 1; break; case VAL_NONE: eq = 1; break;
            case VAL_INSTANCE: eq = a->ptr == b->ptr; break;
            default: eq = 0;
        }
    }
    result->tag = VAL_INT; result->i = eq;
}
void runtime_ne(Value* result, Value* a, Value* b) { runtime_eq(result, a, b); result->i = !result->i; }
void runtime_lt(Value* result, Value* a, Value* b) {
    result->tag = VAL_INT;
    if (a->tag == VAL_STR && b->tag == VAL_STR) result->i = my_strcmp(a->s, b->s) < 0;
    else if (a->tag == VAL_FLOAT || b->tag == VAL_FLOAT) { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->i = af < bf; }
    else result->i = a->i < b->i;
}
void runtime_gt(Value* result, Value* a, Value* b) {
    result->tag = VAL_INT;
    if (a->tag == VAL_STR && b->tag == VAL_STR) result->i = my_strcmp(a->s, b->s) > 0;
    else if (a->tag == VAL_FLOAT || b->tag == VAL_FLOAT) { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->i = af > bf; }
    else result->i = a->i > b->i;
}
void runtime_le(Value* result, Value* a, Value* b) {
    result->tag = VAL_INT;
    if (a->tag == VAL_STR && b->tag == VAL_STR) result->i = my_strcmp(a->s, b->s) <= 0;
    else if (a->tag == VAL_FLOAT || b->tag == VAL_FLOAT) { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->i = af <= bf; }
    else result->i = a->i <= b->i;
}
void runtime_ge(Value* result, Value* a, Value* b) {
    result->tag = VAL_INT;
    if (a->tag == VAL_STR && b->tag == VAL_STR) result->i = my_strcmp(a->s, b->s) >= 0;
    else if (a->tag == VAL_FLOAT || b->tag == VAL_FLOAT) { double af = (a->tag == VAL_FLOAT) ? a->f : (double)a->i; double bf = (b->tag == VAL_FLOAT) ? b->f : (double)b->i; result->i = af >= bf; }
    else result->i = a->i >= b->i;
}

// ============================================================
// 函数调用与类机制
// ============================================================
typedef struct EclFunction { char* name; void* code; int param_count; Value* defaults; } EclFunction;
void runtime_new_function(Value* result, const char* name, void* code, int param_count) {
    EclFunction* fn = (EclFunction*)VirtualAlloc(0, sizeof(EclFunction), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    fn->name = my_strdup(name); fn->code = code; fn->param_count = param_count; fn->defaults = 0;
    result->tag = VAL_FUNCTION; result->ptr = fn;
}
void runtime_func_set_defaults(Value* fn_val, Value* defaults) {
    if (fn_val->tag != VAL_FUNCTION) return;
    EclFunction* fn = (EclFunction*)fn_val->ptr;
    fn->defaults = (Value*)VirtualAlloc(0, fn->param_count * sizeof(Value), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    for (int i = 0; i < fn->param_count; i++) fn->defaults[i] = defaults[i];
}
static void invoke_method(Value* out, EclMethod* m, EclInstance* self, Value** args, int argc) {
    Value self_val; self_val.tag = VAL_INSTANCE; self_val.ptr = self;
    Value* a[17]; a[0] = &self_val;
    a[1] = (argc >= 1) ? args[0] : 0; a[2] = (argc >= 2) ? args[1] : 0; a[3] = (argc >= 3) ? args[2] : 0;
    a[4] = (argc >= 4) ? args[3] : 0; a[5] = (argc >= 5) ? args[4] : 0; a[6] = (argc >= 6) ? args[5] : 0;
    a[7] = (argc >= 7) ? args[6] : 0; a[8] = (argc >= 8) ? args[7] : 0; a[9] = (argc >= 9) ? args[8] : 0;
    a[10]= (argc >=10) ? args[9] : 0; a[11]= (argc >=11) ? args[10]: 0; a[12]= (argc >=12) ? args[11]: 0;
    a[13]= (argc >=13) ? args[12]: 0; a[14]= (argc >=14) ? args[13]: 0; a[15]= (argc >=15) ? args[14]: 0;
    a[16]= (argc >=16) ? args[15]: 0;
    int n = argc + 1; if (n > 17) n = 17;
    ((EclFuncPtr)m->code)(out, a, n);
}
void runtime_call(Value* result, Value* f, Value** args, int argc) {
    if (f->tag == VAL_CLASS) {
        EclClass* cls = (EclClass*)f->ptr;
        EclInstance* inst = (EclInstance*)VirtualAlloc(0, sizeof(EclInstance), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        inst->cls = cls; inst->attrs = 0; result->tag = VAL_INSTANCE; result->ptr = inst;
        EclMethod* init = find_method(cls, "__init__");
        if (init) invoke_method(&(Value){0}, init, inst, args, argc);
        return;
    }
    if (f->tag == VAL_BOUND) {
        EclBoundMethod* bm = (EclBoundMethod*)f->ptr;
        invoke_method(result, bm->m, bm->self, args, argc);
        return;
    }
    if (f->tag == VAL_FUNCTION) {
        EclFunction* fn = (EclFunction*)f->ptr;
        if (argc < fn->param_count && fn->defaults) {
            Value* new_args[16];
            for (int i = 0; i < argc; i++) new_args[i] = args[i];
            for (int i = argc; i < fn->param_count; i++) new_args[i] = &fn->defaults[i];
            ((EclFuncPtr)fn->code)(result, new_args, fn->param_count);
            return;
        }
        ((EclFuncPtr)fn->code)(result, args, argc);
        return;
    }
    result->tag = VAL_NONE; result->i = 0;
}
void runtime_new_class(EclClass** out, const char* name) {
    EclClass* c = (EclClass*)VirtualAlloc(0, sizeof(EclClass), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    c->name = my_strdup(name); c->methods = 0; *out = c;
}
void runtime_class_add_method(EclClass* cls, const char* name, void* code, int64_t nparams) {
    EclMethod* m = (EclMethod*)VirtualAlloc(0, sizeof(EclMethod), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    m->name = my_strdup(name); m->code = code; m->nparams = (int)nparams; m->next = cls->methods; cls->methods = m;
}

// ============================================================
// 属性读写与容器
// ============================================================
void runtime_get_attr(Value* out, Value* obj, const char* name) {
    if (obj->tag == VAL_INSTANCE) {
        EclInstance* inst = (EclInstance*)obj->ptr;
        EclAttr* a = find_attr(inst, name);
        if (a) { *out = a->value; return; }
        EclMethod* m = find_method(inst->cls, name);
        if (m) { out->tag = VAL_BOUND; out->ptr = make_bound(inst, m); return; }
        if (is_dunder(name)) { out->tag = VAL_NULL; out->i = 0; return; }
        out->tag = VAL_NONE; out->i = 0; return;
    }
    if (obj->tag == VAL_CLASS) {
        EclClass* cls = (EclClass*)obj->ptr;
        EclMethod* m = find_method(cls, name);
        if (m) { out->tag = VAL_FUNCTION; out->ptr = m->code; return; }
        if (is_dunder(name)) { out->tag = VAL_NULL; out->i = 0; return; }
        out->tag = VAL_NONE; out->i = 0; return;
    }
    if (obj->tag == VAL_LIST) {
        if (my_strcmp(name, "append") == 0) { out->tag = VAL_FUNCTION; out->ptr = (void*)1; return; }
    }
    out->tag = VAL_NONE; out->i = 0;
}
void runtime_set_attr(Value* obj, const char* name, Value* v) {
    if (obj->tag == VAL_INSTANCE) {
        EclInstance* inst = (EclInstance*)obj->ptr;
        EclAttr* a = find_attr(inst, name);
        if (a) { a->value = *v; return; }
        a = (EclAttr*)VirtualAlloc(0, sizeof(EclAttr), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        a->name = my_strdup(name); a->value = *v; a->next = inst->attrs; inst->attrs = a;
    }
}
void runtime_new_list(Value* out) { out->tag = VAL_LIST; out->ptr = list_new(); }
void runtime_list_append(Value* list_val, Value* item) {
    if (list_val->tag != VAL_LIST) return;
    list_push((EclList*)list_val->ptr, *item);
}
void runtime_new_dict(Value* out) { out->tag = VAL_DICT; out->ptr = dict_new(); }
void runtime_dict_set(Value* dict_val, Value* key, Value* val) {
    if (dict_val->tag != VAL_DICT) return;
    dict_put((EclDict*)dict_val->ptr, *key, *val);
}
void runtime_get_item(Value* out, Value* obj, Value* idx) {
    if (obj->tag == VAL_LIST && idx->tag == VAL_INT) {
        EclList* l = (EclList*)obj->ptr; int64_t i = idx->i;
        if (i < 0) i += l->len;
        if (i < 0 || i >= l->len) { out->tag = VAL_NONE; out->i = 0; return; }
        *out = l->items[i]; return;
    }
    if (obj->tag == VAL_DICT) {
        EclDict* d = (EclDict*)obj->ptr;
        EclDictEntry* e = dict_find(d, *idx);
        if (e) { *out = e->val; return; }
        out->tag = VAL_NONE; out->i = 0; return;
    }
    out->tag = VAL_NONE; out->i = 0;
}
void runtime_set_item(Value* obj, Value* idx, Value* val) {
    if (obj->tag == VAL_LIST && idx->tag == VAL_INT) {
        EclList* l = (EclList*)obj->ptr; int64_t i = idx->i;
        if (i < 0) i += l->len;
        if (i < 0 || i >= l->len) return;
        l->items[i] = *val; return;
    }
    if (obj->tag == VAL_DICT) dict_put((EclDict*)obj->ptr, *idx, *val);
}

// ============================================================
// 内置函数
// ============================================================
void runtime_str(Value* result, Value* v) {
    switch (v->tag) {
        case VAL_INT: result->tag = VAL_STR; result->s = my_itoa(v->i); break;
        case VAL_FLOAT: result->tag = VAL_STR; result->s = my_dtoa(v->f); break;
        case VAL_STR: result->tag = VAL_STR; result->s = v->s; break;
        case VAL_NULL: result->tag = VAL_STR; result->s = my_strdup("null"); break;
        case VAL_NONE: result->tag = VAL_STR; result->s = my_strdup("none"); break;
        case VAL_INSTANCE: {
            EclInstance* inst = (EclInstance*)v->ptr;
            EclMethod* m = find_method(inst->cls, "__str__");
            if (m) { Value self; self.tag = VAL_INSTANCE; self.ptr = inst; Value* args[1] = {&self}; ((EclFuncPtr)m->code)(result, args, 1); return; }
            result->tag = VAL_STR; result->s = my_strdup("<object>"); break;
        }
        default: result->tag = VAL_STR; result->s = my_strdup("<value>"); break;
    }
}
void runtime_len(Value* result, Value* v) {
    result->tag = VAL_INT;
    if (v->tag == VAL_STR) result->i = my_strlen(v->s);
    else if (v->tag == VAL_LIST) result->i = ((EclList*)v->ptr)->len;
    else if (v->tag == VAL_DICT) result->i = ((EclDict*)v->ptr)->size;
    else result->i = 0;
}
void runtime_int(Value* result, Value* v) {
    result->tag = VAL_INT;
    if (v->tag == VAL_INT) result->i = v->i;
    else if (v->tag == VAL_FLOAT) result->i = (int64_t)v->f;
    else result->i = 0;
}
void runtime_float(Value* result, Value* v) {
    result->tag = VAL_FLOAT;
    if (v->tag == VAL_FLOAT) result->f = v->f;
    else if (v->tag == VAL_INT) result->f = (double)v->i;
    else result->f = 0.0;
}
void runtime_bool(Value* result, Value* v) { result->tag = VAL_INT; result->i = runtime_truthy(v); }
void runtime_type(Value* result, Value* v) {
    result->tag = VAL_STR;
    switch (v->tag) {
        case VAL_INT: result->s = my_strdup("int"); break;
        case VAL_FLOAT: result->s = my_strdup("float"); break;
        case VAL_STR: result->s = my_strdup("str"); break;
        case VAL_LIST: result->s = my_strdup("list"); break;
        case VAL_DICT: result->s = my_strdup("dict"); break;
        case VAL_INSTANCE: result->s = ((EclInstance*)v->ptr)->cls->name; break;
        default: result->s = my_strdup("unknown"); break;
    }
}
void runtime_range(Value* result, Value* start, Value* end) { result->tag = VAL_NONE; result->i = 0; }

// ============================================================
// 入口
// ============================================================
__declspec(noreturn) void startup(void);
extern int main(void);
__declspec(noreturn) void startup(void) { int r = main(); ExitProcess((DWORD)r); }