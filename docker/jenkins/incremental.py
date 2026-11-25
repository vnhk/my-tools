"""Conservative build planning and verified snapshots of successful CI artifacts."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

NS = {"m": "http://maven.apache.org/POM/4.0.0"}
SCHEMA = 1


def module_graph(repo):
    root = ET.parse(repo / "pom.xml")
    modules = [m.text.strip() for m in root.findall("m:modules/m:module", NS)]
    poms = {m: ET.parse(repo / m / "pom.xml") for m in modules}
    artifacts = {}
    for name, pom in poms.items():
        group = pom.findtext("m:groupId", namespaces=NS) or pom.findtext("m:parent/m:groupId", namespaces=NS)
        artifact = pom.findtext("m:artifactId", namespaces=NS)
        if group != "com.bervan" or not artifact or "${" in artifact or artifact in artifacts:
            raise ValueError("Incremental builds require unique literal com.bervan module coordinates")
        artifacts[artifact] = name
    # Include dependencies from profiles/dependencyManagement and parent relations.
    # Extra edges rebuild more modules, which is safer than missing a consumer.
    graph = {}
    for name, pom in poms.items():
        references = pom.findall(".//m:dependency/m:artifactId", NS) + pom.findall("m:parent/m:artifactId", NS)
        if any("${" in (item.text or "") for item in references):
            raise ValueError("Property-based artifact IDs need explicit dependency graph support")
        graph[name] = {artifacts[item.text] for item in references if item.text in artifacts} - {name}
    return graph


def make_plan(repositories, previous, graph, force=False, integration_enabled=True):
    current = {r["path"]: r["commit"] for r in repositories}
    old = {r["path"]: r["commit"] for r in previous["repositories"]} if previous else {}
    changed = sorted(p for p in current.keys() | old.keys() if current.get(p) != old.get(p))
    full = force or previous is None or "my-tools" in changed or current.keys() != old.keys()
    utils = full or "bervan-utils" in changed
    selected = set(graph) if utils else {p.removeprefix("my-tools/") for p in changed if p.startswith("my-tools/")}
    if not selected <= graph.keys():
        raise ValueError("Changed repository is absent from the Maven module graph")
    while True:
        expanded = selected | {name for name, deps in graph.items() if deps & selected}
        if expanded == selected:
            break
        selected = expanded
    if selected:
        selected.add("my-tools-app")  # Always repackage the deployable backend.
    reason = "forced" if force else "no valid successful snapshot" if previous is None else "root/manifest changed" if full else "commit comparison"
    frontend = full or "my-tools-react" in changed
    integration = bool(selected) or frontend or not (previous or {}).get("integrationPassed", False)
    return {"schema": SCHEMA, "reason": reason, "changed": changed, "full": full,
            "utils": utils, "modules": [m for m in graph if m in selected],
            "backend": bool(selected), "frontend": frontend,
            "integration": integration,
            "tools": bool(selected) or frontend or (integration and integration_enabled)}


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not supported in successful build snapshots")
        if not path.is_file() or path == directory / "checksums.json":
            continue
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        result[str(path.relative_to(directory))] = digest.hexdigest()
    return result


def load_snapshot(directory):
    try:
        expected = json.loads((directory / "checksums.json").read_text())
        if not expected or inventory(directory) != expected:
            return None
        data = json.loads((directory / "release.json").read_text())
        required = ["contexts/backend/my-tools-app.jar", "contexts/frontend/nginx.conf"]
        if (data.get("snapshotSchema") != SCHEMA or
                not data.get("repositories") or not data.get("images") or
                any(not (directory / name).is_file() for name in required) or
                not (directory / "contexts/frontend/dist").is_dir() or
                not any((directory / "maven/com/bervan").rglob("*.jar"))):
            return None
        return data
    except (OSError, ValueError, TypeError, KeyError):
        return None


def plan_flag(data, name):
    plan = data["plan"]
    if name == "modules":
        return ",".join(plan["modules"])
    if name in {"utils", "full", "backend", "frontend", "integration", "tools"}:
        return str(plan[name]).lower()
    raise ValueError("Unknown build plan flag")


if __name__ == "__main__":
    with open(sys.argv[1]) as source:
        print(plan_flag(json.load(source), sys.argv[2]))
