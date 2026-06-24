from __future__ import annotations

from dataclasses import dataclass, field
import uuid


@dataclass(slots=True)
class Segment:
    start_frame: int
    end_frame: int
    fps: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    layer: str = "base"

    def __post_init__(self) -> None:
        self.start_frame = int(self.start_frame)
        self.end_frame = int(self.end_frame)
        self.fps = float(self.fps)
        if self.end_frame < self.start_frame:
            self.start_frame, self.end_frame = self.end_frame, self.start_frame

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame)

    @property
    def duration_seconds(self) -> float:
        return self.duration_frames / self.fps if self.fps else 0.0

    @property
    def start_sec(self) -> float:
        return self.start_frame / self.fps if self.fps else 0.0

    @property
    def end_sec(self) -> float:
        return self.end_frame / self.fps if self.fps else 0.0

    def contains(self, frame_index: int) -> bool:
        return self.start_frame <= frame_index < self.end_frame

    def clamp(self, max_frames: int) -> "Segment":
        max_frames = max(0, int(max_frames))
        return Segment(
            max(0, min(self.start_frame, max_frames)),
            max(0, min(self.end_frame, max_frames)),
            self.fps,
            id=self.id,
            layer=self.layer,
        )

    def shifted(self, delta_frames: int) -> "Segment":
        return Segment(
            self.start_frame + delta_frames,
            self.end_frame + delta_frames,
            self.fps,
            id=self.id,
            layer=self.layer,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "fps": self.fps,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Segment":
        return cls(
            payload["start_frame"],
            payload["end_frame"],
            payload.get("fps", 0.0),
            id=payload.get("id", str(uuid.uuid4())),
            layer=payload.get("layer", "base"),
        )

