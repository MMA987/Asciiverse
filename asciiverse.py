#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 ASCIIVERSE  --  A Generative Art Studio for the Terminal
===============================================================================
 A single-file, zero-dependency Python program (standard library only).

 Nine rooms in the gallery
 ------------------------
   1  Mandelbrot explorer   -- zoomable, with curated coordinates
   2  Julia set gallery     -- the Mandelbrot's infinite family of cousins
   3  L-system botany       -- grammar-grown ferns, trees and Koch curves
   4  Maze forge            -- recursive-backtracker mazes, solved by BFS
   5  Game of Life          -- animated, with a pattern library
   6  Elementary automata   -- Wolfram's 256 one-dimensional universes
   7  Plasma field          -- smooth interference patterns in full colour
   8  Chaos game            -- Sierpinski and Barnsley's fern from pure chance
   9  Harmonograph          -- decaying pendulum curves and rose petals

 Run it
 ------
   python asciiverse.py             # interactive gallery
   python asciiverse.py --test      # run the self-test suite and exit
   python asciiverse.py --no-color  # plain output for pipes / old terminals

 Everything here is maths on a character grid. No images, no pip, no cheating.
 Python 3.8+.
===============================================================================
"""

import colorsys
import math
import os
import random
import sys
import time
from collections import deque

# =============================================================================
#  SECTION 1 -- TERMINAL CAPABILITIES
# =============================================================================
# Colour and Unicode are both optional. The program detects what the console
# can do and downgrades gracefully instead of crashing or spraying escape codes.


def enable_ansi() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:  # Windows 10+: enable VIRTUAL_TERMINAL_PROCESSING
        import ctypes

        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
        return True
    except Exception:
        return False


def unicode_ok() -> bool:
    try:
        "─│█▓▒░".encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


COLOR = enable_ansi() and "--no-color" not in sys.argv
FANCY = unicode_ok()
ANIMATE = sys.stdout.isatty()

RESET = "\033[0m" if COLOR else ""
BOLD = "\033[1m" if COLOR else ""
DIM = "\033[2m" if COLOR else ""


def rgb(r, g, b):
    """Truecolour foreground escape, or nothing when colour is off."""
    if not COLOR:
        return ""
    return "\033[38;2;%d;%d;%dm" % (int(r), int(g), int(b))


def hsv(h, s=1.0, v=1.0):
    """Hue in [0,1) -> an RGB tuple of ints. colorsys is standard library."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)


# Density ramps: dark to bright.
RAMP = " .:-=+*#%@" if not FANCY else " .:-=+*#%@"
BLOCKS = "░▒▓█" if FANCY else ".:*#"
SOLID = "█" if FANCY else "#"
HALF = "▄" if FANCY else "_"

GLYPH = {
    "h": "─" if FANCY else "-",
    "v": "│" if FANCY else "|",
    "tl": "┌" if FANCY else "+",
    "tr": "┐" if FANCY else "+",
    "bl": "└" if FANCY else "+",
    "br": "┘" if FANCY else "+",
    "dot": "•" if FANCY else "*",
    "arrow": "➜" if FANCY else ">",
}

WIDTH = 78

BANNER = r"""
    _    ____   ____ ___ ___ __     _______ ____  ____  _____
   / \  / ___| / ___|_ _|_ _|\ \   / / ____|  _ \/ ___|| ____|
  / _ \ \___ \| |    | | | |  \ \ / /|  _| | |_) \___ \|  _|
 / ___ \ ___) | |___ | | | |   \ V / | |___|  _ < ___) | |___
/_/   \_\____/ \____|___|___|   \_/  |_____|_| \_\____/|_____|
"""


def title(text):
    inner = WIDTH - 2
    print()
    print(rgb(120, 200, 255) + GLYPH["tl"] + GLYPH["h"] * inner + GLYPH["tr"] + RESET)
    print(rgb(120, 200, 255) + GLYPH["v"] + BOLD + text.center(inner) + RESET
          + rgb(120, 200, 255) + GLYPH["v"] + RESET)
    print(rgb(120, 200, 255) + GLYPH["bl"] + GLYPH["h"] * inner + GLYPH["br"] + RESET)


def info(text):
    print(rgb(140, 160, 200) + "  " + GLYPH["dot"] + " " + RESET + text)


def good(text):
    print(rgb(110, 220, 140) + "  [ok] " + RESET + text)


def warn(text):
    print(rgb(240, 200, 100) + "  [!]  " + RESET + text)


def fail(text):
    print(rgb(240, 110, 110) + "  [x]  " + RESET + text)


def ask(prompt, default=""):
    """input() that survives Ctrl+C, Ctrl+D and exhausted stdin."""
    try:
        raw = input(rgb(240, 200, 100) + "  " + GLYPH["arrow"] + " " + prompt + RESET + " ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return raw if raw else default


def ask_num(prompt, default, low=None, high=None, cast=int):
    while True:
        raw = ask(prompt, str(default))
        try:
            value = cast(raw)
        except ValueError:
            fail("Not a valid number.")
            continue
        if low is not None and value < low:
            fail("Minimum is %s." % low)
            continue
        if high is not None and value > high:
            fail("Maximum is %s." % high)
            continue
        return value


def pause():
    ask("press Enter for the gallery")


def clear():
    if ANIMATE:
        os.system("cls" if os.name == "nt" else "clear")


def home():
    """Move the cursor to the top-left without clearing: flicker-free frames."""
    if COLOR:
        sys.stdout.write("\033[H")


# =============================================================================
#  SECTION 2 -- THE CANVAS
# =============================================================================
class Canvas:
    """A grid of coloured characters. Everything in this program draws here.

    Terminal cells are roughly twice as tall as they are wide, so any routine
    that cares about proportion multiplies its y-scale by ~0.5.
    """

    def __init__(self, width, height, fill=" "):
        self.w = int(width)
        self.h = int(height)
        self.chars = [[fill] * self.w for _ in range(self.h)]
        self.colors = [[None] * self.w for _ in range(self.h)]

    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def plot(self, x, y, char=SOLID, color=None):
        xi, yi = int(round(x)), int(round(y))
        if self.in_bounds(xi, yi):
            self.chars[yi][xi] = char
            self.colors[yi][xi] = color

    def line(self, x0, y0, x1, y1, char=SOLID, color=None):
        """Bresenham's line algorithm: integer arithmetic, no floats, no gaps."""
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.plot(x0, y0, char, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def text(self, x, y, message, color=None):
        for i, ch in enumerate(message):
            self.plot(x + i, y, ch, color)

    def row_string(self, y):
        """One rendered row, emitting a colour code only when the colour changes."""
        out, last = [], None
        for x in range(self.w):
            col = self.colors[y][x]
            if col != last:
                out.append(RESET if col is None else rgb(*col))
                last = col
            out.append(self.chars[y][x])
        if last is not None:
            out.append(RESET)
        return "".join(out)

    def render(self):
        return "\n".join(self.row_string(y) for y in range(self.h))

    def show(self):
        print(self.render())


def ramp_char(t):
    """Map t in [0,1] to a density character."""
    t = max(0.0, min(1.0, t))
    return RAMP[min(len(RAMP) - 1, int(t * len(RAMP)))]


def fit_segments(segments, width, height, margin=1):
    """Scale a list of float line segments to fill the canvas, preserving shape."""
    xs = [p for seg in segments for p in (seg[0], seg[2])]
    ys = [p for seg in segments for p in (seg[1], seg[3])]
    if not xs:
        return []
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    spanx = maxx - minx or 1e-9
    spany = maxy - miny or 1e-9
    # 0.5 corrects for tall, narrow character cells.
    scale = min((width - 2 * margin) / spanx, (height - 2 * margin) / (spany * 0.5))
    out = []
    for x0, y0, x1, y1 in segments:
        out.append((
            margin + (x0 - minx) * scale,
            height - margin - (y0 - miny) * scale * 0.5,
            margin + (x1 - minx) * scale,
            height - margin - (y1 - miny) * scale * 0.5,
        ))
    return out


# =============================================================================
#  SECTION 3 -- ESCAPE-TIME FRACTALS
# =============================================================================
def mandel_escape(c, max_iter=80):
    """Iterate z = z^2 + c. Returns how many steps it took |z| to pass 2."""
    z = 0j
    for n in range(max_iter):
        z = z * z + c
        if (z.real * z.real + z.imag * z.imag) > 4.0:
            return n
    return max_iter


def julia_escape(z, c, max_iter=80):
    for n in range(max_iter):
        z = z * z + c
        if (z.real * z.real + z.imag * z.imag) > 4.0:
            return n
    return max_iter


def render_escape(width, height, cx, cy, zoom, max_iter, julia_c=None, hue_shift=0.0):
    """Shared renderer for Mandelbrot and Julia views."""
    canvas = Canvas(width, height)
    span_x = 3.0 / zoom
    span_y = span_x * (height / width) * 2.0  # character aspect correction
    for py in range(height):
        imag = cy + (py / (height - 1) - 0.5) * span_y
        for px in range(width):
            real = cx + (px / (width - 1) - 0.5) * span_x
            point = complex(real, imag)
            if julia_c is None:
                n = mandel_escape(point, max_iter)
            else:
                n = julia_escape(point, julia_c, max_iter)
            if n >= max_iter:
                canvas.plot(px, py, SOLID, (25, 25, 45))  # inside the set
            else:
                t = n / max_iter
                canvas.plot(px, py, ramp_char(0.25 + 0.75 * t),
                            hsv(hue_shift + 0.62 - 0.75 * t, 0.85, 0.35 + 0.65 * t))
    return canvas


MANDEL_SPOTS = [
    ("Full set", -0.6, 0.0, 1.0, 60),
    ("Seahorse valley", -0.745, 0.113, 40.0, 140),
    ("Elephant valley", 0.285, 0.010, 60.0, 160),
    ("Triple spiral", -0.088, 0.654, 120.0, 200),
    ("Mini brot", -1.749, 0.0, 300.0, 240),
]

JULIA_SPOTS = [
    ("Dendrite", complex(0.0, 1.0)),
    ("Douady rabbit", complex(-0.123, 0.745)),
    ("San Marco", complex(-0.75, 0.0)),
    ("Siegel disk", complex(-0.391, -0.587)),
    ("Lightning", complex(-0.8, 0.156)),
]


# =============================================================================
#  SECTION 4 -- L-SYSTEMS (GRAMMAR-GROWN PLANTS)
# =============================================================================
# An L-system is a string rewriting rule applied over and over, then read as
# turtle instructions. Two lines of grammar produce a convincing fern.

LSYSTEMS = {
    "Fractal plant": dict(axiom="X", rules={"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"},
                          angle=25, depth=5),
    "Koch snowflake": dict(axiom="F--F--F", rules={"F": "F+F--F+F"}, angle=60, depth=4),
    "Dragon curve": dict(axiom="FX", rules={"X": "X+YF+", "Y": "-FX-Y"}, angle=90, depth=11),
    "Sierpinski arrow": dict(axiom="A", rules={"A": "B-A-B", "B": "A+B+A"},
                             angle=60, depth=6),
    "Bushy tree": dict(axiom="F", rules={"F": "F[+F]F[-F][F]"}, angle=22, depth=4),
}


def lsystem_expand(axiom, rules, depth):
    """Apply the rewrite rules `depth` times. Growth is exponential, so cap it."""
    s = axiom
    for _ in range(depth):
        s = "".join(rules.get(ch, ch) for ch in s)
        if len(s) > 400_000:  # safety valve
            break
    return s


def lsystem_segments(commands, angle_deg, step=1.0):
    """Read the string as turtle graphics and return the line segments drawn."""
    x, y, heading = 0.0, 0.0, 90.0
    stack, segments = [], []
    angle = math.radians(angle_deg)
    for ch in commands:
        if ch in "FGAB":  # move forward, drawing
            nx = x + step * math.cos(math.radians(heading))
            ny = y + step * math.sin(math.radians(heading))
            segments.append((x, y, nx, ny))
            x, y = nx, ny
        elif ch == "f":  # move without drawing
            x += step * math.cos(math.radians(heading))
            y += step * math.sin(math.radians(heading))
        elif ch == "+":
            heading += math.degrees(angle)
        elif ch == "-":
            heading -= math.degrees(angle)
        elif ch == "[":
            stack.append((x, y, heading))
        elif ch == "]":
            if stack:
                x, y, heading = stack.pop()
    return segments


def draw_lsystem(name, width, height):
    spec = LSYSTEMS[name]
    commands = lsystem_expand(spec["axiom"], spec["rules"], spec["depth"])
    segments = lsystem_segments(commands, spec["angle"])
    fitted = fit_segments(segments, width, height)
    canvas = Canvas(width, height)
    total = len(fitted) or 1
    for i, (x0, y0, x1, y1) in enumerate(fitted):
        t = i / total  # colour follows the order of growth: trunk to tips
        canvas.line(x0, y0, x1, y1, SOLID, hsv(0.33 - 0.28 * t, 0.7, 0.45 + 0.55 * t))
    return canvas, len(commands), len(segments)


# =============================================================================
#  SECTION 5 -- MAZES
# =============================================================================
class Maze:
    """Recursive-backtracker maze: carve a random depth-first tree of corridors.

    Because it is a spanning tree, every cell is reachable and exactly one
    path connects any two cells -- which is what makes the BFS solve clean.
    """

    def __init__(self, cols, rows, seed=None):
        self.cols, self.rows = cols, rows
        self.rng = random.Random(seed)
        self.links = {(x, y): set() for y in range(rows) for x in range(cols)}
        self._carve()

    def _neighbours(self, cell):
        x, y = cell
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.cols and 0 <= ny < self.rows:
                yield (nx, ny)

    def _carve(self):
        start = (0, 0)
        stack, seen = [start], {start}
        while stack:
            cell = stack[-1]
            options = [n for n in self._neighbours(cell) if n not in seen]
            if not options:
                stack.pop()
                continue
            nxt = self.rng.choice(options)
            self.links[cell].add(nxt)
            self.links[nxt].add(cell)
            seen.add(nxt)
            stack.append(nxt)

    def solve(self, start=None, end=None):
        """Breadth-first search: the first time we reach the exit is the shortest way."""
        start = start or (0, 0)
        end = end or (self.cols - 1, self.rows - 1)
        queue, came = deque([start]), {start: None}
        while queue:
            cell = queue.popleft()
            if cell == end:
                break
            for nxt in self.links[cell]:
                if nxt not in came:
                    came[nxt] = cell
                    queue.append(nxt)
        if end not in came:
            return []
        path, node = [], end
        while node is not None:
            path.append(node)
            node = came[node]
        return list(reversed(path))

    def reachable_count(self, start=(0, 0)):
        seen, queue = {start}, deque([start])
        while queue:
            for nxt in self.links[queue.popleft()]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return len(seen)

    def to_canvas(self, path=None, walked=0):
        """Render walls as solid blocks; draw the solution as far as `walked`."""
        w, h = self.cols * 2 + 1, self.rows * 2 + 1
        canvas = Canvas(w, h, fill=SOLID)
        wall = (70, 70, 110)
        for y in range(h):
            for x in range(w):
                canvas.colors[y][x] = wall
        for (cx, cy), links in self.links.items():
            gx, gy = cx * 2 + 1, cy * 2 + 1
            canvas.plot(gx, gy, " ", None)
            for nx, ny in links:
                canvas.plot(gx + (nx - cx), gy + (ny - cy), " ", None)
        if path:
            shown = path[:max(0, walked)] if walked else path
            for i, (cx, cy) in enumerate(shown):
                t = i / max(1, len(path) - 1)
                color = hsv(0.55 - 0.45 * t, 0.9, 1.0)
                gx, gy = cx * 2 + 1, cy * 2 + 1
                canvas.plot(gx, gy, GLYPH["dot"], color)
                if i:
                    px, py = shown[i - 1]
                    canvas.plot(gx + (px - cx), gy + (py - cy), GLYPH["dot"], color)
        return canvas


# =============================================================================
#  SECTION 6 -- CELLULAR AUTOMATA
# =============================================================================
LIFE_PATTERNS = {
    "Glider": [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)],
    "Blinker": [(0, 0), (1, 0), (2, 0)],
    "R-pentomino": [(1, 0), (2, 0), (0, 1), (1, 1), (1, 2)],
    "Acorn": [(1, 0), (3, 1), (0, 2), (1, 2), (4, 2), (5, 2), (6, 2)],
    "Diehard": [(6, 0), (0, 1), (1, 1), (1, 2), (5, 2), (6, 2), (7, 2)],
    "Pulsar": [(2, 0), (3, 0), (4, 0), (0, 2), (5, 2), (0, 3), (5, 3), (0, 4), (5, 4),
               (2, 5), (3, 5), (4, 5)],
}


def life_step(live):
    """One generation of Conway's rules, counted only near living cells."""
    counts = {}
    for (x, y) in live:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    counts[(x + dx, y + dy)] = counts.get((x + dx, y + dy), 0) + 1
    return {cell for cell, n in counts.items() if n == 3 or (n == 2 and cell in live)}


def life_canvas(live, width, height, generation=0):
    canvas = Canvas(width, height)
    cx, cy = width // 2, height // 2
    for (x, y) in live:
        px, py = x + cx, y + cy
        if canvas.in_bounds(px, py):
            hue = (0.45 + 0.12 * math.sin((x + y + generation) * 0.25)) % 1.0
            canvas.plot(px, py, SOLID, hsv(hue, 0.7, 1.0))
    return canvas


def elementary_ca(rule, width, generations, seed_random=False, seed=7):
    """Wolfram's 1D automata: each cell's next state depends on its 3-cell block."""
    table = [(rule >> i) & 1 for i in range(8)]
    rng = random.Random(seed)
    if seed_random:
        row = [rng.randint(0, 1) for _ in range(width)]
    else:
        row = [0] * width
        row[width // 2] = 1
    history = [row]
    for _ in range(generations - 1):
        prev = history[-1]
        nxt = []
        for i in range(width):
            left = prev[(i - 1) % width]
            mid = prev[i]
            right = prev[(i + 1) % width]
            nxt.append(table[(left << 2) | (mid << 1) | right])
        history.append(nxt)
    return history


def ca_canvas(history, hue=0.08):
    canvas = Canvas(len(history[0]), len(history))
    for y, row in enumerate(history):
        shade = y / max(1, len(history) - 1)
        for x, cell in enumerate(row):
            if cell:
                canvas.plot(x, y, SOLID, hsv(hue + 0.35 * shade, 0.75, 0.55 + 0.45 * shade))
    return canvas


# =============================================================================
#  SECTION 7 -- FIELDS, CHANCE AND CURVES
# =============================================================================
def plasma_value(x, y, t):
    """Sum of sine waves at different angles -- classic demoscene plasma."""
    v = math.sin(x * 0.25 + t)
    v += math.sin((y * 0.5 - t) * 0.6)
    v += math.sin((x + y) * 0.18 + t * 0.7)
    v += math.sin(math.sqrt(x * x + y * y) * 0.28 - t * 1.3)
    return (v + 4.0) / 8.0  # normalised to [0,1]


def plasma_canvas(width, height, t):
    canvas = Canvas(width, height)
    for y in range(height):
        for x in range(width):
            v = plasma_value(x - width / 2, (y - height / 2) * 2, t)
            canvas.plot(x, y, BLOCKS[min(len(BLOCKS) - 1, int(v * len(BLOCKS)))],
                        hsv(v * 0.85 + 0.55, 0.75, 0.45 + 0.55 * v))
    return canvas


def chaos_sierpinski(n, rng):
    """Jump halfway to a randomly chosen corner, forever. A triangle appears."""
    corners = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]
    x, y = 0.3, 0.2
    points = []
    for _ in range(n):
        cx, cy = rng.choice(corners)
        x, y = (x + cx) / 2.0, (y + cy) / 2.0
        points.append((x, y))
    return points


def barnsley_fern(n, rng):
    """Four affine transforms, weighted by probability. Nature from a lookup table."""
    x, y = 0.0, 0.0
    points = []
    for _ in range(n):
        r = rng.random()
        if r < 0.01:
            x, y = 0.0, 0.16 * y
        elif r < 0.86:
            x, y = 0.85 * x + 0.04 * y, -0.04 * x + 0.85 * y + 1.60
        elif r < 0.93:
            x, y = 0.20 * x - 0.26 * y, 0.23 * x + 0.22 * y + 1.60
        else:
            x, y = -0.15 * x + 0.28 * y, 0.26 * x + 0.24 * y + 0.44
        points.append((x, y))
    return points


def scatter_canvas(points, width, height, hue_base=0.3):
    """Plot a point cloud with density-aware shading."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    spanx = (maxx - minx) or 1e-9
    spany = (maxy - miny) or 1e-9
    hits = {}
    for x, y in points:
        px = int((x - minx) / spanx * (width - 1))
        py = int((1.0 - (y - miny) / spany) * (height - 1))
        hits[(px, py)] = hits.get((px, py), 0) + 1
    peak = max(hits.values())
    canvas = Canvas(width, height)
    for (px, py), n in hits.items():
        t = math.log1p(n) / math.log1p(peak)
        canvas.plot(px, py, BLOCKS[min(len(BLOCKS) - 1, int(t * len(BLOCKS)))],
                    hsv(hue_base + 0.18 * t, 0.8, 0.4 + 0.6 * t))
    return canvas


def harmonograph(width, height, a=(1.0, 1.0), freq=(2.0, 3.01), phase=(0.0, math.pi / 4),
                 decay=0.0035, steps=9000, dt=0.012):
    """Two decaying pendulums, one per axis. Slightly detuned ratios spiral."""
    canvas = Canvas(width, height)
    cx, cy = width / 2, height / 2
    scale = min(width, height * 2) * 0.42
    prev = None
    for i in range(steps):
        t = i * dt
        damp = math.exp(-decay * i)
        x = a[0] * math.sin(freq[0] * t + phase[0]) * damp
        y = a[1] * math.sin(freq[1] * t + phase[1]) * damp
        px = cx + x * scale
        py = cy - y * scale * 0.5
        color = hsv(0.6 + 0.35 * (i / steps), 0.75, 0.45 + 0.55 * damp)
        if prev:
            canvas.line(prev[0], prev[1], px, py, SOLID, color)
        prev = (px, py)
    return canvas


def rose_curve(width, height, n=7, d=4, turns=None):
    """r = cos(k*theta): petals whose count depends on the parity of n and d."""
    canvas = Canvas(width, height)
    cx, cy = width / 2, height / 2
    scale = min(width, height * 2) * 0.45
    k = n / d
    turns = turns or d * 2
    steps = 4000
    prev = None
    for i in range(steps + 1):
        theta = turns * math.pi * i / steps
        r = math.cos(k * theta)
        px = cx + r * math.cos(theta) * scale
        py = cy - r * math.sin(theta) * scale * 0.5
        color = hsv(0.9 + 0.4 * (i / steps), 0.8, 1.0)
        if prev:
            canvas.line(prev[0], prev[1], px, py, SOLID, color)
        prev = (px, py)
    return canvas


# =============================================================================
#  SECTION 8 -- GALLERY ROOMS
# =============================================================================
def pick(options, prompt="choose:"):
    """Numbered chooser used by several rooms. Returns the chosen index."""
    for i, label in enumerate(options, 1):
        print("   %s%d%s  %s" % (BOLD, i, RESET, label))
    return ask_num(prompt, 1, 1, len(options)) - 1


def room_mandelbrot():
    title("MANDELBROT EXPLORER")
    info("z = z*z + c, repeated. Points that never escape are the black heart.")
    idx = pick([s[0] for s in MANDEL_SPOTS])
    name, cx, cy, zoom, iters = MANDEL_SPOTS[idx]
    zoom = ask_num("zoom (1-5000):", zoom, 1.0, 5000.0, float)
    iters = ask_num("iterations (40-400):", iters, 40, 400)
    print()
    info("Rendering %s at zoom %.1f ..." % (name, zoom))
    canvas = render_escape(76, 30, cx, cy, zoom, iters)
    canvas.show()
    print()
    good("Centre %.6f%+.6fi  %s  %d iterations" % (cx, cy, GLYPH["dot"], iters))
    pause()


def room_julia():
    title("JULIA SET GALLERY")
    info("Same iteration, but c stays fixed and the starting point varies.")
    idx = pick(["%s  (c = %.3f%+.3fi)" % (n, c.real, c.imag) for n, c in JULIA_SPOTS])
    name, c = JULIA_SPOTS[idx]
    print()
    info("Rendering the %s ..." % name)
    canvas = render_escape(76, 30, 0.0, 0.0, 0.75, 120, julia_c=c, hue_shift=0.35)
    canvas.show()
    print()
    good("Every c inside the Mandelbrot set gives a connected Julia set.")
    pause()


def room_lsystem():
    title("L-SYSTEM BOTANY")
    info("A grammar rewritten a few times, then read as turtle instructions.")
    names = list(LSYSTEMS)
    name = names[pick(names)]
    print()
    canvas, chars, segs = draw_lsystem(name, 76, 34)
    canvas.show()
    print()
    spec = LSYSTEMS[name]
    good("%s  %s  depth %d  %s  %d symbols  %s  %d segments"
         % (name, GLYPH["dot"], spec["depth"], GLYPH["dot"], chars, GLYPH["dot"], segs))
    info("Rules: " + "  ".join("%s -> %s" % (k, v) for k, v in spec["rules"].items()))
    pause()


def room_maze():
    title("MAZE FORGE")
    info("Carved depth-first, then solved breadth-first. Colour marks progress.")
    cols = ask_num("columns (5-36):", 24, 5, 36)
    rows = ask_num("rows (5-14):", 11, 5, 14)
    maze = Maze(cols, rows)
    path = maze.solve()
    if ANIMATE:
        clear()
        for step in range(1, len(path) + 1):
            home()
            print(maze.to_canvas(path, walked=step).render())
            print("   solving ... %d / %d cells" % (step, len(path)))
            time.sleep(0.03)
    else:
        maze.to_canvas(path).show()
    print()
    good("%d cells, all reachable. Shortest route: %d steps."
         % (maze.reachable_count(), len(path)))
    info("A perfect maze is a spanning tree: exactly one route between any two cells.")
    pause()


def room_life():
    title("CONWAY'S GAME OF LIFE")
    info("Four rules, no randomness after the first frame, endless surprises.")
    names = list(LIFE_PATTERNS)
    name = names[pick(names)]
    gens = ask_num("generations (10-400):", 120, 10, 400)
    live = set(LIFE_PATTERNS[name])
    if ANIMATE:
        clear()
        for g in range(gens):
            home()
            print(life_canvas(live, 76, 26, g).render())
            print("   %s  %s  generation %d  %s  %d live cells    "
                  % (name, GLYPH["dot"], g, GLYPH["dot"], len(live)))
            live = life_step(live)
            if not live:
                break
            time.sleep(0.05)
    else:
        for _ in range(gens):
            live = life_step(live)
        life_canvas(live, 76, 26, gens).show()
    print()
    good("Ended with %d live cells after %d generations." % (len(live), gens))
    pause()


def room_elementary():
    title("ELEMENTARY CELLULAR AUTOMATA")
    info("A row of cells, one rule number, and time flowing downward.")
    info("Try 30 (chaos), 90 (Sierpinski), 110 (Turing complete), 184 (traffic).")
    rule = ask_num("rule (0-255):", 30, 0, 255)
    rnd = ask("random start? (y/N):", "n").lower().startswith("y")
    print()
    history = elementary_ca(rule, 76, 30, seed_random=rnd)
    ca_canvas(history, hue=(rule % 16) / 16.0).show()
    print()
    live = sum(sum(row) for row in history)
    good("Rule %d  %s  %d cells alive across %d generations"
         % (rule, GLYPH["dot"], live, len(history)))
    pause()


def room_plasma():
    title("PLASMA FIELD")
    info("Four sine waves interfering. The oldest trick in the demoscene.")
    frames = ask_num("frames (1-300):", 90 if ANIMATE else 1, 1, 300)
    if ANIMATE and frames > 1:
        clear()
        for f in range(frames):
            home()
            print(plasma_canvas(76, 26, f * 0.13).render())
            print("   frame %d / %d    " % (f + 1, frames))
            time.sleep(0.04)
    else:
        plasma_canvas(76, 26, 0.0).show()
    print()
    good("No noise library needed - just sin() and a colour ramp.")
    pause()


def room_chaos():
    title("THE CHAOS GAME")
    info("Random jumps, deterministic shapes. Order out of pure coin-flipping.")
    which = pick(["Sierpinski triangle", "Barnsley fern"])
    points = ask_num("points (2000-120000):", 40000, 2000, 120000)
    rng = random.Random()
    print()
    if which == 0:
        cloud = chaos_sierpinski(points, rng)
        scatter_canvas(cloud, 76, 32, hue_base=0.55).show()
        good("Every point lands inside the triangle, and the gaps never fill in.")
    else:
        cloud = barnsley_fern(points, rng)
        scatter_canvas(cloud, 60, 36, hue_base=0.28).show()
        good("Four affine maps, chosen with probabilities 1%, 85%, 7%, 7%.")
    pause()


def room_curves():
    title("HARMONOGRAPH & ROSE CURVES")
    which = pick(["Harmonograph (decaying pendulums)", "Rose curve (r = cos k0)"])
    print()
    if which == 0:
        f1 = ask_num("frequency A:", 2.0, 0.5, 12.0, float)
        f2 = ask_num("frequency B:", 3.01, 0.5, 12.0, float)
        decay = ask_num("decay (0.0005-0.02):", 0.0035, 0.0005, 0.02, float)
        harmonograph(76, 32, freq=(f1, f2), decay=decay).show()
        good("Near-integer frequency ratios drift slowly; exact ratios close up.")
    else:
        n = ask_num("n (1-12):", 7, 1, 12)
        d = ask_num("d (1-12):", 4, 1, 12)
        rose_curve(76, 32, n, d).show()
        good("n/d both odd gives n petals; otherwise you get 2n.")
    pause()


def room_gallery():
    """A single screen with several pieces side by side."""
    title("CURATOR'S PICKS")
    info("Four small works, rendered back to back.")
    print()
    print(render_escape(74, 18, -0.745, 0.113, 40.0, 120).render())
    print()
    print(draw_lsystem("Fractal plant", 74, 20)[0].render())
    print()
    print(ca_canvas(elementary_ca(90, 74, 20), hue=0.62).render())
    print()
    print(scatter_canvas(barnsley_fern(30000, random.Random(3)), 48, 26, 0.28).render())
    print()
    good("Seahorse valley, a grammar-grown plant, rule 90, and a fern.")
    pause()


# =============================================================================
#  SECTION 9 -- SELF-TEST SUITE
# =============================================================================
def run_tests(verbose=True):
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    # --- canvas ------------------------------------------------------------
    c = Canvas(10, 4)
    c.plot(3, 2, "X")
    check("canvas size", len(c.chars) == 4 and len(c.chars[0]) == 10)
    check("canvas plot", c.chars[2][3] == "X")
    c.plot(99, 99, "Z")  # must be silently ignored
    check("canvas clipping", all("Z" not in row for row in c.chars))
    c.line(0, 0, 9, 3, "#")
    check("line endpoints", c.chars[0][0] == "#" and c.chars[3][9] == "#")
    check("line continuity", all(any(ch == "#" for ch in row) for row in c.chars))
    c.text(0, 1, "hi")
    check("canvas text", c.chars[1][0] == "h" and c.chars[1][1] == "i")
    check("render rows", len(Canvas(5, 3).render().split("\n")) == 3)
    check("ramp bounds", ramp_char(-5) == RAMP[0] and ramp_char(5) == RAMP[-1])

    # --- colour ------------------------------------------------------------
    r, g, b = hsv(0.0, 1.0, 1.0)
    check("hsv red", (r, g, b) == (255, 0, 0))
    check("hsv range", all(0 <= v <= 255 for v in hsv(0.42, 0.8, 0.6)))
    check("hsv wraps", hsv(1.25) == hsv(0.25))

    # --- fractals ----------------------------------------------------------
    check("mandel inside", mandel_escape(0j, 80) == 80)
    check("mandel outside", mandel_escape(complex(2, 2), 80) < 5)
    check("mandel bulb", mandel_escape(complex(-1, 0), 80) == 80)
    check("julia escapes", julia_escape(complex(2, 2), complex(0, 1), 50) < 5)
    check("escape canvas", render_escape(12, 6, -0.6, 0, 1.0, 20).h == 6)

    # --- L-systems ---------------------------------------------------------
    fib = [len(lsystem_expand("A", {"A": "AB", "B": "A"}, d)) for d in range(6)]
    check("lsystem fibonacci", fib == [1, 2, 3, 5, 8, 13])
    check("lsystem koch", lsystem_expand("F", {"F": "F+F--F+F"}, 1) == "F+F--F+F")
    check("lsystem unknown chars", lsystem_expand("F+", {"X": "Y"}, 3) == "F+")
    segs = lsystem_segments("FF", 90)
    check("turtle segments", len(segs) == 2)
    check("turtle continuity", abs(segs[0][2] - segs[1][0]) < 1e-9)
    check("turtle stack", len(lsystem_segments("F[+F]F", 30)) == 3)
    fitted = fit_segments([(0, 0, 10, 10)], 40, 20)
    check("fit in bounds", all(0 <= v <= 40 for v in fitted[0][:1]))

    # --- mazes -------------------------------------------------------------
    maze = Maze(12, 8, seed=42)
    check("maze all reachable", maze.reachable_count() == 12 * 8)
    path = maze.solve()
    check("maze path exists", len(path) > 0)
    check("maze path ends", path[0] == (0, 0) and path[-1] == (11, 7))
    check("maze path minimum", len(path) >= 12 + 8 - 1)
    check("maze links symmetric",
          all(a in maze.links[b] for a, ns in maze.links.items() for b in ns))
    check("maze steps adjacent",
          all(abs(path[i][0] - path[i + 1][0]) + abs(path[i][1] - path[i + 1][1]) == 1
              for i in range(len(path) - 1)))
    check("maze deterministic seed", Maze(8, 6, seed=1).solve() == Maze(8, 6, seed=1).solve())
    check("maze canvas size", maze.to_canvas().w == 12 * 2 + 1)

    # --- automata ----------------------------------------------------------
    blinker = set(LIFE_PATTERNS["Blinker"])
    check("life blinker period", life_step(life_step(blinker)) == blinker)
    check("life blinker flips", life_step(blinker) != blinker)
    glider = set(LIFE_PATTERNS["Glider"])
    after = glider
    for _ in range(4):
        after = life_step(after)
    check("life glider travels", after == {(x + 1, y + 1) for x, y in glider})
    check("life empty stays empty", life_step(set()) == set())
    check("life lone cell dies", life_step({(0, 0)}) == set())

    hist = elementary_ca(30, 21, 3)
    check("ca single seed", sum(hist[0]) == 1)
    check("ca rule30 spread", sum(hist[1]) == 3)
    check("ca rule0 dies", sum(elementary_ca(0, 21, 3)[2]) == 0)
    check("ca rule255 fills", sum(elementary_ca(255, 21, 2)[1]) == 21)
    check("ca dimensions", len(elementary_ca(110, 30, 12)) == 12)

    # --- fields, chance, curves -------------------------------------------
    check("plasma normalised",
          all(0.0 <= plasma_value(x, y, 0.5) <= 1.0
              for x in range(-20, 21, 5) for y in range(-20, 21, 5)))
    check("plasma varies", plasma_value(0, 0, 0) != plasma_value(7, 3, 0))
    tri = chaos_sierpinski(2000, random.Random(5))
    check("chaos point count", len(tri) == 2000)
    check("chaos inside triangle", all(0 <= x <= 1 and 0 <= y <= 1 for x, y in tri))
    fern = barnsley_fern(5000, random.Random(5))
    check("fern bounds", all(-3 <= x <= 3 and -0.1 <= y <= 11 for x, y in fern))
    check("fern deterministic",
          barnsley_fern(50, random.Random(9)) == barnsley_fern(50, random.Random(9)))
    check("scatter canvas", scatter_canvas(fern, 20, 20).w == 20)
    check("harmonograph draws", any(ch != " " for row in harmonograph(40, 16, steps=1500).chars
                                    for ch in row))
    check("rose draws", any(ch != " " for row in rose_curve(40, 16, 5, 2).chars for ch in row))

    passed = sum(1 for _, ok in checks if ok)
    failed = len(checks) - passed
    if verbose:
        title("SELF-TEST SUITE")
        for name, ok in checks:
            mark = (rgb(110, 220, 140) + "PASS" if ok else rgb(240, 110, 110) + "FAIL") + RESET
            print("   [%s] %s" % (mark, name))
        print()
        if failed:
            fail("%d of %d checks failed." % (failed, len(checks)))
        else:
            good("All %d checks passed." % passed)
    return passed, failed


# =============================================================================
#  SECTION 10 -- GALLERY ENTRANCE
# =============================================================================
ROOMS = [
    ("1", "Mandelbrot explorer", room_mandelbrot),
    ("2", "Julia set gallery", room_julia),
    ("3", "L-system botany", room_lsystem),
    ("4", "Maze forge (generate + solve)", room_maze),
    ("5", "Game of Life", room_life),
    ("6", "Elementary cellular automata", room_elementary),
    ("7", "Plasma field", room_plasma),
    ("8", "Chaos game (triangle / fern)", room_chaos),
    ("9", "Harmonograph & rose curves", room_curves),
    ("G", "Curator's picks (four at once)", room_gallery),
    ("T", "Run the built-in self-test", lambda: (run_tests(), pause())),
]


def show_menu():
    clear()
    for i, line in enumerate(BANNER.strip("\n").split("\n")):
        print(rgb(*hsv(0.55 + i * 0.05, 0.6, 1.0)) + line + RESET)
    print(DIM + "   generative art on a character grid  " + GLYPH["dot"]
          + "  pure python  " + GLYPH["dot"] + "  no dependencies" + RESET)
    print(DIM + "=" * WIDTH + RESET)
    for key, label, _ in ROOMS:
        print("   %s%s%s  %s" % (BOLD + rgb(240, 200, 100), key.ljust(2), RESET, label))
    print("   %sQ %s  Quit" % (BOLD + rgb(240, 200, 100), RESET))
    print(DIM + "=" * WIDTH + RESET)


def main():
    if "--test" in sys.argv:
        _, failed = run_tests()
        return 1 if failed else 0

    while True:
        show_menu()
        choice = ask("choose a room:", "Q").upper()
        if choice in ("Q", "QUIT", "EXIT"):
            print(rgb(120, 200, 255) + "\n  The gallery closes. The maths stays open.\n" + RESET)
            return 0
        for key, _, action in ROOMS:
            if choice == key:
                try:
                    action()
                except SystemExit:
                    raise
                except Exception as exc:  # a bad room never takes down the gallery
                    fail("Something went wrong: %s" % exc)
                    pause()
                break
        else:
            fail("No such room: %s" % choice)
            pause()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n  Interrupted.\n")
        sys.exit(130)
