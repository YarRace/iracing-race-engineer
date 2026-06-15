import json

class StintDetector:
    def __init__(self):
        self._prev_on_track = False
    def update(self, on_track: bool) -> str:
        was = self._prev_on_track
        self._prev_on_track = on_track
        if on_track:
            return "running"
        return "closed" if was else "idle"

class StintWriter:
    def __init__(self, path): self._f = open(path, "w", encoding="utf-8")
    def write(self, frame: dict): self._f.write(json.dumps(frame) + "\n")
    def close(self): self._f.close()
