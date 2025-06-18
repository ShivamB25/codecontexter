#!/usr/bin/env python3

import os
import argparse
import pathlib
import pathspec  # Needs: pip install pathspec
import sys
from typing import Iterator, Dict, Set, Optional, Tuple, List

# For a better user experience on large projects
try:
    import tqdm  # Needs: pip install tqdm
except ImportError:
    # A dummy tqdm class if the library is not installed
    class tqdm:
        def __init__(self, iterable, **kwargs):
            self.iterable = iterable
        def __iter__(self):
            return iter(self.iterable)
        def update(self, n=1):
            pass
        def close(self):
            pass

# --- Unified Configuration ---

# This single dictionary drives the logic.
# Key: file extension or full filename.
# Value: Markdown language hint (e.g., 'python', 'javascript').
# Use `None` for extensions/files to be included as plain text.
# Files/extensions not in this map are ignored (unless they have no extension).
LANGUAGE_MAP: Dict[str, Optional[str]] = {
    # Python
    '.py': 'python', '.ipynb': 'json', 'pyproject.toml': 'toml',
    'requirements.txt': 'text', 'pipfile': 'toml', 'pipfile.lock': 'json',
    # Web
    '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.jsx': 'jsx', '.ts': 'typescript', '.tsx': 'tsx',
    '.html': 'html', '.htm': 'html', '.css': 'css', '.scss': 'scss', '.sass': 'sass',
    # Java & C-family
    '.java': 'java', '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.hpp': 'cpp',
    '.cs': 'csharp',
    # Other Languages
    '.go': 'go', '.rs': 'rust', '.rb': 'ruby', '.php': 'php', '.swift': 'swift',
    '.kt': 'kotlin', '.kts': 'kotlin', '.dart': 'dart', '.lua': 'lua',
    '.pl': 'perl', '.pm': 'perl',
    # Shell & Scripts
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash', '.ps1': 'powershell',
    '.bat': 'batch', '.cmd': 'batch',
    # Config & Data
    '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.xml': 'xml', '.toml': 'toml',
    '.ini': 'ini', '.cfg': 'ini', '.conf': 'ini',
    # Docs & Text
    '.md': 'markdown', '.txt': 'text', '.rst': 'rst',
    # DevOps & Build
    '.sql': 'sql', '.dockerfile': 'dockerfile', 'dockerfile': 'dockerfile',
    '.env.example': 'text',
    '.gitignore': None, '.gitattributes': None, '.editorconfig': None,
    'makefile': 'makefile', 'Makefile': 'makefile',
}

# --- Files/Directories ALWAYS Ignored (uses .gitignore syntax) ---
# These patterns are combined with the project's .gitignore for a unified ruleset.
# Use forward slashes for paths, as is standard in .gitignore.
ALWAYS_IGNORE_PATTERNS: Set[str] = {
    # Version Control
    '.git/',

    # === Next.js / Node.js Specific ===
    'node_modules/',
    '.next/',             # Next.js build output
    '.swc/',              # SWC cache
    'out/',               # Static export output
    'public/',            # Often contains images/fonts, not code
    'next-env.d.ts',      # Next.js auto-generated TS definitions
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    '.env.local',         # Local environment variables (often with secrets)
    '.env.development.local',
    '.env.production.local',

    # Python
    '__pycache__/', '*.pyc', '*.pyo', '*.pyd',
    '.venv/', 'venv/', 'env/', 'ENV/', 'virtualenv/',
    '*.egg-info/', '.pytest_cache/', '.mypy_cache/', '.ruff_cache/',
    '.hypothesis/',

    # General Build outputs & Caches
    'build/', 'dist/', 'target/', 'site/', 'htmlcov/',
    '.coverage',

    # IDE & OS specific
    '.idea/', '.vscode/', '*.swp', '*.swo', '.DS_Store', 'Thumbs.db',

    # Logs & Databases
    '*.log', '*.sqlite3', '*.sqlite3-journal', 'celerybeat-schedule',

    # Jupyter
    '.ipynb_checkpoints/',

    # Django
    'media/', 'staticfiles/', 'static_root/',
}


# --- Core Logic ---

def find_project_root(start_dir: pathlib.Path) -> pathlib.Path:
    """Find the nearest parent directory containing .git or return start_dir."""
    current = start_dir.resolve()
    while True:
        if (current / '.git').is_dir():
            return current
        parent = current.parent
        if parent == current:  # Reached filesystem root
            print("Warning: .git directory not found. Using starting directory as project root.", file=sys.stderr)
            return start_dir.resolve()
        current = parent

def get_combined_spec(root_dir: pathlib.Path) -> pathspec.PathSpec:
    """
    Combines ALWAYS_IGNORE_PATTERNS with patterns from .gitignore files.
    """
    all_patterns = list(ALWAYS_IGNORE_PATTERNS)
    gitignore_path = root_dir / '.gitignore'
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_patterns.extend(f.readlines())
        except Exception as e:
            print(f"Warning: Could not read .gitignore at {gitignore_path}: {e}", file=sys.stderr)

    return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, all_patterns)

def get_language_from_path(file_path: pathlib.Path) -> Optional[str]:
    """Determines the language hint from the file path based on LANGUAGE_MAP."""
    # Check by full name first (e.g., 'Makefile'), then by extension.
    if file_path.name in LANGUAGE_MAP:
        return LANGUAGE_MAP[file_path.name]
    if file_path.suffix.lower() in LANGUAGE_MAP:
        return LANGUAGE_MAP[file_path.suffix.lower()]

    # Include files with no extension as plain text if they appear to be text.
    if not file_path.suffix:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(1024)  # Try to read a small chunk
            return 'text'
        except (UnicodeDecodeError, IOError):
            return None  # Likely a binary file

    return None

def create_markdown(target_dir: str, output_file: str, verbose: bool):
    """Generates the Markdown file."""
    start_path = pathlib.Path(target_dir).resolve()
    output_path = pathlib.Path(output_file).resolve()
    
    try:
        script_path = pathlib.Path(__file__).resolve()
    except NameError:
        script_path = pathlib.Path.cwd() / "this_script_placeholder.py"

    if not start_path.is_dir():
        print(f"Error: Directory not found: {target_dir}", file=sys.stderr)
        sys.exit(1)

    project_root = find_project_root(start_path)
    combined_spec = get_combined_spec(project_root)
    
    print(f"Scanning directory: {start_path}")
    print(f"Project root found: {project_root}")
    if (project_root / '.gitignore').exists():
        print(f"Using .gitignore from: {project_root / '.gitignore'}")
    
    # --- Efficiently walk the tree and collect files ---
    files_to_process: List[Tuple[pathlib.Path, str]] = []
    
    # Use os.walk for efficient directory pruning
    for root, dirs, files in os.walk(start_path, topdown=True):
        root_path = pathlib.Path(root)
        
        # Prune ignored directories from the walk
        # We need a copy of dirs to iterate over while modifying the original
        ignored_dirs = []
        for d in list(dirs):
            dir_path = root_path / d
            relative_dir_path_str = str(dir_path.relative_to(project_root)).replace(os.sep, '/')
            if combined_spec.match_file(relative_dir_path_str):
                dirs.remove(d) # Don't descend into this directory
        
        for filename in files:
            file_path = root_path / filename
            
            # 1. Ignore the output file and this script itself
            if file_path.resolve() in (output_path.resolve(), script_path.resolve()):
                continue

            # 2. Check against combined ignore spec (.gitignore + ALWAYS_IGNORE)
            relative_file_path_str = str(file_path.relative_to(project_root)).replace(os.sep, '/')
            if combined_spec.match_file(relative_file_path_str):
                continue
            
            # 3. Check if file type is in our explicit list of text/code files
            lang = get_language_from_path(file_path)
            if lang is not None:
                files_to_process.append((file_path, lang))

    print(f"Found {len(files_to_process)} files to include. Writing to {output_path}...")
    
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as md_file:
            md_file.write(f"# Code Summary: {start_path.name}\n\n")
            md_file.write(f"This summary was generated from the directory: `{start_path}`\n\n---\n\n")

            pbar = tqdm(files_to_process, desc="Writing files", unit="file")
            for item_path, lang in pbar:
                relative_path_to_start = item_path.relative_to(start_path)
                if verbose:
                    print(f"  Including: {relative_path_to_start}")
                
                try:
                    with open(item_path, 'r', encoding='utf-8', errors='ignore') as code_file:
                        content = code_file.read()

                    md_file.write(f"## File: `{relative_path_to_start}`\n\n")
                    md_file.write(f"```{lang or 'text'}\n")
                    md_file.write(content.strip() + "\n")
                    md_file.write("```\n\n")
                except IOError as e:
                    print(f"Warning: Could not read file {relative_path_to_start}: {e}", file=sys.stderr)
                except Exception as e:
                    print(f"Warning: Error processing file {relative_path_to_start}: {e}", file=sys.stderr)
        
        print(f"\nScan complete. Included {len(files_to_process)} files in the summary.")
        print(f"Markdown file created successfully: {output_path}")

    except IOError as e:
        print(f"\nError: Could not write to output file {output_path}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Create a Markdown file containing code from a directory, respecting .gitignore and predefined ignore patterns.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("directory", help="The target directory to scan for code files.")
    parser.add_argument("-o", "--output", default="code_summary.md", help="The path for the output Markdown file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show which files are being included during processing.")
    
    args = parser.parse_args()
    create_markdown(args.directory, args.output, args.verbose)

if __name__ == "__main__":
    main()