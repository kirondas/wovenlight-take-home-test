from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from .models import Base


def build_session_factory(database_url: str):
    engine_kwargs = {"future": True, "pool_pre_ping": True}

    if database_url == "sqlite:///:memory:":
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **engine_kwargs)
    Base.metadata.create_all(engine)

    session_factory = scoped_session(
        sessionmaker(bind=engine, expire_on_commit=False, future=True)
    )
    return session_factory, engine
