import colorsys
import unittest

from PIL import Image

from brillomusical import color


def hsv(rgb):
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))


class TestColor(unittest.TestCase):
    def test_gris_da_ambar(self):
        self.assertEqual(color.dominant(Image.new("RGB", (50, 50), (128, 128, 128))), color.FALLBACK)

    def test_negro_con_rojo_elige_rojo(self):
        img = Image.new("RGB", (100, 100), (5, 5, 5))
        img.paste((200, 30, 30), (0, 0, 100, 30))
        r, g, b = color.dominant(img)
        self.assertTrue(r > g and r > b)

    def test_resultado_saturado_y_luminoso(self):
        h, s, v = hsv(color.dominant(Image.new("RGB", (10, 10), (60, 80, 50))))
        self.assertGreaterEqual(s, 0.54)
        self.assertGreaterEqual(v, 0.74)

    def test_acepta_bytes(self):
        import io
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (0, 0, 200)).save(buf, "PNG")
        r, g, b = color.from_bytes(buf.getvalue())[0][0]
        self.assertTrue(b > r and b > g)

    def test_backdrop_textura_difuminada(self):
        import io
        img = Image.new("RGB", (300, 200), (0, 0, 0))
        img.paste((255, 255, 255), (0, 0, 150, 200))  # mitad blanca, mitad negra: el borde se suaviza
        buf = io.BytesIO()
        img.save(buf, "PNG")
        data, lum = color.backdrop(buf.getvalue())
        self.assertEqual(len(data), color.BACKDROP * color.BACKDROP * 3)
        self.assertTrue(0.3 < lum < 0.7)
        mid = Image.frombytes("RGB", (color.BACKDROP, color.BACKDROP), data).getpixel((color.BACKDROP // 2, 64))
        self.assertTrue(30 < mid[0] < 225)  # gris en la frontera: está difuminado

    def test_caratula_cuadrada_ampliada(self):
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (160, 120), (0, 0, 255))
        img.paste((255, 0, 0), (0, 0, 20, 120))  # franja que el recorte centrado debe quitar
        img.save(buf, "PNG")
        data, side = color.cover(buf.getvalue())
        self.assertEqual(side, 256)
        self.assertEqual(len(data), side * side * 3)
        px = Image.frombytes("RGB", (side, side), data).getpixel((2, 128))
        self.assertGreater(px[2], px[0])  # el borde izquierdo ya es azul: recortado

    def test_caratula_grande_se_limita_a_1024(self):
        import io
        buf = io.BytesIO()
        Image.new("RGB", (1400, 1400), (10, 200, 10)).save(buf, "PNG")
        self.assertEqual(color.cover(buf.getvalue())[1], 1024)

    def test_calido(self):
        self.assertTrue(color.is_warm((255, 120, 40)))
        self.assertTrue(color.is_warm((255, 40, 120)))  # tono > 330°
        self.assertFalse(color.is_warm((60, 120, 255)))

    def test_paleta_gris_da_ambar(self):
        self.assertEqual(color.palette(Image.new("RGB", (20, 20), (128, 128, 128))), [color.FALLBACK])

    def test_paleta_dos_colores(self):
        img = Image.new("RGB", (100, 100), (200, 30, 30))
        img.paste((30, 30, 200), (0, 0, 100, 50))
        pal = color.palette(img)
        self.assertEqual(len(pal), 2)

    def test_paleta_maximo_3_sin_grises(self):
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        for i, c in enumerate([(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]):
            img.paste(c, (0, i * 20, 100, i * 20 + 20))
        pal = color.palette(img)
        self.assertEqual(len(pal), 3)
        for rgb in pal:
            self.assertGreaterEqual(hsv(rgb)[1], 0.54)

    def test_from_bytes_aspecto(self):
        import io
        buf = io.BytesIO()
        Image.new("RGB", (160, 90), (0, 0, 200)).save(buf, "PNG")
        self.assertAlmostEqual(color.from_bytes(buf.getvalue())[1], 160 / 90)


if __name__ == "__main__":
    unittest.main()
