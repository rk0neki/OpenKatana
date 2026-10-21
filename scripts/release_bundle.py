"""Create a history-free, allowlisted source bundle and file-hash manifest. Never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TOP={'LICENSE','NOTICE','README.md','THIRD_PARTY_NOTICES.md','AGENTS.md','MANIFEST.in',
     'pyproject.toml','requirements-lock.txt','mcp.example.json','.gitignore','.gitattributes','.dockerignore','CONTRIBUTING.md'}
DIRS={'openkatana','comfy_nodes','workflows','docs','scripts','tests','examples','.github','skills','licenses','deploy'}
EXCLUDED={'docs/SESSION_HANDOFF.md','docs/NEXT_SESSION_CONTEXT.md'}
EXTENSIONS={'.py','.js','.html','.css','.jpg','.json','.md','.txt','.ttf','.otf','.onnx','.toml','.yml','.yaml','.png','.svg','.service','.worker'}


def entries():
    result=[]
    for name in sorted(TOP|DIRS):
        root=ROOT/name
        if not root.exists():continue
        paths=root.rglob('*') if root.is_dir() else [root]
        for p in sorted(paths):
            rel=p.relative_to(ROOT).as_posix()
            if p.is_symlink():raise ValueError('Release contains a symlink: '+rel)
            if not p.is_file() or '__pycache__' in p.parts or rel in EXCLUDED:continue
            if name in DIRS and p.suffix.lower() not in EXTENSIONS and p.name not in {'LICENSE','NOTICE','COPYING','AUTHORS','Caddyfile'}:raise ValueError('Unreviewed release file type: '+rel)
            if p.name.startswith('.env') or p.name=='.mcp.json':raise ValueError('Private configuration in release: '+rel)
            data=p.read_bytes()
            if p.suffix in {'.py','.js','.md','.json','.toml','.yml','.yaml'}:
                text=data.decode('utf-8')
                if re.search(r'(?:sk-ant-api\d+-|ghp_)[A-Za-z0-9_-]{20,}',text):raise ValueError('Credential-like value in '+rel)
                if re.search(r'[A-Za-z]:[\\/]Users[\\/][^/\\\s"\']+',text):raise ValueError('Personal absolute path in '+rel)
            result.append((rel,data))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    out=args.out.resolve()
    if out==ROOT or not out.is_relative_to(ROOT/'work'):raise ValueError('Release staging must be a new directory under this checkout/work')
    files=entries();version=re.search(r'__version__ = "([^"]+)"',(ROOT/'openkatana/__init__.py').read_text()).group(1)
    out.mkdir(parents=True,exist_ok=False);source=out/f'openkatana-{version}';source.mkdir()
    manifest={'schema':1,'version':version,'history_included':False,'private_work_included':False,
              'scope':'Current source and licensed assets. Private work, local configuration and Git metadata are excluded.',
              'files':{rel:hashlib.sha256(data).hexdigest() for rel,data in files}}
    for rel,data in files:
        dest=source/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    (source/'SOURCE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive=out/f'openkatana-{version}-source.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(source.rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(out).as_posix(),date_time=(2026,10,20,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                z.writestr(info,path.read_bytes())
    result={'source':str(source),'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files),'bytes':archive.stat().st_size}
    (out/'bundle.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
