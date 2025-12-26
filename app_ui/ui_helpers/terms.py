"""Central UI terminology mapping for user-facing labels."""

PROJECT = "Project"
TOPIC = "Topic"
UNIT = "Unit"
LESSON = "Lesson"
ACTIVITY = "Activity"

PACK = "Pack"
BLOCK = "Block"


def label_for(kind: str) -> str:
    """Return the user-facing label for a given internal kind."""
    mapping = {
        "workspace": PROJECT,
        "module": TOPIC,
        "section": UNIT,
        "package": LESSON,
        "part": ACTIVITY,
        "component_pack": PACK,
        "component": BLOCK,
    }
    return mapping.get(kind, kind)
