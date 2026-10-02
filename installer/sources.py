"""Map this repository to the small public installer payload."""

SKILLS = ("trashpickup", "treasurepickup")
SKILL_FILES = ("SKILL.md", "README.md", "agents/openai.yaml")
SHARED_FILES = ("LICENSE", "SECURITY.md")


def regular_bytes(root, relative):
    path = root.resolve() / relative
    if not path.is_file() or path.resolve() != path:
        raise ValueError(f"Missing regular required file: {relative}")
    return path.read_bytes()


def collect(root):
    mapping = {}
    for name in SKILLS:
        package = "skills/" + name + "/"
        mapping.update({name + "/" + path: package + path for path in SKILL_FILES})
        mapping.update({name + "/" + path: path for path in SHARED_FILES})
    mapping["installer/install.sh"] = "installer/install.sh"
    return {name: regular_bytes(root, path) for name, path in mapping.items()}, mapping
