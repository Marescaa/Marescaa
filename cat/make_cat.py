"""Draws a pixel-art cat whose mood depends on the last 7 days of GitHub activity."""
import json, os, sys, urllib.request, datetime
from PIL import Image

SCALE, W, H = 6, 48, 24
OUT, C, D, L, P, E, Z = (70, 45, 35), (233, 150, 70), (199, 108, 44), (250, 228, 195), (240, 130, 145), (30, 30, 30), (130, 150, 200)

def activity(login, token):
    q = """query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""
    req = urllib.request.Request("https://api.github.com/graphql",
        data=json.dumps({"query": q, "variables": {"l": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req))
    days = [d for w in data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    today = datetime.date.today().isoformat()
    days = [d for d in days if d["date"] < today]  # completed days only
    return sum(d["contributionCount"] for d in days[-7:])

def rect(px, x0, x1, y0, y1, c):
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            px[(x, y)] = c

def outline(px):
    out = {}
    for (x, y) in px:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in px:
                out[n] = OUT
    px.update(out)

TAILS = [[(5, 10), (4, 9), (3, 8), (3, 7), (3, 6)],
         [(5, 10), (4, 10), (3, 9), (2, 8), (2, 7)],
         [(5, 10), (4, 10), (3, 10), (2, 9), (1, 8)],
         [(5, 10), (4, 10), (3, 9), (2, 8), (2, 7)]]

def head(px, hx, hy, blink=False, closed=False):
    rect(px, hx, hx + 6, hy, hy + 6, C)
    for x, y in ((hx, hy - 1), (hx, hy - 2), (hx + 1, hy - 1), (hx + 6, hy - 1), (hx + 6, hy - 2), (hx + 5, hy - 1)):
        px[(x, y)] = C
    px[(hx + 1, hy - 1)] = P; px[(hx + 5, hy - 1)] = P
    rect(px, hx + 5, hx + 6, hy + 4, hy + 6, L)
    px[(hx + 6, hy + 4)] = P
    if closed or blink:
        px[(hx + 4, hy + 2)] = D; px[(hx + 3, hy + 2)] = D
    else:
        px[(hx + 4, hy + 2)] = E
    px[(hx + 1, hy + 4)] = D; px[(hx + 2, hy + 6)] = D

def walker(k, ox, bob, blink):
    px = {}
    rect(px, 6, 19, 9, 14, C)
    rect(px, 7, 18, 14, 14, L)
    for x in (9, 12, 15):
        rect(px, x, x, 9, 10, D)
    for i, lx in enumerate((7, 9, 16, 18)):
        lift = (k + i) % 4 == 0
        rect(px, lx + (1 if lift else 0), lx + (1 if lift else 0), 15, 17 - (1 if lift else 0), C if i % 2 else D)
    for x, y in TAILS[k % 4]:
        px[(x, y)] = C
    head(px, 19, 6, blink)
    return place(px, ox, bob)

def sitter(k, blink):
    px = {}
    rect(px, 9, 16, 9, 17, C)
    rect(px, 15, 16, 11, 17, L)
    rect(px, 9, 11, 12, 17, D)
    rect(px, 13, 14, 15, 17, L)
    head(px, 13, 3, blink)
    wag = [0, 1, 2, 1][k % 4]
    for i, x in enumerate(range(8, 2, -1)):
        px[(x, 17 - (wag if i > 2 else 0))] = C
    return place(px, 8, 0)

def sleeper(k):
    px = {}
    rect(px, 6, 22, 13, 18, C)
    rect(px, 7, 21, 18, 18, L)
    for x in (9, 12, 15, 18):
        rect(px, x, x, 13, 14, D)
    rect(px, 17, 23, 12, 17, C)
    rect(px, 17, 19, 12, 12, 0) if False else None
    for x, y in ((17, 10), (17, 11), (18, 10), (23, 10), (23, 11), (22, 10)):
        px[(x, y)] = C
    px[(18, 10)] = P; px[(22, 10)] = P
    rect(px, 22, 23, 15, 17, L); px[(23, 15)] = P
    px[(21, 14)] = E; px[(20, 14)] = E
    rect(px, 4, 5, 16, 18, C)  # tail tucked
    breath = 1 if k % 4 in (1, 2) else 0
    for p in list(px):
        if p[1] <= 14 and p[0] < 17:
            px[(p[0], p[1])] = px.pop(p)
    img = place(px, 8, 0, breath)
    # floating z's
    zy = 8 - (k % 6)
    for n, (zx, s) in enumerate(((30, 2), (33, 3))):
        yy = zy - n * 3
        if yy < 1: continue
        for dx in range(s): img.putpixel((zx + dx, yy), Z + (255,))
        for d in range(s - 1): img.putpixel((zx + s - 2 - d, yy + 1 + d), Z + (255,))
        for dx in range(s): img.putpixel((zx + dx, yy + s), Z + (255,))
    return img

def place(px, ox, bob, breath=0):
    px = dict(px)
    outline(px)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for (x, y), c in px.items():
        X, Y = x + ox, y + 3 - bob + breath * (1 if y < 14 and False else 0)
        if 0 <= X < W and 0 <= Y < H:
            img.putpixel((X, Y), tuple(c) + (255,))
    return img

def build(total):
    frames, dur = [], 120
    if total == 0:
        mood = "sleeping"; frames = [sleeper(k) for k in range(12)]; dur = 280
    elif total < 5:
        mood = "sitting"; frames = [sitter(k, blink=(k in (9, 10))) for k in range(14)]; dur = 180
    elif total < 15:
        mood = "walking"; n = 28; frames = [walker(k, -27 + int(k * (W + 27) / n), 0, False) for k in range(n)]; dur = 90
    else:
        mood = "zoomies"; n = 16; frames = [walker(k, -27 + int(k * (W + 27) / n), 1 if k % 2 else 0, False) for k in range(n)]; dur = 60
    return mood, frames, dur

def main():
    login = os.environ.get("KOI_LOGIN") or os.environ["GITHUB_REPOSITORY_OWNER"]
    total = int(sys.argv[1]) if len(sys.argv) > 1 else activity(login, os.environ["GITHUB_TOKEN"])
    mood, frames, dur = build(total)
    out = [f.resize((W * SCALE, H * SCALE), Image.NEAREST) for f in frames]
    os.makedirs("cat", exist_ok=True)
    path = os.environ.get("CAT_OUT", "cat/cat.gif")
    out[0].save(path, save_all=True, append_images=out[1:], duration=dur, loop=0, disposal=2, transparency=0, optimize=False)
    print(f"{login}: {total} contributions in the last 7 days -> {mood}")

if __name__ == "__main__":
    main()
