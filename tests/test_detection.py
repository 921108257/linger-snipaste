import io
import sys
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service'))
from detection import detect_regions


class DetectionTests(unittest.TestCase):
    def test_nested_containers_including_high_resolution(self):
        for scale in (1, 2):
            image = Image.new('RGB', (1000 * scale, 700 * scale), '#353535')
            draw = ImageDraw.Draw(image)
            for rect, color in (((100, 80, 900, 620), '#eeeeee'), ((160, 160, 460, 480), '#ffffff'),
                                ((510, 160, 840, 320), '#787878')):
                draw.rectangle(tuple(n * scale for n in rect), fill=color)
            png = io.BytesIO(); image.save(png, 'PNG')
            regions = detect_regions(png.getvalue())
            for x, y, w, h in ((.1, 80/700, .8, 540/700), (.16, 160/700, .3, 320/700), (.51, 160/700, .33, 160/700)):
                self.assertTrue(any(max(abs(r[k] - v) for k, v in zip(('x', 'y', 'width', 'height'), (x, y, w, h))) < .012 for r in regions), regions)

    def test_blank_screenshot_has_no_false_container(self):
        image = Image.new('RGB', (800, 600), '#eeeeee')
        png = io.BytesIO(); image.save(png, 'PNG')
        self.assertEqual(detect_regions(png.getvalue()), [])
