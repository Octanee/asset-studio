"""Imports every module's tables so metadata is complete (migrations, tests)."""


def load_all() -> None:
    from asset_studio.modules.assets import models as _assets  # noqa: F401
    from asset_studio.modules.audit import models as _audit  # noqa: F401
    from asset_studio.modules.jobs import models as _jobs  # noqa: F401
    from asset_studio.modules.models import models as _models  # noqa: F401
    from asset_studio.modules.poses import models as _poses  # noqa: F401
    from asset_studio.modules.projects import models as _projects  # noqa: F401
    from asset_studio.modules.publishing import models as _publishing  # noqa: F401
    from asset_studio.modules.quality import models as _quality  # noqa: F401
    from asset_studio.modules.references import models as _references  # noqa: F401
    from asset_studio.modules.review import models as _review  # noqa: F401
    from asset_studio.modules.styles import loras as _loras  # noqa: F401
    from asset_studio.modules.styles import models as _styles  # noqa: F401
    from asset_studio.modules.system import idempotency as _idempotency  # noqa: F401
    from asset_studio.modules.system import settings as _settings  # noqa: F401
    from asset_studio.modules.training import models as _training  # noqa: F401
