"""Reproducible conditional reports and cheap analytical calibration."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, chi2, kstest, norm

from .likelihood import LinearGaussian
from .schema import BASE, digest, write_json


def analytical_calibration(settings):
    rng = np.random.default_rng(settings["calibration_seed"])
    count = settings["trials"]
    prior_mean = np.array(settings["prior_mean_ab_m"], dtype=float)
    prior_cov = np.eye(2) * settings["prior_sd_ab_m"] ** 2
    results = {}
    for name, matrix in [
        ("two_markers", np.array([[1, 0], [0.6, 0.8]])),
        ("parallel_markers", np.array([[1, 0], [1, 0]])),
        ("known_direction_scalar", np.array([[0.6]])),
    ]:
        dimension = matrix.shape[1]
        prior = rng.multivariate_normal(
            prior_mean[:dimension], prior_cov[:dimension, :dimension], count
        )
        observations = prior @ matrix.T + rng.normal(
            0, settings["noise_sd_m"], (count, matrix.shape[0])
        )
        centres, covariance = [], None
        for y in observations:
            problem = LinearGaussian(matrix, y, np.full(len(y), settings["noise_sd_m"]))
            mean, covariance = problem.posterior(
                prior_mean[:dimension], prior_cov[:dimension, :dimension]
            )
            centres.append(mean)
        centres = np.array(centres)
        sd = np.sqrt(np.diag(covariance))
        standard = (prior - centres) / sd
        component = []
        for j in range(dimension):
            hits = int((np.abs(standard[:, j]) <= norm.ppf(0.95)).sum())
            interval = binomtest(hits, count).proportion_ci(confidence_level=0.95)
            pit = norm.cdf(standard[:, j])
            component.append(
                {
                    "coverage90": hits / count,
                    "hits": hits,
                    "trials": count,
                    "binomial95_interval": [float(interval.low), float(interval.high)],
                    "posterior_rank_histogram": np.histogram(pit, np.linspace(0, 1, 11))[
                        0
                    ].tolist(),
                    "rank_KS_distance": float(kstest(pit, "uniform").statistic),
                }
            )
        delta = prior - centres
        mahalanobis = np.einsum("ij,jk,ik->i", delta, np.linalg.inv(covariance), delta)
        results[name] = {
            "components": component,
            "likelihood_rank": int(np.linalg.matrix_rank(matrix)),
            "dimension": dimension,
            "joint90_coverage": float((mahalanobis <= chi2.ppf(0.9, dimension)).mean()),
            "status": "pass" if all(0.85 <= c["coverage90"] <= 0.95 for c in component) else "fail",
        }
    return {
        "seed": settings["calibration_seed"],
        "trials_per_problem": count,
        "results": results,
        "status": "pass" if all(r["status"] == "pass" for r in results.values()) else "fail",
        "scope": "exact linear-Gaussian independent-prior verification, not calibration of the polar-prior dataset posterior",
        "known_direction_prior": "signed scalar Gaussian for verification; dataset D has its separate truncated-uniform check",
        "warning": "85-95% is a screening band; binomial intervals describe its sampling uncertainty",
    }


def make_report(output):
    output = Path(output)
    config = json.loads((output / "configuration.json").read_text())
    evaluation = json.loads((output / "evaluation.json").read_text())
    summaries = [
        json.loads((output / f"fold_{i}" / "summary.json").read_text()) for i in config["folds"]
    ]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    saved = np.load(output / "fold_0" / "posterior.npz")
    vectors, weights = saved["components_ab_m"], saved["weights"]
    keep = np.flatnonzero(weights > weights.max() * 1e-4)
    keep = keep[:: max(1, len(keep) // 20000)]
    axes[0].scatter(
        vectors[keep, 0], vectors[keep, 1], c=np.log10(weights[keep]), s=3, cmap="viridis"
    )
    axes[0].set(
        xlabel="strike component a (m)",
        ylabel="downward component b (m)",
        title=f"{config['case']}, fold 0: compatibility",
    )
    axes[1].hist(
        np.linalg.norm(vectors, axis=1),
        bins=np.linspace(0, 600, 101),
        weights=weights,
        histtype="step",
        label="D",
    )
    axes[1].set(
        xlabel="magnitude D (m)",
        ylabel="posterior mass / bin",
        title="Declared uniform-D prior updated",
    )
    errors = [m["median_group_contact_error_m"] for m in evaluation["folds"]]
    axes[2].bar(config["folds"], errors)
    axes[2].set(
        xlabel="withheld fold", ylabel="median trace error (m)", title="Saved contact predictions"
    )
    fig.tight_layout()
    fig.savefig(output / "diagnostics.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 4))
    if config["case"] == "E1":
        pitch = np.degrees(summaries[0]["constraints"]["fixed"]["pitch_radians"])
        ax.axvline(pitch, label="Fixed expert direction")
        ax.set_xlim(pitch - 5, pitch + 5)
        ax.set_yticks([])
        ax.legend()
    else:
        ax.hist(
            np.degrees(np.arctan2(vectors[:, 1], vectors[:, 0])),
            bins=90,
            weights=weights,
            histtype="step",
        )
    ax.set(
        xlabel="signed pitch (degrees)",
        ylabel="" if config["case"] == "E1" else "posterior mass / bin",
        title="Pitch conditional on declared support; undefined at zero slip",
    )
    fig.tight_layout()
    fig.savefig(output / "pitch.png", dpi=150)
    plt.close(fig)
    curves = pd.read_csv(output / "fold_0" / "predictions.csv")
    heldout = pd.read_csv(output / "fold_0" / "scored_predictions.csv")
    fig, ax = plt.subplots(figsize=(6, 6))
    for _, curve in curves.groupby(["contact_id", "wall"]):
        ax.plot(curve.X, curve.Y, color="grey", linewidth=0.8)
    ax.scatter(heldout.X, heldout.Y, s=12, c="darkblue", label="Withheld contacts")
    ax.axvline(0, color="black", label="Known fault")
    ax.set(
        xlabel="x (m)", ylabel="y (m)", title="Fold 0: fixed predicted traces and withheld contacts"
    )
    ax.set_aspect("equal")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "withheld_contacts.png", dpi=150)
    plt.close(fig)
    lines = [
        f"# {config['case']} first synthetic benchmark",
        "",
        "Status: complete, conditional uncertainty only.",
        "",
        "The likelihood has rank one on every fold. The prior and expert constraints shape the remaining family.",
        "",
        "| Fold | a mean (m) | b mean (m) | D 90% (m) | Contact error (m) | Coverage 90% | Plane sensitivity SD |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for i, (summary, metrics) in enumerate(zip(summaries, evaluation["folds"])):
        a, b = summary["mean_ab_m"]
        lo, hi = summary["interval90_D_m"]
        coverage = metrics["coverage90_group_mean"]
        lines.append(
            f"| {i} | {a:.2f} | {b:.2f} | {lo:.2f}, {hi:.2f} | {metrics['median_group_contact_error_m']:.2f} | {coverage:.3f} | {summary['plane_sensitivity']['sd_from_plane_perturbation']:.2f} |"
        )
    lines += [
        "",
        "Plane sensitivity is a local training-only perturbation check, not posterior marginalisation.",
        "Single-wall-only horizons supply nuisance-level predictions but no marker contrast.",
        "Trace means use a conservative Gaussian working error, not independent-vertex precision.",
        "Predictive intervals include level and measurement error; plane uncertainty remains outside them.",
        "The geometric ensembles are unweighted feasible families and have no probability interpretation.",
        "600 m is physical prior support. Boundary mass is recorded in every fold summary.",
        "Synthetic parameter truth was not read for fitting or scoring. Analytical recovery is checked separately.",
        "",
        "![Diagnostics](diagnostics.png)",
        "",
        "![Pitch](pitch.png)",
        "",
        "![Withheld contacts](withheld_contacts.png)",
        "",
        "Configuration, input and code hashes, seeds, hardware, evaluation counts and failures are in manifest.json.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def stage_report(outputs, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    settings_path = BASE / "configs" / "simple_sensitivity.json"
    settings = json.loads(settings_path.read_text())
    calibration = analytical_calibration(settings)
    calibration["configuration_sha256"] = digest(settings_path)
    write_json(destination / "calibration.json", calibration)
    records = []
    for output in outputs:
        output = Path(output)
        config = json.loads((output / "configuration.json").read_text())
        manifest = json.loads((output / "manifest.json").read_text())
        if manifest["status"] != "complete_conditional":
            raise ValueError("All five folds must complete before the Gate A report")
        evaluation = json.loads((output / "evaluation.json").read_text())
        summaries = [
            json.loads((output / f"fold_{i}" / "summary.json").read_text()) for i in range(5)
        ]
        records.append(
            {
                "case": config["case"],
                "output": str(output.resolve()),
                "manifest_sha256": digest(output / "manifest.json"),
                "config_sha256": manifest["configuration_sha256"],
                "mean_fold_contact_error_m": evaluation["mean_fold_median_contact_error_m"],
                "D_interval_width_m": float(
                    np.mean([np.diff(s["interval90_D_m"])[0] for s in summaries])
                ),
                "free_dimension": len(summaries[0]["constraints"]["free_parameters"]),
                "all_likelihood_rank_one": all(s["likelihood_rank"] == 1 for s in summaries),
                "all_grids_converged": all(
                    s["numerical"]["status"] == "converged" for s in summaries
                ),
                "missing_predictions": sum(m["missing_count"] for m in evaluation["folds"]),
                "fit_seconds": manifest["elapsed_seconds"],
                "evaluation_seconds": manifest["evaluation_seconds"],
            }
        )
    if {r["case"] for r in records} != {"E0", "E1", "E2"}:
        raise ValueError("Gate A requires exactly the three evidence cases")
    status = (
        "conditional_pass"
        if calibration["status"] == "pass"
        and all(
            r["all_likelihood_rank_one"]
            and r["all_grids_converged"]
            and r["missing_predictions"] == 0
            for r in records
        )
        else "fail"
    )
    write_json(
        destination / "gate_a.json",
        {
            "status": status,
            "runs": records,
            "calibration_status": calibration["status"],
            "uncertainty_claim": "conditional only",
            "full_dataset_uncertainty_calibration": "unperformed",
            "advanced_methods_and_real_survey_gates": "unperformed",
        },
    )
    lines = [
        "# Gate A: first synthetic benchmark",
        "",
        f"Decision: **{status}** for the declared conditional planar model.",
        "",
        "| Case | Free dimensions | Mean fold contact error (m) | Mean D 90% width (m) | Fit seconds |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in records:
        lines.append(
            f"| {r['case']} | {r['free_dimension']} | {r['mean_fold_contact_error_m']:.2f} | {r['D_interval_width_m']:.2f} | {r['fit_seconds']:.2f} |"
        )
    lines += [
        "",
        "E0 retains a rank-one likelihood ridge. E1 removes pitch from the search. E2 restricts the family using an assumed five-degree bound.",
        "The smaller E1/E2 uncertainty reflects additional information. No algorithm speedup is claimed.",
        "",
        "The analytical Gaussian coverage screening is separate from the polar-prior dataset benchmark:",
        "",
        "| Verification problem | Component 90% coverages | Joint coverage | Status |",
        "|---|---|---:|---|",
    ]
    for name, result in calibration["results"].items():
        coverages = ", ".join(f"{c['coverage90']:.3f}" for c in result["components"])
        lines.append(
            f"| {name} | {coverages} | {result['joint90_coverage']:.3f} | {result['status']} |"
        )
    lines += [
        "",
        "Binomial confidence intervals and posterior-rank histograms are saved in calibration.json.",
        "",
        "Limitations: fitted-plane uncertainty is assessed by local sensitivity only. Dataset intervals remain conditional; full uncertainty calibration is unperformed.",
        "The trace-mean error is a conservative working model. Terrain/error linearisation and a z-as-height plane limit the current observation model.",
        "Protocol A01-A07 evidence is in the focused test results recorded by HANDOFF.md. Numerical and data-isolation tests must pass before this decision is used.",
        "Geometric feasible ensembles have no posterior-probability or calibrated-interval claim.",
        "Real surveys, variable slip, reactivation and advanced algorithms are unperformed.",
        "",
        "Next work: Stage B synthetic geology, retaining these conditional uncertainty labels. Full uncertainty claims require explicit plane/nuisance marginalisation and same-model calibration.",
    ]
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    axes[0].bar([r["case"] for r in records], [r["D_interval_width_m"] for r in records])
    axes[0].set(
        ylabel="Mean 90% D interval width (m)", title="Effect of independent expert constraints"
    )
    axes[1].bar([r["case"] for r in records], [r["mean_fold_contact_error_m"] for r in records])
    axes[1].set(ylabel="Mean fold contact error (m)", title="Prediction and recovery are different")
    fig.tight_layout()
    fig.savefig(destination / "constraint_impact.png", dpi=150)
    plt.close(fig)
    print(f"Gate A: {status}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs=3, required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    stage_report(args.runs, args.output)
