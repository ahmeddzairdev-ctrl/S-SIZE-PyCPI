"""S-SIZE (SSZ) language interpreter package."""

from .lexer       import Lexer, Token, TT, LexError
from .parser      import Parser, ParseError
from .interpreter import Interpreter, SSZError
from .runtime     import (
    Environment, SSZValue, SSZArray, SSZList,
    SSZObject, SSZEnum, SSZFunction, SSZModule,
)

__version__ = "1.0.0"
__all__ = [
    "Lexer", "Token", "TT", "LexError",
    "Parser", "ParseError",
    "Interpreter", "SSZError",
    "Environment", "SSZValue", "SSZArray", "SSZList",
    "SSZObject", "SSZEnum", "SSZFunction", "SSZModule",
]
