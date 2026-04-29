# Rust Reference Guide

## Naming Conventions

| Element                       | Convention                                                         | Flag If                           |
| ----------------------------- | ------------------------------------------------------------------ | --------------------------------- |
| Variables, functions, modules | `snake_case`                                                       | `camelCase` or `mixedCase` used   |
| Types, traits, enums          | `PascalCase`                                                       | `snake_case` used                 |
| Constants, statics            | `UPPER_SNAKE_CASE`                                                 | `PascalCase` or lowercase used    |
| Lifetimes                     | Short lowercase: `'a`, `'db`                                       | Verbose names like `'lifetime`    |
| Generic type params           | Short `PascalCase`: `T`, `K`, `V`, `E`                             | Single lowercase letters like `t` |
| Crate names                   | `snake_case` (no hyphens in Rust code, hyphens in `Cargo.toml` ok) |                                   |

---

## Ownership & Borrowing

### Common Anti-Patterns

| Anti-pattern                                  | Why                                                       | Fix                                                  |
| --------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------- |
| `.clone()` to avoid borrow errors             | Hides ownership design flaws; unnecessary heap allocation | Restructure to borrow correctly or pass by reference |
| Cloning large structs in hot paths            | Performance cost; often avoidable                         | Pass `&T` or use `Arc<T>` for shared ownership       |
| Returning owned `String` when `&str` would do | Unnecessary allocation                                    | Return `&str` or `Cow<'_, str>`                      |
| Holding a borrow across an `await` point      | Future won't be `Send`                                    | Drop the borrow before `await` or use owned types    |
| `&mut` when immutable borrow is sufficient    | Overly restrictive API                                    | Use `&T` unless mutation is needed                   |

```rust
// BAD: cloning to avoid thinking about lifetimes
fn get_name(user: &User) -> String {
    user.name.clone()
}

// GOOD: return a reference — no allocation needed
fn get_name(user: &User) -> &str {
    &user.name
}

// BAD: clone inside a loop
for item in &items {
    process(item.data.clone());
}

// GOOD: pass by reference
for item in &items {
    process(&item.data);
}
```

---

## Error Handling

### `unwrap` and `expect` Abuse

| Signal                            | Severity | Flag If                                                  |
| --------------------------------- | -------- | -------------------------------------------------------- |
| `.unwrap()` in non-test code      | Major    | Used on `Result` or `Option` that can realistically fail |
| `.expect("msg")` in library code  | Major    | Libraries must not panic on bad input — return `Err`     |
| `.unwrap()` in test code          | OK       | Expected — panics produce clear test failures            |
| `panic!()` for recoverable errors | Major    | Use `Result` and propagate with `?`                      |
| Ignoring `Result` with `let _ =`  | Major    | Silent failure; at minimum log or propagate              |

```rust
// BAD: panics on missing env var at runtime
let db_url = std::env::var("DATABASE_URL").unwrap();

// GOOD: surface the error to the caller
let db_url = std::env::var("DATABASE_URL")
    .map_err(|_| AppError::MissingConfig("DATABASE_URL"))?;

// BAD: panic in library
pub fn parse_config(input: &str) -> Config {
    serde_json::from_str(input).unwrap()
}

// GOOD: return Result
pub fn parse_config(input: &str) -> Result<Config, serde_json::Error> {
    serde_json::from_str(input)
}
```

### Error Type Design

| Anti-pattern                                               | Correct Pattern                                        | Why                                                     |
| ---------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------- |
| `Box<dyn Error>` as public API error type                  | Define a domain-specific `enum` error type             | Callers can't match on `Box<dyn Error>`                 |
| Stringly-typed errors: `Err("user not found".to_string())` | Named enum variants: `Err(AppError::UserNotFound(id))` | Matchable; carries structured context                   |
| No `From` impls for upstream errors                        | Implement `From<UpstreamError> for AppError`           | Enables `?` operator without manual mapping             |
| Massive catch-all error enum                               | Split into domain-specific error enums                 | Avoids leaking internal errors across module boundaries |

```rust
// BAD: stringly typed, no context
fn find_user(id: u64) -> Result<User, String> {
    Err(format!("user {} not found", id))
}

// GOOD: structured, matchable, carries context
#[derive(Debug, thiserror::Error)]
pub enum UserError {
    #[error("user {0} not found")]
    NotFound(u64),
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
}

fn find_user(id: u64) -> Result<User, UserError> {
    db.query_one("SELECT ...", id).map_err(UserError::Database)
}
```

---

## Idiomatic Patterns

### Iterator Chains vs Loops

| Anti-pattern                               | Idiomatic Alternative                            |
| ------------------------------------------ | ------------------------------------------------ |
| Manual `for` loop building a `Vec`         | Iterator chain: `.filter().map().collect()`      |
| `for i in 0..items.len()` then `items[i]`  | `for item in &items` or `.iter().enumerate()`    |
| Nested loops for flat results              | `.flat_map()`                                    |
| Loop to find first match                   | `.find()` or `.position()`                       |
| Loop to check if any/all match             | `.any()` / `.all()`                              |
| Collecting into `Vec` then iterating again | Chain iterators — don't materialize intermediate |

```rust
// BAD: imperative loop
let mut names = Vec::new();
for user in &users {
    if user.active {
        names.push(user.name.to_uppercase());
    }
}

// GOOD: iterator chain
let names: Vec<String> = users.iter()
    .filter(|u| u.active)
    .map(|u| u.name.to_uppercase())
    .collect();
```

### Option Handling

| Anti-pattern                                        | Idiomatic Alternative                               |
| --------------------------------------------------- | --------------------------------------------------- |
| `if opt.is_some() { opt.unwrap() }`                 | `if let Some(val) = opt`                            |
| `match opt { Some(x) => x, None => default }`       | `opt.unwrap_or(default)`                            |
| `match opt { Some(x) => Some(f(x)), None => None }` | `opt.map(f)`                                        |
| `match opt { Some(x) => f(x), None => None }`       | `opt.and_then(f)`                                   |
| Returning `None` from function that can't fail      | Return the value directly; don't wrap unnecessarily |

```rust
// BAD
fn display_name(user: &User) -> String {
    if user.nickname.is_some() {
        user.nickname.clone().unwrap()
    } else {
        user.username.clone()
    }
}

// GOOD
fn display_name(user: &User) -> &str {
    user.nickname.as_deref().unwrap_or(&user.username)
}
```

---

## Performance

| Anti-pattern                                           | Why                                | Fix                                                             |
| ------------------------------------------------------ | ---------------------------------- | --------------------------------------------------------------- |
| Repeated `String::from` or `.to_string()` in hot paths | Heap allocation per call           | Use `&str` or pre-allocate with `String::with_capacity`         |
| `.to_string()` on a `&str` just to pass it             | Unnecessary allocation             | Accept `&str` in the function signature                         |
| `vec.iter().cloned().collect::<Vec<_>>()`              | Double allocation                  | Work with references where possible                             |
| `HashMap::new()` in a tight loop                       | Hash state reinit                  | Reuse or cache the map                                          |
| Locking a `Mutex` for reads in a read-heavy path       | Contention                         | Use `RwLock` — allows concurrent readers                        |
| `format!()` just to log                                | Allocates even if log level is off | Use structured logging macros: `tracing::debug!(field = value)` |
| `Box<dyn Trait>` in performance-critical generic code  | Virtual dispatch overhead          | Use generics with trait bounds: `fn foo<T: Trait>(t: T)`        |

```rust
// BAD: allocates a new String on every call
fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}
for user in &users {
    println!("{}", greet(&user.name));  // allocation per user
}

// GOOD: write directly to output
for user in &users {
    println!("Hello, {}!", user.name);
}
```

---

## Async / Tokio

| Anti-pattern                                    | Why                             | Fix                                                           |
| ----------------------------------------------- | ------------------------------- | ------------------------------------------------------------- |
| Blocking I/O inside `async fn`                  | Blocks the executor thread      | Use `tokio::fs`, `tokio::net`, or `spawn_blocking`            |
| `std::thread::sleep` in async code              | Blocks executor thread          | `tokio::time::sleep`                                          |
| `Mutex<T>` from `std::sync` held across `await` | Can deadlock; not `Send`        | Use `tokio::sync::Mutex` for async-held locks                 |
| Spawning tasks without handling `JoinHandle`    | Silent panics; task result lost | Store and `.await` the handle, or `tokio::spawn` + log errors |
| `async fn` that does no I/O or waiting          | Unnecessary async overhead      | Make it synchronous                                           |
| Deep `async` call chains with no cancellation   | Leaks resources on timeout      | Use `tokio::time::timeout` at appropriate boundaries          |
| Sharing `Rc<T>` across tasks                    | `Rc` is not `Send`              | Use `Arc<T>` for shared ownership across tasks                |

```rust
// BAD: blocking inside async
async fn read_file(path: &str) -> String {
    std::fs::read_to_string(path).unwrap()  // blocks executor
}

// GOOD: async I/O
async fn read_file(path: &str) -> Result<String, tokio::io::Error> {
    tokio::fs::read_to_string(path).await
}

// BAD: std Mutex held across await
async fn update(state: Arc<Mutex<State>>) {
    let mut s = state.lock().unwrap();
    s.do_something();
    some_async_call().await;  // lock held across await point
}

// GOOD: drop lock before await
async fn update(state: Arc<Mutex<State>>) {
    {
        let mut s = state.lock().unwrap();
        s.do_something();
    }  // lock dropped here
    some_async_call().await;
}
```

---

## Safety & Panics

| Signal                                             | Severity                                                       | What to Check                                                                                                                |
| -------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `unsafe` block                                     | Major                                                          | Document the invariant being upheld; every `unsafe` block needs a `// SAFETY:` comment                                       |
| Integer arithmetic without overflow check          | Minor                                                          | In release mode, integer overflow wraps silently — use `checked_add`, `saturating_add`, or enable overflow checks in profile |
| Array indexing with `[i]`                          | Minor                                                          | Panics on out-of-bounds; prefer `.get(i)` and handle `None`                                                                  |
| `unreachable!()` / `todo!()` in reachable branches | Major                                                          | Both panic at runtime; replace with proper handling                                                                          |
| `transmute`                                        | Critical                                                       | Undefined behavior if types are not layout-compatible; almost always avoidable                                               |
| Raw pointer dereference outside `unsafe`           | Compiler-caught, but flag any `unsafe` containing pointer math | Verify pointer validity and alignment                                                                                        |

```rust
// BAD: silent overflow in release, panic in debug
fn add_offset(base: u32, offset: u32) -> u32 {
    base + offset
}

// GOOD: explicit overflow handling
fn add_offset(base: u32, offset: u32) -> Option<u32> {
    base.checked_add(offset)
}

// BAD: panics on out-of-range index
let val = items[user_supplied_index];

// GOOD: graceful handling
let val = items.get(user_supplied_index)
    .ok_or(AppError::IndexOutOfRange)?;
```

---

## Traits & Generics

| Anti-pattern                                              | Correct Pattern                                         | Why                                                              |
| --------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------- |
| Concrete type in public API where trait bound fits        | Use trait bounds or trait objects                       | More flexible, easier to test                                    |
| Implementing traits with panicking methods                | Return `Result` or use `Option`-returning variants      | Panics in trait impls are unexpected by callers                  |
| Orphan rule violations                                    | Only impl foreign traits on local types (or vice versa) | Compiler enforces this — flag workarounds using newtypes         |
| Over-generic code with 5+ type params                     | Simplify with associated types or concrete types        | Readability and compile-time cost                                |
| Missing `Send + Sync` bounds on types used across threads | Causes compile errors in callers                        | Add bounds explicitly when the type will cross thread boundaries |

---

## Testing

| What to Check                 | Flag If                              | Best Practice                                                    |
| ----------------------------- | ------------------------------------ | ---------------------------------------------------------------- |
| Test naming                   | `test1`, `test_it`                   | Use descriptive names: `test_expired_token_returns_unauthorized` |
| `#[should_panic]` tests       | Used without `expected = "..."`      | Add expected panic message to avoid passing on wrong panic       |
| Tests calling `.unwrap()`     | Fine — panics produce clear failures | Acceptable in test code                                          |
| Integration tests in `src/`   | Should be in `tests/` directory      | Unit tests in `src/`, integration tests in `tests/`              |
| No test for `Error` variants  | `Err` paths left untested            | Test each error variant with a dedicated case                    |
| Hardcoded file paths in tests | Breaks on other machines             | Use `std::env::temp_dir()` or test fixtures                      |

```rust
// BAD: vague name, no negative test
#[test]
fn test_parse() {
    let config = parse_config(r#"{"timeout": 30}"#).unwrap();
    assert_eq!(config.timeout, 30);
}

// GOOD: behavior-named, covers error case
#[test]
fn test_parse_config_returns_timeout_value() {
    let config = parse_config(r#"{"timeout": 30}"#).unwrap();
    assert_eq!(config.timeout, 30);
}

#[test]
fn test_parse_config_returns_error_on_invalid_json() {
    let result = parse_config("not json");
    assert!(result.is_err());
}
```

---

## Security

| Vulnerability                                | Detection Signal                                                   | Fix                                                                                   |
| -------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Hardcoded secrets                            | `let api_key = "sk-live-..."` in source                            | Load from environment: `std::env::var("API_KEY")?`                                    |
| Path traversal                               | `Path::new(base).join(user_input)` without canonicalization        | Use `.canonicalize()` and assert the result starts with the allowed base              |
| Command injection                            | `Command::new("sh").arg(user_input)`                               | Never pass user input to shell; use structured `Command::new("binary").arg(safe_arg)` |
| Unchecked deserialization of untrusted input | `serde_json::from_str(body)` on raw HTTP input without size limits | Apply size limits before deserializing; validate fields after                         |
| Integer cast truncation                      | `value as u8` when `value` could exceed 255                        | Use `u8::try_from(value)?` to surface the error                                       |
| Timing-sensitive comparison using `==`       | Password or token comparison with `==`                             | Use a constant-time comparison crate (e.g., `subtle::ConstantTimeEq`)                 |
