import io
from pathlib import Path
import unittest
from PIL import Image
from openkatana.temporal import sample_times, average_png
from openkatana.scene3d import validate, starter
from openkatana.contracts import ContractError


def png(rgba):
    out=io.BytesIO();Image.new('RGBA',(2,2),rgba).save(out,format='PNG');return out.getvalue()


class TemporalTests(unittest.TestCase):
    def test_shutter_samples_are_centered_and_clipped(self):
        self.assertEqual(sample_times(4,10,4,1),[3.625,3.875,4.125,4.375])
        self.assertEqual(sample_times(0,10,4,1)[:2],[0,0])
        self.assertEqual(sample_times(9,10,4,1)[-2:],[9,9])
        self.assertEqual(sample_times(4,10,1,.5),[4])

    def test_linear_light_premultiplied_average(self):
        pixel=Image.open(io.BytesIO(average_png([png((0,0,0,255)),png((255,255,255,255))]))).getpixel((0,0))
        self.assertEqual(pixel,(188,188,188,255))
        pixel=Image.open(io.BytesIO(average_png([png((255,0,0,255)),png((0,0,255,0))]))).getpixel((0,0))
        self.assertEqual(pixel,(255,0,0,128))
        a=png((54,81,190,122));self.assertEqual(Image.open(io.BytesIO(average_png([a,a]))).getpixel((0,0)),(54,81,190,122))

    def test_invalid_config_fails(self):
        for blur in ({'samples':0},{'samples':33},{'samples':True},{'shutter':1.1},{'extra':2}):
            s=starter();s['motion_blur']=blur
            with self.assertRaises(ContractError):validate(s,Path('.'))
        s=starter();s['motion_blur']={'samples':8,'shutter':.5};validate(s,Path('.'))
