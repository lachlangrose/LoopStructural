from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .model import GeologicalModelGraph, ScalarFeature, Unit

try:
    import matplotlib.pyplot as plt
    import networkx as nx

    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False
    nx = None
    plt = None


def check_visualization_available() -> None:
    if not VISUALIZATION_AVAILABLE:
        raise ImportError(
            "Visualization requires networkx and matplotlib. "
            "Install with: pip install networkx matplotlib"
        )


def to_networkx(
    g: GeologicalModelGraph,
    include_scalar_features: bool = True,
    include_observations: bool = False,
    include_fields: Optional[bool] = None,
) -> Any:
    """Convert GeologicalModelGraph to a NetworkX directed graph."""
    check_visualization_available()

    # Backward-compatible alias from pre-0.3 API.
    if include_fields is not None:
        include_scalar_features = include_fields

    G = nx.DiGraph()

    for fid, feature in g.features.items():
        if not include_scalar_features and isinstance(feature, ScalarFeature):
            continue

        source_kind = None
        scalar_role = None
        if isinstance(feature, ScalarFeature):
            source_kind = feature.source.kind
            scalar_role = feature.role

        G.add_node(
            fid,
            name=feature.name,
            type=feature.type,
            scalar_role=scalar_role,
            source_kind=source_kind,
            feature=feature,
        )

    if include_observations:
        for oid, observation in g.geo_observations.items():
            G.add_node(
                oid,
                name=observation.meta.get("name", oid),
                type="observation",
                feature=observation,
            )

    for rel in g.relations:
        if rel.src in G.nodes and rel.dst in G.nodes:
            G.add_edge(rel.src, rel.dst, relation=rel.kind, attrs=rel.attrs)

    for fid, feature in g.features.items():
        if fid not in G.nodes:
            continue
        if not isinstance(feature, Unit):
            continue

        rep = feature.representation
        if rep is not None and rep.scalar_feature_id in G.nodes:
            G.add_edge(fid, rep.scalar_feature_id, relation="uses_scalar")

    if include_observations:
        for oid, observation in g.geo_observations.items():
            if observation.target in G.nodes:
                G.add_edge(oid, observation.target, relation="observes")

    return G


def visualize_topology(
    g: GeologicalModelGraph,
    layout: str = "hierarchical",
    include_scalar_features: bool = True,
    include_observations: bool = False,
    figsize: Tuple[float, float] = (12, 8),
    show_labels: bool = True,
    show_legend: bool = True,
    save_path: Optional[str] = None,
    include_fields: Optional[bool] = None,
) -> Any:
    check_visualization_available()

    # Backward-compatible alias from pre-0.3 API.
    if include_fields is not None:
        include_scalar_features = include_fields

    G = to_networkx(
        g,
        include_scalar_features=include_scalar_features,
        include_observations=include_observations,
    )

    fig, ax = plt.subplots(figsize=figsize)

    color_map = {
        "unit": "#8ecae6",
        "fault": "#e63946",
        "fold": "#f77f00",
        "unconformity": "#9d4edd",
        "intrusion": "#d62828",
        "region": "#95d5b2",
        "scalar_feature": "#ffd60a",
        "observation": "#adb5bd",
    }

    node_colors = [color_map.get(G.nodes[node].get("type", "unit"), "#cccccc") for node in G.nodes()]

    if layout == "hierarchical":
        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
        except Exception:
            pos = _hierarchical_layout(G)
    elif layout == "spring":
        pos = nx.spring_layout(G, k=2, iterations=50)
    elif layout == "circular":
        pos = nx.circular_layout(G)
    elif layout == "shell":
        pos = nx.shell_layout(G)
    else:
        pos = nx.spring_layout(G)

    edge_colors = []
    for _, _, data in G.edges(data=True):
        rel = data.get("relation", "")
        if rel == "overlies":
            edge_colors.append("#2a9d8f")
        elif rel == "uses_scalar":
            edge_colors.append("#ffd60a")
        elif rel == "observes":
            edge_colors.append("#adb5bd")
        elif rel in ["displaces", "folds", "erodes", "intrudes", "crosscuts"]:
            edge_colors.append("#e63946")
        else:
            edge_colors.append("#6c757d")

    nx.draw_networkx_edges(
        G,
        pos,
        edge_color=edge_colors,
        arrows=True,
        arrowsize=20,
        arrowstyle="-|>",
        width=2,
        connectionstyle="arc3,rad=0.1",
        ax=ax,
    )

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1000, alpha=0.9, ax=ax)

    if show_labels:
        labels = {node: G.nodes[node].get("name", node) for node in G.nodes()}
        nx.draw_networkx_labels(G, pos, labels, font_size=9, ax=ax)

    edge_labels = {(u, v): data.get("relation", "") for u, v, data in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=7, ax=ax)

    if show_legend:
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor=color_map["unit"], label="Unit"),
            Patch(facecolor=color_map["fault"], label="Fault"),
            Patch(facecolor=color_map["fold"], label="Fold"),
            Patch(facecolor=color_map["unconformity"], label="Unconformity"),
            Patch(facecolor=color_map["intrusion"], label="Intrusion"),
            Patch(facecolor=color_map["region"], label="Region"),
        ]
        if include_scalar_features:
            legend_elements.append(Patch(facecolor=color_map["scalar_feature"], label="Scalar Feature"))
        if include_observations:
            legend_elements.append(Patch(facecolor=color_map["observation"], label="Observation"))
        ax.legend(handles=legend_elements, loc="upper right")

    ax.set_title(f"Geological Model Topology: {g.name}", fontsize=14, fontweight="bold")
    ax.axis("off")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig


def _hierarchical_layout(G: Any) -> Dict[str, Tuple[float, float]]:
    levels = {}
    in_degree = {node: 0 for node in G.nodes()}

    for u, v, data in G.edges(data=True):
        if data.get("relation") == "overlies":
            in_degree[v] += 1

    queue = [node for node, deg in in_degree.items() if deg == 0]
    level = 0

    while queue:
        next_queue = []
        for node in queue:
            levels[node] = level
            for u, v, data in G.edges(data=True):
                if u == node and data.get("relation") == "overlies":
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        next_queue.append(v)
        queue = next_queue
        level += 1

    pos = {}
    level_counts = {}
    for node in G.nodes():
        node_level = levels.get(node, 0)
        level_counts[node_level] = level_counts.get(node_level, 0) + 1

    level_positions = {lvl: 0 for lvl in level_counts.keys()}

    for node in G.nodes():
        node_level = levels.get(node, 0)
        x = level_positions[node_level]
        y = -node_level
        pos[node] = (x, y)
        level_positions[node_level] += 1

    return pos


def print_topology_summary(g: GeologicalModelGraph) -> None:
    print(f"\n{'='*60}")
    print(f"Geological Model: {g.name}")
    print(f"{'='*60}\n")

    print(f"Features ({len(g.features)}):")
    for ftype in ["unit", "fault", "fold", "unconformity", "intrusion", "region", "scalar_feature"]:
        features = [f for f in g.features.values() if f.type == ftype]
        if not features:
            continue

        print(f"  {ftype.replace('_', ' ').capitalize()}s: {len(features)}")
        for feature in features:
            if isinstance(feature, ScalarFeature):
                print(f"    - {feature.name} ({feature.id}) role={feature.role} source={feature.source.kind}")
            else:
                print(f"    - {feature.name} ({feature.id})")

    print(f"\nRelations ({len(g.relations)}):")
    relation_counts = {}
    for rel in g.relations:
        relation_counts[rel.kind] = relation_counts.get(rel.kind, 0) + 1

    for kind, count in relation_counts.items():
        print(f"  {kind}: {count}")
        for rel in g.relations:
            if rel.kind != kind:
                continue
            src_name = g.features.get(rel.src)
            dst_name = g.features.get(rel.dst)
            if src_name and dst_name:
                print(f"    {src_name.name} -> {dst_name.name}")

    if g.basement:
        basement_feature = g.features.get(g.basement)
        if basement_feature:
            print(f"\nBasement: {basement_feature.name}")

    print(f"\n{'='*60}\n")
