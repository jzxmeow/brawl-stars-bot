import io
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
PORTRAITS_DIR = ROOT / "portraits"

WIDTH = 1080
COLUMNS = 6
ROWS_PER_PAGE = 7
CELL_W = 164
CELL_H = 196
GAP = 10
MARGIN = 23
HEADER_H = 250
FOOTER_H = 58
PAGE_SIZE = COLUMNS * ROWS_PER_PAGE


def _font(size, bold=False):
    candidates = []
    if bold:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _portrait_index():
    index = {}
    if PORTRAITS_DIR.exists():
        for path in PORTRAITS_DIR.iterdir():
            if path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}:
                index[_key(path.stem)] = path
    return index


def _background(height):
    image = Image.new("RGB", (WIDTH, height), "#100d1c")
    pixels = image.load()
    top = (13, 12, 29)
    bottom = (43, 20, 70)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = color
    return image


def _fit_text(draw, text, font, max_width):
    text = str(text)
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-2] + "…" if len(text) > 2 else text[:-1]
    return text


def _centered(draw, xy, text, font, fill, max_width=None):
    if max_width:
        text = _fit_text(draw, text, font, max_width)
    box = draw.textbbox((0, 0), str(text), font=font)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1]), str(text), font=font, fill=fill)


def _draw_portrait(canvas, path, x, y, max_w, max_h):
    if not path or not path.exists():
        return False
    try:
        with Image.open(path) as source:
            portrait = source.convert("RGBA")
        portrait.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        px = x + (max_w - portrait.width) // 2
        py = y + (max_h - portrait.height) // 2
        canvas.alpha_composite(portrait, (px, py))
        return True
    except (OSError, ValueError):
        return False


def generate_cards(player, brawlers, mode):
    """Return [(BytesIO, caption), ...] for power or trophies mode."""
    mode = "trophies" if mode == "trophies" else "power"
    metric_key = "trophies" if mode == "trophies" else "power"
    title = "КУБКИ БОЙЦОВ" if mode == "trophies" else "СИЛА БОЙЦОВ"
    sort_key = lambda b: int(b.get(metric_key, 0) or 0)
    sorted_brawlers = sorted(brawlers, key=sort_key, reverse=True)
    if not sorted_brawlers:
        return []

    portraits = _portrait_index()
    pages = []
    page_count = math.ceil(len(sorted_brawlers) / PAGE_SIZE)

    for page_number in range(page_count):
        group = sorted_brawlers[page_number * PAGE_SIZE:(page_number + 1) * PAGE_SIZE]
        rows = math.ceil(len(group) / COLUMNS)
        height = HEADER_H + rows * CELL_H + max(0, rows - 1) * GAP + FOOTER_H
        base = _background(height).convert("RGBA")
        draw = ImageDraw.Draw(base)

        # Soft decorative rings, intentionally different from the reference layouts.
        draw.ellipse((790, -150, 1190, 250), outline=(125, 75, 190, 95), width=4)
        draw.ellipse((835, -105, 1145, 205), outline=(125, 75, 190, 70), width=3)
        draw.rounded_rectangle((MARGIN, 24, WIDTH - MARGIN, 222), radius=28,
                               fill=(22, 17, 39, 235), outline=(100, 69, 146, 180), width=2)
        draw.text((48, 43), "META HELPER", font=_font(25, True), fill="#c8a4ff")
        draw.text((48, 82), title, font=_font(42, True), fill="#ffffff")
        player_name = str(player.get("name", "Неизвестный игрок"))
        tag = str(player.get("tag", "")).lstrip("#")
        draw.text((50, 143), _fit_text(draw, player_name, _font(24, True), 610),
                  font=_font(24, True), fill="#eee8ff")
        draw.text((50, 179), f"#{tag}  •  {player.get('trophies', 0)} трофеев аккаунта",
                  font=_font(18), fill="#b9b0ce")
        stats_x = WIDTH - 240
        draw.rounded_rectangle((stats_x, 67, WIDTH - 48, 177), radius=22,
                               fill=(66, 39, 96, 235), outline=(158, 112, 218, 190), width=2)
        _centered(draw, (stats_x + 96, 81), str(len(brawlers)), _font(34, True), "#ffffff")
        _centered(draw, (stats_x + 96, 126), "БОЙЦОВ", _font(15, True), "#d9c4ff")

        for i, brawler in enumerate(group):
            row, col = divmod(i, COLUMNS)
            x = MARGIN + col * (CELL_W + GAP)
            y = HEADER_H + row * (CELL_H + GAP)
            draw.rounded_rectangle((x, y, x + CELL_W, y + CELL_H), radius=18,
                                   fill=(25, 21, 43, 242), outline=(79, 60, 111, 220), width=2)

            name = str(brawler.get("name", "Unknown"))
            portrait_path = portraits.get(_key(name))
            _draw_portrait(base, portrait_path, x + 8, y + 8, CELL_W - 16, 119)

            draw.text((x + 10, y + 132), _fit_text(draw, name, _font(15, True), CELL_W - 20),
                      font=_font(15, True), fill="#ffffff")
            value = int(brawler.get(metric_key, 0) or 0)
            if mode == "power":
                label = f"СИЛА  {value}"
                pill_color = (96, 56, 150, 255)
            else:
                label = f"🏆  {value:,}".replace(",", " ")
                pill_color = (130, 86, 30, 255)
            draw.rounded_rectangle((x + 9, y + 158, x + CELL_W - 9, y + 187),
                                   radius=10, fill=pill_color)
            _centered(draw, (x + CELL_W / 2, y + 164), label, _font(15, True),
                      "#ffffff", CELL_W - 25)

        footer_y = height - FOOTER_H + 10
        draw.text((MARGIN, footer_y), "META HELPER  •  BRAWL STARS",
                  font=_font(14, True), fill="#9e8bb9")
        page_text = f"{page_number + 1} / {page_count}"
        _centered(draw, (WIDTH - 65, footer_y), page_text, _font(16, True), "#e8dcff")

        output = io.BytesIO()
        base.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)
        output.seek(0)
        output.name = f"meta_helper_{mode}_{page_number + 1}.jpg"
        caption = f"{title.title()} • {player_name} • страница {page_number + 1}/{page_count}"
        pages.append((output, caption))

    return pages
