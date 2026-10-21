from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    data: Path
    public_url: str
    worker_image: str = 'openkatana-worker:0.1.0rc2'
    runtime: str = 'runsc'
    workspace_bytes: int = 2 * 1024**3
    upload_bytes: int = 256 * 1024**2
    max_users: int = 10
    max_pending: int = 8
    job_seconds: int = 1800
    worker_memory: str = '6g'
    worker_cpus: float = 4
    issuer: str = ''
    jwks_url: str = ''
    client_id: str = ''
    authorize_url: str = ''
    token_url: str = ''
    comfy_proxy: str = ''
    comfy_native: str = ''
    model_network: str = ''
    development: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'data', Path(self.data).resolve())
        object.__setattr__(self, 'public_url', self.public_url.rstrip('/'))
        u = urlsplit(self.public_url)
        if u.username or u.password or u.query or u.fragment or u.path or not u.netloc:
            raise ValueError('public_url must be an origin without a path or credentials')
        if u.scheme != 'https' and not (self.development and u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost')):
            raise ValueError('Hosting requires HTTPS; development HTTP is loopback only')
        if not self.development and self.runtime != 'runsc':
            raise ValueError('Public authored-code execution requires the runsc sandbox runtime')
        if not 1 <= self.max_users <= 100 or not 1 <= self.max_pending <= 100:
            raise ValueError('Invalid capacity limits')
        if not 1024 <= self.upload_bytes <= self.workspace_bytes or self.job_seconds < 1:
            raise ValueError('Invalid upload, workspace or time limits')
        if self.issuer:
            for value in (self.issuer, self.jwks_url, self.authorize_url, self.token_url):
                p = urlsplit(value)
                if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment:
                    raise ValueError('Configure explicit HTTPS identity-provider URLs')
            if not self.client_id:
                raise ValueError('Configure the identity provider’s public PKCE client ID')
        if bool(self.comfy_proxy) != bool(self.comfy_native) or bool(self.comfy_proxy) != bool(self.model_network):
            raise ValueError('Configure both Comfy endpoints and a private model network together')
        if self.comfy_proxy and self.max_users > 1:
            if not all('{user}' in v for v in (self.comfy_proxy, self.comfy_native, self.model_network)):
                raise ValueError('Multi-user model services require separate {user} endpoints and networks')

    def models_for(self, user):
        return tuple(v.replace('{user}', user) for v in (self.comfy_proxy, self.comfy_native, self.model_network))

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding='utf-8')))

    @property
    def audience(self):
        return self.public_url + '/mcp'
