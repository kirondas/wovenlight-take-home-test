"""
SQLAlchemy ORM models for scheduled TfL disruption-fetch tasks.

Defines the shared `DeclarativeBase`, the `TaskStatus` enumeration used throughout
the API and repository, and the `Task` table mapped to Python attributes. This is
the single source of truth for the persistence schema; migrations are not shown
in this take-home, so `create_all` is used at startup. In an interview, emphasize
why `result` and `error_message` are nullable (only set after execution) and how
`Mapped[]` typing helps catch column/type mistakes early.
"""
from datetime import datetime  # Type for schedule and audit timestamps stored in the database
from enum import Enum  # Standard library enumerations with stable string values for API/DB interchange
import uuid  # Generate RFC-4122 UUID strings for primary keys

from sqlalchemy import DateTime, JSON, String, Text  # Column types: timestamps, JSON blobs, short strings, long text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column  # Declarative ORM base and modern typed column API


class Base(DeclarativeBase):  # Subclass SQLAlchemy 2 style declarative base; collects `Model.metadata` for `create_all`
    pass  # No shared columns here; exists only as anchor for all ORM models in this service


class TaskStatus(str, Enum):  # Inherit `str` so member values compare cleanly to strings and serialise trivially to JSON
    PENDING = "pending"  # Task accepted and waiting for its scheduled run time
    RUNNING = "running"  # Worker has started execution (TfL request in flight)
    SUCCEEDED = "succeeded"  # Completed successfully; `result` should be populated
    FAILED = "failed"  # Completed with error; `error_message` should be populated

    @classmethod  # Allows `TaskStatus.values()` without instantiating the enum
    def values(cls) -> list[str]:  # Returns allowed status strings for query validation in the API layer
        return [status.value for status in cls]  # List comprehension over enum members pulling their string values


class Task(Base):  # Maps one row in the `tasks` table to a Python object used by repository and scheduler
    __tablename__ = "tasks"  # Actual SQL table name

    id: Mapped[str] = mapped_column(  # Primary key column typed as str in Python (UUID text)
        String(36),  # Enough length for UUID hex with hyphens
        primary_key=True,  # Defines uniqueness constraint and default join semantics
        default=lambda: str(uuid.uuid4()),  # Generate a new UUID string on INSERT if caller did not set id
    )
    schedule_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # When the job should run (naive local time in this app)
    lines: Mapped[list[str]] = mapped_column(JSON, nullable=False)  # List of normalised TfL line ids stored as JSON array
    status: Mapped[str] = mapped_column(  # Denormalised string mirrors enum `.value` for simple indexing/filtering
        String(20),  # Fits longest status token with margin
        nullable=False,  # Every task always has a lifecycle state
        default=TaskStatus.PENDING.value,  # New rows start as pending unless explicitly overridden
        index=True,  # Speeds up `WHERE status = 'pending'` for scheduler reload and list filters
    )
    result: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)  # TfL JSON list response; None until success
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # Human-readable failure reason; None until failure
    created_at: Mapped[datetime] = mapped_column(  # Row creation timestamp
        DateTime,  # Stored as database datetime
        nullable=False,  # Always set
        default=datetime.now,  # Note: called at insert time without parentheses—SQLAlchemy invokes the callable per row
    )
    updated_at: Mapped[datetime] = mapped_column(  # Last mutation timestamp for any field
        DateTime,  # Same type as created_at
        nullable=False,  # Always set
        default=datetime.now,  # Initial value on insert
        onupdate=datetime.now,  # SQLAlchemy refreshes this on UPDATE operations
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # Set when task finishes (success or failure); None while not finished
