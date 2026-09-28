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
    "column": "#c1bcb2", "upright": "#8e959c", "beam": "#e8641f", "palletWood": "#b58b58",
    "palletBlue": "#2f5cc8", "load": "#c8a878", "desk": "#f6f6f4", "workTop": "#24282d", "workFrame": "#c3c6cb",
    "bench": "#c4ccd6", "sofa": "#9aa6b8", "stair": "#d2d6db", "monitor": "#1b1e23", "gantry": "#1f2226",
    "led": "#ffffff", "sign": "#e8572a", "cooler": "#f3f3f1", "tv": "#16181c", "screen": "#e7e3f4",
    "tape": "#e8b818", "steel": "#b7bcc2", "bin": "#2e62c9", "film": "#7ad6a0", "stackerYellow": "#f2c230",
    "stackerBlue": "#2f6fd0", "chairBeige": "#e6d6b4", "chairRed": "#b8322a", "boxDark": "#3a3f47", "cageSilver": "#c9ced6", "cagePink": "#e46aa3", "cageSilverMesh": "#c9ced6",
    "cagePinkMesh": "#e46aa3", "product": "#c8a878", "productDark": "#2b2f36", "productColor": "#2a8fd6", "person": "#f2c230", "personHead": "#2b3440", "shirtBlue": "#2a8fd6",
    "shirtBlack": "#2a2d33", "legs": "#2b3440", "shoes": "#151515",
    "skin0": "#f1c7a5", "skin1": "#e0ac86", "skin2": "#c68b62", "skin3": "#9a6444", "skin4": "#70472f",
    "hair0": "#1c1714", "hair1": "#3b2a20", "hair2": "#5e412a", "hair3": "#2a2a2a", "hair4": "#8a7d70",
    "pants0": "#1f2833", "pants1": "#2e3f5c", "pants2": "#232428", "pants3": "#34405a", "forklift": "#f08c00", "forkliftDark": "#2b3440",
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

    def sphere(self, cx, cy, cz, r, rings=10, seg=16, top_only=False, sz=1.0):
        """Esfera UV (ou só a calota superior, para cabelo)."""
        base = len(self.verts)
        last = rings // 2 + 1 if top_only else rings
        for i in range(last + 1):
            th = math.pi * i / rings
            for j in range(seg):
                ph = 2 * math.pi * j / seg
                self.verts.append((cx + r * math.sin(th) * math.cos(ph), cy + r * math.sin(th) * math.sin(ph), cz + r * sz * math.cos(th)))
        for i in range(last):
            for j in range(seg):
                a, b = base + i * seg + j, base + i * seg + (j + 1) % seg
                self.faces.append((a, a + seg, b + seg, b))

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


# Texturas procedurais (ruído em coordenadas de objeto, em metros): (escala, intensidade, relevo)
NOISE = {
    "slab": (1.2, 0.35, 0.04), "wall": (0.9, 0.4, 0.08), "load": (6.0, 0.25, 0.0), "palletWood": (14.0, 0.45, 0.0),
    "workTop": (20.0, 0.15, 0.0), "officeWall": (3.0, 0.1, 0.0), "room": (4.0, 0.08, 0.0), "path": (18.0, 0.2, 0.0),
    "tape": (10.0, 0.25, 0.0), "palletBlue": (25.0, 0.2, 0.0),
}


def add_noise(mat, scale, strength, bump):
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = strength
    mix.inputs["Color1"].default_value = bsdf.inputs["Base Color"].default_value
    nt.links.new(noise.outputs["Fac"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    if bump > 0:
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(noise.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])


MATERIAL_OPTS = {
    "upright": {"roughness": 0.6, "metallic": 0.15}, "beam": {"roughness": 0.6, "metallic": 0.1},
    "gantry": {"roughness": 0.5, "metallic": 0.3}, "palletBlue": {"roughness": 0.55},
    "monitor": {"roughness": 0.4}, "fenceMesh": {"alpha": 0.35}, "led": {"emission": 4.0},
    "screen": {"emission": 0.6}, "door": {"roughness": 0.5, "metallic": 0.2},
    "cageSilver": {"roughness": 0.35, "metallic": 0.6}, "steel": {"roughness": 0.4, "metallic": 0.55}, "cagePink": {"roughness": 0.45, "metallic": 0.3},
    "cageSilverMesh": {"alpha": 0.4, "metallic": 0.5}, "cagePinkMesh": {"alpha": 0.4, "metallic": 0.3},
}


def flush(batch, name, mat_key, collection):
    if not batch.faces:
        return None
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(batch.verts, [], batch.faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    fresh = bpy.data.materials.get("DB_" + mat_key) is None
    mat = material("DB_" + mat_key, COLORS[mat_key], **MATERIAL_OPTS.get(mat_key, {}))
    if fresh and mat_key in NOISE:
        add_noise(mat, *NOISE[mat_key])
    obj.data.materials.append(mat)
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
                    # travamento da cabeceira: diagonais em zigue-zague
                    ya, yb, step = f[0] + UP / 2, f[1] - UP / 2, 1.2
                    n_br = int((R["uprightHeight"] - 0.3) // step)
                    for k in range(n_br):
                        z_a = 0.15 + k * step
                        y_s, y_e = (ya, yb) if k % 2 == 0 else (yb, ya)
                        length = math.hypot(step, y_e - y_s)
                        ang = math.atan2(step, y_e - y_s)
                        ym_, zm_ = (y_s + y_e) / 2, z_a + step / 2
                        # caixa longa girada no plano Y-Z
                        base = len(B("upright").verts)
                        hl, t = length / 2, 0.018
                        ca, sa = math.cos(ang), math.sin(ang)
                        for dx in (-t, t):
                            for (ly, lz) in ((-hl, -t), (hl, -t), (hl, t), (-hl, t)):
                                B("upright").verts.append((X(u) + dx, ym_ + ly * ca - lz * sa, zm_ + ly * sa + lz * ca))
                        B("upright").faces += [(base + 0, base + 1, base + 2, base + 3), (base + 4, base + 7, base + 6, base + 5),
                                               (base + 0, base + 4, base + 5, base + 1), (base + 1, base + 5, base + 6, base + 2),
                                               (base + 2, base + 6, base + 7, base + 3), (base + 3, base + 7, base + 4, base + 0)]
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
        for rc in rects:  # paletes no piso demarcados com fita amarela
            tape_rect(X(rc[0]) - 0.08, Y(rc[3]) - 0.08, X(rc[2]) + 0.08, Y(rc[1]) + 0.08, 0.05)
            if "occupancy" in fp and rng.random() > fp["occupancy"]:
                continue
            wood = fp.get("pallet") == "wood"
            rect_box("palletWood" if wood else "palletBlue", rc, 0, 0.14 if wood else 0.15)
            w, d = (rc[2] - rc[0]) / S, (rc[3] - rc[1]) / S
            pxc, pyc = X((rc[0] + rc[2]) / 2), Y((rc[1] + rc[3]) / 2)
            if fp.get("load") == "stack":  # pilha de caixas variadas
                z = 0.14
                for _ in range(1 + int(rng.random() * 3)):
                    h = 0.25 + rng.random() * 0.35
                    sp = rng.random()
                    cells = [(0, 0, 1, 1)] if sp < 0.3 else [(0, 0, .5, 1), (.5, 0, 1, 1)] if sp < 0.65 else \
                        [(0, 0, .5, .5), (.5, 0, 1, .5), (0, .5, .5, 1), (.5, .5, 1, 1)]
                    for c in cells:
                        bw, bd = (c[2] - c[0]) * w - 0.03, (c[3] - c[1]) * d - 0.03
                        bx, by = pxc - w / 2 + (c[0] + c[2]) / 2 * w, pyc - d / 2 + (c[1] + c[3]) / 2 * d
                        B("boxDark" if rng.random() < 0.2 else "load").box(bx - bw / 2, by - bd / 2, bx + bw / 2, by + bd / 2, z, h * (0.8 + rng.random() * 0.4))
                    z += h
                continue
            if fp.get("load") == "tall":
                lw, ld, h = 0.31, 0.475, 0.85
            else:
                lw, ld, h = 0.4 + rng.random() * 0.08, 0.37 + rng.random() * 0.1, 0.45 + rng.random() * 0.75
            B("load").box(pxc - w * lw, pyc - d * ld, pxc + w * lw, pyc + d * ld, 0.15, h)

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
        if t == "steeltable":  # mesa de embalagem em aço com tampo preto
            for px_, py_ in ((x0 + .04, y0 + .04), (x1 - .04, y0 + .04), (x0 + .04, y1 - .04), (x1 - .04, y1 - .04)):
                B("steel").box(px_ - .03, py_ - .03, px_ + .03, py_ + .03, 0, 0.88)
            B("steel").box(x0 + .02, y0 + .02, x1 - .02, y1 - .02, 0.22, 0.03)
            B("workTop").box(x0, y0, x1, y1, 0.88, 0.04)
            continue
        if t == "binshelf":  # estante de aço com caixas plásticas azuis
            for px_, py_ in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                B("steel").box(px_ - .02, py_ - .02, px_ + .02, py_ + .02, 0, 1.6)
            for z in (0.1, 0.62, 1.14):
                B("steel").box(x0, y0, x1, y1, z, 0.02)
                B("bin").box(x0 + .04, y0 + .04, x1 - .04, y1 - .04, z + .02, 0.32)
            continue
        if t == "filmwrap":  # enroladeira de filme stretch
            fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
            B("steel").box(fx - .25, fy - .2, fx + .25, fy + .2, 0, 0.04)
            B("steel").box(fx - .03, fy - .03, fx + .03, fy + .03, 0.04, 1.05)
            B("film").box(fx - .25, fy - .24, fx + .25, fy, 0.93, 0.24)
            continue
        if t == "rackcabinet":
            B("monitor").box(x0, y0, x1, y1, 0, 2.0)
            continue
        if t == "wallbox":
            B("steel").box(x0, y0, x1, y1, 1.2, 1.0)
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

    # Gaiolas metálicas vazadas da triagem (prata e rosa), frente aberta para as mesas, com produtos pequenos
    cages = L.get("cages")
    for i, rc in enumerate(cages["rects"] if cages else []):
        cw, cd, H = cages["size"]
        key = "cageSilver" if i % 2 == 0 else "cagePink"
        gx, gy = X((rc[0] + rc[2]) / 2), Y((rc[1] + rc[3]) / 2)
        x0, x1, y0, y1, t = gx - cw / 2, gx + cw / 2, gy - cd / 2, gy + cd / 2, 0.03
        for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            B("monitor").box(px - 0.05, py - 0.05, px + 0.05, py + 0.05, 0, 0.12)
            B(key).box(px - t, py - t, px + t, py + t, 0.12, H - 0.12)
        B(key).box(x0, y0, x1, y1, 0.12, 0.04)
        for a in ((x0, y0, x1, y0 + t), (x0, y1 - t, x1, y1), (x0, y0, x0 + t, y1), (x1 - t, y0, x1, y1)):
            B(key).box(a[0], a[1], a[2], a[3], H - 0.03, 0.03)
        B(key + "Mesh").box(x0, y1 - 0.005, x1, y1, 0.16, H - 0.16)  # fundo (norte)
        B(key + "Mesh").box(x0, y0, x0 + 0.005, y1, 0.16, H - 0.16)  # laterais
        B(key + "Mesh").box(x1 - 0.005, y0, x1, y1, 0.16, H - 0.16)
        for z in (0.72, 1.28):
            B(key + "Mesh").box(x0, y0, x1, y1, z, 0.005)
        for z in (0.16, 0.72, 1.28):
            x = x0 + 0.04
            for _ in range(2 + int(rng.random() * 3)):
                w, h, d = 0.12 + rng.random() * 0.14, 0.1 + rng.random() * 0.25, 0.2 + rng.random() * 0.35
                if x + w > x1 - 0.04:
                    break
                B(rng.choice(["product", "productDark", "productColor"])).box(x, y1 - 0.06 - d, x + w, y1 - 0.06, z + 0.01, h)
                x += w + 0.03

    # Postos numerados da triagem: poste, placa laranja e câmera
    for u, v, _num in L.get("posts", []):
        px, py = X(u), Y(v)
        B("gantry").box(px - 0.04, py - 0.04, px + 0.04, py + 0.04, 0, 3.3)
        B("sign").box(px - 0.15, py - 0.075, px + 0.15, py - 0.045, 2.33, 0.44)
        B("cooler").box(px - 0.08, py - 0.1, px + 0.08, py + 0.06, 3.3, 0.1)

    # TV de acompanhamento na parede
    for tv in L.get("tvs", []):
        px, py, w = X(tv["p"][0]), Y(tv["p"][1]), tv["w"]
        if tv.get("facing") == "south":
            B("tv").box(px - w / 2, py - 0.05, px + w / 2, py, 1.8, w * 0.57)
            B("screen").box(px - w / 2 + 0.03, py - 0.055, px + w / 2 - 0.03, py - 0.05, 1.83, w * 0.57 - 0.06)
        else:
            B("tv").box(px, py - w / 2, px + 0.05, py + w / 2, 1.6, w * 0.57)
            B("screen").box(px + 0.05, py - w / 2 + 0.03, px + 0.055, py + w / 2 - 0.03, 1.63, w * 0.57 - 0.06)

    # Empilhadeiras manuais (stackers) junto à recarga
    for st in L.get("stackers", []):
        ox, oy = X(st["p"][0]), Y(st["p"][1])
        a = -math.radians(st.get("deg", 0))
        ca, sa = math.cos(a), math.sin(a)

        def sbox(key, f0, s0, f1, s1, z0, h):
            fm, sm = (f0 + f1) / 2, (s0 + s1) / 2
            bx, by = ox + ca * fm - sa * sm, oy + sa * fm + ca * sm
            B(key).box(bx - (f1 - f0) / 2, by - (s1 - s0) / 2, bx + (f1 - f0) / 2, by + (s1 - s0) / 2, z0, h, a, bx, by)
        for sd in (-0.3, 0.3):
            sbox("stackerBlue", 0, sd - .05, 1.05, sd + .05, 0, 0.09)
            sbox("steel", 0.1, sd * .55 - .05, 1.15, sd * .55 + .05, 0.1, 0.04)
            sbox("stackerYellow", -.05, sd - .035, .03, sd + .035, 0, 2.2)
        sbox("stackerYellow", -.05, -.33, .03, .33, 2.15, 0.06)
        sbox("stackerBlue", -.45, -.25, -.05, .25, 0, 0.45)
        sbox("monitor", -.55, -.03, -.5, .03, 0.45, 0.65)

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

    chair_keys = {"beige": "chairBeige", "red": "chairRed"}
    for c in L.get("chairs", []):
        u, v = c[0], c[1]
        ck = chair_keys.get(c[2] if len(c) > 2 else "", "monitor")
        sx, sy, a = X(u), Y(v), face_angle(u, v)  # não usar cx/cy: são o centro da planta usado por X()/Y()
        B(ck).box(sx - 0.24, sy - 0.24, sx + 0.24, sy + 0.24, 0.42, 0.08, a, sx, sy)
        bx, by = sx - math.cos(a) * 0.24, sy - math.sin(a) * 0.24
        B(ck).box(bx - 0.04, by - 0.24, bx + 0.04, by + 0.24, 0.5, 0.78, a, bx, by)
        B("gantry").box(sx - 0.03, sy - 0.03, sx + 0.03, sy + 0.03, 0.07, 0.35)
        for k in range(5):  # base estrela
            ang = a + k * 2 * math.pi / 5
            lx, ly = sx + math.cos(ang) * 0.15, sy + math.sin(ang) * 0.15
            B("gantry").box(lx - 0.15, ly - 0.02, lx + 0.15, ly + 0.02, 0.04, 0.035, ang, lx, ly)
        for sd in (-0.26, 0.26):  # braços
            ax, ay = sx - math.sin(a) * sd, sy + math.cos(a) * sd
            B("monitor").box(ax - 0.15, ay - 0.03, ax + 0.15, ay + 0.03, 0.62, 0.04, a, ax, ay)

    # Pessoas humanoides: em pé trabalhando (triagem) e sentadas nas estações, com uniforme azul ou preto
    def human(px, py, a, pose, shirt, seed):
        ca, sa = math.cos(a), math.sin(a)

        def pt(f, sd):
            return px + ca * f - sa * sd, py + sa * f + ca * sd

        skin, hair = "skin%d" % (seed % 5), "hair%d" % ((seed * 3 + 1) % 5)
        pants = "pants%d" % ((seed * 7 + 2) % 4)
        sit = pose == "sit"
        hip = 0.5 if sit else 0.93
        for sd in (-0.085, 0.085):
            if sit:
                tx, ty = pt(0.18, sd)
                B(pants).box(tx - 0.24, ty - 0.068, tx + 0.24, ty + 0.068, 0.44, 0.14, a, tx, ty)
                kx, ky = pt(0.4, sd)
                B(pants).cylinder(kx, ky, 0.052, 0.06, 0.42)
                sx, sy = pt(0.45, sd)
            else:
                kx, ky = pt(0, sd)
                B(pants).cylinder(kx, ky, 0.052, 0.06, 0.43)
                B(pants).cylinder(kx, ky, 0.068, 0.49, 0.44)
                sx, sy = pt(0.05, sd)
            B("shoes").box(sx - 0.125, sy - 0.05, sx + 0.125, sy + 0.05, 0, 0.07, a, sx, sy)
        B(pants).cylinder(px, py, 0.14, hip - 0.06, 0.14)
        B(shirt).cylinder(px, py, 0.16, hip + 0.06, 0.47, 16)
        B(skin).cylinder(px, py, 0.045, hip + 0.53, 0.09)
        hz = hip + 0.72
        hx, hy = pt(0.01, 0)
        B(skin).sphere(hx, hy, hz, 0.1, sz=1.08)
        bx, by = pt(-0.012, 0)
        B(hair).sphere(bx, by, hz + 0.012, 0.106, top_only=True, sz=1.05)
        nx, ny = pt(0.1, 0)
        B(skin).sphere(nx, ny, hz - 0.01, 0.02, 6, 8)
        sh = hip + 0.49
        for sd in (-0.205, 0.205):
            ux, uy = pt(0.05, sd)
            B(shirt).cylinder(ux, uy, 0.058, sh - 0.14, 0.14)
            B(skin).cylinder(ux, uy, 0.045, sh - 0.27, 0.13)
            fx, fy = pt(0.22, sd * 0.9)
            B(skin).box(fx - 0.17, fy - 0.038, fx + 0.17, fy + 0.038, sh - 0.33, 0.07, a, fx, fy)
            hx2, hy2 = pt(0.42, sd * 0.85)
            B(skin).sphere(hx2, hy2, sh - 0.3, 0.042, 6, 10)

    for i, p in enumerate(L["people"]):
        human(X(p[0]), Y(p[1]), face_angle(p[0], p[1]), "work", "shirtBlack" if i % 3 == 2 else "shirtBlue", i)
    for i, p in enumerate(L.get("seated", [])):
        a = face_angle(p[0], p[1])
        human(X(p[0]) - math.cos(a) * 0.12, Y(p[1]) - math.sin(a) * 0.12, a, "sit",
              "shirtBlack" if i % 3 == 1 else "shirtBlue", i + 5)

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
        "Paletes": ["palletWood", "palletBlue", "load", "boxDark"],
        "Caminho seguro": ["path"],
        "Areas": [k for k in COLORS if k.startswith("tint_")] + ["tape"],
        "Escritorios": ["officeWall", "partition", "room"],
        "Mobiliario": ["desk", "workTop", "workFrame", "bench", "sofa", "stair", "monitor", "gantry", "led",
                       "sign", "cooler", "tv", "screen", "cageSilver", "cagePink", "cageSilverMesh", "cagePinkMesh",
                       "product", "productDark", "productColor", "steel", "bin", "film", "chairBeige", "chairRed"],
        "Pessoas e empilhadeiras": ["person", "personHead", "shirtBlue", "shirtBlack", "legs", "shoes", "forklift", "forkliftDark", "stackerYellow", "stackerBlue"]
                                   + [k for k in COLORS if k[:4] in ("skin", "hair") or k.startswith("pants")],
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
