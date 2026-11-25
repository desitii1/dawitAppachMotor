from app.main import app
from app.database import Base
from app import models as models  # noqa: F401


def test_health_app_and_metadata():
    assert app.title == "DawitAppachMotor Lottery API"
    assert len(Base.metadata.tables) == 12
