import io
import re
import html
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
import requests
import PIL as PIL_pkg

from app.core.logger import logger
from app.core.utils import BASE_DIR

Size = Tuple[int, int]

def load_image(path_or_url: str) -> Image.Image:
    try:
        if path_or_url.startswith(("http://", "https://")):
            r = requests.get(path_or_url, timeout=20)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
        else:
            img = Image.open(path_or_url)
        return img.convert("RGB")
    except Exception as e:
        logger.error(f"Failed to load image {path_or_url}: {e}")

def cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    iw, ih = img.size
    sr = max(target_w / iw, target_h / ih)
    nw, nh = int(iw * sr), int(ih * sr)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    return img.crop((left, top, left + target_w, top + target_h))

def make_rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    img.putalpha(mask)
    return img

def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    lines: List[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split()
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=font) <= max_width or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines

def resolve_font_path() -> Optional[str]:
    candidates = [
        Path(__file__).parent / "SF-Pro.ttf",
    ]
    for p in candidates:
        try:
            path = Path(p)
            if path.exists():
                print(path)
                return str(path)
        except Exception:
            continue
    return None

def pick_font(size: int) -> ImageFont.FreeTypeFont:
    fp = resolve_font_path()
    if fp:
        return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

def compute_line_height(font: ImageFont.FreeTypeFont, multiplier: float = 1.25) -> int:
    try:
        ascent, descent = font.getmetrics()
        return max(1, int((ascent + descent) * multiplier))
    except Exception:
        return max(1, int(getattr(font, "size", 16) * multiplier))

def html_to_plain(text: str) -> str:
    t = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", text)
    t = re.sub(r"(?is)</\s*p\s*>", "\n", t)
    t = re.sub(r"(?is)<\s*p[^>]*>", "", t)
    t = re.sub(r"(?is)<\s*/?\s*(b|strong|i|em|u|span|div|h[1-6])[^>]*>", "", t)
    t = re.sub(r'(?is)<\s*a[^>]*>(.*?)</\s*a\s*>', r"\1", t)
    t = re.sub(r"(?is)<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t

def build_post(
    images: List[str],
    text: str,
    canvas: Size = (1080, 1920),
    bg_color = (16, 24, 32),
    gutter: int = 16,
    outer_pad: int = 24,
    font_size: int = 64,
    line_h: Optional[int] = None,
) -> bytes:
    if len(images) < 3:
        raise ValueError("Need 3 images")

    text = html_to_plain(text)

    W, H = canvas
    base = Image.new("RGBA", canvas, bg_color)
    d = ImageDraw.Draw(base)

    x_left = outer_pad
    x_right = W - outer_pad
    y = outer_pad

    top_h = 510
    img_top = make_rounded(cover_resize(load_image(images[0]), x_right - x_left, top_h), 24)
    base.paste(img_top, (x_left, y), img_top)
    y += top_h + gutter

    half_w = (x_right - x_left - gutter) // 2
    bot_h = 360
    img_l = make_rounded(cover_resize(load_image(images[1]), half_w, bot_h), 24)
    img_r = make_rounded(cover_resize(load_image(images[2]), half_w, bot_h), 24)
    base.paste(img_l, (x_left, y), img_l)
    base.paste(img_r, (x_left + half_w + gutter, y), img_r)
    y += bot_h + gutter

    panel_pad = 28
    panel_box = (outer_pad, y, W - outer_pad, H - outer_pad)
    ImageDraw.Draw(base).rounded_rectangle(panel_box, radius=24, fill=(11, 34, 58))

    inner_x = panel_box[0] + panel_pad
    inner_y = panel_box[1] + panel_pad
    inner_w = panel_box[2] - panel_pad - inner_x

    font = pick_font(font_size)
    lh = line_h if isinstance(line_h, int) and line_h > 0 else compute_line_height(font, 1.25)
    text_color = (232, 240, 248)

    lines = wrap_text(d, text, font, inner_w)

    with Pilmoji(base) as pm:
        for line in lines:
            pm.text((inner_x, inner_y), line, font=font, fill=text_color)
            inner_y += lh

    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="PNG")
    data = buf.getvalue()
    return data

if __name__ == "__main__":
    images = [
        "https://vis.iaai.com/deepzoom?imageKey=41886506~SID~B457~S0~I1~RW2576~H1932~TH0&level=12&x=0&y=0&overlap=0&tilesize=5000",
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
        "https://cs.copart.com/v1/AUTH_svc.pdoc00001/ids-c-prod-lpp/0325/0d6d28068e6747c9b35d011930deefdc_hrs.jpg",
    ]
    text = '''<b>📲 Susisiekite:</b> <a href="https://t.me/bidautoLT">https://t.me/bidautoLT</a><br>
🚗🔥 Labai geras pasiūlymas aukcione! 🔥🚗<br>
🚗 2015 AUDI S4 3.0T PREMIUM PLUS<br>
🕔 76345 miles<br>
⚠️ REZERVAS: $N/A<br>
📌 Pardavėjas: Draudimas 👍<br>
📌 VIN: WAUBGAFL7FA023481<br>
📌 Būklė: Run & Drive<br>
🔧 Pirminė žala: HAIL<br>
📌 Dokumentai: Tinka registracijai 👍<br>
⏳ Aukcionas prasideda: 14.10.2025 17:30 (Vilnius)<br>
🛳️ Transporto išlaidos sudarys:<br>
Vietinis Transportas: $450<br>
Jūrinis pervežimas: $350<br>
Broker Fee: $299<br>
*** Taip pat prisidės aukciono mokesčiai, kurie priklauso nuo statymo sumos!<br>
🇱🇹 Lietuvoje liks sumokėti:<br>
✅ 10% Muitas<br>
✅ 21% PVM<br>
✅ 350€ Krova<br>
⏳ Liko mažai laiko – nepraleiskite progos! ⏳💨<br>
💸 VIDUTINĖ pardavimo kaina: $3931<br>
✉️ Rašykite mums DM arba apsilankykite 👉 <a href="https://bidauto.online">bidauto.online</a>'''
    img_bytes = build_post(images=images, text=text, font_size=32, line_h=20)
    with open("test.png", "wb") as f:
        f.write(img_bytes)
    print(len(img_bytes))
