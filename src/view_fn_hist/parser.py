"""Source code parsing for function and entity detection."""

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FunctionInfo:
    """Information about a function/method in source code."""

    name: str
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed
    signature: str | None = None
    class_name: str | None = None  # For methods
    entity_type: str = "function"  # For compatibility with EntityInfo


# Map file extensions to language names
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".rb": "ruby",
}


def detect_language(file_path: str) -> str | None:
    """Detect programming language from file extension."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def find_entity_auto(
    source: str, entity_name: str, language: str
) -> FunctionInfo | None:
    """
    Find an entity by name, automatically detecting its type.

    Searches across all entity types for the given language.

    Args:
        source: The source code to search
        entity_name: Name of the entity to find
        language: Programming language

    Returns:
        FunctionInfo with line numbers, or None if not found.
    """
    # For Python, try class first then function
    if language == "python":
        result = _find_python_class(source, entity_name)
        if result:
            return result
        return _find_python_function(source, entity_name)

    # For other languages, use tree-sitter auto-detection
    try:
        from .ts_parser import find_entity_auto as ts_find_entity_auto

        result = ts_find_entity_auto(source, entity_name, language)
        if result:
            return FunctionInfo(
                name=result.name,
                start_line=result.start_line,
                end_line=result.end_line,
                signature=result.signature,
                entity_type=result.entity_type,
            )
    except ImportError:
        pass

    return None


def find_entity(
    source: str, entity_name: str, entity_type: str, language: str
) -> FunctionInfo | None:
    """
    Find any entity (function, class, struct, enum, impl) by name in source code.

    Args:
        source: The source code to search
        entity_name: Name of the entity to find
        entity_type: Type of entity ("function", "class", "struct", "enum", "impl", or "auto")
        language: Programming language

    Returns:
        FunctionInfo with line numbers, or None if not found.
    """
    # Auto-detect entity type
    if entity_type == "auto":
        return find_entity_auto(source, entity_name, language)

    # For Python classes, use AST
    if language == "python" and entity_type == "class":
        return _find_python_class(source, entity_name)

    # For Python functions, use AST
    if language == "python" and entity_type == "function":
        return _find_python_function(source, entity_name)

    # For all other cases, use tree-sitter
    try:
        from .ts_parser import find_entity as ts_find_entity

        result = ts_find_entity(source, entity_name, entity_type, language)
        if result:
            # Convert EntityInfo to FunctionInfo for backward compatibility
            return FunctionInfo(
                name=result.name,
                start_line=result.start_line,
                end_line=result.end_line,
                signature=result.signature,
                entity_type=result.entity_type,
            )
    except ImportError:
        pass

    return None


def find_function(source: str, func_name: str, language: str) -> FunctionInfo | None:
    """
    Find a function by name in source code.

    Returns FunctionInfo with line numbers, or None if not found.
    """
    return find_entity(source, func_name, "function", language)


def find_all_functions(source: str, language: str) -> list[FunctionInfo]:
    """Find all functions in source code."""
    if language == "python":
        return _find_all_python_functions(source)
    else:
        return _find_all_functions_regex(source, language)


def _find_python_function(source: str, func_name: str) -> FunctionInfo | None:
    """Find a Python function using the ast module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return FunctionInfo(
                name=node.name,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=_get_python_signature(node),
                class_name=_get_class_name(tree, node),
            )
        elif isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            return FunctionInfo(
                name=node.name,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=_get_python_signature(node, is_async=True),
                class_name=_get_class_name(tree, node),
            )

    return None


def _find_python_class(source: str, class_name: str) -> FunctionInfo | None:
    """Find a Python class using the ast module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            # Build signature with base classes
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.unparse(base))

            signature = f"class {node.name}"
            if bases:
                signature += f"({', '.join(bases)})"
            signature += ":"

            return FunctionInfo(
                name=node.name,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=signature,
                entity_type="class",
            )

    return None


def _find_all_python_functions(source: str) -> list[FunctionInfo]:
    """Find all Python functions using the ast module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            functions.append(
                FunctionInfo(
                    name=node.name,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    signature=_get_python_signature(node, is_async=is_async),
                    class_name=_get_class_name(tree, node),
                )
            )

    return functions


def _get_python_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool = False
) -> str:
    """Get function signature from AST node."""
    args = []
    for arg in node.args.args:
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {ast.unparse(arg.annotation)}"
        args.append(arg_str)

    # Add *args and **kwargs
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")

    prefix = "async def" if is_async else "def"
    return f"{prefix} {node.name}({', '.join(args)})"


def _get_class_name(
    tree: ast.Module, func_node: ast.FunctionDef | ast.AsyncFunctionDef
) -> str | None:
    """Get the class name if the function is a method."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if item is func_node:
                    return node.name
    return None


def _find_function_regex(
    source: str, func_name: str, language: str
) -> FunctionInfo | None:
    """Regex-based fallback for non-Python languages."""
    import re

    lines = source.split("\n")

    # Language-specific function patterns
    patterns = {
        "javascript": rf"(?:function\s+{func_name}\s*\(|(?:const|let|var)\s+{func_name}\s*=\s*(?:async\s*)?\(|{func_name}\s*\([^)]*\)\s*\{{)",
        "typescript": rf"(?:function\s+{func_name}\s*\(|(?:const|let|var)\s+{func_name}\s*=\s*(?:async\s*)?\(|{func_name}\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{{)",
        "go": rf"func\s+(?:\([^)]+\)\s+)?{func_name}\s*\(",
        "rust": rf"fn\s+{func_name}\s*[<(]",
        "java": rf"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+{func_name}\s*\(",
        "c": rf"^\s*\w+\s+{func_name}\s*\(",
        "cpp": rf"^\s*(?:\w+\s+)+{func_name}\s*\(",
        "ruby": rf"def\s+{func_name}\s*(?:\(|$)",
    }

    pattern = patterns.get(language)
    if not pattern:
        return None

    regex = re.compile(pattern, re.MULTILINE)

    for i, line in enumerate(lines):
        if regex.search(line):
            # Found the function start, now find the end
            # This is a simplified approach - just find matching braces/end
            end_line = _find_function_end(lines, i, language)
            return FunctionInfo(
                name=func_name,
                start_line=i + 1,
                end_line=end_line + 1,
                signature=line.strip(),
            )

    return None


def _find_all_functions_regex(source: str, language: str) -> list[FunctionInfo]:
    """Regex-based fallback for finding all functions in non-Python languages."""
    import re

    lines = source.split("\n")
    functions = []

    # Generic function patterns by language
    patterns = {
        "javascript": r"(?:function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()",
        "typescript": r"(?:function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()",
        "go": r"func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
        "rust": r"fn\s+(\w+)\s*[<(]",
        "java": r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(",
        "c": r"^\s*\w+\s+(\w+)\s*\(",
        "cpp": r"^\s*(?:\w+\s+)+(\w+)\s*\(",
        "ruby": r"def\s+(\w+)",
    }

    pattern = patterns.get(language)
    if not pattern:
        return functions

    regex = re.compile(pattern)

    for i, line in enumerate(lines):
        match = regex.search(line)
        if match:
            # Get the function name from the first non-None group
            name = next((g for g in match.groups() if g), None)
            if name:
                end_line = _find_function_end(lines, i, language)
                functions.append(
                    FunctionInfo(
                        name=name,
                        start_line=i + 1,
                        end_line=end_line + 1,
                        signature=line.strip(),
                    )
                )

    return functions


def _find_function_end(lines: list[str], start: int, language: str) -> int:
    """Find the end of a function (simplified brace/indent matching)."""
    if language in ("python", "ruby"):
        # Indent-based languages
        if start >= len(lines):
            return start

        start_indent = len(lines[start]) - len(lines[start].lstrip())
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip() and not line.strip().startswith("#"):
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= start_indent:
                    return i - 1
        return len(lines) - 1
    else:
        # Brace-based languages
        brace_count = 0
        found_first_brace = False

        for i in range(start, len(lines)):
            line = lines[i]
            for char in line:
                if char == "{":
                    brace_count += 1
                    found_first_brace = True
                elif char == "}":
                    brace_count -= 1

            if found_first_brace and brace_count == 0:
                return i

        return len(lines) - 1
