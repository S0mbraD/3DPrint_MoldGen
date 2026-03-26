"""Topology Optimization via SIMP (Solid Isotropic Material with Penalisation).

Implements a density-based structural topology optimiser on a regular voxel
grid, minimising compliance (maximising stiffness) subject to a volume
fraction constraint.  This is the same family of algorithms used in
nTopology's topology optimisation workflow.

Algorithm overview
------------------
1. Discretise design domain into N_e voxel elements
2. Each element has a design variable ρ_e ∈ [ρ_min, 1]
3. Material stiffness: E_e = ρ_e^p · E_0  (p = penalisation power, typically 3)
4. Solve K(ρ) · u = f  for displacements
5. Compliance: C = f^T · u = Σ ρ_e^p · u_e^T · k_0 · u_e
6. Sensitivity: ∂C/∂ρ_e = −p · ρ_e^(p−1) · u_e^T · k_0 · u_e
7. Apply density filter (convolution) for mesh-independence
8. Update densities via Optimality Criteria (OC) method
9. Iterate until convergence or max_iter

For a 2D plate (support plate cross-section) we use a 2D version with
4-node bilinear quad elements.  For full 3D, 8-node brick elements.

References
----------
- Bendsøe & Sigmund, "Topology Optimization: Theory, Methods, and
  Applications", Springer, 2003.
- Sigmund, "A 99 line topology optimization code written in Matlab",
  Structural and Multidisciplinary Optimization, 21(2), 120-127, 2001.
- nTopology topology optimization: ntop.com/software/capabilities
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field as dc_field

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.ndimage import convolve

logger = logging.getLogger(__name__)


# ── Element stiffness matrix (2D plane stress) ───────────────────────

def _ke_2d(E: float = 1.0, nu: float = 0.3) -> np.ndarray:
    """8×8 stiffness matrix for a unit-square 4-node bilinear quad
    element under plane stress.  Sigmund (2001) closed-form.
    """
    k = np.array([
        1/2 - nu/6,   1/8 + nu/8,  -1/4 - nu/12, -1/8 + 3*nu/8,
        -1/4 + nu/12, -1/8 - nu/8,   nu/6,         1/8 - 3*nu/8,
    ])
    KE = E / (1 - nu**2) * np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
    ])
    return KE


# ── 3D brick element stiffness ───────────────────────────────────────

def _ke_3d(E: float = 1.0, nu: float = 0.3) -> np.ndarray:
    """24×24 stiffness matrix for a unit-cube 8-node hexahedral brick
    element under 3D elasticity (2-point Gauss quadrature).
    """
    C = E / ((1 + nu) * (1 - 2 * nu)) * np.array([
        [1 - nu, nu, nu, 0, 0, 0],
        [nu, 1 - nu, nu, 0, 0, 0],
        [nu, nu, 1 - nu, 0, 0, 0],
        [0, 0, 0, (1 - 2*nu)/2, 0, 0],
        [0, 0, 0, 0, (1 - 2*nu)/2, 0],
        [0, 0, 0, 0, 0, (1 - 2*nu)/2],
    ])

    gp = 1.0 / math.sqrt(3)
    gauss_pts = np.array([[-gp, -gp, -gp], [gp, -gp, -gp],
                          [-gp, gp, -gp], [gp, gp, -gp],
                          [-gp, -gp, gp], [gp, -gp, gp],
                          [-gp, gp, gp], [gp, gp, gp]])
    KE = np.zeros((24, 24))
    for xi, eta, zeta in gauss_pts:
        dN = _dN_hex8(xi, eta, zeta)  # 3×8
        B = _strain_displacement_3d(dN)  # 6×24
        KE += B.T @ C @ B  # det(J) = 1/8 for unit cube
    KE *= 1.0 / 8.0  # unit cube Jacobian
    return KE


def _dN_hex8(xi: float, eta: float, zeta: float) -> np.ndarray:
    """Shape function derivatives for 8-node hexahedral element.
    Returns (3, 8) matrix of ∂N/∂ξ, ∂N/∂η, ∂N/∂ζ.
    """
    signs = np.array([[-1,-1,-1],[1,-1,-1],[-1,1,-1],[1,1,-1],
                      [-1,-1,1],[1,-1,1],[-1,1,1],[1,1,1]], dtype=float)
    dN = np.zeros((3, 8))
    for i in range(8):
        si, ei, zi = signs[i]
        dN[0, i] = si * (1 + ei*eta) * (1 + zi*zeta) / 8
        dN[1, i] = ei * (1 + si*xi) * (1 + zi*zeta) / 8
        dN[2, i] = zi * (1 + si*xi) * (1 + ei*eta) / 8
    return dN


def _strain_displacement_3d(dN: np.ndarray) -> np.ndarray:
    """Build 6×24 strain-displacement matrix B from shape function derivatives."""
    B = np.zeros((6, 24))
    for i in range(8):
        col = i * 3
        B[0, col]     = dN[0, i]
        B[1, col + 1] = dN[1, i]
        B[2, col + 2] = dN[2, i]
        B[3, col]     = dN[1, i]
        B[3, col + 1] = dN[0, i]
        B[4, col + 1] = dN[2, i]
        B[4, col + 2] = dN[1, i]
        B[5, col]     = dN[2, i]
        B[5, col + 2] = dN[0, i]
    return B


# ── Density filter ────────────────────────────────────────────────────

def _density_filter_kernel(radius: float) -> np.ndarray:
    """Cone-shaped convolution kernel for density filtering (2D)."""
    r = max(1, int(np.ceil(radius)))
    size = 2 * r + 1
    kernel = np.zeros((size, size))
    for i in range(size):
        for j in range(size):
            d = math.sqrt((i - r)**2 + (j - r)**2)
            kernel[i, j] = max(0, radius - d)
    return kernel / kernel.sum()


def _density_filter_kernel_3d(radius: float) -> np.ndarray:
    """Cone-shaped convolution kernel for density filtering (3D)."""
    r = max(1, int(np.ceil(radius)))
    size = 2 * r + 1
    kernel = np.zeros((size, size, size))
    for i in range(size):
        for j in range(size):
            for k in range(size):
                d = math.sqrt((i - r)**2 + (j - r)**2 + (k - r)**2)
                kernel[i, j, k] = max(0, radius - d)
    return kernel / kernel.sum()


# ── 2D SIMP Topology Optimisation ────────────────────────────────────

@dataclass
class TOConfig2D:
    """Configuration for 2D topology optimisation."""
    nelx: int = 60               # elements in x
    nely: int = 30               # elements in y
    volfrac: float = 0.4         # target volume fraction
    penal: float = 3.0           # SIMP penalisation exponent
    rmin: float = 1.5            # filter radius (in elements)
    E0: float = 1.0              # Young's modulus of solid
    Emin: float = 1e-9           # minimum stiffness (void)
    nu: float = 0.3              # Poisson's ratio
    max_iter: int = 50           # maximum iterations
    tol: float = 0.01            # convergence tolerance on density change
    timeout_s: float = 30.0      # wall-clock timeout in seconds
    # Boundary conditions: "cantilever" | "mbb" | "bridge"
    bc_type: str = "cantilever"


@dataclass
class TOResult2D:
    """Result of 2D topology optimisation."""
    density: np.ndarray          # (nely, nelx) optimised density field
    compliance_history: list[float]
    iterations: int
    final_compliance: float
    final_volfrac: float
    config: TOConfig2D


def topology_opt_2d(config: TOConfig2D | None = None) -> TOResult2D:
    """Run 2D SIMP topology optimisation.

    Based on Sigmund's 99-line code, extended with density filtering
    and robust convergence.
    """
    cfg = config or TOConfig2D()
    nelx, nely = cfg.nelx, cfg.nely
    volfrac, penal, rmin = cfg.volfrac, cfg.penal, cfg.rmin
    E0, Emin, nu = cfg.E0, cfg.Emin, cfg.nu

    KE = _ke_2d(1.0, nu)

    # DOF numbering: (nely+1)*(nelx+1) nodes, 2 DOFs each
    ndof = 2 * (nely + 1) * (nelx + 1)

    # Element-to-DOF connectivity
    def _edof(ex: int, ey: int) -> np.ndarray:
        n1 = (nely + 1) * ex + ey
        n2 = (nely + 1) * (ex + 1) + ey
        return np.array([
            2*n1, 2*n1+1, 2*n2, 2*n2+1,
            2*n2+2, 2*n2+3, 2*n1+2, 2*n1+3,
        ])

    # Precompute element DOF indices
    iK = np.zeros(nelx * nely * 64, dtype=int)
    jK = np.zeros_like(iK)
    edof_all = np.zeros((nelx * nely, 8), dtype=int)
    idx = 0
    for ex in range(nelx):
        for ey in range(nely):
            e = ex * nely + ey
            edof = _edof(ex, ey)
            edof_all[e] = edof
            for ii in range(8):
                for jj in range(8):
                    iK[idx] = edof[ii]
                    jK[idx] = edof[jj]
                    idx += 1

    # Loads and BCs
    F = np.zeros(ndof)
    fixed_dofs: np.ndarray

    if cfg.bc_type == "cantilever":
        # Fixed left edge, load at right-middle
        F[2 * (nelx + 1) * (nely + 1) - nely - 1] = -1.0
        fixed_dofs = np.arange(0, 2 * (nely + 1))
    elif cfg.bc_type == "mbb":
        # MBB beam: load top-left, roller bottom-right
        F[1] = -1.0
        fixed_dofs = np.union1d(
            np.arange(0, 2 * (nely + 1), 2),
            np.array([ndof - 1]),
        )
    else:  # bridge
        mid_node = (nelx // 2) * (nely + 1) + nely
        F[2 * mid_node + 1] = -1.0
        left = np.array([2 * nely, 2 * nely + 1])
        right = np.array([2 * (nelx * (nely + 1) + nely), 2 * (nelx * (nely + 1) + nely) + 1])
        fixed_dofs = np.union1d(left, right)

    free_dofs = np.setdiff1d(np.arange(ndof), fixed_dofs)

    # Density filter kernel
    H = _density_filter_kernel(rmin)

    # Initialise densities
    x = np.full((nely, nelx), volfrac)
    xPhys = x.copy()
    compliance_history: list[float] = []
    start_time = time.time()

    for iteration in range(cfg.max_iter):
        if time.time() - start_time > cfg.timeout_s:
            logger.warning("2D TO timed out after %.1fs at iter %d", cfg.timeout_s, iteration)
            break

        # Filtered density
        xPhys = convolve(x, H, mode="reflect")
        xPhys = np.clip(xPhys, 0.0, 1.0)

        # Assemble global stiffness
        sK = np.zeros(nelx * nely * 64)
        for ex in range(nelx):
            for ey in range(nely):
                e = ex * nely + ey
                Ee = Emin + xPhys[ey, ex] ** penal * (E0 - Emin)
                sK[e*64:(e+1)*64] = (Ee * KE).ravel()

        K = sparse.coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()

        # Solve
        u = np.zeros(ndof)
        try:
            K_ff = K[np.ix_(free_dofs, free_dofs)]
            u[free_dofs] = spsolve(K_ff, F[free_dofs])
        except Exception as exc:
            logger.error("2D TO solve failed at iter %d: %s", iteration, exc)
            break

        # Compliance and sensitivity
        ce = np.zeros(nelx * nely)
        for ex in range(nelx):
            for ey in range(nely):
                e = ex * nely + ey
                ue = u[edof_all[e]]
                ce[e] = ue @ KE @ ue

        compliance = float((Emin + xPhys.ravel() ** penal * (E0 - Emin)) @ ce)
        compliance_history.append(compliance)

        dc = -penal * xPhys.ravel() ** (penal - 1) * (E0 - Emin) * ce
        dc = dc.reshape(nely, nelx)

        # Filter sensitivity
        dc = convolve(dc, H, mode="reflect")

        # OC update
        l1, l2, move = 0.0, 1e9, 0.2
        while l2 - l1 > 1e-9:
            lmid = 0.5 * (l1 + l2)
            Bmin = np.maximum(0.0, x - move)
            Bmax = np.minimum(1.0, x + move)
            xnew = np.maximum(Bmin, np.minimum(Bmax,
                x * np.sqrt(np.maximum(1e-12, -dc / lmid))))
            if xnew.mean() > volfrac:
                l1 = lmid
            else:
                l2 = lmid

        change = float(np.max(np.abs(xnew - x)))
        x = xnew.copy()

        if iteration % 10 == 0:
            logger.info("TO iter %d: C=%.4f, Vf=%.4f, Δ=%.4f",
                        iteration, compliance, float(xPhys.mean()), change)

        if change < cfg.tol and iteration > 5:
            logger.info("TO converged at iter %d (Δ=%.6f)", iteration, change)
            break

    xPhys = convolve(x, H, mode="reflect")
    xPhys = np.clip(xPhys, 0.0, 1.0)

    return TOResult2D(
        density=xPhys,
        compliance_history=compliance_history,
        iterations=iteration + 1,
        final_compliance=compliance_history[-1],
        final_volfrac=float(xPhys.mean()),
        config=cfg,
    )


# ── 3D SIMP Topology Optimisation ────────────────────────────────────

@dataclass
class TOConfig3D:
    """Configuration for 3D topology optimisation."""
    nelx: int = 20
    nely: int = 10
    nelz: int = 10
    volfrac: float = 0.3
    penal: float = 3.0
    rmin: float = 1.5
    E0: float = 1.0
    Emin: float = 1e-9
    nu: float = 0.3
    max_iter: int = 30
    tol: float = 0.01
    timeout_s: float = 60.0
    bc_type: str = "cantilever"


@dataclass
class TOResult3D:
    density: np.ndarray          # (nelz, nely, nelx)
    compliance_history: list[float]
    iterations: int
    final_compliance: float
    final_volfrac: float
    config: TOConfig3D


def topology_opt_3d(config: TOConfig3D | None = None) -> TOResult3D:
    """Run 3D SIMP topology optimisation on a voxel grid.

    Uses 8-node hexahedral elements with 2-point Gauss quadrature.
    OC update with density filtering.
    """
    cfg = config or TOConfig3D()
    nelx, nely, nelz = cfg.nelx, cfg.nely, cfg.nelz
    nel = nelx * nely * nelz
    volfrac, penal = cfg.volfrac, cfg.penal

    KE = _ke_3d(1.0, cfg.nu)
    nke = KE.shape[0]  # 24

    # Node numbering: (nelx+1)*(nely+1)*(nelz+1) nodes, 3 DOFs each
    def node_id(ix: int, iy: int, iz: int) -> int:
        return iz * (nelx+1)*(nely+1) + iy * (nelx+1) + ix

    ndof = 3 * (nelx+1) * (nely+1) * (nelz+1)

    # Element → DOF connectivity
    edof_all = np.zeros((nel, 24), dtype=int)
    e = 0
    for iz in range(nelz):
        for iy in range(nely):
            for ix in range(nelx):
                nodes = [
                    node_id(ix, iy, iz), node_id(ix+1, iy, iz),
                    node_id(ix, iy+1, iz), node_id(ix+1, iy+1, iz),
                    node_id(ix, iy, iz+1), node_id(ix+1, iy, iz+1),
                    node_id(ix, iy+1, iz+1), node_id(ix+1, iy+1, iz+1),
                ]
                dof = []
                for n in nodes:
                    dof.extend([3*n, 3*n+1, 3*n+2])
                edof_all[e] = dof
                e += 1

    # Precompute sparse assembly indices
    iK = np.zeros(nel * nke * nke, dtype=int)
    jK = np.zeros_like(iK)
    for e_idx in range(nel):
        edof = edof_all[e_idx]
        base = e_idx * nke * nke
        for ii in range(nke):
            for jj in range(nke):
                iK[base + ii*nke + jj] = edof[ii]
                jK[base + ii*nke + jj] = edof[jj]

    # BCs and loads
    F = np.zeros(ndof)
    if cfg.bc_type == "cantilever":
        # Fix x=0 face, load at center of x=nelx face
        fixed_nodes = []
        for iz in range(nelz+1):
            for iy in range(nely+1):
                fixed_nodes.append(node_id(0, iy, iz))
        fixed_dofs = []
        for n in fixed_nodes:
            fixed_dofs.extend([3*n, 3*n+1, 3*n+2])
        fixed_dofs = np.array(fixed_dofs)
        load_node = node_id(nelx, nely//2, nelz//2)
        F[3*load_node + 1] = -1.0
    else:
        fixed_dofs = np.arange(3 * (nely+1) * (nelz+1))
        load_node = node_id(nelx, nely//2, nelz//2)
        F[3*load_node + 1] = -1.0

    free_dofs = np.setdiff1d(np.arange(ndof), fixed_dofs)

    # Filter kernel
    H = _density_filter_kernel_3d(cfg.rmin)

    x = np.full((nelz, nely, nelx), volfrac)
    compliance_history: list[float] = []
    start_time = time.time()

    for iteration in range(cfg.max_iter):
        if time.time() - start_time > cfg.timeout_s:
            logger.warning("3D TO timed out after %.1fs at iter %d", cfg.timeout_s, iteration)
            break

        xPhys = convolve(x, H, mode="reflect")
        xPhys = np.clip(xPhys, 0.0, 1.0)
        xflat = xPhys.ravel()

        # Assemble
        sK = np.zeros(nel * nke * nke)
        for e_idx in range(nel):
            Ee = cfg.Emin + xflat[e_idx]**penal * (cfg.E0 - cfg.Emin)
            base = e_idx * nke * nke
            sK[base:base + nke*nke] = (Ee * KE).ravel()

        K = sparse.coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()

        u = np.zeros(ndof)
        try:
            K_ff = K[np.ix_(free_dofs, free_dofs)]
            u[free_dofs] = spsolve(K_ff, F[free_dofs])
        except Exception as exc:
            logger.error("3D TO solve failed at iter %d: %s", iteration, exc)
            break

        ce = np.zeros(nel)
        for e_idx in range(nel):
            ue = u[edof_all[e_idx]]
            ce[e_idx] = ue @ KE @ ue

        compliance = float((cfg.Emin + xflat**penal * (cfg.E0 - cfg.Emin)) @ ce)
        compliance_history.append(compliance)

        dc = -penal * xflat**(penal - 1) * (cfg.E0 - cfg.Emin) * ce
        dc = dc.reshape(nelz, nely, nelx)
        dc = convolve(dc, H, mode="reflect")

        l1, l2, move = 0.0, 1e9, 0.2
        while l2 - l1 > 1e-9:
            lmid = 0.5 * (l1 + l2)
            Bmin = np.maximum(0.0, x - move)
            Bmax = np.minimum(1.0, x + move)
            xnew = np.maximum(Bmin, np.minimum(Bmax,
                x * np.sqrt(np.maximum(1e-12, -dc / lmid))))
            if xnew.mean() > volfrac:
                l1 = lmid
            else:
                l2 = lmid

        change = float(np.max(np.abs(xnew - x)))
        x = xnew.copy()

        if iteration % 10 == 0:
            logger.info("3D-TO iter %d: C=%.4f, Vf=%.4f, Δ=%.4f",
                        iteration, compliance, float(xPhys.mean()), change)

        if change < cfg.tol and iteration > 3:
            logger.info("3D-TO converged at iter %d", iteration)
            break

    xPhys = convolve(x, H, mode="reflect")
    xPhys = np.clip(xPhys, 0.0, 1.0)

    return TOResult3D(
        density=xPhys,
        compliance_history=compliance_history,
        iterations=iteration + 1,
        final_compliance=compliance_history[-1] if compliance_history else 0.0,
        final_volfrac=float(xPhys.mean()),
        config=cfg,
    )


def density_to_mesh(density: np.ndarray, threshold: float = 0.5, spacing: float = 1.0):
    """Convert a density field to a triangle mesh via Marching Cubes.

    Parameters
    ----------
    density : (nz, ny, nx) or (ny, nx) array
    threshold : float
        Iso-surface level; voxels above this are solid.
    spacing : float
        Physical spacing between voxels (mm).

    Returns
    -------
    trimesh.Trimesh
    """
    import trimesh
    if density.ndim == 2:
        # Extrude 2D to thin 3D slab
        density = np.stack([density, density, density], axis=0)

    try:
        from skimage.measure import marching_cubes
    except ImportError:
        from skimage import measure
        marching_cubes = measure.marching_cubes

    verts, faces, _, _ = marching_cubes(
        density, level=threshold,
        spacing=(spacing, spacing, spacing),
    )
    return trimesh.Trimesh(vertices=verts, faces=faces[:, ::-1], process=True)
