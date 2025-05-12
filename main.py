#!/usr/bin/env python3
"""
Directory to Markdown Converter

Creates a markdown documentation of a directory structure and file contents,
with support for including and excluding specific files or directories,
and controlling recursive directory processing.
"""

import argparse
import pathlib
import re
import fnmatch
import os
import typing


def should_process_path(path: pathlib.Path,
                        include_patterns: typing.List[str], include_regexes: typing.List[typing.Pattern],
                        exclude_patterns: typing.List[str], exclude_regexes: typing.List[typing.Pattern],
                        is_checking_dir: bool = False) -> bool:
    """
    Determine if a path should be processed based on include/exclude patterns.

    Args:
        path: The path to check
        include_patterns: Wildcard patterns for inclusion
        include_regexes: Regex patterns for inclusion
        exclude_patterns: Wildcard patterns for exclusion
        exclude_regexes: Regex patterns for exclusion
        is_checking_dir: Whether we're checking a directory (affects inclusion logic)

    Returns:
        Boolean indicating whether the path should be processed
    """
    path_str = str(path)

    # First check exclusions - these take precedence
    if any(fnmatch.fnmatch(path_str, p) for p in exclude_patterns) or \
            any(r.search(path_str) for r in exclude_regexes):
        return False

    # If we're checking a directory and no inclusion patterns, include it
    # This allows us to scan directories that might contain included files
    if is_checking_dir:
        # For directories, we include them if:
        # 1. No inclusion patterns are specified (include everything)
        # 2. OR if the directory itself matches an inclusion pattern
        # 3. OR if we need to check its contents for potential matches
        has_inclusion_patterns = include_patterns or include_regexes
        matches_inclusion = (
                any(fnmatch.fnmatch(path_str, p) for p in include_patterns) or
                any(r.search(path_str) for r in include_regexes)
        )

        return not has_inclusion_patterns or matches_inclusion or True  # Always include dirs for scanning

    # For files, if include patterns are specified, file must match at least one
    if include_patterns or include_regexes:
        return any(fnmatch.fnmatch(path_str, p) for p in include_patterns) or \
            any(r.search(path_str) for r in include_regexes)

    # If no inclusion patterns, include everything not excluded
    return True


def generate_tree(root_dir: pathlib.Path,
                  include_patterns: typing.List[str], include_regexes: typing.List[typing.Pattern],
                  exclude_patterns: typing.List[str], exclude_regexes: typing.List[typing.Pattern],
                  recursive: bool = True) -> str:
    """Generate a tree-like representation of the directory structure."""
    result = [root_dir.name]

    def _generate_tree(directory: pathlib.Path, prefix: str = "", depth: int = 0):
        # Get all items in the directory
        items = sorted(list(directory.iterdir()), key=lambda p: (not p.is_dir(), p.name))

        # Filter items
        visible_items = []
        for item in items:
            is_dir = item.is_dir()
            # Skip subdirectories if not recursive and we're already in the root
            if not recursive and is_dir and depth > 0:
                continue

            if should_process_path(item, include_patterns, include_regexes,
                                   exclude_patterns, exclude_regexes, is_checking_dir=is_dir):
                visible_items.append(item)

        # Process each visible item
        for i, item in enumerate(visible_items):
            is_last = i == len(visible_items) - 1
            is_dir = item.is_dir()

            # Choose the right symbols
            connector = "└── " if is_last else "├── "
            next_prefix = "    " if is_last else "│   "

            # Add this item to the result
            result.append(f"{prefix}{connector}{item.name}")

            # If it's a directory, recursively process it if recursive mode is on
            if is_dir and (recursive or depth == 0):
                _generate_tree(item, prefix + next_prefix, depth + 1)

    _generate_tree(root_dir)
    return "\n".join(result)


def is_binary_file(file_path: pathlib.Path) -> bool:
    """Check if a file is binary."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1024)  # Read a chunk of the file
        return False
    except UnicodeDecodeError:
        return True


def collect_files(directory: pathlib.Path,
                  include_patterns: typing.List[str], include_regexes: typing.List[typing.Pattern],
                  exclude_patterns: typing.List[str], exclude_regexes: typing.List[typing.Pattern],
                  recursive: bool = True) -> typing.List[typing.Tuple[pathlib.Path, pathlib.Path]]:
    """
    Collect all files to be processed, respecting include/exclude patterns.
    Returns list of tuples (file_path, relative_path).
    """
    result = []

    if recursive:
        # Use os.walk for recursive processing
        for root, dirs, files in os.walk(directory):
            root_path = pathlib.Path(root)

            # Filter out excluded directories
            dirs[:] = [d for d in dirs if should_process_path(
                root_path / d,
                include_patterns, include_regexes,
                exclude_patterns, exclude_regexes,
                is_checking_dir=True
            )]

            # Process files
            for file in files:
                file_path = root_path / file
                if should_process_path(
                        file_path,
                        include_patterns, include_regexes,
                        exclude_patterns, exclude_regexes
                ):
                    relative_path = file_path.relative_to(directory)
                    result.append((file_path, relative_path))
    else:
        # Non-recursive - only process files directly in the input directory
        for item in directory.iterdir():
            if item.is_file() and should_process_path(
                    item,
                    include_patterns, include_regexes,
                    exclude_patterns, exclude_regexes
            ):
                relative_path = item.relative_to(directory)
                result.append((item, relative_path))

    return sorted(result, key=lambda x: str(x[1]))


def create_markdown(input_dir: pathlib.Path, output_dir: pathlib.Path,
                    include_patterns: typing.List[str], include_regexes: typing.List[typing.Pattern],
                    exclude_patterns: typing.List[str], exclude_regexes: typing.List[typing.Pattern],
                    recursive: bool = True) -> None:
    """Create a markdown file based on directory content."""
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Output file path
    output_file = output_dir / f"{input_dir.name}_content.md"

    with output_file.open('w', encoding='utf-8') as f:
        # Write directory structure
        f.write("# Directory Structure\n\n")
        f.write("```\n")
        f.write(generate_tree(input_dir, include_patterns, include_regexes,
                              exclude_patterns, exclude_regexes, recursive))
        f.write("\n```\n\n")

        # Write file contents
        f.write("# File Contents\n\n")

        # Collect all files to process
        files_to_process = collect_files(
            input_dir,
            include_patterns, include_regexes,
            exclude_patterns, exclude_regexes,
            recursive
        )

        # Write file contents
        for file_path, rel_path in files_to_process:
            file_ext = file_path.suffix.lstrip('.')

            f.write(f"`{rel_path}`\n")
            f.write(f"```{file_ext}\n")

            if is_binary_file(file_path):
                f.write("/* Binary file not shown */")
            else:
                try:
                    with file_path.open('r', encoding='utf-8') as file_content:
                        f.write(file_content.read())
                except Exception as e:
                    f.write(f"/* Error reading file: {str(e)} */")

            f.write("\n```\n\n")

    print(f"Markdown file created: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown documentation from directory structure and file contents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dir2md.py ~/projects/myapp ./docs
  python dir2md.py ~/projects/myapp ./docs --exclude "*.pyc" --exclude "*__pycache__*"
  python dir2md.py ~/projects/myapp ./docs --include "*.py" --include "*.md"
  python dir2md.py ~/projects/myapp ./docs --include "*.py" --exclude ".git/*"
  python dir2md.py ~/projects/myapp ./docs --no-recursive
"""
    )

    parser.add_argument('input_dir', type=str, help="Input directory to process")
    parser.add_argument('output_dir', type=str, help="Output directory for markdown file")

    # Include options
    parser.add_argument('--include', '-i', action='append', default=[],
                        help="Only include files/directories matching this wildcard pattern (can be used multiple times)")
    parser.add_argument('--include-regex', '-I', action='append', default=[],
                        help="Only include files/directories matching this regex pattern (can be used multiple times)")

    # Exclude options
    parser.add_argument('--exclude', '-e', action='append', default=[],
                        help="Exclude files/directories matching this wildcard pattern (can be used multiple times)")
    parser.add_argument('--exclude-regex', '-E', action='append', default=[],
                        help="Exclude files/directories matching this regex pattern (can be used multiple times)")

    # Recursion control
    parser.add_argument('--no-recursive', '-nr', action='store_true',
                        help="Do not process subdirectories recursively")

    args = parser.parse_args()

    input_dir = pathlib.Path(args.input_dir).resolve()
    output_dir = pathlib.Path(args.output_dir).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Error: Input directory '{input_dir}' does not exist or is not a directory")
        return

    # Compile regex patterns
    include_regexes = [re.compile(pattern) for pattern in args.include_regex]
    exclude_regexes = [re.compile(pattern) for pattern in args.exclude_regex]

    create_markdown(input_dir, output_dir,
                    args.include, include_regexes,
                    args.exclude, exclude_regexes,
                    not args.no_recursive)  # Invert the flag since we want recursive by default


if __name__ == "__main__":
    main()
