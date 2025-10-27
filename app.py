#!/usr/bin/env python3

import os
import argparse
import pathlib
import pathspec
import sys
import mimetypes
import hashlib
from typing import Iterator, Dict, Set, Optional, Tuple, List
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from collections import defaultdict

# For better user experience
try:
    import tqdm
except ImportError:
    class tqdm:
        def __init__(self, iterable=None, **kwargs):
            self.iterable = iterable or []
        def __iter__(self):
            return iter(self.iterable)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def update(self, n=1):
            pass
        def close(self):
            pass

# --- Enhanced Configuration ---

LANGUAGE_MAP: Dict[str, Optional[str]] = {
    # Python
    '.py': 'python', '.pyi': 'python', '.pyx': 'python',
    '.ipynb': 'json', 'pyproject.toml': 'toml', 'setup.py': 'python',
    'requirements.txt': 'text', 'requirements-dev.txt': 'text',
    'pipfile': 'toml', 'pipfile.lock': 'json', 'poetry.lock': 'toml',
    'setup.cfg': 'ini', 'tox.ini': 'ini', 'pytest.ini': 'ini',
    
    # JavaScript/TypeScript/Node
    '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.jsx': 'jsx', '.ts': 'typescript', '.tsx': 'tsx',
    'package.json': 'json', 'package-lock.json': 'json',
    'tsconfig.json': 'json', 'jsconfig.json': 'json',
    '.eslintrc': 'json', '.eslintrc.json': 'json', '.eslintrc.js': 'javascript',
    '.prettierrc': 'json', '.babelrc': 'json', 'babel.config.js': 'javascript',
    'webpack.config.js': 'javascript', 'vite.config.js': 'javascript',
    'vite.config.ts': 'typescript', 'next.config.js': 'javascript',
    'nuxt.config.js': 'javascript', 'vue.config.js': 'javascript',
    
    # Web
    '.html': 'html', '.htm': 'html', '.css': 'css', 
    '.scss': 'scss', '.sass': 'sass', '.less': 'less',
    '.vue': 'vue', '.svelte': 'svelte',
    
    # Java & JVM
    '.java': 'java', '.kt': 'kotlin', '.kts': 'kotlin',
    '.groovy': 'groovy', '.gradle': 'groovy', '.scala': 'scala',
    'pom.xml': 'xml', 'build.gradle': 'groovy', 'build.gradle.kts': 'kotlin',
    'settings.gradle': 'groovy', 'gradlew': 'bash',
    'application.properties': 'properties', 'application.yml': 'yaml',
    'application.yaml': 'yaml',
    
    # C-family
    '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.hpp': 'cpp', '.cc': 'cpp',
    '.cxx': 'cpp', '.hxx': 'cpp', '.cs': 'csharp',
    '.m': 'objective-c', '.mm': 'objective-c',
    'CMakeLists.txt': 'cmake', '.cmake': 'cmake',
    
    # Other Languages
    '.go': 'go', 'go.mod': 'go', 'go.sum': 'text',
    '.rs': 'rust', 'Cargo.toml': 'toml', 'Cargo.lock': 'toml',
    '.rb': 'ruby', 'Gemfile': 'ruby', 'Gemfile.lock': 'text', 'Rakefile': 'ruby',
    '.php': 'php', 'composer.json': 'json', 'composer.lock': 'json',
    '.swift': 'swift', 'Package.swift': 'swift',
    '.dart': 'dart', 'pubspec.yaml': 'yaml', 'pubspec.lock': 'yaml',
    '.lua': 'lua', '.pl': 'perl', '.pm': 'perl',
    '.r': 'r', '.R': 'r', '.jl': 'julia',
    '.ex': 'elixir', '.exs': 'elixir', '.erl': 'erlang',
    '.clj': 'clojure', '.cljs': 'clojure',
    
    # Shell & Scripts
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'zsh', '.fish': 'fish',
    '.ps1': 'powershell', '.psm1': 'powershell',
    '.bat': 'batch', '.cmd': 'batch',
    
    # Config & Data
    '.json': 'json', '.json5': 'json', '.jsonc': 'json',
    '.yaml': 'yaml', '.yml': 'yaml', 
    '.xml': 'xml', '.toml': 'toml', '.ini': 'ini', 
    '.cfg': 'ini', '.conf': 'ini', '.config': 'ini',
    '.properties': 'properties',
    
    # Docker & Containers
    'dockerfile': 'dockerfile', 'Dockerfile': 'dockerfile',
    '.dockerfile': 'dockerfile', 'Dockerfile.dev': 'dockerfile',
    'Dockerfile.prod': 'dockerfile', 'Dockerfile.test': 'dockerfile',
    'docker-compose.yml': 'yaml', 'docker-compose.yaml': 'yaml',
    'docker-compose.dev.yml': 'yaml', 'docker-compose.prod.yml': 'yaml',
    'docker-compose.override.yml': 'yaml',
    '.dockerignore': 'text', 'compose.yml': 'yaml', 'compose.yaml': 'yaml',
    
    # Kubernetes & Orchestration
    'deployment.yaml': 'yaml', 'deployment.yml': 'yaml',
    'service.yaml': 'yaml', 'service.yml': 'yaml',
    'ingress.yaml': 'yaml', 'ingress.yml': 'yaml',
    'configmap.yaml': 'yaml', 'configmap.yml': 'yaml',
    'secret.yaml': 'yaml', 'secret.yml': 'yaml',
    'kustomization.yaml': 'yaml', 'kustomization.yml': 'yaml',
    'helmfile.yaml': 'yaml', 'Chart.yaml': 'yaml',
    'values.yaml': 'yaml', 'values.yml': 'yaml',
    
    # Infrastructure as Code
    '.tf': 'hcl', '.tfvars': 'hcl', '.hcl': 'hcl',
    'terraform.tfvars': 'hcl', 'variables.tf': 'hcl',
    'outputs.tf': 'hcl', 'main.tf': 'hcl',
    'Vagrantfile': 'ruby',
    
    # CI/CD
    '.gitlab-ci.yml': 'yaml', 'gitlab-ci.yml': 'yaml',
    '.travis.yml': 'yaml', 'travis.yml': 'yaml',
    'circle.yml': 'yaml', '.circleci': 'yaml',
    'Jenkinsfile': 'groovy', 'jenkinsfile': 'groovy',
    'azure-pipelines.yml': 'yaml', 'azure-pipelines.yaml': 'yaml',
    '.drone.yml': 'yaml', 'bitbucket-pipelines.yml': 'yaml',
    'appveyor.yml': 'yaml', '.appveyor.yml': 'yaml',
    
    # GitHub Actions
    'action.yml': 'yaml', 'action.yaml': 'yaml',
    
    # Ansible
    'playbook.yml': 'yaml', 'playbook.yaml': 'yaml',
    'ansible.cfg': 'ini', 'hosts': 'ini', 'inventory': 'ini',
    
    # Database
    '.sql': 'sql', '.psql': 'sql', '.mysql': 'sql',
    '.prisma': 'prisma',
    
    # Docs & Text
    '.md': 'markdown', '.markdown': 'markdown',
    '.txt': 'text', '.rst': 'rst', '.adoc': 'asciidoc',
    'README': 'markdown', 'CHANGELOG': 'markdown',
    'LICENSE': 'text', 'CONTRIBUTING': 'markdown',
    
    # Build & Make
    'makefile': 'makefile', 'Makefile': 'makefile',
    'GNUmakefile': 'makefile', 'makefile.am': 'makefile',
    
    # Environment & Config
    '.env': 'bash', '.env.example': 'bash', '.env.local': 'bash',
    '.env.development': 'bash', '.env.production': 'bash',
    '.env.test': 'bash', '.env.sample': 'bash',
    '.envrc': 'bash', '.flaskenv': 'bash',
    
    # Git & VCS
    '.gitignore': 'text', '.gitattributes': 'text', 
    '.gitmodules': 'text', '.dockerignore': 'text',
    '.npmignore': 'text', '.eslintignore': 'text',
    
    # Editor Config
    '.editorconfig': 'ini', '.vimrc': 'vim', '.nvimrc': 'vim',
    
    # GraphQL & API
    '.graphql': 'graphql', '.gql': 'graphql',
    '.proto': 'protobuf', '.avro': 'json', '.thrift': 'thrift',
    'openapi.yaml': 'yaml', 'openapi.yml': 'yaml',
    'swagger.yaml': 'yaml', 'swagger.yml': 'yaml',
}

ALWAYS_IGNORE_PATTERNS: Set[str] = {
    # Version Control
    '.git/', '.svn/', '.hg/', '.bzr/',
    
    # Dependencies
    'node_modules/', 'bower_components/', 'jspm_packages/',
    'vendor/', 'vendors/',
    
    # Build outputs
    '.next/', '.nuxt/', '.output/', 'out/', 'dist/', 'build/',
    'target/', '_site/', '.cache/', '.parcel-cache/',
    '.swc/', '.turbo/', '.vercel/',
    
    # Python
    '__pycache__/', '*.pyc', '*.pyo', '*.pyd', '.Python',
    '.venv/', 'venv/', 'env/', 'ENV/', 'virtualenv/', '.pytest_cache/',
    '.mypy_cache/', '.ruff_cache/', '.hypothesis/', '*.egg-info/',
    '.tox/', '.coverage', 'htmlcov/', '.eggs/', '*.egg',
    
    # Java/JVM
    '*.class', '*.jar', '*.war', '*.ear', 'hs_err_pid*',
    
    # Rust
    'target/',
    
    # Go
    'bin/', 'pkg/',
    
    # Ruby
    '.bundle/',
    
    # IDEs
    '.idea/', '.vscode/', '*.swp', '*.swo', '*~',
    '.DS_Store', 'Thumbs.db', '.project', '.classpath',
    '.settings/', '*.sublime-workspace', '*.sublime-project',
    
    # Logs & Databases
    '*.log', '*.sqlite', '*.sqlite3', '*.db',
    'npm-debug.log*', 'yarn-debug.log*', 'yarn-error.log*',
    
    # OS
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    
    # Misc
    '.env.local', '.env.*.local', '*.lock',
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'composer.lock', 'Gemfile.lock', 'poetry.lock',
    'public/', 'static/', 'assets/', 'media/', 'uploads/',
}

# File categories for better organization
FILE_CATEGORIES = {
    'source': {'.py', '.js', '.ts', '.java', '.go', '.rs', '.rb', '.php', '.cpp', '.c', '.cs'},
    'config': {'.json', '.yaml', '.yml', '.toml', '.ini', '.env', '.config'},
    'docker': {'dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.dockerignore'},
    'iac': {'.tf', '.tfvars', '.hcl'},
    'ci_cd': {'.gitlab-ci.yml', 'Jenkinsfile', 'azure-pipelines.yml'},
    'build': {'makefile', 'CMakeLists.txt', 'build.gradle', 'pom.xml'},
    'docs': {'.md', '.rst', '.txt'},
}

@dataclass
class FileMetadata:
    """Metadata for a single file"""
    path: pathlib.Path
    relative_path: pathlib.Path
    language: str
    size: int
    lines: int
    modified: datetime
    category: str
    hash_md5: Optional[str] = None

# --- Performance Optimizations ---

def get_file_category(file_path: pathlib.Path) -> str:
    """Categorize file by its purpose"""
    name_lower = file_path.name.lower()
    suffix_lower = file_path.suffix.lower()
    
    for category, extensions in FILE_CATEGORIES.items():
        if name_lower in extensions or suffix_lower in extensions:
            return category
    return 'other'

def count_lines(file_path: pathlib.Path) -> int:
    """Efficiently count lines in a file"""
    try:
        with open(file_path, 'rb') as f:
            return sum(1 for _ in f)
    except:
        return 0

def get_file_hash(file_path: pathlib.Path, hash_files: bool = False) -> Optional[str]:
    """Get MD5 hash of file for verification"""
    if not hash_files:
        return None
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except:
        return None

def process_file(file_path: pathlib.Path, start_path: pathlib.Path, 
                 include_hash: bool = False) -> Optional[FileMetadata]:
    """Process a single file and extract metadata"""
    try:
        lang = get_language_from_path(file_path)
        if lang is None:
            return None
            
        stat = file_path.stat()
        return FileMetadata(
            path=file_path,
            relative_path=file_path.relative_to(start_path),
            language=lang or 'text',
            size=stat.st_size,
            lines=count_lines(file_path),
            modified=datetime.fromtimestamp(stat.st_mtime),
            category=get_file_category(file_path),
            hash_md5=get_file_hash(file_path, include_hash)
        )
    except Exception as e:
        print(f"Warning: Error processing {file_path}: {e}", file=sys.stderr)
        return None

def find_project_root(start_dir: pathlib.Path) -> pathlib.Path:
    """Find the nearest parent directory containing .git or return start_dir."""
    current = start_dir.resolve()
    while True:
        if (current / '.git').is_dir():
            return current
        parent = current.parent
        if parent == current:
            print("Warning: .git directory not found. Using starting directory as project root.", 
                  file=sys.stderr)
            return start_dir.resolve()
        current = parent

def get_combined_spec(root_dir: pathlib.Path) -> pathspec.PathSpec:
    """Combines ALWAYS_IGNORE_PATTERNS with patterns from .gitignore files."""
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
    name_lower = file_path.name.lower()
    
    # Check exact name first (case-insensitive)
    if name_lower in LANGUAGE_MAP:
        return LANGUAGE_MAP[name_lower]
    
    # Check exact name (case-sensitive) for files like Makefile
    if file_path.name in LANGUAGE_MAP:
        return LANGUAGE_MAP[file_path.name]
    
    # Check by extension
    if file_path.suffix.lower() in LANGUAGE_MAP:
        return LANGUAGE_MAP[file_path.suffix.lower()]
    
    # Special handling for files in .github/workflows
    if '.github' in file_path.parts and 'workflows' in file_path.parts:
        if file_path.suffix in {'.yml', '.yaml'}:
            return 'yaml'
    
    # Include files with no extension as plain text if they appear to be text
    if not file_path.suffix:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(512)
            return 'text'
        except (UnicodeDecodeError, IOError):
            return None
    
    return None

def collect_files(start_path: pathlib.Path, project_root: pathlib.Path, 
                  combined_spec: pathspec.PathSpec, output_path: pathlib.Path,
                  script_path: pathlib.Path) -> List[pathlib.Path]:
    """Efficiently collect all files to process"""
    files_to_process = []
    
    for root, dirs, files in os.walk(start_path, topdown=True):
        root_path = pathlib.Path(root)
        
        # Prune ignored directories
        for d in list(dirs):
            dir_path = root_path / d
            try:
                relative_dir = dir_path.relative_to(project_root)
                relative_dir_str = str(relative_dir).replace(os.sep, '/')
                if combined_spec.match_file(relative_dir_str):
                    dirs.remove(d)
            except ValueError:
                pass
        
        for filename in files:
            file_path = root_path / filename
            
            # Skip output and script
            try:
                if file_path.resolve() in (output_path.resolve(), script_path.resolve()):
                    continue
            except:
                pass
            
            # Check against ignore patterns
            try:
                relative_file = file_path.relative_to(project_root)
                relative_file_str = str(relative_file).replace(os.sep, '/')
                if combined_spec.match_file(relative_file_str):
                    continue
            except ValueError:
                pass
            
            # Check if file type is supported
            if get_language_from_path(file_path) is not None:
                files_to_process.append(file_path)
    
    return files_to_process

def generate_metadata_table(files_metadata: List[FileMetadata]) -> str:
    """Generate a markdown table with file metadata"""
    table = "| File | Size | Lines | Type | Category | Last Modified |\n"
    table += "|------|------|-------|------|----------|---------------|\n"
    
    for meta in sorted(files_metadata, key=lambda x: str(x.relative_path)):
        size_str = format_size(meta.size)
        modified_str = meta.modified.strftime("%Y-%m-%d %H:%M")
        table += f"| `{meta.relative_path}` | {size_str} | {meta.lines} | {meta.language} | {meta.category} | {modified_str} |\n"
    
    return table

def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def generate_statistics(files_metadata: List[FileMetadata]) -> str:
    """Generate statistics summary"""
    total_files = len(files_metadata)
    total_lines = sum(m.lines for m in files_metadata)
    total_size = sum(m.size for m in files_metadata)
    
    # Group by category
    by_category = defaultdict(list)
    for meta in files_metadata:
        by_category[meta.category].append(meta)
    
    # Group by language
    by_language = defaultdict(list)
    for meta in files_metadata:
        by_language[meta.language].append(meta)
    
    stats = f"## 📊 Statistics\n\n"
    stats += f"- **Total Files:** {total_files}\n"
    stats += f"- **Total Lines of Code:** {total_lines:,}\n"
    stats += f"- **Total Size:** {format_size(total_size)}\n\n"
    
    stats += "### By Category\n\n"
    for category, metas in sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True):
        count = len(metas)
        lines = sum(m.lines for m in metas)
        stats += f"- **{category}:** {count} files, {lines:,} lines\n"
    
    stats += "\n### By Language\n\n"
    for language, metas in sorted(by_language.items(), key=lambda x: len(x[1]), reverse=True):
        count = len(metas)
        lines = sum(m.lines for m in metas)
        stats += f"- **{language}:** {count} files, {lines:,} lines\n"
    
    return stats

def create_markdown(target_dir: str, output_file: str, verbose: bool, 
                    include_metadata_table: bool, include_hash: bool,
                    max_workers: int):
    """Generates the enhanced Markdown file."""
    start_path = pathlib.Path(target_dir).resolve()
    output_path = pathlib.Path(output_file).resolve()
    
    try:
        script_path = pathlib.Path(__file__).resolve()
    except NameError:
        script_path = pathlib.Path.cwd() / "code_summarizer.py"
    
    if not start_path.is_dir():
        print(f"Error: Directory not found: {target_dir}", file=sys.stderr)
        sys.exit(1)
    
    project_root = find_project_root(start_path)
    combined_spec = get_combined_spec(project_root)
    
    print(f"📂 Scanning directory: {start_path}")
    print(f"🔍 Project root: {project_root}")
    if (project_root / '.gitignore').exists():
        print(f"✓ Using .gitignore from: {project_root / '.gitignore'}")
    
    # Collect files
    print("📑 Collecting files...")
    file_paths = collect_files(start_path, project_root, combined_spec, output_path, script_path)
    print(f"✓ Found {len(file_paths)} files to process")
    
    # Process files with metadata
    print("🔄 Processing files and extracting metadata...")
    files_metadata: List[FileMetadata] = []
    
    with tqdm(total=len(file_paths), desc="Processing", unit="file") as pbar:
        for file_path in file_paths:
            meta = process_file(file_path, start_path, include_hash)
            if meta:
                files_metadata.append(meta)
                if verbose:
                    print(f"  ✓ {meta.relative_path} ({meta.lines} lines, {format_size(meta.size)})")
            pbar.update(1)
    
    # Write markdown
    print(f"📝 Writing to {output_path}...")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as md_file:
            # Header
            md_file.write(f"# 📦 Code Summary: {start_path.name}\n\n")
            md_file.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            md_file.write(f"**Source Directory:** `{start_path}`\n\n")
            md_file.write("---\n\n")
            
            # Statistics
            md_file.write(generate_statistics(files_metadata))
            md_file.write("\n---\n\n")
            
            # Metadata table
            if include_metadata_table:
                md_file.write("## 📋 File Metadata\n\n")
                md_file.write(generate_metadata_table(files_metadata))
                md_file.write("\n---\n\n")
            
            # Table of Contents
            md_file.write("## 📑 Table of Contents\n\n")
            for meta in sorted(files_metadata, key=lambda x: str(x.relative_path)):
                anchor = str(meta.relative_path).replace('/', '').replace('.', '').replace(' ', '-')
                md_file.write(f"- [`{meta.relative_path}`](#{anchor})\n")
            md_file.write("\n---\n\n")
            
            # File contents
            md_file.write("## 📄 File Contents\n\n")
            with tqdm(total=len(files_metadata), desc="Writing", unit="file") as pbar:
                for meta in sorted(files_metadata, key=lambda x: str(x.relative_path)):
                    try:
                        with open(meta.path, 'r', encoding='utf-8', errors='ignore') as code_file:
                            content = code_file.read()
                        
                        md_file.write(f"### File: `{meta.relative_path}`\n\n")
                        md_file.write(f"**Language:** {meta.language} | ")
                        md_file.write(f"**Size:** {format_size(meta.size)} | ")
                        md_file.write(f"**Lines:** {meta.lines} | ")
                        md_file.write(f"**Category:** {meta.category}\n\n")
                        
                        if meta.hash_md5:
                            md_file.write(f"**MD5:** `{meta.hash_md5}`\n\n")
                        
                        md_file.write(f"```")
                        md_file.write(content.strip() + "\n")
                        md_file.write("```\n\n")
                        md_file.write("---\n\n")
                    except Exception as e:
                        print(f"⚠ Warning: Could not read {meta.relative_path}: {e}", file=sys.stderr)
                    
                    pbar.update(1)
        
        print(f"\n✅ Success! Processed {len(files_metadata)} files")
        print(f"📊 Total lines: {sum(m.lines for m in files_metadata):,}")
        print(f"💾 Total size: {format_size(sum(m.size for m in files_metadata))}")
        print(f"📄 Output: {output_path}")
    
    except IOError as e:
        print(f"\n❌ Error: Could not write to {output_path}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Create an enhanced Markdown summary of code files with rich metadata and Docker support.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("directory", help="The target directory to scan for code files.")
    parser.add_argument("-o", "--output", default="code_summary.md", 
                       help="The path for the output Markdown file.")
    parser.add_argument("-v", "--verbose", action="store_true", 
                       help="Show detailed processing information.")
    parser.add_argument("--no-metadata-table", action="store_true",
                       help="Skip generating the metadata table.")
    parser.add_argument("--include-hash", action="store_true",
                       help="Include MD5 hash for each file (slower).")
    parser.add_argument("-j", "--jobs", type=int, default=4,
                       help="Number of parallel workers (currently not used, reserved for future).")
    
    args = parser.parse_args()
    
    create_markdown(
        args.directory, 
        args.output, 
        args.verbose,
        not args.no_metadata_table,
        args.include_hash,
        args.jobs
    )

if __name__ == "__main__":
    main()
