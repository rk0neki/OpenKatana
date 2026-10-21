"""F-STU-005: photosensitive flash counting used by the render receipt QA."""
import unittest

import numpy as np

from openkatana.qa import flash_rate


class FlashRateTests(unittest.TestCase):
    def test_strobe_and_calm(self):
        fps = 60
        strobe = np.array([1.0 if (i // 5) % 2 == 0 else .02 for i in range(120)])   # toggles every 5 frames: 6 Hz
        rate, at, _ = flash_rate(strobe, fps)
        self.assertEqual(rate, 6.0)
        self.assertEqual(flash_rate(np.full(120, .4), fps)[0], 0.0)
        two = np.full(120, .05); two[10:13] = 1; two[70:73] = 1                      # two isolated flashes, 1 s apart
        self.assertEqual(flash_rate(two, fps)[0], 1.0)
        bright = np.array([1.0 if (i // 5) % 2 == 0 else .85 for i in range(120)])  # both states above 0.8: not a flash
        self.assertEqual(flash_rate(bright, fps)[0], 0.0)
        noisy = np.clip(.3 + np.random.default_rng(2).normal(0, .03, 600), 0, 1)
        self.assertEqual(flash_rate(noisy, fps)[0], 0.0)


if __name__ == '__main__':
    unittest.main()
