from datetime import datetime

from sqlmodel import Field, SQLModel


class AuditBase(SQLModel):
    created_at: datetime = Field(
        default_factory=datetime.now,
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
        nullable=False,
    )
