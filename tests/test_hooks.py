"""F-NAT-011: project hooks — declaration rules, sandboxed rendering, receipts."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from openkatana.contracts import ContractError, validate


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


HOOK = """
OpenKatanaHooks.layer('dots', {draw(ctx, p, s) { ctx.fillStyle = p.color || '#ff0000';
  for (let i = 0; i < 20; i++) ctx.fillRect(Math.random() * s.W, Math.random() * s.H, 3, 3); }});
OpenKatanaHooks.layer('net', {draw(ctx, p, s) { fetch('http://example.com/x?' + s.f).catch(() => {});
  const im = new Image(); im.src = 'https://example.org/pixel.png'; ctx.fillStyle = '#00ff00'; ctx.fillRect(0, 0, 4, 4); }});
OpenKatanaHooks.text('caps', {draw(ctx, t, s) { ctx.fillStyle = '#ffffff'; ctx.font = 'bold 12px sans-serif'; ctx.fillText(t.text.toUpperCase(), 4, s.H - 4); }});
"""


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir(); Image.new('RGB', (64, 36), (40, 40, 40)).save(self.root / 'f' / '00000.png')
        (self.root / 'hook.js').write_text(HOOK, encoding='utf-8')

    def edit(self, **top):
        e = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 4}, 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}},
             'shots': [{'f0': 0, 'f1': 4, 'clip': 'A', 'speed': 0, 'fx': {'dots': {'color': '#ffff00'}, 'net': True}}],
             'text': [{'type': 'caps', 'text': 'hi', 'f0': 0, 'f1': 4}],
             'hooks': {'src': 'hook.js', 'layers': ['dots', 'net'], 'text_types': ['caps']}}
        e.update(top); return e

    def test_declaration_rules(self):
        canon = validate(self.edit(), self.root)
        self.assertEqual([l['type'] for l in canon['shots'][0]['layers']], ['hook', 'hook'])
        self.assertEqual(canon['text'][0]['name'], 'caps')
        for change, error in (({'hooks': {'src': 'hook.js', 'layers': ['dots']}}, 'unsupported fields: net'),
                              ({'hooks': {'src': 'missing.js', 'layers': ['dots', 'net'], 'text_types': ['caps']}}, 'file missing'),
                              ({'hooks': {'src': 'hook.js', 'layers': ['grain', 'dots', 'net'], 'text_types': ['caps']}}, 'built-in'),
                              ({'hooks': {'src': 'hook.txt', 'layers': ['dots', 'net'], 'text_types': ['caps']}}, '.js')):
            with self.assertRaisesRegex(ContractError, error):
                validate(self.edit(**change), self.root)
        e = self.edit(); del e['hooks']; e['custom_text_types'] = ['caps']
        with self.assertRaisesRegex(ContractError, 'needs a hooks script'):
            validate(e, self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_sandboxed_render_is_deterministic_and_recorded(self):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit()))
        r1 = render(self.root / 't.json', self.root / 'o1'); r2 = render(self.root / 't.json', self.root / 'o2')
        self.assertEqual(r1['frame_hashes'], r2['frame_hashes'])                       # seeded Math.random
        self.assertEqual(r1['hooks']['src'], 'hook.js'); self.assertEqual(len(r1['hooks']['sha256']), 64)
        self.assertTrue(any('example.com' in u for u in r1['hooks']['blocked_requests']), r1['hooks']['blocked_requests'])
        self.assertTrue(any('example.org' in u for u in r1['hooks']['blocked_requests']))
        px = Image.open(self.root / 'o1' / 'frames' / '00000.png').convert('RGB').getpixel((1, 1))
        self.assertEqual(px, (0, 255, 0))                                               # the hook still drew

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_hook_errors_are_named(self):
        from openkatana.render import render
        for i, (script, error) in enumerate((("OpenKatanaHooks.layer('dots', {draw(){ throw Error('boom'); }});"
                                             "OpenKatanaHooks.layer('net',{draw(){}});OpenKatanaHooks.text('caps',{draw(){}});", 'boom'),
                                            ("OpenKatanaHooks.layer('dots', {draw(){}});", 'did not register layer net'),
                                            ("this is not javascript", 'failed'))):
            (self.root / 'hook.js').write_text(script, encoding='utf-8')
            (self.root / 't.json').write_text(json.dumps(self.edit()))
            with self.assertRaisesRegex(RuntimeError, error):
                render(self.root / 't.json', self.root / f'e{i}')


if __name__ == '__main__':
    unittest.main()
