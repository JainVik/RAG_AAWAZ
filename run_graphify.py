import sys
import json
import os
from pathlib import Path
from graphify.detect import detect
from graphify.extract import collect_files, extract
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html

target_dir = Path(".").resolve()
out_dir = target_dir / "graphify-out"
out_dir.mkdir(exist_ok=True)

print(f"Running Graphify on: {target_dir}")
result = detect(target_dir)
total_files = result.get("total_files", 0)
print(f"Detect: {total_files} total files ({result.get('total_words', 0)} words)")

code_files_raw = result.get("files", {}).get("code", [])
code_files = []
for f in code_files_raw:
    p = Path(f)
    if "node_modules" in p.parts or ".venv" in p.parts or "dist" in p.parts or ".pytest_cache" in p.parts:
        continue
    code_files.append(p)

print(f"Processing {len(code_files)} code files for AST extraction...")
ast_res = extract(code_files)
print(f"AST extracted: {len(ast_res.get('nodes', []))} nodes, {len(ast_res.get('edges', []))} edges")

G = build_from_json(ast_res)
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

# Generate descriptive labels based on members
labels = {}
for cid, members in communities.items():
    member_labels = [G.nodes[n].get("label", n) for n in members[:3]]
    labels[cid] = f"Community {cid}: " + ", ".join(member_labels)

questions = suggest_questions(G, communities, labels)

report = generate(
    G,
    communities,
    cohesion,
    labels,
    gods,
    surprises,
    result,
    {"input": 0, "output": 0},
    str(target_dir),
    suggested_questions=questions,
)

(out_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
to_json(G, communities, str(out_dir / "graph.json"))
to_html(G, communities, str(out_dir / "graph.html"), community_labels=labels)

print(f"Graphify Complete!")
print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")
print(f"Outputs written to: {out_dir}")
