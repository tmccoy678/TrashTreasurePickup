"""Map the single source tree to two portable installed skill packages."""

SKILLS = ("trashpickup", "treasurepickup")
POLICIES = ("LICENSE", "SECURITY.md", "CONTRIBUTING.md")
REFERENCES = (
    "macos-setup.md", "pickup-registry.md", "first-use.md", "comparison.md",
    "author-note.md", "lifecycle.md", "support.md", "security-launch.md",
)
INSTALLER_FILES = (
    "install.sh", "setup.py", "assets.tsv", "pixi.toml", "pixi.lock",
    "PIXI-LICENSE", "GITLEAKS-LICENSE", "THIRD_PARTY.md",
)


def regular_bytes(root, relative):
    path = root.resolve() / relative
    if not path.is_file() or path.resolve() != path:
        raise ValueError(f"Missing regular required file: {relative}")
    return path.read_bytes()


def shared_documents(root):
    paths = set(POLICIES) | {"references/" + name for name in REFERENCES}
    paths.update(str(path.relative_to(root)) for path in (root / "references").rglob("*") if path.is_file())
    return {relative: regular_bytes(root, relative) for relative in sorted(paths)}


def sync_documents(root, check=False):
    """Maintain regular-file copies for direct skill discovery and installation."""
    documents = shared_documents(root)
    for name in SKILLS:
        package = root / "skills" / name
        for relative, data in documents.items():
            target = package / relative
            if check:
                if regular_bytes(root, str(target.relative_to(root))) != data:
                    raise ValueError(f"Stale shared document: {target.relative_to(root)}; run scripts/sync_skill_docs.py")
            else:
                if target.resolve() != target:
                    raise ValueError(f"Refusing symlink destination: {target.relative_to(root)}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        extra = [path for path in (package / "references").rglob("*")
                 if path.is_file() and str(path.relative_to(package)) not in documents]
        if extra:
            raise ValueError(f"Unmapped package reference: {extra[0].relative_to(root)}")


def collect(root):
    sync_documents(root, check=True)
    mapping = {}
    for name in SKILLS:
        package = "skills/" + name + "/"
        selected = {"SKILL.md", "README.md", "agents/openai.yaml"}
        selected.update(str(path.relative_to(root / package)) for path in (root / package / "agents").glob("*.yaml"))
        if name == "treasurepickup":
            selected.update("scripts/" + item for item in ("pickup", "pickup_registry.py", "treasurepickup_receipt.py"))
        mapping.update({name + "/" + path: package + path for path in sorted(selected)})
        mapping.update({name + "/" + path: path for path in shared_documents(root)})
    mapping.update({"installer/" + name: "installer/" + name for name in INSTALLER_FILES})
    return {name: regular_bytes(root, path) for name, path in mapping.items()}, mapping
