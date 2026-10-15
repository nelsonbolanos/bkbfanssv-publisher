import sys, shutil
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
if "data-team=" in src:
    sys.exit("already patched")
REPL = [
    ("white-space:nowrap\">{e(nice(w))}</div>", "white-space:nowrap\" data-team=\"{e(w)}\">{e(nice(w))}</div>"),
    ("color:#8F9BB8;white-space:nowrap\">{e(nice(l))}</div>", "color:#8F9BB8;white-space:nowrap\" data-team=\"{e(l)}\">{e(nice(l))}</div>"),
    ("<img src=\"file://{pp}\" style=\"position:relative;flex:none", "<img data-player=\"{e(mn)}|{e(mt)}\" src=\"file://{pp}\" style=\"position:relative;flex:none"),
    ("<div style=\"white-space:nowrap;overflow:hidden;text-overflow:ellipsis\">{e(nice(name))}</div>", "<div data-team=\"{e(name)}\" style=\"white-space:nowrap;overflow:hidden;text-overflow:ellipsis\">{e(nice(name))}</div>"),
]
for old, new in REPL:
    n = src.count(old)
    if n != 1: sys.exit(f"expected 1 match, found {n}: {old[:60]}")
    src = src.replace(old, new)
shutil.copy(path, path + ".bak"); open(path, "w", encoding="utf-8").write(src); print("patched", path)
