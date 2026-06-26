from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.models.icp_blocks import CSLBICPBlock, ZoomInfoICPBlock


class ICP(BaseModel):
    id: str
    label: str
    industries: list[str] = Field(default_factory=list)
    employee_min: int | None = None
    employee_max: int | None = None
    revenue_min: int | None = None
    revenue_max: int | None = None
    geographies: list[str] = Field(default_factory=list)

    # ZoomInfo-shaped fields. Kept at the top level for backwards-compatibility
    # with Phase 1 YAMLs; mirrored into `zoominfo` block via the validator.
    technologies_present: list[str] = Field(default_factory=list)
    technologies_absent: list[str] = Field(default_factory=list)

    # Source-specific blocks. Optional — populated when a YAML carries them.
    zoominfo: ZoomInfoICPBlock | None = None
    cslb: CSLBICPBlock | None = None

    notes: str | None = None

    @model_validator(mode="after")
    def _hydrate_zoominfo_block(self) -> "ICP":
        # Mirror top-level technologies fields into the zoominfo block when
        # the block isn't explicitly provided.
        if self.zoominfo is None and (
            self.technologies_present or self.technologies_absent
        ):
            self.zoominfo = ZoomInfoICPBlock(
                technologies_present=self.technologies_present,
                technologies_absent=self.technologies_absent,
            )
        return self
