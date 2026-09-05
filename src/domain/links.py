"""Graphe immuable des liens entre références d'artefacts."""

from dataclasses import dataclass
from typing import Any

from .outcomes import Accepted, Outcome, RefusalCode, Refused
from .references import ArtifactRef
from .vocabulary import LinkType


@dataclass(frozen=True, slots=True)
class Link:
    source: ArtifactRef
    target: ArtifactRef
    link_type: LinkType


@dataclass(frozen=True, slots=True)
class LinkGraph:
    entries: tuple[Link, ...] = ()


def _dependency_path(
    graph: LinkGraph, start: ArtifactRef, destination: ArtifactRef
) -> tuple[ArtifactRef, ...] | None:
    adjacency: dict[ArtifactRef, list[ArtifactRef]] = {}
    for link in graph.entries:
        if link.link_type is LinkType.DEPENDS_ON:
            adjacency.setdefault(link.source, []).append(link.target)
    pending: list[tuple[ArtifactRef, tuple[ArtifactRef, ...]]] = [(start, (start,))]
    visited: set[ArtifactRef] = set()
    while pending:
        node, path = pending.pop(0)
        if node == destination:
            return path
        if node in visited:
            continue
        visited.add(node)
        for neighbour in adjacency.get(node, ()):
            pending.append((neighbour, path + (neighbour,)))
    return None


def add_link(
    graph: LinkGraph,
    source: ArtifactRef,
    target: ArtifactRef,
    link_type: LinkType | Any,
) -> Outcome[LinkGraph, LinkGraph]:
    try:
        resolved_type = LinkType(link_type)
    except (TypeError, ValueError):
        return Refused(RefusalCode.UNKNOWN_LINK_TYPE, "link_type", graph)
    if resolved_type is LinkType.DEPENDS_ON:
        path = _dependency_path(graph, target, source)
        if path is not None:
            cycle = (source,) + path
            return Refused(
                RefusalCode.DEPENDENCY_CYCLE,
                source.artifact_id,
                graph,
                tuple(ref.artifact_id for ref in cycle),
            )
    return Accepted(LinkGraph(graph.entries + (Link(source, target, resolved_type),)))
