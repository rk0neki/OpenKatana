from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from openkatana.image_morph import correspondence,morph_images
from openkatana.contracts import ContractError


class ImageMorphTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[1]/'work';parent.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_unreliable_automatic_match_fails_instead_of_dissolve(self):
        with self.assertRaisesRegex(ContractError,'features'):
            correspondence(np.zeros((64,64,3),np.uint8),np.zeros((64,64,3),np.uint8))

    def test_invalid_landmarks_fail(self):
        im=np.zeros((64,64,3),np.uint8)
        for points in ({'source':[[0,0]],'target':[[0,0]]},{'source':[[.1,.2]]*3,'target':[[.1,.2]]*3},
                       {'source':[[float('nan'),.2]]*3,'target':[[.1,.2]]*3}):
            with self.assertRaises(ContractError):correspondence(im,im,points)

    def test_real_morph_moves_geometry_and_preserves_endpoints(self):
        import cv2
        a=np.zeros((96,128,3),np.uint8);b=a.copy()
        cv2.circle(a,(32,48),12,(255,120,30),-1);cv2.circle(b,(88,48),12,(255,120,30),-1)
        Image.fromarray(a).save(self.root/'a.png');Image.fromarray(b).save(self.root/'b.png')
        pts={'source':[[20/127,36/95],[44/127,36/95],[32/127,60/95]],
             'target':[[76/127,36/95],[100/127,36/95],[88/127,60/95]]}
        r=morph_images(self.root/'a.png',self.root/'b.png',self.root/'out',128,96,12,3,pts)
        first=np.array(Image.open(self.root/'out/frames/00000.png'));last=np.array(Image.open(self.root/'out/frames/00002.png'))
        mid=np.array(Image.open(self.root/'out/frames/00001.png'))
        self.assertTrue(np.array_equal(first,a));self.assertTrue(np.array_equal(last,b))
        self.assertGreater(int(mid[48,60,0]),180)  # a pure dissolve would have no object here
        self.assertLess(int(mid[48,32,0]),50)
        self.assertTrue(Path(r['video']).is_file())

    def test_automatic_registration_finds_original_shifted_texture(self):
        import cv2
        rng=np.random.default_rng(8);a=np.zeros((256,256,3),np.uint8)
        for _ in range(100):
            xy=tuple(rng.integers(30,210,2).tolist());c=tuple(rng.integers(30,255,3).tolist())
            cv2.circle(a,xy,3,c,-1)
        b=cv2.warpAffine(a,np.float32([[1,0,10],[0,1,5]]),(256,256))
        pa,pb,_,method=correspondence(a,b)
        self.assertIn('ORB',method)
        np.testing.assert_allclose(np.median(pb[4:]-pa[4:],axis=0),[10,5],atol=1.5)


if __name__=='__main__':unittest.main()
