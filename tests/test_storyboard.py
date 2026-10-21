"""Storyboard mode: slots and briefs from a cut plan, slate pictures, filling, and the GAPS verdict."""
import json
import tempfile
import unittest
from pathlib import Path

ANALYSIS = {'duration': 8.0, 'period': .5, 'phase': 0, 'beats': [i * .5 for i in range(16)], 'downbeats': [0, 2, 4, 6], 'bpm': 120,
            'sections': [{'t0': 0, 't1': 4, 'label': 'mid'}, {'t0': 4, 't1': 8, 'label': 'loud', 'step_db': 6}]}


class StoryboardTests(unittest.TestCase):
    def plan(self, root):
        from openkatana import storyboard
        from openkatana.music_plan import plan_cuts
        cut_plan = plan_cuts(ANALYSIS, 30)
        src = root / 'music.wav'; src.write_bytes(b'RIFF0000')
        return storyboard, storyboard.plan(root, src, ANALYSIS, cut_plan, 30, 180, 320, 'a skater', None, None)

    def test_slots_have_briefs_roles_and_slates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sb, (board, edit) = self.plan(root)
            roles = [s['role'] for s in board['slots']]
            self.assertEqual(roles[0], 'hook'); self.assertEqual(roles[-1], 'outro'); self.assertIn('drop_first', roles); self.assertIn('burst', roles)
            self.assertTrue(all(s['subject'] == 'a skater' and s['shot'] and s['camera'] and s['needs_s'] > 0 for s in board['slots']))
            self.assertEqual(sum(s['f1'] - s['f0'] for s in board['slots']), edit['canvas']['frames'])
            for s in board['slots']:
                self.assertTrue((root / edit['clips'][sb.PREFIX + s['id']]['frames_dir'] / '00000.png').is_file())
            v = sb.verdict(board, edit)
            n = len(board['slots'])
            self.assertTrue(v['verdict'].startswith(f'GAPS storyboard: {n} of {n} slots still to fill'))
            from openkatana.warnings import timeline_warnings
            self.assertEqual([w['code'] for w in timeline_warnings(edit)], ['storyboard_gaps'])

    def test_fill_counts_down_and_refuses_short_footage(self):
        from openkatana.contracts import ContractError
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sb, (board, edit) = self.plan(root)
            clip = {'frames_dir': 'plates/a', 'n': 600, 'fps': 30, 'w': 180, 'h': 320, 'pattern': '%05d.png'}
            assets = {'a': {'id': 'a', 'kind': 'video', 'clip': clip}, 'b': {'id': 'b', 'kind': 'video', 'clip': {**clip, 'n': 2}},
                      'i': {'id': 'i', 'kind': 'image', 'clip': {**clip, 'n': 1}}}
            first = board['slots'][0]
            with self.assertRaises(ContractError):
                sb.fill(root, board, edit, assets, [{'slot': first['id'], 'asset_id': 'b'}], 30)
            sb.fill(root, board, edit, assets, [{'slot': first['id'], 'asset_id': 'a', 'srcf': 10}], 30)
            shot = edit['shots'][0]
            self.assertEqual((shot['clip'], shot['srcf'], shot['speed']), ('a', 10, 1))
            n = len(board['slots'])
            self.assertIn(f'{n - 1} of {n}', sb.verdict(board, edit)['verdict'])
            sb.fill(root, board, edit, assets, [{'slot': s['id'], 'asset_id': 'i'} for s in board['slots'][1:]], 30)
            self.assertEqual(sb.verdict(board, edit)['verdict'], 'FILLED')
            self.assertFalse([k for k in edit['clips'] if k.startswith(sb.PREFIX)])
            with self.assertRaises(ContractError):   # already filled
                sb.fill(root, board, edit, assets, [{'slot': first['id'], 'asset_id': 'a'}], 30)


if __name__ == '__main__':
    unittest.main()
