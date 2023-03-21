from math import pi
import jax.numpy as jnp
from jax import lax


def define_all_tridiags(
    voltages: jnp.ndarray,
    na_conds: jnp.ndarray,
    kd_conds: jnp.ndarray,
    leak_conds: jnp.ndarray,
    i_ext: jnp.ndarray,
    num_neighbours: jnp.ndarray,
    nseg_per_branch: int,
    num_branches: int,
    dt: float,
    coupling_conds: float,
):
    """
    Set up tridiagonal system for each branch.
    """
    lowers, diags, uppers, solves = [], [], [], []
    for b in range(num_branches):
        l_ind = b * nseg_per_branch
        u_ind = (b + 1) * nseg_per_branch
        voltages_in_branch = voltages[l_ind:u_ind]
        na_conds_in_branch = na_conds[l_ind:u_ind]
        kd_conds_in_branch = kd_conds[l_ind:u_ind]
        leak_conds_in_branch = leak_conds[l_ind:u_ind]
        i_ext_in_branch = i_ext[l_ind:u_ind]
        num_neighbours_in_branch = num_neighbours[l_ind:u_ind]

        lower, diag, upper, solve = _define_tridiag_for_branch(
            voltages=voltages_in_branch,
            na_conds=na_conds_in_branch,
            kd_conds=kd_conds_in_branch,
            leak_conds=leak_conds_in_branch,
            i_ext=i_ext_in_branch,
            dt=dt,
            num_neighbours=num_neighbours_in_branch,
            coupling_conds=coupling_conds,
            nseg_per_branch=nseg_per_branch,
        )
        lowers.append(lower)
        diags.append(diag)
        uppers.append(upper)
        solves.append(solve)

    return (
        jnp.asarray(lowers),
        jnp.asarray(diags),
        jnp.asarray(uppers),
        jnp.asarray(solves),
    )


def get_external_input(
    voltages: jnp.ndarray,
    t: float,
    i_dur: float,
    i_amp: float,
    radius: float,
    length_single_compartment: float,
    nseg_per_branch: int,
):
    """
    Compute external input to each compartment.
    """
    zero_vec = jnp.zeros_like(voltages)
    stim_on = jnp.greater_equal(t, 5.0)
    stim_off = jnp.less_equal(t, 5.0 + i_dur)
    stim_ = jnp.logical_and(stim_on, stim_off)
    current_in_comp = i_amp / 2 / pi / radius / length_single_compartment
    external_currents = lax.cond(
        stim_,
        lambda x: x.at[nseg_per_branch - 1].set(current_in_comp),
        lambda x: x,
        zero_vec,
    )
    return external_currents


def get_num_neighbours(
    num_kids: jnp.ndarray,
    nseg_per_branch: int,
    num_branches: int,
):
    """
    Number of neighbours of each compartment.
    """
    num_neighbours = 2 * jnp.ones((num_branches * nseg_per_branch))
    num_neighbours = num_neighbours.at[nseg_per_branch - 1].set(1.0)
    num_neighbours = num_neighbours.at[jnp.arange(num_branches) * nseg_per_branch].set(
        num_kids + 1.0
    )
    return num_neighbours


def _define_tridiag_for_branch(
    voltages: jnp.ndarray,
    na_conds: jnp.ndarray,
    kd_conds: jnp.ndarray,
    leak_conds: jnp.ndarray,
    i_ext: jnp.ndarray,
    dt: float,
    num_neighbours: jnp.ndarray,
    coupling_conds: float,
    nseg_per_branch: int,
):
    """
    Defines the tridiagonal system to solve for a single branch.
    """
    voltage_terms = na_conds + kd_conds + leak_conds
    constant_terms = 50.0 * na_conds + (-90.0) * kd_conds + (-65.0) * leak_conds + i_ext

    # Diagonal and solve.
    a_v = 1.0 + dt * voltage_terms + dt * num_neighbours * coupling_conds
    b_v = voltages + dt * constant_terms

    # Subdiagonals.
    upper = jnp.asarray([-dt * coupling_conds] * (nseg_per_branch - 1))
    lower = jnp.asarray([-dt * coupling_conds] * (nseg_per_branch - 1))
    return lower, a_v, upper, b_v