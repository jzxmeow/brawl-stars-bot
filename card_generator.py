import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PORTRAITS_DIR = ROOT / "portraits"
RESOURCES_DIR = ROOT / "resourses"

# One landscape image with exactly 108 slots: 12 columns x 9 rows.
WIDTH = 1920
HEIGHT = 1080
COLUMNS = 12
ROWS = 9
SLOTS = COLUMNS * ROWS
MARGIN_X = 24
GRID_TOP = 158
CELL_W = 148
CELL_H = 88
GAP_X = 8
GAP_Y = 8
FOOTER_Y = 1045

# Muted versions of the game's recognizable rarity colors.
RARITY_COLORS = {
    "common":     {"fill": (31, 65, 83, 244), "outline": (65, 125, 154, 245)},
    "rare":       {"fill": (34, 72, 51, 244), "outline": (69, 132, 86, 245)},
    "super_rare": {"fill": (30, 57, 91, 244), "outline": (66, 112, 171, 245)},
    "epic":       {"fill": (63, 35, 87, 244), "outline": (126, 77, 163, 245)},
    "mythic":     {"fill": (91, 35, 48, 244), "outline": (171, 70, 91, 245)},
    "legendary":  {"fill": (92, 69, 26, 244), "outline": (172, 132, 49, 245)},
    "ultra":      {"fill": (35, 72, 75, 244), "outline": (74, 151, 154, 245)},
}

# Rarity isn't included in the player endpoint, so keep a local name lookup.
RARITY_GROUPS = {
    "common": ["Shelly"],
    "rare": ["Colt", "Bull", "Brock", "Barley", "Nita", "El Primo", "Poco", "Rosa"],
    "super_rare": [
        "Rico", "Jessie", "Dynamike", "Darryl", "Penny", "Tick", "Carl", "8-Bit", "Jacky", "Gus",
    ],
    "epic": [
        "Bo", "Piper", "Pam", "Frank", "Bibi", "Bea", "Emz", "Gale", "Nani", "Colette",
        "Edgar", "Stu", "Belle", "Grom", "Griff", "Ash", "Lola", "Bonnie", "Sam", "Mandy",
        "Maisie", "Hank", "Pearl", "Larry & Lawrie", "Angelo", "Berry", "Shade", "Meeple",
        "Trunk", "Bolt",
    ],
    "mythic": [
        "Mortis", "Tara", "Gene", "Mr. P", "Max", "Sprout", "Lou", "Byron", "Ruffs", "Squeak",
        "Buzz", "Fang", "Eve", "Janet", "Otis", "Buster", "Gray", "R-T", "Willow", "Doug",
        "Chuck", "Charlie", "Mico", "Melodie", "Lily", "Clancy", "Moe", "Juju", "Ollie", "Lumi",
        "Finx", "Jae-Yong", "Alli", "Mina", "Ziggy", "Gigi", "Glowy", "Najia", "Damian",
        "Starr Nova", "Wendy", "Cosmo", "Vince",
    ],
    "legendary": [
        "Spike", "Crow", "Leon", "Sandy", "Surge", "Amber", "Meg", "Chester", "Cordelius",
        "Kit", "Draco", "Kenji", "Pierce", "Nori",
    ],
    "ultra": ["Kaze", "Sirius"],
}
RARITY_BY_NAME = {
    name: rarity
    for rarity, names in RARITY_GROUPS.items()
    for name in names
}


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


# The official Supercell API returns brawler names in uppercase (e.g. SHELLY).
# Normalize names so capitalization and punctuation don't prevent rarity matching.
RARITY_BY_KEY = {
    _key(name): rarity
    for name, rarity in RARITY_BY_NAME.items()
}


def _portrait_index():
    index = {}
    if PORTRAITS_DIR.exists():
        for path in PORTRAITS_DIR.iterdir():
            if path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}:
                index[_key(path.stem)] = path
    return index


def _background():
    image = Image.new("RGB", (WIDTH, HEIGHT), "#100d1c")
    pixels = image.load()
    top = (13, 12, 29)
    bottom = (43, 20, 70)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
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


def _resource_icon(canvas, filename, x, y, size):
    """Paste a small transparent icon from the repository resources folder."""
    path = RESOURCES_DIR / filename
    if not path.exists():
        return False
    try:
        with Image.open(path) as source:
            icon = source.convert("RGBA")
        icon.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas.alpha_composite(icon, (int(x + (size - icon.width) / 2),
                                      int(y + (size - icon.height) / 2)))
        return True
    except (OSError, ValueError):
        return False


def _item_count(brawlers, keys):
    total = 0
    for brawler in brawlers:
        value = None
        for key in keys:
            if key in brawler:
                value = brawler.get(key)
                break
        if isinstance(value, list):
            total += len(value)
        elif isinstance(value, dict):
            total += 1
        elif value is True:
            total += 1
    return total


def _draw_power_resource_summary(canvas, draw, brawlers):
    # Gadget and Star Power lists are returned by the official player endpoint.
    gadgets = _item_count(brawlers, ("gadgets", "gadget"))
    star_powers = _item_count(brawlers, ("starPowers", "star_powers", "starPowersOwned"))
    gears = _item_count(brawlers, ("gears", "gear"))

    # Hypercharge ownership is not consistently exposed by the official API.
    # If the response contains a hypercharge field, count it; otherwise show unavailable,
    # rather than incorrectly treating every Power 11 brawler as owning one.
    has_hypercharge_field = any(
        any(key in brawler for key in ("hypercharge", "hyperCharge", "hypercharges"))
        for brawler in brawlers
    )
    hypercharges = _item_count(brawlers, ("hypercharge", "hyperCharge", "hypercharges"))

    items = [
        ("gadget.png", f"{gadgets}/216"),
        ("starpower.png", f"{star_powers}/216"),
        ("gear.png", f"{gears}"),
        ("hypercharge.png", f"{hypercharges}/104" if has_hypercharge_field else "н/д"),
    ]
    start_x = 850
    item_w = 178
    for i, (filename, label) in enumerate(items):
        x = start_x + i * item_w
        _resource_icon(canvas, filename, x, 50, 30)
        draw.text((x + 36, 56), label, font=_font(17, True), fill="#f0e7ff")


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
    """Return a single landscape image containing 108 brawler slots."""
    mode = "trophies" if mode == "trophies" else "power"
    metric_key = "trophies" if mode == "trophies" else "power"
    title = "КУБКИ БОЙЦОВ" if mode == "trophies" else "СИЛА БОЙЦОВ"
    sorted_brawlers = sorted(
        brawlers,
        key=lambda b: int(b.get(metric_key, 0) or 0),
        reverse=True,
    )

    portraits = _portrait_index()
    base = _background().convert("RGBA")
    draw = ImageDraw.Draw(base)

    # Header panel and subtle purple rings.
    draw.ellipse((1530, -250, 1990, 210), outline=(125, 75, 190, 90), width=5)
    draw.ellipse((1590, -190, 1930, 150), outline=(125, 75, 190, 65), width=3)
    draw.rounded_rectangle(
        (MARGIN_X, 18, WIDTH - MARGIN_X, 140),
        radius=24,
        fill=(22, 17, 39, 238),
        outline=(100, 69, 146, 190),
        width=2,
    )
    draw.text((48, 30), "META HELPER", font=_font(20, True), fill="#c8a4ff")
    draw.text((48, 58), title, font=_font(34, True), fill="#ffffff")

    player_name = str(player.get("name", "Неизвестный игрок"))
    tag = str(player.get("tag", "")).lstrip("#")
    draw.text(
        (50, 103),
        _fit_text(draw, f"{player_name}  •  #{tag}", _font(18, True), 760),
        font=_font(18, True),
        fill="#eee8ff",
    )

    stats_x = WIDTH - 320
    draw.rounded_rectangle(
        (stats_x, 37, WIDTH - 48, 121),
        radius=18,
        fill=(66, 39, 96, 235),
        outline=(158, 112, 218, 190),
        width=2,
    )
    _centered(draw, (stats_x + 136, 43), f"{len(sorted_brawlers)} / {SLOTS}", _font(27, True), "#ffffff")
    _centered(draw, (stats_x + 136, 82), "БОЙЦОВ НА АККАУНТЕ", _font(13, True), "#d9c4ff")

    # Resource counters are shown only on the Power Levels card.
    if mode == "power":
        _draw_power_resource_summary(base, draw, sorted_brawlers)

    # Always draw all 108 cells. Empty slots use a muted purple fill and a question mark.
    for i in range(SLOTS):
        row, col = divmod(i, COLUMNS)
        x = MARGIN_X + col * (CELL_W + GAP_X)
        y = GRID_TOP + row * (CELL_H + GAP_Y)
        is_filled = i < len(sorted_brawlers)

        if is_filled:
            brawler = sorted_brawlers[i]
            name = str(brawler.get("name", "Unknown"))
            rarity = RARITY_BY_KEY.get(_key(name), "")
            palette = RARITY_COLORS.get(
                rarity,
                {"fill": (29, 24, 43, 244), "outline": (78, 61, 103, 235)},
            )
            fill = palette["fill"]
            outline = palette["outline"]
        else:
            fill = (29, 23, 45, 210)
            outline = (62, 45, 83, 190)

        draw.rounded_rectangle(
            (x, y, x + CELL_W, y + CELL_H),
            radius=12,
            fill=fill,
            outline=outline,
            width=2,
        )

        if not is_filled:
            _centered(draw, (x + CELL_W / 2, y + 12), "?", _font(33, True), "#625078")
            _centered(draw, (x + CELL_W / 2, y + 55), "—", _font(15, True), "#6e5b82")
            continue

        portrait_path = portraits.get(_key(name))
        _draw_portrait(base, portrait_path, x + 4, y + 3, CELL_W - 8, 47)

        draw = ImageDraw.Draw(base)
        _centered(
            draw,
            (x + CELL_W / 2, y + 49),
            _fit_text(draw, name, _font(11, True), CELL_W - 8),
            _font(11, True),
            "#ffffff",
            CELL_W - 8,
        )

        value = int(brawler.get(metric_key, 0) or 0)
        if mode == "power":
            label = f"СИЛА {value}"
            pill_color = (96, 56, 150, 255)
        else:
            label = f"{value:,}".replace(",", " ")
            pill_color = (130, 86, 30, 255)
        draw.rounded_rectangle(
            (x + 8, y + 68, x + CELL_W - 8, y + 84),
            radius=6,
            fill=pill_color,
        )
        if mode == "trophies":
            _resource_icon(base, "icon_trophy.png", x + 17, y + 68, 15)
            _centered(draw, (x + CELL_W / 2 + 8, y + 68), label, _font(11, True), "#ffffff", CELL_W - 36)
        else:
            _centered(draw, (x + CELL_W / 2, y + 68), label, _font(11, True), "#ffffff", CELL_W - 20)

    draw = ImageDraw.Draw(base)
    draw.text(
        (MARGIN_X, FOOTER_Y),
        "META HELPER  •  BRAWL STARS  •  108 СЛОТОВ",
        font=_font(14, True),
        fill="#9e8bb9",
    )
    _centered(draw, (WIDTH - 100, FOOTER_Y), "POWER / TROPHIES", _font(13, True), "#e8dcff")

    output = io.BytesIO()
    base.convert("RGB").save(output, format="JPEG", quality=91, optimize=True)
    output.seek(0)
    output.name = f"meta_helper_{mode}.jpg"
    caption = f"{title.title()} • {player_name} • 108 ячеек"
    return [(output, caption)]
