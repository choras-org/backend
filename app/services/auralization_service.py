import gc
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np
import soundfile as sf
from celery import shared_task
from flask_smorest import abort
from scipy.io import wavfile
from scipy.signal import butter, convolve, resample_poly, sosfilt
from sqlalchemy import and_, asc, desc, or_
from werkzeug.datastructures import FileStorage, ImmutableDict

from app.db import db
from app.factory.export_factory.ExportHelper import ExportHelper
from app.models.AudioFile import AudioFile
from app.models.Auralization import Auralization
from app.models.Export import Export
from app.models.Model import Model
from app.models.Simulation import Simulation
from app.types import Status
from config import AuralizationParametersConfig as AuralizationParameters
from config import CustomExportParametersConfig, DefaultConfig, app_dir

from math import ceil

# Create Logger for this module
logger = logging.getLogger(__name__)

debug_celery = False

def get_auralization_by_id(auralization_id: int) -> Optional[Auralization]:
    auralization: Optional[Auralization] = Auralization.query.filter_by(id=auralization_id).first()
    return auralization if auralization else Auralization(status=Status.Uncreated)


def get_auralization_by_simulation_audiofile_ids(simulation_id: int, audiofile_id: int) -> Optional[Auralization]:
    auralization: Optional[Auralization] = Auralization.query.filter_by(
        simulationId=simulation_id, audioFileId=audiofile_id
    ).first()
    return auralization if auralization else Auralization(status=Status.Uncreated)


def get_audio_file_by_id(audiofile_id: int) -> Optional[AudioFile]:
    audiofile: Optional[AudioFile] = AudioFile.query.filter_by(id=audiofile_id).first()
    return audiofile if audiofile else AudioFile(status=Status.Uncreated)


def get_auralization_wav_path(auralization_id: int) -> Optional[Path]:
    auralization: Optional[Auralization] = get_auralization_by_id(auralization_id)
    if auralization is None:
        abort(404, message="No auralization found with this id.")

    elif auralization.status != Status.Completed:
        abort(400, message="Auralization is not completed yet.")

    else:
        try:
            wav_file_path = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, auralization.wavFileName)
            return Path(wav_file_path)
        except Exception as e:
            abort(400, message=f"Error while getting the wav file path: {e}")
            return None


def get_audio_file_wav_path(audiofile_id: int) -> Optional[Path]:
    audiofile: Optional[AudioFile] = get_audio_file_by_id(audiofile_id)
    if audiofile is None:
        abort(404, message="No audio file found with this id.")

    try:
        wav_file_path = os.path.join(audiofile.path, audiofile.filename)
        return Path(wav_file_path)
    except Exception as e:
        abort(400, message=f"Error while getting the wav file path: {e}")
        return None


def get_impulse_response_wav_path(simulation_id: int) -> Optional[Path]:
    simulation: Optional[Simulation] = Simulation.query.filter_by(id=simulation_id).first()
    if simulation is None:
        abort(404, message="No simulation found with this id.")
    elif simulation.status != Status.Completed:
        abort(400, message="Simulation is not completed yet.")
    else:
        try:
            wav_file_path = os.path.join(
                DefaultConfig.UPLOAD_FOLDER_NAME, f"{simulation.export.name.replace('.xlsx', '.wav')}"
            )
            return Path(wav_file_path)
        except Exception as e:
            abort(400, message=f"Error while getting the impulse response wav file path: {e}")
            return None


def get_impulse_response_plot(simulation_id: int) -> Optional[dict]:
    simulation: Optional[Simulation] = Simulation.query.filter_by(id=simulation_id).first()
    if simulation is None:
        abort(404, message="No simulation found with this id.")
    elif simulation.status != Status.Completed:
        abort(400, message="Simulation is not completed yet.")
    else:
        try:
            xlsx_file_path = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, simulation.export.name)
            plot_data = ExportHelper.extract_from_xlsx_to_dict(
                xlsx_file_path,
                {CustomExportParametersConfig.impulse_response: [f"{AuralizationParameters.visualization_fs}Hz"]},
            )
            return {
                "impulseResponse": plot_data[CustomExportParametersConfig.impulse_response][
                    f"{AuralizationParameters.visualization_fs}Hz"
                ],
                "fs": AuralizationParameters.visualization_fs,
                "simulationId": simulation.id,
            }
        except Exception as e:
            abort(400, message=f"Error while getting the impulse response plot: {e}")
            return None


def upload_audio_file(
    audio_data: Optional[ImmutableDict[str, str]], audio_file: Optional[ImmutableDict[str, FileStorage]]
) -> AudioFile:
    try:
        simulation_id = int(audio_data["simulation_id"])

        simulation: Simulation = Simulation.query.filter_by(id=simulation_id).first()
        if simulation is None:
            logger.error(f"No simulation found with this id: {simulation_id}")
            abort(404, message="No simulation found with this id")

        model_id = simulation.modelId
        model: Model = Model.query.filter_by(id=model_id).first()
        if model is None:
            logger.error(f"No model found with this id: {model_id}")
            abort(404, message="No model found with this id")

        project_id = model.projectId
    except Exception as e:
        logger.error(f"Error parsing simulation_id: {e}")
        abort(400, message="Error parsing simulation_id")

    try:
        audio_name = audio_data["name"]
        audio_file_name = audio_name + '_' + uuid4().hex
        audio_file_description = audio_data["description"]
        audio_file_extension = audio_data["extension"]
        audio_file_data = audio_file["file"]

        if audio_file_data is None:
            logger.error("No audio file uploaded.")
            abort(400, message="No audio file uploaded.")

        if audio_file_extension not in AuralizationParameters.allowedextensions:
            logger.error(f"Invalid audio file type: {audio_file_extension}")
            abort(400, message=f"file not match in {AuralizationParameters.allowedextensions}")

        # if audio_file_data.content_length > AuralizationParameters.maxSize:
        if (file_size := __get_file_size__(audio_file_data)) > AuralizationParameters.maxSize:
            logger.error(f"Audio file size is too large: {file_size}")
            abort(400, message=f"Audio file size is larger than {AuralizationParameters.maxSize}")

    except KeyError as e:
        logger.error(f"Error parsing audio file data: {e}")
        abort(400, message="Error parsing audio file data")

    try:
        audio_file_path = Path(
            os.path.join(DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, audio_file_name + '.' + audio_file_extension)
        )
        with open(audio_file_path, "wb") as save_file:
            audio_file_data.save(save_file)

        audio_file = __update_audio_file__(
            audio_name, audio_file_description, audio_file_path, audio_file_extension, project_id, True
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error uploading audio file: {e}")
        abort(400, message="Error uploading audio file")

    return audio_file


def __update_audio_file__(
    name: str, description: str, path: Path, fileExtension: str, projectId: int, isUserFile: bool
) -> AudioFile:
    audio_file: Optional[AudioFile] = AudioFile.query.filter(
        and_(AudioFile.name == name, AudioFile.projectId == projectId)
    ).first()
    if audio_file is None:
        audio_file = AudioFile(
            name=name,
            filename=path.name,
            description=description,
            path=DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME,
            fileExtension=fileExtension,
            projectId=projectId,
            isUserFile=isUserFile,
        )
        db.session.add(audio_file)
    else:
        # delete the old file
        old_file_path = Path(DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, audio_file.filename)
        if old_file_path.exists():
            old_file_path.unlink()
        logger.debug(f"Old audio file deleted: {old_file_path}")

        # update the filename, description, and updatedAt
        audio_file.filename = path.name  # the latest uploaded filename
        audio_file.description = description
        audio_file.updatedAt = datetime.now()
        logger.debug(f"Audio file updated: {audio_file.filename}")

    db.session.commit()
    return audio_file


def __get_file_size__(file_storage: FileStorage) -> int:
    file_storage.seek(0, os.SEEK_END)
    fie_size = file_storage.tell()
    file_storage.seek(0)
    return fie_size


def create_new_auralization(simulation_id: int, audiofile_id: int) -> Optional[Auralization]:
    auralization: Optional[Auralization] = get_auralization_by_simulation_audiofile_ids(simulation_id, audiofile_id)
    # if auralization.status == Status.Uncreated or auralization.status == Status.Error:
    try:
        auralization = Auralization(simulationId=simulation_id, audioFileId=audiofile_id)
        auralization.status = Status.Created

        db.session.add(auralization)
        db.session.commit()

        simulation = Simulation.query.filter_by(id=simulation_id).first()

        logger.info(f"Start running auralization task for auralization id: {auralization.id}")

        if debug_celery:
            run_auralization(auralizationId=auralization.id)
        else:
            run_auralization.delay(auralizationId=auralization.id)

        logger.info(f"Auralization task for auralization id: {auralization.id} is running")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating auralization: {e}")
        abort(400, "Error creating auralization")

    return auralization


@shared_task
def run_auralization(auralizationId: int) -> None:
    try:
        auralization: Auralization = get_auralization_by_id(auralizationId)
        auralization.status = Status.InProgress
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating auralization status to InProgress: {e}")
        abort(400, "Error updating auralization status to InProgress")

    try:
        input_audio_file: AudioFile = auralization.audioFile
        signal_file_name = os.path.join(input_audio_file.path, input_audio_file.filename)

        simulation: Simulation = auralization.simulation
        export: Export = simulation.export
        pressure_file_name = os.path.join(
            DefaultConfig.UPLOAD_FOLDER_NAME, export.name.replace(".xlsx", "_pressure.csv")
        )

        auralization.wavFileName = export.name.replace(".xlsx", f"_{input_audio_file.name}")
        wav_output_file_name = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, auralization.wavFileName)

        logger.debug("signal_file_name: %s", signal_file_name)
        logger.debug("pressure_file_name: %s", pressure_file_name)
        logger.debug("wav_output_file_name: %s", wav_output_file_name)

        logger.debug("run auralization calculation")

        #TODO: fix behavior for DG auralization, DG method output format 
        # should be changed. We want a single universal auralization method,
        # without having to switch logic between them for each simulation method. 
        match simulation.simulationMethod:
            case "DE":
                 _, _ = auralization_calculation(signal_file_name, pressure_file_name, wav_output_file_name)
            case "DG":
                 _, _ = auralization_calculation_DG(signal_file_name, pressure_file_name, wav_output_file_name)
                         

        auralization.status = Status.Completed

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        auralization.status = Status.Error
        db.session.commit()
        logger.error(f"Error running this auralization {auralization.id}: {e}")
        abort(400, "Error running this auralization")


# TODO: too long code, refactor this function
def auralization_calculation_DG(
    signal_file_name: Optional[str], impulse_response: str, wav_output_file_name: Optional[str] = None
) -> Tuple[List[int], int]:
    # Load the signal and pressure data
    try:
        if signal_file_name is not None:
            # Extract data and sampling rate from file
            data_signal, fs = sf.read(signal_file_name)  # this returns "data_signal", which is the
            # audiodata (one_dimentional array) of the anechoic signal. It returns also the
            # "fs" sample frequency of the signal
        else:
            data_signal, fs = None, AuralizationParameters.visualization_fs

        imp_tot = np.loadtxt(
            impulse_response, skiprows=1, usecols=1, delimiter=','
        )  # this returns the pressure data

    except Exception as e:
        logger.error(f'Error loading files: {e}')
        return None, None

    try:
        if data_signal is not None:
            logger.info("Convolving processing ...")
            # CONVOLUTION FOR AURALIZATION
            # Create impulse*signal response
            # convolution of the impulse response with the anechoic signal
            # sh_conv = np.convolve(imp_tot, data_signal, mode='full')
            # normalized to the maximum value of the convolved signal
            # sh_conv = sh_conv / max(abs(sh_conv))
            # normalize the floating-point data to the range of int16
            # sh_conv_normalized = np.int16(sh_conv * 32767)
            # Time vector of the convolved signal
            # t_conv = np.arange(0, (len(sh_conv)) / fs, 1 / fs)

            # The above code can only be used for 1D signal input,
            # so I will use the following code for multi-channel signal input
            # add a new axis to the impulse response for matching the dimensions of the signal
            if data_signal.ndim > 1:
                imp_tot = np.expand_dims(imp_tot, axis=1)

            # scipy.signal.convolve is faster than numpy.convolve
            sh_conv = convolve(imp_tot, data_signal, mode='full', method='auto')
            sh_conv_normalized = normalize_to_int16(sh_conv)

            # # Validation
            # sh_conv_np = np.convolve(imp_tot, data_signal, mode='full')
            # logger.info(f"test for equivalence: {np.allclose(sh_conv_np, sh_conv)}")
            # logger.info(f"test for equivalence: {sh_conv[20:30] - sh_conv_np[20:30]}")
            # logger.info(f"test for equivalence: {sh_conv.shape} {sh_conv_np.shape}")

            if wav_output_file_name is not None:
                # Create a file wav for auralization
                wavfile.write(wav_output_file_name, fs, sh_conv_normalized)
                return None, None  # in 16 bit format

        else:
            imp_tot_normalized = normalize_to_int16(imp_tot)

            if wav_output_file_name is not None:
                # Create a file wav for impulse response
                wavfile.write(wav_output_file_name, fs, imp_tot_normalized)
            return (imp_tot.tolist(), fs)  # fs = 44100 Hz if no signal file is provided

    except Exception as e:
        logger.error(f'Error during auralization calculation: {e}')
        return None, None


# TODO: too long code, refactor this function
def auralization_calculation(
    signal_file_name: Optional[str], pressure_file_name: str, wav_output_file_name: Optional[str] = None
) -> Tuple[List[int], int]:
    # Load the signal and pressure data
    try:
        if signal_file_name is not None:
            # Extract data and sampling rate from file
            data_signal, fs = sf.read(signal_file_name)  # this returns "data_signal", which is the
            # audiodata (one_dimentional array) of the anechoic signal. It returns also the
            # "fs" sample frequency of the signal
        else:
            data_signal, fs = None, AuralizationParameters.visualization_fs

        data_pressure = np.loadtxt(
            pressure_file_name, skiprows=1, usecols=range(1, 6), delimiter=','
        )  # this returns the pressure data
        center_freq = np.loadtxt(
            pressure_file_name, usecols=range(1, 6), delimiter=',', dtype=str, max_rows=1
        )  # this returns the center frequencies of the bands with the suffix "Hz"

        center_freq = np.array([np.int32(f[:-2]) for f in center_freq])  # remove "Hz" suffix from the center frequency
        nBands = len(center_freq)  # number of bands
        p_rec_off_deriv_band = (
            data_pressure.transpose().copy()
        )  # energy decay curve in terms of pressure differentiated

        del data_pressure  # Delete the data to free up memory
        gc.collect()  # Force garbage collection

    except Exception as e:
        logger.error(f'Error loading files: {e}')
        return None, None

    # Auralization Calculation
    try:
        # RESAMPLING PRESSURE ENVELOPE
        num_samples = ceil(p_rec_off_deriv_band.shape[1] * fs / AuralizationParameters.original_fs)
        p_rec_off_deriv_band_resampled = np.zeros((p_rec_off_deriv_band.shape[0], num_samples))
        for i in range(p_rec_off_deriv_band.shape[0]):
            p_rec_off_deriv_band_resampled[i, :] = resample_poly(
                p_rec_off_deriv_band[i, :], up=int(fs), down=int(AuralizationParameters.original_fs)
            )

        # Clip negative values to zero
        p_rec_off_deriv_band_resampled = np.clip(p_rec_off_deriv_band_resampled, a_min=0, a_max=None)

        # SQUARE-ROOT of ENVELOPE
        # From the envelope of the impulse response, we need to get the impulse response
        square_root = np.sqrt(p_rec_off_deriv_band_resampled)  # this gives the impulse response at each frequency

        # FOURTH ATTEMPT of noise creation
        np.random.seed(AuralizationParameters.random_seed)
        noise = np.random.rand(1, p_rec_off_deriv_band_resampled.shape[1]) * 2 * (np.sqrt(3)) - (
            np.sqrt(3)
        )  # random noise vector with unifrom distribution and with numbers between -1 and 1
        noise = sum(noise)  # this line of code is used for passing from a row vector to a column vector

        # BUTTER FILTER
        Nyquist_freq = int(fs / 2)
        filter_order = AuralizationParameters.filter_order  # number of biquad sections of the desired system
        nth_octave = AuralizationParameters.nth_octave  # e.g., 3 for third-octave
        filter_tot = []
        for fc in center_freq:
            # Calculate low and high cutoff frequencies for each band
            lowcut = fc / (2 ** (1 / (2 * nth_octave)))
            highcut = fc * (2 ** (1 / (2 * nth_octave)))

            # Normalize the cutoff frequencies by the Nyquist frequency
            low = lowcut / Nyquist_freq
            high = highcut / Nyquist_freq

            # Design Butterworth bandpass filter
            butter_band = butter(
                filter_order, [low, high], btype='band', output='sos'
            )  # butter_band contains the second-order sections representation of the Butterworth filter

            # Append filter coefficients to filter tot
            filter_tot.append(butter_band)

        # TIME DOMAIN OF THE FILTERED RANDOM NOISE: for each band the sosfilt creates
        # a time domain convolution of the noise with the filter
        filt_noise_band = [
            sosfilt(band, noise) for band in filter_tot
        ]  # this is in the time domain because the sosfilt gives the time domain

        # Make the filt_noise_band list into an array
        filt_noise_band = np.array(filt_noise_band)

        # Padding the square-root to the same length as the filtered random noise
        pad_length = filt_noise_band.shape[1] - p_rec_off_deriv_band_resampled.shape[1]
        square_root_padded = np.pad(square_root, ((0, 0), (0, pad_length)), mode='constant')

        # Multiplication of SQUARE-ROOT of envelope with filtered random noise (FILTERED)
        imp_filt_band = []
        for fi in range(nBands):
            imp_filt = square_root_padded[fi, :] * filt_noise_band[fi, :]
            imp_filt_band.append(imp_filt)

        # ALL FREQUENCY IMPULSE RESPONSE WITHOUT DIRECT SOUND
        # Sum of the bands in the time domain
        imp_tot = [sum(imp_filt_band[i][j] for i in range(len(imp_filt_band))) for j in range(len(imp_filt_band[0]))]
        imp_tot = np.array(imp_tot, dtype=float)

        if data_signal is not None:
            logger.info("Convolving processing ...")
            # CONVOLUTION FOR AURALIZATION
            # Create impulse*signal response
            # convolution of the impulse response with the anechoic signal
            # sh_conv = np.convolve(imp_tot, data_signal, mode='full')
            # normalized to the maximum value of the convolved signal
            # sh_conv = sh_conv / max(abs(sh_conv))
            # normalize the floating-point data to the range of int16
            # sh_conv_normalized = np.int16(sh_conv * 32767)
            # Time vector of the convolved signal
            # t_conv = np.arange(0, (len(sh_conv)) / fs, 1 / fs)

            # The above code can only be used for 1D signal input,
            # so I will use the following code for multi-channel signal input
            # add a new axis to the impulse response for matching the dimensions of the signal
            if data_signal.ndim > 1:
                imp_tot = np.expand_dims(imp_tot, axis=1)

            # scipy.signal.convolve is faster than numpy.convolve
            sh_conv = convolve(imp_tot, data_signal, mode='full', method='auto')
            sh_conv_normalized = normalize_to_int16(sh_conv)

            # # Validation
            # sh_conv_np = np.convolve(imp_tot, data_signal, mode='full')
            # logger.info(f"test for equivalence: {np.allclose(sh_conv_np, sh_conv)}")
            # logger.info(f"test for equivalence: {sh_conv[20:30] - sh_conv_np[20:30]}")
            # logger.info(f"test for equivalence: {sh_conv.shape} {sh_conv_np.shape}")

            if wav_output_file_name is not None:
                # Create a file wav for auralization
                wavfile.write(wav_output_file_name, fs, sh_conv_normalized)
                return None, None  # in 16 bit format

        else:
            imp_tot_normalized = normalize_to_int16(imp_tot)

            if wav_output_file_name is not None:
                # Create a file wav for impulse response
                wavfile.write(wav_output_file_name, fs, imp_tot_normalized)
            return (imp_tot.tolist(), fs)  # fs = 44100 Hz if no signal file is provided

    except Exception as e:
        logger.error(f'Error during auralization calculation: {e}')
        return None, None


def normalize_to_int16(sh_conv: np.ndarray) -> np.ndarray:
    return np.int16(sh_conv / np.max(np.abs(sh_conv), axis=0) * 32767)


def get_all_audio_files() -> Optional[List[AudioFile]]:
    return AudioFile.query.order_by(asc(AudioFile.id)).all()


def get_audio_files_by_simulation_id(simulation_id: int) -> Optional[List[AudioFile]]:
    simulation = Simulation.query.filter_by(id=simulation_id).first()
    if simulation is None:
        abort(404, message="No simulation found with this id")
    model = Model.query.filter_by(id=simulation.modelId).first()
    if model is None:
        abort(404, message="No model found with this id")
    project_id = model.projectId
    return (
        AudioFile.query.filter(or_(AudioFile.projectId == project_id, AudioFile.projectId.is_(None)))
        .order_by(desc(AudioFile.createdAt))
        .all()
    )


def delete_audio_file(audio_file_id: int) -> None:
    audio_file = AudioFile.query.filter_by(id=audio_file_id).first()
    if audio_file is None:
        abort(404, message="No audio file found with this id")

    if not audio_file.isUserFile:
        abort(400, message="Cannot delete system audio file")

    try:
        # Remove physical file if present
        file_path = Path(audio_file.path, audio_file.filename)
        if file_path.exists():
            file_path.unlink()

        # Delete audio file record using ORM
        db.session.delete(audio_file)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting audio file: {e}")
        abort(400, message=f"Error deleting audio file: {e}")


def insert_initial_audios_examples():
    audio_files = get_all_audio_files()
    if len(audio_files):
        return
    logger.info("Inserting initial audio example files")
    with open(os.path.join(app_dir, "models", "data", "audio_files.json")) as json_audio_files:
        initial_audio_files = json.load(json_audio_files)
        try:
            new_audio_files = []
            for audio_file in initial_audio_files:
                new_audio_files.append(
                    AudioFile(
                        name=audio_file["name"],
                        filename=audio_file["filename"],
                        description=audio_file["description"],
                        fileExtension=audio_file["fileExtension"],
                    )
                )

            db.session.add_all(new_audio_files)
            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not insert initial audio files! Error: {ex}")
            abort(400, f"Can not insert initial audio files! Error: {ex}")

    return {"message": "Initial audio files added successfully!"}


def update_audios_examples():
    with open(os.path.join(app_dir, "models", "data", "audio_files.json")) as json_audio_files:
        audio_file_json_dict: Dict[str, Dict[str, Any]] = {
            audio_file["name"]: audio_file for audio_file in json.load(json_audio_files)
        }
        audio_file_db_list: List[AudioFile] = AudioFile.query.all()
        try:
            for audio_file in audio_file_db_list:
                if audio_file.name not in audio_file_json_dict:
                    db.session.delete(audio_file)
                else:
                    for key, value in audio_file_json_dict[audio_file.name].items():
                        audio_file.__setattr__(key, value)
                    audio_file.updatedAt = datetime.now()
                    del audio_file_json_dict[audio_file.name]

            for audio_file in audio_file_json_dict.values():
                db.session.add(AudioFile(**audio_file))

            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not update audio files! Error: {ex}")

    return {"message": "Initial audio files added successfully!"}
