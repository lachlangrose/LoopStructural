"""Four-way FDI fold-constraint/gradient-normalised smoothness experiment.

This adds an explicit geological direction prior to the existing two-contact
example. It does not change production FDI. All derivative rows for the fold
orientation, axis and signed normalisation come from the same FDI helper used
by FDFoldInterpolator. The prior is prescribed, not fitted to any result.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy import sparse

from .._finite_difference_interpolator import FiniteDifferenceInterpolator
from .benchmark_two_contacts import TwoContactExperiment, evaluate, upper_contact


def geological_directions(local: np.ndarray, reference: float) -> tuple:
    """Prescribed flat-to-folded bedding and two normalisation target choices.

    Below level zero bedding is horizontal. Between contacts the slope grows
    with fractional height. Above the unit contact the V-shaped direction
    pattern continues unchanged with height. Axis is local y, dgz is local +z.
    The optional spacing target is piecewise compatible with this direction
    field; the primary target is the existing constant projection convention.
    """
    x, _, z = local.T
    upper = upper_contact(x)
    gap = upper + 0.25
    slope = 1.9 * x / 0.35**2 * np.exp(-((x / 0.35) ** 2))
    phase = (z + 0.25) / gap
    tangent = np.column_stack([np.ones(len(x)), np.zeros(len(x)), np.clip(phase, 0, 1) * slope])
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    axis = np.tile([0.0, 1.0, 0.0], (len(x), 1))
    across = np.tile([0.0, 0.0, 1.0], (len(x), 1))
    target = np.where((phase >= 0) & (phase <= 1), 1 / gap, reference)
    return tangent, axis, across, target


class FoldConstraintExperiment(TwoContactExperiment):
    """Same physical FDI regulariser with an optional common linear fold loss."""

    def __init__(
        self, cells: int, angle: float = 0.0, fold_mode: str = 'constant', fold_gain: float = 1.0
    ) -> None:
        super().__init__(cells, angle)
        if fold_mode not in ('none', 'directions', 'constant', 'spacing'):
            raise ValueError('Unknown fold constraint mode')
        self.fold_mode, self.fold_gain = fold_mode, fold_gain
        self.contact_matrix = self.data_matrix.copy()
        self.contact_target = self.data_target.copy()
        h = 8 / cells
        xx, zz = np.meshgrid(
            -4 + (np.arange(cells) + 0.5) * h, -4 + (np.arange(cells) + 0.5) * h, indexing='ij'
        )
        self.fold_points = np.column_stack([xx.ravel(), np.zeros(xx.size), zz.ravel()])
        # These are world-grid cell centres. Convert to local geometry before
        # evaluating the common fold prior, then rotate its vectors back.
        local = self.fold_points @ self.rotation
        tangent, axis, across, spacing_target = geological_directions(
            local, self.gradient_reference
        )
        self.fold_vectors = {
            'fold orientation': tangent @ self.rotation.T,
            'fold axis': axis @ self.rotation.T,
            'fold normalisation': across @ self.rotation.T,
        }
        self.fold_projection_target = (
            spacing_target
            if fold_mode == 'spacing'
            else np.full(len(local), self.gradient_reference)
        )
        self.fold_quadrature = np.full(len(local), h * h)  # exact unit-thickness extrusion
        self.fold_blocks = {}
        if fold_mode == 'none':
            return
        assembler = FiniteDifferenceInterpolator(self.grid)
        assembler.reset()
        _, gradients, _, inside = self.grid.get_element_gradient_for_location(self.fold_points)
        if not np.all(inside):
            raise ValueError('Fold quadrature points must lie inside the support')
        # Coefficients here multiply energies. FDI's w multiplies residuals.
        coefficients = {'fold orientation': 0.1, 'fold axis': 0.1, 'fold normalisation': 0.01}
        families = (
            ('fold orientation', 'fold axis') if fold_mode == 'directions' else tuple(coefficients)
        )
        matrices, targets = [self.contact_matrix], [self.contact_target]
        for name in families:
            vectors = self.fold_vectors[name]
            target = (
                self.fold_projection_target
                if name == 'fold normalisation'
                else np.zeros(len(local))
            )
            assembler.add_gradient_orthogonal_constraints(
                self.fold_points,
                vectors.copy(),
                w=1.0,
                b=target,
                name=name,
            )
            block = assembler.constraints[name]
            # Undo FDI's numerical row normalisation, retaining its actual
            # physical trilinear derivative rows. Then apply area quadrature
            # and confidence. This makes the fold loss independent of node
            # count and avoids changing the target when its weight changes.
            raw = np.einsum('ij,ijk->ik', vectors, gradients)
            row_norm = np.linalg.norm(raw, axis=1)
            row_weight = row_norm * np.sqrt(self.fold_quadrature * coefficients[name] * fold_gain)
            matrix = sparse.diags(row_weight) @ block['matrix']
            rhs = row_weight * block['b']
            self.fold_blocks[name] = (matrix.tocsr(), rhs)
            matrices.append(matrix)
            targets.append(rhs)
        self.data_matrix = sparse.vstack(matrices, format='csr')
        self.data_target = np.concatenate(targets)

    def fold_diagnostics(self, values: np.ndarray) -> dict:
        gradient = self.grid.evaluate_gradient(self.fold_points, values)
        q = np.linalg.norm(gradient, axis=1)
        tangent = np.sum(gradient * self.fold_vectors['fold orientation'], axis=1)
        projection = np.sum(gradient * self.fold_vectors['fold normalisation'], axis=1)
        angle = np.rad2deg(np.arcsin(np.clip(np.abs(tangent) / np.maximum(q, 1e-15), 0, 1)))
        fold_energy = sum(
            float(np.sum((m @ values - b) ** 2)) for m, b in self.fold_blocks.values()
        )
        contact = self.contact_matrix @ values - self.contact_target
        return dict(
            fold_quadrature_q_min=float(np.min(q)),
            fold_quadrature_q_max=float(np.max(q)),
            fold_quadrature_q_below_epsilon_fraction=float(
                np.mean(q < 0.03 * self.gradient_reference)
            ),
            fold_tangent_derivative_rms=float(np.sqrt(np.mean(tangent * tangent))),
            fold_orientation_angle_mean_deg=float(np.mean(angle)),
            fold_projection_rms=float(
                np.sqrt(np.mean((projection - self.fold_projection_target) ** 2))
            ),
            fold_energy=fold_energy,
            contact_energy=float(contact @ contact),
        )


def layer_roots(
    problem: FoldConstraintExperiment, values: np.ndarray, x: np.ndarray, level: float
) -> tuple:
    """Count all vertical crossings and select the one nearest the stated prior."""
    z = np.linspace(-3.8, 3.8, 501)
    xx, zz = np.meshgrid(x, z, indexing='ij')
    query = problem.world(xx.ravel(), zz.ravel())
    valid = problem.grid.inside(query).reshape(xx.shape)
    safe = np.clip(query, problem.grid.origin + 1e-9, problem.grid.maximum - 1e-9)
    field = problem.grid.evaluate_value(safe, values).reshape(xx.shape) - level
    crossings = ((field[:, :-1] < 0) != (field[:, 1:] < 0)) & valid[:, :-1] & valid[:, 1:]
    count = crossings.sum(axis=1)
    target = (
        np.full(len(x), -0.25)
        if level == 0
        else upper_contact(x) + (level - 1) / problem.gradient_reference
    )
    centre = (z[:-1] + z[1:]) / 2
    which = np.argmin(np.where(crossings, abs(centre[None, :] - target[:, None]), np.inf), axis=1)
    lo, hi = z[which].copy(), z[which + 1].copy()
    flo = field[np.arange(len(x)), which].copy()
    for _ in range(30):
        mid = (lo + hi) / 2
        query = np.clip(
            problem.world(x, mid), problem.grid.origin + 1e-9, problem.grid.maximum - 1e-9
        )
        fmid = problem.grid.evaluate_value(query, values) - level
        same = flo * fmid > 0
        lo, hi = np.where(same, mid, lo), np.where(same, hi, mid)
        flo = np.where(same, fmid, flo)
    root = (lo + hi) / 2
    root[count == 0] = np.nan
    return root, count


def spacing_diagnostics(
    x: np.ndarray, levels: np.ndarray, roots: np.ndarray, counts: np.ndarray
) -> dict:
    """Compare the same level-1 to level-2 interval and x-window for every field."""
    lower = int(np.flatnonzero(levels == 1)[0])
    upper = int(np.flatnonzero(levels == 2)[0])
    window = abs(x) <= 1
    valid = window & (counts[lower] == 1) & (counts[upper] == 1)
    separation = (roots[upper] - roots[lower])[valid]
    return dict(
        level_1_to_2_vertical_spacing_mean=float(np.mean(separation)) if len(separation) else None,
        level_1_to_2_vertical_spacing_cv=(
            float(np.std(separation) / np.mean(separation)) if len(separation) else None
        ),
        level_1_to_2_vertical_spacing_coverage=float(np.sum(valid) / np.sum(window)),
    )


def curvature_diagnostics(
    x: np.ndarray, levels: np.ndarray, roots: np.ndarray, counts: np.ndarray
) -> dict:
    """Central graph curvature from a fixed quadratic fit, suppressing grid noise.

    Positive is a bowl/V, negative is an arch. Require unique crossings at
    80% of locations in the same [-0.6,0.6] window for every field.
    """
    window = abs(x) <= 0.6
    metrics = {}
    available, reversals = 0, 0
    for index, level in enumerate(levels):
        valid = window & (counts[index] == 1) & np.isfinite(roots[index])
        curvature = None
        if np.sum(valid) >= max(5, 0.8 * np.sum(window)):
            a, b, _ = np.polyfit(x[valid], roots[index, valid], 2)
            curvature = float(2 * a / (1 + b * b) ** 1.5)
            if level > 1:
                available += 1
                reversals += curvature < -0.02
        tag = f'{level:g}'.replace('.', 'p')
        metrics[f'level_{tag}_central_curvature_fit'] = curvature
    metrics['overlying_curvature_assessable_count'] = available
    metrics['overlying_curvature_reversal_count'] = int(reversals)
    return metrics


def evaluate_layers(problem: FoldConstraintExperiment, values: np.ndarray) -> tuple:
    x = np.linspace(-3.5, 3.5, 281)
    levels = np.array([0.0, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0])
    roots, counts = zip(*(layer_roots(problem, values, x, level) for level in levels))
    roots, counts = np.array(roots), np.array(counts)
    positions = [int(np.argmin(abs(x - a))) for a in (0.0, -1.0, 1.0)]
    relief = roots[:, positions[0]] - 0.5 * (roots[:, positions[1]] + roots[:, positions[2]])
    # An absent or ambiguous crossing is not evidence of a good fold shape.
    relief[~np.all(counts[:, positions] == 1, axis=1)] = np.nan
    interval = abs(x) <= 1
    spacing = np.diff(roots[1:], axis=0) / np.diff(levels[1:])[:, None]
    spacing[(counts[1:-1] != 1) | (counts[2:] != 1)] = np.nan
    valid_spacing = spacing[:, interval]
    valid_relief = relief[2:][np.isfinite(relief[2:])]
    finite_spacing = valid_spacing[np.isfinite(valid_spacing)]
    metrics = {}
    for index, level in enumerate(levels):
        tag = f'{level:g}'.replace('.', 'p')
        metrics[f'level_{tag}_relief'] = (
            float(relief[index]) if np.isfinite(relief[index]) else None
        )
        metrics[f'level_{tag}_coverage'] = float(np.mean(counts[index] > 0))
        metrics[f'level_{tag}_multiple_crossing_fraction'] = float(np.mean(counts[index] > 1))
    metrics.update(
        overlying_arch_count=int(np.sum(relief[2:] > 0.02)),
        overlying_arch_assessable_count=len(valid_relief),
        overlying_arch_fraction=float(np.mean(valid_relief > 0.02)) if len(valid_relief) else None,
        overlying_arch_relief_max=(
            float(np.max(np.maximum(valid_relief, 0))) if len(valid_relief) else None
        ),
        overlying_vertical_spacing_mean=(
            float(np.mean(finite_spacing)) if len(finite_spacing) else None
        ),
        overlying_vertical_spacing_cv=(
            float(np.std(finite_spacing) / np.mean(finite_spacing)) if len(finite_spacing) else None
        ),
        overlying_nonpositive_spacing_fraction=(
            float(np.mean(finite_spacing <= 0)) if len(finite_spacing) else None
        ),
        overlying_valid_spacing_fraction=float(np.mean(np.isfinite(valid_spacing))),
    )
    metrics.update(curvature_diagnostics(x, levels, roots, counts))
    metrics.update(spacing_diagnostics(x, levels, roots, counts))
    return metrics, dict(
        layer_x=x,
        layer_levels=levels,
        layer_z=roots,
        layer_crossings=counts,
        layer_relief=relief,
        vertical_spacing_per_isovalue=spacing,
    )


def save_fit(
    problem: FoldConstraintExperiment,
    fit: object,
    method: str,
    strength: float,
    epsilon_ratio: float,
    output: Path,
    rows: list,
    tag: str = 'primary',
    initial: np.ndarray | None = None,
) -> None:
    metrics, samples = evaluate(problem, fit.values)
    layers, layer_samples = evaluate_layers(problem, fit.values)
    label = f'n{problem.grid.nsteps_cells[0]}_a{np.rad2deg(np.arctan2(problem.rotation[0,2],problem.rotation[0,0])):g}_{problem.fold_mode}_g{problem.fold_gain:g}_l{strength:g}_{method}_eps{epsilon_ratio:g}_{tag}'
    relative = Path('samples') / f'{label}.npz'
    np.savez_compressed(output / relative, values=fit.values, **samples, **layer_samples)
    result = asdict(fit)
    result.pop('values')
    if initial is not None:
        result['initial_objective'] = problem.energy_gradient(
            initial, strength, epsilon_ratio * problem.gradient_reference
        )[0]
    row = dict(
        cells=int(problem.grid.nsteps_cells[0]),
        angle=float(np.rad2deg(np.arctan2(problem.rotation[0, 2], problem.rotation[0, 0]))),
        fold_mode=problem.fold_mode,
        fold_gain=problem.fold_gain,
        method=method,
        strength=strength,
        epsilon_ratio=epsilon_ratio,
        tag=tag,
        samples=relative.as_posix(),
        first_order_1e6=fit.optimality < 1e-6,
        **result,
        **metrics,
        **layers,
        **problem.fold_diagnostics(fit.values),
    )
    rows.append(row)
    (output / 'metrics.json').write_text(json.dumps(rows, indent=2, allow_nan=False) + '\n')
    print(
        f'{label}: contact={metrics["contact_rms"]:.4g}, level2 relief={layers["level_2_relief"]}, arches={layers["overlying_arch_count"]}, grad={fit.optimality:.2g}, success={fit.success}, {fit.runtime:.2f}s',
        flush=True,
    )


def plot_results(rows: list, output: Path, config: dict) -> None:
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from matplotlib.lines import Line2D

    cells = max(config['resolutions'])
    modes = ('none', 'constant')
    methods = ('baseline', 'normalised')
    titles = {'baseline': 'Ordinary Hessian', 'normalised': 'Gradient-normalised Hessian'}
    colours = {
        ('none', 'baseline'): '#2467a8',
        ('none', 'normalised'): '#d56725',
        ('constant', 'baseline'): '#2a9365',
        ('constant', 'normalised'): '#9251a7',
    }
    # Show the input geological assumption independently of reconstructed
    # fields. It must not be mistaken for extra observed isosurfaces.
    px, pz = np.meshgrid(np.linspace(-1.3, 1.3, 23), np.linspace(-0.75, 2.8, 22))
    local = np.column_stack([px.ravel(), np.zeros(px.size), pz.ravel()])
    tangent, _, _, target = geological_directions(
        local, 1 / np.median(upper_contact(np.linspace(-1, 1, 21)) + 0.25)
    )
    fig, axes = plt.subplots(1, 2, figsize=(8, 6), sharex=True, sharey=True, layout='constrained')
    axes[0].quiver(
        px,
        pz,
        tangent[:, 0].reshape(px.shape),
        tangent[:, 2].reshape(px.shape),
        pivot='mid',
        scale=25,
        width=0.003,
        color='#44566c',
    )
    image = axes[1].pcolormesh(
        px, pz, target.reshape(px.shape), shading='nearest', cmap='viridis', vmin=0.7, vmax=2.5
    )
    for ax in axes:
        x = np.linspace(-1, 1, 101)
        ax.plot(x, np.full_like(x, -0.25), color='#cfab00', lw=2)
        ax.plot(x, upper_contact(x), color='#a34f9d', lw=2)
        ax.set(xlabel='local x', ylabel='local z', aspect='equal')
    axes[0].set_title('Prescribed bedding directions\nSame for both regularisers')
    axes[1].set_title('Variable projection target\nSensitivity check only')
    fig.colorbar(image, ax=axes[1], shrink=0.8, label='Target vertical derivative')
    fig.suptitle(
        'Input prior: flat below zero, V-shaped directions above one\nPrimary projection target is constant 0.8153; arrows are model assumptions, not observations',
        fontsize=10,
    )
    fig.savefig(output / 'fold_direction_prior.png', dpi=170)
    plt.close(fig)
    for angle in config['angles']:
        chosen = [
            r
            for r in rows
            if r['tag'] == 'primary'
            and r['cells'] == cells
            and abs(r['angle'] - angle) < 1e-8
            and r['strength'] == 0.001
            and r['epsilon_ratio'] == 0.03
        ]
        if len(chosen) != 4:
            continue
        problem = FoldConstraintExperiment(cells, angle, 'none')
        xx, zz = np.meshgrid(
            np.linspace(-4 + 1e-8, 4 - 1e-8, 361), np.linspace(-4 + 1e-8, 4 - 1e-8, 361)
        )
        query = problem.world(xx.ravel(), zz.ravel())
        inside = problem.grid.inside(query).reshape(xx.shape)
        safe = np.clip(query, problem.grid.origin + 1e-8, problem.grid.maximum - 1e-8)
        fig, axes = plt.subplots(
            2, 2, figsize=(11, 10.4), sharex=True, sharey=True, layout='constrained'
        )
        for i, mode in enumerate(modes):
            for j, method in enumerate(methods):
                row = next(r for r in chosen if r['fold_mode'] == mode and r['method'] == method)
                values = np.load(output / row['samples'])['values']
                field = problem.grid.evaluate_value(safe, values).reshape(xx.shape)
                q = np.linalg.norm(problem.grid.evaluate_gradient(safe, values), axis=1).reshape(
                    xx.shape
                )
                field[~inside], q[~inside] = np.nan, np.nan
                ax = axes[i, j]
                image = ax.pcolormesh(
                    xx,
                    zz,
                    q,
                    cmap='viridis',
                    norm=LogNorm(0.05, 5),
                    shading='nearest',
                    rasterized=True,
                )
                contours = ax.contour(
                    xx,
                    zz,
                    field,
                    levels=[-2, -1, 0.25, 0.5, 0.75, 1.25, 1.5, 2, 2.5, 3],
                    colors='#333333',
                    linewidths=0.7,
                )
                ax.clabel(contours, fmt='%g', fontsize=7)
                ax.contour(xx, zz, field, levels=[0], colors='#f4dd35', linewidths=1.8)
                ax.contour(xx, zz, field, levels=[1], colors='#e98af2', linewidths=1.8)
                local = problem.observations[:, :3] @ problem.rotation
                ax.scatter(
                    local[:21, 0],
                    local[:21, 2],
                    c='#f4dd35',
                    edgecolors='black',
                    linewidths=0.25,
                    s=13,
                    zorder=5,
                )
                ax.scatter(
                    local[21:, 0],
                    local[21:, 2],
                    c='#e98af2',
                    edgecolors='black',
                    linewidths=0.25,
                    s=13,
                    zorder=5,
                )
                ax.set(
                    xlim=(-4, 4),
                    ylim=(-4, 4),
                    xlabel='local x',
                    ylabel='local z',
                    aspect='equal',
                    title=f'{titles[method]} | {"no fold constraints" if mode=="none" else "with fold constraints"}\ncontact RMS={row["contact_rms"]:.3g}; level-2 relief={row["level_2_relief"]:+.3f}',
                )
        cb = fig.colorbar(image, ax=axes, shrink=0.8, pad=0.02, extend='min')
        cb.set_label(r'Gradient magnitude $\|\nabla f\|$ (log scale)')
        cb.set_ticks([0.05, 0.1, 0.2, 0.5, 1, 2, 5])
        cb.set_ticklabels(['0.05', '0.1', '0.2', '0.5', '1', '2', '5'])
        fig.suptitle(
            f'Fold constraints x smoothness regulariser | {cells} cells | {angle:g} degrees | lambda=0.001\n'
            'Common fold direction prior; constant signed projection target 0.8153, imposed softly\n'
            'Yellow: level 0 | magenta: level 1 | positive level-2 relief indicates an arch above the V',
            fontsize=11,
        )
        fig.savefig(output / f'four_way_n{cells}_a{angle:g}.png', dpi=170)
        fig.savefig(output / f'four_way_n{cells}_a{angle:g}.svg')
        plt.close(fig)

        fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), layout='constrained')
        for row in chosen:
            data = np.load(output / row['samples'])
            colour = colours[row['fold_mode'], row['method']]
            label = titles[row['method']] + (' + fold' if row['fold_mode'] == 'constant' else '')
            axes[0].plot(
                data['layer_levels'][1:],
                data['layer_relief'][1:],
                marker='o',
                color=colour,
                label=label,
            )
            axes[1].plot(data['layer_x'], data['layer_z'][4] - data['layer_z'][1], color=colour)
            axes[2].plot(data['x'], data['zero'] + 0.25, color=colour)
        axes[0].axhline(0, color='black', lw=0.8)
        axes[2].axhline(0, color='black', lw=0.8)
        axes[0].set(
            xlabel='Isovalue',
            ylabel='Centre height minus shoulder height',
            title='Fold sense: positive = arch, negative = V',
        )
        axes[1].set(
            xlabel='local x',
            ylabel='Vertical separation: levels 1 to 2',
            title='Layer spacing along the fold-normal direction',
        )
        axes[2].set(
            xlabel='local x', ylabel='Departure from z=-0.25', title='Lower zero contact: flatness'
        )
        for ax in axes:
            ax.grid(alpha=0.2)
        handles = [
            Line2D(
                [],
                [],
                color=colours[mode, method],
                label=titles[method] + (' + fold' if mode == 'constant' else ''),
            )
            for mode in modes
            for method in methods
        ]
        fig.legend(handles=handles, loc='outside lower center', ncol=2, fontsize=9, frameon=False)
        fig.suptitle(
            f'Geometric diagnostics | {cells} cells | {angle:g} degrees | same lambda and fold prior',
            fontsize=11,
        )
        fig.savefig(output / f'layer_diagnostics_n{cells}_a{angle:g}.png', dpi=170)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output', type=Path, default=Path('docs/experiments/fold_normalisation_combination')
    )
    parser.add_argument('--resolutions', type=int, nargs='+', default=[32, 48])
    parser.add_argument('--angles', type=float, nargs='+', default=[0, 23])
    parser.add_argument('--strengths', type=float, nargs='+', default=[0.0001, 0.001, 0.01])
    parser.add_argument('--max-evaluations', type=int, default=1000)
    parser.add_argument('--skip-sensitivity', action='store_true')
    parser.add_argument('--plot-only', action='store_true')
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / 'samples').mkdir(exist_ok=True)
    if args.plot_only:
        plot_results(
            json.loads((output / 'metrics.json').read_text()),
            output,
            json.loads((output / 'config.json').read_text()),
        )
        return
    config = {k: v for k, v in vars(args).items() if k not in ('output', 'plot_only')}
    config.update(
        epsilon_ratio=0.03,
        fold_orientation_energy_coefficient=0.1,
        fold_projection_energy_coefficient=0.01,
        fold_projection_target='inverse median observed contact gap = 0.815279297958106',
        fold_direction_prior='flat below zero; height-blended between contacts; V-shaped directions persist above one',
        fold_quadrature='one point per world-grid x/z cell, unit extrusion thickness',
        seed=None,
    )
    (output / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    rows = []
    for cells in args.resolutions:
        for angle in args.angles:
            initial_problem = FoldConstraintExperiment(cells, angle, 'none')
            np.savez_compressed(
                output / 'samples' / f'observations_n{cells}_a{angle:g}.npz',
                contacts=initial_problem.observations,
            )
            for strength in args.strengths:
                native = initial_problem.solve_native(strength)
                for mode in ('none', 'constant'):
                    problem = FoldConstraintExperiment(cells, angle, mode)
                    baseline = problem.solve_baseline(strength)
                    normalised = problem.solve_normalised(
                        native.values, strength, 0.03, args.max_evaluations
                    )
                    save_fit(problem, baseline, 'baseline', strength, 0.03, output, rows)
                    save_fit(
                        problem,
                        normalised,
                        'normalised',
                        strength,
                        0.03,
                        output,
                        rows,
                        initial=native.values,
                    )
                    if (
                        not args.skip_sensitivity
                        and cells == max(args.resolutions)
                        and strength == 0.001
                    ):
                        if mode == 'constant':
                            alternate = problem.solve_normalised(
                                baseline.values, strength, 0.03, args.max_evaluations
                            )
                            save_fit(
                                problem,
                                alternate,
                                'normalised',
                                strength,
                                0.03,
                                output,
                                rows,
                                'baseline_start',
                                baseline.values,
                            )
                        if angle == 0:
                            for eps in (0.01, 0.1):
                                fit = problem.solve_normalised(
                                    native.values, strength, eps, args.max_evaluations
                                )
                                save_fit(
                                    problem,
                                    fit,
                                    'normalised',
                                    strength,
                                    eps,
                                    output,
                                    rows,
                                    'epsilon',
                                    native.values,
                                )
                if (
                    not args.skip_sensitivity
                    and cells == max(args.resolutions)
                    and angle == 0
                    and strength == 0.001
                ):
                    for mode, gain, tag in [
                        ('directions', 1.0, 'direction_only'),
                        ('spacing', 1.0, 'variable_target'),
                        ('constant', 0.25, 'fold_gain'),
                        ('constant', 4.0, 'fold_gain'),
                    ]:
                        problem = FoldConstraintExperiment(cells, angle, mode, gain)
                        baseline = problem.solve_baseline(strength)
                        fit = problem.solve_normalised(
                            native.values, strength, 0.03, args.max_evaluations
                        )
                        save_fit(problem, baseline, 'baseline', strength, 0.03, output, rows, tag)
                        save_fit(
                            problem,
                            fit,
                            'normalised',
                            strength,
                            0.03,
                            output,
                            rows,
                            tag,
                            native.values,
                        )
    keys = sorted(set().union(*(r.keys() for r in rows)) - {'history'})
    with (output / 'metrics.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows({k: r.get(k) for k in keys} for r in rows)
    plot_results(rows, output, config)


if __name__ == '__main__':
    main()
