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
HAPPY_MAX = 6         # 3..6   -> happy     (hops around, hearts)
EUPHORIC_MAX = 13     # 7..13  -> euphoric  (runs and jumps, sparkles)
                      # 14+    -> king      (crown, sparkle aura, spin jumps)
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
PAW = [".ooo.", "obbbo", "obkbo", "obbbo", ".obo."]
CROWN = ["y...y...y", "yy.yRy.yy", "yyyyyyyyy", "yByyRyyBy", "YYYYYYYYY"]
HEART = [".R.R.", "RhRRR", "RRRRR", ".RRR.", "..R.."]
ZS = {4: ["zzzz", "..z.", ".z..", "zzzz"], 5: ["zzzzz", "...z.", "..z..", ".z...", "zzzzz"]}
SPARKS = {1: ["y"], 2: [".y.", "yWy", ".y."], 3: ["..y..", "..y..", "yyWyy", "..y..", "..y.."]}
for _rows in (HEAD, BODY, TAIL_UP, PAW, CROWN, HEART, *TIPS.values()):
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
    """Recolour a sprite key for a coat. part: head, body, tail (raised), paw or fx."""
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
    elif coat == "siamese":
        if part == "head" and (y <= 3 or ((x - 8.5) / 6.6) ** 2 + ((y - 8.3) / 4.4) ** 2 <= 1):
            return "P"
        if part in ("tail", "paw") or k == "t":
            return "P"
    elif coat == "tuxedo":
        if part == "head":
            if (x in (8, 9) and 3 <= y <= 8) or ((x - 8.5) / 3.4) ** 2 + ((y - 11) / 2.6) ** 2 <= 1:
                return "W"
            return k
        if part == "body":
            return k if k == "b" and ((x - 3.5) / 5.4) ** 2 + ((y - 6) / 6.2) ** 2 <= 1 else "W"
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
        elif eyes == "happy":
            rows[7][c:c + 2] = list("mm"); rows[8][c:c + 2] = list("bb")
            rows[8][c - 1] = "m"; rows[8][c + 2] = "m"
    return rows

def sprite(coat, pose):
    """Key grid {(x, y): key} for a pose, in the sprite box."""
    g = {}
    def stamp(rows, ox, oy, part):
        for y, row in enumerate(rows):
            for x, k in enumerate(row):
                if k != ".":
                    g[(ox + x, oy + y)] = coat_key(coat, part, x, y, k)
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
        stamp(tl, BX - 3, by - 4, "tail")
    stamp(body, BX, by, "body")
    hx, hy = BX + 5 + pose.get("hdx", 0), by - 12 + pose.get("hdy", 0)
    stamp(head_rows(pose.get("eyes", "open"), pose.get("ears", "")), hx, hy, "head")
    if pose.get("paw"):
        stamp(PAW, hx + 4, hy + 8 + pose.get("lick", 0), "paw")
        if pose.get("tongue"):
            g[(hx + 9, hy + 9)] = "r"
    if pose.get("crown"):
        stamp(CROWN, hx + 4, hy - 2, "fx")
    return g

def colorize(g, coat, mirror):
    if mirror:
        g = {(SPR_W - 1 - x, y): k for (x, y), k in g.items()}
    pal = dict(BASE); pal.update(FX); pal.update(COAT_COLORS[coat])
    img = Image.new("RGBA", (SPR_W, SPR_H), (0, 0, 0, 0))
    for (x, y), k in g.items():
        c = pal.get(k, pal["b"])
        if k in FUR:
            left, below = g.get((x - 1, y), "."), g.get((x, y + 1), ".")
            if left in "oq." or below in "oq.":
                c = tuple(round(v * f) for v, f in zip(c, (0.84, 0.84, 0.9)))
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
    frames, n = [], 16
    x = 25
    hx, hy = head_top(x, 0, False)
    for k in range(n):
        br = 1 if 4 <= k < 12 else 0
        fx = []
        for ph in (0, 8):
            t = ((k + ph) % 16) / 16
            if t < 0.9:
                fx.append((("z", 4 if t < 0.5 else 5), hx + 12 + 8 * t, hy + 8 - 20 * t))
        frames.append(frame(coat, x, eyes="closed", ears="lr" if k != 9 else "l", hdy=2,
                            stretch=br - 1, tail="c" if k in (6, 7) else "a", fx=fx))
    return frames, 200

def state_calm(coat):
    frames, tips = [], "aabbaacc"
    for k in range(40):
        p = dict(tail=tips[k % 8], stretch=1 if (k // 5) % 2 else 0)
        if k in (6, 27):
            p["eyes"] = "closed"
        if 9 <= k <= 13:
            p["hdx"] = -1
        if 30 <= k <= 34:
            p["hdx"] = 1
        if k in (20, 21):
            p["ears"] = "l"
        if k == 37:
            p["ears"] = "r"
        if 15 <= k <= 25:                       # grooming: paw to the mouth, licking
            p.update(paw=True, eyes="closed", lick=k % 2, tongue=k % 2 == 0, hdy=1, stretch=0)
        frames.append(frame(coat, 25, **p))
    return frames, 120

def state_happy(coat):
    seq = []
    for d in (1, -1):
        for _ in range(4):
            seq += [("hop", d, lift, st) for lift, st in hop(6, 4.5)]
        seq += [("pause", d, 0.0, 0)] * 6
    poses, x = [], 13.0
    for i, (kind, d, lift, st) in enumerate(seq):
        if kind == "hop" and lift > 0:
            x += d * 1.5
        p = dict(tail="up" if (i // 2) % 2 else "up2", eyes="happy", stretch=st)
        if kind == "pause":
            j = i % 30 - 24
            p.update(eyes="closed" if j == 3 else "open", ears="l" if j == 1 else "", stretch=1 if j in (2, 3) else 0)
        elif st < 0:
            p["ears"] = "lr"
        poses.append((x, lift, d < 0, p, kind))
    n = len(poses)
    starts = [i for i in range(n) if poses[i][4] == "pause" and poses[i - 1][4] == "hop"]
    out = []
    for i, (x, lift, mirror, p, _) in enumerate(poses):
        fx = []
        for s in starts:
            j = (i - s) % n
            if j < 10:
                hx, hy = head_top(poses[s][0], 0, poses[s][2])
                fx.append((("heart",), hx + (6 if not poses[s][2] else -6) + math.sin(j * 0.9), hy + 1 - 1.2 * j))
        out.append(frame(coat, x, lift, mirror, fx=fx, **p))
    return out, 80

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
    seq = []
    for d in (1, -1):
        for _ in range(4):
            seq += [(d, lift, st, 2.0) for lift, st in hop(3, 2.5)]
        seq += [(d, lift, st, 1.6) for lift, st in hop(9, 11)]
        seq += [(d, 0.0, -1, 0.0)] * 2
    out, n, x = [], len(seq), 6.0
    for i, (d, lift, st, dx) in enumerate(seq):
        x += d * dx
        p = dict(tail="up" if i % 2 else "up2", eyes="happy" if lift > 0 or i % 6 else "open",
                 stretch=st, ears="l" if i % 4 == 0 else ("r" if i % 4 == 2 else ""))
        fx = sparkles(i, n, x + 15, GROUND - 14 - lift, 6, 19, 16, seed=3)
        out.append(frame(coat, x, lift, d < 0, fx=fx, **p))
    return out, 60

def state_king(coat):
    seq = []
    def sit(nf):
        seq.extend([(0.0, 0, False, "sit")] * nf)
    def spin_jump():
        seq.append((0.0, -1, False, "crouch"))
        for j, (lift, st) in enumerate(hop(12, 9)):
            if 0 < j < 11:
                seq.append((lift, st, (j // 2) % 2 == 1, "air"))
        seq.append((0.0, -1, False, "land"))
        seq.append((0.0, 0, False, "land"))
    sit(12); spin_jump(); sit(10); spin_jump()
    out, n = [], len(seq)
    for i, (lift, st, mirror, kind) in enumerate(seq):
        p = dict(crown=True, stretch=st, tail="abac"[(i // 2) % 4] if kind == "sit" else "up")
        if kind == "sit":
            p.update(eyes="closed" if i in (5, 30) else "open", stretch=1 if (i // 4) % 2 else 0)
        else:
            p["eyes"] = "happy"
        cx, cy = 25 + 15, GROUND - 18 - lift * 0.5
        fx = []
        for s in range(8):                         # orbiting sparkle aura
            a = 2 * math.pi * (s / 8 + i / n)
            spark = (("spark", [1, 2, 3, 2][(s + i // 2) % 4]), cx + 21 * math.cos(a), cy + 13 * math.sin(a))
            fx.append(spark + (("back",) if math.sin(a) < 0 else ()))
        out.append(frame(coat, 25, lift, mirror, fx=fx, **p))
    return out, 70

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
