"""Global application settings stored as key-value pairs."""

from __future__ import annotations

from sqlmodel import Field

from .base import AuditBase


class AppSetting(AuditBase, table=True):
    __tablename__ = "app_settings"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(max_length=100, unique=True)
    value: str = Field(max_length=500)
    description: str | None = None
