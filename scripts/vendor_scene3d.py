"""Reproduce the explicitly pinned MIT browser dependencies; never run during rendering."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'openkatana' / 'web' / 'vendor3d'


def package(name, version):
    url = f'https://registry.npmjs.org/{name}/{version}'
    meta = json.load(urllib.request.urlopen(url, timeout=60))
    raw = urllib.request.urlopen(meta['dist']['tarball'], timeout=60).read()
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode()
    if integrity != meta['dist']['integrity']:
        raise RuntimeError(f'{name}: registry integrity mismatch')
    archive = tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz')
    files = {m.name.removeprefix('package/'): archive.extractfile(m).read()
             for m in archive if m.isfile()}
    return files, {'version': version, 'source': meta['dist']['tarball'], 'integrity': integrity,
                   'license': meta['license'], 'files': {}}


def main():
    manifests = {}
    for name, version, entrypoints in [
        ('three', '0.180.0', ['build/three.module.js', 'examples/jsm/loaders/GLTFLoader.js',
         'examples/jsm/environments/RoomEnvironment.js', 'examples/jsm/loaders/RGBELoader.js',
         'examples/jsm/postprocessing/EffectComposer.js', 'examples/jsm/postprocessing/RenderPass.js',
         'examples/jsm/postprocessing/UnrealBloomPass.js', 'examples/jsm/postprocessing/BokehPass.js',
         'examples/jsm/postprocessing/OutputPass.js']),
        ('cannon-es', '0.20.0', ['dist/cannon-es.js']),
    ]:
        files, manifest = package(name, version)
        pending = ['LICENSE', 'package.json', *entrypoints]
        while pending:
            rel = pending.pop()
            if rel in manifest['files']:
                continue
            data = files[rel]
            out = ROOT / name / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            manifest['files'][rel] = hashlib.sha256(data).hexdigest()
            if rel.endswith('.js'):
                import posixpath
                code = re.sub(r'/\*.*?\*/|^\s*//[^\n]*', '', data.decode(), flags=re.S | re.M)
                for dep in re.findall(r"^\s*(?:import|export)\s+(?:[\w*{},\s]+?\s+from\s*)?['\"]([^'\"]+)['\"]", code, re.M):
                    if dep.startswith('.'):
                        pending.append(posixpath.normpath(posixpath.join(posixpath.dirname(rel), dep)))
                    elif dep.startswith('three/addons/'):
                        pending.append(dep.replace('three/addons/', 'examples/jsm/'))
                    elif dep != 'three':
                        raise RuntimeError(f'Unresolved dependency: {rel}: {dep}')
        manifests[name] = manifest
    (ROOT / 'manifest.json').write_text(json.dumps(manifests, indent=2), encoding='utf-8')
    print(json.dumps({k: {'version': v['version'], 'files': len(v['files'])} for k, v in manifests.items()}))


if __name__ == '__main__':
    main()
