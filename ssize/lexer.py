"""
S-SIZE (SSZ) Lexer — faithful to the real IKEMEN engine source.

New tokens vs original:
  PIPE_LEFT    <,    pipe operator: f()<, x  =  f(x)
  DOTDOTDOT    ...   exclusive range end
  COLONCOLON   ::    scope resolution (Enum::Member, Type::Const)
  DEREF        <>    dereference first element of a reference
  DEREF_ASSIGN <>= 
  FAT_ARROW    =>    result capture: expr=>var
  TILDE_ACC    ~     direct field access on a reference/object
  PERCENTPERCENT %%  nested list type
  LANGLE_BANG  <!   consteval open?
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Any, List


class TT(Enum):
    # Literals
    INT_LIT    = auto()
    FLOAT_LIT  = auto()
    STRING_LIT = auto()
    CHAR_LIT   = auto()

    # Primitive types
    T_BYTES  = auto(); T_UBYTE  = auto()
    T_SHORT  = auto(); T_USHORT = auto()
    T_INT    = auto(); T_UINT   = auto()
    T_LONG   = auto(); T_ULONG  = auto()
    T_FLOAT  = auto(); T_DOUBLE = auto()
    T_CHAR   = auto(); T_INDEX  = auto()
    T_BOOL   = auto(); T_VOID   = auto()

    # Value keywords
    KW_TRUE = auto(); KW_FALSE = auto()

    # Control flow
    KW_IF       = auto(); KW_ELSE     = auto()
    KW_LOOP     = auto(); KW_WHILE    = auto()
    KW_DO       = auto(); KW_BREAK    = auto()
    KW_CONTINUE = auto(); KW_RET      = auto()
    KW_SWITCH   = auto(); KW_CASE     = auto()
    KW_DEFAULT  = auto(); KW_BRANCH   = auto()
    KW_COND     = auto(); KW_COMM     = auto()
    KW_DIFF     = auto(); KW_LOCK     = auto()
    KW_WAIT     = auto()

    # Declaration
    KW_NEW       = auto(); KW_DELETE    = auto()
    KW_SELF      = auto(); KW_PUBLIC    = auto()
    KW_CONST     = auto(); KW_TYPE      = auto()
    KW_TYPEID    = auto(); KW_TYPESIZE  = auto()
    KW_CAST      = auto(); KW_FUNC      = auto()
    KW_METHOD    = auto(); KW_REF       = auto()
    KW_LIST      = auto(); KW_THREAD    = auto()
    KW_THREADS   = auto(); KW_LIB       = auto()
    KW_LIBS      = auto(); KW_CORE      = auto()
    KW_PLUGINS   = auto(); KW_SIGNATURE = auto()

    IDENT = auto()

    # Arithmetic
    PLUS      = auto(); MINUS     = auto()
    STAR      = auto(); SLASH     = auto()
    PERCENT   = auto(); STARSTAR  = auto()
    PERCENTPERCENT = auto()   # %%  nested list type

    # Bitwise
    AMP    = auto(); CARET  = auto()
    PIPE   = auto(); PIPEPIPE = auto(); TILDE  = auto()
    LSHIFT = auto(); RSHIFT = auto()

    # Logical
    AMPAMP = auto(); BANG = auto()

    # Comparison
    EQ = auto(); NEQ = auto()
    LT = auto(); LTE = auto()
    GT = auto(); GTE = auto()

    # Assignment
    ASSIGN          = auto()
    PLUS_ASSIGN     = auto(); MINUS_ASSIGN    = auto()
    STAR_ASSIGN     = auto(); SLASH_ASSIGN    = auto()
    PERCENT_ASSIGN  = auto(); STARSTAR_ASSIGN = auto()
    LSHIFT_ASSIGN   = auto(); RSHIFT_ASSIGN   = auto()
    AND_ASSIGN      = auto(); XOR_ASSIGN      = auto()
    DOT_ASSIGN      = auto()   # .=  append

    # Special operators
    DOLLAR      = auto()   # $
    HASH        = auto()   # #
    QUESTION    = auto()   # ?
    TOSTR       = auto()   # ''
    BANGBANG    = auto()   # !!
    PLUSPLUS    = auto()   # ++
    MINUSMINUS  = auto()   # --
    BACKTICK    = auto()   # `  member var
    TILDE_ACC   = auto()   # ~  direct field access (NOT anon func ptr)

    # Real-engine operators
    PIPE_LEFT    = auto()   # <,   pipe
    DOTDOTDOT    = auto()   # ...  exclusive range
    COLONCOLON   = auto()   # ::   scope resolution
    DEREF        = auto()   # <>   dereference
    DEREF_ASSIGN = auto()   # <>=  dereference-assign
    FAT_ARROW    = auto()   # =>   result capture
    CONSTEVAL_L  = auto()   # <consteval>(
    WAIT_L       = auto()   # <wait>(

    # Punctuation
    LPAREN    = auto(); RPAREN    = auto()
    LBRACE    = auto(); RBRACE    = auto()
    LBRACKET  = auto(); RBRACKET  = auto()
    SEMICOLON = auto(); COMMA     = auto()
    DOT       = auto(); DOTDOT    = auto()
    COLON     = auto(); ARROW_L   = auto()   # <-  fallthrough
    FCALL_L   = auto(); FCALL_R   = auto()   # (:  :)

    EOF = auto()


KEYWORDS: dict[str, TT] = {
    "bytes":  TT.T_BYTES,  "ubyte":  TT.T_UBYTE,
    "short":  TT.T_SHORT,  "ushort": TT.T_USHORT,
    "int":    TT.T_INT,    "uint":   TT.T_UINT,
    "long":   TT.T_LONG,   "ulong":  TT.T_ULONG,
    "float":  TT.T_FLOAT,  "double": TT.T_DOUBLE,
    "char":   TT.T_CHAR,   "index":  TT.T_INDEX,
    "bool":   TT.T_BOOL,   "void":   TT.T_VOID,
    "true":   TT.KW_TRUE,  "false":  TT.KW_FALSE,
    "if":       TT.KW_IF,       "else":     TT.KW_ELSE,
    "loop":     TT.KW_LOOP,     "while":    TT.KW_WHILE,
    "do":       TT.KW_DO,       "break":    TT.KW_BREAK,
    "continue": TT.KW_CONTINUE, "ret":      TT.KW_RET,
    "switch":   TT.KW_SWITCH,   "case":     TT.KW_CASE,
    "default":  TT.KW_DEFAULT,  "branch":   TT.KW_BRANCH,
    "branches": TT.KW_BRANCH,   "cond":     TT.KW_COND,
    "comm":     TT.KW_COMM,     "diff":     TT.KW_DIFF,
    "lock":     TT.KW_LOCK,     "wait":     TT.KW_WAIT,
    "new":      TT.KW_NEW,      "delete":   TT.KW_DELETE,
    "self":     TT.KW_SELF,     "public":   TT.KW_PUBLIC,
    "const":    TT.KW_CONST,    "type":     TT.KW_TYPE,
    "typeid":   TT.KW_TYPEID,   "cast":     TT.KW_CAST,
    "func":     TT.KW_FUNC,     "method":   TT.KW_METHOD,
    "ref":      TT.KW_REF,      "list":     TT.KW_LIST,
    "thread":   TT.KW_THREAD,   "threads":  TT.KW_THREADS,
    "lib":      TT.KW_LIB,      "libs":     TT.KW_LIBS,
    "core":     TT.KW_CORE,     "plugins":  TT.KW_PLUGINS,
    "signature":TT.KW_SIGNATURE,"typesize": TT.KW_TYPESIZE,
}

TYPE_NAMES: dict[TT, str] = {
    TT.T_BYTES: "bytes", TT.T_UBYTE: "ubyte",
    TT.T_SHORT: "short", TT.T_USHORT: "ushort",
    TT.T_INT:   "int",   TT.T_UINT:  "uint",
    TT.T_LONG:  "long",  TT.T_ULONG: "ulong",
    TT.T_FLOAT: "float", TT.T_DOUBLE:"double",
    TT.T_CHAR:  "char",  TT.T_INDEX: "index",
    TT.T_BOOL:  "bool",  TT.T_VOID:  "void",
}


@dataclass
class Token:
    type:  TT
    value: Any
    line:  int
    col:   int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.col})"


class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(f"LexError at {line}:{col}: {msg}")
        self.line = line; self.col = col


class Lexer:
    def __init__(self, source: str, filename: str = "<unknown>"):
        if source.startswith("\ufeff"):
            source = source[1:]
        # Normalise CRLF → LF
        source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.src      = source
        self.filename = filename
        self.pos      = 0
        self.line     = 1
        self.col      = 1
        self.tokens: List[Token] = []

    # ------------------------------------------------------------------ helpers

    def peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.src[idx] if idx < len(self.src) else "\0"

    def advance(self) -> str:
        ch = self.src[self.pos]; self.pos += 1
        if ch == "\n": self.line += 1; self.col = 1
        else:          self.col  += 1
        return ch

    def match(self, expected: str) -> bool:
        if self.pos < len(self.src) and self.src[self.pos] == expected:
            self.advance(); return True
        return False

    def error(self, msg: str) -> LexError:
        return LexError(msg, self.line, self.col)

    # ------------------------------------------------------------------ skip

    def skip(self) -> None:
        while self.pos < len(self.src):
            ch = self.peek()
            if ch in " \t\r\n":
                self.advance(); continue

            # // line comment
            if ch == "/" and self.peek(1) == "/":
                while self.pos < len(self.src) and self.peek() != "\n":
                    self.advance()
                continue

            # /?/* … /*?*/  conditional comment — always skip
            if ch == "/" and self.peek(1) == "?" and self.peek(2) == "/":
                self._skip_conditional()
                continue

            # /* … */  block comment
            if ch == "/" and self.peek(1) == "*":
                self.advance(); self.advance()
                self._skip_block()
                continue
            break

    def _skip_block(self) -> None:
        while self.pos < len(self.src):
            if self.peek() == "*" and self.peek(1) == "/":
                self.advance(); self.advance(); return
            self.advance()
        raise self.error("Unterminated block comment")

    def _skip_conditional(self) -> None:
        # consume everything until /*?*/
        while self.pos < len(self.src):
            if (self.peek() == "/" and self.peek(1) == "*"
                    and self.peek(2) == "?" and self.peek(3) == "*"
                    and self.peek(4) == "/"):
                for _ in range(5): self.advance()
                return
            self.advance()

    def _is_hex(self, ch: str) -> bool:
        return ch in "0123456789abcdefABCDEF"

    # ------------------------------------------------------------------ escaped-string  \"...\"

    def lex_escaped_string(self) -> Token:
        """
        \" alternate string delimiter.
        Opens with \\\" and closes with the next \\\".
        Can contain bare \" inside without escaping.
        If no closing \\\" found, treat as a 1-char string containing just \".
        """
        ln, col = self.line, self.col
        self.advance()  # consume \ 
        self.advance()  # consume opening "
        buf = []
        # peek for closing \"
        while self.pos < len(self.src):
            if self.peek() == "\\" and self.peek(1) == '"':
                self.advance(); self.advance()  # consume \"
                return Token(TT.STRING_LIT, "".join(buf), ln, col)
            if self.peek() == "\n":  # unclosed — treat as 1-char string
                break
            buf.append(self.advance())
        # Unclosed \"...  — return string containing just \"
        return Token(TT.STRING_LIT, '"' + "".join(buf), ln, col)

    # ------------------------------------------------------------------ char literal  'c'

    def lex_char_literal(self) -> Token:
        """'c' or '\\n' etc. — single character literal."""
        ln, col = self.line, self.col
        self.advance()  # consume opening '
        ch = self.peek()
        if ch == "\\":
            self.advance()
            esc = self.advance()
            if esc == 'x' and self._is_hex(self.peek()) and self._is_hex(self.peek(1)):
                h1 = self.advance(); h2 = self.advance()
                value = chr(int(h1+h2, 16))
            else:
                value = {"n": "\n", "t": "\t", "r": "\r", "'": "'",
                         "\\": "\\", "0": "\0", '"': '"',
                         "a": "\x07", "b": "\x08"}.get(esc, esc)
        elif ch == "'":
            # empty char ''  (closing immediately)
            self.advance()
            return Token(TT.CHAR_LIT, "", ln, col)
        else:
            value = self.advance()
        # consume closing '
        if self.peek() == "'":
            self.advance()
        return Token(TT.CHAR_LIT, value, ln, col)

    # ------------------------------------------------------------------ string

    def lex_string(self) -> Token:
        ln, col = self.line, self.col
        self.advance()  # opening "
        buf = []
        while self.pos < len(self.src):
            ch = self.advance()
            if ch == '"': return Token(TT.STRING_LIT, "".join(buf), ln, col)
            if ch == "\\":
                esc = self.advance()
                if esc == 'x' and self._is_hex(self.peek()) and self._is_hex(self.peek(1)):
                    h1 = self.advance(); h2 = self.advance()
                    buf.append(chr(int(h1+h2, 16)))
                else:
                    buf.append({"n":"\n","t":"\t","r":"\r",'"':'"',"\\":"\\",
                                "0":"\0","a":"\x07","b":"\x08"}.get(esc, esc))
            else:
                buf.append(ch)
        raise self.error("Unterminated string literal")

    # ------------------------------------------------------------------ number

    def lex_number(self) -> Token:
        ln, col = self.line, self.col
        buf = []

        # Hex: 0x…
        if self.peek() == "0" and self.peek(1) in "xX":
            buf += [self.advance(), self.advance()]
            while self.peek() in "0123456789abcdefABCDEF_":
                c = self.advance()
                if c != "_": buf.append(c)
            return Token(TT.INT_LIT, int("".join(buf), 16), ln, col)

        # Binary: 0b…
        if self.peek() == "0" and self.peek(1) in "bB":
            buf += [self.advance(), self.advance()]
            while self.peek() in "01_":
                c = self.advance()
                if c != "_": buf.append(c)
            return Token(TT.INT_LIT, int("".join(buf), 2), ln, col)

        # Decimal integer part
        while self.peek().isdigit() or self.peek() == "_":
            c = self.advance()
            if c != "_": buf.append(c)

        # `0d16`  — "d" suffix means double literal
        #  e.g. 0d16 = 16.0,  1d5 = 15.0??  No: just Nd = N as double
        if self.peek() in "dD" and not self.peek(1).isalpha():
            self.advance()  # consume d
            rest = []
            while self.peek().isdigit() or self.peek() == "_":
                c = self.advance()
                if c != "_": rest.append(c)
            base = int("".join(buf)) if buf else 0
            exp  = int("".join(rest)) if rest else 0
            # Nd<digits>: treat as base * 10^exp? No — looking at usage:
            # 0d0=0, 0d8=8, 0d16=16, 0d1=1  => just the digits after d
            # Actually 0d16 → integer 16 (used as shift amounts)
            return Token(TT.INT_LIT, exp, ln, col)

        # Float
        is_float = False
        if self.peek() == "." and self.peek(1).isdigit():
            is_float = True
            buf.append(self.advance())
            while self.peek().isdigit(): buf.append(self.advance())
        if self.peek() in "eE":
            is_float = True
            buf.append(self.advance())
            if self.peek() in "+-": buf.append(self.advance())
            while self.peek().isdigit(): buf.append(self.advance())

        raw = "".join(buf)
        if is_float:
            return Token(TT.FLOAT_LIT, float(raw), ln, col)
        return Token(TT.INT_LIT, int(raw), ln, col)

    # ------------------------------------------------------------------ main loop

    def tokenize(self) -> List[Token]:
        while True:
            self.skip()
            if self.pos >= len(self.src):
                self.tokens.append(Token(TT.EOF, None, self.line, self.col))
                break

            ln, col = self.line, self.col

            def tok(tt: TT, v: Any = None) -> Token:
                return Token(tt, v, ln, col)

            ch = self.peek()

            # backslash-quote alternate string delimiter \"...\"
            if ch == "\\" and self.peek(1) == '"':
                self.tokens.append(self.lex_escaped_string()); continue

            # '' to-string (MUST precede single-quote char literal check)
            if ch == "'" and self.peek(1) == "'":
                self.advance(); self.advance()
                self.tokens.append(tok(TT.TOSTR, "''")); continue

            # 'c' char literal
            if ch == "'":
                self.tokens.append(self.lex_char_literal()); continue

            # regular "..." string
            if ch == '"':
                self.tokens.append(self.lex_string()); continue

            # number literal
            if ch.isdigit():
                self.tokens.append(self.lex_number()); continue

            # identifier / keyword
            if ch.isalpha() or ch == "_":
                start = self.pos
                while self.peek().isalnum() or self.peek() == "_":
                    self.advance()
                word = self.src[start:self.pos]
                tt = KEYWORDS.get(word, TT.IDENT)
                self.tokens.append(Token(tt, word, ln, col))
                continue

            self.advance()  # consume single char for operator dispatch

            if ch == "*":
                if self.match("*"):
                    if self.match("="): self.tokens.append(tok(TT.STARSTAR_ASSIGN,"**="))
                    else:               self.tokens.append(tok(TT.STARSTAR,"**"))
                elif self.match("="): self.tokens.append(tok(TT.STAR_ASSIGN,"*="))
                else:                 self.tokens.append(tok(TT.STAR,"*"))

            elif ch == "%":
                if self.match("%"):   self.tokens.append(tok(TT.PERCENTPERCENT,"%%"))
                elif self.match("="): self.tokens.append(tok(TT.PERCENT_ASSIGN,"%="))
                else:                 self.tokens.append(tok(TT.PERCENT,"%"))

            elif ch == "+":
                if self.match("+"): self.tokens.append(tok(TT.PLUSPLUS,"++"))
                elif self.match("="): self.tokens.append(tok(TT.PLUS_ASSIGN,"+="))
                else:               self.tokens.append(tok(TT.PLUS,"+"))

            elif ch == "-":
                if self.match("-"): self.tokens.append(tok(TT.MINUSMINUS,"--"))
                elif self.match("="): self.tokens.append(tok(TT.MINUS_ASSIGN,"-="))
                else:               self.tokens.append(tok(TT.MINUS,"-"))

            elif ch == "/":
                if self.match("="): self.tokens.append(tok(TT.SLASH_ASSIGN,"/="))
                else:               self.tokens.append(tok(TT.SLASH,"/"))

            elif ch == "&":
                if self.match("&"):   self.tokens.append(tok(TT.AMPAMP,"&&"))
                elif self.match("="): self.tokens.append(tok(TT.AND_ASSIGN,"&="))
                else:                 self.tokens.append(tok(TT.AMP,"&"))

            elif ch == "^":
                if self.match("="): self.tokens.append(tok(TT.XOR_ASSIGN,"^="))
                else:               self.tokens.append(tok(TT.CARET,"^"))

            elif ch == "|":
                if self.match("|"): self.tokens.append(tok(TT.PIPEPIPE,"||"))
                else:               self.tokens.append(tok(TT.PIPE,"|"))

            elif ch == "~":
                # ~ followed immediately by an identifier → field access operator
                # ~ followed by $ or space → anon func ptr prefix
                if self.peek().isalpha() or self.peek() == "_":
                    self.tokens.append(tok(TT.TILDE_ACC,"~"))
                else:
                    self.tokens.append(tok(TT.TILDE,"~"))

            elif ch == "!":
                if self.match("!"): self.tokens.append(tok(TT.BANGBANG,"!!"))
                elif self.match("="): self.tokens.append(tok(TT.NEQ,"!="))
                else:               self.tokens.append(tok(TT.BANG,"!"))

            elif ch == "=":
                if self.match(">"): self.tokens.append(tok(TT.FAT_ARROW,"=>"))
                elif self.match("="): self.tokens.append(tok(TT.EQ,"=="))
                else:               self.tokens.append(tok(TT.ASSIGN,"="))

            elif ch == "<":
                # <>= dereference-assign
                if self.peek() == ">" and self.peek(1) == "=":
                    self.advance(); self.advance()
                    self.tokens.append(tok(TT.DEREF_ASSIGN,"<>="))
                # <> dereference
                elif self.peek() == ">":
                    self.advance()
                    self.tokens.append(tok(TT.DEREF,"<>"))
                # <<= 
                elif self.peek() == "<":
                    self.advance()
                    if self.match("="): self.tokens.append(tok(TT.LSHIFT_ASSIGN,"<<="))
                    else:               self.tokens.append(tok(TT.LSHIFT,"<<"))
                # <=
                elif self.peek() == "=":
                    self.advance()
                    self.tokens.append(tok(TT.LTE,"<="))
                # <- fallthrough
                elif self.peek() == "-":
                    self.advance()
                    self.tokens.append(tok(TT.ARROW_L,"<-"))
                # <, pipe
                elif self.peek() == ",":
                    self.advance()
                    self.tokens.append(tok(TT.PIPE_LEFT,"<,"))
                # <consteval>(
                elif self.src[self.pos:self.pos+10] == "consteval>":
                    for _ in range(10): self.advance()
                    self.tokens.append(tok(TT.CONSTEVAL_L,"<consteval>"))
                # <wait>(
                elif self.src[self.pos:self.pos+5] == "wait>":
                    for _ in range(5): self.advance()
                    self.tokens.append(tok(TT.WAIT_L,"<wait>"))
                else:
                    self.tokens.append(tok(TT.LT,"<"))

            elif ch == ">":
                if self.peek() == ">":
                    self.advance()
                    if self.match("="): self.tokens.append(tok(TT.RSHIFT_ASSIGN,">>="))
                    else:               self.tokens.append(tok(TT.RSHIFT,">>"))
                elif self.match("="): self.tokens.append(tok(TT.GTE,">="))
                else:                 self.tokens.append(tok(TT.GT,">"))

            elif ch == ".":
                if self.peek() == "." and self.peek(1) == ".":
                    self.advance(); self.advance()
                    self.tokens.append(tok(TT.DOTDOTDOT,"..."))
                elif self.peek() == ".":
                    self.advance()
                    self.tokens.append(tok(TT.DOTDOT,".."))
                elif self.match("="):
                    self.tokens.append(tok(TT.DOT_ASSIGN,".="))
                else:
                    self.tokens.append(tok(TT.DOT,"."))

            elif ch == ":":
                if self.peek() == ")":
                    self.advance(); self.tokens.append(tok(TT.FCALL_R,":)"))
                elif self.peek() == ":":
                    self.advance(); self.tokens.append(tok(TT.COLONCOLON,"::"))
                else:
                    self.tokens.append(tok(TT.COLON,":"))

            elif ch == "(":
                if self.match(":"): self.tokens.append(tok(TT.FCALL_L,"(:"))
                else:               self.tokens.append(tok(TT.LPAREN,"("))

            elif ch == ")": self.tokens.append(tok(TT.RPAREN,")"))
            elif ch == "{": self.tokens.append(tok(TT.LBRACE,"{"))
            elif ch == "}": self.tokens.append(tok(TT.RBRACE,"}"))
            elif ch == "[": self.tokens.append(tok(TT.LBRACKET,"["))
            elif ch == "]": self.tokens.append(tok(TT.RBRACKET,"]"))
            elif ch == ";": self.tokens.append(tok(TT.SEMICOLON,";"))
            elif ch == ",": self.tokens.append(tok(TT.COMMA,","))
            elif ch == "$": self.tokens.append(tok(TT.DOLLAR,"$"))
            elif ch == "#": self.tokens.append(tok(TT.HASH,"#"))
            elif ch == "?": self.tokens.append(tok(TT.QUESTION,"?"))
            elif ch == "`": self.tokens.append(tok(TT.BACKTICK,"`"))
            # ignore unknown characters silently (engine is lenient)

        return self.tokens
