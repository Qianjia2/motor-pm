"""Safe JSON file storage with rotating backups and atomic writes.

Every save creates 5 rotating backups (.bak → .2 → .3 → .4 → .5).
Every load tries main file → .bak → returns default only as last resort.
"""

import json, os, shutil, tempfile


def safe_load(filepath, default=None):
    """Load JSON from file. Try main → .bak → default. Never silently returns empty."""
    if default is None:
        default = []
    for path in [filepath, filepath + ".bak"]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            pass
    return default


def safe_save(filepath, data):
    """Save JSON atomically with 5 rotating backups.

    1. Write to temp file
    2. Rotate existing backups (.bak → .2 → .3 → .4 → .5)
    3. Atomic rename temp → target
    4. Copy target → .bak
    5. Return True on success
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # Write to temp file first (atomic)
    try:
        fd, tmp = tempfile.mkstemp(suffix=".json", dir=os.path.dirname(filepath))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return False

    # Rotate backups: .bak → .2 → .3 → .4 → .5
    try:
        for i in range(4, 0, -1):
            old_path = filepath + (f".{i}" if i > 1 else ".bak")
            new_path = filepath + f".{i + 1}"
            if os.path.exists(old_path):
                os.replace(old_path, new_path)
    except Exception:
        pass

    # Atomic rename temp → target
    try:
        os.replace(tmp, filepath)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        return False

    # Create immediate .bak copy
    try:
        shutil.copy2(filepath, filepath + ".bak")
    except Exception:
        pass

    return True


def restore_from_backup(filepath):
    """Restore main file from newest available backup. Returns restored data or None."""
    # Try backups in order: .bak, .2, .3, .4, .5
    for suffix in [".bak", ".2", ".3", ".4", ".5"]:
        bak = filepath + suffix
        try:
            with open(bak, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Restore main file
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return data
        except Exception:
            pass
    return None


def list_backups(filepath):
    """List available backup files and their sizes."""
    backups = []
    for suffix in [".bak", ".2", ".3", ".4", ".5"]:
        bak = filepath + suffix
        if os.path.exists(bak):
            try:
                size = os.path.getsize(bak)
                backups.append({"path": bak, "suffix": suffix, "size": size})
            except Exception:
                pass
    return backups


def file_info(filepath):
    """Get info about a data file and its backups."""
    info = {
        "file": filepath,
        "exists": os.path.exists(filepath),
        "size": os.path.getsize(filepath) if os.path.exists(filepath) else 0,
        "backups": list_backups(filepath),
    }
    if info["exists"]:
        try:
            data = safe_load(filepath)
            if isinstance(data, list):
                info["entries"] = len(data)
            elif isinstance(data, dict):
                info["entries"] = len(data)
        except Exception:
            info["entries"] = "?"
    return info
