import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0])))
from lib import *

OUT = sys.argv[1] + "/brand/out/"


def put(name, s):
    open(OUT + name + ".svg", "w", encoding="utf8").write(s)


WINE, SAND, EMBER = "#7F011F", "#F5EBDD", "#FF9A3D"
FOREST, LEAF = "#064734", "#E0FFC2"
BLUE, CREAM = "#014BAA", "#F8F3F0"
ORANGE, MILK = "#EC5E27", "#FDFDF1"

# ---------- Angeethi: the dots of the Urdu letters are coals
gul = F("gulzar", "gulzar-arabic-400-normal.woff")
roz = F("rozha-one", "rozha-one-latin-400-normal.woff")
word = "انگیٹھی"
S = 300
COALS = {"glyph00758", "glyph00715"}
letters = gul.path(word, S, 40, 330, names=lambda n: n not in COALS)
dots = gul.path(word, S, 40, 330, names=lambda n: n in COALS)
print("urdu", box(letters), box(dots))
bx = box(union(letters, dots))
letters = xf(letters, e=40 - bx[0], f=40 - bx[1])
dots = xf(dots, e=40 - bx[0], f=40 - bx[1])
bx = box(union(letters, dots))
W = bx[2] + 40
en = roz.path("ANGEETHI HOUSE", 74, 0, 0, track=60)
eb = box(en)
en = xf(en, e=(W - (eb[2] - eb[0])) / 2 - eb[0], f=bx[3] + 110)
W = max(W, box(en)[2] + 40)
H = box(en)[3] + 40
put("angeethi-lockup", svg(W, H, [(letters, SAND), (dots, EMBER), (en, SAND)]))
belly = op(xf(circle(100, 96, 78), d=0.98), poly([(0, 70), (200, 70), (200, 200), (0, 200)]), I)
rim = soften(poly([(20, 66), (180, 66), (180, 76), (20, 76)]), 4)
mouth = union(poly([(76, 172), (124, 172), (124, 132), (76, 132)]), circle(100, 132, 24))
feet = union(poly([(44, 160), (66, 160), (58, 190), (44, 190)]), poly([(134, 160), (156, 160), (156, 190), (142, 190)]))
braz = op(union(belly, rim, feet), mouth, D)
glow = xf(mouth, a=0.62, d=0.62, e=38, f=64)
coals = union(circle(72, 46, 15), circle(128, 46, 15), circle(100, 34, 17))
put("angeethi-mark", svg(200, 200, [(braz, SAND), (union(coals, glow), EMBER)], bg=WINE))

# ---------- Kehwa: bitten cup from above; the b loses a bite too
yng = F("young-serif", "young-serif-latin-400-normal.woff")
def crumb(cx, cy, r, seedv):
    pts = [(cx + r * (0.72 + 0.28 * ((seedv * (i + 3)) % 5) / 4) * math.cos(i * 1.257 + seedv), cy + r * (0.72 + 0.28 * ((seedv * (i + 2)) % 5) / 4) * math.sin(i * 1.257 + seedv)) for i in range(5)]
    return soften(poly(pts), r * 0.14)


def podp(cx, cy, L, Wd, deg):
    p = pathops.Path()
    n = p.getPen()
    n.moveTo((-L, 0))
    n.curveTo((-L * 0.45, -Wd), (L * 0.45, -Wd), (L, 0))
    n.curveTo((L * 0.45, Wd), (-L * 0.45, Wd), (-L, 0))
    n.closePath()
    return rot(xf(p, e=cx, f=cy), deg, cx, cy)


disc = circle(92, 108, 76)
bx_, by_ = 150, 50
bite = union(circle(bx_, by_, 44), circle(bx_ - 42, by_ - 6, 18), circle(bx_ + 8, by_ + 42, 18))
disc = op(disc, bite, D)
pod = op(podp(80, 120, 38, 20, -32), podp(80, 120, 26, 2.6, -32), D)
disc = op(disc, pod, D)
crumbs = union(crumb(168, 40, 11, 2), crumb(146, 22, 7, 3), crumb(182, 68, 6, 4))
put("kehwa-mark", svg(200, 200, [(union(disc, crumbs), LEAF)], bg=FOREST))
kw = yng.path("kehwa & crumb", 120, 30, 130)
b = box(kw)
kw = op(kw, union(circle(b[2] + 3, 130 - 44, 12), circle(b[2] + 1, 130 - 26, 7)), D)
fall = union(crumb(b[2] + 8, 130 + 8, 7, 2), crumb(b[2] - 12, 130 + 24, 5, 3), crumb(b[2] + 14, 130 + 34, 4, 4))
put("kehwa-lockup", svg(b[2] + 40, 190, [(union(kw, fall), LEAF)]))

# ---------- Noor: nun is a bowl, its one dot a sesame seed
ruq = F("aref-ruqaa", "aref-ruqaa-arabic-700-normal.woff")
rk = F("reem-kufi", "reem-kufi-latin-700-normal.woff")
def seed(cx, cy, s, deg):
    p = pathops.Path()
    n = p.getPen()
    n.moveTo((0, -s))
    n.curveTo((s * 0.72, -s * 0.3), (s * 0.62, s * 0.9), (0, s * 0.9))
    n.curveTo((-s * 0.62, s * 0.9), (-s * 0.72, -s * 0.3), (0, -s))
    n.closePath()
    return rot(xf(p, e=cx, f=cy), deg, cx, cy)


outer = xf(circle(0, 0, 1), a=80, d=112, e=100, f=66)
inner = xf(circle(0, 0, 1), a=54, d=88, e=100, f=54)
keep = poly([(0, 44), (200, 26), (200, 200), (0, 200)])
nun = union(op(op(outer, inner, D), keep, I), seed(100, 68, 28, 18))
put("noor-mark", svg(200, 200, [(xf(nun, f=4), CREAM)], bg=BLUE))
en = rk.path("Noor & Za'atar", 92, 230, 96)
ar = ruq.path("نور وزعتر", 92, 230, 200)
wb = box(en)
arb = box(ar)
ar = xf(ar, e=wb[2] - arb[2])
put("noor-lockup", svg(wb[2] + 30, 250, [(xf(nun, f=30), CREAM), (en, CREAM), (ar, CREAM)]))

# ---------- Tikka: the letters are pieces on a skewer
st = 40
hgt = 124


def T(x):
    return union(poly([(x, 0), (x + 100, 0), (x + 100, st - 4), (x, st - 4)]),
                 poly([(x + 30, 0), (x + 30 + st, 0), (x + 30 + st, hgt), (x + 30, hgt)])), 100


def Ii(x):
    return poly([(x, 0), (x + st + 2, 0), (x + st + 2, hgt), (x, hgt)]), st + 2


def K(x):
    return union(poly([(x, 0), (x + st, 0), (x + st, hgt), (x, hgt)]),
                 poly([(x + st - 2, 56), (x + 58, 0), (x + 104, 0), (x + 58, 54), (x + 108, hgt), (x + 60, hgt), (x + st - 2, 84)])), 108


def A(x):
    o = poly([(x + 40, 0), (x + 84, 0), (x + 124, hgt), (x + 80, hgt), (x + 74, 98), (x + 50, 98), (x + 44, hgt), (x, hgt)])
    return op(o, poly([(x + 62, 34), (x + 71, 72), (x + 53, 72)]), D), 124


x = 92
pieces = []
for fn, dg, dy in ((T, -3, 2), (Ii, 2.5, -4), (K, -2, 3), (K, 3, -3), (A, -2.5, 2)):
    p, w = fn(x)
    p = soften(p, 3)
    p = rot(xf(p, f=30 + dy), dg, x + w / 2, 92)
    pieces.append(p)
    x += w + 16
letters = union(*pieces)
y0 = 92
end = x + 66
shaft = poly([(40, y0 - 4.5), (end - 30, y0 - 4.5), (end, y0), (end - 30, y0 + 4.5), (40, y0 + 4.5)])
ringh = op(circle(36, y0, 22), circle(36, y0, 12), D)
cut = poly([(0, y0 - 7), (end + 10, y0 - 7), (end + 10, y0 + 7), (0, y0 + 7)])
letters = op(letters, cut, D)
stick = union(shaft, ringh)
bow = F("bowlby-one", "bowlby-one-latin-400-normal.woff")
lb = box(letters)
t0 = bow.path("TOWN", 88, 0, 0)
tr = ((lb[2] - lb[0]) - (box(t0)[2] - box(t0)[0])) / 3 * bow.upm / 88
town = bow.path("TOWN", 88, 0, 0, track=tr)
tb = box(town)
town = xf(town, e=lb[0] - tb[0], f=lb[3] + 100)
put("tikka-lockup", svg(end + 24, box(town)[3] + 24, [(union(letters, stick, town), MILK)]))
c = soften(poly([(-27, -42), (27, -42), (27, 42), (-27, 42)]), 6)
ps = [rot(xf(c, e=px, f=100), g, px, 100) for px, g in ((22, 6), (100, -5), (178, 4))]
cubes = op(union(*ps), poly([(-20, 90), (240, 90), (240, 110), (-20, 110)]), D)
sh = poly([(-20, 94), (226, 94), (258, 100), (226, 106), (-20, 106)])
rg = op(circle(-34, 100, 20), circle(-34, 100, 10), D)
art = xf(union(cubes, sh, rg), a=0.66, d=0.66, e=30, f=34)
put("tikka-mark", svg(200, 200, [(rot(art, -40, 100, 100), MILK)], bg=ORANGE))
