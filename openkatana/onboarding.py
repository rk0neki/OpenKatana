"""Local, agent-neutral project setup. No accounts or model services."""
from pathlib import Path
import re
import sys

from . import projects
from .agent_api import AgentAPI
from .render import write_json


def skill_source():
    source=Path(__file__).resolve().parent.parent
    for path in (source/'skills/openkatana-video/SKILL.md',
                 Path(sys.prefix)/'share/openkatana/skills/openkatana-video/SKILL.md',
                 source/'share/openkatana/skills/openkatana-video/SKILL.md'):
        if path.is_file():return path
    raise FileNotFoundError('The video skill is missing. Reinstall OpenKatana from the official repository.')


def setup_project(directory, name='My first film'):
    root=Path(directory).expanduser().resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',root.name):
        raise ValueError('Choose a project folder name with letters, digits, hyphens or underscores.')
    source=skill_source()
    resources=source.parents[2]
    skill=source.read_text(encoding='utf-8')
    playbook=(resources/'docs/EFFECTS-PLAYBOOK.md').read_text(encoding='utf-8')
    if (root/'project.json').is_file():
        projects.state(root)
    elif root.exists():
        raise ValueError('This folder is not an OpenKatana project. Choose a new folder; existing files are preserved.')
    else:
        root.parent.mkdir(parents=True,exist_ok=True)
        projects.create(root,name)
    target=root/'.agents/skills/openkatana-video/SKILL.md'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        skill_status='current' if target.read_text(encoding='utf-8')==skill else 'existing skill preserved'
    else:
        target.write_text(skill,encoding='utf-8');skill_status='installed'
    reference=target.parent/'references/effects-playbook.md'
    reference.parent.mkdir(parents=True,exist_ok=True)
    if reference.exists():
        playbook_status='current' if reference.read_text(encoding='utf-8')==playbook else 'existing playbook preserved'
    else:
        reference.write_text(playbook,encoding='utf-8');playbook_status='installed'
    arguments=root/'.openkatana/agent/project.json'
    arguments.parent.mkdir(parents=True,exist_ok=True)
    if not arguments.exists():write_json(arguments,{'project_id':root.name})
    capabilities=AgentAPI(root.parent).get_capabilities()
    missing=[name for name in ('ffmpeg','ffprobe','chrome') if not capabilities[name]]
    return {'project':str(root),'workspace':str(root.parent),'project_id':root.name,
            'skill':str(target),'skill_status':skill_status,'project_arguments':str(arguments),
            'resources':str(resources),'effects_playbook':str(reference),'playbook_status':playbook_status,
            'tool_count':len(capabilities['tools']),'missing_runtime':missing,
            'core_runtime_ready':not missing,'agent_connected':False,
            'next_commands':[
                [sys.executable,'-m','openkatana','doctor'],
                [sys.executable,'-m','openkatana','call','get_project','--workspace',str(root.parent),'--arguments',str(arguments)],
                [sys.executable,'-m','openkatana','studio',str(root)]],
            'next_step':'Load the installed skill in your local agent, then use the CLI. No login is required.'}
