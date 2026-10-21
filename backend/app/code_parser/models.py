from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class SymbolKind(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    TYPE_DEF = "type_def"
    STRUCT = "struct"


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    kind: SymbolKind
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    parent_symbol: Optional[str] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None


@dataclass(frozen=True)
class ImportReference:
    module: str
    names: List[str] = field(default_factory=list)
    is_wildcard: bool = False
    alias: Optional[str] = None
    line_number: int = 1  # 1-based


@dataclass(frozen=True)
class ParsedFile:
    language: str
    symbols: List[CodeSymbol] = field(default_factory=list)
    imports: List[ImportReference] = field(default_factory=list)
    syntax_valid: bool = True
    error: Optional[str] = None
