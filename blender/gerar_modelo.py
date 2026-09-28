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
    "slab": "#c9c8c3", "slabSide": "#aeaca5", "wall": "#cbc5ba", "louver": "#aba6bb", "door": "#8e949c",
    "officeWall": "#e7e5e0", "partition": "#b9bec6", "fence": "#2b2f34", "fenceMesh": "#2b2f34",
    "column": "#c1bcb2", "upright": "#2f55d4", "beam": "#e8a317", "palletWood": "#b58b58",
    "palletBlue": "#2f5cc8", "load": "#c8a878", "desk": "#f6f6f4", "workTop": "#24282d", "workFrame": "#c3c6cb",
    "bench": "#c4ccd6", "sofa": "#9aa6b8", "stair": "#d2d6db", "monitor": "#1b1e23", "gantry": "#1f2226",
    "led": "#ffffff", "sign": "#e8572a", "cooler": "#f3f3f1", "tv": "#16181c", "screen": "#e7e3f4",
    "tape": "#e8b818", "person": "#f2c230", "personHead": "#2b3440", "shirtBlue": "#2a8fd6",
    "shirtBlack": "#2a2d33", "legs": "#2b3440", "forklift": "#f08c00", "forkliftDark": "#2b3440",
    "path": "#178a4c", "room": "#f3f1ec",
    "tint_storage": "#dfe5f2", "tint_danger": "#f3d4d4", "tint_ship": "#d6ecde", "tint_neutral": "#e0e2e5",
    "tint_sort": "#d8e3f7", "tint_test": "#f5e6c8", "tint_office": "#e3e6ee", "tint_receive": "#e7ddf3",
    "tint_dock": "#cfd3d8",
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


def material(name, hex_color, roughness=0.9, metallic=0.0, alpha=1.0, emission=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = hex_to_linear(hex_color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    if emission > 0:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = hex_to_linear(hex_color)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = hex_to_linear(hex_color)
    return mat


MATERIAL_OPTS = {
    "upright": {"roughness": 0.6, "metallic": 0.15}, "beam": {"roughness": 0.6, "metallic": 0.1},
    "gantry": {"roughness": 0.5, "metallic": 0.3}, "palletBlue": {"roughness": 0.55},
    "monitor": {"roughness": 0.4}, "fenceMesh": {"alpha": 0.35}, "led": {"emission": 4.0},
    "screen": {"emission": 0.6}, "door": {"roughness": 0.5, "metallic": 0.2},
}


def flush(batch, name, mat_key, collection):
    if not batch.faces:
        return None
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(batch.verts, [], batch.faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material("DB_" + mat_key, COLORS[mat_key], **MATERIAL_OPTS.get(mat_key, {})))
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
    # Paredes de concreto; com --paredes-altas, faixa de venezianas no alto (como nas fotos)
    wall_h = HT["louverBase"] if tall else HT["cutWall"]
    for s in L["walls"]["perimeter"]:
        wall("wall", s, 0.25, wall_h)
        if tall:
            x1, y1, x2, y2 = X(s[0]), Y(s[1]), X(s[2]), Y(s[3])
            length = math.hypot(x2 - x1, y2 - y1)
            mx, my, rot = (x1 + x2) / 2, (y1 + y2) / 2, math.atan2(y2 - y1, x2 - x1)
            B("louver").box(mx - length / 2, my - 0.09, mx + length / 2, my + 0.09, HT["louverBase"],
                            HT["warehouseWall"] - HT["louverBase"], rot, mx, my)
    for c in L["columns"]:
        B("column").box(X(c[0]) - 0.22, Y(c[1]) - 0.22, X(c[0]) + 0.22, Y(c[1]) + 0.22, 0, HT["column"] if tall else HT["cutWall"] + 0.05)
    for i, s in enumerate(L["walls"]["office"]):  # alturas levemente diferentes: sem topos coplanares
        wall("officeWall", s, 0.16, HT["officeWall"] + 0.002 * (i % 3))
    for s in L["walls"]["partition"]:
        wall("partition", s, 0.08, HT["partition"])
    # Cercas de tela das docas: postes a cada ~2 m, travessa superior e tela semitransparente
    for s in L["walls"]["fence"]:
        x1, y1, x2, y2 = X(s[0]), Y(s[1]), X(s[2]), Y(s[3])
        n = max(1, round(math.hypot(x2 - x1, y2 - y1) / 2))
        for i in range(n + 1):
            px, py = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
            B("fence").box(px - 0.04, py - 0.04, px + 0.04, py + 0.04, 0, HT["fence"] + 0.05)
        wall("fenceMesh", s, 0.01, HT["fence"])
        rail = [s[0], s[1], s[2], s[3]]
        x1, y1, x2, y2 = X(rail[0]), Y(rail[1]), X(rail[2]), Y(rail[3])
        length = math.hypot(x2 - x1, y2 - y1)
        mx, my, rot = (x1 + x2) / 2, (y1 + y2) / 2, math.atan2(y2 - y1, x2 - x1)
        B("fence").box(mx - length / 2, my - 0.03, mx + length / 2, my + 0.03, HT["fence"], 0.06, rot, mx, my)

    # Áreas e salas (placas finas no piso)
    def tape_rect(x0, y0, x1, y1, w):
        for a in ((x0, y0 - w / 2, x1, y0 + w / 2), (x0, y1 - w / 2, x1, y1 + w / 2),
                  (x0 - w / 2, y0, x0 + w / 2, y1), (x1 - w / 2, y0, x1 + w / 2, y1)):
            B("tape").box(a[0], a[1], a[2], a[3], 0.009, 0.004)

    for z in L["zones"]:
        rect_box("tint_" + z.get("tint", "neutral"), z["rect"], 0.0, 0.008)
        r = z["rect"]
        if z.get("tint") != "storage":
            tape_rect(X(r[0]), Y(r[3]), X(r[2]), Y(r[1]), 0.07)
        if z.get("door"):  # porta de enrolar da doca
            d = z["door"]
            x1, y1, x2, y2 = X(d[0]), Y(d[1]), X(d[2]), Y(d[3])
            length = math.hypot(x2 - x1, y2 - y1)
            mx, my, rot = (x1 + x2) / 2, (y1 + y2) / 2, math.atan2(y2 - y1, x2 - x1)
            B("door").box(mx - length / 2, my - 0.17, mx + length / 2, my + 0.17, 0,
                          HT["dockDoor"] if tall else HT["cutWall"] + 0.02, rot, mx, my)
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
        for rc in rects:  # paletes plásticos azuis demarcados com fita amarela
            rect_box("palletBlue", rc, 0, 0.15)
            w, d = (rc[2] - rc[0]) / S, (rc[3] - rc[1]) / S
            pxc, pyc = X((rc[0] + rc[2]) / 2), Y((rc[1] + rc[3]) / 2)
            if fp.get("load") == "tall":
                lw, ld, h = 0.31, 0.475, 0.85
            else:
                lw, ld, h = 0.4 + rng.random() * 0.08, 0.37 + rng.random() * 0.1, 0.45 + rng.random() * 0.75
            B("load").box(pxc - w * lw, pyc - d * ld, pxc + w * lw, pyc + d * ld, 0.15, h)
            tape_rect(X(rc[0]) - 0.08, Y(rc[3]) - 0.08, X(rc[2]) + 0.08, Y(rc[1]) + 0.08, 0.05)

    # Mobiliário
    furn = {"counter": ("bench", 0.9), "cabinet": ("bench", 1.8), "sofa": ("sofa", 0.5)}

    def monitors(x0, y0, x1, y1, top, n=None, side=0.0):
        along_x = abs(x1 - x0) >= abs(y1 - y0)
        length = abs(x1 - x0) if along_x else abs(y1 - y0)
        n = int(length // 1.3) if n is None else n
        for i in range(n):
            t = (i + 0.5) / n
            cx = x0 + (x1 - x0) * t if along_x else (x0 + x1) / 2 + side
            cy = (y0 + y1) / 2 + side if along_x else y0 + (y1 - y0) * t
            rot = 0.0 if along_x else math.pi / 2
            B("monitor").box(cx - 0.1, cy - 0.08, cx + 0.1, cy + 0.08, top, 0.18, rot, cx, cy)
            B("monitor").box(cx - 0.29, cy - 0.018, cx + 0.29, cy + 0.018, top + 0.16, 0.36, rot, cx, cy)

    for f in L["furniture"]:
        r = f["rect"]
        x0, y0, x1, y1 = X(r[0]), Y(r[3]), X(r[2]), Y(r[1])
        t = f["type"]
        if t == "worktable":
            B("workFrame").box(x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05, 0, 0.72)
            B("workTop").box(x0, y0, x1, y1, 0.72, 0.04)
            monitors(x0, y0, x1, y1, 0.76, f.get("monitors"))
            continue
        if t in ("desk", "table"):
            along_x = (x1 - x0) >= (y1 - y0)
            B("desk").box(x0, y0, x1, y1, 0.71, 0.04)
            if along_x:
                B("desk").box(x0, y0, x0 + 0.04, y1, 0, 0.71)
                B("desk").box(x1 - 0.04, y0, x1, y1, 0, 0.71)
            else:
                B("desk").box(x0, y0, x1, y0 + 0.04, 0, 0.71)
                B("desk").box(x0, y1 - 0.04, x1, y1, 0, 0.71)
            if f.get("divider"):
                ym, xm = (y0 + y1) / 2, (x0 + x1) / 2
                if along_x:
                    B("bench").box(x0, ym - 0.02, x1, ym + 0.02, 0.75, 0.3)
                else:
                    B("bench").box(xm - 0.02, y0, xm + 0.02, y1, 0.75, 0.3)
                half = -(-(f.get("monitors") or 2) // 2)
                for off in (-0.3, 0.3):
                    monitors(x0, y0, x1, y1, 0.75, half, off)
            elif t == "desk":
                monitors(x0, y0, x1, y1, 0.75, f.get("monitors"))
            continue
        if t == "bench":  # bancada de teste dupla com pórtico e luminárias
            xm, yc = (x0 + x1) / 2, (y0 + y1) / 2
            B("desk").box(x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05, 0, 0.72)
            B("workTop").box(x0, y0, x1, y1, 0.72, 0.04)
            B("desk").box(xm - 0.03, y0, xm + 0.03, y1, 0.76, 0.62)
            monitors(xm - 0.35, y0, xm - 0.35, y1, 0.76, 2)
            monitors(xm + 0.35, y0, xm + 0.35, y1, 0.76, 2)
            g0, g1, H = y0 - 0.15, y1 + 0.15, 2.7
            B("gantry").box(xm - 0.03, g0 - 0.03, xm + 0.03, g0 + 0.03, 0, H)
            B("gantry").box(xm - 0.03, g1 - 0.03, xm + 0.03, g1 + 0.03, 0, H)
            B("gantry").box(xm - 0.03, g0 - 0.03, xm + 0.03, g1 + 0.03, H, 0.06)
            for dx in (-0.45, 0.45):
                B("gantry").box(min(xm, xm + dx), yc - 0.02, max(xm, xm + dx), yc + 0.02, H - 0.02, 0.04)
                B("led").box(xm + dx - 0.03, y0 + 0.2, xm + dx + 0.03, y1 - 0.2, H - 0.06, 0.03)
            continue
        if t == "cooler":  # climatizador evaporativo
            B("cooler").box(x0, y0, x1, y1, 0, 1.5)
            B("cooler").box(x0 + 0.15, y0 + 0.1, x1 - 0.15, y1 - 0.1, 1.5, 0.7)
            continue
        if t == "stair":
            steps, yn, ys = 12, Y(r[1]), Y(r[3])
            for i in range(steps):
                ya, yb = ys + (yn - ys) * i / steps, ys + (yn - ys) * (i + 1) / steps
                B("stair").box(X(r[0]), ya, X(r[2]), yb, 0, HT["officeWall"] * (i + 1) / steps)
            continue
        key, h = furn.get(t, ("desk", 0.75))
        rect_box(key, r, 0, h)

    # Postos numerados da triagem: poste, placa laranja e câmera
    for u, v, _num in L.get("posts", []):
        px, py = X(u), Y(v)
        B("gantry").box(px - 0.04, py - 0.04, px + 0.04, py + 0.04, 0, 3.3)
        B("sign").box(px - 0.15, py - 0.075, px + 0.15, py - 0.045, 2.33, 0.44)
        B("cooler").box(px - 0.08, py - 0.1, px + 0.08, py + 0.06, 3.3, 0.1)

    # TV de acompanhamento na parede
    for tv in L.get("tvs", []):
        px, py, w = X(tv["p"][0]), Y(tv["p"][1]), tv["w"]
        B("tv").box(px, py - w / 2, px + 0.05, py + w / 2, 1.6, w * 0.57)
        B("screen").box(px + 0.05, py - w / 2 + 0.03, px + 0.055, py + w / 2 - 0.03, 1.63, w * 0.57 - 0.06)

    # Cadeiras viradas para a mesa mais próxima
    tables = [f["rect"] for f in L["furniture"] if re.search("desk|table|worktable|bench|counter", f["type"])]

    def face_angle(u, v):
        best, bd = None, float("inf")
        for r in tables:
            cu, cv = max(r[0], min(u, r[2])), max(r[1], min(v, r[3]))
            dd = math.hypot(cu - u, cv - v)
            if dd < bd:
                bd, best = dd, (cu, cv)
        if best is None or bd < 1:
            return 0.0
        return math.atan2(Y(best[1]) - Y(v), X(best[0]) - X(u))

    for u, v in L.get("chairs", []):
        sx, sy, a = X(u), Y(v), face_angle(u, v)  # não usar cx/cy: são o centro da planta usado por X()/Y()
        B("monitor").box(sx - 0.24, sy - 0.24, sx + 0.24, sy + 0.24, 0.42, 0.08, a, sx, sy)
        bx, by = sx - math.cos(a) * 0.24, sy - math.sin(a) * 0.24
        B("monitor").box(bx - 0.035, by - 0.23, bx + 0.035, by + 0.23, 0.5, 0.6, a, bx, by)
        B("gantry").box(sx - 0.03, sy - 0.03, sx + 0.03, sy + 0.03, 0, 0.42)

    # Pessoas: em pé (triagem) e sentadas nas estações, com uniforme azul ou preto
    for i, p in enumerate(L["people"]):
        px, py = X(p[0]), Y(p[1])
        B("legs").cylinder(px, py, 0.18, 0, 0.78)
        B("shirtBlack" if i % 3 == 2 else "shirtBlue").cylinder(px, py, 0.19, 0.78, 0.55)
        B("personHead").cylinder(px, py, 0.13, 1.36, 0.24)
    for i, p in enumerate(L.get("seated", [])):
        px, py, a = X(p[0]), Y(p[1]), face_angle(p[0], p[1])
        B("shirtBlack" if i % 3 == 1 else "shirtBlue").cylinder(px, py, 0.19, 0.48, 0.55)
        B("personHead").cylinder(px, py, 0.13, 1.06, 0.24)
        tx, ty = px + math.cos(a) * 0.2, py + math.sin(a) * 0.2
        B("legs").box(tx - 0.21, ty - 0.17, tx + 0.21, ty + 0.17, 0.45, 0.14, a, tx, ty)
        sx, sy = px + math.cos(a) * 0.38, py + math.sin(a) * 0.38
        B("legs").box(sx - 0.06, sy - 0.15, sx + 0.06, sy + 0.15, 0, 0.45, a, sx, sy)

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
        "Estrutura": ["slab", "slabSide", "wall", "louver", "door", "column", "fence", "fenceMesh"],
        "Porta-paletes": ["upright", "beam"],
        "Paletes": ["palletWood", "palletBlue", "load"],
        "Caminho seguro": ["path"],
        "Areas": [k for k in COLORS if k.startswith("tint_")] + ["tape"],
        "Escritorios": ["officeWall", "partition", "room"],
        "Mobiliario": ["desk", "workTop", "workFrame", "bench", "sofa", "stair", "monitor", "gantry", "led",
                       "sign", "cooler", "tv", "screen"],
        "Pessoas e empilhadeiras": ["person", "personHead", "shirtBlue", "shirtBlack", "legs", "forklift", "forkliftDark"],
    }
    for gname, keys in groups.items():
        c = coll(gname)
        for k in keys:
            if k in batches:
                flush(batches[k], "DB_" + k, k, c)

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
