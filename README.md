# S-SIZE (SSZ) Language – Python Cross-Platform Interpreter

A faithful Python replica of the **S-SIZE scripting language** originally created by
**supersuehiro** as the interpreter core of the
**I.K.E.M.E.N.** (*Itsu made mo Kansei shinai Eien ni Mikansei ENgine*) fighting-game
engine – a libre M.U.G.E.N clone.

```
S-SIZE abbreviation: SSZ
Script file extension: .ssz
```

---

## Features Implemented

| Category | Status |
|---|---|
| All primitive types (`int`, `long`, `double`, `bool`, `char`, `bytes`, …) | ✅ |
| Variable declarations with initializers, multi-decl | ✅ |
| Arithmetic, bitwise, logical, comparison operators | ✅ |
| Unary prefix/postfix (`++`, `--`, `!!`, `#`, `''`) | ✅ |
| Explicit `(type)` casts | ✅ |
| Auto-widening coercion (int → float) | ✅ |
| `if` (no else) | ✅ |
| `loop / do: / continue: / while cond:` | ✅ |
| `switch / case / default / break` with `<-` fallthrough | ✅ |
| `branch / cond / comm / diff / else` blocks | ✅ |
| Plain `{ break: }` labeled block | ✅ |
| Functions (`int f(int x){ ret x; }`) | ✅ |
| Alternate function syntax (`..f(x) int { … }`) | ✅ |
| Signature-type syntax (`$int(int) f(x){ … }`) | ✅ |
| Global function pointers (`func $sig name = fn;`) | ✅ |
| Member function pointers (`method $sig name = fn;`) | ✅ |
| Anonymous functions (`[RetType(params){ body }]`) | ✅ |
| Anonymous function pointer (`~$sig name = [anon];`) | ✅ |
| Function pointer call `fp(:args:)` | ✅ |
| Classes (`&ClassName { new() … methods … }`) | ✅ |
| Enums (`\|EnumName { a, b, c }`) | ✅ |
| Templates (`&Class<foo_t>`) | ✅ (parse only) |
| Type aliases (`type int_t = int;`) | ✅ |
| Reference types (`^Type var.new(n);`) | ✅ |
| List types (`%Type`) with `.=` append | ✅ |
| Array slicing (`arr[start..end]`) | ✅ |
| `lock` / `wait` blocks | ✅ (stub, single-threaded) |
| `thread!f? t..();` | ✅ (synchronous) |
| `lib alias = <file.ssz>;` | ✅ |
| `libs = <file.ssz>;` (namespace merge) | ✅ |
| Identifier scopes: local / member (backtick) / global (`.`) | ✅ |
| Comments (`//`, `/* */`, conditional `/?/*`) | ✅ |
| Binary / hex integer literals (`0b…`, `0x…`) | ✅ |
| `''` to-string operator | ✅ |
| Ternary `cond ? a : b` | ✅ |
| `$` right-associative expression | ✅ |

---

## Project Structure

```
ssz_interpreter/
├── ssz.py              ← entry point (run this)
├── tests.py            ← test suite (80 tests)
├── helloworld.ssz      ← sample: Hello, world!
├── root2.ssz           ← sample: √2 approximation
└── ssize/
    ├── __init__.py
    ├── lexer.py        ← tokeniser
    ├── ast_nodes.py    ← AST dataclasses
    ├── parser.py       ← recursive-descent parser
    ├── runtime.py      ← value types, environment, signals
    ├── interpreter.py  ← tree-walk executor
    └── stdlib/
        ├── alert.py    ← alert.ssz  (message box / console)
        ├── string.py   ← string.ssz (iToS, sToI, strLen, …)
        ├── math.py     ← math.ssz   (sin, cos, sqrt, floor, …)
        ├── io.py       ← io.ssz     (readLine, writeFile, …)
        └── sys.py      ← sys.ssz    (exit, timeMs, platform, …)
```

---

## Requirements

- **Python 3.10+** (uses `match` patterns in stdlib stubs — actually 3.8+ suffices for the core)
- No third-party packages required
- `tkinter` is optional (used by `alert.ssz` for GUI pop-ups; falls back to console if absent)

---

## Usage

```bash
# Run a script (defaults to main.ssz if no argument given)
python ssz.py helloworld.ssz

# Dump the token stream
python ssz.py --tokens helloworld.ssz

# Dump the AST
python ssz.py --ast helloworld.ssz

# Add extra library search directories
python ssz.py --lib ./mylibs myscript.ssz

# Run the test suite
python tests.py -v
```

---

## Writing SSZ Scripts

### Hello, World

```ssz
lib al = <alert.ssz>;
al.alert!self?("Hello, world!");
```

### Variables and types

```ssz
int a = 42;
double pi = 3.14159;
bool flag = true;
char c = (char)65;          // 'A'
long big = 9223372036854;
```

### Functions

```ssz
int add(int a, int b) {
    ret a + b;
}

// Alternate syntax
..square(int x) int {
    ret x * x;
}

// Signature-type syntax
$int(int, int) multiply(a, b) {
    ret a * b;
}
```

### Control structures

```ssz
// if  (no else — use branch for if/else)
if(a < b) a = b;

// loop with do: continue: while:
int sum = 0;
int i = 1;
loop {
do:
    sum += i;
    i++;
while i <= 10:
}

// switch with fallthrough  :<-
switch(val) {
case 1:  result = 1; break;
case 2:  result = 2; break;
default: result = 0; break;
}

// branch (if/else equivalent)
branch {
cond a < b:
    a = b;
else:
    break;
comm:
    // runs if not broken
}
```

### Classes

```ssz
&Vec2 {
    double x;
    double y;
    new(double px, double py) { x = px; y = py; }
    public double length() { ret (x*x + y*y) ** 0.5; }
}

Vec2 v;
```

### Enums

```ssz
|Direction { north, south, east, west }
// Access: Direction.north
```

### Libraries

```ssz
lib al = <alert.ssz>;
lib s  = <string.ssz>;
libs   = <math.ssz>;     // merge into current namespace

al.alert!self?(s.iToS(42));
double r = sqrt(2.0);
```

### Function pointers & anonymous functions

```ssz
// Global function pointer
func $int(int) fp = myFunc;
int result = fp(:5:);

// Anonymous function
void demo() {
    int sum = [int(int a, int b){ ret a + b; }](:3, 4:);
}

// Anonymous function pointer
~$int(int, int) add = [int(int a, int b){ ret a + b; }];
int r = add(:10, 20:);
```

### Reference types

```ssz
^int arr.new(10);       // array of 10 ints
%int lst;               // appendable list
lst .= 1;               // append
lst .= 2;
```

---

## Standard Library Stubs

| Library | Functions |
|---|---|
| `alert.ssz` | `alert(msg)`, `alertConsole(msg)` |
| `string.ssz` | `iToS`, `fToS`, `sToI`, `sToF`, `strLen`, `strCat`, `subStr`, `strFind`, `strUpper`, `strLower`, `strReplace`, `boolToS` |
| `math.ssz` | `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sqrt`, `pow`, `exp`, `log`, `log10`, `floor`, `ceil`, `round`, `abs`, `min`, `max`, `pi`, `e` |
| `io.ssz` | `readLine`, `write`, `writeln`, `readFile`, `writeFile`, `appendFile`, `fileExists`, `deleteFile` |
| `sys.ssz` | `exit`, `getArgs`, `getEnv`, `getCwd`, `sleep`, `timeMs`, `platform`, `pythonVer`, `sszVer` |

---

## Known Limitations vs Original C++ SSZ

- **Threads** run synchronously (Python's GIL and the tree-walk design make true parallel SSZ threads non-trivial; use Python threads externally if needed).
- **Memory management** — the original SSZ has explicit reference-counting and `lock` mutexes with real mutex semantics. This replica uses Python's garbage collector.
- **Template specialisation** is parsed but not fully instantiated at runtime.
- **The `core` / `plugins` system** from IKEMEN is not implemented (those are engine-level concerns, not language-level).
- Some **specification issues** documented in `Interprete.md` (memory corruption on freed arrays) do not apply here since Python manages memory safely.

---

## Architecture

```
Source (.ssz)
    │
    ▼
Lexer  ──────────────►  Token stream
    │
    ▼
Parser  ─────────────►  AST (Program node)
    │
    ▼
Interpreter
    ├── Environment (scope chain)
    │       ├── local vars
    │       ├── member vars (backtick)
    │       └── global vars (dot prefix)
    ├── Class registry
    ├── Enum registry
    └── Library loader
            ├── Python stdlib stubs  (ssize/stdlib/*.py)
            └── .ssz files on disk
```

---

## Credits

- **S-SIZE language** — designed and implemented in C++ by **supersuehiro**
- **I.K.E.M.E.N.** engine — supersuehiro, built atop S-SIZE with SDL, OpenGL, Lua, Ogg Vorbis
- **I.K.E.M.E.N. Plus Ultra wiki** — English documentation by the community
- **This Python replica** — cross-platform interpreter preserving the S-SIZE language semantics
