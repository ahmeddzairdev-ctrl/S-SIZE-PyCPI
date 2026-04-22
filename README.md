# S-SIZE (SSZ) Language – Python Cross-Platform Interpreter

A faithful Python replica of the **S-SIZE scripting language** originally created by
**supersuehiro** as the interpreter core of the
**I.K.E.M.E.N.** (*Itsu made mo Kansei shinai Eien ni Mikansei ENgine*) fighting-game
engine – a libre M.U.G.E.N clone.

## Architecture

The pipeline is classic and clean:

```
.ssz source → Lexer → Token stream → Parser → AST → Interpreter → Result
```

**`lexer.py`** (~23KB) — A hand-written character-by-character tokenizer. It handles a rich token set including SSZ-specific operators like `<,` (pipe-left), `<>` (dereference), `<>=`, `=>` (result capture), `(:` / `:)` (function pointer call delimiters), `<-` (switch fallthrough), `!!` (bool-flip), `''` (to-string), and `??`-style conditional comments.

**`ast_nodes.py`** (~7.5KB) — Pure dataclass AST node definitions covering types, expressions, statements, and declarations. Notably includes SSZ-specific constructs: `BranchStmt`, `LoopStmt`, `BlockBreak`, `ScopeAccess (::)`, `DerefExpr (<>)`, `ResultCapture (=>)`, `PipeLeft (<,)`.

**`parser.py`** (~45KB) — The largest file: a recursive-descent parser for the full SSZ grammar, including all three function declaration syntaxes, anonymous functions, class/enum/template declarations, library imports, and the unusual loop structure (`loop { do: ... while cond: }`).

**`interpreter.py`** (~38KB) — The tree-walking evaluator. Key design choices:
- **"IgnoreMostErrors" mode** — silently returns `None` for unresolved identifiers/calls, matching the engine's lenient runtime behavior.
- Control flow via Python exceptions (`ReturnSignal`, `BreakSignal`, `ContinueSignal`, `ElseJumpSignal`, `MultiBreak`).
- Threads run **synchronously** (a known limitation vs. the C++ original).
- Library loading tries Python stubs first, then `.ssz` files on disk, then falls back to an empty module.

**`runtime.py`** (~11KB) — The value model: `SSZValue`, `SSZArray` (`^T`), `SSZList` (`%T`), `SSZObject`, `SSZEnum`, `SSZFunction`, `SSZAnonFunc`, `SSZModule`, and the `Environment` scope chain (local → member/backtick → global/dot-prefix).

---

## Standard Library Stubs (`stdlib/`)

| Module | Notes |
|---|---|
| `alert`, `string`, `math`, `io`, `sys` | Core stdlib — fully implemented in Python |
| `file`, `table`, `socket`, `thread`, `regex`, `sound`, `shell` | Extended stdlib |
| `alpha/sdlplugin`, `alpha/lua`, `alpha/sdlevent`, `alpha/mesdialog` | Alpha/engine-level — SDL2, Lua bridge, sound |

The `alpha/lua.py` module is particularly interesting — it wraps `lupa` (or similar) to bridge SSZ ↔ Lua, which is how IKEMEN's gameplay scripts work.

---

## Interesting Language Features Handled

- **Three function declaration syntaxes**: `int f(int x){…}`, `..f(int x) int {…}`, `$int(int) f(x){…}`
- **`branch` blocks** as if/else-if/else (with optional `comm:` for shared post-body and `diff:` for label-matched blocks)
- **`loop { do: … while cond: }`** — SSZ's unique loop form with optional pre-check
- **Function/method pointers** with `func`/`method`/`~$sig` declarations and `fp(:args:)` call syntax
- **`<>` dereference**, **`=>` result capture**, **`<,` pipe-left**
- **`lib`/`libs` imports** with namespace merging
- **Templates** (parsed, not fully instantiated)

---

## Requirements

- **Python 3.10+** (uses `match` patterns in stdlib stubs — actually 3.8+ suffices for the core)
- No third-party packages required
- `tkinter` is optional (used by `alert.ssz` for GUI pop-ups; falls back to console if absent)

# Fix pip first (one-time)
```bash
python3 -m ensurepip --upgrade
```
# OR: 
```bash
curl https://bootstrap.pypa.io/get-pip.py | python3
```

# Install dependencies
```bash
pip3 install lupa pygame Pillow
```
---

## Usage

```bash
# Run a script (defaults to main.ssz if no argument given)
python3 ssz.py helloworld.ssz

# Dump the token stream
python3 ssz.py --tokens helloworld.ssz

# Dump the AST
python3 ssz.py --ast helloworld.ssz

# Add extra library search directories
python3 ssz.py --lib ./mylibs myscript.ssz

# Run the test suite
python3 tests.py -v

# Run the engine
python3 ikemen.py // or python3 ikemen.py main.ssz

# help command
python3 ikemen.py --help
python3 ssz.py --help
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

## Credits

- **S-SIZE language** — designed and implemented in C++ by **supersuehiro**
- **I.K.E.M.E.N.** engine — supersuehiro, built atop S-SIZE with SDL, OpenGL, Lua, Ogg Vorbis
- **I.K.E.M.E.N. Plus Ultra wiki** — English documentation by the community
- **This Python replica** — cross-platform interpreter preserving the S-SIZE language semantics
