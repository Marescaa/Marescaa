"""Chibi pixel-art cat for the GitHub profile README.

A hand-drawn kitten (8 coats) on a transparent background. What it does depends
on the contributions of the last 7 complete days; the coat can be picked by
name or deduced from the languages of the public repositories.

    python cat/make_cat.py                         # real data (GITHUB_TOKEN + KOI_LOGIN / GITHUB_REPOSITORY_OWNER)
    python cat/make_cat.py 5 --coat calico         # 5 contributions, calico coat
    python cat/make_cat.py --state sleep --coat black
    CAT_COAT=siamese CAT_STATE=king CAT_OUT=/tmp/x.gif python cat/make_cat.py

Environment: CAT_COAT (auto | gray orange calico siamese white tuxedo black brown),
CAT_STATE (auto | sleep calm happy euphoric king), CAT_OUT (default cat/cat.gif).
"""
import datetime, hashlib, json, math, os, sys, urllib.request
from PIL import Image, ImageFilter

# ---- contributions in the last 7 complete days -> state (edit freely) ------
CALM_MAX = 2          # 0..2   -> calm      (sits, blinks, grooms)
HAPPY_MAX = 6         # 3..6   -> happy     (walks around, hearts)
EUPHORIC_MAX = 13     # 7..13  -> euphoric  (trots fast, happy hops, sparkles)
                      # 14+    -> king      (crown, sparkle aura, walks, spin jump)
# "sleep" is never chosen automatically: use CAT_STATE=sleep / --state sleep.

COATS = ["gray", "orange", "calico", "siamese", "white", "tuxedo", "black", "brown"]
STATES = ["sleep", "calm", "happy", "euphoric", "king"]

W, H, SCALE = 80, 44, 5          # grid and scale -> 400x220 GIF
GROUND = 42                      # canvas row just below the cat's feet
SPR_W, SPR_H = 30, 34            # sprite box (room for a raised tail and a crown)
BX = 4                           # body's left edge inside the sprite box

# ------------------------------------------------------------------ sprites --
# o outline  b fur  t tail fur  q tail outline (fur when the tail is raised)
# p inner ear  e eye  w eye highlight  m mouth/lines  k blush
HEAD = [
    "..o............o..",
    ".obo..........obo.",
    ".obpo........opbo.",
    "obppboooooooobppbo",
    "obbbbbbbbbbbbbbbbo",
    "obbbbbbbbbbbbbbbbo",
    "obbbbbbbbbbbbbbbbo",
    "obbbewbbbbbbewbbbo",
    "obbbeebbmmbbeebbbo",
    "obbkkbbbbbbbbkkbbo",
    "obbkkbbbbbbbbkkbbo",
    ".obbbbbbbbbbbbbbo.",
    "..oo..........oo..",
]
BODY = [
    "......obbbbbbbbbbbbbbbo.",
    ".....obbbbbbbbbbbbbbbbo.",
    "...oobbbbbbbbbbbbbbbbbo.",
    "..obbbbbbbbbbbbbbbbbbbo.",
    ".obbbbbbbbbbbbbbbbbbbbo.",
    ".obbbbbbbbbbbbbbbbbbbbo.",
    "obbbbbbbbbbbbbbbbbbbbbo.",
    "obbbbbbbbbbbbbbbbbbbbbo.",
    "obbbbbbbbbbbbbbbbqqbbbo.",
    "obbbbbbbbbbbbbbbqttqbbo.",
    "obbbbbbbbbbbqqqqqttqbbo.",
    "obbbqqqqqqqqtttttttqbbo.",
    "obbqtttttttttttttttqbbo.",
    ".oooooooooooooooooooooo.",
]
# tail tip in front of the body (rows 7..10, cols 15..20 of BODY); "." = fur
TIPS = {
    "a": ["......", "..qq..", ".qttq.", "qqttq."],
    "b": ["...qq.", "..qttq", ".qttq.", "qqttq."],
    "c": [".qq...", "qttq..", ".qttq.", "qqttq."],
}
TAIL_UP = [
    ".qq....",
    "qttq...",
    "qttq...",
    ".qttq..",
    ".qttq..",
    "..qttq.",
    "..qttq.",
    "..qttq.",
    "...qttq",
    "...qttq",
    "....qtt",
    "....qtt",
]
# raised foreleg for grooming: paw at the mouth, forearm down to the chest
LICK_ARM = [".oooo.", "obbbbo", "obbbbo", "obbbbo", ".obbbo", ".obbo.", ".obbo.", ".obbo."]
CROWN = ["y...y...y", "yy.yRy.yy", "yyyyyyyyy", "yByyRyyBy", "YYYYYYYYY"]
HEART = [".R.R.", "RhRRR", "RRRRR", ".RRR.", "..R.."]
ZS = {4: ["zzzz", "..z.", ".z..", "zzzz"], 5: ["zzzzz", "...z.", "..z..", ".z...", "zzzzz"]}
SPARKS = {1: ["y"], 2: [".y.", "yWy", ".y."], 3: ["..y..", "..y..", "yyWyy", "..y..", "..y.."]}
for _rows in (HEAD, BODY, TAIL_UP, LICK_ARM, CROWN, HEART, *TIPS.values()):
    assert len({len(r) for r in _rows}) == 1, _rows

OUTLINE = (26, 22, 28)
BASE = {"o": OUTLINE, "q": OUTLINE, "m": OUTLINE, "e": OUTLINE, "k": (240, 132, 148),
        "p": (240, 172, 176), "w": (124, 198, 236), "r": (236, 96, 122)}
COAT_COLORS = {
    "gray":    {"b": (104, 104, 110)},
    "orange":  {"b": (240, 152, 74), "S": (206, 112, 44), "p": (250, 192, 152), "w": (255, 255, 255)},
    "calico":  {"b": (252, 252, 250), "1": (48, 46, 50), "2": (216, 116, 50)},
    "siamese": {"b": (232, 218, 208), "P": (96, 60, 46)},
    "white":   {"b": (252, 252, 252)},
    "tuxedo":  {"b": (50, 48, 54), "W": (250, 250, 248), "w": (240, 182, 66)},
    "black":   {"b": (56, 52, 60), "p": (90, 84, 96), "w": (240, 182, 66)},
    "brown":   {"b": (148, 106, 66), "S": (102, 70, 42), "p": (238, 182, 142), "w": (255, 255, 255)},
}
FX = {"y": (252, 206, 64), "Y": (222, 160, 40), "W": (255, 255, 236), "h": (255, 210, 222),
      "z": (172, 192, 255), "R": (230, 64, 92), "B": (90, 160, 240)}
FX_OUTLINE = (40, 30, 46)
FUR = set("bt12SPW")

# tabby dashes (x, y, length) in BODY coordinates
DASHES = [(3, 4, 2), (8, 3, 3), (14, 3, 3), (19, 4, 2), (2, 7, 3), (7, 6, 3), (12, 6, 2),
          (17, 6, 3), (4, 9, 3), (10, 9, 2), (13, 8, 2), (1, 10, 2), (20, 9, 2)]

def coat_key(coat, part, x, y, k):
    """Recolour a sprite key for a coat.

    part: head, body (sitting), tail (raised), paw (grooming foreleg / tucked paws),
    walk (walking torso), leg, loaf (sleeping body) or fx; (x, y) are coordinates
    inside that part.
    """
    if part == "fx":
        return k
    if k == "p":
        return {"siamese": "P", "tuxedo": "W"}.get(coat, k)
    if k not in ("b", "t"):
        return k
    if coat in ("orange", "brown"):
        if part == "head" and ((x in (6, 11) and 4 <= y <= 5) or (x in (8, 9) and 4 <= y <= 6)
                               or (x in (1, 2, 15, 16) and y in (6, 8))):
            return "S"
        if part == "body":
            if k == "t" and (x in (6, 10, 14) or y == 9):
                return "S"
            if k == "b" and any(y == dy and dx <= x < dx + n for dx, dy, n in DASHES):
                return "S"
        if part == "tail" and y in (2, 5, 8):
            return "S"
        if part == "walk" and ((x in (4, 8) and 2 <= y <= 4) or (x in (2, 3) and y == 6)):
            return "S"
        if part == "leg" and y == 2:
            return "S"
        if part == "paw" and y == 4:
            return "S"
        if part == "loaf":
            if k == "t" and x % 4 == 1:
                return "S"
            if k == "b" and ((x in (3, 6) and 2 <= y <= 4) or (x in (2, 3) and y == 6) or (x == 7 and y == 2)):
                return "S"
    elif coat == "calico":
        if part == "head":
            if x + y <= 9:
                return "1"
            if (17 - x) + y <= 8:
                return "2"
        if part == "body":
            if k == "t":
                return "2" if x < 10 else ("1" if y <= 10 else k)
            if ((x - 4) / 4.2) ** 2 + ((y - 4.5) / 3.2) ** 2 <= 1:
                return "1"
            if ((x - 3) / 3.4) ** 2 + ((y - 9.5) / 2.4) ** 2 <= 1:
                return "2"
        if part == "tail":
            return "1" if y < 5 else "2"
        if part == "walk":
            if ((x - 6) / 5.2) ** 2 + ((y - 2.5) / 3.2) ** 2 <= 1:
                return "1"
            if ((x - 3) / 3.6) ** 2 + ((y - 8) / 3.0) ** 2 <= 1:
                return "2"
        if part == "loaf":
            if k == "t":
                return "2" if x < 9 else "1"
            if ((x - 6) / 5.5) ** 2 + ((y - 3) / 3.4) ** 2 <= 1:
                return "1"
            if ((x - 2) / 3.2) ** 2 + ((y - 7) / 2.6) ** 2 <= 1:
                return "2"
    elif coat == "siamese":
        if part == "head" and (y <= 3 or ((x - 8.5) / 6.6) ** 2 + ((y - 8.3) / 4.4) ** 2 <= 1):
            return "P"
        if part in ("tail", "paw", "leg") or k == "t":
            return "P"
    elif coat == "tuxedo":
        if part == "head":
            if (x in (8, 9) and 3 <= y <= 8) or ((x - 8.5) / 3.4) ** 2 + ((y - 11) / 2.6) ** 2 <= 1:
                return "W"
            return k
        if part == "body":
            return k if k == "b" and ((x - 3.5) / 5.4) ** 2 + ((y - 6) / 6.2) ** 2 <= 1 else "W"
        if part == "walk":
            return "W" if ((x - 21) / 7) ** 2 + ((y - 7) / 5) ** 2 <= 1 else k
        if part == "loaf":
            return "W" if k == "t" or (x >= 13 and y >= 7) else k
        if part == "leg" and y == 0:
            return k
        return "W"
    return k

def head_rows(eyes="open", ears=""):
    rows = [list(r) for r in HEAD]
    if "l" in ears:
        rows[0][2] = "."; rows[1][1:4] = list("oo.")
    if "r" in ears:
        rows[0][15] = "."; rows[1][14:17] = list(".oo")
    for c in (4, 12):
        if eyes == "closed":
            rows[7][c:c + 2] = list("bb"); rows[8][c:c + 2] = list("mm")
        elif eyes == "happy":                      # ^ ^
            rows[7][c:c + 2] = list("mm"); rows[8][c:c + 2] = list("bb")
            rows[8][c - 1] = "m"; rows[8][c + 2] = "m"
        elif eyes == "sleep":                      # closed, curved downwards: u u
            rows[7][c:c + 2] = list("bb"); rows[8][c:c + 2] = list("mm")
            rows[7][c - 1] = "m"; rows[7][c + 2] = "m"
    return rows

def blob(w, h, r):
    """Rounded rectangle: fur inside, a 1px outline on its edge."""
    def inside(x, y):
        if not (0 <= x < w and 0 <= y < h):
            return False
        dx = max(r - x, 0, x - (w - 1 - r))
        dy = max(r - y, 0, y - (h - 1 - r))
        return dx * dx + dy * dy <= r * r + r * 0.6
    rows = []
    for y in range(h):
        row = ""
        for x in range(w):
            if not inside(x, y):
                row += "."
            elif all(inside(x + a, y + b) for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                row += "b"
            else:
                row += "o"
        rows.append(row)
    return rows

WALK_TORSO = blob(27, 10, 4)
LOAF = blob(29, 12, 5)

def stamp(g, coat, rows, ox, oy, part, dark=False):
    for y, row in enumerate(rows):
        for x, k in enumerate(row):
            if k != ".":
                k = coat_key(coat, part, x, y, k)
                g[(ox + x, oy + y)] = k + "_" if dark and k not in "oqme" else k

def put_head(g, coat, pose, hx, hy):
    stamp(g, coat, head_rows(pose.get("eyes", "open"), pose.get("ears", "")), hx, hy, "head")
    if pose.get("crown"):
        stamp(g, coat, CROWN, hx + 4, hy - 2, "fx")

def leg(g, coat, x0, hip, foot, dx, dark, w=4):
    """A w-px-wide leg from the torso's bottom outline (row `hip`) down to row `foot`,
    its lower part shifted dx px (stride); the last row is the sole."""
    n = foot - hip
    for i in range(n + 1):
        s = round(dx * min(1.0, i / max(1, n - 1)))
        row = "o" * w if i == n else "o" + "b" * (w - 2) + "o"
        for j, k in enumerate(row):
            k = coat_key(coat, "leg", j, i, k)
            g[(x0 + s + j, hip + i)] = k + "_" if dark and k != "o" else k

# walking (facing right). Legs: (x, far side?, pair); diagonal pairs move together.
WALK_LEGS = [(3, True, 0), (17, True, 1), (7, False, 1), (21, False, 0)]   # far ones first

def walk_sprite(coat, pose):
    """Walking/trotting cat in 3/4 view: torso, 4 legs, raised tail, head in front."""
    g = {}
    ph, stride, up = pose.get("phase", 0) % 4, pose.get("stride", 1), pose.get("step", 2)
    dy = -1 if ph % 2 else 0                      # body bobs up while a pair passes
    top = 18 + dy
    hip = top + len(WALK_TORSO) - 1
    tail = pose.get("tail", "up")
    tl = TAIL_UP if tail == "up" else [r[1:] + "." if i < 5 else r for i, r in enumerate(TAIL_UP)]
    stamp(g, coat, tl, 1 + pose.get("tdx", 0), top - 8 + pose.get("tdy", 0), "tail")
    stamp(g, coat, WALK_TORSO, 1, top, "walk")
    for x0, far, pair in WALK_LEGS:
        p = (ph + 2 * pair) % 4
        off, lift = [(stride, 0), (0, 0), (-stride, 0), (0, up)][p]
        leg(g, coat, x0, hip, SPR_H - 1 - lift, off, far, 4 if far else 5)
    put_head(g, coat, pose, 11 + pose.get("hdx", 0), 8 + dy + pose.get("hdy", 0))
    return g

def loaf_sprite(coat, pose):
    """Sleeping 'loaf': body flat on the ground, head resting in front, tail curled."""
    g = {}
    br = pose.get("breath", 0)                    # 1 = inhale: body 1px taller
    body = [list(r) for r in ([LOAF[0], LOAF[1]] + LOAF[1:] if br else LOAF)]
    h = len(body)
    # tail curled along the bottom, from the rump towards the front paws
    for x in range(3, 17):
        body[h - 4][x] = "q"
    for x in range(2, 17):
        body[h - 3][x] = "t"; body[h - 2][x] = "t"
    for y in range(h - 7, h - 3):
        body[y][2] = "t"; body[y][3] = "q"
    body[h - 3][17] = "q"; body[h - 2][17] = "q"
    by = SPR_H - h
    stamp(g, coat, ["".join(r) for r in body], 1, by, "loaf")
    for px in (18, 22):                           # front paws tucked under the chin
        stamp(g, coat, [".oo.", "obbo", "oooo"], px, SPR_H - 3, "paw")
    put_head(g, coat, pose, 10, by - 6 + pose.get("hdy", 0))
    return g

def sprite(coat, pose):
    """Key grid {(x, y): key} for a pose, in the sprite box."""
    if pose.get("body") == "walk":
        return walk_sprite(coat, pose)
    if pose.get("body") == "loaf":
        return loaf_sprite(coat, pose)
    g = {}
    stretch = pose.get("stretch", 0)
    body = [list(r) for r in BODY]
    tail = pose.get("tail", "a")
    if tail.startswith("up"):
        body = [[("b" if k in "qt" else k) for k in r] for r in body]
    else:
        tip = TIPS[tail]
        for j in range(4):
            for i in range(6):
                if body[7 + j][15 + i] in "bqt":
                    body[7 + j][15 + i] = "b" if tip[j][i] == "." else tip[j][i]
    if stretch > 0:
        body = body[:7] + [body[7]] * (1 + stretch) + body[8:]
    elif stretch < 0:
        body = body[:6] + body[7:]
    by = SPR_H - len(body)
    if tail.startswith("up"):
        tl = TAIL_UP if tail == "up" else [r[1:] + "." if i < 5 else r for i, r in enumerate(TAIL_UP)]
        stamp(g, coat, tl, BX - 3, by - 4, "tail")
    stamp(g, coat, ["".join(r) for r in body], BX, by, "body")
    hx, hy = BX + 5 + pose.get("hdx", 0), by - 12 + pose.get("hdy", 0)
    put_head(g, coat, pose, hx, hy)
    if pose.get("lick") is not None:              # grooming: paw raised to the mouth
        stamp(g, coat, LICK_ARM, hx + 9, hy + 9 + pose["lick"], "paw")
        if pose.get("tongue"):
            g[(hx + 8, hy + 9)] = g[(hx + 9, hy + 9)] = "r"
    return g

def colorize(g, coat, mirror):
    if mirror:
        g = {(SPR_W - 1 - x, y): k for (x, y), k in g.items()}
    pal = dict(BASE); pal.update(FX); pal.update(COAT_COLORS[coat])
    img = Image.new("RGBA", (SPR_W, SPR_H), (0, 0, 0, 0))
    for (x, y), k in g.items():
        dark = k.endswith("_")                    # far-side legs: a shade darker
        k = k[0]
        c = pal.get(k, pal["b"])
        if k in FUR:
            left, below = g.get((x - 1, y), "."), g.get((x, y + 1), ".")
            if left[0] in "oq." or below[0] in "oq.":
                c = tuple(round(v * f) for v, f in zip(c, (0.84, 0.84, 0.9)))
        if dark:
            c = tuple(round(v * 0.8) for v in c)
        if 0 <= x < SPR_W and 0 <= y < SPR_H:
            img.putpixel((x, y), c + (255,))
    return img

def fx_image(rows):
    w, h = len(rows[0]), len(rows)
    img = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, k in enumerate(row):
            if k != ".":
                img.putpixel((x + 1, y + 1), FX.get(k, FX["y"]) + (255,))
    if w * h == 1:
        return img
    out = Image.new("RGBA", img.size, FX_OUTLINE + (0,))
    out.putalpha(img.getchannel("A").filter(ImageFilter.MaxFilter(3)))
    out.alpha_composite(img)
    return out

FX_CACHE = {}
def draw_fx(canvas, kind, cx, cy):
    """kind: ('z', size) | ('heart',) | ('spark', size); (cx, cy) is its centre."""
    if kind not in FX_CACHE:
        rows = {"z": lambda: ZS[kind[1]], "heart": lambda: HEART, "spark": lambda: SPARKS[kind[1]]}[kind[0]]()
        FX_CACHE[kind] = fx_image(rows)
    im = FX_CACHE[kind]
    canvas.alpha_composite(im, (round(cx - im.width / 2), round(cy - im.height / 2)))

# --------------------------------------------------------------- animation --
def frame(coat, x, lift=0.0, mirror=False, fx=(), **pose):
    """Cat sprite with its box's left edge at canvas x, lifted `lift` px off the ground."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    spr = colorize(sprite(coat, pose), coat, mirror)
    cx = x + (SPR_W - 1 - 15.5 if mirror else 15.5)
    half = max(4, 10 - lift * 0.6)
    for xx in range(round(cx - half), round(cx + half) + 1):
        canvas.putpixel((xx, GROUND), (118, 122, 134, 255))       # small contact shadow
    for kind, fxx, fxy, *back in fx:
        if back:                                   # behind the cat
            draw_fx(canvas, kind, fxx, fxy)
    canvas.alpha_composite(spr, (round(x), GROUND - SPR_H - round(lift)))
    for kind, fxx, fxy, *back in fx:
        if not back:
            draw_fx(canvas, kind, fxx, fxy)
    return canvas

def head_top(x, lift, mirror):
    """Canvas point at the top of the cat's head (sitting pose)."""
    hx = x + (SPR_W - 1 - (BX + 5 + 8.5) if mirror else BX + 5 + 8.5)
    return hx, GROUND - 26 - round(lift)

def hop(n, height):
    """(lift, stretch) over an n-frame hop: takeoff squash, stretch in the air, landing squash."""
    out = []
    for i in range(n):
        t = i / (n - 1)
        out.append((height * math.sin(math.pi * t), -1 if i in (0, n - 1) else (1 if t < 0.5 else 0)))
    return out

def state_sleep(coat):
    """Curled up as a loaf: slow breathing, an ear twitch, z's floating up."""
    frames, n = [], 16
    x = 25
    zx, zy = x + 27, GROUND - SPR_H + 17          # just above the right ear
    for k in range(n):
        br = 1 if 4 <= k < 12 else 0
        fx = []
        for ph in (0, 8):
            t = ((k + ph) % 16) / 16
            if t < 0.9:
                fx.append((("z", 4 if t < 0.5 else 5), zx + 8 * t, zy - 2 - 16 * t))
        frames.append(frame(coat, x, body="loaf", eyes="sleep", breath=br,
                            ears="l" if k == 9 else "", fx=fx))
    return frames, 200

def state_calm(coat):
    frames, tips = [], "aabbaacc"
    lick = [(1, False), (0, True), (0, True), (1, False)]
    for k in range(40):
        p = dict(tail=tips[k % 8], stretch=1 if (k // 5) % 2 else 0)
        if k in (6, 33):
            p["eyes"] = "closed"
        if 9 <= k <= 12:
            p["hdx"] = -1
        if 35 <= k <= 38:
            p["hdx"] = 1
        if k == 37:
            p["ears"] = "r"
        if 14 <= k <= 29:                       # grooming: paw to the mouth, licking
            j = k - 14
            if j in (0, 15):                    # paw on its way up / down
                p.update(lick=3, eyes="closed" if j else "open")
            else:
                d, tongue = lick[(j - 1) % 4]
                p.update(lick=d, tongue=tongue, eyes="happy")
            p.update(hdy=1, stretch=0)
        frames.append(frame(coat, 25, **p))
    return frames, 120

# ---- walking --------------------------------------------------------------
# Facing right the walking cat's head is 2px right of the sitting cat's, and a
# mirrored sitting cat's head is 6px right of an unmirrored one (same box x).
# These offsets keep the head in place when the cat stops, sits and turns.
SIT_FROM_WALK, TURN = 2, 6
TRIP = 40                                        # px walked each way (box x 0..40, 50..10)

def walk_frames(speed, d, x0, extra):
    """One crossing: (x, mirror, pose) with the legs' stride equal to the step, so
    the grounded feet stay put on the floor (no sliding)."""
    out = []
    for i in range(TRIP // speed + 1):
        p = dict(body="walk", phase=i, stride=speed, tail="up" if (i // 2) % 2 else "up2")
        p.update(extra(i))
        out.append((x0 + d * i * speed, d < 0, p))
    return out

def patrol(speed, extra, at_end):
    """Walk right, do `at_end` (sitting, facing right), turn; walk left, `at_end`, turn.
    at_end(x, mirror, side) -> list of (x, mirror, pose) for a sitting cat at box x."""
    seq = walk_frames(speed, 1, 0, extra)
    x = seq[-1][0] + SIT_FROM_WALK
    seq += at_end(x, False, 0)
    seq += walk_frames(speed, -1, x + TURN + SIT_FROM_WALK, extra)
    x = seq[-1][0] - SIT_FROM_WALK
    seq += at_end(x, True, 1)
    return seq

def sit_and_turn(x, mirror, frames_sit, frames_turn, pose_sit, pose_turn):
    """Sit facing the way it came, then turn round (head stays put)."""
    tx = x - TURN if mirror else x + TURN
    return ([(x, mirror, pose_sit(j)) for j in range(frames_sit)]
            + [(tx, not mirror, pose_turn(j)) for j in range(frames_turn)])

def state_happy(coat):
    def extra(i):
        return dict(eyes="closed" if i % 23 == 11 else "open")
    def at_end(x, mirror, side):
        return sit_and_turn(
            x, mirror, 9, 5,
            lambda j: dict(eyes="happy", tail="up" if (j // 2) % 2 else "up2", stretch=1 if j in (3, 4, 5) else 0),
            lambda j: dict(eyes="closed" if j == 2 else "open", ears="l" if j == 1 else "",
                           tail="up" if (j // 2) % 2 else "up2"))
    seq = patrol(2, extra, at_end)
    n = len(seq)
    starts = [i for i in range(n) if seq[i][2].get("body") is None and seq[i - 1][2].get("body") == "walk"]
    out = []
    for i, (x, mirror, p) in enumerate(seq):
        fx = []
        for s in starts:
            j = (i - s) % n
            if j < 12:
                hx, hy = head_top(seq[s][0], 0, seq[s][1])
                fx.append((("heart",), hx + (6 if not seq[s][1] else -6) + math.sin(j * 0.9), hy + 1 - 1.2 * j))
        out.append(frame(coat, x, 0, mirror, fx=fx, **p))
    return out, 100

def sparkles(k, n, cx, cy, count, rx, ry, seed=7):
    """Twinkling sparkles around (cx, cy); each lives 8 frames at a pseudo-random spot."""
    fx = []
    for s in range(count):
        ph = (s * 5 + seed) % 8
        life = (k + ph) % 8
        cycle = ((k + ph) // 8) % max(1, n // 8)
        h = int(hashlib.md5(f"{seed}-{s}-{cycle}".encode()).hexdigest()[:6], 16)
        ang = (h % 360) * math.pi / 180
        r = 1.0 + ((h >> 9) % 20) / 100
        size = [1, 2, 3, 3, 2, 1, 0, 0][life]
        if size:
            fx.append((("spark", size), min(W - 6, max(5, cx + rx * r * math.cos(ang))),
                       min(GROUND - 4, max(5, cy + ry * r * math.sin(ang)))))
    return fx

def state_euphoric(coat):
    """Trots fast from side to side (longer stride, leaning forward); at each end a
    happy hop in place that turns it round."""
    def extra(i):
        return dict(step=2, hdx=1, hdy=1, eyes="happy" if (i // 4) % 3 == 2 else "open",
                    tail="up" if i % 2 else "up2", tdy=1)
    def at_end(x, mirror, side):
        seq = [(x, mirror, dict(stretch=-1, eyes="happy", tail="up"))]
        tx = x - TURN if mirror else x + TURN
        for j, (lift, st) in enumerate(hop(7, 6)):
            if 0 < j < 6:
                m = mirror if j < 3 else not mirror
                seq.append((x if m == mirror else tx, m, dict(stretch=st, eyes="happy", tail="up", lift=lift,
                                                               ears="lr" if j in (1, 5) else "")))
        seq.append((tx, not mirror, dict(stretch=-1, eyes="happy", tail="up2")))
        seq.append((tx, not mirror, dict(eyes="open", tail="up")))
        return seq
    seq = patrol(3, extra, at_end)
    out, n = [], len(seq)
    for i, (x, mirror, p) in enumerate(seq):
        lift = p.pop("lift", 0.0)
        cx = x + (13 if not mirror else 16) if p.get("body") else x + 15
        fx = sparkles(i, n, cx, GROUND - 14 - lift, 6, 19, 15, seed=3)
        out.append(frame(coat, x, lift, mirror, fx=fx, **p))
    return out, 60

def state_king(coat):
    """Walks from side to side with a crown and a sparkle aura; at the right end it
    sits and does a spin jump in place, at the left end it sits and looks around."""
    def extra(i):
        return dict(crown=True, hdy=-1, eyes="closed" if i % 29 == 14 else "open",
                    tail="up" if (i // 3) % 2 else "up2")
    def sitp(j):
        return dict(crown=True, tail="abac"[(j // 2) % 4], eyes="closed" if j == 3 else "open")
    def at_end(x, mirror, side):
        tx = x - TURN if mirror else x + TURN
        seq = [(x, mirror, sitp(j)) for j in range(6)]
        if side == 0:                              # spin jump, in place
            seq.append((x, mirror, dict(crown=True, stretch=-1, eyes="happy", tail="up")))
            for j, (lift, st) in enumerate(hop(12, 9)):
                if 0 < j < 11:
                    m = mirror if (j // 2) % 2 == 0 else not mirror
                    seq.append((x if m == mirror else tx, m,
                                dict(crown=True, stretch=st, eyes="happy", tail="up", lift=lift)))
            seq.append((x, mirror, dict(crown=True, stretch=-1, eyes="happy", tail="up")))
            seq += [(x, mirror, sitp(j + 4)) for j in range(3)]
        seq += [(tx, not mirror, sitp(j + 1)) for j in range(4)]
        return seq
    seq = patrol(2, extra, at_end)
    out, n = [], len(seq)
    turns = max(1, round(n / 48))                  # whole turns of the aura per loop
    for i, (x, mirror, p) in enumerate(seq):
        lift = p.pop("lift", 0.0)
        cx = x + (13 if not mirror else 16) if p.get("body") else x + (14 if not mirror else 15)
        cy = GROUND - 18 - lift * 0.5
        fx = []
        for s in range(8):                         # orbiting sparkle aura
            a = 2 * math.pi * (s / 8 + turns * i / n)
            spark = (("spark", [1, 2, 3, 2][(s + i // 2) % 4]), cx + 21 * math.cos(a), cy + 13 * math.sin(a))
            fx.append(spark + (("back",) if math.sin(a) < 0 else ()))
        out.append(frame(coat, x, lift, mirror, fx=fx, **p))
    return out, 110

BUILDERS = {"sleep": state_sleep, "calm": state_calm, "happy": state_happy,
            "euphoric": state_euphoric, "king": state_king}

def state_for(total):
    if total <= CALM_MAX:
        return "calm"
    if total <= HAPPY_MAX:
        return "happy"
    if total <= EUPHORIC_MAX:
        return "euphoric"
    return "king"

def build(state, coat):
    return BUILDERS[state](coat)

# -------------------------------------------------------------------- data --
FAMILIES = {
    "orange": {"Python", "Jupyter Notebook", "R", "Julia", "MATLAB"},
    "brown": {"Shell", "PowerShell", "Ruby", "Perl", "PHP", "Lua"},
    "calico": {"JavaScript", "TypeScript", "HTML", "CSS", "SCSS", "Vue", "Svelte", "Astro"},
    "tuxedo": {"C", "C++", "Rust", "Go", "Zig", "Assembly", "Verilog", "VHDL", "SystemVerilog", "Cuda"},
    "siamese": {"Java", "Kotlin", "Swift", "C#", "Dart", "Scala", "Objective-C", "Groovy"},
}
IGNORED = {"Dockerfile", "Makefile", "Batchfile", "CMake"}
WEIGHT = {"Jupyter Notebook": 0.1, "HTML": 0.5}

def coat_for(lang):
    for coat, names in FAMILIES.items():
        if lang in names:
            return coat
    return COATS[int(hashlib.md5(lang.encode()).hexdigest(), 16) % len(COATS)]

def gql(query, variables, token):
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]

def activity(login, token):
    q = "query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"
    weeks = gql(q, {"l": login}, token)["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    today = datetime.date.today().isoformat()
    days = [d for d in days if d["date"] < today]  # completed days only
    return sum(d["contributionCount"] for d in days[-7:])

def top_language(login, token):
    q = """query($l:String!){user(login:$l){repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
           nodes{languages(first:8, orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}}}"""
    total = {}
    for r in gql(q, {"l": login}, token)["user"]["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            if name not in IGNORED:
                total[name] = total.get(name, 0) + e["size"] * WEIGHT.get(name, 1.0)
    return max(total, key=total.get) if total else None

# -------------------------------------------------------------------- main --
def save_gif(frames, dur, path):
    """One global palette (index 0 = transparent) shared by every frame."""
    colors, data = {}, []
    for f in frames:
        b = f.tobytes()
        px = [(b[i], b[i + 1], b[i + 2]) if b[i + 3] > 127 else None for i in range(0, len(b), 4)]
        for c in px:
            if c is not None and c not in colors:
                colors[c] = len(colors) + 1
        data.append(px)
    if len(colors) > 255:
        raise SystemExit(f"too many colours: {len(colors)}")
    pal = [0, 0, 0]
    for c in sorted(colors, key=colors.get):
        pal += list(c)
    pal += [0] * (768 - len(pal))
    out = []
    for px in data:
        im = Image.frombytes("P", (W, H), bytes(colors[c] if c is not None else 0 for c in px))
        im.putpalette(pal)
        out.append(im.resize((W * SCALE, H * SCALE), Image.NEAREST))
    out[0].save(path, save_all=True, append_images=out[1:], duration=dur, loop=0, disposal=2,
                transparency=0, optimize=False, background=0)

def option(args, flag, env, default):
    if flag in args:
        i = args.index(flag)
        value = args[i + 1]
        del args[i:i + 2]
        return value.strip().lower()
    return (os.environ.get(env) or default).strip().lower()

def main():
    args = sys.argv[1:]
    coat = option(args, "--coat", "CAT_COAT", "auto")
    state = option(args, "--state", "CAT_STATE", "auto")
    if coat not in COATS + ["auto"]:
        raise SystemExit(f"unknown coat {coat!r}; use auto or one of: {', '.join(COATS)}")
    if state not in STATES + ["auto"]:
        raise SystemExit(f"unknown state {state!r}; use auto or one of: {', '.join(STATES)}")
    login = os.environ.get("KOI_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    total = int(args[0]) if args else None
    if state == "auto":
        if total is None:
            try:
                total = activity(login, token)
            except Exception as e:  # keep the current GIF rather than guessing
                print(f"contributions unavailable ({e}); leaving the cat as it is")
                return
        state = state_for(total)
    lang = None
    if coat == "auto":
        try:
            lang = top_language(login, token)
        except Exception as e:  # never break the workflow over the coat
            print(f"languages unavailable ({e}); using the orange coat")
        coat = coat_for(lang) if lang else "orange"
    frames, dur = build(state, coat)
    path = os.environ.get("CAT_OUT", "cat/cat.gif")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    save_gif(frames, dur, path)
    why = f"{total} contributions in the last 7 days" if total is not None else "state set by hand"
    print(f"{login}: {why} -> {state}; {coat} coat" + (f" (from {lang})" if lang else "")
          + f"; {len(frames)} frames, {os.path.getsize(path) // 1024} KB")

if __name__ == "__main__":
    main()
