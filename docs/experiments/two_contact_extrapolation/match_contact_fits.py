"""Match the native and quadratic contact RMS to the middle normalised fit."""

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from loop_interpolation.experimental.benchmark_two_contacts import TwoContactExperiment, evaluate
from scipy.optimize import brentq


def main() -> None:
    """Tune only lambda, retaining all observations and the scientific objectives."""
    output = Path(__file__).resolve().parent
    rows = json.loads((output / 'metrics.json').read_text())
    finest = max(r['cells'] for r in rows)
    references = [
        r
        for r in rows
        if r['cells'] == finest
        and r['method'] == 'normalised'
        and r['strength'] == 0.001
        and r['epsilon_ratio'] == 0.03
        and r['start'] == 'native'
    ]
    matched = []
    for reference in references:
        problem = TwoContactExperiment(finest, reference['angle'])
        target = reference['contact_rms']
        for method in ('native', 'baseline'):
            solve = problem.solve_native if method == 'native' else problem.solve_baseline

            def discrepancy(
                log_strength: float, solve=solve, problem=problem, target=target
            ) -> float:
                fit = solve(float(np.exp(log_strength)))
                residual = (
                    problem.grid.evaluate_value(problem.observations[:, :3], fit.values)
                    - problem.observations[:, 3]
                )
                return float(np.sqrt(np.mean(residual * residual))) - target

            strength = float(np.exp(brentq(discrepancy, np.log(1e-8), np.log(1e4), xtol=1e-9)))
            fit = solve(strength)
            metrics, samples = evaluate(problem, fit.values)
            relative = (
                Path('samples')
                / f'n{finest}_a{reference["angle"]:g}_{method}_contact_fit_matched.npz'
            )
            np.savez_compressed(output / relative, values=fit.values, **samples)
            result = asdict(fit)
            result.pop('values')
            matched.append(
                dict(
                    cells=finest,
                    angle=reference['angle'],
                    strength=strength,
                    method=method,
                    samples=relative.as_posix(),
                    target_contact_rms=target,
                    reference_run=reference['samples'],
                    **result,
                    **metrics,
                )
            )
            print(
                f'{method}, {reference["angle"]:g} degrees: lambda={strength:.6g}, contact={metrics["contact_rms"]:.6g}, zero extrapolation={metrics["zero_extrapolation_rms"]:.6g}',
                flush=True,
            )
    (output / 'matched_contact_metrics.json').write_text(
        json.dumps(matched, indent=2, allow_nan=False) + '\n'
    )


if __name__ == '__main__':
    main()
