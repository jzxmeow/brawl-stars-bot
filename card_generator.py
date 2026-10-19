import io
import re
from functools import lru_cache
from pathlib import Path

import requests

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
PORTRAITS_DIR = ROOT / "portraits"
RESOURCES_DIR = ROOT / "resourses"

# One image with 108 slots: 12 columns x 9 rows.
WIDTH = 2160
HEIGHT = 1250
COLUMNS = 12
ROWS = 9
SLOTS = COLUMNS * ROWS
MARGIN_X = 20
GRID_TOP = 150
CELL_W = 166
CELL_H = 100
PORTRAIT_W = 100
GAP_X = 7
GAP_Y = 5
FOOTER_Y = 1185

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


@lru_cache(maxsize=64)
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

# Current roster data: as of October 2026, the roster contains 108 brawlers;
# Cosmo and Vince are the two without a released Hypercharge. The official
# player API does not expose whether a player has actually unlocked it.
NO_HYPERCHARGE = {_key("Cosmo"), _key("Vince")}
HYPERCHARGE_BRAWLERS = {
    _key(name) for name in RARITY_BY_NAME
    if _key(name) not in NO_HYPERCHARGE
}
HYPERCHARGE_TOTAL = len(HYPERCHARGE_BRAWLERS)


def _portrait_index():
    index = {}
    if PORTRAITS_DIR.exists():
        for path in PORTRAITS_DIR.iterdir():
            if path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}:
                index[_key(path.stem)] = path
    return index


@lru_cache(maxsize=1)
def _background():
    # Cached because each card uses the same static background.
    background_path = RESOURCES_DIR / "yiuDhs4ftqkUwdHbwgcE.png"
    if background_path.exists():
        try:
            with Image.open(background_path) as source:
                return ImageOps.fit(
                    source.convert("RGB"),
                    (WIDTH, HEIGHT),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
        except (OSError, ValueError):
            pass

    # Fast gradient fallback: draw one horizontal line per row instead of
    # assigning 2.56 million pixels in Python.
    image = Image.new("RGB", (WIDTH, HEIGHT), "#100d1c")
    draw = ImageDraw.Draw(image)
    top = (13, 12, 29)
    bottom = (43, 20, 70)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, WIDTH, y), fill=color)
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


@lru_cache(maxsize=128)
def _cached_player_avatar(icon_id, size):
    """Fetch and cache a player's profile icon between card generations."""
    avatar = None
    if icon_id is not None:
        try:
            response = requests.get(
                f"https://cdn.brawlify.com/profile-icons/regular/{int(icon_id)}.png",
                timeout=2,
            )
            if response.ok:
                with Image.open(io.BytesIO(response.content)) as source:
                    avatar = source.convert("RGBA")
        except (requests.RequestException, OSError, ValueError, TypeError):
            avatar = None

    if avatar is None:
        avatar = Image.new("RGBA", (size, size), (67, 42, 98, 255))
        fallback_draw = ImageDraw.Draw(avatar)
        _centered(fallback_draw, (size / 2, size / 13), "?", _font(38, True), "#eee5ff")

    return ImageOps.fit(avatar, (size, size), method=Image.Resampling.LANCZOS)


def _draw_player_avatar(canvas, player, x, y, size):
    icon = player.get("icon") or {}
    icon_id = icon.get("id") if isinstance(icon, dict) else None
    avatar = _cached_player_avatar(icon_id, size)
    canvas.alpha_composite(avatar, (x, y))
 

@lru_cache(maxsize=256)
def _cached_twemoji(code, size):
    """Download and cache an emoji image so repeated card requests do not refetch it."""
    try:
        response = requests.get(
            f"https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/{code}.png",
            timeout=1.5,
        )
        if response.ok:
            with Image.open(io.BytesIO(response.content)) as source:
                glyph = source.convert("RGBA")
            glyph.thumbnail((size, size), Image.Resampling.LANCZOS)
            return glyph
    except (requests.RequestException, OSError, ValueError):
        pass
    return None


def _draw_text_with_emoji(canvas, xy, text, font, fill):
    """Draw text and use Twemoji PNGs for emoji glyphs missing from server fonts."""
    draw = ImageDraw.Draw(canvas)
    x, y = xy
    emoji_ranges = (
        (0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2300, 0x23FF),
        (0x1F1E6, 0x1F1FF),
    )
    for char in str(text):
        cp = ord(char)
        # Variation selectors, joiners and skin-tone modifiers should not become tofu boxes.
        if cp in (0xFE0E, 0xFE0F, 0x200D) or 0x1F3FB <= cp <= 0x1F3FF:
            continue
        is_emoji = any(start <= cp <= end for start, end in emoji_ranges)
        if is_emoji:
            code = f"{cp:x}"
            glyph = _cached_twemoji(code, font.size + 2)
            if glyph is not None:
                canvas.alpha_composite(glyph, (int(x), int(y + max(0, (font.size - glyph.height) / 2))))
                x += font.size + 3
                continue
        draw = ImageDraw.Draw(canvas)
        draw.text((int(x), int(y)), char, font=font, fill=fill)
        try:
            advance = draw.textlength(char, font=font)
        except AttributeError:
            box = draw.textbbox((0, 0), char, font=font)
            advance = box[2] - box[0]
        x += max(1, advance)


def _draw_centered_text_with_emoji(canvas, center_x, y, text, font, fill, max_width):
    """Center a nickname/label while reserving space for image-rendered emoji."""
    width = 0
    draw = ImageDraw.Draw(canvas)
    emoji_ranges = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2300, 0x23FF))
    for char in str(text):
        cp = ord(char)
        if cp in (0xFE0E, 0xFE0F, 0x200D) or 0x1F3FB <= cp <= 0x1F3FF:
            continue
        if any(start <= cp <= end for start, end in emoji_ranges):
            width += font.size + 3
        else:
            try:
                width += draw.textlength(char, font=font)
            except AttributeError:
                box = draw.textbbox((0, 0), char, font=font)
                width += box[2] - box[0]
    if width > max_width:
        text = _fit_text(draw, text, font, max_width)
        width = min(width, max_width)
    _draw_text_with_emoji(canvas, (center_x - width / 2, y), text, font, fill)


@lru_cache(maxsize=128)
def _cached_resource_icon(filename, size):
    path = RESOURCES_DIR / filename
    if not path.exists():
        return None
    try:
        with Image.open(path) as source:
            icon = source.convert("RGBA")
        icon.thumbnail((size, size), Image.Resampling.LANCZOS)
        return icon
    except (OSError, ValueError):
        return None


def _resource_icon(canvas, filename, x, y, size):
    """Paste a cached, pre-scaled transparent resource icon."""
    icon = _cached_resource_icon(filename, size)
    if icon is None:
        return False
    canvas.alpha_composite(
        icon, (int(x + (size - icon.width) / 2), int(y + (size - icon.height) / 2))
    )
    return True


def _has_hypercharge(brawler):
    for key in ("hypercharge", "hyperCharge", "hypercharges"):
        value = brawler.get(key)
        if value:
           return True
    return _key(brawler.get("name", "")) in HYPERCHARGE_BRAWLERS


@lru_cache(maxsize=32)
def _cached_badge_art(filename, size):
    path = RESOURCES_DIR / filename
    if not path.exists():
        return None
    try:
        with Image.open(path) as source:
            art = source.convert("RGBA")
        art.thumbnail((size, size), Image.Resampling.LANCZOS)
        badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        badge.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
        return badge
    except (OSError, ValueError):
        return None


def _draw_power_badge(canvas, brawler, cell_x, cell_y):
    """Draw a clearly visible power badge in the top-right corner of each brawler cell."""
    value = int(brawler.get("power", 0) or 0)
    has_hypercharge = value == 11 and _has_hypercharge(brawler)
    # Hypercharge artwork is oversized, aligned to the top-right, and slightly
    # overlaps the cell's upper edge for a more prominent badge.
    size = 115 if has_hypercharge else 44
    # Anchor the hypercharge to the cell's top-right corner: 40% of its
    # height protrudes above the cell, with only a small overlap to the right.
    # Regular power badges stay 44px and protrude slightly less in both directions.
    x = cell_x + CELL_W - size + 12 if has_hypercharge else cell_x + CELL_W - size + 4
    y = cell_y - int(size * 0.40) if has_hypercharge else cell_y - 5

    if value == 11:
        filename = (
            "Picsart_26-10-17_23-40-21-172.png"
            if _has_hypercharge(brawler)
            else "Picsart_26-10-17_23-04-28-907.png"
        )
        badge = _cached_badge_art(filename, size)
        if badge is not None:
            canvas.alpha_composite(badge, (int(x), int(y)))
            return

    # Below Power 11: subtle purple outline, kept thin so it doesn't overpower the portrait.
    badge_draw = ImageDraw.Draw(canvas)
    badge_draw.rounded_rectangle(
        (x, y, x + size - 1, y + size - 1),
        radius=8,
        fill=(0, 0, 0, 245),
        outline=(153, 91, 218, 230),
        width=2,
    )
    font = _font(21, True)
    box = badge_draw.textbbox((0, 0), str(value), font=font)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    badge_draw.text((x + (size - text_w) / 2, y + (size - text_h) / 2 - box[1]),
                    str(value), font=font, fill="#ffffff")


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

    # Count Power 11 brawlers whose Hypercharge exists in the game. This is
    # availability, not verified ownership: Supercell's player endpoint omits ownership.
    hypercharges = sum(
        1 for brawler in brawlers
        if int(brawler.get("power", 0) or 0) == 11
        and _key(brawler.get("name", "")) in HYPERCHARGE_BRAWLERS
    )

    # Compact 2-column x 2-row layout, aligned consistently in the header.
    # Left column: gadgets above star powers. Right column: gears above hypercharges.
    items = [
        (850, 42, "gadget.png", f"{gadgets}/216"),
        (850, 84, "starpower.png", f"{star_powers}/216"),
        (1100, 42, "gear.png", f"{gears}"),
        (1100, 84, "hypercharge.png", f"{hypercharges}/{HYPERCHARGE_TOTAL}"),
    ]
    for x, y, filename, label in items:
        _resource_icon(canvas, filename, x, y, 28)
        draw.text((x + 36, y + 6), label, font=_font(17, True), fill="#f0e7ff")


@lru_cache(maxsize=256)
def _cached_portrait(path_string, max_w, max_h):
    try:
        with Image.open(path_string) as source:
            portrait = source.convert("RGBA")
        return ImageOps.fit(
            portrait, (max_w, max_h), method=Image.Resampling.LANCZOS
        )
    except (OSError, ValueError):
        return None


def _draw_portrait(canvas, path, x, y, max_w, max_h):
    if not path or not path.exists():
        return False
    portrait = _cached_portrait(str(path), max_w, max_h)
    if portrait is None:
        return False
    canvas.alpha_composite(portrait, (x, y))
    return True


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
    player_name = str(player.get("name", "Неизвестный игрок"))
    tag = str(player.get("tag", "")).lstrip("#")

    # Player avatar on the far left, with the tag directly underneath.
    _draw_player_avatar(base, player, 48, 31, 70)
    _centered(draw, (83, 105), f"#{tag}", _font(13, True), "#d9c4ff", 120)

    # The nickname is the main header element; title/brand are already in the footer.
    draw = ImageDraw.Draw(base)
    name_font = _font(40, True)
    nickname = _fit_text(draw, player_name, name_font, 660)
    _draw_text_with_emoji(base, (140, 47), nickname, name_font, "#ffffff")

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
            _centered(draw, (x + CELL_W / 2, y + 15), "?", _font(36, True), "#625078")
            _centered(draw, (x + CELL_W / 2, y + 63), "—", _font(17, True), "#6e5b82")
            continue

        portrait_path = portraits.get(_key(name))
        # Large portrait fills the cell height; names are intentionally hidden.
        portrait_x, portrait_y = x, y
        _draw_portrait(base, portrait_path, portrait_x, portrait_y, PORTRAIT_W, CELL_H)
        if mode == "power":
            _draw_power_badge(base, brawler, x, y)

        if mode == "trophies":
            value = int(brawler.get(metric_key, 0) or 0)
            label = f"{value:,}".replace(",", " ")
            text_left = x + PORTRAIT_W + 4
            text_width = CELL_W - PORTRAIT_W - 8
            draw = ImageDraw.Draw(base)
            draw.rounded_rectangle(
                (text_left, y + 35, x + CELL_W - 6, y + 65),
                radius=7,
                fill=(130, 86, 30, 255),
            )
            _resource_icon(base, "icon_trophy.png", text_left + 2, y + 42, 16)
            _centered(draw, (text_left + text_width / 2 + 8, y + 40), label, _font(12, True), "#ffffff", text_width - 20)

    draw = ImageDraw.Draw(base)
    draw.text(
        (MARGIN_X, FOOTER_Y),
        "META HELPER  •  BRAWL STARS  •  108 СЛОТОВ",
        font=_font(14, True),
        fill="#9e8bb9",
    )
    footer_mode = "СИЛА" if mode == "power" else "КУБКИ"
    _centered(draw, (WIDTH - 100, FOOTER_Y), footer_mode, _font(16, True), "#e8dcff")

    output = io.BytesIO()
    # optimize=True spends extra CPU on Huffman-table optimization; disabling it
    # makes the card noticeably faster to encode at a nearly identical visual quality.
    base.convert("RGB").save(output, format="JPEG", quality=88, optimize=False, subsampling=1)
    output.seek(0)
    output.name = f"meta_helper_{mode}.jpg"
    caption = f"{title.title()} • {player_name} • 108 ячеек"
    return [(output, caption)]
