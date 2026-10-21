"""Local, deterministic retrieval of source excerpts from one project's workspace.

What it is: `retrieve(project_root, question)` scans the project's files on disk and returns at most 8 excerpts
(24,000 characters in total) that lexically match the question, each with its relative path and exact line numbers.

What it is not: it never calls a model or any service, opens no socket, imports no database code, writes nothing (no
file, no database row, no cache) and executes nothing it reads. File contents are untrusted DATA: they are only split,
redacted, tokenised and counted. Stage 3c decides what, if anything, is sent to a provider.

Which files are read (nothing is read outside the project folder)
  * Candidates come only from walking the project folder, never from a path taken from the question. Each one is
    resolved with `resolve_in_project` and must resolve to exactly the walked location, so traversal, absolute and
    drive-letter paths, `:` (NTFS streams) and links that lead elsewhere are impossible. Symlinks, junctions and other
    reparse points (files and folders) are skipped, and the real path must still lie inside the real project root.
    The file is opened once; its identity is compared with the earlier `lstat`, and the same bytes are hashed and parsed.
    (A swap between the check and the open by another process is detected by that identity check only on a best-effort
    basis.)
  * Skipped entirely, never returned (counted in `RetrievalResult.skipped`): the project's ignored folders and files
    (`IGNORED_DIRS`, `IGNORED_FILES`) plus a few dependency/cache folders; `.env` and `*.env` (but not the
    `.env.example`/`.sample`/`.template`/`.dist` templates, which are redacted like any file); key and certificate files;
    `secrets*`, `credentials*` and similar; binaries (known extensions, a NUL byte, or not valid UTF-8); generated files
    (lock files, `*.min.js`, source maps, protobuf output, a "generated / do not edit" header, absurdly long lines);
    files over 256 KB; empty files. Ordinary text of any other kind is eligible: there is no extension allow-list.
    Judgment calls: `secrets.json` is excluded but `secret_algorithm.py` is not; a template such as `.env.example` is
    included (redacted) because it documents configuration; OneDrive-style placeholders are reparse points and are skipped.

How lines are numbered
  Exactly like the editor (Monaco): a line break is `\\r\\n`, `\\r` or `\\n` and nothing else. Form feed, vertical tab,
  U+0085, U+2028 and U+2029 stay inside their line. A file ending in a newline therefore has a final empty line. This is NOT
  the same as Python's `str.splitlines()` (used by the files API's `line_count`). A UTF-8 BOM does not count as text.
  `Excerpt.text` joins the (redacted) lines with "\\n"; the original separators are not preserved, the line structure is.

How excerpts are found and ranked (all deterministic)
  1. Chunks: a file of up to 60 lines is one chunk; longer files get 40-line windows every 30 lines, plus a window starting at
     every definition line (`def`, `class`, `function`, `export ...`, `fn`, `struct` ... and, in .md/.rst/.txt files, headings).
  2. Terms: lower-cased words of the question, with snake_case and camelCase split (the whole identifier is kept as well),
     minus English stop words and one-character words. Terms that look like identifiers or paths (underscore, camelCase,
     digit, `/`, `.`) weigh double. Terms present in more than half of all chunks (when there are at least 10) are dropped
     as non-discriminating; if no term is left, nothing is returned.
  3. Score of a chunk = BM25 (k1 = 1.2, b = 0.75, idf = ln(1 + (N - df + 0.5) / (df + 0.5))) over the REDACTED text,
     summed in sorted term order, plus 1.5 x weight per query term found in the file's path, plus 3 x weight when the
     chunk's first line defines a symbol named like a term, plus 5 when the question names the file (full relative path or
     file name). For overview questions (readme, overview, architecture, structure, purpose ...) documentation chunks that
     already match get +2. A chunk must have a positive lexical score to be considered at all; there is no fallback.
  4. Chunks scoring below 25% of the best score are dropped. Scores are rounded to 6 places.
  5. Order: score descending, then path ascending (plain string order), then start line ascending.
  6. Selection, greedily in that order: at most 3 excerpts per file; skip a chunk overlapping an already chosen one in the same
     file by more than 25% of its lines; at most 8 excerpts; at most 24,000 characters of excerpt text in total (counted on
     the redacted text). A chunk that does not fit the remaining budget is cut at a line boundary if at least 400 characters
     remain, otherwise skipped. A single over-long line is cut to the budget with a marker. Each excerpt is also limited to
     3,000 characters.
  The scan is bounded (2,000 files, 8 MB read); if a bound is hit `scan_truncated` is True and later paths (in sorted order)
  were not looked at. Words are matched literally: there are no synonyms or stemming, and non-ASCII words work but are not
  normalised further.

Redaction (best effort, NOT a guarantee)
  Applied to every line before ranking and before the size limits. The line count never changes. Replaced with `[REDACTED]`:
  PEM private-key blocks (whole block, one marker per line), well-known token formats (AWS, Google, OpenAI-style `sk-`, `gsk_`,
  GitHub, GitLab, Slack, Stripe, npm, JWTs), `Bearer` tokens, passwords inside URLs, and the VALUE of assignments whose name
  mentions password, secret, token, api key, credentials, private key and the like (quoted values, or unquoted values that
  look like secrets). It will miss secrets in unusual formats, split across lines, encoded, embedded in prose or in minified
  code, and it can redact harmless values (false positives). Treat redaction as a mitigation, not as permission to read
  files that hold real secrets.
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import math
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from app.services.workspace import IGNORED_DIRS, IGNORED_FILES, UnsafePathError, resolve_in_project

logger = logging.getLogger("stackpilot.retrieval")

__all__ = [
    "HARD_MAX_EXCERPTS",
    "HARD_MAX_CHARS",
    "Excerpt",
    "RetrievalResult",
    "retrieve",
    "split_lines",
    "redact_lines",
    "is_prohibited_file_name",
]

# --- limits ------------------------------------------------------------------------------------------------------
HARD_MAX_EXCERPTS = 8
HARD_MAX_CHARS = 24_000
MAX_EXCERPT_CHARS = 3_000
MAX_PER_FILE = 3
MAX_FILE_BYTES = 256 * 1024
MAX_FILES_SCANNED = 2_000
MAX_BYTES_SCANNED = 8 * 1024 * 1024
MAX_QUESTION_CHARS = 4_000
MAX_LINE_CHARS = 10_000  # a longer line means minified or generated text
MIN_TRUNCATED_EXCERPT_CHARS = 400
SMALL_FILE_LINES = 60
WINDOW_LINES = 40
WINDOW_STRIDE = 30
MAX_OVERLAP_FRACTION = 0.25
RELATIVE_CUTOFF = 0.25
UBIQUITOUS_FRACTION = 0.5
UBIQUITOUS_MIN_CHUNKS = 10

BM25_K1 = 1.2
BM25_B = 0.75
PATH_BONUS = 1.5
DEFINITION_BONUS = 3.0
MENTION_BONUS = 5.0
DOC_BONUS = 2.0
IDENTIFIER_WEIGHT = 2.0

TRUNCATION_MARKER = " ...[line truncated]"
REDACTED = "[REDACTED]"
REDACTED_KEY_LINE = "[REDACTED PRIVATE KEY]"

# --- what is never read ------------------------------------------------------------------------------------------
_EXTRA_IGNORED_DIRS = frozenset(
    {".mypy_cache", ".ruff_cache", ".tox", ".gradle", ".terraform", ".cache", ".nuxt", ".svelte-kit", ".parcel-cache",
     "coverage", "htmlcov", "site-packages"}
)
_IGNORED_DIRS_LOWER = frozenset(d.lower() for d in IGNORED_DIRS) | _EXTRA_IGNORED_DIRS
_IGNORED_FILES_LOWER = frozenset(f.lower() for f in IGNORED_FILES)

_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})
_PROHIBITED_PATTERNS = (
    "secrets*", "*.secrets", "*.secret",
    "secret.json", "secret.yml", "secret.yaml", "secret.toml", "secret.ini", "secret.txt", "secret.cfg",
    "credentials*", "credential.json", "credential.yml", "credential.yaml",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.ppk", "*.p8", "*.kdbx", "*.gpg", "*.asc",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".htpasswd", ".git-credentials", ".pgpass", ".dockercfg", ".dockerconfigjson",
    "*.tfvars", "*.tfstate", "*.tfstate.*", "kubeconfig", "*.kubeconfig",
    "service-account*.json", "serviceaccount*.json", "client_secret*.json",
)
_BINARY_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".psd", ".svgz", ".mp3", ".mp4", ".mov", ".avi", ".mkv",
     ".wav", ".flac", ".ogg", ".webm", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".war", ".exe",
     ".dll", ".so", ".dylib", ".bin", ".o", ".obj", ".a", ".lib", ".class", ".pyc", ".pyo", ".pyd", ".whl", ".egg", ".woff",
     ".woff2", ".ttf", ".otf", ".eot", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".db", ".sqlite", ".sqlite3",
     ".mdb", ".iso", ".dmg", ".pkl", ".npy", ".parquet", ".onnx", ".pt", ".h5"}
)
_GENERATED_NAMES = frozenset(
    {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock", "cargo.lock", "composer.lock",
     "gemfile.lock", "go.sum", "bun.lockb", "uv.lock"}
)
_GENERATED_PATTERNS = ("*.min.js", "*.min.css", "*.map", "*.bundle.js", "*.chunk.js", "*_pb2.py", "*_pb2_grpc.py", "*.pb.go", "*.generated.*")
_GENERATED_HEADER = re.compile(r"@generated|code generated\b.*\bdo not edit|\bauto-?generated\b", re.I)
_DOC_EXTENSIONS = frozenset({".md", ".rst", ".txt", ".adoc"})


def is_prohibited_file_name(name: str) -> bool:
    """True for file names that must never be read: `.env` and `*.env`, key files, `secrets*`, `credentials*`, ..."""
    lowered = name.lower()
    if lowered == ".env" or lowered.endswith(".env"):
        return True
    if lowered.startswith(".env.") and lowered not in _ENV_TEMPLATES:
        return True
    return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in _PROHIBITED_PATTERNS)


def _is_generated_name(lowered: str) -> bool:
    return lowered in _GENERATED_NAMES or any(fnmatch.fnmatchcase(lowered, p) for p in _GENERATED_PATTERNS)


# --- lines ---------------------------------------------------------------------------------------------------------
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def split_lines(text: str) -> List[str]:
    """Split like the editor does: only CRLF, CR and LF end a line. Always returns at least one (possibly empty) line."""
    return _LINE_BREAK.split(text)


# --- redaction -----------------------------------------------------------------------------------------------------
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_PEM_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_TOKEN_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        r"\bAIza[0-9A-Za-z_\-]{35}\b",
        r"\bsk-[A-Za-z0-9_\-]{20,}",
        r"\bgsk_[A-Za-z0-9]{20,}",
        r"\bgh[pousr]_[A-Za-z0-9]{30,}",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}",
        r"\bglpat-[A-Za-z0-9_\-]{20,}",
        r"\bxox[abeprs]-[A-Za-z0-9\-]{10,}",
        r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+",
        r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}",
        r"\bnpm_[A-Za-z0-9]{36}\b",
        r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    )
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/\-]{20,}=*")
# Every quantifier below is bounded so that a hostile line (file contents are untrusted) cannot make matching quadratic.
_URL_PASSWORD = re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]{0,19}://[^\s:/@\"']{1,100}:)[^\s@/\"']{1,200}(@)")
_SECRET_NAME = (
    r"(?:api[_-]?key|apikey|secret(?:[_-]?key)?|client[_-]?secret|(?:access|auth|refresh|id|session)[_-]?token|token|"
    r"password|passwd|pwd|passphrase|private[_-]?key|credentials?|authorization)"
)
_ASSIGNMENT = re.compile(
    rf"""(?P<k>{_SECRET_NAME}[A-Za-z0-9_.\-]{{0,40}}["']?[ \t]{{0,20}}[:=][ \t]{{0,20}})"""
    r"""(?P<v>"[^"\n]{4,}"|'[^'\n]{4,}'|[^\s"'`,;#(){}\[\]]{8,})""",
    re.I,
)
_PLACEHOLDER = re.compile(
    r"^(?:x+|\*+|\.+|<[^>]*>|\$\{[^}]*\}|\{\{[^}]*\}\}|%\([^)]*\)s?|your[-_ ].*|my[-_ ].*|.*[-_ ]here|"
    r"changeme|change[-_]me|password|secret|example|test|dummy|placeholder|none|null|undefined|true|false|todo)$",
    re.I,
)
_CODE_REFERENCE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")  # settings.API_KEY, os.environ


def _looks_like_secret(raw: str) -> bool:
    quoted = len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]
    value = raw[1:-1] if quoted else raw
    if _PLACEHOLDER.match(value.strip()):
        return False
    if quoted:
        return len(value) >= 6 and not value.startswith(("${", "{{", "<", "%("))
    # unquoted (env files, YAML, shell, INI): must look like a credential, not like a code reference or a path
    if value.startswith(("$", "%", "<", "{", "/", ".")) or "(" in value:
        return False
    return any(c.isdigit() for c in value) and not _CODE_REFERENCE.match(value)


def _redact_line(line: str) -> Tuple[str, int]:
    count = 0
    for pattern in _TOKEN_PATTERNS:
        line, n = pattern.subn(REDACTED, line)
        count += n
    line, n = _BEARER.subn(lambda m: m.group(1) + REDACTED, line)
    count += n
    line, n = _URL_PASSWORD.subn(lambda m: m.group(1) + REDACTED + m.group(2), line)
    count += n

    replaced = 0

    def assignment(match: "re.Match[str]") -> str:
        nonlocal replaced
        raw = match.group("v")
        if raw.startswith(REDACTED) or not _looks_like_secret(raw):
            return match.group(0)
        replaced += 1
        quote = raw[0] if raw[0] in "\"'" and raw[-1] == raw[0] and len(raw) >= 2 else ""
        return match.group("k") + quote + REDACTED + quote

    line = _ASSIGNMENT.sub(assignment, line)
    return line, count + replaced


def redact_lines(lines: Sequence[str]) -> Tuple[List[str], int]:
    """Redact secrets line by line. Returns (lines, number of replacements); the number of lines never changes."""
    out: List[str] = []
    total = 0
    in_key_block = False
    for line in lines:
        if in_key_block:
            out.append(REDACTED_KEY_LINE)
            if _PEM_END.search(line):
                in_key_block = False
            continue
        if _PEM_BEGIN.search(line):
            out.append(REDACTED_KEY_LINE)
            total += 1
            in_key_block = not _PEM_END.search(line)
            continue
        redacted, n = _redact_line(line)
        out.append(redacted)
        total += n
    return out, total


# --- tokens --------------------------------------------------------------------------------------------------------
_WORD = re.compile(r"[^\W\d]\w*|\d+")
_CAMEL_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_STOP_WORDS = frozenset(
    "a about above after again all also am an and any are as at be because been before being below between both but by can "
    "could did do does doing down during each few for from further had has have having he her here hers him his how i if in "
    "into is it its itself just me more most my myself no nor not of off on once only or other our ours out over own same she "
    "should so some such than that the their theirs them then there these they this those through to too under until up us "
    "very was we were what when where which while who whom why will with would you your yours please tell explain show give "
    "find".split()
)
_OVERVIEW_TERMS = frozenset({"readme", "overview", "architecture", "structure", "purpose", "introduction", "about", "summary", "describe"})


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for word in _WORD.findall(text):
        lowered = word.lower()
        parts = [p.lower() for p in _CAMEL_PARTS.findall(word.replace("_", " "))] if word.isascii() else []
        if len(parts) > 1 or not parts:
            out.append(lowered)  # the whole identifier (also the only token for non-ASCII words)
        out.extend(parts)
    return out


def _identifier_like(word: str) -> bool:
    return "_" in word or "/" in word or "." in word or any(c.isdigit() for c in word) or bool(re.search(r"[a-z][A-Z]", word))


def _question_terms(question: str) -> Dict[str, float]:
    """term -> weight. Identifier- or path-like words weigh double."""
    weights: Dict[str, float] = {}
    for raw in re.findall(r"[^\s,;:!?()\[\]{}\"'`<>]+", question):
        raw = raw.strip(".")
        heavy = _identifier_like(raw)
        for term in _tokens(raw):
            if len(term) < 2 or term in _STOP_WORDS:
                continue
            weights[term] = max(weights.get(term, 0.0), IDENTIFIER_WEIGHT if heavy else 1.0)
    return weights


# --- chunks --------------------------------------------------------------------------------------------------------
_CODE_ANCHOR = re.compile(
    r"^\s*(?:async\s+def|def|class|function|export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|interface|type|enum)|"
    r"interface|enum|struct|impl|fn|func|trait|pub\s+(?:fn|struct|enum|trait)|public\s+class)\b"
)
_DOC_ANCHOR = re.compile(r"^#{1,6}\s+\S")
_SYMBOL = re.compile(r"\b(?:def|class|function|interface|type|enum|struct|trait|fn|func|const|let|var)\s+([A-Za-z_]\w*)")


@dataclass(frozen=True)
class _Chunk:
    path: str
    start: int  # 0-based, inclusive
    end: int  # 0-based, exclusive
    tokens: int = 0
    counts: Mapping[str, int] = field(default_factory=dict)
    symbol: Optional[str] = None


def _chunk_ranges(lines: Sequence[str], is_doc: bool) -> List[Tuple[int, int]]:
    n = len(lines)
    if n <= SMALL_FILE_LINES:
        return [(0, n)]
    starts = set(range(0, n, WINDOW_STRIDE))
    anchor = _DOC_ANCHOR if is_doc else _CODE_ANCHOR
    starts.update(i for i, line in enumerate(lines) if anchor.match(line))
    return sorted({(s, min(n, s + WINDOW_LINES)) for s in starts})


# --- results -------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Excerpt:
    id: str  # "E1", "E2", ... in rank order
    path: str  # relative to the project root, forward slashes
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    text: str  # the lines start_line..end_line (redacted), joined with "\n"
    file_sha256: str  # SHA-256 of the file's bytes as they were read
    score: float
    redactions: int  # replacements made inside this excerpt


@dataclass(frozen=True)
class RetrievalResult:
    excerpts: Tuple[Excerpt, ...] = ()
    total_chars: int = 0
    redactions: int = 0  # replacements inside the returned excerpts
    files_scanned: int = 0  # files actually read
    skipped: Mapping[str, int] = field(default_factory=dict)  # reason -> count (counts only, never names)
    scan_truncated: bool = False
    problem: Optional[str] = None  # set when nothing could be searched at all


def _empty(problem: Optional[str] = None, **kwargs) -> RetrievalResult:
    return RetrievalResult(problem=problem, **kwargs)


# --- reading files safely ------------------------------------------------------------------------------------------
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_link_like(path: str) -> bool:
    """True for symlinks, junctions and other reparse points, and for anything that cannot be inspected."""
    try:
        info = os.lstat(path)
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _real_path(path: str) -> str:
    return os.path.realpath(path)


def _inside(root_real: str, candidate_real: str) -> bool:
    root_n, cand_n = os.path.normcase(root_real), os.path.normcase(candidate_real)
    return cand_n == root_n or cand_n.startswith(root_n.rstrip(os.sep) + os.sep)


def _ignored_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered in _IGNORED_DIRS_LOWER or lowered.endswith(".egg-info")


def _walk(root_real: str, skipped: Counter) -> Iterator[Tuple[str, str]]:
    """Yield (relative posix path, absolute path) of regular-looking files, in a fixed order."""
    for dirpath, dirnames, filenames in os.walk(root_real, followlinks=False):
        kept = []
        for name in sorted(dirnames):
            if _ignored_dir(name):
                skipped["ignored"] += 1
            elif _is_link_like(os.path.join(dirpath, name)):
                skipped["unsafe"] += 1
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            absolute = os.path.join(dirpath, name)
            relative = os.path.relpath(absolute, root_real).replace(os.sep, "/")
            yield relative, absolute


@dataclass(frozen=True)
class _Loaded:
    path: str
    sha256: str
    lines: Tuple[str, ...]  # redacted
    redactions: int
    is_doc: bool
    size: int


def _load(root_real: str, relative: str, absolute: str) -> Tuple[Optional[_Loaded], Optional[str]]:
    """Read one file if it is allowed. Returns (loaded, None) or (None, reason it was skipped)."""
    name = relative.rsplit("/", 1)[-1]
    lowered = name.lower()
    extension = os.path.splitext(lowered)[1]

    if is_prohibited_file_name(name):
        return None, "prohibited"
    if lowered in _IGNORED_FILES_LOWER:
        return None, "ignored"
    if extension in _BINARY_EXTENSIONS:
        return None, "binary"
    if _is_generated_name(lowered):
        return None, "generated"

    try:
        resolved = resolve_in_project(root_real, relative)
    except (UnsafePathError, OSError, ValueError):
        return None, "unsafe"
    expected = os.path.join(root_real, *relative.split("/"))
    if os.path.normcase(str(resolved)) != os.path.normcase(expected):
        return None, "unsafe"  # an intermediate link or a case/short-name trick led somewhere else
    if _is_link_like(absolute):
        return None, "unsafe"
    if not _inside(root_real, _real_path(absolute)):
        return None, "unsafe"

    try:
        before = os.lstat(absolute)
        if not stat.S_ISREG(before.st_mode):
            return None, "unsafe"
        if before.st_size == 0:
            return None, "empty"
        if before.st_size > MAX_FILE_BYTES:
            return None, "too_large"
        with open(absolute, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if opened.st_ino and before.st_ino and (opened.st_ino, opened.st_dev) != (before.st_ino, before.st_dev):
                return None, "unsafe"  # the file was swapped between the check and the open
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None, "unreadable"

    if len(data) > MAX_FILE_BYTES:
        return None, "too_large"
    if b"\x00" in data[:8192]:
        return None, "binary"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "binary"
    if text.startswith("\ufeff"):
        text = text[1:]
    if _GENERATED_HEADER.search(text[:600]):
        return None, "generated"

    lines = split_lines(text)
    if any(len(line) > MAX_LINE_CHARS for line in lines):
        return None, "generated"
    redacted, count = redact_lines(lines)
    return (
        _Loaded(
            path=relative,
            sha256=hashlib.sha256(data).hexdigest(),
            lines=tuple(redacted),
            redactions=count,
            is_doc=extension in _DOC_EXTENSIONS,
            size=len(data),
        ),
        None,
    )


# --- ranking -------------------------------------------------------------------------------------------------------
def _path_terms(path: str) -> frozenset:
    return frozenset(_tokens(path.replace("/", " ").replace(".", " ")))


def _mentions_file(question_lower: str, path: str) -> bool:
    relative = path.lower()
    base = relative.rsplit("/", 1)[-1]
    normalized = question_lower.replace("\\", "/")
    if relative in normalized:
        return True
    return bool(re.search(rf"(?<![\w.\-/]){re.escape(base)}(?![\w\-])", normalized))


def _clamp(value: object, ceiling: int) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return min(value, ceiling)


def retrieve(
    project_root: "str | os.PathLike[str]",
    question: str,
    *,
    max_excerpts: int = HARD_MAX_EXCERPTS,
    max_chars: int = HARD_MAX_CHARS,
) -> RetrievalResult:
    """Find the excerpts of the project that best match `question`.

    Never raises for bad input or unreadable files: it returns what it safely can, possibly nothing. The limits can only be
    lowered (to at most 8 excerpts and 24,000 characters); a malformed limit yields an empty result.
    """
    limit_excerpts, limit_chars = _clamp(max_excerpts, HARD_MAX_EXCERPTS), _clamp(max_chars, HARD_MAX_CHARS)
    if limit_excerpts is None or limit_chars is None:
        return _empty("The retrieval limits are invalid.")
    if not isinstance(question, str):
        return _empty("The question must be text.")
    try:
        root_text = os.fspath(project_root)
        if not isinstance(root_text, str) or not root_text.strip() or "\x00" in root_text:
            return _empty("The project folder is invalid.")
        root_real = _real_path(root_text)
    except (TypeError, ValueError, OSError):
        return _empty("The project folder is invalid.")
    if not os.path.isdir(root_real):
        return _empty("The project folder does not exist.")

    question = question[:MAX_QUESTION_CHARS]
    weights = _question_terms(question)
    if not weights or limit_excerpts == 0 or limit_chars == 0:
        return _empty()

    # 1. read the allowed files (fixed order, bounded)
    skipped: Counter = Counter()
    loaded: List[_Loaded] = []
    examined = 0
    scanned_bytes = 0
    truncated = False
    for relative, absolute in _walk(root_real, skipped):
        if examined >= MAX_FILES_SCANNED or scanned_bytes >= MAX_BYTES_SCANNED:
            truncated = True
            break
        examined += 1
        item, reason = _load(root_real, relative, absolute)
        if item is None:
            skipped[reason or "unreadable"] += 1
            continue
        loaded.append(item)
        scanned_bytes += item.size

    # 2. chunk and count terms
    chunks: List[_Chunk] = []
    owners: Dict[str, _Loaded] = {item.path: item for item in loaded}
    query_set = frozenset(weights)
    for item in loaded:
        for start, end in _chunk_ranges(item.lines, item.is_doc):
            words = _tokens("\n".join(item.lines[start:end]))
            counts = Counter(w for w in words if w in query_set)
            first = item.lines[start]
            symbol_match = _SYMBOL.search(first)
            chunks.append(_Chunk(item.path, start, end, len(words), counts, symbol_match.group(1).lower() if symbol_match else None))

    total = len(chunks)
    if total == 0:
        return _result((), 0, 0, len(loaded), skipped, truncated)

    # 3. drop terms that appear almost everywhere, compute idf
    document_frequency = {t: sum(1 for c in chunks if c.counts.get(t)) for t in query_set}
    path_term_sets = {item.path: _path_terms(item.path) for item in loaded}
    for t in list(query_set):
        in_paths = any(t in terms for terms in path_term_sets.values())
        if total >= UBIQUITOUS_MIN_CHUNKS and document_frequency[t] / total > UBIQUITOUS_FRACTION:
            weights.pop(t)
        elif document_frequency[t] == 0 and not in_paths:
            weights.pop(t)
    if not weights:
        return _result((), 0, 0, len(loaded), skipped, truncated)
    terms = sorted(weights)
    idf = {t: math.log(1.0 + (total - document_frequency[t] + 0.5) / (document_frequency[t] + 0.5)) for t in terms}
    average_length = max(1.0, sum(c.tokens for c in chunks) / total)

    question_lower = question.lower()
    overview = any(t in _OVERVIEW_TERMS for t in _tokens(question_lower))
    mentioned = {item.path: _mentions_file(question_lower, item.path) for item in loaded}

    # 4. score
    scored: List[Tuple[float, _Chunk]] = []
    for chunk in chunks:
        score = 0.0
        for t in terms:
            tf = chunk.counts.get(t, 0)
            if tf:
                norm = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * chunk.tokens / average_length)
                score += weights[t] * idf[t] * tf * (BM25_K1 + 1.0) / norm
        score += sum(PATH_BONUS * weights[t] for t in terms if t in path_term_sets[chunk.path])
        if chunk.symbol and chunk.symbol in weights:
            score += DEFINITION_BONUS * weights[chunk.symbol]
        if mentioned[chunk.path]:
            score += MENTION_BONUS
        if score <= 0.0:
            continue
        if overview and owners[chunk.path].is_doc:
            score += DOC_BONUS
        scored.append((round(score, 6), chunk))
    if not scored:
        return _result((), 0, 0, len(loaded), skipped, truncated)

    best = max(s for s, _ in scored)
    ranked = sorted(
        (item for item in scored if item[0] >= RELATIVE_CUTOFF * best),
        key=lambda item: (-item[0], item[1].path, item[1].start),
    )

    # 5. select
    chosen: List[Excerpt] = []
    taken: Dict[str, List[Tuple[int, int]]] = {}
    used = 0
    for score, chunk in ranked:
        if len(chosen) >= limit_excerpts:
            break
        ranges = taken.setdefault(chunk.path, [])
        if len(ranges) >= MAX_PER_FILE:
            continue
        length = chunk.end - chunk.start
        if any(min(chunk.end, e) - max(chunk.start, s) > MAX_OVERLAP_FRACTION * length for s, e in ranges):
            continue
        item = owners[chunk.path]
        built = _fit(item.lines, chunk.start, chunk.end, min(MAX_EXCERPT_CHARS, limit_chars - used), limit_chars - used, query_set)
        if built is None:
            continue
        text, first, end = built
        if any(min(end, e) - max(first, s) > MAX_OVERLAP_FRACTION * (end - first) for s, e in ranges):
            continue  # the part that was kept overlaps an excerpt already chosen
        ranges.append((first, end))
        chosen.append(
            Excerpt(
                id=f"E{len(chosen) + 1}",
                path=chunk.path,
                start_line=first + 1,
                end_line=end,
                text=text,
                file_sha256=item.sha256,
                score=score,
                redactions=text.count("[REDACTED"),
            )
        )
        used += len(text)

    return _result(tuple(chosen), used, sum(e.redactions for e in chosen), len(loaded), skipped, truncated)


def _fit(
    lines: Sequence[str], start: int, end: int, budget: int, remaining: int, terms: frozenset
) -> Optional[Tuple[str, int, int]]:
    """The lines start..end (0-based, end exclusive) joined, reduced to fit `budget` characters.

    Returns (text, first line index, end index exclusive) or None. If everything fits it is returned unchanged. Otherwise,
    and only if at least MIN_TRUNCATED_EXCERPT_CHARS of the result's budget remain, the contiguous run of whole lines that
    fits and contains the most matching words is kept (earliest wins a tie), so a cut never throws away the matching line.
    A single matching line that is longer than the budget is itself cut, with a marker, and keeps its line number.
    """
    if budget <= 0:
        return None
    text = "\n".join(lines[start:end])
    if len(text) <= budget:
        return text, start, end
    if remaining < MIN_TRUNCATED_EXCERPT_CHARS:
        return None
    matches = [sum(1 for w in _tokens(lines[i]) if w in terms) for i in range(start, end)]
    top = max(matches)
    if top > 0:
        best_line = start + matches.index(top)
        if len(lines[best_line]) > budget:
            if budget <= len(TRUNCATION_MARKER) + 20:
                return None
            return lines[best_line][: budget - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER, best_line, best_line + 1
    best: Optional[Tuple[int, int, int]] = None  # (matches, first, last exclusive)
    for first in range(start, end):
        size, last, found = 0, first, 0
        while last < end:
            added = len(lines[last]) + (1 if last > first else 0)
            if size + added > budget:
                break
            size += added
            found += matches[last - start]
            last += 1
        if last > first and (best is None or found > best[0]):
            best = (found, first, last)
    if best is None:  # every line is longer than the budget and none matched: cut the first line
        if budget <= len(TRUNCATION_MARKER) + 20:
            return None
        return lines[start][: budget - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER, start, start + 1
    _, first, last = best
    return "\n".join(lines[first:last]), first, last


def _result(excerpts, total_chars, redactions, scanned, skipped, truncated) -> RetrievalResult:
    logger.debug("retrieval: %d excerpts, %d chars, %d files read, truncated=%s", len(excerpts), total_chars, scanned, truncated)
    return RetrievalResult(
        excerpts=tuple(excerpts),
        total_chars=total_chars,
        redactions=redactions,
        files_scanned=scanned,
        skipped=dict(skipped),
        scan_truncated=truncated,
    )
