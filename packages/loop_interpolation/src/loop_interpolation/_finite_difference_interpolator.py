"""
FiniteDifference interpolator
"""

import numpy as np

from loop_common.math import get_vectors
from ._discrete_interpolator import DiscreteInterpolator
from ._interpolatortype import InterpolatorType
from ._operator import Operator
from scipy.spatial import KDTree
from loop_common.logging import get_logger as getLogger

logger = getLogger(__name__)


def compute_weighting(grid_points, gradient_constraint_points, alpha=10.0, sigma=1.0):
    """
    Compute weights for second derivative regularization based on proximity to gradient constraints.

    Parameters:
        grid_points (ndarray): (N, 3) array of 3D coordinates for grid cells.
        gradient_constraint_points (ndarray): (M, 3) array of 3D coordinates for gradient constraints.
        alpha (float): Strength of weighting increase.
        sigma (float): Decay parameter for Gaussian-like influence.

    Returns:
        weights (ndarray): (N,) array of weights for each grid point.
    """
    # Build a KDTree with the gradient constraint locations
    tree = KDTree(gradient_constraint_points)

    # Find the distance from each grid point to the nearest gradient constraint
    distances, _ = tree.query(grid_points, k=1)

    # Compute weighting function (higher weight for nearby points)
    weights = 1 + alpha * np.exp(-(distances**2) / (2 * sigma**2))

    return weights


class FiniteDifferenceInterpolator(DiscreteInterpolator):
    def __init__(self, grid, data={}):
        """
        Finite difference interpolation on a regular cartesian grid

        Parameters
        ----------
        grid : StructuredGrid
        """
        self.shape = "rectangular"
        DiscreteInterpolator.__init__(self, grid, data=data)
        self.set_interpolation_weights(
            {
                "dxy": 1.0,
                "dyz": 1.0,
                "dxz": 1.0,
                "dxx": 1.0,
                "dyy": 1.0,
                "dzz": 1.0,
                "dx": 1.0,
                "dy": 1.0,
                "dz": 1.0,
                "cpw": 1.0,
                "gpw": 1.0,
                "npw": 1.0,
                "tpw": 1.0,
                "ipw": 1.0,
            }
        )

        self.type = InterpolatorType.FINITE_DIFFERENCE
        self.use_regularisation_weight_scale = False

    def setup_interpolator(self, **kwargs):
        """

        Parameters
        ----------
        kwargs
            possible kwargs are weights for the different masks and masks.

        Notes
        -----
        Default masks are the second derivative in x,y,z direction and the second
        derivative of x wrt y and y wrt z and z wrt x. Custom masks can be used
        by specifying the operator as a 3d numpy array
        e.g. [ [ [ 0 0 0 ]
                 [ 0 1 0 ]
                 [ 0 0 0 ] ]
                 [ [ 1 1 1 ]
                 [ 1 1 1 ]
                 [ 1 1 1 ] ]
                 [ [ 0 0 0 ]
                 [ 0 1 0 ]
                 [ 0 0 0 ] ]

        Returns
        -------

        """
        self.reset()
        regularisation_config = self.resolve_regularisation_config(
            regularisation=kwargs.get("regularisation", None),
            directional_regularisation=kwargs.get("directional_regularisation", None),
        )
        if regularisation_config.isotropic is not None:
            self.interpolation_weights["dxy"] = regularisation_config.isotropic
            self.interpolation_weights["dyz"] = regularisation_config.isotropic
            self.interpolation_weights["dxz"] = regularisation_config.isotropic
            self.interpolation_weights["dxx"] = regularisation_config.isotropic
            self.interpolation_weights["dyy"] = regularisation_config.isotropic
            self.interpolation_weights["dzz"] = regularisation_config.isotropic

        for key in kwargs:
            self.up_to_date = False
            if key in ("regularisation", "directional_regularisation"):
                continue
            self.interpolation_weights[key] = kwargs[key]
        # either use the default operators or the ones passed to the function
        operators = kwargs.get(
            "operators", self.support.get_operators(weights=self.interpolation_weights)
        )

        self.use_regularisation_weight_scale = kwargs.get("use_regularisation_weight_scale", False)
        self.add_norm_constraints(self.interpolation_weights["npw"])
        self.add_gradient_constraints(self.interpolation_weights["gpw"])
        self.add_value_constraints(self.interpolation_weights["cpw"])
        self.add_tangent_constraints(self.interpolation_weights["tpw"])
        self.add_interface_constraints(self.interpolation_weights["ipw"])
        self.add_value_inequality_constraints()
        self.add_inequality_pairs_constraints(
            pairs=kwargs.get("inequality_pairs", None),
            upper_bound=kwargs.get("inequality_pair_upper_bound", np.finfo(float).eps),
            lower_bound=kwargs.get("inequality_pair_lower_bound", -np.inf),
        )
        for k, o in operators.items():
            self.assemble_inner(o[0], o[1], name=k)
        self.add_directional_regularisation(regularisation_config.directional)
        self.assemble_borders()
        return self.finalize_setup_diagnostics_report()

    def copy(self):
        """
        Create a new identical interpolator

        Returns
        -------
        returns a new empy interpolator from the same support
        """
        return FiniteDifferenceInterpolator(self.support)

    def add_value_constraints(self, w=1.0):
        """

        Parameters
        ----------
        w : double or numpy array

        Returns
        -------

        """

        points = self.get_value_constraints()
        # check that we have added some points
        if points.shape[0] > 0:
            node_idx, inside = self.support.position_to_cell_corners(
                points[:, : self.support.dimension]
            )
            # print(points[inside,:].shape)
            gi = np.zeros(self.support.n_nodes, dtype=int)
            gi[:] = -1
            gi[self.region] = np.arange(0, self.dof, dtype=int)
            idc = np.zeros(node_idx.shape)
            idc[:] = -1
            idc[inside, :] = gi[node_idx[inside, :]]
            inside = np.logical_and(~np.any(idc == -1, axis=1), inside)
            a = self.support.position_to_dof_coefs(points[inside, : self.support.dimension])
            # a *= w
            # a/=self.support.enp.product(self.support.step_vector)
            self.add_constraints_to_least_squares(
                a,
                points[inside, self.support.dimension],
                idc[inside, :],
                w=w * points[inside, self.support.dimension + 1],
                name="value",
            )
            if np.sum(inside) <= 0:
                logger.warning(
                    f"{np.sum(~inside)} \
                        value constraints not added: outside of model bounding box"
                )

    def add_interface_constraints(self, w=1.0):
        """
        Adds a constraint that defines all points
        with the same 'id' to be the same value
        Sets all P1-P2 = 0 for all pairs of points

        Parameters
        ----------
        w : double
            weight

        Returns
        -------

        """
        # get elements for points
        points = self.get_interface_constraints()
        if points.shape[0] > 1:
            node_idx, inside = self.support.position_to_cell_corners(
                points[:, : self.support.dimension]
            )
            gi = np.zeros(self.support.n_nodes, dtype=int)
            gi[:] = -1
            gi[self.region] = np.arange(0, self.dof, dtype=int)
            idc = np.zeros(node_idx.shape).astype(int)
            idc[:] = -1
            idc[inside, :] = gi[node_idx[inside, :]]
            inside = np.logical_and(~np.any(idc == -1, axis=1), inside)
            idc = idc[inside, :]
            A = self.support.position_to_dof_coefs(points[inside, : self.support.dimension])
            for unique_id in np.unique(
                points[
                    np.logical_and(~np.isnan(points[:, self.support.dimension]), inside),
                    self.support.dimension,
                ]
            ):
                mask = points[inside, self.support.dimension] == unique_id
                ij = np.array(
                    np.meshgrid(
                        np.arange(0, A[mask, :].shape[0]),
                        np.arange(0, A[mask, :].shape[0]),
                    )
                ).T.reshape(-1, 2)
                interface_A = np.hstack([A[mask, :][ij[:, 0], :], -A[mask, :][ij[:, 1], :]])
                interface_idc = np.hstack([idc[mask, :][ij[:, 0], :], idc[mask, :][ij[:, 1], :]])
                # now map the index from global to region create array size of mesh
                # initialise as np.nan, then map points inside region to 0->dof
                gi = np.zeros(self.support.n_nodes).astype(int)
                gi[:] = -1

                gi[self.region] = np.arange(0, self.dof)
                interface_idc = gi[interface_idc]
                outside = ~np.any(interface_idc == -1, axis=1)
                self.add_constraints_to_least_squares(
                    interface_A[outside, :],
                    np.zeros(interface_A[outside, :].shape[0]),
                    interface_idc[outside, :],
                    w=w,
                    name="interface_{}".format(unique_id),
                )

    def add_gradient_constraints(self, w=1.0):
        """

        Parameters
        ----------
        w : double / numpy array

        Returns
        -------

        """

        points = self.get_gradient_constraints()
        if points.shape[0] > 0:
            # calculate unit vector for orientation data

            node_idx, inside = self.support.position_to_cell_corners(
                points[:, : self.support.dimension]
            )
            # calculate unit vector for node gradients
            # this means we are only constraining direction of grad not the
            # magnitude
            gi = np.zeros(self.support.n_nodes)
            gi[:] = -1
            gi[self.region] = np.arange(0, self.dof)
            idc = np.zeros(node_idx.shape)
            idc[:] = -1
            idc[inside, :] = gi[node_idx[inside, :]]
            inside = np.logical_and(~np.any(idc == -1, axis=1), inside)

            (
                vertices,
                T,
                elements,
                inside_,
            ) = self.support.get_element_gradient_for_location(
                points[inside, : self.support.dimension]
            )
            # normalise constraint vector and scale element matrix by this
            norm = np.linalg.norm(
                points[:, self.support.dimension : self.support.dimension + self.support.dimension],
                axis=1,
            )
            points[:, 3:6] /= norm[:, None]
            T /= norm[inside, None, None]
            # calculate two orthogonal vectors to constraint (strike and dip vector)
            strike_vector, dip_vector = get_vectors(
                points[
                    inside, self.support.dimension : self.support.dimension + self.support.dimension
                ]
            )
            A = np.einsum("ij,ijk->ik", strike_vector.T, T)
            B = np.zeros(points[inside, :].shape[0])
            self.add_constraints_to_least_squares(A, B, idc[inside, :], w=w, name="gradient")
            A = np.einsum("ij,ijk->ik", dip_vector.T, T)
            self.add_constraints_to_least_squares(A, B, idc[inside, :], w=w, name="gradient")
            # self.regularisation_scale += compute_weighting(
            #     self.support.nodes,
            #     points[inside, : self.support.dimension],
            #     sigma=self.support.nsteps[0] * 10,
            # )
            if np.sum(inside) <= 0:
                logger.warning(
                    f" {np.sum(~inside)} \
                        norm constraints not added: outside of model bounding box"
                )

    def add_norm_constraints(self, w=1.0):
        """
        Add constraints to control the norm of the gradient of the scalar field

        Parameters
        ----------
        w : double
            weighting of this constraint (double)

        Returns
        -------

        """
        points = self.get_norm_constraints()
        if points.shape[0] > 0:
            # calculate unit vector for orientation data
            # points[:,3:]/=np.linalg.norm(points[:,3:],axis=1)[:,None]
            node_idx, inside = self.support.position_to_cell_corners(
                points[:, : self.support.dimension]
            )
            gi = np.zeros(self.support.n_nodes)
            gi[:] = -1
            gi[self.region] = np.arange(0, self.dof)
            idc = np.zeros(node_idx.shape)
            idc[:] = -1
            idc[inside, :] = gi[node_idx[inside, :]]
            inside = np.logical_and(~np.any(idc == -1, axis=1), inside)

            # calculate unit vector for node gradients
            # this means we are only constraining direction of grad not the
            # magnitude
            (
                vertices,
                T,
                elements,
                inside_,
            ) = self.support.get_element_gradient_for_location(
                points[inside, : self.support.dimension]
            )
            # T*=np.product(self.support.step_vector)
            # T/=self.support.step_vector[0]
            # indexes, inside2 = self.support.position_to_nearby_cell_indexes(
            # points[inside, : self.support.dimension]
            # )
            # indexes = indexes[inside2, :]

            # corners = self.support.cell_corner_indexes(indexes)
            # node_indexes = corners.reshape(-1, 3)
            # indexes = self.support.global_node_indices(indexes)
            # self.regularisation_scale[indexes]  =10

            self.regularisation_scale += compute_weighting(
                self.support.nodes,
                points[inside, : self.support.dimension],
                sigma=self.support.nsteps[0] * 10,
            )
            # global_indexes = self.support.neighbour_global_indexes().T.astype(int)
            # close_indexes =
            # self.regularisation_scale[global_indexes[idc[inside,:].astype(int),]]=10
            w /= 3
            for d in range(self.support.dimension):
                self.add_constraints_to_least_squares(
                    T[:, d, :],
                    points[inside, self.support.dimension + d],
                    idc[inside, :],
                    w=w,
                    name=f"norm_{d}",
                )

            if np.sum(inside) <= 0:
                logger.warning(
                    f"{np.sum(~inside)} \
                        norm constraints not added: outside of model bounding box"
                )
            self.up_to_date = False

    def add_gradient_orthogonal_constraints(
        self,
        points: np.ndarray,
        vectors: np.ndarray,
        w: float = 1.0,
        b: float = 0,
        name="gradient orthogonal",
    ):
        """
        constraints scalar field to be orthogonal to a given vector

        Parameters
        ----------
        points : np.darray
            location to add gradient orthogonal constraint
        vector : np.darray
            vector to be orthogonal to, should be the same shape as points
        w : double
        B : np.array

        Returns
        -------

        """
        if points.shape[0] > 0:
            # calculate unit vector for orientation data
            node_idx, inside = self.support.position_to_cell_corners(
                points[:, : self.support.dimension]
            )
            # calculate unit vector for node gradients
            # this means we are only constraining direction of grad not the
            # magnitude
            gi = np.zeros(self.support.n_nodes)
            gi[:] = -1
            gi[self.region] = np.arange(0, self.dof)
            idc = np.zeros(node_idx.shape)
            idc[:] = -1

            idc[inside, :] = gi[node_idx[inside, :]]
            inside = np.logical_and(~np.any(idc == -1, axis=1), inside)
            # normalise vector and scale element gradient matrix by norm as well
            norm = np.linalg.norm(vectors, axis=1)
            vectors[norm > 0, :] /= norm[norm > 0, None]

            # normalise element vector to unit vector for dot product
            (
                vertices,
                T,
                elements,
                inside_,
            ) = self.support.get_element_gradient_for_location(
                points[inside, : self.support.dimension]
            )
            # norm_inside indexes norm over the inside-filtered subset so
            # the boolean mask aligns with T (shape n_inside x ...).
            norm_inside = norm[inside]
            T[norm_inside > 0, :, :] /= norm_inside[norm_inside > 0, None, None]

            # dot product of vector and element gradient = 0
            A = np.einsum("ij,ijk->ik", vectors[inside, : self.support.dimension], T)
            b_ = np.zeros(np.sum(inside)) + b
            self.add_constraints_to_least_squares(A, b_, idc[inside, :], w=w, name=name)

            if np.sum(inside) <= 0:
                logger.warning(
                    f"{np.sum(~inside)} \
                        gradient constraints not added: outside of model bounding box"
                )
            self.up_to_date = False

    def _full_neighbour_mask(self):
        if self.support.dimension == 2:
            return np.array([[-1, 0, 1, -1, 0, 1, -1, 0, 1], [1, 1, 1, 0, 0, 0, -1, -1, -1]])
        return np.array(
            [
                [
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                    -1,
                    0,
                    1,
                ],
                [
                    -1,
                    -1,
                    -1,
                    0,
                    0,
                    0,
                    1,
                    1,
                    1,
                    -1,
                    -1,
                    -1,
                    0,
                    0,
                    0,
                    1,
                    1,
                    1,
                    -1,
                    -1,
                    -1,
                    0,
                    0,
                    0,
                    1,
                    1,
                    1,
                ],
                [
                    -1,
                    -1,
                    -1,
                    -1,
                    -1,
                    -1,
                    -1,
                    -1,
                    -1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                ],
            ]
        )

    def _boundary_indexes(self, axis, upper=False):
        if self.support.nsteps[axis] < 3:
            return None
        indexes = self.support.global_index_to_node_index(np.arange(self.support.n_nodes))
        boundary_index = self.support.nsteps[axis] - 2 if upper else 1
        return indexes[indexes[:, axis] == boundary_index, :].T

    def _assemble_operator(self, operator, w, name="regularisation", indexes=None):
        active = operator.flatten() != 0
        if not np.any(active):
            return

        full_mask = self._full_neighbour_mask()
        active_mask = full_mask[:, active]
        operator_values = operator.flatten()[active]

        neighbour_kwargs = {"mask": active_mask}
        if indexes is not None:
            neighbour_kwargs["indexes"] = indexes
        global_indexes = self.support.neighbour_global_indexes(**neighbour_kwargs)
        if global_indexes is None or global_indexes.size == 0:
            return

        centre_kwargs = {"mask": np.zeros((self.support.dimension, 1), dtype=int)}
        if indexes is not None:
            centre_kwargs["indexes"] = indexes
        centre_indexes = self.support.neighbour_global_indexes(**centre_kwargs)

        a = np.tile(operator_values, (global_indexes.shape[1], 1))
        idc = global_indexes.T

        gi = np.zeros(self.support.n_nodes, dtype=int)
        gi[:] = -1
        gi[self.region] = np.arange(0, self.dof, dtype=int)
        idc = gi[idc]
        centre_idc = gi[centre_indexes.T[:, 0]]
        inside = np.logical_and(~np.any(idc == -1, axis=1), centre_idc != -1)
        if not np.any(inside):
            return

        B = np.zeros(global_indexes.shape[1])
        self.add_constraints_to_least_squares(
            a[inside, :],
            B[inside],
            idc[inside, :],
            w=(self.regularisation_scale[centre_idc[inside].astype(int)] * w)
            if self.use_regularisation_weight_scale
            else w,
            name=name,
        )

    def assemble_borders(self):
        operators = []
        if self.support.dimension == 2:
            operators = [
                (
                    Operator.Dx_forward_mask[1, :, :],
                    self.interpolation_weights["dx"],
                    "dx_lower",
                    self._boundary_indexes(0, upper=False),
                ),
                (
                    Operator.Dx_backward_mask[1, :, :],
                    self.interpolation_weights["dx"],
                    "dx_upper",
                    self._boundary_indexes(0, upper=True),
                ),
                (
                    Operator.Dy_forward_mask[1, :, :],
                    self.interpolation_weights["dy"],
                    "dy_lower",
                    self._boundary_indexes(1, upper=False),
                ),
                (
                    Operator.Dy_backward_mask[1, :, :],
                    self.interpolation_weights["dy"],
                    "dy_upper",
                    self._boundary_indexes(1, upper=True),
                ),
            ]
        else:
            operators = [
                (
                    Operator.Dx_forward_mask,
                    self.interpolation_weights["dx"],
                    "dx_lower",
                    self._boundary_indexes(0, upper=False),
                ),
                (
                    Operator.Dx_backward_mask,
                    self.interpolation_weights["dx"],
                    "dx_upper",
                    self._boundary_indexes(0, upper=True),
                ),
                (
                    Operator.Dy_forward_mask,
                    self.interpolation_weights["dy"],
                    "dy_lower",
                    self._boundary_indexes(1, upper=False),
                ),
                (
                    Operator.Dy_backward_mask,
                    self.interpolation_weights["dy"],
                    "dy_upper",
                    self._boundary_indexes(1, upper=True),
                ),
                (
                    Operator.Dz_forward_mask,
                    self.interpolation_weights["dz"],
                    "dz_lower",
                    self._boundary_indexes(2, upper=False),
                ),
                (
                    Operator.Dz_backward_mask,
                    self.interpolation_weights["dz"],
                    "dz_upper",
                    self._boundary_indexes(2, upper=True),
                ),
            ]

        for operator, weight, name, indexes in operators:
            if weight == 0 or indexes is None or indexes.shape[1] == 0:
                continue
            self._assemble_operator(operator, weight, name=name, indexes=indexes)

    def assemble_inner(self, operator, w, name="regularisation"):
        """

        Parameters
        ----------
        operator : Operator mask (ndarray) or None for rectilinear grids
        w : double

        Returns
        -------

        """
        if operator is None:
            # Rectilinear grid: operator rows are built from the grid itself
            # using the operator name as a hint for which derivative to assemble.
            self._assemble_rectilinear_operator(name, w)
            return
        self._assemble_operator(operator, w, name=name)
        return

    def _assemble_rectilinear_operator(self, name: str, w: float):
        """Assemble a scaled FD regularisation operator for a rectilinear grid.

        Parameters
        ----------
        name : str
            Operator name, e.g. 'dxx', 'dyy', 'dzz', 'dxy', 'dyz', 'dxz'.
        w : float
            Weight applied to every row.
        """
        axis_map = {
            "dxx": (0, -1),
            "dyy": (1, -1),
            "dzz": (2, -1),
            "dxy": (0, 1),
            "dxz": (0, 2),
            "dyz": (1, 2),
        }
        if name not in axis_map:
            logger.warning(f"Unknown rectilinear operator name '{name}', skipping.")
            return
        axis, cross = axis_map[name]
        A_values, col_global, row_global = self.support.build_scaled_operator_rows(axis, cross)

        gi = np.full(self.support.n_nodes, -1, dtype=int)
        gi[self.region] = np.arange(self.dof, dtype=int)

        idc = gi[col_global]  # map to DOF indices
        centre_dof = gi[row_global]

        inside = np.logical_and(~np.any(idc == -1, axis=1), centre_dof != -1)
        if not np.any(inside):
            return

        B = np.zeros(np.sum(inside))
        row_w = (
            self.regularisation_scale[centre_dof[inside].astype(int)] * w
            if self.use_regularisation_weight_scale
            else w
        )
        self.add_constraints_to_least_squares(
            A_values[inside, :],
            B,
            idc[inside, :],
            w=row_w,
            name=name,
        )

    def minimise_directional_gradient_change(
        self,
        w: float,
        vector: np.ndarray,
        name: str = "directional regularisation",
    ):
        """
        Anisotropic regularisation that penalises the directional second
        derivative ``(v·∇)²f = 0`` at each interior grid node.

        This is the finite-difference analogue of the P1
        ``minimise_edge_jumps`` with a direction vector.  For a given
        direction field ``v = (vx, vy, vz)`` sampled at every grid node, the
        constraint at each interior node is

        .. math::

            v_x^2 f_{xx} + v_y^2 f_{yy} + v_z^2 f_{zz}
            + 2 v_x v_y f_{xy} + 2 v_x v_z f_{xz} + 2 v_y v_z f_{yz} = 0

        The six second-derivative operators are each weighted by the
        corresponding squared direction component so the regularisation is
        strong along ``v`` and weak across it.

        Parameters
        ----------
        w : float
            Base regularisation weight.
        vector : np.ndarray, shape (n_nodes, 3)
            Direction field evaluated at every grid node
            (``self.support.nodes``).  Typically the fold normal, fold axis,
            or deformed-orientation vector returned by
            ``FoldEvent.get_deformed_orientation``.
        name : str
            Label stored with these constraints.
        """
        if vector is None or vector.ndim != 2 or vector.shape != (self.support.n_nodes, 3):
            logger.warning(
                f"{name}: vector must have shape ({self.support.n_nodes}, 3), "
                f"got {None if vector is None else vector.shape}.  Skipping."
            )
            return

        has_scaled_rows = hasattr(self.support, "build_scaled_operator_rows")

        # Map global node indices to DOF indices for the active region.
        gi = np.full(self.support.n_nodes, -1, dtype=int)
        gi[self.region] = np.arange(self.dof, dtype=int)

        # Six second-derivative operator types and the matching direction-
        # weight formula.  For RectilinearGrid we use build_scaled_operator_rows
        # which gives per-node stencil coefficients scaled by the local spacing.
        # For StructuredGrid (uniform spacing) we use the fixed Operator masks via
        # neighbour_global_indexes, which mirrors how _assemble_operator works.
        axis_map = {
            "dxx": (0, -1),
            "dyy": (1, -1),
            "dzz": (2, -1),
            "dxy": (0, 1),
            "dxz": (0, 2),
            "dyz": (1, 2),
        }
        # Operator masks for the mask-based path (StructuredGrid).
        op_masks = {
            "dxx": Operator.Dxx_mask,
            "dyy": Operator.Dyy_mask,
            "dzz": Operator.Dzz_mask,
            "dxy": Operator.Dxy_mask,
            "dxz": Operator.Dxz_mask,
            "dyz": Operator.Dyz_mask,
        }

        for op_key, (ax, cx) in axis_map.items():
            if has_scaled_rows:
                # --- RectilinearGrid path: per-node scaled stencil rows -------
                A_values, col_global, row_nodes = self.support.build_scaled_operator_rows(ax, cx)
                idc = gi[col_global]
                centre_dof = gi[row_nodes]
                inside = np.logical_and(~np.any(idc == -1, axis=1), centre_dof != -1)
                if not np.any(inside):
                    continue
            else:
                # --- StructuredGrid path: fixed stencil mask ------------------
                operator = op_masks[op_key]
                active = operator.flatten() != 0
                if not np.any(active):
                    continue
                full_mask = self._full_neighbour_mask()
                active_mask = full_mask[:, active]
                operator_values = operator.flatten()[active]

                global_indexes = self.support.neighbour_global_indexes(mask=active_mask)
                if global_indexes is None or global_indexes.size == 0:
                    continue
                centre_indexes = self.support.neighbour_global_indexes(
                    mask=np.zeros((self.support.dimension, 1), dtype=int)
                )
                col_global = global_indexes
                row_nodes = centre_indexes.T[:, 0]  # global index of each interior centre node
                A_values = np.tile(operator_values, (col_global.shape[1], 1))
                idc = gi[col_global.T]
                centre_dof = gi[row_nodes]
                inside = np.logical_and(~np.any(idc == -1, axis=1), centre_dof != -1)
                if not np.any(inside):
                    continue

            # Direction-component weight for this operator type.
            vx = vector[row_nodes[inside], 0]
            vy = vector[row_nodes[inside], 1]
            vz = vector[row_nodes[inside], 2]
            if op_key == "dxx":
                comp_w = vx**2
            elif op_key == "dyy":
                comp_w = vy**2
            elif op_key == "dzz":
                comp_w = vz**2
            elif op_key == "dxy":
                comp_w = 2.0 * vx * vy
            elif op_key == "dxz":
                comp_w = 2.0 * vx * vz
            else:  # dyz
                comp_w = 2.0 * vy * vz

            row_w = w * comp_w
            # Skip rows where the direction weight is effectively zero.
            nonzero = np.abs(row_w) > 0.0
            if not np.any(nonzero):
                continue

            B = np.zeros(np.sum(nonzero))
            self.add_constraints_to_least_squares(
                A_values[inside][nonzero],
                B,
                idc[inside][nonzero],
                w=row_w[nonzero],
                name=f"{name}_{op_key}",
            )

    def get_regularisation_sample_points(self) -> np.ndarray:
        return self.support.nodes

    def _add_directional_regularisation(
        self,
        weight: float,
        vectors: np.ndarray,
        name: str = "directional regularisation",
    ):
        self.minimise_directional_gradient_change(weight, vectors, name=name)
