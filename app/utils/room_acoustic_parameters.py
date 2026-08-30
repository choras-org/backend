import numpy as np
import pyfar as pf
import pyrato


def calculate_room_acoustic_parameters(
        room_impulse_response: pf.Signal,
        bands: np.ndarray | list[float],
    ) -> dict[str, list[float]]:
    """Calculate room acoustic parameters from the RIR.

    Parameters
    ----------
    room_impulse_response : pf.Signal
        The room impulse response.
    bands : np.ndarray or list of float
        The frequency bands for which to calculate acoustic parameters.
        This assumes octave bands.

    Returns
    -------
    parameters : dict
        A dictionary containing the calculated room acoustic parameters for
        each frequency band. Keys include 'bands', 'edt', 't20', 't30', 'd50',
        'c80', 'ts', and 'spl_t0_freq'; values are lists with one entry per band.
    """

    bands = np.asarray(bands, dtype=float)

    start_sample = pf.dsp.find_impulse_response_start(room_impulse_response)

    rir_bands = pf.dsp.filter.fractional_octave_bands(
        room_impulse_response,
        num_fractions=1,
        frequency_range=[np.min(bands), np.max(bands)],
        order=10,
    )

    rir_bands_shifted = pf.dsp.time_shift(
        rir_bands,
        -start_sample,
        unit='samples',
        mode='linear',
        pad_value=np.nan,
    )

    bands = pf.constants.fractional_octave_frequencies_nominal(
        num_fractions=1,
        frequency_range=(np.min(bands), np.max(bands)),
    )

    # pyrato returns per-band arrays directly; no pre-allocation required.

    edc_bands = pyrato.edc.schroeder_integration(
        rir_bands_shifted,
        is_energy=False
    )

    edc_bands = pf.dsp.normalize(edc_bands, nan_policy='omit')

    EDT = pyrato.parameters.reverberation_time_linear_regression(
        edc_bands, T='EDT')
    T_20 = pyrato.parameters.reverberation_time_linear_regression(
        edc_bands, T='T20')
    T_30 = pyrato.parameters.reverberation_time_linear_regression(
        edc_bands, T='T30')

    # pyrato returns a range [0, 1] for D50,
    # CHORAS expects a percentage value in [0, 100]
    D_50 = pyrato.parameters.definition(edc_bands, early_time_limit=50) * 1e2

    C_80 = pyrato.parameters.clarity(edc_bands, early_time_limit=80)

    spl_t0_freq = 20*np.log10(pf.dsp.rms(rir_bands)/20e-6)

    T_s = center_time(edc_bands) * 1e3 # convert to ms

    def _normalize_nan_and_inf(arr: np.ndarray) -> np.ndarray:
        """Replace NaN and Inf values in the array with 0.0.

        The CHORAS frontend does not handle NaN and Inf values at the moment.

        Parameters
        ----------
        arr : np.ndarray
            The input array.

        Returns
        -------
        np.ndarray
            The array with NaN and Inf values replaced by 0.0.
        """
        arr = np.where(np.isnan(arr), 0.0, arr)
        arr = np.where(np.isinf(arr), 0.0, arr)
        return arr

    parameters = {
        'bands': bands.tolist(),
        'edt': np.squeeze(_normalize_nan_and_inf(EDT)).tolist(),
        't20': np.squeeze(_normalize_nan_and_inf(T_20)).tolist(),
        't30': np.squeeze(_normalize_nan_and_inf(T_30)).tolist(),
        'd50': np.squeeze(_normalize_nan_and_inf(D_50)).tolist(),
        'c80': np.squeeze(_normalize_nan_and_inf(C_80)).tolist(),
        'ts': np.squeeze(_normalize_nan_and_inf(T_s)).tolist(),
        'spl_t0_freq': np.squeeze(
            _normalize_nan_and_inf(spl_t0_freq)).tolist(),
    }

    return parameters


# This can replaced once pyrato 1.1.0 is released
def center_time(energy_decay_curve):
    r"""
    Calculate the room-acoustic center time (:math:`T_s`).

    The center time :math:`T_s` is the time of the centroid of the squared
    impulse response. It quantifies the balance between early and late
    sound energy [#isoTs]_.

    The parameter is defined as

    .. math::

        T_s =
        \frac{
            \displaystyle \int_{0}^{\infty} t \cdot p^2(t)\,\mathrm{d}t
        }{
            \displaystyle \int_{0}^{\infty} p^2(t)\,\mathrm{d}t
        }

    where :math:`p(t)` is the room impulse response sound pressure.

    Using the energy decay curve :math:`e(t)`, the parameter can be
    computed efficiently via the EDC identity as

    .. math::

        T_s =
        \frac{
            \displaystyle \int_{0}^{\infty} e(t)\,\mathrm{d}t
        }{
            e(0)
        }.

    Parameters
    ----------
    energy_decay_curve : pyfar.TimeData
        Energy decay curve of the room impulse response. The EDC must
        start at time zero and must have equal time spacing.

    Returns
    -------
    center_time : numpy.ndarray
        Center time (:math:`T_s`) in seconds,
        shaped according to the channel shape of the input EDC.

    References
    ----------
    .. [#isoTs] ISO 3382, Acoustics — Measurement of the reverberation
        time of rooms with reference to other acoustical parameters.

    Note
    ----

    This function is taken from the pyrato package (<https://github.com/pyfar/pyrato>).
    See the attached license below:

    MIT License

    Copyright (c) 2021-2023, Marco Berzborn - Institute of Technical Acoustics
    Copyright (c) 2023, The pyfar developers

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.



    """

    if not isinstance(energy_decay_curve, pf.TimeData):
        raise TypeError(
            "energy_decay_curve must be a pyfar.TimeData or derived object.")

    if not np.isclose(energy_decay_curve.times[0], 0.0):
        raise ValueError("energy_decay_curve must start at time zero.")

    if np.any(energy_decay_curve.time[..., 0] == 0):
        raise ValueError(
            "Initial energy of energy_decay_curve must not be zero.")

    dt = np.diff(energy_decay_curve.times)
    if not np.allclose(dt, dt[0]):
        raise ValueError(
            "energy_decay_curve must have equal time spacing.")

    sampling_interval = dt[0]
    initial_energy = energy_decay_curve.time[..., 0]
    center_time = (
        np.nansum(energy_decay_curve.time, axis=-1)
        * sampling_interval
        / initial_energy
    )

    return center_time
