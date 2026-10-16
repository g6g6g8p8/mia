from __future__ import annotations

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SetupInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(default="", max_length=200)
    timezone: str = Field(default="America/Sao_Paulo", min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=200)
    area_name: str = Field(default='Minha biblioteca', min_length=2, max_length=80)
    area_description: str = Field(default="", max_length=500)

    @field_validator("name", "area_name")
    @classmethod
    def clean_required(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Campo obrigatório")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Fuso horário inválido") from exc
        return value


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AreaInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    color: Literal["slate", "violet", "blue", "green", "amber", "rose"] = "slate"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Use pelo menos dois caracteres")
        return value


class TaskInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    notes: str = Field(default="", max_length=10_000)
    area_id: str | None = None
    due_date: date | None = None
    priority: int = Field(default=2, ge=1, le=3)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Use pelo menos dois caracteres")
        return value


class TaskPatch(BaseModel):
    status: Literal["open", "done"]


class TaskReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=2, max_length=200)
    notes: str = Field(default='', max_length=10_000)
    due_date: date | None = None
    priority: int = Field(default=2, ge=1, le=3)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value: str) -> str:
        return TaskInput.clean_title(value)


class TaskApproval(BaseModel):
    model_config = ConfigDict(extra='forbid')
    edits: TaskReview | None = None


class OnboardingInput(BaseModel):
    goal: str = Field(default='',max_length=1000)
    completed: bool = False
    step: int = Field(default=0,ge=0,le=3)
    expected_goal_revision: int | None = Field(default=None,ge=0)
