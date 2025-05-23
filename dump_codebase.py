import os

# Folders and files to ignore
IGNORE_DIRS = {
    '.git', '.github', '__pycache__', 'venv', 'env', '.venv', '.mypy_cache',
    '.pytest_cache', '.idea', '.vscode', 'node_modules', 'dist', 'build',
    '.eggs', '.tox', '.coverage', '.cache', '.svn', '.hg', '.DS_Store',
    'state.sqlite-shm', 'state.sqlite-wal', 'startup_log.txt'
}
IGNORE_FILE_EXTS = {
    '.pyc', '.pyo', '.sqlite', '.log', '.db', '.exe', '.dll', '.so', '.zip',
    '.tar', '.gz', '.rar', '.7z', '.egg-info', '.swp', '.bak'
}
IGNORE_FILES = {
    'state.sqlite', 'startup_log.txt'
}

def should_ignore(path, is_dir):
    name = os.path.basename(path)
    if is_dir and name in IGNORE_DIRS:
        return True
    if not is_dir:
        if name in IGNORE_FILES:
            return True
        ext = os.path.splitext(name)[1]
        if ext in IGNORE_FILE_EXTS:
            return True
    return False

def walk_codebase(root='.'):
    for dirpath, dirnames, filenames in os.walk(root):
        # Modify dirnames in-place to skip ignored dirs
        dirnames[:] = [d for d in dirnames if not should_ignore(os.path.join(dirpath, d), True)]
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if should_ignore(filepath, False):
                continue
            yield filepath

def main():
    root = os.path.abspath('.')
    output_file = os.path.join(root, 'codebase_dump.txt')
    with open(output_file, 'w', encoding='utf-8', errors='replace') as out:
        for filepath in walk_codebase(root):
            relpath = os.path.relpath(filepath, root)
            out.write(f"\n--- FILE: {relpath} ---\n\n")
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"[Could not read file: {e}]\n")

if __name__ == '__main__':
    main()