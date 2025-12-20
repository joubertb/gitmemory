"""Tree-sitter based parser for multi-language entity detection."""

import warnings
from dataclasses import dataclass

# Suppress tree-sitter deprecation warnings about Language(path, name)
warnings.filterwarnings("ignore", category=FutureWarning, module="tree_sitter")

from tree_sitter_languages import get_parser


@dataclass
class EntityInfo:
    """Information about a code entity (function, class, struct, etc.)."""

    name: str
    entity_type: str  # "function", "class", "struct", "enum", "impl", "interface"
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed
    signature: str | None = None


# Map our language names to tree-sitter language names
LANGUAGE_MAP = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "ruby": "ruby",
}

# Tree-sitter queries for each language and entity type
# Format: (node_type, name_field, name_node_type)
ENTITY_PATTERNS = {
    "rust": {
        "function": ("function_item", "name", "identifier"),
        "struct": ("struct_item", "name", "type_identifier"),
        "enum": ("enum_item", "name", "type_identifier"),
        "impl": ("impl_item", "type", "type_identifier"),
    },
    "python": {
        "function": ("function_definition", "name", "identifier"),
        "class": ("class_definition", "name", "identifier"),
    },
    "typescript": {
        "function": ("function_declaration", "name", "identifier"),
        "class": ("class_declaration", "name", "identifier"),
        "interface": ("interface_declaration", "name", "identifier"),
        "enum": ("enum_declaration", "name", "identifier"),
    },
    "javascript": {
        "function": ("function_declaration", "name", "identifier"),
        "class": ("class_declaration", "name", "identifier"),
    },
    "go": {
        "function": ("function_declaration", "name", "identifier"),
        "struct": ("type_declaration", None, None),  # Special handling needed
        "interface": ("type_declaration", None, None),  # Special handling needed
    },
    "java": {
        "function": ("method_declaration", "name", "identifier"),
        "class": ("class_declaration", "name", "identifier"),
        "interface": ("interface_declaration", "name", "identifier"),
        "enum": ("enum_declaration", "name", "identifier"),
    },
}


def find_entity_auto(source: str, entity_name: str, language: str) -> EntityInfo | None:
    """
    Find an entity by name, automatically detecting its type.

    Searches across all entity types for the given language.

    Args:
        source: The source code to search
        entity_name: Name of the entity to find
        language: Programming language

    Returns:
        EntityInfo if found, None otherwise
    """
    ts_lang = LANGUAGE_MAP.get(language)
    if not ts_lang:
        return None

    patterns = ENTITY_PATTERNS.get(ts_lang, {})

    # Try each entity type in order of specificity
    # (structs/classes before functions, since a struct named X is more specific than a function named X)
    type_order = ["struct", "class", "enum", "interface", "impl", "function"]

    for entity_type in type_order:
        if entity_type in patterns:
            result = find_entity(source, entity_name, entity_type, language)
            if result:
                return result

    return None


def find_entity(
    source: str, entity_name: str, entity_type: str, language: str
) -> EntityInfo | None:
    """
    Find an entity by name and type using tree-sitter.

    Args:
        source: The source code to search
        entity_name: Name of the entity to find
        entity_type: Type of entity ("function", "struct", "class", etc.)
        language: Programming language

    Returns:
        EntityInfo if found, None otherwise
    """
    ts_lang = LANGUAGE_MAP.get(language)
    if not ts_lang:
        return None

    patterns = ENTITY_PATTERNS.get(ts_lang, {})
    pattern = patterns.get(entity_type)
    if not pattern:
        return None

    node_type, name_field, name_node_type = pattern

    try:
        parser = get_parser(ts_lang)
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        return None

    # Walk the tree to find matching entities
    def find_in_node(node):
        if node.type == node_type:
            # Try to get the name from the expected field
            name_node = None

            if name_field:
                name_node = node.child_by_field_name(name_field)

            # For impl blocks in Rust, we need special handling
            if ts_lang == "rust" and entity_type == "impl":
                # Look for the type being implemented
                name_node = node.child_by_field_name("type")
                if name_node and name_node.type == "generic_type":
                    # Handle generic types like Foo<T>
                    type_node = name_node.child_by_field_name("type")
                    if type_node:
                        name_node = type_node

            if name_node and name_node.text:
                found_name = name_node.text.decode("utf-8")
                if found_name == entity_name:
                    # Get the signature (first line or declaration)
                    lines = source.split("\n")
                    start_line = node.start_point[0]
                    signature = (
                        lines[start_line].strip() if start_line < len(lines) else None
                    )

                    return EntityInfo(
                        name=entity_name,
                        entity_type=entity_type,
                        start_line=node.start_point[0] + 1,  # 1-indexed
                        end_line=node.end_point[0] + 1,  # 1-indexed
                        signature=signature,
                    )

        # Recursively search children
        for child in node.children:
            result = find_in_node(child)
            if result:
                return result

        return None

    return find_in_node(tree.root_node)


def find_all_entities(
    source: str, language: str, entity_types: list[str] | None = None
) -> list[EntityInfo]:
    """
    Find all entities of specified types in source code.

    Args:
        source: The source code to search
        language: Programming language
        entity_types: List of entity types to find, or None for all

    Returns:
        List of EntityInfo for all found entities
    """
    ts_lang = LANGUAGE_MAP.get(language)
    if not ts_lang:
        return []

    patterns = ENTITY_PATTERNS.get(ts_lang, {})
    if entity_types:
        patterns = {k: v for k, v in patterns.items() if k in entity_types}

    if not patterns:
        return []

    try:
        parser = get_parser(ts_lang)
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        return []

    entities = []
    lines = source.split("\n")

    def find_in_node(node):
        for entity_type, (node_type, name_field, _) in patterns.items():
            if node.type == node_type:
                name_node = None

                if name_field:
                    name_node = node.child_by_field_name(name_field)

                # Special handling for Rust impl
                if ts_lang == "rust" and entity_type == "impl":
                    name_node = node.child_by_field_name("type")
                    if name_node and name_node.type == "generic_type":
                        type_node = name_node.child_by_field_name("type")
                        if type_node:
                            name_node = type_node

                if name_node and name_node.text:
                    found_name = name_node.text.decode("utf-8")
                    start_line = node.start_point[0]
                    signature = (
                        lines[start_line].strip() if start_line < len(lines) else None
                    )

                    entities.append(
                        EntityInfo(
                            name=found_name,
                            entity_type=entity_type,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=signature,
                        )
                    )

        for child in node.children:
            find_in_node(child)

    find_in_node(tree.root_node)
    return entities
