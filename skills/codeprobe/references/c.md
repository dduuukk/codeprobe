# C Reference Guide

## Naming Conventions

| Element                       | Convention                                                 | Flag If                                           |
| ----------------------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| Variables, functions          | `snake_case`                                               | `camelCase` or `PascalCase` used                  |
| Types (`typedef`, `struct`)   | `PascalCase` or `snake_case_t`                             | Inconsistent within a codebase                    |
| Macros, constants (`#define`) | `UPPER_SNAKE_CASE`                                         | Lowercase macros (shadow variables, hard to spot) |
| Global variables              | `g_` prefix or module-scoped `static`                      | Unscoped globals with no prefix                   |
| Header guards                 | `PROJECT_MODULE_H`                                         | Missing or duplicated include guards              |
| Function prefixes             | Module-prefix all public functions: `http_parse_request()` | Flat global namespace without module prefix       |

---

## Memory Management

### Allocation & Deallocation

| Anti-pattern                                    | Severity | Fix                                                                              |
| ----------------------------------------------- | -------- | -------------------------------------------------------------------------------- |
| `malloc` result unchecked                       | Critical | Always check for `NULL` before use                                               |
| Memory allocated but never freed                | Major    | Every `malloc` needs a matching `free` on all paths                              |
| Double free                                     | Critical | Set pointer to `NULL` immediately after `free`                                   |
| Use after free                                  | Critical | Set pointer to `NULL` after `free`; never access freed memory                    |
| `realloc` result discarded                      | Critical | `realloc` can return `NULL` on failure — assign to a temp pointer first          |
| `free` on stack-allocated memory                | Critical | Only `free` memory from `malloc`/`calloc`/`realloc`                              |
| `malloc` without `calloc` when zero-init needed | Minor    | Use `calloc` for zero-initialized allocations; avoids reading uninitialized data |

```c
/* BAD: unchecked malloc, potential leak on early return */
char *buf = malloc(size);
if (parse_failed) {
    return -1;  /* leak: buf never freed */
}
free(buf);

/* GOOD: check allocation, free on all paths */
char *buf = malloc(size);
if (buf == NULL) {
    return -ENOMEM;
}
if (parse_failed) {
    free(buf);
    return -1;
}
free(buf);
buf = NULL;

/* BAD: realloc overwrites original pointer — loses it on failure */
ptr = realloc(ptr, new_size);
if (ptr == NULL) { /* original ptr is now lost */ }

/* GOOD: use a temporary */
void *tmp = realloc(ptr, new_size);
if (tmp == NULL) {
    free(ptr);
    return -ENOMEM;
}
ptr = tmp;
```

---

## Buffer Overflows & String Safety

| Anti-pattern                                     | Severity | Fix                                                                                  |
| ------------------------------------------------ | -------- | ------------------------------------------------------------------------------------ |
| `strcpy(dst, src)`                               | Critical | Use `strncpy(dst, src, dst_size - 1)` + null-terminate, or `strlcpy` where available |
| `strcat(dst, src)`                               | Critical | Use `strncat` or track remaining capacity manually                                   |
| `sprintf(buf, fmt, ...)`                         | Critical | Use `snprintf(buf, sizeof(buf), fmt, ...)`                                           |
| `gets(buf)`                                      | Critical | Removed in C11 — use `fgets(buf, sizeof(buf), stdin)`                                |
| `scanf("%s", buf)`                               | Critical | Use `scanf("%255s", buf)` with an explicit width limit                               |
| Fixed-size stack buffer for user input           | Major    | Validate input length before copy; prefer heap allocation with known bounds          |
| `strlen` on potentially non-null-terminated data | Major    | Ensure buffers are always null-terminated or use explicit length tracking            |

```c
/* BAD: classic buffer overflow */
char buf[64];
strcpy(buf, user_input);   /* overflows if input > 63 bytes */
sprintf(buf, "Hello %s", name);  /* same problem */

/* GOOD: bounded copies */
char buf[64];
strncpy(buf, user_input, sizeof(buf) - 1);
buf[sizeof(buf) - 1] = '\0';

snprintf(buf, sizeof(buf), "Hello %s", name);
```

---

## Undefined Behavior

| Pattern                                     | Why It's UB                                                   | Fix                                                                       |
| ------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Signed integer overflow                     | C standard says it's UB — compiler may optimize it away       | Use unsigned arithmetic or check before operation: `if (a > INT_MAX - b)` |
| Reading uninitialized variables             | Value is indeterminate; compilers may assume it never happens | Always initialize variables at declaration                                |
| Out-of-bounds array access                  | UB even if the memory "happens to be accessible"              | Validate index before access                                              |
| Dereferencing `NULL` or dangling pointer    | UB — no guaranteed segfault                                   | Check pointers before dereferencing                                       |
| Shifting by negative amount or >= bit width | UB in C                                                       | Validate shift amount: `0 <= n < sizeof(type) * CHAR_BIT`                 |
| Modifying a string literal                  | UB — string literals may be in read-only memory               | Use `char buf[] = "..."` for mutable strings, not `char *p = "..."`       |
| Strict aliasing violation                   | Compiler may reorder or elide loads/stores                    | Use `memcpy` for type-punning; or `union` (C99+)                          |

```c
/* BAD: UB — signed overflow */
int a = INT_MAX;
int b = a + 1;  /* undefined behavior */

/* GOOD: check before operation */
if (a > INT_MAX - 1) {
    return -EOVERFLOW;
}
int b = a + 1;

/* BAD: uninitialized read */
int result;
if (condition) {
    result = compute();
}
return result;  /* UB if condition was false */

/* GOOD: always initialize */
int result = 0;
if (condition) {
    result = compute();
}
return result;
```

---

## Pointer Safety

| Anti-pattern                                                      | Severity | Fix                                                                               |
| ----------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------- |
| Pointer arithmetic beyond array bounds                            | Critical | Stay within `[ptr, ptr + n)` for an array of size `n`                             |
| Returning pointer to local variable                               | Critical | Local stack frame is invalid after return — heap-allocate or use output parameter |
| Casting away `const`                                              | Major    | Signals broken API design; fix the const-correctness instead                      |
| Void pointer arithmetic                                           | Major    | UB in C — cast to `char *` first for byte-level arithmetic                        |
| Function pointer called without null check                        | Major    | Always check function pointer is non-NULL before calling                          |
| `int *p = (int *)malloc(n)` where `n` is element count, not bytes | Critical | `malloc(n * sizeof(int))` or `malloc(n * sizeof(*p))`                             |

```c
/* BAD: returns pointer to stack variable */
int *get_value(void) {
    int x = 42;
    return &x;  /* dangling pointer */
}

/* GOOD: heap allocate */
int *get_value(void) {
    int *x = malloc(sizeof(int));
    if (x != NULL) *x = 42;
    return x;  /* caller must free */
}

/* BAD: wrong malloc size */
int *arr = malloc(count);          /* allocates count bytes, not count ints */

/* GOOD */
int *arr = malloc(count * sizeof(*arr));
```

---

## Error Handling

| Anti-pattern                                                  | Correct Pattern                                                                            | Why                                            |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------- |
| Ignoring return values from `fclose`, `fwrite`, `munmap`      | Check all I/O return values                                                                | Silent data loss on write failures             |
| Using `errno` without checking return value first             | Check return value for error, then inspect `errno`                                         | `errno` is only meaningful after a failed call |
| Mixing error codes and valid return values in the same range  | Use `int` with negative = error, non-negative = success (POSIX style), or output parameter | Callers can't distinguish success from failure |
| No cleanup on error path                                      | Use `goto cleanup` pattern for multi-resource functions                                    | Prevents leaks and ensures consistent teardown |
| `perror`/`fprintf` as the only error handling in library code | Libraries should return error codes, not print                                             | Callers should decide how to report errors     |

```c
/* BAD: ignored errors, no cleanup on failure */
FILE *f = fopen(path, "r");
char *buf = malloc(size);
fread(buf, 1, size, f);
process(buf);
free(buf);
fclose(f);

/* GOOD: check errors, goto cleanup */
int result = 0;
FILE *f = fopen(path, "r");
if (f == NULL) { return -errno; }

char *buf = malloc(size);
if (buf == NULL) { result = -ENOMEM; goto close_file; }

if (fread(buf, 1, size, f) != size) {
    result = -EIO;
    goto free_buf;
}

process(buf);

free_buf:
    free(buf);
close_file:
    fclose(f);
return result;
```

---

## Preprocessor & Macros

| Anti-pattern                                           | Why                                           | Fix                                                                   |
| ------------------------------------------------------ | --------------------------------------------- | --------------------------------------------------------------------- |
| Function-like macro with unparenthesized args          | Operator precedence bugs                      | Wrap every argument and the whole expression in parens                |
| Multi-statement macro not wrapped in `do { } while(0)` | Breaks `if/else` without braces               | Use `do { ... } while(0)`                                             |
| Macro with side-effectful argument evaluated twice     | `MAX(i++, j++)` increments twice              | Use inline functions or `__typeof__` (GCC) to avoid double evaluation |
| Missing include guards                                 | Multiple inclusion causes redefinition errors | Add `#ifndef PROJECT_MODULE_H` / `#define` / `#endif`                 |
| Magic numbers via `#define` for types needing scope    | No type safety, no debugger visibility        | Use `enum` or `const` typed variables instead                         |

```c
/* BAD: argument evaluated twice, no parens */
#define MAX(a, b) a > b ? a : b

int x = MAX(i++, j);  /* i incremented twice if i > j */
int y = 2 * MAX(a, b);  /* expands to: 2 * a > b ? a : b — wrong precedence */

/* GOOD: fully parenthesized, do-while wrapper */
#define MAX(a, b) (((a) > (b)) ? (a) : (b))

/* BEST: inline function — type-safe, no double evaluation */
static inline int max_int(int a, int b) {
    return a > b ? a : b;
}

/* BAD: multi-statement macro breaks if/else */
#define SWAP(a, b) int tmp = a; a = b; b = tmp;
if (x > y)
    SWAP(x, y);  /* only first statement is inside if */
else
    do_other();

/* GOOD */
#define SWAP(a, b) do { int tmp = (a); (a) = (b); (b) = tmp; } while(0)
```

---

## Security

| Vulnerability                          | Detection Signal                                                    | Fix                                                                           |
| -------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Format string injection                | `printf(user_input)`, `fprintf(f, buf)` with user-controlled format | Always use a literal format string: `printf("%s", user_input)`                |
| Integer overflow before allocation     | `malloc(count * size)` without overflow check                       | Use `calloc(count, size)` or check: `if (count > SIZE_MAX / size)`            |
| Stack buffer overflow                  | Fixed-size buffers receiving external input                         | Validate length; use `snprintf`/`fgets` with explicit size                    |
| Path traversal                         | `open(user_path)` without canonicalization                          | Resolve with `realpath()` and verify prefix matches allowed base              |
| `system(cmd)` with user input          | Shell injection — any metachar is dangerous                         | Use `execv`/`execvp` with explicit argument array, no shell                   |
| Hardcoded credentials                  | `char *password = "secret"` in source                               | Load from environment or secure config; never commit secrets                  |
| `rand()` for security-sensitive values | `rand()` is not cryptographically random                            | Use OS CSPRNG: `getrandom()` (Linux), `arc4random()` (BSD), or `/dev/urandom` |
| Sensitive data not zeroed before free  | May remain in memory after deallocation                             | Use `explicit_bzero()` or `memset_s()` — plain `memset` may be optimized away |

```c
/* BAD: format string vulnerability */
char log_msg[256];
snprintf(log_msg, sizeof(log_msg), user_input);  /* user_input IS the format string */
printf(log_msg);

/* GOOD */
printf("%s", user_input);

/* BAD: integer overflow in allocation */
void *buf = malloc(count * element_size);  /* overflows if count * element_size > SIZE_MAX */

/* GOOD: use calloc which handles the overflow check */
void *buf = calloc(count, element_size);
if (buf == NULL) { return -ENOMEM; }

/* BAD: shell injection */
char cmd[256];
snprintf(cmd, sizeof(cmd), "ls %s", user_path);
system(cmd);  /* user_path = "; rm -rf /" */

/* GOOD: execv — no shell, args are separate */
char *args[] = { "ls", user_path, NULL };
execv("/bin/ls", args);
```

---

## Performance

| Anti-pattern                                   | Why                                         | Fix                                                                                |
| ---------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| `malloc`/`free` in a tight loop                | Heap allocation is expensive                | Pre-allocate a pool or reuse a single buffer                                       |
| Repeated `strlen` on the same string in a loop | O(n) scan each call                         | Cache the length: `size_t len = strlen(s)` before the loop                         |
| `memcpy` of structs when assignment works      | Unnecessary overhead for plain types        | Use struct assignment: `dst = src` for trivially-copyable structs                  |
| Passing large structs by value                 | Full copy on the stack                      | Pass by pointer: `void process(const MyStruct *s)`                                 |
| Cache-unfriendly linked list traversal         | Pointer chasing causes cache misses         | Prefer arrays/flat buffers for hot data; linked lists for infrequent insert/delete |
| `volatile` for cross-thread communication      | `volatile` does not provide memory ordering | Use `_Atomic` types (C11) or explicit memory fences                                |

---

## Testing

| What to Check                  | Flag If                                   | Best Practice                                                            |
| ------------------------------ | ----------------------------------------- | ------------------------------------------------------------------------ |
| Test naming                    | `test1`, `testFunc`                       | Describe behavior: `test_parse_returns_null_on_empty_input`              |
| Tests that leak memory         | Allocation in test with no free           | Run tests under Valgrind or AddressSanitizer (`-fsanitize=address`)      |
| No negative / error-path tests | Only happy-path cases                     | Test `NULL` inputs, zero sizes, max values, and allocation failure paths |
| Magic numbers in assertions    | `assert(result == 42)`                    | Use named constants so failure messages are meaningful                   |
| Global state mutated by tests  | Tests pass or fail depending on run order | Reset global state in teardown; prefer stateless functions               |

```c
/* BAD: vague name, no error path */
void test_parse(void) {
    Config *cfg = parse_config("key=val");
    assert(cfg != NULL);
    free_config(cfg);
}

/* GOOD: behavior-named, covers error path */
void test_parse_config_returns_valid_struct_for_well_formed_input(void) {
    Config *cfg = parse_config("key=val");
    assert(cfg != NULL);
    assert(strcmp(cfg->key, "key") == 0);
    free_config(cfg);
}

void test_parse_config_returns_null_on_empty_input(void) {
    Config *cfg = parse_config("");
    assert(cfg == NULL);
}

void test_parse_config_returns_null_on_null_input(void) {
    Config *cfg = parse_config(NULL);
    assert(cfg == NULL);
}
```
