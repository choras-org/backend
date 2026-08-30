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

    T_s = pyrato.parameters.center_time(edc_bands) * 1e3 # convert to ms

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
