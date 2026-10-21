"""Project setup must be repeatable and preserve existing user work."""
from pathlib import Path
from contextlib import redirect_stdout
import importlib.metadata
import io
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openkatana.onboarding import setup_project
from openkatana.projects import state


class OnboardingTests(unittest.TestCase):
    def test_cli_doctor_does_not_require_mcp(self):
        from openkatana.cli import main
        def version(name):
            if name=='mcp':raise importlib.metadata.PackageNotFoundError(name)
            return 'test-version'
        out=io.StringIO()
        with patch('sys.argv',['openkatana','doctor']), patch('openkatana.cli.importlib.metadata.version',side_effect=version), patch('openkatana.cli.shutil.which',side_effect=lambda name:name), patch('openkatana.render.chrome_path',return_value='chrome'), redirect_stdout(out):
            main()
        result=json.loads(out.getvalue())
        self.assertEqual(result['missing'],[])
        self.assertEqual(result['optional_missing'],['mcp'])
        self.assertTrue(result['ready_to_render'])

    def test_repeat_setup_preserves_project_and_custom_skill(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'my-film'
            with patch('openkatana.onboarding.AgentAPI.get_capabilities',return_value={
                'ffmpeg':'ffmpeg','ffprobe':'ffprobe','chrome':'chrome','tools':['get_project']}):
                first=setup_project(root,'My film');before=state(root)
                skill=Path(first['skill']);self.assertTrue(skill.is_file())
                skill.write_text('My project-specific instructions',encoding='utf-8')
                second=setup_project(root,'Do not rename')
                self.assertEqual(state(root),before)
                self.assertEqual(skill.read_text(),'My project-specific instructions')
                self.assertEqual(second['skill_status'],'existing skill preserved')
                self.assertTrue(second['core_runtime_ready'])
                self.assertFalse(second['agent_connected'])
                self.assertEqual(Path(second['workspace']),root.parent.resolve())

    def test_existing_unrelated_folder_is_not_overwritten(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'existing';root.mkdir()
            media=root/'keep.txt';media.write_text('original')
            with self.assertRaisesRegex(ValueError,'not an OpenKatana project'):
                setup_project(root)
            self.assertEqual(media.read_text(),'original')
            self.assertFalse((root/'project.json').exists())

    def test_missing_runtime_is_reported_without_claiming_connection(self):
        with TemporaryDirectory() as folder:
            with patch('openkatana.onboarding.AgentAPI.get_capabilities',return_value={
                'ffmpeg':None,'ffprobe':None,'chrome':None,'tools':[]}):
                result=setup_project(Path(folder)/'film')
            self.assertEqual(result['missing_runtime'],['ffmpeg','ffprobe','chrome'])
            self.assertFalse(result['core_runtime_ready'])
            self.assertFalse(result['agent_connected'])
