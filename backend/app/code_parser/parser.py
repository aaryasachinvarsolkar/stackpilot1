from pathlib import Path
from typing import Dict, Optional, Union
from tree_sitter import Language, Parser, Tree

import tree_sitter_python
import tree_sitter_typescript
import tree_sitter_javascript
import tree_sitter_go

from app.code_parser.models import ParsedFile
from app.code_parser.languages.python import extract_python_symbols_and_imports
from app.code_parser.languages.typescript import extract_typescript_symbols_and_imports
from app.code_parser.languages.go import extract_go_symbols_and_imports

# Lazy-loaded Language and Parser singletons
_LANGUAGES: Dict[str, Language] = {}
_PARSERS: Dict[str, Parser] = {}

EXTENSION_TO_LANG: Dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
}


def _get_language(lang_key: str) -> Optional[Language]:
    if lang_key in _LANGUAGES:
        return _LANGUAGES[lang_key]

    if lang_key == "python":
        lang = Language(tree_sitter_python.language())
    elif lang_key == "typescript":
        lang = Language(tree_sitter_typescript.language_typescript())
    elif lang_key == "tsx":
        lang = Language(tree_sitter_typescript.language_tsx())
    elif lang_key == "javascript":
        lang = Language(tree_sitter_javascript.language())
    elif lang_key == "go":
        lang = Language(tree_sitter_go.language())
    else:
        return None

    _LANGUAGES[lang_key] = lang
    return lang


def _get_parser(lang_key: str) -> Optional[Parser]:
    lang = _get_language(lang_key)
    if not lang:
        return None
    if lang_key in _PARSERS:
        return _PARSERS[lang_key]

    parser = Parser(lang)
    _PARSERS[lang_key] = parser
    return parser


def detect_language(path_or_ext: str) -> Optional[str]:
    ext = Path(path_or_ext).suffix.lower()
    return EXTENSION_TO_LANG.get(ext)


def parse_source(
    source: Union[str, bytes],
    file_path_or_ext: str,
    language: Optional[str] = None,
) -> ParsedFile:
    lang_key = language.lower() if language else detect_language(file_path_or_ext)
    if not lang_key:
        return ParsedFile(
            language="unsupported",
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"Unsupported file extension or language for {file_path_or_ext}",
        )

    # Convert to bytes safely
    if isinstance(source, str):
        source_bytes = source.encode("utf-8", errors="replace")
    elif isinstance(source, bytes):
        source_bytes = source
    else:
        return ParsedFile(
            language=lang_key,
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"Invalid source type: {type(source)}",
        )

    # Handle empty source gracefully
    if not source_bytes.strip():
        return ParsedFile(
            language=lang_key,
            symbols=[],
            imports=[],
            syntax_valid=True,
            error=None,
        )

    parser = _get_parser(lang_key)
    if not parser:
        return ParsedFile(
            language=lang_key,
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"Parser not initialized for language {lang_key}",
        )

    try:
        tree: Tree = parser.parse(source_bytes)
    except Exception as exc:
        return ParsedFile(
            language=lang_key,
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"Parser error: {str(exc)}",
        )

    root = tree.root_node
    syntax_valid = not root.has_error

    try:
        if lang_key == "python":
            symbols, imports = extract_python_symbols_and_imports(root, source_bytes)
        elif lang_key in ("typescript", "tsx", "javascript"):
            symbols, imports = extract_typescript_symbols_and_imports(root, source_bytes)
        elif lang_key == "go":
            symbols, imports = extract_go_symbols_and_imports(root, source_bytes)
        else:
            symbols, imports = [], []
    except Exception as exc:
        return ParsedFile(
            language=lang_key,
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"Extraction error: {str(exc)}",
        )

    return ParsedFile(
        language=lang_key,
        symbols=symbols,
        imports=imports,
        syntax_valid=syntax_valid,
        error=None,
    )


def parse_file(file_path: Union[str, Path]) -> ParsedFile:
    path = Path(file_path)
    if not path.is_file():
        return ParsedFile(
            language="unknown",
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"File not found: {file_path}",
        )

    try:
        source_bytes = path.read_bytes()
    except Exception as exc:
        return ParsedFile(
            language=detect_language(path.name) or "unknown",
            symbols=[],
            imports=[],
            syntax_valid=False,
            error=f"File read error: {str(exc)}",
        )

    return parse_source(source_bytes, path.name)
