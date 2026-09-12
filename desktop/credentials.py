from __future__ import annotations


class CredentialError(RuntimeError):
    pass


class CredentialStore:
    SERVICE = "AntibodyAI"

    def __init__(self, keyring_module=None):
        self._keyring = keyring_module
        self._session = {}

    def _module(self):
        if self._keyring is None:
            try:
                import keyring
                self._keyring = keyring
            except Exception as exc:
                raise CredentialError("keyring 不可用，无法安全保存凭据") from exc
        return self._keyring

    def set_session(self, provider: str, secret: str) -> None:
        if secret:
            self._session[provider] = secret

    def get(self, provider: str) -> str:
        if provider in self._session:
            return self._session[provider]
        try:
            return self._module().get_password(self.SERVICE, provider) or ""
        except Exception as exc:
            raise CredentialError("无法读取安全凭据") from exc

    def save_secure(self, provider: str, secret: str) -> None:
        try:
            self._module().set_password(self.SERVICE, provider, secret)
        except Exception as exc:
            raise CredentialError("无法安全保存凭据；未使用明文回退") from exc

    def delete(self, provider: str) -> None:
        self._session.pop(provider, None)
        try:
            self._module().delete_password(self.SERVICE, provider)
        except Exception as exc:
            # Missing credentials are harmless; unavailable keyring must remain visible.
            if exc.__class__.__name__ not in {"PasswordDeleteError", "CredentialNotFoundError"}:
                raise CredentialError("无法清除安全凭据") from exc
