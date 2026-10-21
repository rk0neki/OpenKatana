"""Point-click cut-out workflow (SAM2 video model through ComfyUI): graph shape, click-point validation, the
no-download guard on the third-party loader, and the OpenKatana click-point node (run without ComfyUI)."""
import json
import unittest
from unittest import mock


class CutoutWorkflowTests(unittest.TestCase):
    def test_graph_links_points_and_omits_empty_negatives(self):
        from openkatana.workflows import build
        g = build('cutout', model='sam2.1_hiera_base_plus.safetensors', positive=[[.5, .4]])
        self.assertEqual(g['1']['class_type'], 'VHS_LoadVideo')
        self.assertEqual(g['2']['inputs']['segmentor'], 'video')
        self.assertEqual(json.loads(g['3']['inputs']['positive']), [[.5, .4]])
        self.assertNotIn('coordinates_negative', g['4']['inputs'])
        g = build('cutout', model='sam2.1_hiera_base_plus.safetensors', positive=[[.5, .4]], negative=[[.1, .9]])
        self.assertEqual(g['4']['inputs']['coordinates_negative'], ['3', 1])

    def test_points_are_validated(self):
        from openkatana.workflows import build
        for bad in ([], [[1.2, 0]], [[.5]], [[True, .5]], 'x'):
            with self.assertRaises(ValueError):
                build('cutout', model='m.safetensors', positive=bad)
        with self.assertRaises(ValueError):
            build('cutout', positive=[[.5, .5]])   # model is required
        with self.assertRaises(ValueError):
            build('cutout', model='m', positive=[[.5, .5]], prompt='x')   # unsupported parameter

    def test_loader_is_refused_when_its_file_is_missing(self):
        from openkatana import workflows
        g = workflows.build('cutout', model='sam2.1_hiera_large.safetensors', positive=[[.5, .5]])
        info = {n['class_type']: {'input': {'required': {k: ['*'] for k in n['inputs']}}} for n in g.values()}
        with mock.patch.object(workflows, 'capabilities', return_value=info), \
             mock.patch.object(workflows, 'installed_models', return_value={'sam2.1_hiera_base_plus-fp16.safetensors'}):
            check = workflows.preflight(g, 'http://127.0.0.1:8000')
        self.assertFalse(check['ready'])
        self.assertTrue(any('sam2.1_hiera_large-fp16.safetensors is not installed' in e and 'download' in e for e in check['errors']))
        g = workflows.build('cutout', model='sam2.1_hiera_base_plus.safetensors', positive=[[.5, .5]])
        with mock.patch.object(workflows, 'capabilities', return_value=info), \
             mock.patch.object(workflows, 'installed_models', return_value={'sam2.1_hiera_base_plus-fp16.safetensors'}):
            self.assertTrue(workflows.preflight(g, 'http://127.0.0.1:8000')['ready'])

    def test_sam2_file_naming(self):
        from openkatana.workflows import sam2_file
        self.assertEqual(sam2_file('sam2.1_hiera_base_plus.safetensors', 'fp16'), 'sam2.1_hiera_base_plus-fp16.safetensors')
        self.assertEqual(sam2_file('sam2.1_hiera_base_plus.safetensors', 'fp32'), 'sam2.1_hiera_base_plus.safetensors')
        self.assertEqual(sam2_file('sam2_hiera_tiny.safetensors', 'bf16'), 'sam2_hiera_tiny.safetensors')

    def test_click_point_node_maps_to_pixels(self):
        try:
            import torch
        except ImportError:
            self.skipTest('torch is only in ComfyUI environments')
        import comfy_nodes
        node = comfy_nodes.OpenKatanaPoints()
        pos, neg = node.execute(torch.zeros(2, 101, 201, 3), '[[0.5, 0.25]]', '[[0, 1]]')
        self.assertEqual(json.loads(pos), [{'x': 100, 'y': 25}])
        self.assertEqual(json.loads(neg), [{'x': 0, 'y': 100}])
        with self.assertRaises(ValueError):
            node.execute(torch.zeros(1, 8, 8, 3), '[[2, 0]]', '[]')


if __name__ == '__main__':
    unittest.main()
