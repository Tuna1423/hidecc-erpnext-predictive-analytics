from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field


class FeatureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    features: Dict[str, Any]


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    probability: float = Field(ge=0.0, le=1.0)
    band: str


class ScoreFromERPNextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overwrite: bool = False
