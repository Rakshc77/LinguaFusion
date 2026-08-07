import pefile
from pathlib import Path

# Folders where we know DLLs live (venv copies, not the frozen dist --
# checking the source venv is equivalent and easier to iterate on).
SEARCH_DIRS = [
    Path(r".venv\Lib\site-packages\nvidia\cublas\bin"),
    Path(r".venv\Lib\site-packages\nvidia\cuda_runtime\bin"),
    Path(r".venv\Lib\site-packages\nvidia\nvjitlink\bin"),
    Path(r".venv\Lib\site-packages\nvidia\cudnn\bin"),
    Path(r".venv\Lib\site-packages\ctranslate2"),
    Path(r"C:\Windows\System32"),
]

def find_dll(name):
    for d in SEARCH_DIRS:
        p = d / name
        if p.exists():
            return p
    return None

def walk(dll_path, seen=None, depth=0):
    if seen is None:
        seen = set()
    name = dll_path.name.lower()
    if name in seen:
        return
    seen.add(name)

    try:
        pe = pefile.PE(str(dll_path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    except Exception as e:
        print(f"{'  '*depth}[!] could not parse {dll_path.name}: {e}")
        return

    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return

    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dep_name = entry.dll.decode(errors="ignore")
        found = find_dll(dep_name)
        marker = "OK" if found else "MISSING"
        print(f"{'  '*depth}{dep_name}: {marker}" + (f" ({found})" if found else ""))
        if found and marker == "OK":
            walk(found, seen, depth + 1)

start = find_dll("cublas64_12.dll")
if not start:
    print("cublas64_12.dll not found in any search dir!")
else:
    print(f"Walking dependencies of: {start}\n")
    walk(start)