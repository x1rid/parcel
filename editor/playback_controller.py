from enum import Enum, auto

class PlaybackState(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()

class PlaybackMode(Enum):
    NORMAL = auto()
    REPLAY = auto()

class PlaybackController:
    """Centralized playback state management."""
    def __init__(self):
        self.state = PlaybackState.STOPPED
        self.mode = PlaybackMode.NORMAL

    @property
    def is_playing(self) -> bool:
        return self.state == PlaybackState.PLAYING

    @property
    def is_replay_mode(self) -> bool:
        return self.mode == PlaybackMode.REPLAY

    def play(self, mode: PlaybackMode = PlaybackMode.NORMAL) -> None:
        self.state = PlaybackState.PLAYING
        self.mode = mode

    def pause(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.state = PlaybackState.PAUSED

    def stop(self) -> None:
        self.state = PlaybackState.STOPPED
        self.mode = PlaybackMode.NORMAL

    def toggle(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.pause()
        else:
            self.play(self.mode)
