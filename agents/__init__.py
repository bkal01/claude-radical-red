from agents.hardcoded import HardcodedAgent
from agents.simple import SimpleAgent

REGISTRY: dict[str, type] = {
    "hardcoded": HardcodedAgent,
    "simple": SimpleAgent,
}
