"""Gera no Blender o modelo 3D do barracão Duas Barras a partir de apps-script/Layout.html.

Os mesmos dados alimentam o visualizador web (Apps Script); este script serve para renders,
vídeos e para exportar o modelo em .glb/.blend.

Uso pela linha de comando (Blender 3.6 ou mais novo):
    blender --background --python blender/gerar_modelo.py -- --blend saida/duas-barras.blend --glb saida/duas-barras.glb

Opções depois de "--":
    --layout CAMINHO     arquivo Layout.html (padrão: ../apps-script/Layout.html ao lado deste script)
    --blend CAMINHO      salva a cena em .blend
    --glb CAMINHO        exporta a cena em glTF binário (.glb)
    --paredes-altas      paredes externas com a altura real (10 m) em vez do corte de 2,4 m

Dentro do Blender: abra este arquivo no editor de texto, ajuste LAYOUT_PATH se necessário e clique em "Run Script".
Eixos: X = leste, Y = norte, Z = altura, em metros.
"""

import json
import math
import os
import random
import re
import sys

import bpy

LAYOUT_PATH = ""  # preencha se o script não encontrar o Layout.html sozinho

COLORS = {
    "slab": "#f7f7f5", "slabSide": "#d5d9de", "wall": "#d9d6cf", "officeWall": "#ead7a4",
    "partition": "#b9bec6", "enclosure": "#c3c7cd", "column": "#c4c8ce", "upright": "#2f55d4",
    "beam": "#e8a317", "palletWood": "#b58b58", "load": "#cfb893", "desk": "#fbfbfa",
    "bench": "#c4ccd6", "sofa": "#9aa6b8", "stair": "#d2d6db", "person": "#f2c230",
    "personHead": "#2b3440", "forklift": "#f08c00", "forkliftDark": "#2b3440", "path": "#178a4c",
    "room": "#f3eee5",
    "tint_storage": "#e2e8f4", "tint_danger": "#f6dada", "tint_ship": "#dbeee2", "tint_neutral": "#e2e4e7",
    "tint_sort": "#dce6f8", "tint_test": "#f8eacf", "tint_office": "#e5e8ef", "tint_receive": "#eae1f5",
}


# ---------------------------------------------------------------------------
# Leitura dos dados
# ---------------------------------------------------------------------------
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"layout": None, "blend": None, "glb": None, "tall": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--layout", "--blend", "--glb"):
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        if a == "--paredes-altas":
            opts["tall"] = True
        i += 1
    return opts


def find_layout(explicit):
    candidates = [explicit, LAYOUT_PATH]
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(here, "..", "apps-script", "Layout.html"))
    except NameError:
        pass
    if bpy.data.filepath:
        candidates.append(os.path.join(os.path.dirname(bpy.data.filepath), "apps-script", "Layout.html"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError("Layout.html não encontrado. Informe --layout ou preencha LAYOUT_PATH no script.")


def load_layout(path):
    text = open(path, encoding="utf-8").read()
    match = re.search(r"<script[^>]*id=\"layout-data\"[^>]*>(.*?)</script>", text, re.S)
    if not match:
        raise ValueError("Bloco layout-data não encontrado em " + path)
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# Construção de malhas: cada material vira um único objeto (rápido e leve)
# ---------------------------------------------------------------------------
class Batch:
    def __init__(self):
        self.verts, self.faces = [], []

    def box(self, x0, y0, x1, y1, z0, h, rot=0.0, cx=None, cy=None):
        """Caixa alinhada aos eixos (ou girada em torno de cx, cy) com base em z0."""
        xs, ys = (min(x0, x1), max(x0, x1)), (min(y0, y1), max(y0, y1))
        base = len(self.verts)
        corners = [(xs[0], ys[0]), (xs[1], ys[0]), (xs[1], ys[1]), (xs[0], ys[1])]
        if rot:
            c, s = math.cos(rot), math.sin(rot)
            corners = [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in corners]
        for z in (z0, z0 + h):
            for x, y in corners:
                self.verts.append((x, y, z))
        self.faces += [
            (base + 0, base + 3, base + 2, base + 1), (base + 4, base + 5, base + 6, base + 7),
            (base + 0, base + 1, base + 5, base + 4), (base + 1, base + 2, base + 6, base + 5),
            (base + 2, base + 3, base + 7, base + 6), (base + 3, base + 0, base + 4, base + 7),
        ]

    def cylinder(self, cx, cy, r, z0, h, n=12):
        base = len(self.verts)
        for z in (z0, z0 + h):
            for i in range(n):
                a = 2 * math.pi * i / n
                self.verts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
        self.faces.append(tuple(base + i for i in reversed(range(n))))
        self.faces.append(tuple(base + n + i for i in range(n)))
        for i in range(n):
            j = (i + 1) % n
            self.faces.append((base + i, base + j, base + n + j, base + n + i))


def hex_to_linear(h):
    h = h.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb) + (1.0,)


def material(name, hex_color, roughness=0.9, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = hex_to_linear(hex_color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = hex_to_linear(hex_color)
    return mat


def flush(batch, name, mat_key, collection, roughness=0.9, metallic=0.0):
    if not batch.faces:
        return None
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(batch.verts, [], batch.faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material("DB_" + mat_key, COLORS[mat_key], roughness, metallic))
    collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Cena
# ---------------------------------------------------------------------------
def build(L, tall):
    S = L["meta"]["pxPerMeter"]
    HT = L["meta"]["heights"]
    b = L["meta"]["bounds"]
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    W, D = (b[2] - b[0]) / S, (b[3] - b[1]) / S

    def X(u):
        return (u - cx) / S

    def Y(v):  # norte da planta (topo da imagem) = +Y
        return -(v - cy) / S

    rng = random.Random(20260928)

    for obj in list(bpy.data.objects):
        if obj.name.startswith("DB_") or obj.name in ("Camera_DuasBarras", "Sol_DuasBarras"):
            bpy.data.objects.remove(obj, do_unlink=True)
    root = bpy.data.collections.get("Duas Barras") or bpy.data.collections.new("Duas Barras")
    if root.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(root)

    def coll(name):
        c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if c.name not in root.children:
            root.children.link(c)
        return c

    batches = {}

    def B(key):
        return batches.setdefault(key, Batch())

    def rect_box(key, r, z0, h):
        B(key).box(X(r[0]), Y(r[1]), X(r[2]), Y(r[3]), z0, h)

    def wall(key, seg, thick, h, extend=None):
        # Por padrão cada ponta avança meia espessura (fecha os cantos), 3 mm a menos para
        # não deixar faces coplanares nas junções, que aparecem como riscos pretos no render.
        x1, y1, x2, y2 = X(seg[0]), Y(seg[1]), X(seg[2]), Y(seg[3])
        length = math.hypot(x2 - x1, y2 - y1)
        ext = thick / 2 - 0.003 if extend is None else extend
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        rot = math.atan2(y2 - y1, x2 - x1)
        B(key).box(mx - length / 2 - ext, my - thick / 2, mx + length / 2 + ext, my + thick / 2, 0, h, rot, mx, my)

    # Piso
    B("slabSide").box(-W / 2 - 0.4, -D / 2 - 0.4, W / 2 + 0.4, D / 2 + 0.4, -0.35, 0.34)
    B("slab").box(-W / 2, -D / 2, W / 2, D / 2, -0.01, 0.01)

    # Paredes e pilares
    wall_h = HT["warehouseWall"] if tall else HT["cutWall"]
    for s in L["walls"]["perimeter"]:
        wall("wall", s, 0.25, wall_h)
    for c in L["columns"]:
        B("column").box(X(c[0]) - 0.22, Y(c[1]) - 0.22, X(c[0]) + 0.22, Y(c[1]) + 0.22, 0, HT["column"] if tall else HT["cutWall"] + 0.05)
    for i, s in enumerate(L["walls"]["office"]):  # alturas levemente diferentes: sem topos coplanares
        wall("officeWall", s, 0.16, HT["officeWall"] + 0.002 * (i % 3))
    for s in L["walls"]["partition"]:
        wall("partition", s, 0.08, HT["partition"])
    for s in L["walls"]["enclosure"]:
        wall("enclosure", s, 0.1, HT["enclosure"])

    # Áreas e salas (placas finas no piso)
    for z in L["zones"]:
        rect_box("tint_" + z.get("tint", "neutral"), z["rect"], 0.0, 0.008)
    for rm in L["rooms"]:
        rect_box("room", rm["rect"], 0.0, 0.012)

    # Porta-paletes
    R = L["racks"]
    UP, BEAM_H, BEAM_T = 0.09, 0.12, 0.06
    top = len(R["levels"]) - 1
    for row in R["rows"]:
        y0, y1 = Y(row["v"][0]), Y(row["v"][1])  # y0 > y1
        ym = (y0 + y1) / 2
        faces = [(ym + 0.06, y0), (y1, ym - 0.06)]
        bays = []
        for bl in (R["bays"]["left"], R["bays"]["right"]):
            for u in bl:
                for f in faces:
                    for yy in (f[0] + UP / 2, f[1] - UP / 2):
                        B("upright").box(X(u) - UP / 2, yy - UP / 2, X(u) + UP / 2, yy + UP / 2, 0, R["uprightHeight"])
            bays += [(bl[i], bl[i + 1], 0) for i in range(len(bl) - 1)]
        bays.append((R["bays"]["tunnel"][0], R["bays"]["tunnel"][1], R["tunnelFirstLevel"]))
        for ua, ub, first in bays:
            xa, xb = X(ua), X(ub)
            bw = xb - xa
            for f in faces:
                fd = f[1] - f[0]
                for li in range(first, top + 1):
                    z = R["levels"][li]
                    if li > 0:
                        for yy in (f[0] + UP / 2, f[1] - UP / 2):
                            B("beam").box(xa + UP / 2, yy - BEAM_T / 2, xb - UP / 2, yy + BEAM_T / 2, z - BEAM_H, BEAM_H)
                    for t in (0.27, 0.73):
                        if rng.random() < R["occupancy"]:
                            w, d = min(1.0, bw * 0.42), fd * 0.92
                            pxc, pyc = xa + bw * t, (f[0] + f[1]) / 2
                            B("palletWood").box(pxc - w / 2, pyc - d / 2, pxc + w / 2, pyc + d / 2, z, 0.14)
                            h = 0.85 + rng.random() * 0.45
                            B("load").box(pxc - w * 0.48, pyc - d * 0.47, pxc + w * 0.48, pyc + d * 0.47, z + 0.14, h)

    # Paletes no piso
    for fp in L["floorPallets"]:
        rects = list(fp.get("rects", []))
        g = fp.get("grid")
        if g:
            for r in range(g["rows"]):
                for c in range(g["cols"]):
                    u0, v0 = g["u0"] + c * g["du"], g["v0"] + r * g["dv"]
                    rects.append([u0, v0, u0 + g["w"], v0 + g["h"]])
        for rc in rects:
            rect_box("palletWood", rc, 0, 0.14)
            w, d = (rc[2] - rc[0]) / S, (rc[3] - rc[1]) / S
            pxc, pyc = X((rc[0] + rc[2]) / 2), Y((rc[1] + rc[3]) / 2)
            B("load").box(pxc - w * 0.48, pyc - d * 0.47, pxc + w * 0.48, pyc + d * 0.47, 0.14, 0.7 + rng.random() * 0.6)

    # Mobiliário
    furn = {"desk": ("desk", 0.75), "table": ("desk", 0.75), "bench": ("bench", 0.9), "counter": ("bench", 0.9),
            "cabinet": ("bench", 1.8), "sofa": ("sofa", 0.5)}
    for f in L["furniture"]:
        r = f["rect"]
        if f["type"] == "stair":
            steps, yn, ys = 12, Y(r[1]), Y(r[3])
            for i in range(steps):
                ya, yb = ys + (yn - ys) * i / steps, ys + (yn - ys) * (i + 1) / steps
                B("stair").box(X(r[0]), ya, X(r[2]), yb, 0, HT["officeWall"] * (i + 1) / steps)
            continue
        key, h = furn.get(f["type"], furn["desk"])
        rect_box(key, r, 0, h)

    # Pessoas
    for p in L["people"]:
        B("person").cylinder(X(p[0]), Y(p[1]), 0.21, 0, 1.15)
        B("personHead").cylinder(X(p[0]), Y(p[1]), 0.14, 1.22, 0.28)

    # Empilhadeiras (posição inicial do visualizador)
    for fl in L["forklifts"]:
        ox, oy = X(fl["u"][0]), Y(fl["v"])
        B("forklift").box(ox - 0.95, oy - 0.52, ox + 0.75, oy + 0.52, 0.12, 0.95)
        B("forkliftDark").box(ox - 0.95, oy - 0.52, ox + 0.41, oy + 0.52, 2.1, 0.05)
        for dx, dy in ((-0.9, -0.47), (-0.9, 0.47), (0.35, -0.47), (0.35, 0.47)):
            B("forkliftDark").box(ox + dx - 0.03, oy + dy - 0.03, ox + dx + 0.03, oy + dy + 0.03, 1.07, 1.05)
        for dy in (-0.37, 0.37):
            B("forkliftDark").box(ox + 0.78, oy + dy - 0.05, ox + 0.88, oy + dy + 0.05, 0, 2.4)
            B("forkliftDark").box(ox + 0.88, oy + dy - 0.06, ox + 2.0, oy + dy + 0.06, 0.08, 0.05)

    # Caminho seguro
    # Faixas terminam no vértice; altura diferente por direção e discos um pouco abaixo evitam faces coplanares.
    pw = L["path"]["width"]
    for line in L["path"]["segments"]:
        for i, pt in enumerate(line):
            B("path").cylinder(X(pt[0]), Y(pt[1]), pw / 2 * 0.995, 0.0, 0.02, 20)
            if i == 0:
                continue
            vertical = abs(pt[0] - line[i - 1][0]) < abs(pt[1] - line[i - 1][1])
            wall("path", [line[i - 1][0], line[i - 1][1], pt[0], pt[1]], pw, 0.023 if vertical else 0.022, extend=0)

    groups = {
        "Estrutura": ["slab", "slabSide", "wall", "column", "enclosure"],
        "Porta-paletes": ["upright", "beam"],
        "Paletes": ["palletWood", "load"],
        "Caminho seguro": ["path"],
        "Areas": [k for k in COLORS if k.startswith("tint_")],
        "Escritorios": ["officeWall", "partition", "room"],
        "Mobiliario": ["desk", "bench", "sofa", "stair"],
        "Pessoas e empilhadeiras": ["person", "personHead", "forklift", "forkliftDark"],
    }
    for gname, keys in groups.items():
        c = coll(gname)
        for k in keys:
            if k in batches:
                metal = 0.15 if k in ("upright", "beam") else 0.0
                flush(batches[k], "DB_" + k, k, c, 0.6 if metal else 0.9, metal)

    # Câmera, luz e mundo
    cam_data = bpy.data.cameras.new("Camera_DuasBarras")
    cam_data.lens = 35
    cam = bpy.data.objects.new("Camera_DuasBarras", cam_data)
    root.objects.link(cam)
    cam.location = (30, -42, 44)
    target = bpy.data.objects.new("DB_alvo_camera", None)
    target.location = (0, -1, 0)
    root.objects.link(target)
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("Sol_DuasBarras", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Sol_DuasBarras", sun_data)
    sun.rotation_euler = (math.radians(40), math.radians(12), math.radians(35))
    root.objects.link(sun)

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_linear("#e9ecef")
        bg.inputs["Strength"].default_value = 0.8

    bpy.context.scene.unit_settings.system = "METRIC"
    return sum(len(bt.faces) for bt in batches.values())


def main():
    opts = parse_args()
    path = find_layout(opts["layout"])
    faces = build(load_layout(path), opts["tall"])
    print(f"[Duas Barras] modelo gerado a partir de {path}: {faces} faces")
    if opts["blend"]:
        os.makedirs(os.path.dirname(os.path.abspath(opts["blend"])), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opts["blend"]))
        print("[Duas Barras] salvo", opts["blend"])
    if opts["glb"]:
        os.makedirs(os.path.dirname(os.path.abspath(opts["glb"])), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=os.path.abspath(opts["glb"]), export_format="GLB", export_apply=True)
        print("[Duas Barras] exportado", opts["glb"])


if __name__ == "__main__":
    main()
