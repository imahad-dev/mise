import io, math, sys
import uharfbuzz as hb, pathops
from fontTools.ttLib import TTFont
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.recordingPen import DecomposingRecordingPen

FD = sys.argv[1] + "/fonts-dl/node_modules/@fontsource/"


class F:
    def __init__(s, pkg, file):
        t = TTFont(FD + pkg + "/files/" + file)
        t.flavor = None
        b = io.BytesIO()
        t.save(b)
        s.t = TTFont(io.BytesIO(b.getvalue()))
        s.gs = s.t.getGlyphSet()
        s.order = s.t.getGlyphOrder()
        s.upm = s.t["head"].unitsPerEm
        s.hb = hb.Font(hb.Face(b.getvalue()))

    def shape(s, text, track=0):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(s.hb, buf, {"kern": True, "liga": True})
        x = 0
        out = []
        for i, p in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((s.order[i.codepoint], x + p.x_offset, p.y_offset))
            x += p.x_advance + track
        return out, x

    def path(s, text, size, x=0, y=0, track=0, keep=None, names=None):
        """y-down Path; baseline at y, left at x. keep(w_em, h_em) filters contours."""
        k = size / s.upm
        gl, _ = s.shape(text, track=track)
        p = pathops.Path()
        for name, gx, gy in gl:
            if names and not names(name):
                continue
            rec = DecomposingRecordingPen(s.gs)
            s.gs[name].draw(rec)
            cs, cur = [], []
            for o in rec.value:
                cur.append(o)
                if o[0] in ("closePath", "endPath"):
                    cs.append(cur)
                    cur = []
            for c in cs:
                pts = [q for o in c for q in o[1] if q]
                if not pts:
                    continue
                bw = max(a for a, _ in pts) - min(a for a, _ in pts)
                bh = max(b for _, b in pts) - min(b for _, b in pts)
                if keep and not keep(bw / s.upm, bh / s.upm):
                    continue
                pen = TransformPen(p.getPen(glyphSet=s.gs), (k, 0, 0, -k, x + gx * k, y - gy * k))
                for o, a in c:
                    getattr(pen, o)(*a)
        p.simplify(fix_winding=True, keep_starting_points=False)
        return p


def poly(pts):
    p = pathops.Path()
    n = p.getPen()
    n.moveTo(pts[0])
    for q in pts[1:]:
        n.lineTo(q)
    n.closePath()
    return p


def circle(cx, cy, r):
    p = pathops.Path()
    n = p.getPen()
    k = 0.5522847 * r
    n.moveTo((cx + r, cy))
    n.curveTo((cx + r, cy + k), (cx + k, cy + r), (cx, cy + r))
    n.curveTo((cx - k, cy + r), (cx - r, cy + k), (cx - r, cy))
    n.curveTo((cx - r, cy - k), (cx - k, cy - r), (cx, cy - r))
    n.curveTo((cx + k, cy - r), (cx + r, cy - k), (cx + r, cy))
    n.closePath()
    return p


U, D, I = pathops.PathOp.UNION, pathops.PathOp.DIFFERENCE, pathops.PathOp.INTERSECTION


def op(a, b, kind):
    return pathops.op(a, b, kind, fix_winding=True)


def union(*ps):
    r = ps[0]
    for q in ps[1:]:
        r = op(r, q, U)
    return r


def xf(p, a=1, b=0, c=0, d=1, e=0, f=0):
    r = pathops.Path()
    p.draw(TransformPen(r.getPen(), (a, b, c, d, e, f)))
    return r


def rot(p, deg, cx, cy):
    t = math.radians(deg)
    co, si = math.cos(t), math.sin(t)
    return xf(p, co, si, -si, co, cx - co * cx + si * cy, cy - si * cx - co * cy)


def soften(p, r):
    q = pathops.Path(p)
    q.stroke(2 * r, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    q.convertConicsToQuads()
    return union(p, q)


def d(p):
    n = SVGPathPen(None, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    p.draw(n)
    return n.getCommands()


def svg(w, h, layers, bg=None):
    body = f'<rect width="{w:.1f}" height="{h:.1f}" fill="{bg}"/>' if bg else ""
    body += "".join(f'<path fill="{c}" d="{d(p)}"/>' for p, c in layers)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}">{body}</svg>'


def box(p):
    return p.bounds
