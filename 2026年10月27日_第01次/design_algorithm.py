#!/usr/bin/env python3
"""Reproducible composition coverage and conditional I-criterion level selection.

The output is an exploratory design, not observed sensory results.
I-selection targets the explicitly declared additive 86-column baseline.
It does not identify all 435 interactions without assumptions or follow-up data.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import openpyxl  # Reading the source only; workbook authoring is in build_workbook.mjs.


def blob_sha(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


def read_source(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    source = list(wb["all data"].values)
    headers = source[0]
    assert len(headers[7:120]) == 113 and "OAV" not in str(headers[119])
    assert "OAV" in str(headers[120])
    compounds = []
    for row in source[1:]:
        vals = [float(x) for x in row[7:120]
                if isinstance(x, (int, float)) and math.isfinite(x)]
        assert vals and min(vals) >= 0
        pos = [x for x in vals if x > 0]
        threshold = float(row[6])
        med, mean, high = float(np.median(vals)), float(np.mean(vals)), max(vals)
        assert threshold > 0 and pos and high > min(pos)
        med_oav, mean_oav = med / threshold, mean / threshold
        base = mean_oav < 1 or med_oav < 1
        tier = "骨架成分" if med_oav > 50 else ("重要成分" if med_oav >= 2 else "两档成分")
        nlevels = 0 if base else (3 if med_oav >= 2 else 2)
        # New three-level grid: log-equidistant over the observed positive range.
        # Two-level compounds retain the user's median / maximum rule.
        levels = ([min(pos), math.sqrt(min(pos) * high), high] if nlevels == 3
                  else ([med, high] if nlevels == 2 else []))
        codes = ["L", "M", "H"] if nlevels == 3 else (["M", "H"] if nlevels == 2 else [])
        if not base:
            assert 0 < levels[0] < levels[-1] and len(set(levels)) == len(levels)
        compounds.append({
            "id": int(row[0]), "cas": str(row[1]), "english": str(row[2]),
            "name": str(row[3]), "threshold": threshold, "n": len(vals),
            "raw_min": min(vals), "min_positive": min(pos), "median": med,
            "max": high, "mean": mean, "median_oav": med_oav,
            "mean_oav": mean_oav, "base": base, "tier": tier,
            "nlevels": nlevels, "levels": levels, "codes": codes,
            "fixed_concentration": mean if base else 0.0,
            "raw": [float(x) if isinstance(x, (int, float)) and math.isfinite(x)
                    else None for x in row[7:120]],
        })
    wb.close()
    assert len(compounds) == 41 and len({c["id"] for c in compounds}) == 41
    assert sum(c["base"] for c in compounds) == 11
    assert sum(c["nlevels"] == 3 for c in compounds) == 25
    assert sum(c["nlevels"] == 2 for c in compounds) == 5
    return compounds, list(headers[7:120])


def setup(compounds):
    variables = [c for c in compounds if not c["base"]]
    n = len(variables)
    pair_list = list(itertools.combinations(range(n), 2))
    pair_lookup = {p: j for j, p in enumerate(pair_list)}
    compositions = np.array(list(itertools.combinations(range(n), 4)), dtype=np.int16)
    slots = list(itertools.combinations(range(4), 2))
    composition_pairs = np.array(
        [[pair_lookup[(int(a[i]), int(a[j]))] for i, j in slots] for a in compositions],
        dtype=np.int16,
    )
    quad = {i: 1 + 2*n + k for k, i in enumerate(
        i for i, c in enumerate(variables) if c["nlevels"] == 3)}
    dim = 1 + 2*n + len(quad)
    assert n == 30 and dim == 86 and len(compositions) == 27405

    def feature(active, levels):
        f = np.zeros(dim)
        f[0] = 1
        for i, li in zip(active, levels):
            c = variables[int(i)]
            concentration = c["levels"][int(li)]
            # Conditional log coding: absent => presence=0 and z=0.
            z = (2*math.log(concentration)-math.log(c["levels"][0])-math.log(c["levels"][-1])) / (
                math.log(c["levels"][-1])-math.log(c["levels"][0]))
            f[1+i] = 1
            f[1+n+i] = z
            if i in quad:
                f[quad[i]] = z*z
        return f

    def states(active):
        choices = list(itertools.product(*(range(variables[int(i)]["nlevels"]) for i in active)))
        return choices, np.array([feature(active, s) for s in choices])
    return variables, pair_list, compositions, composition_pairs, feature, states, dim


def select_compositions(compositions, cpairs, count, seed):
    """Lexicographic greedy coverage. No chemical classes or OAV weights."""
    rng = np.random.default_rng(seed)
    pair_counts = np.zeros(435, dtype=np.int16)
    freq = np.zeros(30, dtype=np.int16)
    available = np.ones(len(compositions), dtype=bool)
    selected = []
    for _ in range(count):
        floor = int(pair_counts.min())
        gain = (pair_counts[cpairs] == floor).sum(axis=1)
        gain[~available] = -1
        candidates = np.flatnonzero(gain == gain.max())
        burden = freq[compositions[candidates]].sum(axis=1)
        candidates = candidates[burden == burden.min()]
        local_load = pair_counts[cpairs[candidates]].sum(axis=1)
        candidates = candidates[local_load == local_load.min()]
        j = int(rng.choice(candidates))
        selected.append(j)
        available[j] = False
        pair_counts[cpairs[j]] += 1
        freq[compositions[j]] += 1
    key = (int(pair_counts.min()), -float(np.var(pair_counts)), -float(np.var(freq)))
    return key, selected, pair_counts, freq


def choose_levels(active_sets, anchor_x, states, moments, seed, criterion="I", sweeps=3):
    """Greedy addition followed by exact single-row exchanges, fixed compositions."""
    rng = np.random.default_rng(seed)
    state_lists = [states(a) for a in active_sets]
    information = anchor_x.T @ anchor_x
    inv = np.linalg.inv(information)
    chosen = [None] * len(active_sets)
    xrows = [None] * len(active_sets)
    order = rng.permutation(len(active_sets))
    for j in order:
        labels, F = state_lists[j]
        h = np.einsum("ij,jk,ik->i", F, inv, F)
        if criterion == "I":
            G = inv @ moments @ inv
            gain = np.einsum("ij,jk,ik->i", F, G, F) / (1+h)
        else:
            gain = np.log1p(h)
        candidates = np.flatnonzero(np.isclose(gain, gain.max(), rtol=1e-11, atol=1e-13))
        k = int(rng.choice(candidates))
        f = F[k].copy()
        chosen[j], xrows[j] = labels[k], f
        a = inv @ f
        inv -= np.outer(a, a) / (1+f@a)
    X = np.vstack([anchor_x, *xrows])
    for _ in range(sweeps):
        changed = 0
        inv = np.linalg.inv(X.T @ X)
        for j in rng.permutation(len(active_sets)):
            labels, F = state_lists[j]
            old = xrows[j]
            a = inv @ old
            denom = 1-old@a
            assert denom > 1e-8
            minus_inv = inv + np.outer(a, a)/denom
            h = np.einsum("ij,jk,ik->i", F, minus_inv, F)
            if criterion == "I":
                G = minus_inv @ moments @ minus_inv
                gain = np.einsum("ij,jk,ik->i", F, G, F)/(1+h)
            else:
                gain = np.log1p(h)
            k = int(np.argmax(gain))
            old_h = float(old @ minus_inv @ old)
            old_gain = (float(old @ minus_inv @ moments @ minus_inv @ old)/(1+old_h)
                        if criterion == "I" else math.log1p(old_h))
            if gain[k] > old_gain + 1e-11:
                f = F[k].copy()
                chosen[j], xrows[j] = labels[k], f
                b = minus_inv @ f
                inv = minus_inv - np.outer(b, b)/(1+f@b)
                changed += 1
        X = np.vstack([anchor_x, *xrows])
        if not changed:
            break
    A = X.T @ X
    inv = np.linalg.inv(A)
    return {
        "levels": chosen, "X": X, "I": float(np.trace(inv @ moments)),
        "logdet": float(np.linalg.slogdet(A)[1]), "rank": int(np.linalg.matrix_rank(X)),
        "condition": float(np.linalg.cond(X)),
    }


def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    compounds, raw_headers = read_source(args.input)
    v, pairs, compositions, cpairs, feature, states, dim = setup(compounds)
    anchor = [{"active": [], "level_indices": [], "purpose": "拟合", "kind": "共同基底对照"}]
    for i, c in enumerate(v):
        for li in range(c["nlevels"]):
            anchor.append({"active": [i], "level_indices": [li], "purpose": "拟合", "kind": "单体浓度锚点"})
    anchor_x = np.array([feature(a["active"], a["level_indices"]) for a in anchor])
    assert len(anchor) == dim and np.linalg.matrix_rank(anchor_x) == dim
    candidates = [select_compositions(compositions, cpairs, 224, args.seed+s)
                  for s in range(args.starts)]
    best_key = max(r[0] for r in candidates)
    best = next(r for r in candidates if r[0] == best_key)
    _, selected, pair_counts, freq = best
    assert pair_counts.min() >= 2
    active_sets = [tuple(map(int, compositions[j])) for j in selected]
    print(json.dumps({"composition_coverage": int((pair_counts > 0).sum()),
                      "min_pair_count": int(pair_counts.min()), "max_pair_count": int(pair_counts.max()),
                      "mixture_frequency": [int(freq.min()), int(freq.max())]}), flush=True)

    # Independent, seeded design-domain integration sample, no sensory outcomes.
    ref_rng = np.random.default_rng(args.seed+10000)
    eval_x = []
    for _ in range(6000):
        a = tuple(map(int, compositions[int(ref_rng.integers(len(compositions)))]))
        li = [int(ref_rng.integers(v[i]["nlevels"])) for i in a]
        eval_x.append(feature(a, li))
    eval_x = np.array(eval_x)
    moments = eval_x.T @ eval_x / len(eval_x)
    runs = []
    for s in range(4):
        r = choose_levels(active_sets, anchor_x, states, moments, args.seed+200+s, "I")
        runs.append(r)
        print(json.dumps({"I_start": s, "I": r["I"], "rank": r["rank"]}), flush=True)
    chosen = min(runs, key=lambda r: r["I"])
    d_run = choose_levels(active_sets, anchor_x, states, moments, args.seed+999, "D")
    baseline_rng = np.random.default_rng(args.seed+30000)
    baseline_I = []
    for _ in range(32):
        random_x = np.array([feature(a, [int(baseline_rng.integers(v[i]["nlevels"])) for i in a])
                             for a in active_sets])
        X = np.vstack([anchor_x, random_x])
        baseline_I.append(float(np.trace(np.linalg.inv(X.T @ X) @ moments)))
    train = anchor + [
        {"active": list(a), "level_indices": list(li), "purpose": "拟合", "kind": "四元组合"}
        for a, li in zip(active_sets, chosen["levels"])]
    assert len(train) == 310
    for j, r in enumerate(train, 1):
        r["sample_id"] = f"T{j:03d}"
        r["repeat_of"] = ""
    X = chosen["X"]
    inv = np.linalg.inv(X.T @ X)
    leverage = np.einsum("ij,jk,ik->i", X, inv, X)
    # Independent preparation repeats; two baseline controls + 18 reference mixtures.
    repeat_indices = [0, 0] + list(86+np.argsort(leverage[86:])[-18:])
    repeats = []
    for j, ix in enumerate(repeat_indices, 1):
        r = dict(train[int(ix)])
        r.update(sample_id=f"R{j:03d}", purpose="独立配制重复",
                 kind="共同基底重复" if ix == 0 else "组合重复",
                 repeat_of=train[int(ix)]["sample_id"])
        repeats.append(r)
    # Completely unused composition sets for validation; no response-dependent selection.
    val_rng = np.random.default_rng(args.seed+40000)
    unused = np.setdiff1d(np.arange(len(compositions)), np.array(selected))
    validation = []
    for j, ci in enumerate(val_rng.choice(unused, 20, replace=False), 1):
        a = list(map(int, compositions[int(ci)]))
        li = [int(val_rng.integers(v[i]["nlevels"])) for i in a]
        validation.append({"sample_id": f"V{j:03d}", "purpose": "留出验证",
                           "kind": "新组成验证", "repeat_of": "",
                           "active": a, "level_indices": li})
    rows = train+repeats+validation
    assert len(rows) == 350
    group_ids = {}
    for r in rows:
        a = tuple(r["active"])
        if not a:
            gid = "BASE"
        elif len(a) == 1:
            gid = f"S-{v[a[0]]['id']}"
        else:
            group_ids.setdefault(a, f"C{len(group_ids)+1:03d}")
            gid = group_ids[a]
        r["composition_id"] = gid
        r["compound_ids"] = [v[i]["id"] for i in a]
        r["codes"] = [v[i]["codes"][li] for i, li in zip(a, r["level_indices"])]
        r["concentrations"] = [v[i]["levels"][li] for i, li in zip(a, r["level_indices"])]
        r["names"] = [v[i]["name"] for i in a]
        r["OAV"] = [c/v[i]["threshold"] for i, c in zip(a, r["concentrations"])]
        r["mass_20ml_ug"] = [c*0.02 for c in r["concentrations"]]
    composition_counts = {}
    for r in rows:
        key = r["composition_id"]
        composition_counts[key] = composition_counts.get(key, 0)+1
    assert max(composition_counts.values()) <= 30
    unique = len({(tuple(r["compound_ids"]), tuple(r["codes"])) for r in rows})
    assert unique == 330

    pair_output = []
    cross = 0
    for pi, (i, j) in enumerate(pairs):
        subsets = {}
        for purpose in ["拟合", "独立配制重复", "留出验证"]:
            rr = [r for r in rows if r["purpose"] == purpose and i in r["active"] and j in r["active"]]
            subsets[purpose] = len(rr)
        cells = set()
        backgrounds = set()
        for r in train:
            if i in r["active"] and j in r["active"]:
                a, b = r["active"].index(i), r["active"].index(j)
                cells.add((r["codes"][a], r["codes"][b]))
                backgrounds.add(tuple(k for k in r["active"] if k not in [i, j]))
        is_cross = v[i]["nlevels"] != v[j]["nlevels"]
        cross += int(is_cross and subsets["拟合"] > 0)
        pair_output.append({"i": i, "j": j, "id_a": v[i]["id"], "id_b": v[j]["id"],
                            "name_a": v[i]["name"], "name_b": v[j]["name"],
                            "type": f"{v[i]['nlevels']}档×{v[j]['nlevels']}档",
                            "training": subsets["拟合"], "repeat": subsets["独立配制重复"],
                            "validation": subsets["留出验证"], "distinct_backgrounds": len(backgrounds),
                            "level_cells": len(cells), "possible_level_cells": v[i]["nlevels"]*v[j]["nlevels"]})
    # Full model with presence interactions: show rank, not independent estimability.
    presence_pairs = np.array([[f[1+i]*f[1+j] for i,j in pairs] for f in X])
    full_X = np.hstack([X, presence_pairs])
    full_rank = int(np.linalg.matrix_rank(full_X))
    # Independent integrations to check sensitivity to the numerical reference sample.
    ref_check = np.random.default_rng(args.seed+50000)
    hold_x = []
    for _ in range(6000):
        a = tuple(map(int, compositions[int(ref_check.integers(len(compositions)))]))
        hold_x.append(feature(a, [int(ref_check.integers(v[i]["nlevels"])) for i in a]))
    hold_x = np.array(hold_x)
    I_check = float(np.mean(np.einsum("ij,jk,ik->i", hold_x, inv, hold_x)))
    baseline_mean = float(np.mean(baseline_I))
    summary = {
        "total_preparations": 350, "unique_formulations": unique,
        "candidate_count": len(compounds), "variable_count": len(v), "base_count": 11,
        "three_level": 25, "two_level": 5,
        "training": 310, "single_compound_anchors": 85, "training_base_control": 1,
        "training_four_component": 224, "independent_repeats": 20, "validation": 20,
        "total_pairs": 435, "covered_training_pairs": int((pair_counts > 0).sum()),
        "min_training_pair_count": int(pair_counts.min()),
        "max_training_pair_count": int(pair_counts.max()), "cross_level_pairs": cross,
        "training_level_cells_covered": sum(p["level_cells"] for p in pair_output),
        "training_level_cells_possible": sum(p["possible_level_cells"] for p in pair_output),
        "core_model_columns": dim, "core_model_rank": chosen["rank"],
        "core_condition_number": chosen["condition"], "core_I": chosen["I"],
        "independent_reference_I": I_check, "D_comparison_I": d_run["I"],
        "random_level_I_mean": baseline_mean,
        "I_reduction_vs_random_mean": 1-chosen["I"]/baseline_mean,
        "full_presence_interaction_columns": int(full_X.shape[1]),
        "full_presence_interaction_rank": full_rank,
        "max_preparations_per_composition": max(composition_counts.values()),
        "four_component_composition_count": len(group_ids),
        "mixture_appearances_min": int(freq.min()), "mixture_appearances_max": int(freq.max()),
    }
    output = {
        "config": {"seed": args.seed, "composition_starts": args.starts, "level_starts": 4,
                   "level_exchange_sweeps": 3, "reference_draws": 6000,
                   "integration_distribution": "uniform 4-compound subset, then uniform allowed level per compound",
                   "source_git_blob_sha": blob_sha(args.input),
                   "source_name": "可用化合物原始数据.xlsx",
                   "algorithm": "lexicographic greedy coverage; conditional I-criterion concentration exchange",
                   "unit": "ug/L", "volume_ml": 20, "ethanol_vv_percent": 53,
                   "model": "intercept + 30 presence + 30 conditional log-dose + 25 single-compound curvature",
                   "base_rule": "mean_OAV<1 OR median_OAV<1; concentration=arithmetic mean",
                   "three_level_rule": "observed minimum positive; geometric midpoint; observed maximum",
                   "two_level_rule": "observed median; observed maximum",
                   "inference_scope": "exploratory global screening, not separate 4-factor surfaces or all-pair inference"},
        "summary": summary, "compounds": compounds, "raw_headers": raw_headers,
        "rows": rows, "pairs": pair_output,
        "level_optimization_starts": [{"I": r["I"], "logdet": r["logdet"]} for r in runs],
        "random_baseline_I": baseline_I,
    }
    (out/"design.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    (out/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="可用化合物原始数据.xlsx")
    ap.add_argument("--output", default="outputs/algorithm350")
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--starts", type=int, default=12)
    run(ap.parse_args())
