"""Bootstrap OpenKatana from a checkout, using only Python's standard library."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser=argparse.ArgumentParser(description='Install the local CLI and project skill for any capable agent.')
    parser.add_argument('--project',type=Path,default=Path('projects/my-first-film'))
    parser.add_argument('--venv',type=Path,default=Path('.venv'))
    parser.add_argument('--skip-install',action='store_true',help='Use the existing environment without installing dependencies.')
    parser.add_argument('--name',default='My first film')
    args=parser.parse_args()
    if sys.version_info<(3,11):parser.error('Python 3.11 or newer is required.')
    source=Path(__file__).resolve().parents[1]
    environment=(source/args.venv).resolve()
    python=environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not python.is_file():
        if args.skip_install:parser.error('The selected Python environment does not exist.')
        if environment.exists():parser.error('The environment folder exists but has no Python executable; choose another --venv.')
        venv.EnvBuilder(with_pip=True).create(environment)
    if not args.skip_install:
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-e',str(source)+'[text,vision]'],check=True,cwd=source)
    project=(source/args.project).resolve()
    subprocess.run([str(python),'-m','openkatana','setup','--project',str(project),'--name',args.name],check=True,cwd=source)


if __name__=='__main__':main()
