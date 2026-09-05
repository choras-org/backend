import json
import os
from typing import Literal, Optional

import numpy as np
import pyfar as pf
import pyrato
from config import DefaultConfig
from flask_smorest import abort
from pydantic import BaseModel

from app.models.Simulation import Simulation
from app.types import Status

# ---------------------------------------------------------------------------
# Plot data model and export helpers
# ---------------------------------------------------------------------------

TimeLike = pf.TimeData | pf.Signal
FreqLike = pf.FrequencyData | pf.Signal


class PlotData(BaseModel):
    x: list[float]
    y: list[list[float]]  # (n_channels, n_samples)
    xlabel: str
    ylabel: str
    x_limits: tuple[float, float]
    y_limits: tuple[float, float]
    x_scale: Literal["linear", "log"] = "linear"
    legend: list[str]


def _default_legend(data) -> list[str]:
    return [f"Channel {i+1}" for i in range(int(np.prod(data.cshape)))]


def _process_y(
    raw: np.ndarray,
    dB: bool,
    log_prefix: float,
    db_margin: float,
    unit: str,
    quantity: str,
) -> tuple[list[list[float]], tuple[float, float], str]:
    y = np.squeeze(raw).astype(float)
    if dB:
        y = log_prefix * np.log10(np.abs(y))
        y_limits = (float(np.max(y) - db_margin), float(np.max(y) + 5))
        ylabel = f"{quantity} (dB re 1 {unit})"
    else:
        y_limits = (float(np.min(y)), float(np.max(y)))
        ylabel = f"{quantity} ({unit})"
    return y.reshape(-1, y.shape[-1]).tolist(), y_limits, ylabel


def export_time_data(
        data: TimeLike,
        unit: str = "-",
        dB: bool = False,
        legend: list[str] | None = None,
        log_prefix: float = 20,
    ) -> PlotData:
    x = data.times.tolist()
    y, y_limits, ylabel = _process_y(data.time, dB, log_prefix, 85, unit, "Magnitude")
    return PlotData(
        x=x, y=y,
        xlabel="Time (s)", ylabel=ylabel,
        x_limits=(x[0], x[-1]), y_limits=y_limits,
        legend=legend if legend is not None else _default_legend(data),
    )


def export_time_data_energy(
        data: TimeLike,
        unit: str = "-",
        dB: bool = False,
        legend: list[str] | None = None,
    ) -> PlotData:
    x = data.times.tolist()
    y, y_limits, ylabel = _process_y(data.time, dB, 10, 65, unit, "Energy")
    return PlotData(
        x=x, y=y,
        xlabel="Time (s)", ylabel=ylabel,
        x_limits=(x[0], x[-1]), y_limits=y_limits,
        legend=legend if legend is not None else _default_legend(data),
    )


def export_frequency_data(
        data: FreqLike,
        unit: str = "-",
        dB: bool = False,
        legend: list[str] | None = None,
    ) -> PlotData:
    x = data.frequencies.tolist()
    y, y_limits, ylabel = _process_y(np.abs(data.freq), dB, 20, 80, unit, "Magnitude")
    return PlotData(
        x=x, y=y,
        xlabel="Frequency (Hz)", ylabel=ylabel,
        x_limits=(max(x[0], 20.0), float(x[-1])), y_limits=y_limits,
        x_scale="log",
        legend=legend if legend is not None else _default_legend(data),
    )

# Visualization types the frontend can request, and the suffix used for
# their sidecar JSON file on disk (see `generate_visualization_data`).
VISUALIZATION_TYPES: list[str] = ["rir", "rir_db", "spectrum", "spectrum_db", "edc"]


def generate_visualization_data(room_impulse_response: pf.Signal, json_path: str) -> None:
    """
    Compute and persist the visualization plot data for a completed simulation.

    One JSON file per entry in `VISUALIZATION_TYPES` is written next to the
    simulation's other result files (e.g. the `.wav`/`.xlsx` exports),
    following the same `json_path` naming convention (`{base}_{type}.json`).

    Parameters
    ----------
    room_impulse_response : array-like
        The room impulse response resulting from the simulation.
    json_path : str
        Path to the simulation result JSON file. Used as the base name for
        the generated sidecar files.
    """
    rirs_bandpassed = pf.dsp.filter.fractional_octave_bands(
        room_impulse_response, num_fractions=1, frequency_range=(125, 2e3),
    )

    center_freqs = pf.dsp.filter.fractional_octave_frequencies(
        frequency_range=(125, 2e3))[0]
    center_freqs_legend = [f"{int(f)} Hz" for f in center_freqs]

    start_samples = pf.dsp.find_impulse_response_delay(
        rirs_bandpassed,
    )

    rirs_bandpassed = pf.dsp.time_shift(
        rirs_bandpassed, -start_samples, mode='linear')

    edc = pf.dsp.normalize(
        pyrato.edc.schroeder_integration(rirs_bandpassed),
        channel_handling="max",
    )

    plots = {
        "rir": export_time_data(room_impulse_response, dB=False),
        "rir_db": export_time_data(room_impulse_response, dB=True),
        "spectrum": export_frequency_data(room_impulse_response, dB=False),
        "spectrum_db": export_frequency_data(room_impulse_response, dB=True),
        "edc": export_time_data_energy(edc, dB=True, legend=center_freqs_legend),
    }

    for visualization_type, plot_data in plots.items():
        output_path = json_path.replace(".json", f"_{visualization_type}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(plot_data.model_dump_json())


def get_visualization_data(simulation_id: int, visualization_type: str) -> Optional[dict]:
    """
    Load previously generated visualization plot data for a completed simulation.

    Parameters
    ----------
    simulation_id : int
        The ID of the simulation to get visualization data for.
    visualization_type : str
        One of `VISUALIZATION_TYPES`.
    """
    if visualization_type not in VISUALIZATION_TYPES:
        abort(400, message=f"Unknown visualization type '{visualization_type}'.")
        return None

    simulation = check_if_simulation_completed(simulation_id)

    if simulation.export is None:
        abort(404, message=f"No result export found for simulation with ID {simulation_id}.")
        return None

    file_path = os.path.join(
        DefaultConfig.UPLOAD_FOLDER_NAME,
        simulation.export.name.replace(".xlsx", f"_{visualization_type}.json"),
    )

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        abort(
            404,
            message=(
                f"No '{visualization_type}' visualization data found for simulation "
                f"with ID {simulation_id}."
            ),
        )
        return None


def check_if_simulation_completed(simulation_id: int):
    """
    Check if the simulation with the given ID exists and has completed.

    Parameters
    ----------
    simulation_id : int
        The ID of the simulation to check.

    """
    simulation = Simulation.query.filter_by(id=simulation_id).first()
    if simulation is None:
        abort(404, message=f"Simulation with ID {simulation_id} not found.")
    if simulation.status != Status.Completed:
        abort(400, message=f"Simulation with ID {simulation_id} is not finalized.")

    return simulation
