"""Pixel-art cat for the GitHub profile README.

The cat lives in a small scene (a wooden plank, a crate and a ball of yarn) and
never leaves it. What it does depends on the last 7 complete days of
contributions; its coat is painted with the colours of the languages in the
user's public repositories.

    python cat/make_cat.py                      # real data (GITHUB_TOKEN + KOI_LOGIN / GITHUB_REPOSITORY_OWNER)
    python cat/make_cat.py 7 --langs "Python:#3572A5,JavaScript:#f1e05a"
    CAT_OUT=/tmp/x.gif python cat/make_cat.py 0
"""
import colorsys, datetime, hashlib, json, math, os, sys, urllib.request
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

W, H, SCALE = 128, 72, 3
FLOOR = 60                      # first row of the plank (paws rest on it)
CRATE_X0, CRATE_X1, CRATE_TOP = 84, 120, 44
YARN_X, YARN_Y, YARN_R = 11, 55, 4.6
STAND_H = 18                    # spine height above the surface when standing
SPINE = 7.0                     # half distance shoulder <-> hip

# ----------------------------------------------------------------- colours --
def hex2rgb(h):
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def hsv(rgb):
    return colorsys.rgb_to_hsv(*[c / 255 for c in rgb])

def rgb(h, s, v):
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h % 1, max(0, min(1, s)), max(0, min(1, v))))

def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))

def mul(c, f):
    return tuple(max(0, min(255, round(x * f))) for x in c)

def tune(c, smax=0.62, vmin=0.5, vmax=0.9):
    """Pull a language colour into the range of believable fur."""
    h, s, v = hsv(c)
    return rgb(h, min(s, smax), min(max(v, vmin), vmax))

def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

FAMILIES = {
    "tabby": {"Python", "Jupyter Notebook", "R", "Julia", "MATLAB", "Shell", "Ruby", "Perl", "PHP", "Lua", "PowerShell"},
    "calico": {"JavaScript", "TypeScript", "HTML", "CSS", "SCSS", "Vue", "Svelte", "Astro"},
    "tuxedo": {"C", "C++", "Rust", "Go", "Zig", "Assembly", "Verilog", "VHDL", "SystemVerilog", "Cuda"},
    "siamese": {"Java", "Kotlin", "Swift", "C#", "Dart", "Scala", "Objective-C", "Groovy"},
}
IGNORED = {"Dockerfile", "Makefile", "Batchfile", "CMake"}
WEIGHT = {"Jupyter Notebook": 0.1, "HTML": 0.5}
EYES = {"tabby": (118, 196, 82), "calico": (236, 168, 48), "tuxedo": (238, 214, 64), "siamese": (96, 168, 244)}
PINK, NOSE, WHITE, CREAM = (238, 150, 162), (226, 112, 132), (244, 242, 236), (250, 238, 218)

def pattern_for(lang):
    for k, names in FAMILIES.items():
        if lang in names:
            return k
    return ["tabby", "calico", "tuxedo", "siamese"][int(hashlib.md5(lang.encode()).hexdigest(), 16) % 4]

def palette(langs):
    """langs: [(name, '#rrggbb'), ...] ordered by importance."""
    langs = [(n, c) for n, c in langs if c]
    if not langs:
        langs = [("Python", None)]
        cols = [(226, 140, 62)]               # default: orange tabby
    else:
        cols = [hex2rgb(c) for _, c in langs]
    pattern = pattern_for(langs[0][0])
    c1 = tune(cols[0])
    h1, s1, v1 = hsv(c1)
    c2 = tune(cols[1]) if len(cols) > 1 else rgb(h1 + 0.04, s1 + 0.1, v1 * 0.62)
    if dist(c1, c2) < 70:
        c2 = rgb(h1 + 0.04, s1 + 0.1, v1 * 0.62)
    acc = None
    for c in cols[2:]:
        t = tune(c, smax=0.8, vmin=0.45, vmax=0.95)
        if dist(t, c1) > 90 and dist(t, c2) > 60:
            acc = t
            break
    if acc is None:
        acc = rgb(h1 + 0.5, 0.65, 0.8)
    p = {"pattern": pattern, "acc": acc, "eye": EYES[pattern], "c1": c1, "c2": c2}
    if pattern == "tabby":
        p.update(base=c1, sec=tune(c2, smax=0.7, vmin=0.4, vmax=0.78), light=rgb(h1, s1 * 0.32, 0.95))
    elif pattern == "calico":
        p.update(base=CREAM, sec=c2, light=WHITE)
    elif pattern == "tuxedo":
        p.update(base=rgb(h1, min(s1, 0.4), 0.27), sec=c1, light=WHITE)
    else:
        p.update(base=rgb(h1, 0.1, 0.93), sec=rgb(h1, min(s1, 0.45) + 0.05, 0.36), light=WHITE)
    hb, sb, vb = hsv(p["base"])
    p["outline"] = rgb(hb, min(1, sb + 0.25), max(0.1, min(vb * 0.3, 0.24)))
    p["acc_dark"] = mul(p["acc"], 0.55)
    p["acc_light"] = mix(p["acc"], (255, 255, 255), 0.45)
    return p

# ---------------------------------------------------------------- geometry --
def ell(cx, cy, rx, ry, rot=0.0, n=28):
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out

def hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]

def capsule(p, q, r0, r1):
    return hull(ell(p[0], p[1], r0, r0, n=16) + ell(q[0], q[1], r1, r1, n=16))

def add(p, q, k=1.0):
    return (p[0] + q[0] * k, p[1] + q[1] * k)

def lerp(a, b, t):
    return a + (b - a) * t

def lerp2(p, q, t):
    return (lerp(p[0], q[0], t), lerp(p[1], q[1], t))

def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def ik(a_pt, target, a, b, bend):
    """2-bone IK. bend=+1 puts the joint behind (elbow), -1 in front (knee)."""
    dx, dy = target[0] - a_pt[0], target[1] - a_pt[1]
    d0 = math.hypot(dx, dy)
    th = math.atan2(dy, dx)
    d = max(abs(a - b) + 0.05, min(a + b - 0.05, d0))
    end = (a_pt[0] + d * math.cos(th), a_pt[1] + d * math.sin(th))
    ca = (a * a + d * d - b * b) / (2 * a * d)
    al = math.acos(max(-1, min(1, ca)))
    ang = th + bend * al
    return (a_pt[0] + a * math.cos(ang), a_pt[1] + a * math.sin(ang)), end

# --------------------------------------------------------------- rendering --
class Layer:
    def __init__(self, pal):
        self.img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.pal = pal

    def part(self, shapes, color, decor=None, dim=1.0, clip_y=None, outline=True, hard=False):
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        for s in shapes:
            d.polygon(s, fill=255)
        if clip_y is not None:
            d.rectangle([0, clip_y, W, H], fill=0)
        col = Image.new("RGBA", (W, H), color + (255,))
        if decor:
            decor(ImageDraw.Draw(col))
        if dim != 1.0:
            col = ImageChops.multiply(col, Image.new("RGBA", (W, H), (round(255 * dim), round(255 * dim), round(255 * min(1, dim + 0.06)), 255)))
        shadow = ImageChops.subtract(m, ImageChops.offset(m, -1, -2))
        light = ImageChops.subtract(m, ImageChops.offset(m, 1, 1))
        col = Image.composite(ImageChops.multiply(col, Image.new("RGBA", (W, H), (196, 192, 214, 255))), col, shadow)
        col = Image.composite(Image.blend(col, Image.new("RGBA", (W, H), (255, 255, 246, 255)), 0.2), col, light)
        if outline:
            ring = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(3)), m)
            inner = ImageChops.multiply(ring, self.img.getchannel("A")) if not hard else Image.new("L", (W, H), 0)
            self.img.paste(self.pal["outline"] + (255,), mask=ImageChops.subtract(ring, inner))
            self.img.paste(mix(self.pal["outline"], mul(color, dim), 0.5) + (255,), mask=inner)
        self.img.paste(col, mask=m)
        return m

    def px(self, pt, color):
        x, y = round(pt[0]), round(pt[1])
        if 0 <= x < W and 0 <= y < H:
            self.img.putpixel((x, y), color + (255,))

def render_cat(p, pal):
    """Render pose p (world coordinates) to a W x H RGBA layer."""
    face = p["face"]
    loc = (lambda q: (W - 1 - q[0], q[1])) if face < 0 else (lambda q: (q[0], q[1]))
    wx = (lambda x: W - 1 - x) if face < 0 else (lambda x: x)
    R = (round(loc((p["x"], 0))[0]), round(p["y"]))
    paws = {k: (round(loc(v)[0]), round(v[1])) for k, v in p["paws"].items()}
    pitch, sp, mode = p["pitch"], p["spine"], p["mode"]
    u = (math.cos(pitch), -math.sin(pitch))
    n = (math.sin(pitch), math.cos(pitch))
    S, Hp = add(R, u, sp), add(R, u, -sp)
    FJ = add(add(S, n, 3.0), u, -0.5)
    HJ = add(add(Hp, n, 1.5), u, -0.5)
    hoff = p["hoff"]
    Hc = (S[0] + hoff[0], S[1] + hoff[1])
    tilt = p["tilt"]
    ct, st = math.cos(-tilt), math.sin(-tilt)
    def hp(x, y):
        return (Hc[0] + x * ct - y * st, Hc[1] + x * st + y * ct)
    def hpoly(pts):
        return [hp(x, y) for x, y in pts]
    def hell(x, y, rx, ry, n_=24):
        return hpoly(ell(x, y, rx, ry, n=n_))

    pat = pal["pattern"]
    base, sec, light, ol = pal["base"], pal["sec"], pal["light"], pal["outline"]
    L = Layer(pal)
    surf = p["surf"]
    clip = surf if mode in ("sit", "loaf", "groom") else None
    flen = p["flen"]

    # ---- legs
    def front_leg(paw):
        a, b = 6.2 * flen, 6.6 * flen
        elbow, wrist = ik(FJ, (paw[0] - 0.3, paw[1] - 1.2), a, b, +1)
        paw = (wrist[0] + 0.3, wrist[1] + 1.2)
        shapes = [capsule(FJ, elbow, 2.4, 1.8), capsule(elbow, wrist, 1.6, 1.4), ell(paw[0] + 0.7, paw[1], 2.2, 1.5, n=16)]
        return shapes, (FJ, elbow, wrist, paw)

    def hind_leg(paw, beta):
        c = 4.8
        hock_t = (paw[0] - c * math.sin(beta), paw[1] - c * math.cos(beta))
        knee, hock = ik(HJ, hock_t, 6.2, 6.2, -1)
        paw = (hock[0] + c * math.sin(beta), hock[1] + c * math.cos(beta))
        mid = lerp2(HJ, knee, 0.5)
        ang = math.atan2(knee[1] - HJ[1], knee[0] - HJ[0])
        hz = p["haunch"]
        shapes = [ell(mid[0], mid[1], 5.0 + 1.4 * hz, 3.3 + 1.5 * hz, ang, n=24), capsule(knee, hock, 1.8, 1.3),
                  capsule(hock, paw, 1.3, 1.3), ell(paw[0] + 0.6, paw[1], 2.2, 1.5, n=16)]
        return shapes, (HJ, knee, hock, paw)

    def leg_decor(joints, front):
        def deco(d):
            j0, j1, j2, pw = joints
            if pat == "tabby":
                for t in (0.45,):
                    q = lerp2(j1, j2, t)
                    d.line([q[0] - 2, q[1] - 0.5, q[0] + 2, q[1] + 0.5], fill=sec, width=1)
            elif pat == "tuxedo":
                q = lerp2(j1, j2, 0.45 if front else 0.2)
                d.polygon(capsule(q, pw, 2.4, 2.4), fill=light)
                d.polygon(ell(pw[0] + 0.7, pw[1], 3, 2.2), fill=light)
            elif pat == "siamese":
                q = lerp2(j1, j2, 0.15)
                d.polygon(capsule(q, pw, 2.6, 2.6), fill=sec)
                d.polygon(ell(pw[0] + 0.7, pw[1], 3, 2.2), fill=sec)
        return deco

    def draw_leg(name, dim):
        if name[0] == "f":
            shapes, j = front_leg(paws[name])
            L.part(shapes, base, leg_decor(j, True), dim=dim, clip_y=clip)
        else:
            shapes, j = hind_leg(paws[name], p["beta"][name])
            L.part(shapes, base, leg_decor(j, False), dim=dim, clip_y=clip)

    # ---- tail
    def tail_shapes():
        a0, curl, amp, ph = p["tail"]
        if mode == "loaf":
            B = add(add(Hp, u, -3.5), n, 3.0)
        else:
            B = add(add(Hp, u, -4.6), n, -2.2)
        pts = [B]
        segs = 8
        for i in range(segs):
            a = math.radians(a0 + curl * i + amp * math.sin(ph - i * 0.75) * (0.3 + i / segs))
            q = (pts[-1][0] - 2.1 * math.cos(a), pts[-1][1] - 2.1 * math.sin(a))
            sy = surf_at(wx(q[0]), p) - 2.0
            pts.append((q[0], min(q[1], sy)))
        shapes = []
        for i in range(segs):
            r0 = lerp(2.3, 1.45, i / segs)
            r1 = lerp(2.3, 1.45, (i + 1) / segs)
            shapes.append(capsule(pts[i], pts[i + 1], r0, r1))
        return shapes, pts

    def tail_decor(pts):
        def deco(d):
            if pat == "tabby":
                for i in (2, 4, 6):
                    a, b = pts[i], pts[i + 1]
                    m = lerp2(a, b, 0.5)
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    ln = math.hypot(dx, dy) or 1
                    nx, ny = -dy / ln * 3, dx / ln * 3
                    d.line([m[0] - nx, m[1] - ny, m[0] + nx, m[1] + ny], fill=sec, width=2)
                d.polygon(capsule(pts[7], pts[8], 2.2, 2.2), fill=sec)
            elif pat == "calico":
                d.polygon(hull(sum((ell(q[0], q[1], 2.6, 2.6, n=12) for q in pts[2:6]), [])), fill=pal["c1"])
                d.polygon(capsule(pts[6], pts[8], 2.5, 2.5), fill=sec)
            elif pat == "siamese":
                d.polygon(hull(sum((ell(q[0], q[1], 2.6, 2.6, n=12) for q in pts[2:]), [])), fill=sec)
        return deco

    def draw_tail():
        shapes, pts = tail_shapes()
        L.part(shapes, base, tail_decor(pts))

    # ---- body
    def body_shapes():
        sq = p.get("squash", 1.0)
        if mode == "loaf":
            br = p.get("breath", 0)
            chest = ell(S[0], S[1] + 0.8, 6.4, 5.4 + br * 0.5)
            hips = ell(Hp[0], Hp[1] + 0.8, 6.4, 5.4 + br * 0.5)
            torso = hull(chest + hips)
            belly = ell(R[0], R[1] + 1.0, 8.5, 6.0 + br * 0.5)
            return [torso, belly]
        chest = ell(S[0] + n[0] * 0.3, S[1] + n[1] * 0.3, 5.8, 5.8 * sq)
        hips = ell(Hp[0] + n[0] * 0.2, Hp[1] + n[1] * 0.2, 5.4, 5.4 * sq)
        torso = hull(chest + hips)
        bc = add(R, n, 1.5)
        belly = ell(bc[0], bc[1], 6.6, 4.5 * sq, -pitch)
        neck_a = add(add(S, n, -1.5), u, 1.5)
        neck = capsule(neck_a, hp(-1.0, 1.5), 3.6, 3.4)
        return [torso, belly, neck]

    def body_decor(d):
        if pat == "tabby":
            for t in (-0.85, -0.2, 0.45):
                a = add(add(R, u, sp * t), n, -6.5)
                b = add(add(R, u, sp * t - 1.2), n, -2.4)
                c = add(add(R, u, sp * t - 2.4), n, -0.2)
                d.polygon([add(a, u, -1.2), add(a, u, 1.2), b, c, add(b, u, -1.0)], fill=sec)
            bc = add(R, n, 5.2)
            d.polygon(ell(bc[0], bc[1], 8.5, 2.4, -pitch), fill=light)
            cc = add(add(S, n, 3.4), u, 3.0)
            d.polygon(ell(cc[0], cc[1], 3.2, 3.6, -pitch), fill=light)
        elif pat == "calico":
            a = add(add(R, u, -sp * 0.6), n, -2.8)
            d.polygon(ell(a[0], a[1], 5.6, 4.6, -pitch - 0.3), fill=pal["c1"])
            b = add(add(R, u, sp * 0.55), n, -4.2)
            d.polygon(ell(b[0], b[1], 4.0, 3.0, -pitch + 0.2), fill=sec)
            c = add(add(R, u, -sp * 1.0), n, 1.5)
            d.polygon(ell(c[0], c[1], 2.6, 2.0), fill=sec)
        elif pat == "tuxedo":
            cc = add(add(S, n, 3.6), u, 3.0)
            d.polygon(ell(cc[0], cc[1], 3.6, 5.0, -pitch), fill=light)
            bc = add(R, n, 5.6)
            d.polygon(ell(bc[0], bc[1], 6.5, 1.8, -pitch), fill=light)

    def draw_body():
        L.part(body_shapes(), base, body_decor, clip_y=clip)

    # ---- head
    def draw_head():
        far = hpoly([(-5.4, -1.6), (-3.9, -9.6), (-0.4, -4.4)])
        def far_deco(d):
            if pat == "siamese":
                d.polygon(far, fill=sec)
            if pat == "calico":
                d.polygon(far, fill=pal["c1"])
            d.polygon(hpoly([(-4.2, -2.6), (-3.8, -7.4), (-1.9, -4.0)]), fill=mul(PINK, 0.85))
        L.part([far], base, far_deco, dim=0.82)
        ear = [(-0.6, -3.6), (2.4, -10.2), (5.4, -2.4)]
        shapes = [hell(0, -0.6, 5.8, 5.0), hell(0.4, 1.7, 5.9, 3.4), hell(4.6, 2.1, 2.7, 2.2, 16), hpoly(ear)]

        def deco(d):
            if pat == "tabby":
                for x, y0, y1 in ((-1.4, -5.2, -3.6), (0.8, -5.4, -3.8)):
                    d.line([hp(x, y0), hp(x, y1)], fill=sec, width=1)
                d.line([hp(-5.0, 1.0), hp(-2.4, 1.2)], fill=sec, width=1)
                d.polygon(hell(4.0, 2.7, 3.4, 2.2, 16), fill=light)
                d.polygon(hell(1.8, 4.0, 3.0, 1.3, 16), fill=light)
            elif pat == "calico":
                d.polygon(hell(-3.4, -2.2, 3.8, 4.2), fill=pal["c1"])
                d.polygon(hpoly([(-0.6, -3.6), (2.4, -10.2), (5.4, -2.4), (2.4, -1.4)]), fill=sec)
                d.polygon(hell(4.0, 2.7, 3.4, 2.2, 16), fill=light)
            elif pat == "tuxedo":
                d.polygon(hell(4.0, 2.8, 3.6, 2.4, 16), fill=light)
                d.polygon(hell(1.6, 4.0, 3.4, 1.5, 16), fill=light)
                d.polygon(hpoly([(2.6, 0.6), (4.6, -1.2), (5.2, 1.4)]), fill=light)
            elif pat == "siamese":
                d.polygon(hell(3.2, 1.6, 4.4, 3.4), fill=sec)
                d.polygon(hpoly(ear), fill=sec)
            d.polygon(hpoly([(0.6, -3.9), (2.4, -8.5), (4.1, -3.0)]), fill=PINK)
        L.part(shapes, base, deco)
        # eye
        e = hp(2.4, -0.4)
        ex, ey = round(e[0]), round(e[1])
        if p["eye"] == "open":
            for dx in (-1, 0, 1):
                L.px((ex + dx, ey - 2), ol)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    L.px((ex + dx, ey + dy), pal["eye"])
            for dy in (-1, 0, 1):
                L.px((ex, ey + dy), (20, 18, 24))
            L.px((ex + 1, ey + 1), mul(pal["eye"], 0.75)); L.px((ex - 1, ey + 1), mul(pal["eye"], 0.75))
            L.px((ex - 1, ey - 1), (255, 255, 255))
        else:
            L.px((ex - 1, ey), ol); L.px((ex, ey + 1), ol); L.px((ex + 1, ey), ol)
        # nose, mouth, tongue, whiskers
        L.px(hp(6.9, 0.9), NOSE); L.px(hp(6.2, 0.6), NOSE)
        L.px(hp(6.0, 3.4), ol); L.px(hp(5.0, 3.9), ol)
        if p.get("tongue"):
            L.px(hp(6.4, 4.4), PINK); L.px(hp(6.8, 4.8), NOSE)
        wcol = (226, 226, 232) if pat != "tuxedo" else (250, 250, 250)
        d = ImageDraw.Draw(L.img)
        d.line([hp(7.2, 2.0), hp(10.4, 1.2)], fill=wcol + (255,))
        d.line([hp(7.2, 3.0), hp(10.2, 4.2)], fill=wcol + (255,))

    def draw_collar():
        nv = (S[0] - Hc[0], S[1] - Hc[1])
        ln = math.hypot(*nv) or 1
        nv = (nv[0] / ln, nv[1] / ln)
        perp = (-nv[1], nv[0])
        if perp[0] < 0:
            perp = (-perp[0], -perp[1])
        cc = add(add(Hc, nv, 5.6), perp, -0.6)
        a, b = add(cc, perp, -3.4), add(cc, perp, 3.0)
        L.part([capsule(a, b, 0.9, 0.9)], pal["acc"], hard=True)
        tag = add(add(b, nv, 1.9), perp, -0.3)
        L.part([ell(tag[0], tag[1], 0.8, 0.9, n=12)], pal["acc_light"], hard=True)

    if mode == "loaf":
        draw_body()
        draw_tail()
        pa = (S[0] + 5.6, surf - 1.6)
        L.part([ell(pa[0], pa[1], 2.4, 1.5, n=16)], light if pat == "tuxedo" else (sec if pat == "siamese" else base), clip_y=clip)
        draw_collar()
        draw_head()
    else:
        draw_leg("hr", 0.74)
        draw_leg("fr", 0.74)
        draw_tail()
        draw_body()
        draw_leg("hl", 1.0)
        draw_leg("fl", 1.0)
        draw_head()
        draw_collar()
    return ImageOps.mirror(L.img) if face < 0 else L.img

def surf_at(x, p):
    if p.get("on_crate") and CRATE_X0 <= x <= CRATE_X1:
        return CRATE_TOP
    return FLOOR

# ----------------------------------------------------------------- scenery --
WOOD_OL = (58, 36, 26)

def scenery(pal, yarn_dx=0.0):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # floor plank
    d.rectangle([2, FLOOR, W - 3, FLOOR + 6], fill=WOOD_OL)
    d.rectangle([3, FLOOR + 1, W - 4, FLOOR + 5], fill=(150, 98, 58))
    d.line([3, FLOOR + 1, W - 4, FLOOR + 1], fill=(190, 134, 84))
    d.line([3, FLOOR + 5, W - 4, FLOOR + 5], fill=(118, 76, 44))
    for x0, y, ln in ((8, 3, 9), (30, 4, 6), (52, 3, 11), (70, 4, 5), (96, 3, 8), (112, 4, 6), (20, 2, 4)):
        d.line([x0, FLOOR + y, x0 + ln, FLOOR + y], fill=(128, 82, 48))
    for x in (46, 92):
        d.line([x, FLOOR + 1, x, FLOOR + 5], fill=WOOD_OL)
    # crate
    x0, x1, y0, y1 = CRATE_X0, CRATE_X1, CRATE_TOP, FLOOR
    d.rectangle([x0, y0, x1, y1], fill=WOOD_OL)
    d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=(184, 132, 78))
    d.rectangle([x0 + 1, y0 + 1, x1 - 1, y0 + 3], fill=(214, 164, 104))
    d.line([x0 + 1, y0 + 1, x1 - 1, y0 + 1], fill=(236, 192, 132))
    d.line([x0 + 1, y0 + 4, x1 - 1, y0 + 4], fill=WOOD_OL)
    d.line([x0 + 5, y0 + 10, x1 - 5, y0 + 10], fill=(132, 88, 50))
    d.polygon([(x0 + 5, y1 - 2), (x0 + 5, y1 - 4), (x1 - 7, y0 + 5), (x1 - 5, y0 + 5), (x1 - 5, y0 + 7), (x0 + 7, y1 - 1)], fill=(206, 154, 96))
    d.line([(x0 + 7, y1 - 1), (x1 - 5, y0 + 7)], fill=(140, 94, 54))
    for xa in (x0 + 1, x1 - 4):
        d.rectangle([xa, y0 + 5, xa + 3, y1 - 1], fill=(200, 148, 90))
        xl = xa + 3 if xa == x0 + 1 else xa - 1
        d.line([xl, y0 + 5, xl, y1 - 1], fill=WOOD_OL)
        d.line([xa + 1, y0 + 5, xa + 1, y1 - 1], fill=(222, 172, 112))
    d.rectangle([x0 + 5, y1 - 1, x1 - 5, y1 - 1], fill=(140, 94, 54))
    for xa in (x0 + 2, x1 - 3):
        for ya in (y0 + 7, y1 - 3):
            d.point((xa + (1 if xa == x0 + 2 else -1), ya), fill=(96, 70, 52))
    # yarn
    cx, cy, r = YARN_X + yarn_dx, YARN_Y, YARN_R
    acc, dk, lt = pal["acc"], pal["acc_dark"], pal["acc_light"]
    rot = -yarn_dx / r
    d.line([(cx + 2, FLOOR - 1), (cx + 7, FLOOR - 1), (cx + 9, FLOOR - 2), (cx + 13, FLOOR - 1)], fill=acc)
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon(ell(cx, cy, r, r), fill=255)
    ball = Image.new("RGBA", (W, H), acc + (255,))
    bd = ImageDraw.Draw(ball)
    for k in range(3):
        a = rot + k * math.pi / 3
        c, s = math.cos(a), math.sin(a)
        pts = [(cx + (t * c - 1.6 * math.sin(t * 0.9) * s), cy + (t * s + 1.6 * math.sin(t * 0.9) * c)) for t in [i * 0.5 - 5 for i in range(21)]]
        bd.line(pts, fill=dk)
    shadow = ImageChops.subtract(m, ImageChops.offset(m, -1, -2))
    ball = Image.composite(ImageChops.multiply(ball, Image.new("RGBA", (W, H), (190, 186, 210, 255))), ball, shadow)
    bd = ImageDraw.Draw(ball)
    bd.point([(round(cx - 2), round(cy - 2)), (round(cx - 1), round(cy - 3))], fill=lt)
    ring = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(3)), m)
    img.paste(mul(acc, 0.32) + (255,), mask=ring)
    img.paste(ball, mask=m)
    return img

def draw_z(img, x, y, s, color):
    ImageDraw.Draw(img).line([(x, y), (x + s, y), (x, y + s), (x + s, y + s)], fill=color + (255,))

# ------------------------------------------------------------------- poses --
NEUT = {"fl": 7.5, "fr": 9.0, "hl": -6.0, "hr": -4.5}

def pose(x, surf, face, **kw):
    p = dict(x=x, y=surf - STAND_H, face=face, pitch=0.0, spine=SPINE, flen=1.0, hoff=(5.6, -8.0), tilt=0.0,
             tail=(38.0, 10.0, 8.0, 0.0), eye="open", mode="stand", haunch=0.0, surf=surf, tongue=False,
             on_crate=surf == CRATE_TOP, beta={"hl": 0.35, "hr": 0.35})
    p["paws"] = {k: (x + face * v, surf - 2) for k, v in NEUT.items()}
    p.update(kw)
    return p

def sit(x, surf, face, **kw):
    pitch = 0.78
    hp_y = surf - 6.4
    y = hp_y - SPINE * math.sin(pitch)
    hx = x - face * SPINE * math.cos(pitch)
    p = pose(x, surf, face, y=y, pitch=pitch, flen=1.05, haunch=1.0, mode="sit", hoff=(2.2, -8.6),
             tail=(-30.0, 15.0, 9.0, 0.0), beta={"hl": 1.45, "hr": 1.45})
    p["paws"] = {"fl": (x + face * 7.8, surf - 2), "fr": (x + face * 9.2, surf - 2),
                 "hl": (hx + face * 4.6, surf - 2), "hr": (hx + face * 6.0, surf - 2)}
    p.update(kw)
    return p

NUM = ("x", "y", "pitch", "flen", "tilt", "haunch", "spine")

def blend(a, b, t):
    if a["face"] != b["face"]:
        return b
    p = dict(b)
    for k in NUM:
        p[k] = lerp(a[k], b[k], t)
    p["hoff"] = lerp2(a["hoff"], b["hoff"], t)
    p["paws"] = {}
    for k in b["paws"]:
        pa, pb = a["paws"][k], b["paws"][k]
        q = lerp2(pa, pb, t)
        if abs(pa[0] - pb[0]) >= 1 and pa[1] >= a["surf"] - 2.01 and pb[1] >= b["surf"] - 2.01:
            q = (q[0], q[1] - min(2.4, 0.8 + 0.4 * abs(pa[0] - pb[0])) * math.sin(math.pi * t))  # step, don't slide
        p["paws"][k] = q
    p["beta"] = {k: lerp(a["beta"][k], b["beta"][k], t) for k in b["beta"]}
    p["tail"] = tuple(lerp(x, y, t) for x, y in zip(a["tail"], b["tail"]))
    return p

class Seq:
    def __init__(self):
        self.f = []

    def add(self, poses, n=0, prev=None):
        prev = prev or (self.f[-1] if self.f else None)
        if prev and n:
            for i in range(min(n, len(poses))):
                poses[i] = blend(prev, poses[i], smooth((i + 1) / (n + 1)))
        self.f += poses

    def last(self):
        return self.f[-1]

def gait(x0, x1, surf, face, N, stride, duty, phases, lift, k0=0, run=False, **kw):
    v = stride / (duty * N)
    n = max(1, round(abs(x1 - x0) / v))
    out = []
    for i in range(n):
        k = k0 + i
        x = x0 + face * v * i
        paws = {}
        for leg, ph in phases.items():
            u_ = (k / N + ph) % 1
            if u_ < duty:
                rel, lf = stride / 2 - stride * u_ / duty, 0.0
            else:
                s = (u_ - duty) / (1 - duty)
                rel, lf = -stride / 2 + stride * smooth(s), lift * math.sin(math.pi * s)
            paws[leg] = (x + face * (NEUT[leg] + rel), surf - 2 - lf)
        w = 2 * math.pi * k / N
        if run:
            p = pose(x, surf, face, paws=paws, y=surf - STAND_H + 1 - 1.4 * abs(math.sin(w)),
                     pitch=0.1 * math.sin(w + 0.6), spine=SPINE + 1.1 * math.cos(w - 2 * math.pi * 0.45),
                     hoff=(6.5, -6.6), tilt=-0.1, tail=(12.0, 2.0, 6.0, w), **kw)
        else:
            p = pose(x, surf, face, paws=paws, tail=(34.0, 9.0, 9.0, w * 0.5),
                     hoff=(5.6, -7.4 + 0.4 * math.sin(2 * w)), **kw)
        out.append(p)
    return out, x0 + face * v * n

WALK = {"hl": 0.0, "fl": 0.25, "hr": 0.5, "fr": 0.75}
RUN = {"hl": 0.0, "hr": 0.1, "fl": 0.5, "fr": 0.6}

def jump(prev, x1, surf1, h, nA=3, nF=8, nL=3, far=False):
    """Crouch, leap along a parabola from prev's spot to (x1, surf1) and land."""
    f, x0, s0 = prev["face"], prev["x"], prev["surf"]
    y0, y1 = s0 - STAND_H, surf1 - STAND_H
    st0 = pose(x0, s0, f, tail=prev["tail"])
    out = []
    for i in range(nA):
        t = smooth((i + 1) / nA)
        p = pose(x0, s0, f, y=y0 + 3.6 * t, pitch=-0.12 * t, hoff=(5.8, -6.6 + 0.6 * t),
                 tail=(lerp(prev["tail"][0], 20, t), 6.0, 4.0, prev["tail"][3]), beta={"hl": 0.35 + 0.5 * t, "hr": 0.35 + 0.5 * t})
        p["paws"] = st0["paws"]
        out.append(p)
    crouch = out[-1]
    rel0 = {k: (f * (v[0] - x0), v[1] - crouch["y"]) for k, v in crouch["paws"].items()}
    reach = 2.0 if far else 0.0
    keys = [
        (0.0, rel0, 0.85),
        (0.2, {"fl": (12.5 + reach, 5.0), "fr": (13.5 + reach, 4.0), "hl": (-12.0, 12.0), "hr": (-11.0, 12.5)}, -0.6),
        (0.5, {"fl": (11.0, 8.5), "fr": (12.0, 8.0), "hl": (-3.5, 10.5), "hr": (-2.5, 10.0)}, 0.8),
        (0.8, {"fl": (11.5 + reach, 12.5), "fr": (12.5 + reach, 12.0), "hl": (-8.0, 11.0), "hr": (-7.0, 11.0)}, 0.3),
        (1.0, {k: (v, STAND_H - 2) for k, v in NEUT.items()}, 0.35),
    ]
    for i in range(nF):
        t = (i + 1) / (nF + 1)
        x = lerp(x0, x1, t)
        y = lerp(y0 + 3.6, y1, t) - 4 * h * t * (1 - t)
        pitch = 0.5 * math.cos(math.pi * min(1, t * 1.1))
        for j in range(len(keys) - 1):
            if keys[j][0] <= t <= keys[j + 1][0]:
                ka, kb = keys[j], keys[j + 1]
                break
        s = smooth((t - ka[0]) / (kb[0] - ka[0]))
        paws = {k: (x + f * lerp(ka[1][k][0], kb[1][k][0], s), y + lerp(ka[1][k][1], kb[1][k][1], s)) for k in NEUT}
        beta = lerp(ka[2], kb[2], s)
        c, sn = math.cos(pitch * 0.7), math.sin(pitch * 0.7)
        hoff = (5.5 * c - 7.5 * sn, -5.5 * sn - 7.5 * c)
        tail_a = lerp(10, -20, t) if t > 0.5 else lerp(20, 10, t * 2)
        p = pose(x, surf1, f, y=y, pitch=pitch, paws=paws, hoff=hoff, tilt=-pitch * 0.6,
                 tail=(tail_a, 4.0, 5.0, t * 4), beta={"hl": beta, "hr": beta}, on_crate=False)
        out.append(p)
    for i in range(nL):
        t = (i + 1) / nL
        dip = 3.2 * math.sin(math.pi * (0.5 + 0.5 * t)) if i < nL - 1 else 0.6
        p = pose(x1, surf1, f, y=y1 + dip, pitch=-0.08 * (1 - t), hoff=(5.8, -6.8 + 0.6 * (1 - t)),
                 tail=(lerp(-10, 34, t), lerp(4, 9, t), 6.0, 0.0), beta={"hl": 0.35 + 0.4 * (1 - t), "hr": 0.35 + 0.4 * (1 - t)})
        out.append(p)
    return out

def tail_swish(p, k, period, amp=10.0):
    a0, curl, _, _ = p["tail"]
    p["tail"] = (a0, curl, amp, 2 * math.pi * k / period)
    return p

# ------------------------------------------------------------------- moods --
def mood_sleep():
    frames, n = [], 12
    for k in range(n):
        br = 0.5 + 0.5 * math.sin(2 * math.pi * k / n)
        p = pose(102, CRATE_TOP, 1, mode="loaf", y=CRATE_TOP - 7.6 - br * 0.6, hoff=(4.4, -2.8 + br * 0.4), tilt=-0.08,
                 eye="closed", tail=(-88.0, -24.0, 3.0 if k in (4, 5, 6) else 0.0, 2 * math.pi * k / 3))
        p["breath"] = br
        frames.append((p, {"z": k / n}))
    return frames

def mood_sit():
    frames, n, x = [], 40, 54
    for k in range(n):
        p = sit(x, FLOOR, 1)
        tail_swish(p, k, 20, 12.0)
        if k in (5, 6, 33):
            p["eye"] = "closed"
        j = k - 14
        if 0 <= j < 14:
            g = smooth(j / 3) if j < 3 else (smooth((13 - j) / 3) if j > 10 else 1.0)
            hx = x + SPINE * math.cos(p["pitch"]) + p["hoff"][0]
            hy = p["y"] - SPINE * math.sin(p["pitch"]) + p["hoff"][1]
            licking = 3 <= j <= 10
            lick = 0.8 * math.sin(k * 2.2) if licking else 0
            target = (hx + 4.2, hy + 5.2 + lick)
            p["paws"]["fl"] = lerp2(p["paws"]["fl"], target, g)
            p["tilt"] = -0.28 * g
            p["hoff"] = (p["hoff"][0] + 0.6 * g, p["hoff"][1] + 1.0 * g)
            if licking:
                p["eye"] = "closed"
                p["tongue"] = k % 2 == 0
        frames.append((p, {}))
    return frames

def mood_stroll():
    s = Seq()
    xa, xb, xc = 38.0, 62.0, 99.0
    s.add([pose(xa, FLOOR, 1)])
    w, xe = gait(xa, xb, FLOOR, 1, 14, 10.0, 0.6, WALK, 2.8)
    s.add(w, 3)
    s.add([pose(xe, FLOOR, 1, tail=s.last()["tail"])], 2)
    s.add(jump(s.last(), xc, CRATE_TOP, 9.0))
    sits = []
    for k in range(12):
        p = sit(xc, CRATE_TOP, 1, on_crate=True)
        tail_swish(p, k, 12, 11.0)
        if k in (7, 8):
            p["eye"] = "closed"
        sits.append(p)
    s.add(sits, 4)
    up = pose(xc, CRATE_TOP, 1)
    s.add([up], 2)
    s.add([pose(xc, CRATE_TOP, -1)])
    s.add(jump(s.last(), xb, FLOOR, 5.0))
    s.add([pose(xb, FLOOR, -1)], 1)
    w, xe = gait(xb, xa, FLOOR, -1, 14, 10.0, 0.6, WALK, 2.8)
    s.add(w, 3)
    rest = []
    for k in range(6):
        p = pose(xa, FLOOR, -1, hoff=(6.3, -6.6), tilt=-0.22)
        tail_swish(p, k, 6, 10.0)
        if k in (3, 4):
            p["eye"] = "closed"
        rest.append(p)
    s.add(rest, 3)
    return [(p, {}) for p in s.f]

def mood_zoomies():
    s = Seq()
    xa, xb, xc, xd = 34.0, 58.0, 98.0, 52.0
    s.add([pose(xa, FLOOR, 1)])
    r, xe = gait(xa, xb, FLOOR, 1, 8, 12.0, 0.4, RUN, 3.5, run=True)
    s.add(r, 2)
    s.add(jump(pose(xe, FLOOR, 1, tail=s.last()["tail"]), xc, CRATE_TOP, 14.0, nA=2, nF=9, nL=2), 2)
    wig = []
    for k in range(6):
        p = pose(xc, CRATE_TOP, 1, y=CRATE_TOP - STAND_H + 2.5, pitch=-0.14, hoff=(6.2, -6.0),
                 tail=(8.0, 3.0, 14.0, k * 2.4), beta={"hl": 0.7, "hr": 0.7})
        p["spine"] = SPINE - 0.5
        wig.append(p)
    s.add(wig, 2)
    s.add([pose(xc, CRATE_TOP, -1, y=CRATE_TOP - STAND_H + 2)])
    s.add(jump(s.last(), xd, FLOOR, 10.0, nA=2, nF=10, nL=2, far=True))
    r, xe = gait(xd, xa, FLOOR, -1, 8, 12.0, 0.4, RUN, 3.5, run=True, k0=4)
    s.add(r, 2)
    s.add([pose(xa, FLOOR, -1, hoff=(6.0, -6.5))], 2)
    swat = []
    keys = [(0, 0), (-1.5, -5.0), (-3.5, -8.5), (-7.0, -4.0), (-8.5, -1.0), (-4.0, -2.0), (0, 0)]
    for dx, dy in keys:
        p = pose(xa, FLOOR, -1, hoff=(6.4, -6.2), tilt=-0.12, pitch=0.06 if dy < -3 else 0.0)
        fx, fy = p["paws"]["fl"]
        p["paws"]["fl"] = (fx - p["face"] * dx, fy + dy)
        swat.append(p)
    i0 = len(s.f)
    s.add(swat)
    s.add([pose(xa, FLOOR, -1, hoff=(6.2, -6.8)) for _ in range(3)], 2)
    frames = [(p, {}) for p in s.f]
    # yarn: knocked left by the swat, then rolls back with the plank's tilt
    hit = i0 + 4
    for i, (p, ex) in enumerate(frames):
        j = (i - hit) % len(frames)
        ex["yarn"] = -4.5 * smooth((j + 1) / 4) if j < 4 else -4.5 * (1 - smooth((j - 3) / 22))
    return frames

def build(total, pal):
    if total == 0:
        mood, frames, dur = "sleeping", mood_sleep(), 170
    elif total < 5:
        mood, frames, dur = "sitting", mood_sit(), 110
    elif total < 15:
        mood, frames, dur = "strolling", mood_stroll(), 70
    else:
        mood, frames, dur = "zoomies", mood_zoomies(), 60
    out, cache = [], {}
    for p, ex in frames:
        yd = round(ex.get("yarn", 0.0))
        if yd not in cache:
            cache[yd] = scenery(pal, yd)
        img = cache[yd].copy()
        img.alpha_composite(render_cat(p, pal))
        if "z" in ex:
            for j, (s_, ph) in enumerate(((2, 0.0), (3, 0.5))):
                t = (ex["z"] + ph) % 1
                if t < 0.92:
                    draw_z(img, round(115 + 6 * t + j * 2), round(19 - 15 * t), s_, (132, 150, 214))
        out.append(img)
    return mood, out, dur

# -------------------------------------------------------------------- data --
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

def languages(login, token):
    q = """query($l:String!){user(login:$l){repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
           nodes{languages(first:8, orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}"""
    repos = gql(q, {"l": login}, token)["user"]["repositories"]["nodes"]
    total, colors = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            if name in IGNORED:
                continue
            total[name] = total.get(name, 0) + e["size"] * WEIGHT.get(name, 1.0)
            colors[name] = e["node"]["color"]
    return [(n, colors[n]) for n in sorted(total, key=total.get, reverse=True)]

def parse_langs(s):
    out = []
    for item in s.split(","):
        if ":" in item:
            name, col = item.rsplit(":", 1)
            out.append((name.strip(), col.strip()))
    return out

# -------------------------------------------------------------------- main --
def save_gif(frames, dur, path):
    """One global palette (index 0 = transparent) shared by every frame."""
    colors, data = {}, []
    for f in frames:
        b = f.convert("RGBA").tobytes()
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

def main():
    args = sys.argv[1:]
    langs = None
    if "--langs" in args:
        i = args.index("--langs")
        langs = parse_langs(args[i + 1])
        del args[i:i + 2]
    login = os.environ.get("KOI_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    total = int(args[0]) if args else activity(login, token)
    if langs is None:
        try:
            langs = languages(login, token)
        except Exception as e:  # never break the workflow over the coat
            print(f"languages unavailable ({e}); using the default orange tabby")
            langs = []
    pal = palette(langs)
    mood, frames, dur = build(total, pal)
    path = os.environ.get("CAT_OUT", "cat/cat.gif")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    save_gif(frames, dur, path)
    top = ", ".join(n for n, _ in langs[:3]) or "default"
    print(f"{login}: {total} contributions in the last 7 days -> {mood}; "
          f"{pal['pattern']} coat from {top}; {len(frames)} frames, {os.path.getsize(path) // 1024} KB")

if __name__ == "__main__":
    main()
