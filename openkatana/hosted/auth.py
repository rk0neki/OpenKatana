"""Local invite credentials or an external OAuth issuer; never an OAuth imitation."""
import asyncio
from contextvars import ContextVar
import hashlib
import time

current_user = ContextVar('openkatana_hosted_user', default=None)


class Identity:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.jwks = None
        if settings.issuer:
            import jwt
            self.jwks = jwt.PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=300, timeout=10)

    async def bearer(self, token):
        local = self.store.authenticate(token, {'api'})
        if local:
            return local
        if not self.jwks or not token or len(token) > 8192:
            return None
        try:
            return await asyncio.to_thread(self.jwt_user, token)
        except Exception:
            return None

    def jwt_user(self, token):
        import jwt
        key = self.jwks.get_signing_key_from_jwt(token)
        data = jwt.decode(token, key.key, algorithms=['RS256'], audience=self.settings.audience,
                          issuer=self.settings.issuer, options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
        if 'openkatana' not in str(data.get('scope', '')).split() or not isinstance(data['sub'], str):
            raise ValueError('Missing editing scope or subject')
        user = hashlib.sha256((self.settings.issuer + '\n' + data['sub']).encode()).hexdigest()[:32]
        return self.store.ensure_user(user, data.get('name', 'Editor'))

    def challenge(self):
        text = 'Bearer realm="OpenKatana"'
        if self.settings.issuer:
            text += ', resource_metadata="' + self.settings.public_url + '/.well-known/oauth-protected-resource/mcp"'
        return text
