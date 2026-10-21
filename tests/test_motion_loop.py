"""F-MOT-001: bounded camera-only proposals from a motion check (pure functions; the render loop is covered by
audit finding F-MOT-001) and the optional motion review gate."""
import tempfile
import unittest
from pathlib import Path

from openkatana import gates
from openkatana.motion_loop import propose, score, structure


def edit():
    return {'canvas': {'w': 1000, 'h': 600, 'fps': 30, 'frames': 90}, 'clips': {'A': {'frames_dir': 'f', 'n': 90, 'fps': 30, 'w': 1000, 'h': 600}},
            'cam': {'handheld': {'amp': 3}}, 'post': {'flash': {'at': 1}},
            'shots': [{'f0': 0, 'f1': 30, 'clip': 'A', 'cam': {'push': {'v': .05}}}, {'f0': 30, 'f1': 60, 'clip': 'A', 'in': 'white'},
                      {'f0': 60, 'f1': 90, 'clip': 'A', 'cam': {'shake': {'at': 0, 'amp': [10, 8], 'd': .2}}}]}


REF = {'events': {'shakes': [{'t': .5, 'd': .4, 'amp_px': 400.0}, {'t': 2.2, 'd': .3, 'amp_px': 20.0}],
                  'pans': [{'t': 1.2, 'edl': {'cam': {'pan': {'dx': .9, 'dy': -.01}}}}],
                  'hits': [{'t': .1}, {'t': 1.5}, {'t': 2.5}], 'cuts': [], 'flashes': []}}


def chk(**rows):
    out = []
    for key, label in (('cuts_ps', 'cuts / s'), ('flashes_ps', 'flashes / s'), ('shake_ps', 'shake frames / s'), ('jitter_px', 'jitter px'),
                       ('move_px', 'camera movement px'), ('motion', 'motion energy')):
        ours, ref = rows.get(key, (1, 1))
        verdict = 'PASS' if ours >= .6 * ref else 'FAIL (too little)'
        if key in ('shake_ps', 'jitter_px') and ours > max(1.5 * ref, ref + 1):
            verdict = 'FAIL (too much)'
        out.append({'measure': label, 'reference': ref, 'ours': ours, 'ratio': round(ours / ref, 2), 'verdict': verdict})
    return {'rows': out, 'fails': [r['measure'] for r in out if r['verdict'].startswith('FAIL')], 'pass': False}


class MotionLoopTests(unittest.TestCase):
    def test_first_revision_places_reference_events_on_unlocked_shots(self):
        e = edit(); added = set()
        new, changes, editor = propose(e, REF, chk(shake_ps=(1, 4), move_px=(1, 4), cuts_ps=(1, 3)), added, {1}, 0.0)
        self.assertEqual(structure(new), structure(e))                      # only shot cameras changed
        self.assertEqual(new['shots'][1], e['shots'][1])                     # locked shot untouched (its pan event is skipped)
        sh = new['shots'][0]['cam']['shake']
        self.assertEqual((sh['hits'], sh['d'], sh['amp'], sh['every']), ([.5], .4, [20.0, 16.0], 1))   # new bursts: .6 x amp, capped at 2% of the width
        sh2 = new['shots'][2]['cam']['shake']
        self.assertEqual(sh2['hits'], [0, .2]); self.assertNotIn('at', sh2); self.assertEqual(sh2['amp'], [12.0, 9.6])
        self.assertEqual(new['shots'][0]['cam']['punch']['hits'], [.1]); self.assertEqual(new['shots'][2]['cam']['punch']['hits'], [.5])
        self.assertNotIn('pan', new['shots'][0]['cam'])
        self.assertEqual({c['shot'] for c in changes}, {0, 2}); self.assertEqual(added, {'shakes', 'pans', 'hits'})
        self.assertTrue(any('cuts / s' in x for x in editor))

    def test_later_revisions_scale_within_bounds(self):
        e = edit(); e['shots'][0]['cam']['pan'] = {'dx': .2, 'dy': 0}
        new, _, _ = propose(e, REF, chk(jitter_px=(.1, 1), move_px=(.5, 1)), {'shakes', 'pans', 'hits'}, set(), 0.0)
        self.assertEqual(new['shots'][2]['cam']['shake']['amp'], [20.0, 16.0])   # x2 max per step
        self.assertEqual(new['shots'][0]['cam']['pan'], {'dx': .25, 'dy': 0})   # pan clamped to 0.25
        self.assertEqual(new['shots'][0]['cam']['push']['v'], .1)
        new, _, editor = propose(e, REF, chk(shake_ps=(9, 2)), set(), set(), 0.0)
        self.assertEqual(new['shots'][2]['cam']['shake']['amp'], [5.0, 4.0])     # too much: x0.5 min
        self.assertTrue(any('handheld' in x for x in editor))
        self.assertEqual(new['cam'], e['cam'])                                    # timeline camera never changed

    def test_over_busy_scales_camera_down(self):
        e = edit(); e['shots'][0]['cam'] = {'push': {'v': .1}, 'zoom': {'z0': 1, 'z1': 1.2}, 'punch': {'amt': .1, 'hits': [0]}}
        c = chk(move_px=(3, 1), motion=(2.5, 1))
        for r in c['rows']:
            if r['measure'] in ('camera movement px', 'motion energy'):
                r['verdict'] = 'FAIL (too much)'
        new, changes, editor = propose(e, REF, c, set(), {2}, 0.0, ceiling=2)
        cam = new['shots'][0]['cam']   # k = max(.5, .9 * 2 * 1 / 3) = .6
        self.assertEqual((cam['push']['v'], cam['zoom']['z1'], cam['punch']['amt']), (.06, 1.12, .06))
        self.assertEqual(new['shots'][2], e['shots'][2]); self.assertEqual(new['cam'], e['cam'])
        self.assertTrue(any('timeline-level' in x for x in editor))

    def test_not_responding(self):
        from openkatana.motion_loop import not_responding
        row = lambda m, ours, ref, verdict, ratio: {'measure': m, 'ours': ours, 'reference': ref, 'verdict': verdict, 'ratio': ratio}
        before = [row('jitter px', .9, .36, 'FAIL (too much)', None), row('motion energy', 4.8, 2.1, 'FAIL (too much)', 2.29),
                  row('cuts / s', .7, .8, 'FAIL (too little)', .88)]
        now = [row('jitter px', .71, .36, 'PASS', None), row('motion energy', 4.96, 2.1, 'FAIL (too much)', 2.36), row('cuts / s', .6, .8, 'FAIL (too little)', .75)]
        out = not_responding(before, now, 1)
        self.assertEqual(len(out), 1); self.assertIn('motion energy', out[0])   # jitter got closer (no ratio); cuts are structural

    def test_nothing_adjustable(self):
        new, changes, editor = propose(edit(), REF, chk(cuts_ps=(1, 4), flashes_ps=(0, 1)), set(), set(), 0.0)
        self.assertEqual(changes, []); self.assertEqual(len(editor), 2)

    def test_score_orders_attempts(self):
        self.assertLess(score(chk(move_px=(.5, 1))), score(chk(move_px=(.1, 1))))
        self.assertLess(score(chk(move_px=(.1, 1))), score(chk(move_px=(.5, 1), shake_ps=(1, 4))))

    def test_motion_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = {'timeline': {'clips': {}}, 'revision': 'r1', 'assets': []}
            gates.set_strict(root, True, require_motion=True); gates.record_preview(root, 'r1', [0])
            self.assertEqual(gates.missing(root, state), ['measure the current revision against the reference with revise_motion'])
            gates.record_motion(root, 'r1', {'status': 'needs_editor'})
            self.assertEqual(gates.missing(root, state), [])
            gates.set_strict(root, True)                                       # require_motion stays as set
            self.assertTrue(gates.load(root)['require_motion'])


if __name__ == '__main__':
    unittest.main()
