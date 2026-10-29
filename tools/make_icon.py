"""Dibuja el icono (estrella con halo ámbar) y lo guarda en assets/icon.ico."""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

SIZE = 256
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico")


def star(cx, cy, r_out, r_in, points=4):
    pts = []
    for i in range(points * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.pi * i / points - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
halo = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(halo).ellipse((48, 48, 208, 208), fill=(255, 179, 71, 170))
img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(28)))
d = ImageDraw.Draw(img)
d.polygon(star(128, 128, 112, 26), fill=(255, 214, 140, 255))
d.ellipse((108, 108, 148, 148), fill=(255, 255, 255, 255))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icono:", OUT)
