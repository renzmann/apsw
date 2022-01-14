#!/usr/bin/env python3

import sys
import os
import io
import textwrap
import glob

from typing import Union, List

# symbols to skip because we can't apply docstrings
skip = {
    "apsw.compile_options",
    "apsw.connection_hooks",
    "apsw.keywords",
    "apsw.main",
    "apsw.using_amalgamation",
}

skipseen = set()


def process_file(name: str) -> list:
    "Read one rst file and extract docstrings"
    items = []
    current : List[str] = []

    def do_current():
        nonlocal current
        if current:
            while not current[-1].strip():
                current.pop()
            item = classify(current)
            if item:
                items.append(item)
        current = []

    for line in open(name):
        if line.startswith(".. "):
            do_current()
            kind = line.split()[1]
            if kind.endswith("::"):
                current.append(line)
                continue
        if current:
            current.append(line)

    do_current()
    return items


def classify(doc: list) -> Union[dict,  None]:
    "Process docstring and ignore or update details"
    line = doc[0]
    assert line.startswith(".. ")
    kind = line.split()[1]
    assert kind.endswith("::")
    kind = kind.rstrip(":")
    if kind in {"index", "currentmodule", "code-block", "note", "seealso", "module", "data"}:
        return None

    assert kind in ("class", "method", "attribute"), f"unknown kind { kind } in { line }"
    rest = line.split("::", 1)[1].strip()
    if "(" in rest:
        name, signature = rest.split("(", 1)
        signature = "(" + signature
    else:
        name, signature = rest, ""
    name = name.strip()
    signature = signature.strip()

    if kind == "class":
        name += ".__init__"
    elif "." not in name:
        name = "apsw." + name

    doc = doc[1:]
    while doc and not doc[0].strip():
        doc = doc[1:]

    if not doc:
        return None
    if name in skip:
        skipseen.add(name)
        return None
    # These aren't real classes
    if name.split(".")[0] in {"VTCursor", "VTModule", "VTTable"}:
        return None

    doc = [f"{ line }\n" for line in textwrap.dedent("".join(doc)).strip().split("\n")]

    symbol = make_symbol(name)

    return {"name": name, "symbol": symbol, "signature": signature, "doc": doc}


def make_symbol(n: str) -> str:
    "Returns C symbol name"
    n = n[0].upper() + n[1:]
    n = n.replace(".", "_").replace("__", "_")
    return n + "_DOC"


def fixup(item: dict, eol: str) -> str:
    "Return docstring lines after making safe for C"

    def backslash(l):
        return l.replace('"', '\\"').replace("\n", "\\n")

    lines = item["doc"]
    if item["signature"]:
        # cpython can't handle the return type info
        sig = simplify_signature(item["signature"])
        func = item["name"].split(".")[1]
        if func != "__init__":
            assert sig[0] == "("
            sig = "($self, " + sig[1:]
        lines = [f'''{ func }{ sig }\n--\n\n{ item["name"] }{ item["signature"] }\n\n'''] + lines

    res = "\n".join(f'''"{ backslash(line) }"{ eol }''' for line in lines)
    res = res.strip().strip("\\").strip()
    return res

def simplify_signature(s: str) -> str:
    "Remove information CPython won't include in __text_signature__"
    # it doesn't like types, defaults
    s = s.split("->")[0].strip() # ... or return information

    assert s[0] == "(" and s[-1] == ")"

    # we want to split on commas, but a param could be:  Union[Dict[A,B],X]
    nest_start = "[("
    nest_end = "])"

    params = []
    pos = 1
    nesting = 0
    name = ""
    skip_to_next = False

    for pos in range(1, len(s)-1):
        c = s[pos]
        if c in nest_start or nesting:
            if c in nest_start:
                nesting += 1
                continue
            if c not in nest_end:
                continue
            nesting -= 1
            continue

        if c == ',':
            assert name
            params.append(name)
            name = ""
            skip_to_next = False
            continue

        if name and not (name + c).isidentifier() and not (name[0] == "*" and (name[1:] + c).isidentifier()):
            skip_to_next = True
            continue

        if skip_to_next:
            continue

        if c.isidentifier() or (not name and c in "/*"):
            name += c

    if name:
        params.append(name)

    if "/" not in params and not any(p.startswith("*") for p in params):
        params.append("/")

    return f"({ ', '.join(params) })"

items = []
for fname in sys.argv[2:]:
    items.extend(process_file(fname))

out = io.StringIO()
print("/* This file is generated by rst2docstring */\n", file=out)
method, mid, eol, end = "static const char * const ", " = ", "", ";"
method, mid, eol, end = "#define ", " ", " \\", ""
for item in sorted(items, key=lambda x: x["symbol"]):
    print(f"""{ method } { item["symbol"] }{ mid }{ fixup( item, eol) } { end }\n""", file=out)

outval = out.getvalue()
if not os.path.exists(sys.argv[1]) or open(sys.argv[1]).read() != outval:
    open(sys.argv[1], "w").write(outval)

symbols = sorted([item["symbol"] for item in items])

code = "\n".join(open(fn).read() for fn in glob.glob("src/*.c"))

if skip != skipseen:
    print("in skip, but not seen\n")
    for s in skip:
        if s not in skipseen:
            print("  ", s)
    print()

if any(s not in code for s in symbols):
    print("Unreferenced doc\n")
    for s in symbols:
        if s not in code:
            print("  ", s)
    sys.exit(2)