#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
An implementation of the time frequency phase misfit and adjoint source after
Fichtner et al. (2008).

:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de), 2013
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
import numpy as np
from scipy.interpolate import interp1d
from scipy.interpolate import RectBivariateSpline
import warnings

from lasif.adjoint_sources import time_frequency

eps = np.spacing(1)

misfit_upper_bound = 2.0


def adsrc_tf(t, tapered_data, tapered_synthetic,
        tapered_and_weighted_synthetic, dt_new, width, threshold):

    # Compute time-frequency representation via cross-correlation
    tau_cc, nu_cc, tf_cc = time_frequency.time_frequency_cc_difference(
        t, tapered_data, tapered_and_weighted_synthetic, dt_new, width,
        threshold)

    # Compute the time-frequency representation of two synthetic traces??
    tau, nu, tf_synth_weighted = time_frequency.time_frequency_transform(t,
        tapered_and_weighted_synthetic, dt_new, width, threshold)
    tau, nu, tf_synth = time_frequency.time_frequency_transform(t,
        tapered_synthetic, dt_new, width, threshold)

    # 2D interpolation. Use a two step interpolation for the real and the
    # imaginary parts.
    tf_cc_interp = RectBivariateSpline(tau_cc[0], nu_cc[:, 0], tf_cc.real,
        kx=1, ky=1, s=0)(tau[0], nu[:, 0])
    tf_cc_interp = np.require(tf_cc_interp, dtype="complex128")
    tf_cc_interp.imag = RectBivariateSpline(tau_cc[0], nu_cc[:, 0], tf_cc.imag,
        kx=1, ky=1, s=0)(tau[0], nu[:, 0])
    tf_cc = tf_cc_interp

    ####
    # Make window functionality
    ####
    # noise taper
    m = np.abs(tf_cc).max() / 10.0
    W = 1.0 - np.exp(-(np.abs(tf_cc) ** 2) / (m ** 2))

    # high-pass filter
    W = W * (1.0 - np.exp((-nu.transpose() ** 2) / (0.002 ** 2)))

    nu_t = nu.transpose()
    nu_t_large = nu_t.copy()
    nu_t_small = nu_t.copy()
    thres = (nu_t <= 0.005)
    nu_t_large[thres] = 0.0
    nu_t_large[np.invert(thres)] = 1.0
    nu_t_small[thres] = 1.0
    nu_t_small[np.invert(thres)] = 0.0

    # low-pass filter
    W *= (np.exp(-(nu_t - 0.005) ** 4 / 0.005 ** 4) * nu_t_large + nu_t_small)

    # normalisation
    W /= W.max()

    ####
    # Compute phase difference
    ####
    DP = np.imag(np.log(eps + tf_cc / (eps + np.abs(tf_cc))))

    ####
    # Detect phase jumps
    ####
    test_field = W * DP / np.abs(W * DP).max()
    criterion_1 = np.abs(np.diff(test_field)).max()
    criterion_2 = np.abs(np.diff(test_field.transpose())).max()
    criterion = max(criterion_1, criterion_2)
    ad_kill = 1.0

    print "Criterion:", criterion
    if criterion > 0.7:
        ad_kill = 0.0
        warnings.warn("Possible Phase Jump")

    ####
    # Compute phase misfit
    ####
    dnu = nu[1, 0] - nu[0, 0]

    Ep = np.sqrt(np.sum(np.sum(W * W * DP * DP)) * dt_new * dnu)

    if np.isnan(Ep):
        ad_kill = 1
        Ep = 0.0

    print "Phase misfit: %g" % (Ep)

    if Ep > misfit_upper_bound:
        ad_kill = 0.0
        print "Misfit exceeds upper bound: set to zero!"

    print "Phase misfit (unweighted): %g" % Ep

    ####
    # Make kernel for the inverse tf transform
    ####
    IDP = W * W * DP * tf_synth_weighted / (eps + np.abs(tf_synth) *
        np.abs(tf_synth))

    ####
    # Invert tf transform and make adjoint source
    ####
    ad_src, it, I = time_frequency.itfa(tau, nu, IDP, width, threshold)

    ad_src = interp1d(tau[0, :], np.imag(ad_src), kind=2)(t)

    # Divide by misfit
    ad_src /= (Ep + eps)
    ad_src = np.diff(ad_src) / (t[1] - t[0])

    # Kill if phase jump
    ad_src *= ad_kill

    # Reverse time
    ad_src = ad_src[::-1]
    ad_src = np.concatenate([[0.0], ad_src])

    return ad_src