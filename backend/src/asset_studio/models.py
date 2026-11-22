"""Imports every module's tables so metadata is complete (migrations, tests)."""


def load_all() -> None:
    from asset_studio.modules.assets import models as _assets  # noqa: F401
    from asset_studio.modules.audit import models as _audit  # noqa: F401
    from asset_studio.modules.projects import models as _projects  # noqa: F401
