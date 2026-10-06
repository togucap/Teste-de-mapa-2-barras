"""Gera no Blender o modelo 3D da casa "Jardim Primavera - 2 dormitórios, lado esquerdo".

As paredes saem dos vetores da planta de arquitetura (PDF, escala 1:75): cada polígono laranja de
alvenaria estrutural foi copiado em pontos do PDF para WALL_POLYS e é convertido para metros por P().
Portas, janelas, móveis e iluminação seguem a planta e as fotos de referência (tons bege, LED quente).

Uso (Blender 4.2 ou mais novo, ou o módulo bpy no Python):
    blender --background --python blender/gerar_casa.py -- --glb saida/casa.glb --blend saida/casa.blend
    python3 blender/gerar_casa.py --glb saida/casa.glb --render renders/

Opções:
    --glb CAMINHO      exporta o modelo em glTF binário (é o que o visualizador do Apps Script usa)
    --blend CAMINHO    salva a cena em .blend
    --render PASTA     renderiza as câmeras com Cycles em PASTA (JPG)
    --cams a,b,c       renderiza só essas câmeras (nomes sem o prefixo "Cam_")
    --samples N        amostras do Cycles (padrão 96)
    --res LxA          resolução do render (padrão 1600x900)

Dentro do Blender: abra o arquivo no editor de texto e clique em "Run Script" (só monta a cena).
Eixos: X = da parede do vizinho (esquerda) para a direita, Y = da fachada (frente) para os fundos, Z = altura.
"""

import json
import math
import os
import random
import sys

import bpy
import numpy as np

# ---------------------------------------------------------------------------------------------------
# Escala e medidas gerais
# ---------------------------------------------------------------------------------------------------
K = 25.4 / 72 * 75 / 1000  # 1 ponto do PDF na escala 1:75 = 0,026458 m
PX0, PY0 = 57.72, 536.28    # canto frontal esquerdo externo da casa, em pontos do PDF


def P(x, y):
    """Ponto do PDF -> metros (X para a direita, Y da frente para os fundos)."""
    return ((x - PX0) * K, (PY0 - y) * K)


def PX(x):
    return (x - PX0) * K


def PYm(y):
    return (PY0 - y) * K


H = 2.60          # pé-direito
SLAB = 0.12       # laje (HT 12 cm na planta de lajes)
TOP = H + SLAB
DOOR_H = 2.10

# Polígonos laranja (alvenaria estrutural) da página "Planta de arquitetura", em pontos do PDF.
WALL_POLYS = [
    [(429.96, 170.64), (429.96, 177.84), (393.12, 177.84), (393.12, 170.64)],  # (fora da planta, ignorado)
    [(170.28, 232.92), (170.28, 159.6), (134.16, 159.6), (134.16, 165.24), (164.16, 165.24), (164.16, 276.36),
     (169.92, 276.36), (169.92, 238.56), (170.28, 238.56)],
    [(209.52, 329.64), (209.52, 354.12), (202.08, 354.12), (202.08, 348.48), (203.88, 348.48), (203.88, 271.2),
     (209.52, 271.2), (209.52, 324.0), (262.44, 324.0), (262.44, 291.84), (268.08, 291.84), (268.08, 324.0),
     (295.32, 324.0), (295.32, 372.84), (288.96, 372.84), (288.96, 329.64)],
    [(162.36, 439.2), (162.36, 348.48), (171.84, 348.48), (171.84, 354.12), (168.0, 354.12), (168.0, 433.56),
     (288.96, 433.56), (288.96, 418.56), (295.32, 418.56), (295.32, 458.04), (288.96, 458.04), (288.96, 439.2)],
    [(288.96, 488.28), (295.32, 488.28), (295.32, 536.28), (258.84, 536.28), (258.84, 529.92), (288.96, 529.92)],
    [(235.8, 529.92), (235.8, 536.28), (221.04, 536.28), (221.04, 529.92)],
    [(162.36, 499.68), (168.0, 499.68), (168.0, 529.92), (198.0, 529.92), (198.0, 536.28), (149.28, 536.28),
     (149.28, 529.92), (162.36, 529.92)],
    [(107.4, 536.28), (99.96, 536.28), (99.96, 529.92), (107.4, 529.92)],
    [(64.08, 308.88), (164.16, 308.88), (164.16, 306.6), (169.92, 306.6), (169.92, 314.52), (64.08, 314.52),
     (64.08, 529.92), (66.0, 529.92), (66.0, 536.28), (57.72, 536.28), (57.72, 159.6), (88.44, 159.6),
     (88.44, 165.24), (64.08, 165.24)],
    [(203.88, 240.96), (209.52, 240.96), (209.52, 238.56), (262.44, 238.56), (262.44, 261.24), (268.08, 261.24),
     (268.08, 238.56), (295.32, 238.56), (295.32, 232.92), (203.88, 232.92)],
]
WALL_POLYS = WALL_POLYS[1:]

# Cômodos: retângulos internos em pontos do PDF (para piso, rótulos e áreas)
ROOMS = {
    "sala":     {"nome": "Sala de estar e jantar", "rects": [(64.08, 314.52, 162.36, 529.92)]},
    "cozinha":  {"nome": "Cozinha", "rects": [(168.0, 439.2, 288.96, 529.92)]},
    "dorm1":    {"nome": "Dormitório 01", "rects": [(64.08, 165.24, 164.16, 308.88)]},
    "dorm2":    {"nome": "Dormitório 02 · Home office",
                 "rects": [(168.0, 354.12, 288.96, 433.56), (209.52, 329.64, 288.96, 354.12)]},
    "banho":    {"nome": "Banho social", "rects": [(209.52, 238.56, 262.44, 324.0)]},
    "servico":  {"nome": "Área de serviço", "rects": [(268.08, 238.56, 295.32, 324.0)]},
    "circ":     {"nome": "Circulação", "rects": [(169.92, 238.56, 203.88, 348.48)]},
}

# ---------------------------------------------------------------------------------------------------
# Utilidades de cena
# ---------------------------------------------------------------------------------------------------
GROUPS = {}
MATS = {}
IMAGES = {}
TILE = {}  # material -> tamanho da repetição da textura em metros
rng = random.Random(7)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights,
                 bpy.data.cameras):
        for item in list(coll):
            coll.remove(item)


def group(name):
    if name not in GROUPS:
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.2
        bpy.context.scene.collection.objects.link(e)
        GROUPS[name] = e
    return GROUPS[name]


def link(obj, grp):
    bpy.context.scene.collection.objects.link(obj)
    if grp:
        obj.parent = group(grp)
    return obj


def auto_uv(mesh, tile):
    """Projeção cúbica em metros: a textura repete a cada `tile` metros em qualquer face."""
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    uv = mesh.uv_layers.active.data
    verts = mesh.vertices
    for poly in mesh.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = verts[mesh.loops[li].vertex_index].co
            if ax == 2:
                u, v = co.x, co.y
            elif ax == 0:
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            uv[li].uv = (u / tile, v / tile)


def make_mesh(name, verts, faces, mat, grp, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    obj = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(MATS[mat])
        auto_uv(me, TILE.get(mat, 1.0))
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return link(obj, grp)


def B(name, x0, y0, z0, x1, y1, z1, mat, grp, bevel=0.0, seg=2):
    """Caixa alinhada aos eixos, de (x0,y0,z0) a (x1,y1,z1), em metros."""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = make_mesh(name, v, f, mat, grp)
    if bevel > 0:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = seg
        m.limit_method = "NONE"
        for p in obj.data.polygons:
            p.use_smooth = True
        try:
            obj.data.set_sharp_from_angle(angle=math.radians(40))
        except AttributeError:
            pass
    return obj


def C(name, cx, cy, z0, z1, r, mat, grp, seg=20, ry=None, r_top=None):
    """Cilindro vertical (ou tronco de cone se r_top for dado), elíptico se ry for dado."""
    ry = ry if ry is not None else r
    rt = r_top if r_top is not None else r
    rty = ry * rt / r if r else rt
    v = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((cx + r * math.cos(a), cy + ry * math.sin(a), z0))
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((cx + rt * math.cos(a), cy + rty * math.sin(a), z1))
    f = [tuple(range(seg - 1, -1, -1)), tuple(range(seg, 2 * seg))]
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, seg + j, seg + i))
    obj = make_mesh(name, v, f, mat, grp)
    for p in obj.data.polygons[2:]:
        p.use_smooth = True
    return obj


def ELL(name, cx, cy, cz, rx, ry, rz, mat, grp, seg=16, rings=10):
    v = [(cx, cy, cz - rz)]
    for j in range(1, rings):
        t = math.pi * j / rings
        for i in range(seg):
            a = 2 * math.pi * i / seg
            v.append((cx + rx * math.sin(t) * math.cos(a), cy + ry * math.sin(t) * math.sin(a), cz - rz * math.cos(t)))
    v.append((cx, cy, cz + rz))
    f = []
    for i in range(seg):
        f.append((0, 1 + (i + 1) % seg, 1 + i))
    for j in range(rings - 2):
        for i in range(seg):
            a = 1 + j * seg + i
            b = 1 + j * seg + (i + 1) % seg
            f.append((a, b, b + seg, a + seg))
    top = len(v) - 1
    base = 1 + (rings - 2) * seg
    for i in range(seg):
        f.append((base + i, base + (i + 1) % seg, top))
    return make_mesh(name, v, f, mat, grp, smooth=True)


def TUBE(name, pts, r, mat, grp, seg=10):
    """Tubo ao longo de uma polilinha (torneiras, hastes, cabideiros)."""
    from mathutils import Vector
    pts = [Vector(p) for p in pts]
    v, f = [], []
    for k, p in enumerate(pts):
        if k == 0:
            d = pts[1] - pts[0]
        elif k == len(pts) - 1:
            d = pts[-1] - pts[-2]
        else:
            d = (pts[k + 1] - pts[k]).normalized() + (pts[k] - pts[k - 1]).normalized()
        d.normalize()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        a = d.cross(up).normalized()
        b = d.cross(a).normalized()
        for i in range(seg):
            t = 2 * math.pi * i / seg
            v.append(tuple(p + r * (math.cos(t) * a + math.sin(t) * b)))
    for k in range(len(pts) - 1):
        for i in range(seg):
            j = (i + 1) % seg
            f.append((k * seg + i, k * seg + j, (k + 1) * seg + j, (k + 1) * seg + i))
    f.append(tuple(range(seg - 1, -1, -1)))
    n = len(pts) - 1
    f.append(tuple(n * seg + i for i in range(seg)))
    return make_mesh(name, v, f, mat, grp, smooth=True)


def PRISM(name, poly, z0, z1, mat, grp):
    """Extruda um polígono 2D (em metros) de z0 a z1."""
    pts = []
    for p in poly:
        if not pts or (abs(p[0] - pts[-1][0]) > 1e-6 or abs(p[1] - pts[-1][1]) > 1e-6):
            pts.append(p)
    if abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
        pts.pop()
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    if area < 0:
        pts.reverse()
    n = len(pts)
    v = [(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts]
    f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    return make_mesh(name, v, f, mat, grp)


def PANEL_X(name, x, y0, y1, z0, z1, t, mat, grp):
    """Placa fina em uma parede perpendicular a X (face em x, espessura t para +X se t>0)."""
    return B(name, x, y0, z0, x + t, y1, z1, mat, grp)


def rot_obj(obj, angle, pivot):
    """Gira o objeto em torno de Z passando por pivot (x, y), aplicando na malha."""
    from mathutils import Matrix
    T = Matrix.Translation((pivot[0], pivot[1], 0)) @ Matrix.Rotation(angle, 4, "Z") @ \
        Matrix.Translation((-pivot[0], -pivot[1], 0))
    obj.data.transform(T)
    obj.data.update()
    return obj


# ---------------------------------------------------------------------------------------------------
# Texturas geradas (numpy) e materiais
# ---------------------------------------------------------------------------------------------------
def vnoise(w, h, cx, cy, seed):
    g = np.random.default_rng(seed).random((cy + 1, cx + 1))
    g[:, -1] = g[:, 0]
    g[-1, :] = g[0, :]
    xs = np.linspace(0, cx, w, endpoint=False)
    ys = np.linspace(0, cy, h, endpoint=False)
    x0 = xs.astype(int)
    y0 = ys.astype(int)
    fx = xs - x0
    fy = ys - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = g[np.ix_(y0, x0)]
    b = g[np.ix_(y0, x0 + 1)]
    c = g[np.ix_(y0 + 1, x0)]
    d = g[np.ix_(y0 + 1, x0 + 1)]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(w, h, base, octaves, seed):
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += amp * vnoise(w, h, base * 2 ** o, base * 2 ** o, seed + o)
        tot += amp
        amp *= 0.5
    return out / tot


def make_image(name, rgb):
    """rgb: array (h, w, 3) em sRGB 0..1, linha 0 = topo."""
    h, w, _ = rgb.shape
    img = bpy.data.images.new(name, w, h, alpha=False)
    px = np.ones((h, w, 4), dtype=np.float32)
    px[:, :, :3] = np.clip(rgb[::-1], 0, 1)
    img.pixels.foreach_set(px.ravel())
    img.file_format = "JPEG"
    img.pack()
    IMAGES[name] = img
    return img


def build_textures():
    s = 512
    # Porcelanato polido creme, 90 x 90 cm, com veios suaves e rejunte fino
    n = fbm(s, s, 4, 5, 11)
    veins = np.abs(np.sin((np.linspace(0, 1, s)[None, :] * 3 + np.linspace(0, 1, s)[:, None] * 1.4 + n * 2.6)
                          * math.pi * 2))
    veins = np.clip(1 - veins * 7, 0, 1) * 0.06
    base = np.array([0.915, 0.872, 0.80])
    rgb = base[None, None, :] * (0.97 + 0.05 * n[:, :, None]) - veins[:, :, None] * np.array([0.6, 0.6, 0.55])
    g = 2
    rgb[:g, :, :] = rgb[-g:, :, :] = [0.80, 0.76, 0.70]
    rgb[:, :g, :] = rgb[:, -g:, :] = [0.80, 0.76, 0.70]
    make_image("tex_porcelanato", rgb)

    # Revestimento branco do banheiro (peças 60 x 120 deitadas): imagem 2:1
    n = fbm(512, 256, 3, 4, 21)
    rgb = np.ones((256, 512, 3)) * (0.935 + 0.03 * n[:, :, None])
    rgb[:2, :, :] = rgb[-2:, :, :] = 0.80
    rgb[:, :2, :] = rgb[:, -2:, :] = 0.80
    make_image("tex_azulejo", rgb)

    # Revestimento bege da cozinha (30 x 60, imagem 2:1)
    n = fbm(512, 256, 3, 4, 23)
    rgb = np.array([0.90, 0.84, 0.74])[None, None, :] * (0.96 + 0.06 * n[:, :, None])
    rgb[:2, :, :] = rgb[-2:, :, :] = [0.82, 0.76, 0.66]
    rgb[:, :2, :] = rgb[:, -2:, :] = [0.82, 0.76, 0.66]
    make_image("tex_rev_bege", rgb)

    # Madeira clara (freijó)
    n = fbm(256, 512, 3, 4, 31)
    y = np.linspace(0, 1, 256)[None, :]
    stripes = np.sin((y * 38 + n * 3.5) * math.pi * 2) * 0.5 + 0.5
    rgb = np.array([0.74, 0.56, 0.38])[None, None, :] * (0.86 + 0.12 * stripes[:, :, None] + 0.05 * n[:, :, None])
    make_image("tex_madeira", rgb)

    # Tapete: trama fina bege
    n = fbm(256, 256, 8, 3, 41)
    xx, yy = np.meshgrid(np.arange(256), np.arange(256))
    weave = ((xx // 3 + yy // 3) % 2) * 0.04
    rgb = np.array([0.74, 0.68, 0.60])[None, None, :] * (0.9 + 0.12 * n[:, :, None] + weave[:, :, None])
    make_image("tex_tapete", rgb)

    # Quadro com folha (traço marrom sobre papel creme)
    w, h = 240, 340
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.ones((h, w, 3)) * np.array([0.93, 0.89, 0.83])
    ink = np.array([0.55, 0.43, 0.33])
    cx = w / 2
    stem = (np.abs(xx - cx - (yy - h * 0.15) * 0.05) < 2.2) & (yy > h * 0.12) & (yy < h * 0.88)
    rgb[stem] = ink
    for k in range(7):
        yc = h * (0.22 + k * 0.095)
        for side in (-1, 1):
            ang = math.radians(35) * side
            lx = (xx - (cx + side * 26)) * math.cos(ang) + (yy - yc) * math.sin(ang)
            ly = -(xx - (cx + side * 26)) * math.sin(ang) + (yy - yc) * math.cos(ang)
            leaf = (lx / 30.0) ** 2 + (ly / 11.0) ** 2 < 1
            rgb[leaf] = rgb[leaf] * 0.25 + np.array([0.78, 0.69, 0.58]) * 0.75
            edge = ((lx / 30.0) ** 2 + (ly / 11.0) ** 2 < 1) & ((lx / 27.0) ** 2 + (ly / 8.5) ** 2 > 1)
            rgb[edge] = ink
    tip = ((xx - cx) / 12.0) ** 2 + ((yy - h * 0.13) / 22.0) ** 2 < 1
    rgb[tip] = np.array([0.78, 0.69, 0.58])
    make_image("tex_quadro", rgb)

    # Grama
    n = fbm(256, 256, 6, 5, 51)
    rgb = np.array([0.36, 0.50, 0.24])[None, None, :] * (0.75 + 0.45 * n[:, :, None])
    make_image("tex_grama", rgb)

    # Telha cerâmica (fileiras com ondas)
    xx, yy = np.meshgrid(np.linspace(0, 1, 256), np.linspace(0, 1, 256))
    wave = np.sin(xx * math.pi * 2 * 4) * 0.5 + 0.5
    rows = (yy * 6) % 1
    shade = 0.75 + 0.25 * wave - 0.25 * (rows > 0.9)
    n = fbm(256, 256, 4, 3, 61)
    rgb = np.array([0.66, 0.36, 0.24])[None, None, :] * (shade[:, :, None] * (0.9 + 0.15 * n[:, :, None]))
    make_image("tex_telha", rgb)

    # Concreto da calçada
    n = fbm(256, 256, 8, 5, 71)
    rgb = np.ones((256, 256, 3)) * (0.66 + 0.12 * n[:, :, None]) * np.array([1.0, 0.98, 0.95])
    rgb[:2, :, :] = rgb[:, :2, :] = 0.45
    make_image("tex_concreto", rgb)


def mat(name, color, rough=0.6, metal=0.0, alpha=1.0, emit=None, emit_strength=0.0, tex=None, tile=1.0,
        transmission=0.0, coat=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    col = tuple(c / 255 for c in bytes.fromhex(color[1:])) if isinstance(color, str) else color
    lin = tuple(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in col)
    bsdf.inputs["Base Color"].default_value = (*lin, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except AttributeError:
            m.blend_method = "BLEND"
    if emit:
        ec = tuple(c / 255 for c in bytes.fromhex(emit[1:]))
        ec = tuple(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in ec)
        bsdf.inputs["Emission Color"].default_value = (*ec, 1)
        bsdf.inputs["Emission Strength"].default_value = emit_strength
    if tex:
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = IMAGES[tex]
        node.location = (-400, 300)
        nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    m.use_backface_culling = False
    m.diffuse_color = (*lin, alpha)
    MATS[name] = m
    TILE[name] = tile
    return m


def build_materials():
    mat("Piso_Porcelanato", "#eadfcf", rough=0.12, tex="tex_porcelanato", tile=0.90, coat=0.3)
    mat("Parede", "#ece3d6", rough=0.85)
    mat("Parede_Bege", "#e3d6c4", rough=0.85)
    mat("Parede_Externa", "#efe9df", rough=0.9)
    mat("Corte_Parede", "#3b3631", rough=0.9)
    mat("Teto_Gesso", "#f6f2ec", rough=0.9)
    mat("Azulejo_Branco", "#f2f2f0", rough=0.15, tex="tex_azulejo", tile=1.20)
    mat("Piso_Banho", "#e8e6e2", rough=0.3, tex="tex_azulejo", tile=1.20)
    mat("Revestimento_Bege", "#e6dac7", rough=0.25, tex="tex_rev_bege", tile=0.60)
    mat("Marcenaria_Bege", "#c7b7a2", rough=0.55)
    mat("Marcenaria_Creme", "#e9e0d2", rough=0.45)
    mat("Marcenaria_Branca", "#efede8", rough=0.4)
    mat("Bancada_Creme", "#ece3d3", rough=0.18, coat=0.4)
    mat("Granito_Preto", "#232323", rough=0.3)
    mat("Inox", "#c9c9c7", rough=0.3, metal=0.65)
    mat("Inox_Escuro", "#7d7d7b", rough=0.35, metal=0.6)
    mat("Cromado", "#e6e6e6", rough=0.12, metal=0.75)
    mat("Metal_Dourado", "#c9a46a", rough=0.3, metal=0.6)
    mat("Vidro", "#dfe9ea", rough=0.02, alpha=0.18, transmission=1.0)
    mat("Vidro_Escuro", "#1a1c1e", rough=0.05, alpha=0.85)
    mat("Espelho", "#cdd5d6", rough=0.03, metal=0.55)
    mat("Aluminio_Preto", "#1f2022", rough=0.35, metal=0.6)
    mat("Aluminio_Branco", "#f2f1ee", rough=0.35, metal=0.1)
    mat("Porta_Branca", "#f1efea", rough=0.4)
    mat("Tecido_Bege", "#ddd0bf", rough=0.95)
    mat("Tecido_Areia", "#cdbca6", rough=0.95)
    mat("Tecido_Cinza", "#b9b2a8", rough=0.95)
    mat("Tecido_Marrom", "#8c7260", rough=0.95)
    mat("Tecido_Branco", "#f2eee7", rough=0.9)
    mat("Cortina", "#efe6d8", rough=0.95, alpha=0.88)
    mat("Madeira_Clara", "#b98b5c", rough=0.5, tex="tex_madeira", tile=0.8)
    mat("Tapete", "#bcae9b", rough=1.0, tex="tex_tapete", tile=0.5)
    mat("Louca_Branca", "#f7f7f5", rough=0.08)
    mat("Tela_TV", "#0b0c0d", rough=0.1)
    mat("Plastico_Preto", "#1b1b1c", rough=0.45)
    mat("Folha_Verde", "#4f7d3b", rough=0.6)
    mat("Folha_Escura", "#365f2e", rough=0.6)
    mat("Vaso_Branco", "#f1efea", rough=0.3)
    mat("Fibra_Natural", "#a98a63", rough=0.95)
    mat("Quadro_Folha", "#e8dfd2", rough=0.8, tex="tex_quadro", tile=1.0)
    mat("Livro_A", "#a7957f", rough=0.8)
    mat("Livro_B", "#e3d9c9", rough=0.8)
    mat("Livro_C", "#6f6155", rough=0.8)
    mat("LED", "#fff1dc", rough=0.5, emit="#ffd49a", emit_strength=12.0)
    mat("Luminaria", "#fff6e8", rough=0.5, emit="#ffe2b8", emit_strength=6.0)
    mat("Cupula", "#f3eadb", rough=0.9, emit="#ffd9a6", emit_strength=1.2)
    mat("Telha", "#a85c3e", rough=0.8, tex="tex_telha", tile=1.2)
    mat("Concreto", "#b8b3aa", rough=0.9, tex="tex_concreto", tile=1.0)
    mat("Grama", "#5f8540", rough=1.0, tex="tex_grama", tile=2.0)
    mat("Asfalto", "#4a4a4c", rough=0.95)
    mat("Muro", "#e4ddd2", rough=0.95)
    mat("Vizinho", "#e9e4dc", rough=0.95)
    mat("Vizinho_Esquadria", "#8f8a84", rough=0.4)


# ---------------------------------------------------------------------------------------------------
# Estrutura: paredes, vergas e peitoris, pisos, teto, telhado
# ---------------------------------------------------------------------------------------------------
# Aberturas: (nome, tipo, eixo, a0, a1, b0, b1, peitoril, topo) em pontos do PDF.
# eixo "h" = parede horizontal na planta (a = x, b = y); "v" = parede vertical (a = y, b = x).
OPENINGS = [
    ("PortaSala", "porta_vidro", "h", 66.0, 99.96, 529.92, 536.28, 0.0, DOOR_H),
    ("JanelaSala", "janela", "h", 107.4, 149.28, 529.92, 536.28, 1.00, DOOR_H),
    ("JanelaCoz1", "maxim_ar", "h", 198.0, 221.04, 529.92, 536.28, 1.05, DOOR_H),
    ("JanelaCoz2", "maxim_ar", "h", 235.8, 258.84, 529.92, 536.28, 1.05, DOOR_H),
    ("JanelaDorm1", "janela", "h", 88.44, 134.16, 159.6, 165.24, 1.10, DOOR_H),
    ("PortaDorm1", "porta", "v", 276.36, 306.6, 164.16, 169.92, 0.0, DOOR_H),
    ("PortaBanho", "porta", "v", 240.96, 271.2, 203.88, 209.52, 0.0, DOOR_H),
    ("JanelaBanho", "basculante", "v", 261.24, 291.84, 262.44, 268.08, 1.50, DOOR_H),
    ("PortaDorm2", "porta", "h", 171.84, 202.08, 348.48, 354.12, 0.0, DOOR_H),
    ("JanelaDorm2", "janela", "v", 372.84, 418.56, 288.96, 295.32, 1.10, DOOR_H),
    ("PortaCozinha", "porta_cozinha", "v", 458.04, 488.28, 288.96, 295.32, 0.0, DOOR_H),
]


def opening_box(op):
    _, _, ax, a0, a1, b0, b1, _, _ = op
    if ax == "h":
        (x0, y0), (x1, y1) = P(a0, b1), P(a1, b0)
    else:
        (x0, y0), (x1, y1) = P(b0, a1), P(b1, a0)
    return x0, y0, x1, y1


def build_structure():
    g = "Estrutura"
    for i, poly in enumerate(WALL_POLYS):
        PRISM(f"Parede_{i + 1:02d}", [P(*p) for p in poly], 0, H, "Parede", g)
        PRISM(f"CortePlanta_{i + 1:02d}", [P(*p) for p in poly], 0, 0.002, "Corte_Parede", "CorteParedes")
    # Parede de vedação da "previsão de ampliação" no fim da circulação
    x0, y0 = P(170.28, 238.56)
    x1, y1 = P(203.88, 232.92)
    B("Parede_Vedacao", x0, y0, 0, x1, y1, H, "Parede", g)
    B("CortePlanta_Vedacao", x0, y0, 0, x1, y1, 0.002, "Corte_Parede", "CorteParedes")
    # Vergas e peitoris
    for op in OPENINGS:
        name, kind, ax, *_r, sill, head = op
        x0, y0, x1, y1 = opening_box(op)
        B(f"Verga_{name}", x0, y0, head, x1, y1, H, "Parede", g)
        if sill > 0:
            B(f"Peitoril_{name}", x0, y0, 0, x1, y1, sill, "Parede", g)
            # pingadeira/soleira de granito claro
            B(f"Soleira_{name}", x0 - 0.02, y0 - 0.0, sill, x1 + 0.02, y1, sill + 0.02, "Bancada_Creme", g)
    # Viga sobre a lateral aberta da área de serviço
    x0, y0 = P(289.68, 324.0)
    x1, y1 = P(295.32, 238.56)
    B("Viga_Servico", x0, y0, H - 0.30, x1, y1, H, "Parede", g)

    # Piso
    fx0, fy0 = P(57.72, 536.28)
    fx1, fy1 = P(295.32, 232.92)
    B("Piso_Principal", fx0, fy0, -0.15, fx1, fy1, 0, "Piso_Porcelanato", g)
    rx1, ry1 = P(170.28, 159.6)
    B("Piso_Fundos", fx0, fy1, -0.15, rx1, ry1, 0, "Piso_Porcelanato", g)
    bx0, by0 = P(209.52, 324.0)
    bx1, by1 = P(262.44, 238.56)
    B("Piso_Banho", bx0, by0, 0, bx1, by1, 0.004, "Piso_Banho", g)
    sx0, sy0 = P(268.08, 324.0)
    sx1, sy1 = P(295.32, 238.56)
    B("Piso_Servico", sx0, sy0, 0, sx1, sy1, 0.004, "Piso_Banho", g)
    # soleiras nas portas internas
    for op in OPENINGS:
        if op[1] == "porta":
            x0, y0, x1, y1 = opening_box(op)
            B(f"SoleiraPorta_{op[0]}", x0, y0, 0, x1, y1, 0.006, "Bancada_Creme", g)

    # Revestimento do banheiro (paredes internas, até o teto)
    t = 0.008
    gb = "Estrutura"
    B("Azulejo_Banho_Fundo", bx0, by1 - t, 0, bx1, by1, H, "Azulejo_Branco", gb)
    B("Azulejo_Banho_Frente", bx0, by0, 0, bx1, by0 + t, H, "Azulejo_Branco", gb)
    # parede esquerda (com a porta): dois trechos
    dy0, dy1 = PYm(271.2), PYm(240.96)
    B("Azulejo_Banho_Esq1", bx0, by0, 0, bx0 + t, dy0, H, "Azulejo_Branco", gb)
    B("Azulejo_Banho_Esq2", bx0, dy1, 0, bx0 + t, by1, H, "Azulejo_Branco", gb)
    B("Azulejo_Banho_Esq3", bx0, dy0, DOOR_H, bx0 + t, dy1, H, "Azulejo_Branco", gb)
    # parede direita (com o basculante)
    wy0, wy1 = PYm(291.84), PYm(261.24)
    B("Azulejo_Banho_Dir1", bx1 - t, by0, 0, bx1, wy0, H, "Azulejo_Branco", gb)
    B("Azulejo_Banho_Dir2", bx1 - t, wy1, 0, bx1, by1, H, "Azulejo_Branco", gb)
    B("Azulejo_Banho_Dir3", bx1 - t, wy0, 0, bx1, wy1, 1.50, "Azulejo_Branco", gb)
    B("Azulejo_Banho_Dir4", bx1 - t, wy0, DOOR_H, bx1, wy1, H, "Azulejo_Branco", gb)
    # Área de serviço: revestimento até 1,50 m na parede do tanque
    B("Azulejo_Servico", sx0, sy1 - t, 0, sx1, sy1, 1.5, "Azulejo_Branco", gb)

    # Rodapé (porcelanato) nos ambientes secos: faixa de 7 cm pelas faces internas principais
    # (feito como caixas finas nas paredes mais visíveis)

    # Teto / laje
    gt = "Teto"
    B("Laje_Principal", fx0, fy0, H, fx1, fy1, TOP, "Teto_Gesso", gt)
    B("Laje_Fundos", fx0, fy1, H, rx1, ry1, TOP, "Teto_Gesso", gt)


def build_ceiling_details():
    """Sancas de gesso com LED, plafons quadrados e pontos de luz (empties para o visualizador)."""
    gt = "Teto"
    # Sala: sanca no perímetro do estar com fita LED voltada para as paredes
    sx0, sy0 = P(64.08, 529.92)
    sx1, sy1 = P(162.36, 314.52)
    drop = 0.12
    w = 0.30
    zc = H - drop
    # rebaixo em "moldura" (gesso), com o LED escondido no recorte
    B("Sanca_Sala_E", sx0, sy0, zc, sx0 + w, sy1, H, "Teto_Gesso", gt)
    B("Sanca_Sala_D", sx1 - w, sy0, zc, sx1, sy1, H, "Teto_Gesso", gt)
    B("LED_Sala_E", sx0 + w - 0.01, sy0 + 0.1, zc + 0.02, sx0 + w, sy1 - 0.1, zc + 0.05, "LED", gt)
    B("LED_Sala_D", sx1 - w, sy0 + 0.1, zc + 0.02, sx1 - w + 0.01, sy1 - 0.1, zc + 0.05, "LED", gt)
    # Dormitório 1: sanca ao longo da cortina (como na foto) e no perímetro
    dx0, dy0 = P(64.08, 308.88)
    dx1, dy1 = P(164.16, 165.24)
    B("Sanca_Dorm1_Fundo", dx0, dy1 - 0.32, zc, dx1, dy1, H, "Teto_Gesso", gt)
    B("LED_Dorm1_Cortina", dx0 + 0.05, dy1 - 0.33, zc + 0.02, dx1 - 0.05, dy1 - 0.32, zc + 0.06, "LED", gt)
    B("Sanca_Dorm1_Frente", dx0, dy0, zc, dx1, dy0 + 0.25, H, "Teto_Gesso", gt)
    B("Sanca_Dorm1_E", dx0, dy0, zc, dx0 + 0.25, dy1, H, "Teto_Gesso", gt)
    B("Sanca_Dorm1_D", dx1 - 0.25, dy0, zc, dx1, dy1, H, "Teto_Gesso", gt)
    B("LED_Dorm1_Frente", dx0 + 0.25, dy0 + 0.25, zc + 0.02, dx1 - 0.25, dy0 + 0.26, zc + 0.05, "LED", gt)
    # Banheiro: faixa de luz no teto sobre o espelho (como na foto)
    bx1 = PX(262.44)
    B("LED_Banho", bx1 - 0.10, PYm(320.0) + 0.0, H - 0.02, bx1 - 0.02, PYm(241.0), H - 0.005, "LED", gt)
    # Arandela externa ao lado da porta da sala (ponto de arandela da planta elétrica) - fica na fachada
    B("Arandela_Corpo", 0.04, -0.10, 2.02, 0.16, 0.0, 2.30, "Aluminio_Preto", "Estrutura")
    B("Arandela_Luz", 0.05, -0.105, 2.04, 0.15, -0.10, 2.28, "Luminaria", "Estrutura")
    # Plafons quadrados
    spots = {
        "Sala_Estar": (1.47, 4.25), "Sala_Jantar": (1.75, 1.55), "Cozinha": (4.45, 1.40),
        "Dorm1": (1.49, 7.75), "Dorm2": (4.55, 3.75), "Circulacao": (3.42, 6.40), "Banho": (4.55, 6.60),
        "Servico": (5.93, 6.60),
    }
    for k, (x, y) in spots.items():
        B(f"Plafon_{k}", x - 0.11, y - 0.11, H - 0.012, x + 0.11, y + 0.11, H, "Luminaria", gt)
    return spots


RIDGE_Y, RIDGE_Z = 4.60, 3.80


def gable_x(name, x0, x1, y0, y1, z, matname, grp):
    """Oitão: parede entre a laje (TOP) e o telhado, de y0 a y1, com espessura de x0 a x1."""
    ys = [y0, RIDGE_Y, y1] if y0 < RIDGE_Y < y1 else [y0, y1]
    top = [(y, z(y)) for y in ys]
    poly = [(y0, TOP), (y1, TOP)] + list(reversed(top))
    n = len(poly)
    v = [(x0, y, zz) for y, zz in poly] + [(x1, y, zz) for y, zz in poly]
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, n + i, n + j, j))
    return make_mesh(name, v, f, matname, grp)


def build_roof():
    gr = "Telhado"
    yr, zr, s = RIDGE_Y, RIDGE_Z, 0.18

    def z(y):
        return zr - s * abs(y - yr)

    xl, xr, xs = PX(57.72) - 0.0, PX(314.16), PX(189.12)
    yf, yb_r, yb_l = PYm(555.24), PYm(213.96), PYm(140.64)
    t = 0.07

    def slab_poly(name, pts):
        n = len(pts)
        v = [(x, y, z(y)) for x, y in pts] + [(x, y, z(y) + t) for x, y in pts]
        f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        for i in range(n):
            j = (i + 1) % n
            f.append((i, j, n + j, n + i))
        return make_mesh(name, v, f, "Telha", gr)

    slab_poly("Telhado_Frente", [(xl, yf), (xr, yf), (xr, yr), (xl, yr)])
    slab_poly("Telhado_Fundos", [(xl, yr), (xr, yr), (xr, yb_r), (xs, yb_r), (xs, yb_l), (xl, yb_l)])
    TUBE("Cumeeira", [(xl, yr, zr + t), (xr, yr, zr + t)], 0.07, "Telha", gr, seg=8)
    # Testeiras (acabamento branco nas bordas)
    B("Testeira_Frente", xl, yf - 0.03, z(yf) - 0.15, xr, yf, z(yf) + t, "Aluminio_Branco", gr)
    B("Testeira_Fundos_D", xs, yb_r, z(yb_r) - 0.15, xr, yb_r + 0.03, z(yb_r) + t, "Aluminio_Branco", gr)
    B("Testeira_Fundos_E", xl, yb_l, z(yb_l) - 0.15, xs, yb_l + 0.03, z(yb_l) + t, "Aluminio_Branco", gr)
    # Oitões: completam a alvenaria entre a laje e o telhado
    gable_x("Oitao_Esquerdo", PX(57.72), PX(64.08), PYm(536.28), PYm(159.6), z, "Parede_Externa", gr)
    gable_x("Oitao_Direito", PX(288.96), PX(295.32), PYm(536.28), PYm(232.92), z, "Parede_Externa", gr)
    gable_x("Oitao_Dorm1", PX(164.16), PX(170.28), PYm(232.92), PYm(159.6), z, "Parede_Externa", gr)
    B("Platibanda_Frente", PX(57.72), PYm(536.28), TOP, PX(295.32), PYm(529.92), z(PYm(536.28)), "Parede_Externa", gr)
    B("Platibanda_Fundos_D", PX(170.28), PYm(238.56), TOP, PX(295.32), PYm(232.92), z(PYm(232.92)),
      "Parede_Externa", gr)
    B("Platibanda_Fundos_E", PX(57.72), PYm(165.24), TOP, PX(170.28), PYm(159.6), z(PYm(159.6)) - 0.0,
      "Parede_Externa", gr)
    return z


def build_exterior(roof_z):
    ge = "Externo"
    W = PX(295.32)
    B("Grama", -7.5, -4.2, -0.17, 8.35, 12.5, -0.15, "Grama", ge)
    B("Calcada_Rua", -7.5, -5.6, -0.15, 8.35, -4.2, -0.10, "Concreto", ge)
    B("Rua", -7.5, -12.0, -0.30, 8.35, -5.6, -0.22, "Asfalto", ge)
    B("Guia", -7.5, -5.65, -0.30, 8.35, -5.55, -0.10, "Concreto", ge)
    B("Entrada_Garagem", 2.6, -4.2, -0.15, 8.2, 0.0, -0.04, "Concreto", ge)
    B("Caminho_Porta", 0.0, -4.2, -0.15, 2.6, 0.0, -0.04, "Concreto", ge)
    B("Corredor_Lateral", W, 0.0, -0.15, 8.2, 9.2, -0.04, "Concreto", ge)
    B("Calcada_Fundos", 0.0, PYm(159.6), -0.15, 3.4, 11.0, -0.04, "Concreto", ge)
    # Muro de divisa lateral e de fundos
    B("Muro_Lateral", 8.2, -4.2, -0.15, 8.35, 12.5, 1.9, "Muro", ge)
    B("Muro_Fundos", -7.5, 12.35, -0.15, 8.35, 12.5, 1.9, "Muro", ge)
    # Arbustos no jardim da frente
    for i, (x, y) in enumerate([(0.6, -3.6), (1.9, -3.7), (7.6, 0.6), (7.6, 3.0), (7.6, 5.4)]):
        ELL(f"Arbusto_{i}", x, y, 0.15, 0.38, 0.34, 0.42, "Folha_Escura", ge, seg=12, rings=8)
    # Casa geminada vizinha (espelhada, só volumetria)
    gv = "Vizinho"
    PRISM("Vizinho_Corpo", [(0, 0), (-W, 0), (-W, PYm(232.92)), (-PX(170.28), PYm(232.92)),
                            (-PX(170.28), PYm(159.6)), (0, PYm(159.6))], -0.15, TOP + 0.02, "Vizinho", gv)
    yr = 4.60
    for name, pts in (("Vizinho_Telhado_F", [(0, PYm(555.24)), (-PX(314.16), PYm(555.24)), (-PX(314.16), yr),
                                             (0, yr)]),
                      ("Vizinho_Telhado_T", [(0, yr), (-PX(314.16), yr), (-PX(314.16), PYm(213.96)),
                                             (-PX(189.12), PYm(213.96)), (-PX(189.12), PYm(140.64)),
                                             (0, PYm(140.64))])):
        n = len(pts)
        v = [(x, y, roof_z(y)) for x, y in pts] + [(x, y, roof_z(y) + 0.07) for x, y in pts]
        f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
        for i in range(n):
            j = (i + 1) % n
            f.append((i, n + i, n + j, j))
        make_mesh(name, v, f, "Telha", gv)
    gable_x("Vizinho_OitaoE", -PX(64.08), -PX(57.72) + 0.0, PYm(536.28), PYm(159.6), roof_z, "Vizinho", gv)
    gable_x("Vizinho_OitaoD", -W, -PX(288.96), PYm(536.28), PYm(232.92), roof_z, "Vizinho", gv)
    gable_x("Vizinho_OitaoT", -PX(170.28), -PX(164.16), PYm(232.92), PYm(159.6), roof_z, "Vizinho", gv)
    B("Vizinho_PlatF", -W, 0, TOP, 0, 0.15, roof_z(0.0), "Vizinho", gv)
    B("Vizinho_PlatT", -W, PYm(238.56), TOP, -PX(170.28), PYm(232.92), roof_z(PYm(232.92)), "Vizinho", gv)
    # janelas e porta escuras da vizinha (só sugestão)
    B("Vizinho_Porta", -1.12, -0.01, 0, -0.22, 0.0, DOOR_H, "Vizinho_Esquadria", gv)
    B("Vizinho_Janela", -2.41, -0.01, 1.0, -1.30, 0.0, DOOR_H, "Vizinho_Esquadria", gv)


# ---------------------------------------------------------------------------------------------------
# Esquadrias
# ---------------------------------------------------------------------------------------------------
def frame_rect(prefix, ax, a0, a1, z0, z1, b, t, prof, matname, grp):
    """Moldura retangular num plano. ax 'x': plano XZ em y=b (largura em x); 'y': plano YZ em x=b."""
    parts = [(a0, a1, z1 - prof, z1), (a0, a1, z0, z0 + prof), (a0, a0 + prof, z0, z1), (a1 - prof, a1, z0, z1)]
    out = []
    for i, (p0, p1, q0, q1) in enumerate(parts):
        if ax == "x":
            out.append(B(f"{prefix}_{i}", p0, b - t / 2, q0, p1, b + t / 2, q1, matname, grp))
        else:
            out.append(B(f"{prefix}_{i}", b - t / 2, p0, q0, b + t / 2, p1, q1, matname, grp))
    return out


def glass(prefix, ax, a0, a1, z0, z1, b, grp, matname="Vidro"):
    if ax == "x":
        return B(prefix, a0, b - 0.003, z0, a1, b + 0.003, z1, matname, grp)
    return B(prefix, b - 0.003, a0, z0, b + 0.003, a1, z1, matname, grp)


def build_openings():
    gq = "Esquadrias"
    for op in OPENINGS:
        name, kind, ax, a0p, a1p, b0p, b1p, sill, head = op
        x0, y0, x1, y1 = opening_box(op)
        if ax == "h":
            a0, a1, bmid = x0, x1, (y0 + y1) / 2
            axis = "x"
        else:
            a0, a1, bmid = y0, y1, (x0 + x1) / 2
            axis = "y"
        if kind in ("janela", "maxim_ar", "basculante"):
            pf = 0.045
            frame_rect(f"Caixilho_{name}", axis, a0, a1, sill + 0.02, head, bmid, 0.07, pf, "Aluminio_Branco", gq)
            if kind == "janela":
                mid = (a0 + a1) / 2
                # duas folhas de correr
                for k, (p0, p1, off) in enumerate(((a0 + pf, mid + 0.02, -0.018), (mid - 0.02, a1 - pf, 0.018))):
                    frame_rect(f"Folha_{name}_{k}", axis, p0, p1, sill + 0.02 + pf, head - pf, bmid + off, 0.03,
                               0.035, "Aluminio_Branco", gq)
                    glass(f"Vidro_{name}_{k}", axis, p0 + 0.03, p1 - 0.03, sill + pf + 0.05, head - pf - 0.03,
                          bmid + off, gq)
            else:
                glass(f"Vidro_{name}", axis, a0 + pf, a1 - pf, sill + 0.02 + pf, head - pf, bmid, gq)
                if kind == "maxim_ar":
                    zm = sill + 0.02 + (head - sill) * 0.5
                    if axis == "x":
                        B(f"Travessa_{name}", a0, bmid - 0.03, zm - 0.02, a1, bmid + 0.03, zm + 0.02,
                          "Aluminio_Branco", gq)
        elif kind == "porta":
            # batente branco
            frame_rect(f"Batente_{name}", axis, a0, a1, -0.5, head, bmid, (y1 - y0) if axis == "x" else (x1 - x0),
                       0.035, "Porta_Branca", gq)
        elif kind == "porta_cozinha":
            # porta de alumínio branca: vidro escuro em cima e venezianas em baixo (como na foto)
            t = 0.045
            frame_rect(f"Batente_{name}", axis, a0, a1, -0.5, head, bmid, 0.08, 0.04, "Aluminio_Branco", gq)
            p0, p1 = a0 + 0.04, a1 - 0.04
            frame_rect(f"Folha_{name}", axis, p0, p1, 0.0, head - 0.04, bmid, t, 0.06, "Aluminio_Branco", gq)
            B(f"FolhaTravessa_{name}", bmid - t / 2, p0, 1.12, bmid + t / 2, p1, 1.20, "Aluminio_Branco", gq)
            glass(f"Vidro_{name}", "y", p0 + 0.06, p1 - 0.06, 1.20, head - 0.10, bmid, gq, "Vidro_Escuro")
            for k in range(13):
                zz = 0.10 + k * 0.077
                B(f"Veneziana_{name}_{k}", bmid - 0.012, p0 + 0.06, zz, bmid + 0.012, p1 - 0.06, zz + 0.05,
                  "Aluminio_Branco", gq)
            C(f"Macaneta_{name}", bmid - 0.05, p0 + 0.10, 1.02, 1.05, 0.012, "Cromado", gq, seg=10)
            TUBE(f"Puxador_{name}", [(bmid - 0.05, p0 + 0.10, 1.04), (bmid - 0.05, p0 + 0.22, 1.04)], 0.01,
                 "Cromado", gq)
        elif kind == "porta_vidro":
            build_glass_door(name, a0, a1, y0, y1)

    # Folhas das portas internas, abertas como desenhado na planta
    leaf_t = 0.035
    # Dormitório 1: dobradiça em (164.16, 306.6), folha encostada na parede de baixo, para dentro do quarto
    hx, hy = P(164.16, 306.6)
    door_leaf("Folha_PortaDorm1", hx - 0.72, hy + 0.035, hx - 0.0, hy + 0.035 + leaf_t, "x", gq)
    # Banho: dobradiça em (209.52, 240.96), folha ao longo da parede do fundo do banheiro
    hx, hy = P(209.52, 240.96)
    door_leaf("Folha_PortaBanho", hx + 0.0, hy - 0.035 - leaf_t, hx + 0.72, hy - 0.035, "x", gq)
    # Dormitório 2: dobradiça em (171.84, 354.12), folha ao longo da parede esquerda do quarto
    hx, hy = P(171.84, 354.12)
    door_leaf("Folha_PortaDorm2", hx + 0.01, hy - 0.72, hx + 0.01 + leaf_t, hy, "y", gq)


def door_leaf(name, x0, y0, x1, y1, along, grp):
    B(name, x0, y0, 0.01, x1, y1, DOOR_H - 0.01, "Porta_Branca", grp)
    # maçaneta tipo alavanca (preto fosco)
    if along == "x":
        cx = x0 + 0.06 if name.endswith("Dorm1") else x1 - 0.06
        for s in (-1, 1):
            yy = (y0 + y1) / 2 + s * 0.035
            C(f"{name}_Roseta{s}", cx, yy, 1.0, 1.0001, 0.025, "Plastico_Preto", grp)
            B(f"{name}_Alavanca{s}", cx - 0.01 - (0.12 if name.endswith("Dorm1") else -0.0), yy - 0.01, 1.0,
              cx + 0.01 + (0.0 if name.endswith("Dorm1") else 0.12), yy + 0.01, 1.02, "Plastico_Preto", grp)
    else:
        cy = y0 + 0.06
        for s in (-1, 1):
            xx = (x0 + x1) / 2 + s * 0.035
            B(f"{name}_Alavanca{s}", xx - 0.01, cy, 1.0, xx + 0.01, cy + 0.12, 1.02, "Plastico_Preto", grp)


def build_glass_door(name, x0, x1, y0, y1):
    """Porta da sala: vidro temperado de correr, perfil de alumínio preto, trilho aparente pelo lado de dentro.

    O vão estrutural da planta tem 0,90 m (alvenaria estrutural não pode ser alterada), então a folha
    única de 1,00 m corre por dentro, sobre o trecho de parede ao lado e a janela.
    """
    g = "PortaVidro"
    yin = max(y0, y1)  # face interna da parede da fachada
    w = (x1 - x0) + 0.10
    lx0 = x0 - 0.05
    yl = yin + 0.035
    t = 0.03
    pf = 0.04
    leaf = []
    leaf += frame_rect("PortaVidro_Perfil", "x", lx0, lx0 + w, 0.01, DOOR_H + 0.04, yl, t, pf, "Aluminio_Preto",
                       None)
    leaf.append(glass("PortaVidro_Vidro", "x", lx0 + pf, lx0 + w - pf, 0.01 + pf, DOOR_H + 0.04 - pf, yl, None))
    leaf.append(B("PortaVidro_Puxador", lx0 + 0.07, yl + 0.02, 0.75, lx0 + 0.09, yl + 0.045, 1.35, "Aluminio_Preto",
                  None))
    leaf.append(B("PortaVidro_PuxadorExt", lx0 + 0.07, yl - 0.045, 0.75, lx0 + 0.09, yl - 0.02, 1.35,
                  "Aluminio_Preto", None))
    # junta tudo numa folha móvel (o visualizador anima o "abrir/fechar")
    for o in leaf:
        o.select_set(True)
    root = bpy.data.objects.new("PortaVidro_Folha", None)
    bpy.context.scene.collection.objects.link(root)
    root.parent = group(g)
    for o in leaf:
        o.parent = root
    root["anim"] = "correr"
    root["curso"] = round(x1 - x0, 3)
    # trilho aparente preto e guia no piso
    B("PortaVidro_Trilho", x0 - 0.08, yin + 0.005, DOOR_H + 0.04, x0 + 2 * (x1 - x0) + 0.25, yin + 0.07,
      DOOR_H + 0.10, "Aluminio_Preto", g)
    B("PortaVidro_Guia", x1 + 0.0, yin + 0.0, 0, x1 + 0.03, yin + 0.07, 0.03, "Aluminio_Preto", g)
    # moldura preta no vão (acabamento do requadro)
    frame_rect("PortaVidro_Requadro", "x", x0, x1, -0.5, DOOR_H, (y0 + y1) / 2, abs(y1 - y0), 0.02,
               "Aluminio_Preto", g)


# ---------------------------------------------------------------------------------------------------
# Mobiliário
# ---------------------------------------------------------------------------------------------------
def plant(prefix, x, y, z, grp, size=1.0, kind="bush", pot="Vaso_Branco"):
    if pot:
        C(f"{prefix}_Vaso", x, y, z, z + 0.12 * size, 0.07 * size, pot, grp, seg=16, r_top=0.085 * size)
        z += 0.12 * size
    if kind == "bush":
        for i in range(7):
            a = rng.random() * math.tau
            r = rng.random() * 0.05 * size
            ELL(f"{prefix}_Folha{i}", x + r * math.cos(a), y + r * math.sin(a), z + (0.04 + rng.random() * 0.08) * size,
                0.06 * size, 0.06 * size, 0.05 * size, "Folha_Verde" if i % 2 else "Folha_Escura", grp, seg=8,
                rings=5)
    elif kind == "palm":
        for i in range(9):
            a = i / 9 * math.tau + rng.random() * 0.3
            h = (0.9 + rng.random() * 0.6) * size
            tip = (x + math.cos(a) * 0.35 * size, y + math.sin(a) * 0.35 * size, z + h)
            mid = (x + math.cos(a) * 0.08 * size, y + math.sin(a) * 0.08 * size, z + h * 0.6)
            TUBE(f"{prefix}_Haste{i}", [(x, y, z), mid, tip], 0.006 * size, "Folha_Escura", grp, seg=5)
            # folíolos em leque
            for j in range(6):
                t = 0.45 + j * 0.1
                px = x + (tip[0] - x) * t
                py = y + (tip[1] - y) * t
                pz = z + h * (0.6 + 0.4 * t)
                for s in (-1, 1):
                    b = a + s * 1.2
                    TUBE(f"{prefix}_Fol{i}_{j}_{s}", [(px, py, pz), (px + math.cos(b) * 0.13 * size,
                                                                  py + math.sin(b) * 0.13 * size, pz - 0.05 * size)],
                         0.012 * size, "Folha_Verde", grp, seg=3)
    elif kind == "hanging":
        for i in range(10):
            a = i / 10 * math.tau
            pts = [(x, y, z + 0.04), (x + math.cos(a) * 0.12 * size, y + math.sin(a) * 0.12 * size, z + 0.05),
                   (x + math.cos(a) * 0.18 * size, y + math.sin(a) * 0.18 * size, z - 0.08 * size)]
            TUBE(f"{prefix}_Rama{i}", pts, 0.004, "Folha_Escura", grp, seg=4)
            for j, p in enumerate(pts[1:]):
                ELL(f"{prefix}_F{i}_{j}", p[0], p[1], p[2], 0.035 * size, 0.035 * size, 0.012 * size,
                    "Folha_Verde", grp, seg=6, rings=4)


def frame_art(prefix, wall, a, z0, w, h, grp, d=0.025, inward=+1):
    """Quadro com moldura de madeira numa parede perpendicular a X (wall = x da face)."""
    x = wall
    B(f"{prefix}_Moldura", x, a - w / 2, z0, x + inward * d, a + w / 2, z0 + h, "Madeira_Clara", grp)
    pic = B(f"{prefix}_Arte", x + inward * d, a - w / 2 + 0.03, z0 + 0.03, x + inward * (d + 0.002),
            a + w / 2 - 0.03, z0 + h - 0.03, "Quadro_Folha", grp)
    # UV: a arte inteira na face
    me = pic.data
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv[li].uv = ((co.y - (a - w / 2 + 0.03)) / (w - 0.06), (co.z - (z0 + 0.03)) / (h - 0.06))
    return pic


def chair(prefix, x, y, facing, grp):
    """Cadeira de jantar estofada (bege) com pés de madeira. facing: ângulo para onde o assento olha."""
    objs = []
    objs.append(B(f"{prefix}_Assento", x - 0.23, y - 0.23, 0.42, x + 0.23, y + 0.23, 0.50, "Tecido_Bege", grp,
                  bevel=0.025))
    objs.append(B(f"{prefix}_Encosto", x - 0.25, y - 0.23, 0.50, x - 0.18, y + 0.23, 0.95, "Tecido_Bege", grp,
                  bevel=0.03))
    for i, (dx, dy) in enumerate(((-0.19, -0.19), (0.19, -0.19), (-0.19, 0.19), (0.19, 0.19))):
        objs.append(C(f"{prefix}_Pe{i}", x + dx, y + dy, 0, 0.42, 0.017, "Madeira_Clara", grp, seg=8, r_top=0.02))
    for o in objs:
        rot_obj(o, facing, (x, y))


def build_sala():
    g = "Mob_Sala"
    wx0 = PX(64.08)            # parede do vizinho (face interna)
    wx1 = PX(162.36)           # parede do dormitório 2 (face da TV)
    # Sofá em L (assento voltado para a TV)
    sy0, sy1 = 2.72, 5.30
    B("Sofa_Base", wx0 + 0.02, sy0, 0.08, wx0 + 0.92, sy1, 0.40, "Tecido_Bege", g, bevel=0.03)
    B("Sofa_Encosto", wx0 + 0.02, sy0, 0.40, wx0 + 0.22, sy1 - 0.20, 0.80, "Tecido_Bege", g, bevel=0.05)
    B("Sofa_Braco", wx0 + 0.02, sy1 - 0.20, 0.40, wx0 + 0.92, sy1, 0.60, "Tecido_Bege", g, bevel=0.05)
    B("Sofa_Chaise", wx0 + 0.92, sy0, 0.08, wx0 + 1.62, sy0 + 0.80, 0.40, "Tecido_Bege", g, bevel=0.03)
    n = 3
    seg = (sy1 - 0.20 - sy0) / n
    for i in range(n):
        a = sy0 + i * seg
        B(f"Sofa_Assento{i}", wx0 + 0.22, a + 0.01, 0.40, wx0 + 0.90, a + seg - 0.01, 0.50, "Tecido_Bege", g,
          bevel=0.04)
        B(f"Sofa_Almofada{i}", wx0 + 0.20, a + 0.03, 0.50, wx0 + 0.38, a + seg - 0.03, 0.88, "Tecido_Bege", g,
          bevel=0.07, seg=3)
    B("Sofa_AssentoChaise", wx0 + 0.90, sy0 + 0.01, 0.40, wx0 + 1.60, sy0 + 0.79, 0.50, "Tecido_Bege", g,
      bevel=0.04)
    for i, yy in enumerate((3.2, 3.85, 4.5)):
        o = B(f"Sofa_Manta{i}", wx0 + 0.36, yy - 0.22, 0.50, wx0 + 0.50, yy + 0.22, 0.86, "Tecido_Areia", g,
              bevel=0.06, seg=3)
        rot_obj(o, 0.0, (0, 0))
    for i, (xx, yy) in enumerate(((wx0 + 0.07, sy0 + 0.07), (wx0 + 1.55, sy0 + 0.07), (wx0 + 0.07, sy1 - 0.07),
                                  (wx0 + 1.55, sy0 + 0.73), (wx0 + 0.85, sy1 - 0.07))):
        C(f"Sofa_Pe{i}", xx, yy, 0, 0.08, 0.025, "Madeira_Clara", g, seg=8)
    # Tapete
    B("Tapete_Sala", wx0 + 0.45, 2.55, 0.0, wx1 - 0.35, 5.35, 0.012, "Tapete", g)
    # Quadros (três folhas) acima do sofá
    for i, yy in enumerate((3.35, 3.98, 4.61)):
        frame_art(f"Quadro_Sala{i}", wx0, yy, 1.25, 0.46, 0.66, g)
    # Palmeira no canto
    plant("Palmeira", wx0 + 0.32, 5.58, 0.0, g, size=1.0, kind="palm", pot="Fibra_Natural")
    # Painel ripado com TV e LED nas bordas
    py0, py1 = 2.95, 4.75
    B("Painel_Fundo", wx1 - 0.02, py0, 0, wx1, py1, H, "Marcenaria_Creme", g)
    nr = 24
    step = (py1 - py0) / nr
    for i in range(nr):
        a = py0 + i * step
        B(f"Ripa_{i}", wx1 - 0.045, a + 0.012, 0.0, wx1 - 0.02, a + step - 0.012, H, "Marcenaria_Creme", g)
    B("LED_Painel_A", wx1 - 0.03, py0 - 0.02, 0.0, wx1 - 0.005, py0 - 0.005, H, "LED", g)
    B("LED_Painel_B", wx1 - 0.03, py1 + 0.005, 0.0, wx1 - 0.005, py1 + 0.02, H, "LED", g)
    B("TV_Corpo", wx1 - 0.09, 3.23, 0.86, wx1 - 0.05, 4.47, 1.58, "Plastico_Preto", g)
    B("TV_Tela", wx1 - 0.0905, 3.245, 0.875, wx1 - 0.0895, 4.455, 1.565, "Tela_TV", g)
    # Rack suspenso branco com tampo de madeira
    B("Rack", wx1 - 0.42, 3.0, 0.18, wx1 - 0.045, 4.70, 0.52, "Marcenaria_Branca", g)
    B("Rack_Tampo", wx1 - 0.43, 2.99, 0.52, wx1 - 0.045, 4.71, 0.55, "Madeira_Clara", g)
    B("Rack_Divisao", wx1 - 0.425, 3.85, 0.19, wx1 - 0.42, 3.851, 0.51, "Plastico_Preto", g)
    plant("Rack_Planta", wx1 - 0.22, 4.40, 0.55, g, size=1.0, kind="hanging")
    B("Rack_PortaRetrato", wx1 - 0.25, 3.25, 0.55, wx1 - 0.23, 3.42, 0.70, "Plastico_Preto", g)
    B("Rack_Difusor", wx1 - 0.30, 3.55, 0.55, wx1 - 0.25, 3.60, 0.66, "Vidro_Escuro", g)

    # Mesa de jantar (tampo branco brilhante, base de madeira) e 6 cadeiras
    cx, cy = 1.87, 1.58
    B("Mesa_Tampo", cx - 0.43, cy - 0.80, 0.72, cx + 0.43, cy + 0.80, 0.76, "Marcenaria_Branca", g, bevel=0.01)
    B("Mesa_Base1", cx - 0.30, cy - 0.55, 0.0, cx + 0.30, cy - 0.47, 0.72, "Madeira_Clara", g)
    B("Mesa_Base2", cx - 0.30, cy + 0.47, 0.0, cx + 0.30, cy + 0.55, 0.72, "Madeira_Clara", g)
    B("Mesa_Viga", cx - 0.04, cy - 0.55, 0.55, cx + 0.04, cy + 0.55, 0.62, "Madeira_Clara", g)
    C("Mesa_Sousplat", cx, cy, 0.76, 0.768, 0.17, "Fibra_Natural", g, seg=24)
    C("Mesa_Bowl", cx, cy, 0.768, 0.84, 0.07, "Vaso_Branco", g, seg=20, r_top=0.11)
    plant("Mesa_Planta", cx, cy, 0.80, g, size=1.1, kind="bush", pot=None)
    for i, yy in enumerate((cy - 0.52, cy, cy + 0.52)):
        chair(f"Cadeira_E{i}", cx - 0.62, yy, 0.0, g)
        chair(f"Cadeira_D{i}", cx + 0.62, yy, math.pi, g)


def build_cozinha():
    g = "Mob_Cozinha"
    x0 = PX(168.0)
    x1 = PX(288.96)
    yf = PYm(529.92)          # face interna da fachada
    yb = PYm(439.2)           # face da parede do dormitório 2
    # Geladeira inox (duas portas + freezer embaixo)
    gx0, gx1 = x0 + 0.02, x0 + 0.72
    B("Geladeira", gx0, yf + 0.02, 0.0, gx1, yf + 0.72, 1.86, "Inox", g, bevel=0.01)
    B("Geladeira_Junta", gx0 + 0.005, yf + 0.719, 0.70, gx1 - 0.005, yf + 0.723, 0.71, "Inox_Escuro", g)
    B("Geladeira_JuntaV", (gx0 + gx1) / 2 - 0.002, yf + 0.719, 0.71, (gx0 + gx1) / 2 + 0.002, yf + 0.723, 1.85,
      "Inox_Escuro", g)
    for s in (-1, 1):
        xm = (gx0 + gx1) / 2 + s * 0.04
        B(f"Geladeira_Puxador{s}", xm - 0.01, yf + 0.723, 0.95, xm + 0.01, yf + 0.75, 1.55, "Inox_Escuro", g)
    B("Geladeira_PuxadorFz", gx0 + 0.15, yf + 0.723, 0.60, gx1 - 0.15, yf + 0.75, 0.62, "Inox_Escuro", g)
    B("Geladeira_Painel", gx1 - 0.25, yf + 0.723, 1.40, gx1 - 0.20, yf + 0.726, 1.55, "Vidro_Escuro", g)
    # Armário sobre a geladeira
    B("Armario_SobreGeladeira", gx0 - 0.0, yf, 1.92, gx1, yf + 0.62, 2.40, "Marcenaria_Bege", g)

    # Bancada da fachada (com cuba e cooktop)
    bx0 = gx1 + 0.02
    bx1 = x1
    B("Rodape_Bancada", bx0, yf, 0.0, bx1, yf + 0.52, 0.10, "Plastico_Preto", g)
    # portas e gavetas bege com frisos
    xs = [bx0, bx0 + 0.45, 4.27, 4.77, 5.25, bx1]
    for i in range(len(xs) - 1):
        a, b = xs[i], xs[i + 1]
        if i == 0:
            B("LavaLoucas", a + 0.003, yf + 0.55, 0.10, b - 0.003, yf + 0.58, 0.86, "Inox", g)
            B("LavaLoucas_Painel", a + 0.01, yf + 0.58, 0.78, b - 0.01, yf + 0.585, 0.84, "Inox_Escuro", g)
            continue
        B(f"Gabinete_{i}", a, yf, 0.10, b, yf + 0.55, 0.88, "Marcenaria_Bege", g)
        if i in (3, 4):
            for k, (z0, z1) in enumerate(((0.10, 0.40), (0.41, 0.64), (0.65, 0.87))):
                B(f"Gaveta_{i}_{k}", a + 0.003, yf + 0.55, z0 + 0.003, b - 0.003, yf + 0.575, z1 - 0.003,
                  "Marcenaria_Bege", g)
        else:
            B(f"Porta_{i}", a + 0.003, yf + 0.55, 0.103, b - 0.003, yf + 0.575, 0.84, "Marcenaria_Bege", g)
    # tampo em pedra creme com recorte para a cuba
    sx0, sx1, sy0, sy1 = 4.30, 4.80, yf + 0.10, yf + 0.50
    B("Tampo_A", bx0, yf, 0.88, sx0, yf + 0.60, 0.92, "Bancada_Creme", g)
    B("Tampo_B", sx1, yf, 0.88, bx1, yf + 0.60, 0.92, "Bancada_Creme", g)
    B("Tampo_C", sx0, yf, 0.88, sx1, sy0, 0.92, "Bancada_Creme", g)
    B("Tampo_D", sx0, sy1, 0.88, sx1, yf + 0.60, 0.92, "Bancada_Creme", g)
    # cuba inox
    B("Cuba_Fundo", sx0, sy0, 0.70, sx1, sy1, 0.71, "Inox", g)
    B("Cuba_P1", sx0, sy0, 0.70, sx1, sy0 + 0.01, 0.92, "Inox", g)
    B("Cuba_P2", sx0, sy1 - 0.01, 0.70, sx1, sy1, 0.92, "Inox", g)
    B("Cuba_P3", sx0, sy0, 0.70, sx0 + 0.01, sy1, 0.92, "Inox", g)
    B("Cuba_P4", sx1 - 0.01, sy0, 0.70, sx1, sy1, 0.92, "Inox", g)
    # torneira gourmet
    tx, ty = (sx0 + sx1) / 2 + 0.12, yf + 0.06
    C("Torneira_Base", tx, ty, 0.92, 0.97, 0.03, "Cromado", g, seg=14)
    TUBE("Torneira_Bica", [(tx, ty, 0.95), (tx, ty, 1.30), (tx, ty + 0.06, 1.40), (tx, ty + 0.16, 1.40),
                           (tx, ty + 0.22, 1.32), (tx, ty + 0.22, 1.20)], 0.014, "Cromado", g)
    for k in range(10):
        C(f"Torneira_Mola{k}", tx, ty, 1.0 + k * 0.025, 1.012 + k * 0.025, 0.022, "Cromado", g, seg=12)
    # revestimento bege na parede da pia (entre bancada e janelas)
    B("Revestimento_Pia", bx0, yf, 0.92, bx1, yf + 0.006, 1.05, "Revestimento_Bege", g)
    # Cooktop 4 bocas
    cx0, cx1 = 5.35, 5.95
    B("Cooktop", cx0, yf + 0.08, 0.92, cx1, yf + 0.55, 0.93, "Vidro_Escuro", g)
    for k, (dx, dy) in enumerate(((0.15, 0.15), (0.45, 0.15), (0.15, 0.36), (0.45, 0.36))):
        C(f"Queimador_{k}", cx0 + dx, yf + 0.08 + dy, 0.93, 0.95, 0.045, "Plastico_Preto", g, seg=14)
        for s in range(4):
            a = s * math.pi / 2
            B(f"Trempe_{k}_{s}", cx0 + dx + math.cos(a) * 0.02 - 0.006, yf + 0.08 + dy + math.sin(a) * 0.02 - 0.006,
              0.95, cx0 + dx + math.cos(a) * 0.08 + 0.006, yf + 0.08 + dy + math.sin(a) * 0.08 + 0.006, 0.962,
              "Plastico_Preto", g)
    # Armários aéreos sobre o cooktop, coifa e LED
    ax0 = 5.38
    B("Aereo_Fachada", ax0, yf, 1.60, x1, yf + 0.36, 2.40, "Marcenaria_Bege", g)
    B("Coifa", 5.38, yf + 0.0, 1.52, 5.95, yf + 0.40, 1.60, "Inox", g)
    B("LED_AereoFachada", ax0 + 0.02, yf + 0.30, 1.515, x1 - 0.02, yf + 0.33, 1.52, "LED", g)
    B("Revestimento_Cooktop", ax0 - 0.05, yf, 0.92, x1, yf + 0.006, 1.60, "Revestimento_Bege", g)

    # Parede do fundo: torre quente (forno + micro-ondas), bancada e aéreos
    tx0, tx1 = x0 + 0.02, x0 + 0.68
    yb0 = yb - 0.60
    B("Torre", tx0, yb0, 0.0, tx1, yb, 2.40, "Marcenaria_Bege", g)
    B("Forno_Moldura", tx0 + 0.04, yb0 - 0.01, 0.78, tx1 - 0.04, yb0, 1.38, "Inox", g)
    B("Forno_Vidro", tx0 + 0.08, yb0 - 0.012, 0.84, tx1 - 0.08, yb0 - 0.01, 1.22, "Vidro_Escuro", g)
    B("Forno_Puxador", tx0 + 0.08, yb0 - 0.05, 1.26, tx1 - 0.08, yb0 - 0.03, 1.28, "Inox", g)
    B("Micro_Moldura", tx0 + 0.04, yb0 - 0.01, 1.42, tx1 - 0.04, yb0, 1.80, "Inox", g)
    B("Micro_Vidro", tx0 + 0.07, yb0 - 0.012, 1.46, tx1 - 0.20, yb0 - 0.01, 1.76, "Vidro_Escuro", g)
    B("Micro_Painel", tx1 - 0.17, yb0 - 0.012, 1.48, tx1 - 0.07, yb0 - 0.01, 1.74, "Inox_Escuro", g)
    for k, (z0, z1) in enumerate(((0.10, 0.44), (0.45, 0.76), (1.82, 2.38))):
        B(f"Torre_Frente{k}", tx0 + 0.003, yb0 - 0.02, z0, tx1 - 0.003, yb0, z1, "Marcenaria_Bege", g)
    bb0, bb1 = tx1, 5.20
    B("Rodape_Fundo", bb0, yb0 + 0.05, 0.0, bb1, yb, 0.10, "Plastico_Preto", g)
    nb = 3
    for i in range(nb):
        a = bb0 + (bb1 - bb0) * i / nb
        b = bb0 + (bb1 - bb0) * (i + 1) / nb
        B(f"GabFundo_{i}", a, yb0, 0.10, b, yb, 0.88, "Marcenaria_Bege", g)
        for k, (z0, z1) in enumerate(((0.10, 0.40), (0.41, 0.64), (0.65, 0.87))):
            B(f"GavFundo_{i}_{k}", a + 0.003, yb0 - 0.02, z0 + 0.003, b - 0.003, yb0, z1 - 0.003, "Marcenaria_Bege", g)
    B("Tampo_Fundo", bb0, yb0 - 0.02, 0.88, bb1, yb, 0.92, "Bancada_Creme", g)
    B("Revestimento_Fundo", bb0, yb - 0.006, 0.92, bb1, yb, 1.55, "Revestimento_Bege", g)
    B("Aereo_Fundo", bb0, yb - 0.36, 1.55, bb1, yb, 2.40, "Marcenaria_Bege", g)
    for i in range(4):
        a = bb0 + (bb1 - bb0) * i / 4
        b = bb0 + (bb1 - bb0) * (i + 1) / 4
        B(f"AereoFundo_Porta{i}", a + 0.003, yb - 0.38, 1.553, b - 0.003, yb - 0.36, 2.397, "Marcenaria_Bege", g)
    B("LED_AereoFundo", bb0 + 0.02, yb - 0.34, 1.545, bb1 - 0.02, yb - 0.31, 1.55, "LED", g)
    # Nichos de madeira com plantas (como na foto)
    B("Nicho_Madeira", bb1, yb - 0.36, 1.55, bb1 + 0.30, yb, 2.40, "Madeira_Clara", g)
    B("Nicho_Fundo", bb1 + 0.02, yb - 0.34, 1.57, bb1 + 0.28, yb - 0.005, 2.38, "Marcenaria_Creme", g)
    B("Nicho_Prateleira", bb1 + 0.02, yb - 0.34, 1.96, bb1 + 0.28, yb - 0.005, 1.98, "Madeira_Clara", g)
    plant("Nicho_Planta1", bb1 + 0.15, yb - 0.18, 1.57, g, size=0.8)
    plant("Nicho_Planta2", bb1 + 0.15, yb - 0.18, 1.98, g, size=0.7, kind="hanging")
    # objetos na bancada do fundo
    B("Tabua1", 4.80, yb - 0.10, 0.92, 5.05, yb - 0.08, 1.30, "Madeira_Clara", g, bevel=0.005)
    B("Tabua2", 4.95, yb - 0.13, 0.92, 5.15, yb - 0.11, 1.22, "Madeira_Clara", g, bevel=0.005)
    C("Pote_Utensilios", 4.55, yb - 0.18, 0.92, 1.06, 0.06, "Vaso_Branco", g, seg=16)
    for k in range(4):
        TUBE(f"Utensilio{k}", [(4.55 + (k - 1.5) * 0.015, yb - 0.18, 1.0), (4.55 + (k - 1.5) * 0.03, yb - 0.18 +
                                                                             (k % 2) * 0.02, 1.25)], 0.007,
             "Madeira_Clara", g, seg=5)
    plant("Bancada_Planta", 4.20, yb - 0.25, 0.92, g, size=0.9)
    C("Garrafa1", 3.95, yb - 0.15, 0.92, 1.12, 0.035, "Vidro", g, seg=12)
    C("Garrafa2", 3.85, yb - 0.12, 0.92, 1.08, 0.03, "Vaso_Branco", g, seg=12)
    # Passadeira
    B("Passadeira", 3.70, yf + 0.95, 0.0, 5.25, yb - 0.85, 0.01, "Tapete", g)


def build_dorm1():
    g = "Mob_Dorm1"
    x0, x1 = PX(64.08), PX(164.16)
    y0, y1 = PYm(308.88), PYm(165.24)
    cx = (x0 + x1) / 2
    # Cortinas do piso ao teto (voil) com ondas
    def curtain(name, xa, xb, yy, z0, z1, amp, wl, matname):
        nx = max(8, int((xb - xa) / 0.04))
        nz = 2
        v, f = [], []
        for j in range(nz):
            z = z0 + (z1 - z0) * j / (nz - 1)
            for i in range(nx + 1):
                x = xa + (xb - xa) * i / nx
                v.append((x, yy + amp * math.sin(x / wl * math.tau), z))
        for i in range(nx):
            f.append((i, i + 1, nx + 1 + i + 1, nx + 1 + i))
        o = make_mesh(name, v, f, matname, g, smooth=True)
        return o
    curtain("Cortina_Voil", x0 + 0.02, x1 - 0.02, y1 - 0.22, 0.01, H - 0.12, 0.035, 0.16, "Cortina")
    curtain("Cortina_Blackout", x0 + 0.02, x1 - 0.02, y1 - 0.12, 0.01, H - 0.12, 0.03, 0.22, "Tecido_Areia")
    B("Trilho_Cortina", x0, y1 - 0.26, H - 0.12, x1, y1 - 0.10, H - 0.10, "Aluminio_Branco", g)
    # Cama casal com cabeceira estofada em gomos verticais
    bw, bl = 1.70, 2.08
    hb = y1 - 0.27        # cabeceira encostada na cortina
    B("Cama_Base", cx - bw / 2, hb - bl, 0.10, cx + bw / 2, hb - 0.10, 0.42, "Tecido_Bege", g, bevel=0.04)
    for i, (dx, dy) in enumerate(((-1, 0), (1, 0))):
        C(f"Cama_Pe{i}", cx + dx * (bw / 2 - 0.08), hb - bl + 0.08, 0.0, 0.10, 0.03, "Madeira_Clara", g, seg=10,
          r_top=0.022)
    B("Cama_Colchao", cx - 0.80, hb - bl + 0.04, 0.42, cx + 0.80, hb - 0.12, 0.64, "Tecido_Branco", g, bevel=0.05)
    B("Cama_Edredom", cx - 0.83, hb - bl + 0.02, 0.50, cx + 0.83, hb - 0.55, 0.68, "Tecido_Bege", g, bevel=0.05)
    B("Cama_Peseira", cx - 0.86, hb - bl + 0.10, 0.52, cx + 0.86, hb - bl + 0.75, 0.71, "Tecido_Marrom", g,
      bevel=0.04)
    ng = 8
    gw = 1.80 / ng
    for i in range(ng):
        a = cx - 0.90 + i * gw
        B(f"Cabeceira_Gomo{i}", a + 0.004, hb - 0.10, 0.42, a + gw - 0.004, hb, 1.38, "Tecido_Bege", g, bevel=0.035,
          seg=3)
    B("Cabeceira_Base", cx - 0.90, hb - 0.08, 0.10, cx + 0.90, hb, 0.42, "Tecido_Bege", g)
    for i, s in enumerate((-1, 1)):
        xx = cx + s * 0.38
        B(f"Travesseiro{i}", xx - 0.36, hb - 0.42, 0.62, xx + 0.36, hb - 0.12, 0.88, "Tecido_Branco", g, bevel=0.07,
          seg=3)
        B(f"Almofada{i}", xx - 0.30, hb - 0.50, 0.62, xx + 0.30, hb - 0.32, 0.92, "Tecido_Marrom", g, bevel=0.07,
          seg=3)
    B("Almofada_Centro", cx - 0.25, hb - 0.62, 0.64, cx + 0.25, hb - 0.48, 0.86, "Tecido_Areia", g, bevel=0.06,
      seg=3)
    # Mesas de cabeceira com abajur
    for i, s in enumerate((-1, 1)):
        nx = cx + s * (bw / 2 + 0.25)
        B(f"CriadoMudo{i}", nx - 0.21, hb - 0.40, 0.25, nx + 0.21, hb - 0.02, 0.58, "Marcenaria_Creme", g, bevel=0.01)
        B(f"CriadoMudo{i}_Gaveta", nx - 0.19, hb - 0.405, 0.30, nx + 0.19, hb - 0.40, 0.52, "Marcenaria_Creme", g)
        C(f"CriadoMudo{i}_Puxador", nx, hb - 0.41, 0.41, 0.412, 0.012, "Metal_Dourado", g, seg=8)
        for k, (dx, dy) in enumerate(((-0.18, -0.37), (0.18, -0.37), (-0.18, -0.05), (0.18, -0.05))):
            C(f"CriadoMudo{i}_Pe{k}", nx + dx, hb + dy, 0.0, 0.25, 0.008, "Metal_Dourado", g, seg=6)
        C(f"Abajur{i}_Base", nx - 0.04, hb - 0.20, 0.58, 0.82, 0.055, "Vaso_Branco", g, seg=16, r_top=0.04)
        C(f"Abajur{i}_Cupula", nx - 0.04, hb - 0.20, 0.82, 1.02, 0.12, "Cupula", g, seg=20, r_top=0.10)
        plant(f"CriadoMudo{i}_Planta", nx + 0.12, hb - 0.28, 0.58, g, size=0.6)
    # Tapete sob a cama
    B("Tapete_Dorm1", cx - 1.05, hb - bl - 0.55, 0.0, cx + 1.05, hb - 0.45, 0.014, "Tapete", g)
    # Guarda-roupa na parede da frente (portas lisas bege)
    B("GuardaRoupa", x0, y0, 0.0, x0 + 1.80, y0 + 0.58, 2.40, "Marcenaria_Creme", g)
    for i in range(4):
        a = x0 + i * 0.45
        B(f"GuardaRoupa_Porta{i}", a + 0.003, y0 + 0.58, 0.003, a + 0.447, y0 + 0.60, 2.397, "Marcenaria_Creme", g)
        xx = a + (0.42 if i % 2 == 0 else 0.03)
        B(f"GuardaRoupa_Puxador{i}", xx - 0.006, y0 + 0.60, 0.9, xx + 0.006, y0 + 0.62, 1.5, "Metal_Dourado", g)
    # Cômoda e quadros na parede do vizinho
    B("Comoda", x0, 7.05, 0.10, x0 + 0.45, 7.95, 0.85, "Marcenaria_Creme", g, bevel=0.01)
    for k in range(3):
        B(f"Comoda_Gaveta{k}", x0 + 0.45, 7.07, 0.13 + k * 0.24, x0 + 0.46, 7.93, 0.34 + k * 0.24,
          "Marcenaria_Creme", g)
    C("Comoda_Vaso", x0 + 0.22, 7.25, 0.85, 1.00, 0.06, "Vaso_Branco", g, seg=14)
    plant("Comoda_Planta", x0 + 0.22, 7.25, 1.00, g, size=0.8, pot=None)
    B("Comoda_Bandeja", x0 + 0.10, 7.55, 0.85, x0 + 0.35, 7.85, 0.86, "Metal_Dourado", g)
    for i, yy in enumerate((7.05, 7.55, 8.05)):
        frame_art(f"Quadro_Dorm1_{i}", x0, yy, 1.25, 0.40, 0.56, g)
    # Ar-condicionado split
    ax = x1
    B("Split_Dorm1", ax - 0.20, 7.10, 2.18, ax, 7.95, 2.47, "Marcenaria_Branca", g, bevel=0.02)


def build_dorm2():
    g = "Mob_Dorm2"
    x0, x1 = PX(168.0), PX(288.96)
    y0, y1 = PYm(433.56), PYm(354.12)
    yt = PYm(329.64)
    xn = PX(209.52)
    # Escrivaninha sob a janela (parede direita)
    dx0, dx1 = x1 - 0.62, x1
    dy0, dy1 = 3.00, 4.45
    B("Mesa_Tampo", dx0, dy0, 0.72, dx1, dy1, 0.75, "Madeira_Clara", g)
    B("Mesa_Gaveteiro", dx0 + 0.02, dy0 + 0.02, 0.0, dx1 - 0.02, dy0 + 0.45, 0.72, "Marcenaria_Branca", g)
    for k in range(3):
        B(f"Mesa_Gaveta{k}", dx0 + 0.015, dy0 + 0.03, 0.03 + k * 0.23, dx0 + 0.02, dy0 + 0.44, 0.23 + k * 0.23,
          "Marcenaria_Branca", g)
    B("Mesa_Pe", dx0 + 0.04, dy1 - 0.06, 0.0, dx1 - 0.02, dy1 - 0.03, 0.72, "Marcenaria_Branca", g)
    # Monitor, teclado, luminária, planta
    mx = x1 - 0.18
    B("Monitor_Tela", mx - 0.025, 3.35, 1.00, mx, 3.97, 1.36, "Plastico_Preto", g)
    B("Monitor_Imagem", mx - 0.0255, 3.37, 1.02, mx - 0.025, 3.95, 1.34, "Tela_TV", g)
    B("Monitor_Haste", mx - 0.01, 3.64, 0.75, mx + 0.03, 3.68, 1.05, "Plastico_Preto", g)
    B("Monitor_Pe", mx - 0.10, 3.56, 0.75, mx + 0.08, 3.76, 0.76, "Plastico_Preto", g)
    B("Teclado", x1 - 0.45, 3.45, 0.75, x1 - 0.32, 3.87, 0.765, "Marcenaria_Branca", g)
    B("Mouse", x1 - 0.42, 3.98, 0.75, x1 - 0.36, 4.03, 0.77, "Marcenaria_Branca", g, bevel=0.008)
    C("Luminaria_Base", x1 - 0.14, 4.25, 0.75, 0.77, 0.06, "Metal_Dourado", g, seg=14)
    TUBE("Luminaria_Haste", [(x1 - 0.14, 4.25, 0.77), (x1 - 0.20, 4.25, 1.15), (x1 - 0.32, 4.25, 1.20)], 0.008,
         "Metal_Dourado", g)
    C("Luminaria_Cupula", x1 - 0.34, 4.25, 1.10, 1.20, 0.07, "Cupula", g, seg=14, r_top=0.03)
    plant("Mesa_Planta", x1 - 0.20, 3.12, 0.75, g, size=0.8)
    # Cadeira de escritório
    cx, cy = x1 - 0.85, 3.70
    C("Cadeira_Pistao", cx, cy, 0.08, 0.42, 0.025, "Inox_Escuro", g, seg=10)
    for k in range(5):
        a = k / 5 * math.tau
        TUBE(f"Cadeira_Pata{k}", [(cx, cy, 0.09), (cx + math.cos(a) * 0.30, cy + math.sin(a) * 0.30, 0.05)], 0.02,
             "Plastico_Preto", g, seg=6)
        ELL(f"Cadeira_Rodizio{k}", cx + math.cos(a) * 0.30, cy + math.sin(a) * 0.30, 0.03, 0.03, 0.03, 0.03,
            "Plastico_Preto", g, seg=8, rings=5)
    B("Cadeira_Assento", cx - 0.25, cy - 0.25, 0.42, cx + 0.25, cy + 0.25, 0.50, "Tecido_Cinza", g, bevel=0.03)
    B("Cadeira_Encosto", cx - 0.32, cy - 0.23, 0.55, cx - 0.25, cy + 0.23, 1.05, "Tecido_Cinza", g, bevel=0.03)
    B("Cadeira_Suporte", cx - 0.30, cy - 0.03, 0.45, cx - 0.26, cy + 0.03, 0.60, "Plastico_Preto", g)
    # Sofá-cama na parede da frente (y0), voltado para os fundos
    sx0, sx1 = x0 + 0.10, x0 + 2.00
    B("SofaCama_Base", sx0, y0, 0.10, sx1, y0 + 0.85, 0.42, "Tecido_Areia", g, bevel=0.03)
    B("SofaCama_Encosto", sx0, y0, 0.42, sx1, y0 + 0.20, 0.82, "Tecido_Areia", g, bevel=0.05)
    B("SofaCama_BracoE", sx0, y0, 0.42, sx0 + 0.15, y0 + 0.85, 0.62, "Tecido_Areia", g, bevel=0.04)
    B("SofaCama_BracoD", sx1 - 0.15, y0, 0.42, sx1, y0 + 0.85, 0.62, "Tecido_Areia", g, bevel=0.04)
    for k in range(2):
        a = sx0 + 0.15 + k * 0.80
        B(f"SofaCama_Assento{k}", a + 0.01, y0 + 0.20, 0.42, a + 0.79, y0 + 0.84, 0.52, "Tecido_Areia", g, bevel=0.04)
        B(f"SofaCama_Almofada{k}", a + 0.20, y0 + 0.18, 0.52, a + 0.60, y0 + 0.34, 0.84, "Tecido_Bege", g, bevel=0.06,
          seg=3)
    for k, xx in enumerate((sx0 + 0.06, sx1 - 0.06)):
        for kk, yy in enumerate((y0 + 0.06, y0 + 0.79)):
            C(f"SofaCama_Pe{k}{kk}", xx, yy, 0.0, 0.10, 0.02, "Madeira_Clara", g, seg=8)
    # Quadros acima do sofá-cama (parede da frente, perpendicular a Y)
    for i, xx in enumerate((x0 + 0.65, x0 + 1.45)):
        art = B(f"Quadro_Dorm2_{i}_Moldura", xx - 0.25, y0, 1.25, xx + 0.25, y0 + 0.025, 1.95, "Madeira_Clara", g)
        pic = B(f"Quadro_Dorm2_{i}_Arte", xx - 0.22, y0 + 0.025, 1.28, xx + 0.22, y0 + 0.027, 1.92, "Quadro_Folha", g)
        me = pic.data
        uvl = me.uv_layers.active.data
        for poly in me.polygons:
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                uvl[li].uv = ((co.x - (xx - 0.22)) / 0.44, (co.z - 1.28) / 0.64)
    # Estante no nicho do fundo (parede de cima)
    ex0, ex1 = xn + 0.10, x1 - 0.10
    B("Estante_Lateral1", ex0, yt - 0.34, 0.0, ex0 + 0.03, yt, 2.10, "Madeira_Clara", g)
    B("Estante_Lateral2", ex1 - 0.03, yt - 0.34, 0.0, ex1, yt, 2.10, "Madeira_Clara", g)
    B("Estante_Fundo", ex0, yt - 0.02, 0.0, ex1, yt, 2.10, "Marcenaria_Creme", g)
    books = ["Livro_A", "Livro_B", "Livro_C"]
    for k, z in enumerate((0.0, 0.42, 0.84, 1.26, 1.68, 2.07)):
        B(f"Estante_Prat{k}", ex0, yt - 0.34, z, ex1, yt, z + 0.03, "Madeira_Clara", g)
        if k >= 5:
            continue
        xx = ex0 + 0.06
        while xx < ex1 - 0.35:
            if rng.random() < 0.25:
                xx += 0.12
                continue
            bw_ = 0.025 + rng.random() * 0.025
            bh = 0.22 + rng.random() * 0.12
            B(f"Livro_{k}_{xx:.2f}", xx, yt - 0.30, z + 0.03, xx + bw_, yt - 0.06, z + 0.03 + bh, rng.choice(books), g)
            xx += bw_ + 0.003
        plant(f"Estante_Planta{k}", ex1 - 0.18, yt - 0.18, z + 0.03, g, size=0.6,
              kind="hanging" if k % 2 else "bush")
    # Tapete e luminária de piso
    B("Tapete_Dorm2", x0 + 0.40, y0 + 0.95, 0.0, x1 - 0.95, y1 - 0.10, 0.012, "Tapete", g)
    C("Luminaria_Piso_Base", x0 + 0.22, y0 + 1.05, 0.0, 0.02, 0.14, "Metal_Dourado", g, seg=16)
    C("Luminaria_Piso_Haste", x0 + 0.22, y0 + 1.05, 0.02, 1.45, 0.012, "Metal_Dourado", g, seg=8)
    C("Luminaria_Piso_Cupula", x0 + 0.22, y0 + 1.05, 1.40, 1.65, 0.20, "Cupula", g, seg=20, r_top=0.16)
    plant("Dorm2_PlantaPiso", x1 - 0.30, y0 + 0.30, 0.0, g, size=1.6, kind="bush", pot="Fibra_Natural")
    # Ar-condicionado split na parede do fundo
    B("Split_Dorm2", 4.40, yt - 0.20, 2.18, 5.25, yt, 2.47, "Marcenaria_Branca", g, bevel=0.02)


def build_banho():
    g = "Mob_Banho"
    x0, x1 = PX(209.52) + 0.008, PX(262.44) - 0.008
    y0, y1 = PYm(324.0) + 0.008, PYm(238.56) - 0.008
    # Bancada preta suspensa (com saia) e prateleira
    vy0 = 7.20
    B("Bancada_Tampo", x1 - 0.46, vy0, 0.80, x1, y1, 0.84, "Granito_Preto", g)
    B("Bancada_Saia", x1 - 0.46, vy0, 0.62, x1 - 0.43, y1, 0.84, "Granito_Preto", g)
    B("Bancada_SaiaLat", x1 - 0.46, vy0, 0.62, x1, vy0 + 0.03, 0.84, "Granito_Preto", g)
    B("Bancada_Prateleira", x1 - 0.42, vy0, 0.26, x1, y1, 0.29, "Granito_Preto", g)
    C("Cuba_Apoio", x1 - 0.22, (vy0 + y1) / 2, 0.84, 0.99, 0.17, "Louca_Branca", g, seg=28)
    C("Cuba_Interior", x1 - 0.22, (vy0 + y1) / 2, 0.86, 0.991, 0.15, "Louca_Branca", g, seg=28)
    TUBE("Torneira_Banho", [(x1 - 0.03, (vy0 + y1) / 2, 0.84), (x1 - 0.03, (vy0 + y1) / 2, 1.18),
                            (x1 - 0.12, (vy0 + y1) / 2, 1.20), (x1 - 0.16, (vy0 + y1) / 2, 1.12)], 0.012, "Cromado", g)
    C("Sifao", x1 - 0.22, (vy0 + y1) / 2, 0.29, 0.62, 0.02, "Cromado", g, seg=10)
    # bandeja, difusor, orquídea
    B("Bandeja_Banho", x1 - 0.30, vy0 + 0.02, 0.84, x1 - 0.06, vy0 + 0.20, 0.85, "Plastico_Preto", g)
    C("Difusor", x1 - 0.18, vy0 + 0.10, 0.85, 1.02, 0.03, "Vidro_Escuro", g, seg=12)
    TUBE("Orquidea_Haste", [(x1 - 0.12, vy0 + 0.10, 0.85), (x1 - 0.13, vy0 + 0.12, 1.10), (x1 - 0.18, vy0 + 0.16,
                                                                                         1.20)], 0.004,
         "Folha_Escura", g, seg=5)
    for k in range(5):
        ELL(f"Orquidea_Flor{k}", x1 - 0.13 - k * 0.012, vy0 + 0.11 + k * 0.01, 1.06 + k * 0.03, 0.025, 0.025, 0.012,
            "Louca_Branca", g, seg=8, rings=4)
    # cesto com rolos e planta na prateleira
    B("Cesto", x1 - 0.30, vy0 + 0.25, 0.29, x1 - 0.06, y1 - 0.03, 0.37, "Plastico_Preto", g)
    for k in range(3):
        C(f"Rolo{k}", x1 - 0.18, vy0 + 0.30 + k * 0.08, 0.37, 0.47, 0.04, "Tecido_Branco", g, seg=12)
    plant("Banho_Planta", x1 - 0.20, vy0 + 0.08, 0.29, g, size=0.8, pot="Fibra_Natural")
    # Espelho (sobre a bancada)
    B("Espelho", x1 - 0.012, vy0 + 0.07, 1.05, x1, y1 - 0.02, 2.0, "Espelho", g)
    # Bacia com caixa acoplada (encostada na parede direita, voltada para a esquerda)
    ty = PYm(280.5)
    B("Bacia_Caixa", x1 - 0.18, ty - 0.19, 0.40, x1, ty + 0.19, 0.78, "Louca_Branca", g, bevel=0.02)
    C("Bacia_Corpo", x1 - 0.40, ty, 0.0, 0.40, 0.17, "Louca_Branca", g, seg=24, ry=0.18, r_top=0.20)
    B("Bacia_Base", x1 - 0.30, ty - 0.17, 0.0, x1 - 0.12, ty + 0.17, 0.40, "Louca_Branca", g, bevel=0.03)
    C("Bacia_Tampa", x1 - 0.40, ty, 0.40, 0.43, 0.20, "Louca_Branca", g, seg=24, ry=0.18)
    C("Bacia_Botao", x1 - 0.09, ty, 0.78, 0.79, 0.025, "Cromado", g, seg=12)
    C("Papeleira", x1 - 0.06, ty - 0.30, 0.65, 0.66, 0.06, "Tecido_Branco", g, seg=14)
    C("Lixeira", x1 - 0.12, ty + 0.30, 0.0, 0.28, 0.10, "Inox", g, seg=18)
    # Box de vidro do chuveiro
    yb = PYm(296.0)
    B("Box_Perfil", x0, yb - 0.01, 0.0, x1, yb + 0.01, 0.03, "Aluminio_Branco", g)
    B("Box_PerfilSup", x0, yb - 0.01, 1.92, x1, yb + 0.01, 1.95, "Aluminio_Branco", g)
    B("Box_Vidro1", x0 + 0.01, yb - 0.004, 0.03, (x0 + x1) / 2 + 0.05, yb + 0.004, 1.92, "Vidro", g)
    B("Box_Vidro2", (x0 + x1) / 2 - 0.05, yb + 0.006, 0.03, x1 - 0.01, yb + 0.014, 1.92, "Vidro", g)
    C("Box_Puxador", (x0 + x1) / 2 - 0.02, yb + 0.02, 0.9, 1.1, 0.01, "Cromado", g, seg=8)
    # Chuveiro elétrico e registro
    sy = PYm(308.0)
    TUBE("Chuveiro_Cano", [(x1, sy, 2.10), (x1 - 0.25, sy, 2.12)], 0.012, "Louca_Branca", g, seg=8)
    C("Chuveiro", x1 - 0.30, sy, 1.98, 2.12, 0.08, "Louca_Branca", g, seg=18, r_top=0.06)
    B("Registro", x1 - 0.02, sy - 0.05, 1.05, x1, sy + 0.05, 1.15, "Cromado", g)
    # Ralo linear
    B("Ralo", x0 + 0.1, y0 + 0.08, 0.004, x1 - 0.1, y0 + 0.12, 0.006, "Inox", g)
    # Toalheiro
    TUBE("Toalheiro", [(x0, 6.05, 1.25), (x0 + 0.06, 6.05, 1.25), (x0 + 0.06, 6.55, 1.25), (x0, 6.55, 1.25)],
         0.008, "Cromado", g, seg=6)
    B("Toalha", x0 + 0.03, 6.10, 0.85, x0 + 0.08, 6.50, 1.27, "Tecido_Areia", g, bevel=0.01)


def build_servico():
    g = "Mob_Servico"
    x0, x1 = PX(268.08), PX(295.32)
    y0, y1 = PYm(324.0), PYm(238.56)
    # Tanque
    B("Tanque", x0 + 0.02, y1 - 0.55, 0.62, x1 - 0.02, y1, 0.90, "Louca_Branca", g, bevel=0.02)
    C("Tanque_Coluna", (x0 + x1) / 2, y1 - 0.20, 0.0, 0.62, 0.10, "Louca_Branca", g, seg=16)
    TUBE("Tanque_Torneira", [((x0 + x1) / 2, y1 - 0.01, 1.05), ((x0 + x1) / 2, y1 - 0.12, 1.05),
                             ((x0 + x1) / 2, y1 - 0.12, 0.98)], 0.01, "Cromado", g, seg=8)
    # Máquina de lavar
    mx0, mx1 = x0 + 0.04, x1 - 0.04
    B("Lavadora", mx0, y1 - 1.25, 0.0, mx1, y1 - 0.60, 0.95, "Marcenaria_Branca", g, bevel=0.015)
    C("Lavadora_Tampa", (mx0 + mx1) / 2, y1 - 0.92, 0.95, 0.955, 0.24, "Vidro_Escuro", g, seg=24)
    B("Lavadora_Painel", mx0, y1 - 0.70, 0.95, mx1, y1 - 0.60, 1.05, "Marcenaria_Branca", g)
    # Prateleira e varal de teto
    B("Prateleira_Servico", x0, y1 - 0.30, 1.60, x1, y1, 1.62, "Madeira_Clara", g)
    for k in range(3):
        C(f"Produto{k}", x0 + 0.15 + k * 0.18, y1 - 0.15, 1.62, 1.85, 0.04, "Vaso_Branco" if k % 2 else "Livro_A", g,
          seg=12)
    for k in range(4):
        xx = x0 + 0.12 + k * 0.14
        TUBE(f"Varal{k}", [(xx, y0 + 0.15, 2.35), (xx, y1 - 1.35, 2.35)], 0.006, "Aluminio_Branco", g, seg=6)


# ---------------------------------------------------------------------------------------------------
# Rótulos, vistas, luzes e câmeras
# ---------------------------------------------------------------------------------------------------
def room_info():
    out = []
    for key, r in ROOMS.items():
        area = 0.0
        cx = cy = 0.0
        for (a, b, c, d) in r["rects"]:
            (x0, y0), (x1, y1) = P(a, d), P(c, b)
            ar = abs(x1 - x0) * abs(y1 - y0)
            area += ar
            cx += (x0 + x1) / 2 * ar
            cy += (y0 + y1) / 2 * ar
        out.append({"id": key, "nome": r["nome"], "area": round(area, 2), "x": round(cx / area, 3),
                    "y": round(cy / area, 3)})
    return out


LABEL_POS = {"sala": (1.45, 3.9), "cozinha": (4.5, 1.25), "dorm1": (1.49, 8.0), "dorm2": (4.4, 3.75),
             "banho": (4.7, 6.6), "servico": (5.93, 6.1), "circ": (3.42, 6.6)}

# Vistas: posição da câmera e ponto de mira (metros). Usadas no visualizador web e nos renders.
VIEWS = [
    {"id": "geral", "nome": "Visão geral", "pos": [10.5, -7.5, 11.0], "alvo": [3.1, 4.6, 0.4], "lente": 30,
     "corte": True},
    {"id": "planta", "nome": "Planta", "pos": [3.15, 4.85, 17.0], "alvo": [3.15, 4.86, 0.0], "lente": 35,
     "corte": True},
    {"id": "fachada", "nome": "Fachada", "pos": [8.6, -9.5, 2.3], "alvo": [2.6, 2.5, 1.6], "lente": 28,
     "corte": False, "telhado": True},
    {"id": "sala", "nome": "Sala", "pos": [2.55, 0.45, 1.55], "alvo": [0.9, 4.6, 1.0], "lente": 18,
     "corte": False, "teto": True},
    {"id": "jantar", "nome": "Jantar", "pos": [2.35, 5.55, 1.62], "alvo": [1.2, 0.6, 0.85], "lente": 18,
     "corte": False, "teto": True},
    {"id": "cozinha", "nome": "Cozinha", "pos": [2.55, 1.45, 1.55], "alvo": [6.1, 1.25, 1.1], "lente": 17,
     "corte": False, "teto": True},
    {"id": "dorm1", "nome": "Dormitório 01", "pos": [2.55, 6.35, 1.60], "alvo": [1.1, 9.7, 0.9], "lente": 17,
     "corte": False, "teto": True},
    {"id": "dorm2", "nome": "Home office", "pos": [3.25, 4.65, 1.55], "alvo": [6.1, 2.9, 0.9], "lente": 17,
     "corte": False, "teto": True},
    {"id": "banho", "nome": "Banheiro", "pos": [4.07, 6.80, 1.55], "alvo": [5.41, 6.80, 1.05], "lente": 14,
     "corte": False, "teto": True},
]

LIGHTS = [  # pontos de luz quentes (x, y, z, potência relativa)
    ("Sala_Estar", 1.47, 4.25, 2.35, 1.0), ("Sala_Jantar", 1.80, 1.55, 2.35, 0.9), ("Cozinha", 4.45, 1.40, 2.35, 1.0),
    ("Dorm1", 1.49, 7.75, 2.35, 0.8), ("Dorm2", 4.55, 3.75, 2.35, 0.8), ("Circulacao", 3.42, 6.40, 2.35, 0.5),
    ("Banho", 4.55, 6.60, 2.35, 0.6), ("Servico", 5.93, 6.60, 2.35, 0.4),
    ("Arandela", 0.10, -0.35, 2.05, 0.6),
]


def build_meta():
    rooms = room_info()
    for r in rooms:
        lx, ly = LABEL_POS[r["id"]]
        e = bpy.data.objects.new(f"Rotulo_{r['id']}", None)
        bpy.context.scene.collection.objects.link(e)
        e.parent = group("Rotulos")
        e.location = (lx, ly, 1.0)
        e["rotulo"] = r["nome"]
        e["area"] = r["area"]
    for name, x, y, z, p in LIGHTS:
        e = bpy.data.objects.new(f"Luz_{name}", None)
        bpy.context.scene.collection.objects.link(e)
        e.parent = group("Luzes")
        e.location = (x, y, z)
        e["potencia"] = p
    total = sum(r["area"] for r in rooms)
    W = PX(295.32)
    meta = {
        "titulo": "Casa Jardim Primavera",
        "subtitulo": "2 dormitórios · lado esquerdo",
        "escala": "1:75",
        "peDireito": H,
        "areaUtil": round(total, 2),
        "areaConstruida": round(W * PYm(232.92) + PX(170.28) * (PYm(159.6) - PYm(232.92)), 2),
        "dimensoes": [round(W, 2), round(PYm(159.6), 2)],
        "comodos": rooms,
        "vistas": VIEWS,
    }
    bpy.context.scene["casa"] = json.dumps(meta, ensure_ascii=False)
    return meta


def blender_lights_and_cameras():
    """Luzes reais para o Cycles (não vão para o GLB) e câmeras das vistas."""
    scn = bpy.context.scene
    for name, x, y, z, p in LIGHTS:
        ld = bpy.data.lights.new(f"Area_{name}", "AREA")
        ld.energy = 55 * p
        ld.size = 0.22
        ld.color = (1.0, 0.80, 0.58)
        o = bpy.data.objects.new(f"Area_{name}", ld)
        o.location = (x, y, H - 0.02)
        scn.collection.objects.link(o)
    for i, s in enumerate((-1, 1)):
        ld = bpy.data.lights.new(f"Abajur_{i}", "POINT")
        ld.energy = 14
        ld.shadow_soft_size = 0.08
        ld.color = (1.0, 0.75, 0.5)
        o = bpy.data.objects.new(f"Abajur_{i}", ld)
        cx = (PX(64.08) + PX(164.16)) / 2
        o.location = (cx + s * (0.85 + 0.25) - 0.04, PYm(165.24) - 0.27 - 0.20, 0.92)
        scn.collection.objects.link(o)
    # Sol
    sd = bpy.data.lights.new("Sol", "SUN")
    sd.energy = 2.2
    sd.angle = math.radians(1.5)
    sd.color = (1.0, 0.95, 0.88)
    so = bpy.data.objects.new("Sol", sd)
    so.rotation_euler = (math.radians(48), math.radians(12), math.radians(150))
    scn.collection.objects.link(so)
    from mathutils import Vector
    for v in VIEWS:
        cd = bpy.data.cameras.new(f"Cam_{v['id']}")
        cd.lens = v["lente"]
        cd.clip_start = 0.05
        cd.clip_end = 200
        co = bpy.data.objects.new(f"Cam_{v['id']}", cd)
        co.location = v["pos"]
        d = Vector(v["alvo"]) - Vector(v["pos"])
        co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        scn.collection.objects.link(co)


def setup_world(night):
    scn = bpy.context.scene
    w = scn.world or bpy.data.worlds.new("Mundo")
    scn.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    # céu simples: gradiente azul-claro de dia, azul-noite à noite
    grad = nt.nodes.new("ShaderNodeTexGradient")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    if night:
        ramp.color_ramp.elements[0].color = (0.010, 0.012, 0.020, 1)
        ramp.color_ramp.elements[1].color = (0.004, 0.006, 0.014, 1)
    else:
        ramp.color_ramp.elements[0].color = (0.62, 0.74, 0.90, 1)
        ramp.color_ramp.elements[1].color = (0.22, 0.42, 0.80, 1)
    ramp.color_ramp.elements[0].position = 0.5
    ramp.color_ramp.elements[1].position = 0.75
    nt.nodes.remove(grad)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    sun = bpy.data.objects.get("Sol")
    if sun:
        sun.hide_render = night


# ---------------------------------------------------------------------------------------------------
# Consolidação (menos objetos para o visualizador) e exportação
# ---------------------------------------------------------------------------------------------------
def apply_modifiers():
    dg = bpy.context.evaluated_depsgraph_get()
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj.modifiers:
            ev = obj.evaluated_get(dg)
            me = bpy.data.meshes.new_from_object(ev)
            old = obj.data
            obj.modifiers.clear()
            obj.data = me
            bpy.data.meshes.remove(old)


def consolidate():
    """Junta as malhas de cada grupo em um único objeto (mantém materiais); a folha da porta de vidro fica separada."""
    apply_modifiers()
    for gname, gobj in GROUPS.items():
        kids = [o for o in gobj.children if o.type == "MESH"]
        if len(kids) < 2:
            continue
        base = kids[0]
        with bpy.context.temp_override(active_object=base, selected_editable_objects=kids, object=base):
            bpy.ops.object.join()
        base.name = f"{gname}_malha"
        base.data.name = f"{gname}_malha"
    leaf = bpy.data.objects.get("PortaVidro_Folha")
    if leaf:
        kids = [o for o in leaf.children if o.type == "MESH"]
        base = kids[0]
        with bpy.context.temp_override(active_object=base, selected_editable_objects=kids, object=base):
            bpy.ops.object.join()
        base.name = "PortaVidro_Folha_malha"


def export_glb(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    kwargs = dict(filepath=path, export_format="GLB", export_extras=True, export_apply=True,
                  export_cameras=False, export_lights=False, export_yup=True, use_visible=False)
    try:
        bpy.ops.export_scene.gltf(**kwargs, export_image_format="JPEG", export_jpeg_quality=82)
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    print(f"GLB: {path} ({os.path.getsize(path) // 1024} KB)")


def render(folder, cams, samples, res):
    import addon_utils
    addon_utils.enable("cycles", default_set=True)
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.02
    scn.cycles.max_bounces = 6
    scn.cycles.diffuse_bounces = 3
    scn.cycles.glossy_bounces = 3
    scn.cycles.transmission_bounces = 4
    scn.cycles.sample_clamp_indirect = 4.0
    try:
        scn.cycles.use_denoising = True
    except AttributeError:
        pass
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 88
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Punchy"
    except TypeError:
        scn.view_settings.view_transform = "Filmic"
    os.makedirs(folder, exist_ok=True)
    for v in VIEWS:
        if cams and v["id"] not in cams:
            continue
        interior = bool(v.get("teto"))
        GROUPS["Teto"].hide_render = False
        for name in ("Teto", "Telhado"):
            show = bool(v.get("teto")) if name == "Teto" else bool(v.get("telhado"))
            for o in [GROUPS[name]] + list(GROUPS[name].children_recursive):
                o.hide_render = not show
        for o in [GROUPS["CorteParedes"]] + list(GROUPS["CorteParedes"].children_recursive):
            o.hide_render = True
        setup_world(night=interior)
        scn.view_settings.exposure = -1.1 if interior else -0.5
        scn.camera = bpy.data.objects[f"Cam_{v['id']}"]
        scn.render.filepath = os.path.join(folder, f"{v['id']}.jpg")
        bpy.ops.render.render(write_still=True)
        print("render:", scn.render.filepath)


def build():
    reset_scene()
    build_textures()
    build_materials()
    build_structure()
    build_ceiling_details()
    roof_z = build_roof()
    build_exterior(roof_z)
    build_openings()
    build_sala()
    build_cozinha()
    build_dorm1()
    build_dorm2()
    build_banho()
    build_servico()
    meta = build_meta()
    return meta


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    opts = {"glb": None, "blend": None, "render": None, "cams": None, "samples": 96, "res": (1600, 900)}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--glb", "--blend", "--render", "--cams", "--samples", "--res"):
            val = argv[i + 1]
            i += 2
            key = a[2:]
            if key == "samples":
                val = int(val)
            elif key == "res":
                val = tuple(int(x) for x in val.lower().split("x"))
            elif key == "cams":
                val = val.split(",")
            opts[key] = val
        else:
            i += 1
    return opts


def main():
    opts = parse_args()
    meta = build()
    blender_lights_and_cameras()
    consolidate()
    print(f"Área útil: {meta['areaUtil']} m² · construída: {meta['areaConstruida']} m²")
    if opts["glb"]:
        export_glb(opts["glb"])
    if opts["render"]:
        render(opts["render"], opts["cams"], opts["samples"], opts["res"])
    if opts["blend"]:
        os.makedirs(os.path.dirname(os.path.abspath(opts["blend"])), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opts["blend"]))


if __name__ == "__main__":
    main()
