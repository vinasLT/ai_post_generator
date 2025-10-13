import io
import os
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
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

def ensure_font(paths: List[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def draw_block_rounded(img: Image.Image, box: Tuple[int, int, int, int], radius: int, fill: Tuple[int, int, int]):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=radius, fill=fill)

def draw_rich_lines(pm: Pilmoji, start_xy: Tuple[int, int], text: str, font: ImageFont.FreeTypeFont, bold_font: ImageFont.FreeTypeFont, color: Tuple[int, int, int], max_width: int, line_h: int) -> int:
    x0, y = start_xy
    d = ImageDraw.Draw(pm.image)
    for raw_line in text.split("\n"):
        if raw_line == "":
            y += line_h
            continue
        words = raw_line.split(" ")
        lines = []
        cur = ""
        for w in words:
            t = (cur + " " + w).strip()
            bb = d.textbbox((0, 0), t.replace("**", ""), font=font)
            if bb[2] - bb[0] <= max_width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        for line in lines:
            cx = x0
            buf = ""
            is_bold = False
            i = 0
            while i < len(line):
                if line[i:i+2] == "**":
                    if buf:
                        f = bold_font if is_bold else font
                        pm.text((cx, y), buf, font=f, fill=color)
                        cx += int(d.textlength(buf, font=f))
                        buf = ""
                    is_bold = not is_bold
                    i += 2
                else:
                    buf += line[i]
                    i += 1
            if buf:
                f = bold_font if is_bold else font
                pm.text((cx, y), buf, font=f, fill=color)
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
):
    W, H = canvas
    base = Image.new("RGB", canvas, bg_color)

    f_reg = ensure_font([
        font_regular_path,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ], 42)
    f_bold = ensure_font([
        font_bold_path,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ], 42)

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

    f_link = f_reg.font_variant(size=36)
    f_body = f_reg.font_variant(size=42)
    f_body_b = f_bold.font_variant(size=42)

    with Pilmoji(base) as pm:
        link_color = (160, 200, 255)
        text_color = (232, 240, 248)
        inner_y = draw_rich_lines(pm, (inner_x, inner_y), "https://bidauto.online/lot/43023473?auction_name=IAAI", f_link, f_link, link_color, inner_w, 54)
        inner_y += 6
        txt = (
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
        inner_y = draw_rich_lines(pm, (inner_x, inner_y), txt, f_body, f_body_b, text_color, inner_w, 58)

    base.save(out_path, "PNG")

if __name__ == "__main__":
    images = [
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
    ]
    build_post(images, out_path="post.png")
