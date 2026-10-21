from typing import List, Optional, Tuple
from tree_sitter import Node
from app.code_parser.models import CodeSymbol, ImportReference, SymbolKind


def _get_node_text(node: Optional[Node], source_bytes: bytes) -> str:
    if not node:
        return ""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_docstring(body_node: Optional[Node], source_bytes: bytes) -> Optional[str]:
    if not body_node:
        return None
    for child in body_node.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    raw = _get_node_text(sub, source_bytes).strip()
                    # Strip leading/trailing quotes (''' or """ or ' or ")
                    if (raw.startswith('"""') and raw.endswith('"""')) or (raw.startswith("'''") and raw.endswith("'''")):
                        return raw[3:-3].strip()
                    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
                        return raw[1:-1].strip()
                    return raw
        elif child.type not in ("comment", "\n"):
            break
    return None


def extract_python_symbols_and_imports(
    root_node: Node,
    source_bytes: bytes,
) -> Tuple[List[CodeSymbol], List[ImportReference]]:
    symbols: List[CodeSymbol] = []
    imports: List[ImportReference] = []

    def visit(node: Node, parent_name: Optional[str] = None, in_class: bool = False):
        if node.type == "import_statement":
            # e.g. import os, sys as system
            start_line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(ImportReference(
                        module=_get_node_text(child, source_bytes),
                        line_number=start_line,
                    ))
                elif child.type == "aliased_import":
                    # name as alias
                    orig = None
                    alias = None
                    for sub in child.children:
                        if sub.type == "dotted_name" and orig is None:
                            orig = _get_node_text(sub, source_bytes)
                        elif sub.type == "identifier":
                            alias = _get_node_text(sub, source_bytes)
                    if orig:
                        imports.append(ImportReference(
                            module=orig,
                            alias=alias,
                            line_number=start_line,
                        ))

        elif node.type == "import_from_statement":
            # e.g. from math import sqrt, pi as PI
            start_line = node.start_point[0] + 1
            mod_node = node.child_by_field_name("module_name")
            module_name = _get_node_text(mod_node, source_bytes) if mod_node else ""
            names: List[str] = []
            is_wildcard = False
            for child in node.children:
                if child.type == "wildcard_import":
                    is_wildcard = True
                elif node.field_name_for_child(node.children.index(child)) == "name":
                    if child.type == "dotted_name":
                        names.append(_get_node_text(child, source_bytes))
                    elif child.type == "aliased_import":
                        sub_name = None
                        for sub in child.children:
                            if sub.type == "identifier" and sub_name is None:
                                sub_name = _get_node_text(sub, source_bytes)
                        if sub_name:
                            names.append(sub_name)

            imports.append(ImportReference(
                module=module_name,
                names=names,
                is_wildcard=is_wildcard,
                line_number=start_line,
            ))


        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            body_node = node.child_by_field_name("body")
            docstring = _extract_docstring(body_node, source_bytes)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            superclasses_node = node.child_by_field_name("superclasses")
            sig = None
            if superclasses_node:
                sig = f"class {class_name}{_get_node_text(superclasses_node, source_bytes)}"
            else:
                sig = f"class {class_name}"

            symbols.append(CodeSymbol(
                name=class_name,
                kind=SymbolKind.CLASS,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=sig,
                docstring=docstring,
            ))

            # Traverse class body with class_name as parent
            if body_node:
                for child in body_node.children:
                    visit(child, parent_name=class_name, in_class=True)
            return

        elif node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            fn_name = _get_node_text(name_node, source_bytes) if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            ret_node = node.child_by_field_name("return_type")
            body_node = node.child_by_field_name("body")
            docstring = _extract_docstring(body_node, source_bytes)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            sig_parts = [f"def {fn_name}"]
            if params_node:
                sig_parts.append(_get_node_text(params_node, source_bytes))
            if ret_node:
                sig_parts.append(f" -> {_get_node_text(ret_node, source_bytes)}")
            sig = "".join(sig_parts)

            kind = SymbolKind.METHOD if in_class else SymbolKind.FUNCTION
            symbols.append(CodeSymbol(
                name=fn_name,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
                parent_symbol=parent_name,
                signature=sig,
                docstring=docstring,
            ))

            # Traverse function body for nested functions or inner classes
            if body_node:
                for child in body_node.children:
                    visit(child, parent_name=fn_name, in_class=False)
            return

        # Fall through to children
        for child in node.children:
            visit(child, parent_name=parent_name, in_class=in_class)

    visit(root_node)
    return symbols, imports
