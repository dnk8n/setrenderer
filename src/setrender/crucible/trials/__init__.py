"""The twenty trials. Each chapter of the set gets one; the music decides which goes where."""
from __future__ import annotations

from .ants import Ants
from .life import Commons, Lander, Slime
from .pixel import Crossing, Flap, Maze, Runner, Snake
from .soft import Boulders, Canyon, Courier, Sprint, Stairway, Sumo, Swim
from .swarm import Flock, SwarmSearch
from .three import MoonWalk, Summit

_ALL = [Sprint(), Canyon(), Boulders(), Stairway(), Courier(), Swim(), Sumo(), MoonWalk(), Summit(), SwarmSearch(),
        Flock(), Ants(), Flap(), Snake(), Maze(), Crossing(), Runner(), Lander(), Commons(), Slime()]
TRIALS = {t.key: t for t in _ALL}
