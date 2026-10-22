"""Fake collaborators and a fake Firebase SDK for the OC-011 startup tests.

The fake SDK mirrors the subset of ``firebase_admin`` the connector touches
(``credentials``, ``firestore``, ``auth``, ``initialize_app``, ``delete_app`` and
``_apps``) so enabled-mode paths can be exercised without the real package being
installed. No Firebase import, credential or network call happens anywhere.
"""

from types import SimpleNamespace


class FakeMemgraph:
    """Records lifecycle calls; can fail on connect or on close on demand."""

    def __init__(self, fail: bool = False, close_fail: bool = False):
        self.connect_calls = 0
        self.close_calls = 0
        self.is_ready = False
        self._fail = fail
        self._close_fail = close_fail

    async def connect(self):
        self.connect_calls += 1
        if self._fail:
            raise RuntimeError("graph boom with provider detail")
        self.is_ready = True

    def close(self):
        self.close_calls += 1
        self.is_ready = False
        if self._close_fail:
            raise RuntimeError("graph close boom")


class FakeFirestore:
    """Records lifecycle calls; readiness is configurable."""

    def __init__(self, ready: bool = True):
        self.connect_calls = 0
        self.verify_calls = 0
        self.close_calls = 0
        self.is_ready = False
        self._ready = ready

    def connect(self, enabled=None):
        self.connect_calls += 1
        self.is_ready = True

    def verify_connectivity(self):
        self.verify_calls += 1
        return self._ready

    def close(self):
        self.close_calls += 1
        self.is_ready = False


def build_fake_sdk(
    *,
    existing_apps=None,
    app_name: str = "[DEFAULT]",
    client_error: Exception = None,
    list_users_error: Exception = None,
):
    """Build a ``firebase_admin``-shaped namespace for connector tests."""
    apps = existing_apps if existing_apps is not None else {}
    created = []
    deleted = []

    class FakeApp:
        def __init__(self, name):
            self.name = name

    class FakeCredentials:
        @staticmethod
        def Certificate(path):
            return SimpleNamespace(path=path)

    class FakeFirestoreModule:
        @staticmethod
        def client():
            if client_error is not None:
                raise client_error
            return SimpleNamespace()

    class FakeAuth:
        @staticmethod
        def list_users(max_results=1):
            if list_users_error is not None:
                raise list_users_error
            return []

    def initialize_app(cred):
        app = FakeApp(app_name)
        created.append(app)
        apps[app_name] = app
        return app

    def delete_app(app):
        deleted.append(app)
        for key, value in list(apps.items()):
            if value is app:
                del apps[key]

    sdk = SimpleNamespace(
        credentials=FakeCredentials,
        firestore=FakeFirestoreModule,
        auth=FakeAuth,
        initialize_app=initialize_app,
        delete_app=delete_app,
        _apps=apps,
    )
    sdk.created = created
    sdk.deleted = deleted
    return sdk


def boom_loader():
    """Loader sentinel proving Firestore mode never touched the SDK."""
    raise AssertionError("firebase_admin must not be loaded in graph-only mode")
