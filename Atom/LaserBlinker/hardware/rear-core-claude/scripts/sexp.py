"""KiCad S式の最小パーサ／ライタ。"""
import copy
import re
import uuid

KICAD = "/Applications/KiCad/KiCad.app/Contents/SharedSupport"
UUID_NS = uuid.UUID("6f0f3a52-8c1e-4c55-9d7e-1a2b3c4d5e6f")


class Q(str):
    """引用符付き文字列（中身はエスケープ済みのまま保持）。"""


def q(s):
    return Q(str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n"))


def uid(*key):
    return str(uuid.uuid5(UUID_NS, "/".join(map(str, key))))


_TOK = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')


def parse(text):
    stack = [[]]
    for t in _TOK.findall(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            node = stack.pop()
            stack[-1].append(node)
        elif t.startswith('"'):
            stack[-1].append(Q(t[1:-1]))
        else:
            stack[-1].append(t)
    return stack[0][0]


def dump(node, indent=0):
    if isinstance(node, Q):
        return '"' + node + '"'
    if not isinstance(node, list):
        return str(node)
    if not any(isinstance(x, list) for x in node):
        return "(" + " ".join(dump(x) for x in node) + ")"
    pad = "\t" * (indent + 1)
    head = [dump(x) for x in node if not isinstance(x, list)]
    out = "(" + " ".join(head)
    for x in node:
        if isinstance(x, list):
            out += "\n" + pad + dump(x, indent + 1)
    return out + "\n" + "\t" * indent + ")"


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def find1(node, key):
    r = find(node, key)
    return r[0] if r else None


_libs = {}


def load_lib(name, path=None):
    if name not in _libs:
        path = path or f"{KICAD}/symbols/{name}.kicad_sym"
        root = parse(open(path, encoding="utf-8").read())
        _libs[name] = {x[1]: x for x in find(root, "symbol")}
    return _libs[name]


def flatten_symbol(lib, name):
    """extends を解決した単体シンボル定義を返す（名前は lib 内の名前のまま）。"""
    node = load_lib(lib)[name]
    ext = find1(node, "extends")
    if not ext:
        return copy.deepcopy(node)
    parent = flatten_symbol(lib, ext[1])
    pname = parent[1]
    out = ["symbol", Q(name)]
    child_props = find(node, "property")
    for x in parent[2:]:
        if isinstance(x, list) and x[0] == "property":
            continue
        if isinstance(x, list) and x[0] == "symbol":
            continue
        out.append(copy.deepcopy(x))
    out += copy.deepcopy(child_props)
    for x in find(parent, "symbol"):
        sub = copy.deepcopy(x)
        if sub[1].startswith(pname + "_"):
            sub[1] = Q(name + sub[1][len(pname):])
        out.append(sub)
    return out


def symbol_pins(sym):
    """[(number, name, type, x, y, angle, hidden)]（ボディスタイル1のみ）。"""
    pins = []
    for sub in find(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", sub[1])
        if m and m.group(2) not in ("0", "1"):
            continue
        for p in find(sub, "pin"):
            at = find1(p, "at")
            num = find1(p, "number")[1]
            nm = find1(p, "name")[1]
            hidden = "hide" in p or any(
                isinstance(y, list) and y[0] == "hide" and (len(y) == 1 or y[1] == "yes") for y in p)
            pins.append((str(num), str(nm), p[1], float(at[1]), float(at[2]),
                         int(float(at[3])) if len(at) > 3 else 0, hidden))
    return pins
