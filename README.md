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

## What Stands Out / Potential Issues

A few things worth noting if you're looking to improve it:

1. **`ExprStmt` silently swallows all exceptions** — the `try/except Exception: pass` in `exec()` is intentionally lenient, but it can hide real interpreter bugs during development. You might want a debug flag to surface these.

2. **`Environment.set()` auto-defines on miss** — if a variable is used before declaration, it silently creates it in the current scope rather than raising. This may or may not match the C++ engine's behavior exactly.

3. **`_do_binary` doesn't short-circuit `||`** — `&&` properly short-circuits, but `||` evaluates both sides before calling `bool(L) or bool(R)`. This matters if one side has side effects or crashes.

4. **The `$` operator** (`right-associative expression`) is implemented as simply returning `R`, which seems like a placeholder — worth double-checking the original semantics.

5. **`tests.py`** is 792 lines with 80 tests — a solid regression suite. Running it would be a good first check: `python tests.py -v`.

## Credits

- **S-SIZE language** — designed and implemented in C++ by **supersuehiro**
- **I.K.E.M.E.N.** engine — supersuehiro, built atop S-SIZE with SDL, OpenGL, Lua, Ogg Vorbis
- **I.K.E.M.E.N. Plus Ultra wiki** — English documentation by the community
- **This Python replica** — cross-platform interpreter preserving the S-SIZE language semantics
