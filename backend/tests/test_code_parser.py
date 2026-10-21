from pathlib import Path
import pytest
from app.code_parser import (
    CodeSymbol,
    ImportReference,
    ParsedFile,
    SymbolKind,
    parse_source,
    parse_file,
    detect_language,
)


def test_detect_language():
    assert detect_language("main.py") == "python"
    assert detect_language("app/index.ts") == "typescript"
    assert detect_language("components/Header.tsx") == "tsx"
    assert detect_language("server.js") == "javascript"
    assert detect_language("server.mjs") == "javascript"
    assert detect_language("main.go") == "go"
    assert detect_language("unknown.xyz") is None


def test_empty_source():
    res = parse_source("", "test.py")
    assert res.language == "python"
    assert res.syntax_valid is True
    assert res.symbols == []
    assert res.imports == []
    assert res.error is None

    res_ws = parse_source("   \n\n\t  ", "test.ts")
    assert res_ws.language == "typescript"
    assert res_ws.syntax_valid is True
    assert res_ws.symbols == []


def test_unsupported_language():
    res = parse_source("hello world", "test.unknown")
    assert res.language == "unsupported"
    assert res.syntax_valid is False
    assert "Unsupported" in (res.error or "")


def test_python_parsing():
    source = '''"""Module docstring."""
import os
from typing import List, Optional as Opt

class BaseService:
    """Service base class."""
    def __init__(self, name: str):
        self.name = name

    def execute(self) -> bool:
        return True

def standalone_func(x: int, y: int = 0) -> int:
    """Add numbers."""
    def inner_helper():
        return x
    return inner_helper() + y
'''
    res = parse_source(source, "service.py")
    assert res.language == "python"
    assert res.syntax_valid is True

    # Imports check
    mod_names = [imp.module for imp in res.imports]
    assert "os" in mod_names
    assert "typing" in mod_names

    # Symbols check
    symbols_by_name = {s.name: s for s in res.symbols}
    assert "BaseService" in symbols_by_name
    cls_sym = symbols_by_name["BaseService"]
    assert cls_sym.kind == SymbolKind.CLASS
    assert cls_sym.docstring == "Service base class."
    assert cls_sym.start_line == 5
    assert cls_sym.parent_symbol is None

    assert "__init__" in symbols_by_name
    init_sym = symbols_by_name["__init__"]
    assert init_sym.kind == SymbolKind.METHOD
    assert init_sym.parent_symbol == "BaseService"

    assert "execute" in symbols_by_name
    exec_sym = symbols_by_name["execute"]
    assert exec_sym.kind == SymbolKind.METHOD
    assert exec_sym.parent_symbol == "BaseService"

    assert "standalone_func" in symbols_by_name
    func_sym = symbols_by_name["standalone_func"]
    assert func_sym.kind == SymbolKind.FUNCTION
    assert func_sym.parent_symbol is None
    assert func_sym.docstring == "Add numbers."

    assert "inner_helper" in symbols_by_name
    helper_sym = symbols_by_name["inner_helper"]
    assert helper_sym.kind == SymbolKind.FUNCTION
    assert helper_sym.parent_symbol == "standalone_func"


def test_typescript_parsing():
    source = '''
import React, { useState } from 'react';
import * as path from 'path';

export interface UserProfile {
    id: string;
    email: string;
}

export type UserId = string | number;

export class UserManager {
    private users: UserProfile[] = [];

    public findUser(id: string): UserProfile | undefined {
        return this.users.find(u => u.id === id);
    }
}

export function formatName(first: string, last: string): string {
    return `${first} ${last}`;
}

export const multiply = (a: number, b: number): number => {
    return a * b;
};
'''
    res = parse_source(source, "users.ts")
    assert res.language == "typescript"
    assert res.syntax_valid is True

    # Imports
    assert any(imp.module == "react" for imp in res.imports)
    assert any(imp.module == "path" and imp.is_wildcard for imp in res.imports)

    symbols_by_name = {s.name: s for s in res.symbols}

    assert "UserProfile" in symbols_by_name
    assert symbols_by_name["UserProfile"].kind == SymbolKind.INTERFACE

    assert "UserId" in symbols_by_name
    assert symbols_by_name["UserId"].kind == SymbolKind.TYPE_DEF

    assert "UserManager" in symbols_by_name
    assert symbols_by_name["UserManager"].kind == SymbolKind.CLASS

    assert "findUser" in symbols_by_name
    assert symbols_by_name["findUser"].kind == SymbolKind.METHOD
    assert symbols_by_name["findUser"].parent_symbol == "UserManager"

    assert "formatName" in symbols_by_name
    assert symbols_by_name["formatName"].kind == SymbolKind.FUNCTION

    assert "multiply" in symbols_by_name
    assert symbols_by_name["multiply"].kind == SymbolKind.FUNCTION


def test_javascript_parsing():
    source = '''
import express from 'express';

class RouterService {
    setup() {
        return true;
    }
}

function handleRequest(req, res) {
    res.send("ok");
}

const computeHash = (data) => data.length;
'''
    res = parse_source(source, "server.js")
    assert res.language == "javascript"
    assert res.syntax_valid is True

    sym_names = [s.name for s in res.symbols]
    assert "RouterService" in sym_names
    assert "setup" in sym_names
    assert "handleRequest" in sym_names
    assert "computeHash" in sym_names


def test_go_parsing():
    source = '''package repository

import (
    "context"
    db "database/sql"
)

type DatabaseConfig struct {
    Host string
    Port int
}

type Querier interface {
    QueryRow(ctx context.Context, query string) *db.Row
}

func Connect(cfg DatabaseConfig) (*db.DB, error) {
    return nil, nil
}

func (c *DatabaseConfig) DSN() string {
    return ""
}
'''
    res = parse_source(source, "db.go")
    assert res.language == "go"
    assert res.syntax_valid is True

    # Imports
    mods = {imp.module: imp.alias for imp in res.imports}
    assert "context" in mods
    assert "database/sql" in mods
    assert mods["database/sql"] == "db"

    symbols_by_name = {s.name: s for s in res.symbols}

    assert "DatabaseConfig" in symbols_by_name
    assert symbols_by_name["DatabaseConfig"].kind == SymbolKind.STRUCT

    assert "Querier" in symbols_by_name
    assert symbols_by_name["Querier"].kind == SymbolKind.INTERFACE

    assert "Connect" in symbols_by_name
    assert symbols_by_name["Connect"].kind == SymbolKind.FUNCTION
    assert symbols_by_name["Connect"].parent_symbol is None

    assert "DSN" in symbols_by_name
    assert symbols_by_name["DSN"].kind == SymbolKind.METHOD
    assert symbols_by_name["DSN"].parent_symbol == "DatabaseConfig"


def test_malformed_syntax_error_handling():
    # Tree-sitter handles incomplete/malformed code gracefully
    malformed_py = "def incomplete_func(\nclass Broken:\n    def valid_sub(): pass\n"
    res = parse_source(malformed_py, "broken.py")
    assert res.language == "python"
    assert res.syntax_valid is False  # root_node.has_error is True
    # Should still extract symbols that can be parsed
    sym_names = [s.name for s in res.symbols]
    assert "Broken" in sym_names or "valid_sub" in sym_names or "incomplete_func" in sym_names


def test_non_utf8_decoding():
    # Contains invalid UTF-8 bytes
    invalid_bytes = b"def valid_name():\n    # \xff\xfe invalid\n    return 1\n"
    res = parse_source(invalid_bytes, "invalid.py")
    assert res.language == "python"
    sym_names = [s.name for s in res.symbols]
    assert "valid_name" in sym_names


def test_deterministic_output():
    src = "def a(): pass\ndef b(): pass\nclass C:\n    def m(): pass\n"
    res1 = parse_source(src, "test.py")
    res2 = parse_source(src, "test.py")
    assert res1 == res2
