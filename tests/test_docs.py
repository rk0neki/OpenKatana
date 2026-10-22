"""Doc lint (audit F-DOC-003): documentation that states counts or field tables must match the code."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


class DocLintTests(unittest.TestCase):
    def test_tool_counts_match(self):
        from openkatana.agent_api import TOOLS
        for rel in ('README.md', 'docs/ROADMAP.md', 'docs/EDITOR_TOOLS.md', 'docs/VALIDATION.md', 'docs/AGENT_INTERFACE.md', 'docs/TOOLS.md'):
            for n in re.findall(r'(\d+)(?:-tool| tools| shared MCP| named operations)', read(rel)):
                self.assertEqual(int(n), len(TOOLS), f'{rel} states {n} tools; code has {len(TOOLS)}')

    def test_tool_reference_is_generated_and_current(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('build_tools_doc', ROOT / 'scripts/build_tools_doc.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(read('docs/TOOLS.md').replace('\r\n', '\n'), module.render(),
                         'docs/TOOLS.md is stale; run python scripts/build_tools_doc.py')

    def test_every_tool_is_documented(self):
        from openkatana.agent_api import TOOLS
        docs = ' '.join(p.read_text(encoding='utf-8') for p in (ROOT / 'docs').glob('*.md'))
        self.assertEqual([t for t in TOOLS if t not in docs], [])

    def test_shot_field_table_lists_every_accepted_field(self):
        fields = re.search(r"fields\(shot, '([^']+)'", read('openkatana/contracts.py')).group(1).split()
        row = next(line for line in read('docs/TIMELINE.md').splitlines() if line.startswith('| Shots |'))
        self.assertEqual([f for f in fields if f'`{f}`' not in row], [])

    def test_python_phase_order_tables_match_renderer(self):
        from openkatana.expanded import ORDERS, PHASES
        js = read('openkatana/web/effects.js')
        parse = lambda name: json.loads(re.sub(r'([A-Za-z0-9_]+):', r'"\1":', re.search(r'const ' + name + r'=(\{[^}]*\})', js).group(1)).replace("'", '"'))
        self.assertEqual(parse('orders'), ORDERS)
        self.assertEqual(parse('phase'), {**PHASES})

    def test_json_examples_parse_and_full_timelines_validate(self):
        # Documented JSON examples must parse and full timelines must validate.
        from openkatana.contracts import validate
        checked = 0
        for path in [ROOT / 'README.md', *sorted((ROOT / 'docs').glob('*.md'))]:
            text = path.read_text(encoding='utf-8')
            for m in re.finditer(r'```json\n(.*?)```', text, re.S):
                line = text[:m.start()].count('\n') + 1
                block = m.group(1)
                try:
                    value = json.loads(block)
                except ValueError:
                    value = json.loads('{' + block + '}')   # documented fragments: "key": value pairs
                if isinstance(value, dict) and 'canvas' in value and 'shots' in value:
                    validate(value)
                checked += 1
                self.assertIsInstance(value, (dict, list), f'{path.name}:{line}')
        self.assertGreater(checked, 5)

    def test_timeline_fields_are_documented(self):
        fields = re.search(r"fields\(edit, '([^']+)', 'timeline'\)", read('openkatana/contracts.py')).group(1).split()
        doc = read('docs/TIMELINE.md')
        self.assertEqual([f for f in fields if f'`{f}`' not in doc and f'"{f}"' not in doc], [])


if __name__ == '__main__':
    unittest.main()
