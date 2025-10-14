import io
import os
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import requests

Size = Tuple[int, int]

def load_image(path_or_url: str) -> Image.Image:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        r = requests.get(path_or_url, timeout=20)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
    else:
        img = Image.open(path_or_url)
    return img.convert("RGB")

def cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    iw, ih = img.size
    sr = max(target_w / iw, target_h / ih)
    nw, nh = int(iw * sr), int(ih * sr)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    return img.crop((left, top, left + target_w, top + target_h))

def ensure_font(paths: List[Optional[str]], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def ensure_apple_emoji_font(paths: List[Optional[str]], size: int = 48) -> ImageFont.FreeTypeFont:
    for p in paths:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception as e:
                print(f"Failed to load font {p}: {e}")
                pass
    raise RuntimeError("Apple Color Emoji font not found. Provide Apple Color Emoji.ttc via emoji_font_path or place it next to the script.")

def draw_block_rounded(img: Image.Image, box: Tuple[int, int, int, int], radius: int, fill: Tuple[int, int, int]):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=radius, fill=fill)

def _is_emoji_start(ch: str) -> bool:
    cp = ord(ch)
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return True
    if 0x1F300 <= cp <= 0x1FAFF:
        return True
    if 0x2600 <= cp <= 0x26FF:
        return True
    if 0x2700 <= cp <= 0x27BF:
        return True
    return ch in ("©", "®", "™", "#", "*")

def _is_emoji_extender(ch: str) -> bool:
    cp = ord(ch)
    if ch == "\u200d":
        return True
    if cp == 0xFE0F:
        return True
    if 0x1F3FB <= cp <= 0x1F3FF:
        return True
    if 0x20E3 == cp:
        return True
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return True
    return False

def split_into_emoji_clusters(s: str) -> List[Tuple[str, bool]]:
    res: List[Tuple[str, bool]] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if _is_emoji_start(ch):
            j = i + 1
            while j < n:
                if _is_emoji_extender(s[j]):
                    j += 1
                    continue
                if j < n and s[j - 1] == "\u200d":
                    j += 1
                    continue
                break
            res.append((s[i:j], True))
            i = j
        else:
            j = i + 1
            while j < n and not _is_emoji_start(s[j]):
                j += 1
            res.append((s[i:j], False))
            i = j
    return res

def measure_mixed_text_width(s: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, bold_font: ImageFont.FreeTypeFont, emoji_font: ImageFont.FreeTypeFont) -> int:
    width = 0
    i = 0
    bold = False
    buf = ""
    while i < len(s):
        if s[i:i+2] == "**":
            if buf:
                chunks = split_into_emoji_clusters(buf)
                for chunk, is_emoji in chunks:
                    if is_emoji:
                        width += int(draw.textlength(chunk, font=emoji_font))
                    else:
                        f = bold_font if bold else font
                        width += int(draw.textlength(chunk, font=f))
                buf = ""
            bold = not bold
            i += 2
        else:
            buf += s[i]
            i += 1
    if buf:
        chunks = split_into_emoji_clusters(buf)
        for chunk, is_emoji in chunks:
            if is_emoji:
                width += int(draw.textlength(chunk, font=emoji_font))
            else:
                f = bold_font if bold else font
                width += int(draw.textlength(chunk, font=f))
    return width

def layout_lines(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, bold_font: ImageFont.FreeTypeFont, emoji_font: ImageFont.FreeTypeFont, max_width: int, line_h: int) -> List[str]:
    out_lines: List[str] = []
    for raw in text.split("\n"):
        if raw == "":
            out_lines.append("")
            continue
        words = raw.split(" ")
        cur = ""
        for w in words:
            t = (cur + " " + w).strip()
            if measure_mixed_text_width(t, draw, font, bold_font, emoji_font) <= max_width:
                cur = t
            else:
                if cur:
                    out_lines.append(cur)
                cur = w
        if cur:
            out_lines.append(cur)
    return out_lines

def draw_rich_lines_with_emoji(draw: ImageDraw.ImageDraw, start_xy: Tuple[int, int], text: str, font: ImageFont.FreeTypeFont, bold_font: ImageFont.FreeTypeFont, emoji_font: ImageFont.FreeTypeFont, color: Tuple[int, int, int], max_width: int, line_h: int) -> int:
    x0, y = start_xy
    lines = layout_lines(text, draw, font, bold_font, emoji_font, max_width, line_h)
    for line in lines:
        if line == "":
            y += line_h
            continue
        cx = x0
        i = 0
        bold = False
        buf = ""
        while i < len(line):
            if line[i:i+2] == "**":
                if buf:
                    chunks = split_into_emoji_clusters(buf)
                    for chunk, is_emoji in chunks:
                        if is_emoji:
                            try:
                                draw.text((cx, y), chunk, font=emoji_font, embedded_color=True)
                            except TypeError:
                                draw.text((cx, y), chunk, font=emoji_font)
                            cx += int(draw.textlength(chunk, font=emoji_font))
                        else:
                            f = bold_font if bold else font
                            draw.text((cx, y), chunk, font=f, fill=color)
                            cx += int(draw.textlength(chunk, font=f))
                    buf = ""
                bold = not bold
                i += 2
            else:
                buf += line[i]
                i += 1
        if buf:
            chunks = split_into_emoji_clusters(buf)
            for chunk, is_emoji in chunks:
                if is_emoji:
                    try:
                        draw.text((cx, y), chunk, font=emoji_font, embedded_color=True)
                    except TypeError:
                        draw.text((cx, y), chunk, font=emoji_font)
                    cx += int(draw.textlength(chunk, font=emoji_font))
                else:
                    f = bold_font if bold else font
                    draw.text((cx, y), chunk, font=f, fill=color)
                    cx += int(draw.textlength(chunk, font=f))
        y += line_h
    return y

def build_post(
    images: List[str],
    out_path: str = "post.png",
    canvas: Size = (1080, 1920),
    bg_color: Tuple[int, int, int] = (16, 24, 32),
    gutter: int = 16,
    outer_pad: int = 24,
    font_regular_path: Optional[str] = None,
    font_bold_path: Optional[str] = None,
    emoji_font_path: Optional[str] = None,
    link_text: str = "",
    body_text: str = "",
    link_font_size: int = 38,
    body_font_size: int = 48,
    link_line_h: int = 56,
    body_line_h: int = 60,
):
    W, H = canvas
    base = Image.new("RGB", canvas, bg_color)

    f_reg = ensure_font([
        font_regular_path,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ], body_font_size)
    f_bold = ensure_font([
        font_bold_path,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ], body_font_size)
    f_emoji = ensure_apple_emoji_font([
        emoji_font_path,
    ], body_font_size)

    x_left = outer_pad
    x_right = W - outer_pad
    y = outer_pad

    top_h = 660
    if len(images) < 3:
        raise ValueError("Need 3 images")
    img_top = cover_resize(load_image(images[0]), x_right - x_left, top_h)
    base.paste(img_top, (x_left, y))
    y += top_h + gutter

    half_w = (x_right - x_left - gutter) // 2
    bot_h = 360
    img_l = cover_resize(load_image(images[1]), half_w, bot_h)
    img_r = cover_resize(load_image(images[2]), half_w, bot_h)
    base.paste(img_l, (x_left, y))
    base.paste(img_r, (x_left + half_w + gutter, y))
    y += bot_h + gutter

    panel_pad = 28
    panel_box = (outer_pad, y, W - outer_pad, H - outer_pad)
    draw_block_rounded(base, panel_box, 24, (11, 34, 58))

    inner_x = panel_box[0] + panel_pad
    inner_y = panel_box[1] + panel_pad
    inner_w = panel_box[2] - panel_pad - inner_x

    f_link = f_reg.font_variant(size=link_font_size)
    f_body = f_reg.font_variant(size=body_font_size)
    f_body_b = f_bold.font_variant(size=body_font_size)

    d = ImageDraw.Draw(base)
    link_color = (160, 200, 255)
    text_color = (232, 240, 248)

    if not link_text:
        link_text = "https://bidauto.online/lot/43023473?auction_name=IAAI"
    if not body_text:
        body_text = (
            "📲 Susisiekite : https://t.me/bidautoLT\n"
            "🔥🚗 Labai geras pasiūlymas aukcione! 🔥🚗\n"
            "🗓️ 2022 Audi Q7\n"
            "🧭 1 miles\n"
            "⚠️ **REZERVAS: $19,500**\n"
            "🧾 Pardavėjas: Draudimas 👍\n"
            "🔑 VIN: WA1LXBFP9N0D20394\n"
            "🅿️ Būklė: Stationary\n"
            "📄 Dokumentai: Tinka registracijai 👍\n"
            "🚚 Transporto išlaidos sudarys:\n"
            " Vietinis Transportas: $400\n"
            " Jūrinis pervežimas: $775\n"
            " Broker Fee: $299\n"
            "***Taip pat prisidės aukciono mokesčiai kurie priklauso nuo statymo sumos!***\n"
            "🇱🇹 Lietuvoje liks sumokėti:\n"
            " ✅ 10% Muitas\n"
            " ✅ 21% PVM\n"
            " ✅ 350€ Krova\n"
            "⏳ Liko mažai laiko – nepraleiskite progos! 🕒🏁\n"
            "📈 **VIDUTINĖ pardavimo kaina: $23643**\n"
            "✉️ Rašykite mums DM arba apsilankykite 👉 bidauto.online"
        )

    inner_y = draw_rich_lines_with_emoji(d, (inner_x, inner_y), link_text, f_link, f_link, f_emoji, link_color, inner_w, link_line_h)
    inner_y += 6
    inner_y = draw_rich_lines_with_emoji(d, (inner_x, inner_y), body_text, f_body, f_body_b, f_emoji, text_color, inner_w, body_line_h)

    base.save(out_path, "PNG")

if __name__ == "__main__":
    images = [
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
    ]
    link_text = "https://bidauto.online/lot/43023473?auction_name=IAAI"
    build_post(
        images=images,
        out_path="post.png",
        emoji_font_path='apple_font.ttc',
        link_text=link_text,)
        # body_text=body_text,    )