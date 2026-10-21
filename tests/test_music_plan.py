"""F-STU-004: beat-aligned cut planning from an analysis (pure function, no audio decoding)."""
import unittest

from openkatana.contracts import ContractError
from openkatana.music_plan import draft_timeline, plan_cuts


def analysis(bpm=120, dur=16.0, drop_at=8.0):
    P = 60 / bpm; beats = [round(k * P, 4) for k in range(int(dur / P))]
    return {'duration': dur, 'period': P, 'phase': 0.0, 'beats': beats, 'downbeats': beats[::4],
            'sections': [{'t0': 0.0, 't1': drop_at, 'label': 'mid', 'step_db': None}, {'t0': drop_at, 't1': dur, 'label': 'loud', 'step_db': 6.0}]}


class MusicPlanTests(unittest.TestCase):
    def test_auto_pacing_drop_and_burst(self):
        a = analysis(); p = plan_cuts(a, 30)
        P = .5; grid = {round(k * P / 2, 4) for k in range(64)}
        self.assertTrue(all(round(c['t'], 4) in grid for c in p['cuts']))           # every cut on a beat or half-beat
        mid = [c['t'] for c in p['cuts'] if c['t'] < 8]
        self.assertEqual(mid, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])                   # mid at 120 BPM: 2 beats = 1 s
        drop = next(c for c in p['cuts'] if c['kind'] == 'drop')
        self.assertEqual((drop['t'], drop['frame']), (8.0, 240))
        burst = [c['t'] for c in p['cuts'] if c['kind'] == 'burst']
        self.assertEqual(burst, [8.25, 8.5, 8.75, 9.0, 9.25, 9.5, 9.75, 10.0])        # first bar after the drop
        loud = [c['t'] for c in p['cuts'] if c['kind'] == 'beat' and c['t'] > 10]
        self.assertEqual(loud[:3], [10.5, 11.0, 11.5])                               # loud: 1 beat = 0.5 s
        self.assertEqual(p['shots'][0]['f0'], 0); self.assertEqual(p['shots'][-1]['f1'], 480)
        self.assertTrue(any('specials' in s for s in p['suggestions']))

    def test_fixed_pace_min_shot_and_errors(self):
        p = plan_cuts(analysis(), 30, pace='bar', burst=False)
        self.assertEqual([c['t'] for c in p['cuts']][:4], [2.0, 4.0, 6.0, 8.0])
        p = plan_cuts(analysis(bpm=240), 30, pace='half', min_shot=.2)
        self.assertGreaterEqual(min(s['f1'] - s['f0'] for s in p['shots']), 6)
        with self.assertRaisesRegex(ContractError, 'pace'):
            plan_cuts(analysis(), 30, pace='frantic')

    def test_draft_timeline_assigns_and_advances_clips(self):
        p = plan_cuts(analysis(), 30, pace='bar', burst=False)
        assets = [('v', {'kind': 'video', 'clip': {'frames_dir': 'f', 'n': 400, 'fps': 30, 'w': 64, 'h': 36}}),
                  ('i', {'kind': 'image', 'clip': {'frames_dir': 'g', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}})]
        e = draft_timeline(p, assets, 30, 64, 36)
        self.assertEqual([s['clip'] for s in e['shots']][:4], ['v', 'i', 'v', 'i'])
        self.assertEqual([s.get('srcf') for s in e['shots'] if s['clip'] == 'v'][:2], [0, 60])
        self.assertEqual(e['canvas']['frames'], 480)


if __name__ == '__main__':
    unittest.main()
