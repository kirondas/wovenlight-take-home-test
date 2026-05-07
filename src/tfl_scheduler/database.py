"""
SQLAlchemy engine and session factory construction.

This module isolates database bootstrap logic: creating the SQLAlchemy `Engine`,
applying connection-pool tweaks for SQLite in-memory tests, creating tables from
ORM metadata, and returning a `scoped_session` factory suitable for multi-threaded
Flask or APScheduler workers. Interview angle: explain why `scoped_session` ties
one Session per thread and why `expire_on_commit=False` keeps attributes readable
after the transaction ends.
"""
from sqlalchemy.orm import scoped_session, sessionmaker  # scoped_session: thread-local Session registry; sessionmaker: factory that builds Session classes
from sqlalchemy.pool import StaticPool  # Connection pool that holds one connection shared across threads—needed for SQLite `:memory:`
from sqlalchemy import create_engine  # Factory that builds a database Engine from a URL

from .models import Base  # Declarative metadata registry; `create_all` uses it to emit CREATE TABLE


def build_session_factory(database_url: str):  # Returns (session_factory, engine); caller may keep engine for disposal in tests
    engine_kwargs = {"future": True, "pool_pre_ping": True}  # `future=True` opts into SQLAlchemy 2.0-style behaviour; `pool_pre_ping` validates connections before use

    if database_url == "sqlite:///:memory:":  # Special case: in-memory SQLite is not multi-thread safe by default
        engine_kwargs["connect_args"] = {"check_same_thread": False}  # Allow SQLite connection to be used from APScheduler / Flask worker threads
        engine_kwargs["poolclass"] = StaticPool  # Keep a single shared connection so `:memory:` survives across threads

    engine = create_engine(database_url, **engine_kwargs)  # Create low-level DB connection pool and dialect handler
    Base.metadata.create_all(engine)  # CREATE TABLE for all models registered on `Base` if they do not exist

    session_factory = scoped_session(  # Thread-local registry: `session_factory()` returns a Session for the current thread
        sessionmaker(bind=engine, expire_on_commit=False, future=True)  # `expire_on_commit=False` keeps loaded columns usable after commit; `bind` ties Session to this engine
    )
    return session_factory, engine  # Tuple so tests can `engine.dispose()`; app.py currently ignores engine with `_`
