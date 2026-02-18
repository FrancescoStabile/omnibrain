"""
OmniBrain — Share Card Generator

Generates a 1200×630 PNG image (Open Graph format) with personalised
onboarding stats for social sharing. Used by the onboarding reveal screen
and the /api/v1/share-card endpoint.

Falls back gracefully if Pillow is not installed — returns None.

Usage::

    from omnibrain.share_card import generate_share_card

    png_bytes = generate_share_card(
        stats={"emails": 247, "contacts": 12, "events": 8},
        insights_count=5,
        user_name="Francesco",
    )
"""

from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger("omnibrain.share_card")

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

WIDTH = 1200
HEIGHT = 630

# Brand colours
BG_COLOR = (15, 15, 20)  # --bg-primary
BRAND_PRIMARY = (99, 102, 241)  # indigo-500
ACCENT_ORANGE = (249, 115, 22)  # orange-500
TEXT_PRIMARY = (255, 255, 255)
TEXT_SECONDARY = (156, 163, 175)  # gray-400
TEXT_TERTIARY = (107, 114, 128)  # gray-500
BORDER_COLOR = (55, 65, 81)  # gray-700

# Gradient stops for logo bg
GRADIENT_START = BRAND_PRIMARY
GRADIENT_END = ACCENT_ORANGE


# ═══════════════════════════════════════════════════════════════════════════
# Core generator
# ═══════════════════════════════════════════════════════════════════════════


def generate_share_card(
    *,
    stats: dict[str, int],
    insights_count: int = 0,
    user_name: str = "",
    duration_ms: int = 0,
) -> bytes | None:
    """Generate a 1200×630 PNG share card.

    Returns PNG bytes, or None if Pillow is not available.

    Args:
        stats: {"emails": int, "contacts": int, "events": int}
        insights_count: Number of insights generated
        user_name: User's display name (optional)
        duration_ms: Analysis duration in milliseconds
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow not installed — share card generation unavailable")
        return None

    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── Load fonts (fall back to default if system fonts unavailable) ──
    font_title = _load_font(48)
    font_large = _load_font(36)
    font_stat_value = _load_font(64)
    font_stat_label = _load_font(18)
    font_body = _load_font(22)
    font_small = _load_font(16)
    font_cta = _load_font(20)

    # ── Subtle gradient accent bar at top ──
    for x in range(WIDTH):
        t = x / WIDTH
        r = int(GRADIENT_START[0] * (1 - t) + GRADIENT_END[0] * t)
        g = int(GRADIENT_START[1] * (1 - t) + GRADIENT_END[1] * t)
        b = int(GRADIENT_START[2] * (1 - t) + GRADIENT_END[2] * t)
        draw.line([(x, 0), (x, 4)], fill=(r, g, b))

    # ── Logo area ──
    # Draw a rounded rectangle "logo"
    logo_x, logo_y = 60, 40
    logo_size = 56
    draw.rounded_rectangle(
        [logo_x, logo_y, logo_x + logo_size, logo_y + logo_size],
        radius=14,
        fill=BRAND_PRIMARY,
    )
    # "O" letter inside logo
    _draw_centered_text(
        draw, "O", logo_x + logo_size // 2, logo_y + logo_size // 2,
        font_large, TEXT_PRIMARY,
    )

    # Brand name next to logo
    draw.text(
        (logo_x + logo_size + 16, logo_y + 8),
        "OmniBrain",
        fill=TEXT_PRIMARY,
        font=font_title,
    )

    # ── Tagline ──
    tagline = (
        f"Analyzed {user_name}'s digital life" if user_name
        else "Your AI just analyzed your digital life"
    )
    if duration_ms > 0:
        tagline += f" in {duration_ms / 1000:.1f} seconds"
    draw.text((60, 120), tagline, fill=TEXT_SECONDARY, font=font_body)

    # ── Stats row ──
    stat_items = [
        ("📧", str(stats.get("emails", 0)), "emails"),
        ("👥", str(stats.get("contacts", 0)), "contacts"),
        ("📅", str(stats.get("events", 0)), "events"),
    ]
    if insights_count > 0:
        stat_items.append(("💡", str(insights_count), "insights"))

    stat_y = 190
    stat_width = (WIDTH - 120) // len(stat_items)

    for i, (emoji, value, label) in enumerate(stat_items):
        cx = 60 + stat_width * i + stat_width // 2

        # Card background
        card_left = 60 + stat_width * i + 8
        card_right = card_left + stat_width - 16
        draw.rounded_rectangle(
            [card_left, stat_y, card_right, stat_y + 170],
            radius=16,
            fill=(25, 25, 35),
            outline=BORDER_COLOR,
            width=1,
        )

        # Emoji
        _draw_centered_text(draw, emoji, cx, stat_y + 35, font_large, TEXT_PRIMARY)

        # Value
        _draw_centered_text(draw, value, cx, stat_y + 95, font_stat_value, BRAND_PRIMARY)

        # Label
        _draw_centered_text(draw, label, cx, stat_y + 145, font_stat_label, TEXT_TERTIARY)

    # ── Divider ──
    divider_y = stat_y + 200
    draw.line([(60, divider_y), (WIDTH - 60, divider_y)], fill=BORDER_COLOR, width=1)

    # ── Quote / tagline ──
    quote = "Your AI must be yours."
    draw.text((60, divider_y + 20), quote, fill=TEXT_PRIMARY, font=font_large)

    # ── CTA ──
    cta_y = divider_y + 75
    cta_text = "Try it free → github.com/FrancescoStabile/omnibrain"
    draw.text((60, cta_y), cta_text, fill=BRAND_PRIMARY, font=font_cta)

    # ── Footer badges ──
    footer_y = HEIGHT - 50
    badges = ["🔒 Local-first", "🛡️ Privacy by design", "🆓 Open source"]
    badge_text = "  ·  ".join(badges)
    draw.text((60, footer_y), badge_text, fill=TEXT_TERTIARY, font=font_small)

    # ── Export ──
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _load_font(size: int) -> Any:
    """Load a font, falling back to Pillow's default if system fonts are unavailable."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None

    # Try common system fonts in order of preference
    font_paths = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        # Generic
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    # Fall back to default
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow versions don't accept size arg
        return ImageFont.load_default()


def _draw_centered_text(
    draw: Any,
    text: str,
    cx: int,
    cy: int,
    font: Any,
    fill: tuple[int, ...],
) -> None:
    """Draw text centered at (cx, cy)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(
        (cx - text_w // 2, cy - text_h // 2),
        text,
        fill=fill,
        font=font,
    )
