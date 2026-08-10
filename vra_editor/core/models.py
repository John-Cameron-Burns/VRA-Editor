from dataclasses import dataclass, field
from typing import List


@dataclass
class VraAgent:
    name: str = ""
    role: str = ""


@dataclass
class VraTitle:
    title: str = ""
    type_: str = ""


@dataclass
class VraWork:
    id: str = "w1"
    titles: List[VraTitle] = field(default_factory=list)
    agents: List[VraAgent] = field(default_factory=list)
