#!/usr/bin/env python3
"""Game layout profiles — registry and auto-detection.

`settings.game` in voices.json picks one by name; "auto" (the default)
starts on the last-used profile and switches when a frame carries chrome
unique to another game.
"""
from .base import Profile, in_region, narration_self_certain, split_camel  # noqa: F401
from .genshin import Genshin
from .hsr import HSR

PROFILES = {p.name: p for p in (HSR, Genshin)}
DEFAULT = HSR.name
# Profiles are stateless (layout constants + pure functions of a frame's
# blocks), so one shared instance each is enough.
_INSTANCES = {name: cls() for name, cls in PROFILES.items()}


def get_profile(name):
    """The profile with this name. Unknown names fall back to DEFAULT — a
    typo in voices.json must not take the app down."""
    return _INSTANCES.get((name or "").lower(), _INSTANCES[DEFAULT])


def profile_choices():
    """[(name, label)] for the dashboard, "auto" first."""
    return [("auto", "Auto-detect")] + [(n, c.label)
                                        for n, c in PROFILES.items()]


class ProfileSelector:
    """Holds the active profile and, in auto mode, switches games when the
    evidence is one-sided for a sustained run of frames.

    Deliberately sticky. Most frames (combat, overworld, menus) carry no
    game-identifying chrome at all, and a single misread must never swap
    the layout mid-conversation — that would drop the line being read.
    """

    # consecutive frames of one game's chrome, with none of the current
    # game's, before switching (~1.5s at 6fps)
    SWITCH_AFTER = 9

    def __init__(self, setting, on_switch=None):
        self.auto = (setting or "auto").lower() == "auto"
        self.profile = get_profile(DEFAULT if self.auto else setting)
        self.on_switch = on_switch
        self._votes = {}

    def observe(self, blocks):
        """Feed a frame's OCR blocks; returns the profile to classify with."""
        if not self.auto:
            return self.profile
        if self.profile.fingerprint(blocks) > 0:
            self._votes.clear()          # current game confirmed
            return self.profile
        for name, other in _INSTANCES.items():
            if name == self.profile.name:
                continue
            if other.fingerprint(blocks) > 0:
                self._votes[name] = self._votes.get(name, 0) + 1
                if self._votes[name] >= self.SWITCH_AFTER:
                    self.switch(name)
            else:
                self._votes.pop(name, None)
        return self.profile

    def switch(self, name):
        self.profile = get_profile(name)
        self._votes.clear()
        if self.on_switch:
            self.on_switch(self.profile)
        return self.profile

    def set_setting(self, setting):
        """Apply a game choice from the dashboard."""
        self.auto = (setting or "auto").lower() == "auto"
        self._votes.clear()
        if not self.auto:
            self.profile = get_profile(setting)
        return self.profile
