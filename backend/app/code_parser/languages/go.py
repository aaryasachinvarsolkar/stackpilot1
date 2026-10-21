import re
from typing import List, Optional, Tuple
from tree_sitter import Node
from app.code_parser.models import CodeSymbol, ImportReference, SymbolKind


def _get_node_text(node: Optional[Node], source_bytes: bytes) -> str:
    if not node:
        return ""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _clean_string(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith('`') and s.endswith('`')):
        return s[1:-1]
    return s


def _extract_go_receiver_type(receiver_node: Optional[Node], source_bytes: bytes) -> Optional[str]:
    if not receiver_node:
        return None
    raw = _get_node_text(receiver_node, source_bytes)
    # Extracts type from (c *Config) or (Config) or (c Config)
    # Match alphanumeric word at end of receiver before ')'
    m = re.search(r"(\w+)\s*\)$", raw)
    if m:
        return m.group(1)
    return None


def extract_go_symbols_and_imports(
    root_node: Node,
    source_bytes: bytes,
) -> Tuple[List[CodeSymbol], List[ImportReference]]:
    symbols: List[CodeSymbol] = []
    imports: List[ImportReference] = []

    def visit(node: Node, parent_name: Optional[str] = None):
        if node.type == "import_declaration":
            start_line = node.start_point[0] + 1
            # Could be import "fmt" or import ( ... )
            for child in node.children:
                if child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    alias_node = child.child_by_field_name("name")
                    mod = _clean_string(_get_node_text(path_node, source_bytes)) if path_node else ""
                    alias = _get_node_text(alias_node, source_bytes) if alias_node else None
                    imports.append(ImportReference(
                        module=mod,
                        alias=alias,
                        line_number=child.start_point[0] + 1,
                    ))
                elif child.type == "import_spec_list":
                    for sub in child.children:
                        if sub.type == "import_spec":
                            path_node = sub.child_by_field_name("path")
                            alias_node = sub.child_by_field_name("name")
                            mod = _clean_string(_get_node_text(path_node, source_bytes)) if path_node else ""
                            alias = _get_node_text(alias_node, source_bytes) if alias_node else None
                            imports.append(ImportReference(
                                module=mod,
                                alias=alias,
                                line_number=sub.start_point[0] + 1,
                            ))

        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    type_node = child.child_by_field_name("type")
                    name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
                    start_line = child.start_point[0] + 1
                    end_line = child.end_point[0] + 1

                    kind = SymbolKind.TYPE_DEF
                    if type_node and type_node.type == "struct_type":
                        kind = SymbolKind.STRUCT
                    elif type_node and type_node.type == "interface_type":
                        kind = SymbolKind.INTERFACE

                    symbols.append(CodeSymbol(
                        name=name,
                        kind=kind,
                        start_line=start_line,
                        end_line=end_line,
                        parent_symbol=parent_name,
                        signature=f"type {name} {kind.value}",
                    ))

        elif node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            fn_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            result_node = node.child_by_field_name("result")
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            sig_parts = [f"func {fn_name}"]
            if params_node:
                sig_parts.append(_get_node_text(params_node, source_bytes))
            if result_node:
                sig_parts.append(f" {_get_node_text(result_node, source_bytes)}")

            symbols.append(CodeSymbol(
                name=fn_name,
                kind=SymbolKind.FUNCTION,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature="".join(sig_parts),
            ))

        elif node.type == "method_declaration":
            receiver_node = node.child_by_field_name("receiver")
            receiver_type = _extract_go_receiver_type(receiver_node, source_bytes)
            name_node = node.child_by_field_name("name")
            m_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            result_node = node.child_by_field_name("result")
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            sig_parts = ["func "]
            if receiver_node:
                sig_parts.append(f"{_get_node_text(receiver_node, source_bytes)} ")
            sig_parts.append(m_name)
            if params_node:
                sig_parts.append(_get_node_text(params_node, source_bytes))
            if result_node:
                sig_parts.append(f" {_get_node_text(result_node, source_bytes)}")

            symbols.append(CodeSymbol(
                name=m_name,
                kind=SymbolKind.METHOD,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=receiver_type or parent_name,
                signature="".join(sig_parts),
            ))

        # Fall through to children
        for child in node.children:
            visit(child, parent_name=parent_name)

    visit(root_node)
    return symbols, imports
