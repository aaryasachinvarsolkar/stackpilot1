from typing import List, Optional, Tuple
from tree_sitter import Node
from app.code_parser.models import CodeSymbol, ImportReference, SymbolKind


def _get_node_text(node: Optional[Node], source_bytes: bytes) -> str:
    if not node:
        return ""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _clean_string(s: str) -> str:
    s = s.strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    return s


def extract_typescript_symbols_and_imports(
    root_node: Node,
    source_bytes: bytes,
) -> Tuple[List[CodeSymbol], List[ImportReference]]:
    symbols: List[CodeSymbol] = []
    imports: List[ImportReference] = []

    def visit(node: Node, parent_name: Optional[str] = None, in_class: bool = False):
        if node.type == "import_statement":
            start_line = node.start_point[0] + 1
            source_node = node.child_by_field_name("source")
            module_name = _clean_string(_get_node_text(source_node, source_bytes)) if source_node else ""

            clause_node = None
            for child in node.children:
                if child.type == "import_clause":
                    clause_node = child
                    break

            names: List[str] = []
            alias: Optional[str] = None
            is_wildcard = False

            if clause_node:
                for child in clause_node.children:
                    if child.type == "identifier":
                        # default import: import React from 'react'
                        names.append(_get_node_text(child, source_bytes))
                    elif child.type == "named_imports":
                        for spec in child.children:
                            if spec.type == "import_specifier":
                                n_node = spec.child_by_field_name("name")
                                if n_node:
                                    names.append(_get_node_text(n_node, source_bytes))
                                elif spec.named_children:
                                    names.append(_get_node_text(spec.named_children[0], source_bytes))
                    elif child.type == "namespace_import":
                        is_wildcard = True
                        for sub in child.children:
                            if sub.type == "identifier":
                                alias = _get_node_text(sub, source_bytes)

            imports.append(ImportReference(
                module=module_name,
                names=names,
                is_wildcard=is_wildcard,
                alias=alias,
                line_number=start_line,
            ))

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            class_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            sig = f"class {class_name}"
            body_node = node.child_by_field_name("body")

            symbols.append(CodeSymbol(
                name=class_name,
                kind=SymbolKind.CLASS,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=sig,
            ))

            if body_node:
                for child in body_node.children:
                    visit(child, parent_name=class_name, in_class=True)
            return

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            iface_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            symbols.append(CodeSymbol(
                name=iface_name,
                kind=SymbolKind.INTERFACE,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=f"interface {iface_name}",
            ))

        elif node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            type_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            symbols.append(CodeSymbol(
                name=type_name,
                kind=SymbolKind.TYPE_DEF,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=f"type {type_name}",
            ))

        elif node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            fn_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            ret_node = node.child_by_field_name("return_type")
            body_node = node.child_by_field_name("body")
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            sig_parts = [f"function {fn_name}"]
            if params_node:
                sig_parts.append(_get_node_text(params_node, source_bytes))
            if ret_node:
                sig_parts.append(_get_node_text(ret_node, source_bytes))
            sig = "".join(sig_parts)

            symbols.append(CodeSymbol(
                name=fn_name,
                kind=SymbolKind.FUNCTION,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=sig,
            ))

            if body_node:
                for child in body_node.children:
                    visit(child, parent_name=fn_name, in_class=False)
            return

        elif node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            m_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            ret_node = node.child_by_field_name("return_type")
            body_node = node.child_by_field_name("body")
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            sig_parts = [m_name]
            if params_node:
                sig_parts.append(_get_node_text(params_node, source_bytes))
            if ret_node:
                sig_parts.append(_get_node_text(ret_node, source_bytes))
            sig = "".join(sig_parts)

            symbols.append(CodeSymbol(
                name=m_name,
                kind=SymbolKind.METHOD,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=sig,
            ))

            if body_node:
                for child in body_node.children:
                    visit(child, parent_name=m_name, in_class=False)
            return

        elif node.type in ("lexical_declaration", "variable_declaration"):
            # Check for const fn = () => {} or const fn = function() {}
            for decl in node.children:
                if decl.type == "variable_declarator":
                    name_node = decl.child_by_field_name("name")
                    val_node = decl.child_by_field_name("value")
                    if val_node and val_node.type in ("arrow_function", "function_expression"):
                        fn_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        params_node = val_node.child_by_field_name("parameters")
                        ret_node = val_node.child_by_field_name("return_type")

                        sig_parts = [f"const {fn_name} = "]
                        if params_node:
                            sig_parts.append(_get_node_text(params_node, source_bytes))
                        if ret_node:
                            sig_parts.append(_get_node_text(ret_node, source_bytes))
                        sig_parts.append(" => ...")

                        symbols.append(CodeSymbol(
                            name=fn_name,
                            kind=SymbolKind.FUNCTION,
                            start_line=start_line,
                            end_line=end_line,
                            parent_symbol=parent_name,
                            signature="".join(sig_parts),
                        ))

                        body_node = val_node.child_by_field_name("body")
                        if body_node:
                            for child in body_node.children:
                                visit(child, parent_name=fn_name, in_class=False)
                        return

        # Fall through to children
        for child in node.children:
            visit(child, parent_name=parent_name, in_class=in_class)

    visit(root_node)
    return symbols, imports
