"""
Audio quality assessment tools for evaluating processing performance.

This module provides comprehensive audio quality metrics and assessment
tools for validating the effectiveness of audio processing algorithms.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import scipy.signal
from scipy.fft import fft, fftfreq

from .models import AudioFrame


@dataclass
class QualityMetrics:
    """Container for audio quality assessment metrics."""
    
    # Signal quality metrics
    snr_db: float = 0.0
    thd_percent: float = 0.0
    dynamic_range_db: float = 0.0
    
    # Frequency response metrics
    frequency_response_flatness: float = 0.0
    bandwidth_hz: float = 0.0
    
    # Noise metrics
    noise_floor_db: float = 0.0
    noise_reduction_db: float = 0.0
    
    # Distortion metrics
    harmonic_distortion_db: float = 0.0
    intermodulation_distortion_db: float = 0.0
    
    # Perceptual metrics
    loudness_lufs: float = 0.0
    speech_intelligibility_score: float = 0.0


class AudioQualityAssessment:
    """Comprehensive audio quality assessment toolkit."""
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.reference_signals = self._generate_reference_signals()
    
    def assess_frame_quality(self, frame: AudioFrame, 
                           reference_frame: Optional[AudioFrame] = None) -> QualityMetrics:
        """
        Assess the quality of an audio frame.
        
        Args:
            frame: Audio frame to assess
            reference_frame: Optional reference frame for comparison
            
        Returns:
            Quality metrics for the frame
        """
        metrics = QualityMetrics()
        
        # Convert to mono for analysis if stereo
        audio_data = frame.to_mono().data.flatten()
        
        # Basic signal quality metrics
        metrics.snr_db = self._calculate_snr(audio_data)
        metrics.thd_percent = self._calculate_thd(audio_data)
        metrics.dynamic_range_db = self._calculate_dynamic_range(audio_data)
        
        # Frequency domain analysis
        metrics.frequency_response_flatness = self._calculate_frequency_flatness(audio_data)
        metrics.bandwidth_hz = self._calculate_bandwidth(audio_data)
        
        # Noise analysis
        metrics.noise_floor_db = self._calculate_noise_floor(audio_data)
        
        # Distortion analysis
        metrics.harmonic_distortion_db = self._calculate_harmonic_distortion(audio_data)
        
        # Perceptual metrics
        metrics.loudness_lufs = self._calculate_loudness(audio_data)
        metrics.speech_intelligibility_score = self._calculate_speech_intelligibility(audio_data)
        
        # Comparative metrics if reference provided
        if reference_frame is not None:
            ref_data = reference_frame.to_mono().data.flatten()
            metrics.noise_reduction_db = self._calculate_noise_reduction(ref_data, audio_data)
        
        return metrics
    
    def assess_processing_quality(self, input_frame: AudioFrame, 
                                output_frame: AudioFrame) -> Dict[str, float]:
        """
        Assess the quality impact of audio processing.
        
        Args:
            input_frame: Original input frame
            output_frame: Processed output frame
            
        Returns:
            Dictionary of quality impact metrics
        """
        input_metrics = self.assess_frame_quality(input_frame)
        output_metrics = self.assess_frame_quality(output_frame, input_frame)
        
        quality_impact = {
            'snr_improvement_db': output_metrics.snr_db - input_metrics.snr_db,
            'thd_change_percent': output_metrics.thd_percent - input_metrics.thd_percent,
            'dynamic_range_change_db': output_metrics.dynamic_range_db - input_metrics.dynamic_range_db,
            'noise_reduction_db': output_metrics.noise_reduction_db,
            'frequency_response_preservation': self._calculate_frequency_preservation(
                input_frame.to_mono().data.flatten(),
                output_frame.to_mono().data.flatten()
            ),
            'loudness_change_lufs': output_metrics.loudness_lufs - input_metrics.loudness_lufs,
            'speech_intelligibility_improvement': (
                output_metrics.speech_intelligibility_score - 
                input_metrics.speech_intelligibility_score
            )
        }
        
        return quality_impact
    
    def generate_quality_report(self, frames: List[AudioFrame], 
                              processed_frames: List[AudioFrame] = None) -> Dict:
        """
        Generate comprehensive quality assessment report.
        
        Args:
            frames: List of audio frames to assess
            processed_frames: Optional list of processed frames for comparison
            
        Returns:
            Comprehensive quality report
        """
        if not frames:
            return {}
        
        # Assess individual frames
        frame_metrics = []
        for i, frame in enumerate(frames):
            ref_frame = processed_frames[i] if processed_frames and i < len(processed_frames) else None
            metrics = self.assess_frame_quality(frame, ref_frame)
            frame_metrics.append(metrics)
        
        # Calculate aggregate statistics
        report = {
            'frame_count': len(frames),
            'average_metrics': self._calculate_average_metrics(frame_metrics),
            'quality_consistency': self._calculate_quality_consistency(frame_metrics),
            'overall_quality_score': self._calculate_overall_quality_score(frame_metrics)
        }
        
        # Add processing impact analysis if processed frames provided
        if processed_frames:
            processing_impacts = []
            for i, (input_frame, output_frame) in enumerate(zip(frames, processed_frames)):
                if i < len(processed_frames):
                    impact = self.assess_processing_quality(input_frame, output_frame)
                    processing_impacts.append(impact)
            
            report['processing_impact'] = self._aggregate_processing_impacts(processing_impacts)
        
        return report
    
    def _calculate_snr(self, audio_data: np.ndarray) -> float:
        """Calculate Signal-to-Noise Ratio."""
        # Estimate signal power (RMS of signal)
        signal_power = np.mean(audio_data ** 2)
        
        # Estimate noise power (using quiet segments)
        # Simple approach: assume lowest 10% of energy represents noise
        windowed_power = []
        window_size = len(audio_data) // 20  # 5% windows
        
        for i in range(0, len(audio_data) - window_size, window_size):
            window = audio_data[i:i + window_size]
            windowed_power.append(np.mean(window ** 2))
        
        noise_power = np.percentile(windowed_power, 10)  # Lowest 10%
        
        if noise_power > 0:
            snr_linear = signal_power / noise_power
            return 10 * np.log10(snr_linear)
        else:
            return 60.0  # Very high SNR if no detectable noise
    
    def _calculate_thd(self, audio_data: np.ndarray) -> float:
        """Calculate Total Harmonic Distortion."""
        # Perform FFT
        fft_data = fft(audio_data)
        freqs = fftfreq(len(audio_data), 1/self.sample_rate)
        magnitude = np.abs(fft_data)
        
        # Find fundamental frequency (peak in spectrum)
        positive_freqs = freqs[:len(freqs)//2]
        positive_magnitude = magnitude[:len(magnitude)//2]
        
        # Look for peak between 80Hz and 2kHz (typical speech/music range)
        freq_mask = (positive_freqs >= 80) & (positive_freqs <= 2000)
        if not np.any(freq_mask):
            return 0.0
        
        masked_freqs = positive_freqs[freq_mask]
        masked_magnitude = positive_magnitude[freq_mask]
        
        fundamental_idx = np.argmax(masked_magnitude)
        fundamental_freq = masked_freqs[fundamental_idx]
        fundamental_power = masked_magnitude[fundamental_idx] ** 2
        
        # Calculate harmonic powers
        harmonic_power = 0
        for harmonic in range(2, 6):  # 2nd through 5th harmonics
            harmonic_freq = fundamental_freq * harmonic
            if harmonic_freq < self.sample_rate / 2:
                # Find closest frequency bin
                harmonic_idx = np.argmin(np.abs(positive_freqs - harmonic_freq))
                harmonic_power += positive_magnitude[harmonic_idx] ** 2
        
        if fundamental_power > 0:
            thd = np.sqrt(harmonic_power / fundamental_power)
            return thd * 100  # Convert to percentage
        else:
            return 0.0
    
    def _calculate_dynamic_range(self, audio_data: np.ndarray) -> float:
        """Calculate dynamic range of audio signal."""
        # Calculate RMS in overlapping windows
        window_size = len(audio_data) // 10
        hop_size = window_size // 2
        rms_values = []
        
        for i in range(0, len(audio_data) - window_size, hop_size):
            window = audio_data[i:i + window_size]
            rms = np.sqrt(np.mean(window ** 2))
            if rms > 0:
                rms_values.append(20 * np.log10(rms))
        
        if len(rms_values) > 0:
            return max(rms_values) - min(rms_values)
        else:
            return 0.0
    
    def _calculate_frequency_flatness(self, audio_data: np.ndarray) -> float:
        """Calculate frequency response flatness."""
        fft_data = fft(audio_data)
        magnitude = np.abs(fft_data[:len(fft_data)//2])
        
        # Focus on audible frequency range (20Hz - 20kHz)
        freqs = fftfreq(len(audio_data), 1/self.sample_rate)[:len(fft_data)//2]
        audible_mask = (freqs >= 20) & (freqs <= 20000)
        
        if not np.any(audible_mask):
            return 1.0
        
        audible_magnitude = magnitude[audible_mask]
        
        # Calculate flatness as ratio of geometric mean to arithmetic mean
        if len(audible_magnitude) > 0 and np.all(audible_magnitude > 0):
            geometric_mean = np.exp(np.mean(np.log(audible_magnitude)))
            arithmetic_mean = np.mean(audible_magnitude)
            flatness = geometric_mean / arithmetic_mean
            return flatness
        else:
            return 0.0
    
    def _calculate_bandwidth(self, audio_data: np.ndarray) -> float:
        """Calculate effective bandwidth of signal."""
        fft_data = fft(audio_data)
        magnitude = np.abs(fft_data[:len(fft_data)//2])
        freqs = fftfreq(len(audio_data), 1/self.sample_rate)[:len(fft_data)//2]
        
        # Find -3dB bandwidth
        max_magnitude = np.max(magnitude)
        threshold = max_magnitude / np.sqrt(2)  # -3dB point
        
        above_threshold = magnitude >= threshold
        if np.any(above_threshold):
            freq_indices = np.where(above_threshold)[0]
            bandwidth = freqs[freq_indices[-1]] - freqs[freq_indices[0]]
            return bandwidth
        else:
            return 0.0
    
    def _calculate_noise_floor(self, audio_data: np.ndarray) -> float:
        """Calculate noise floor level."""
        # Use spectral analysis to estimate noise floor
        fft_data = fft(audio_data)
        magnitude = np.abs(fft_data[:len(fft_data)//2])
        
        # Estimate noise floor as percentile of spectrum
        noise_floor_linear = np.percentile(magnitude, 10)  # Bottom 10%
        
        if noise_floor_linear > 0:
            return 20 * np.log10(noise_floor_linear)
        else:
            return -80.0  # Very low noise floor
    
    def _calculate_harmonic_distortion(self, audio_data: np.ndarray) -> float:
        """Calculate harmonic distortion in dB."""
        thd_percent = self._calculate_thd(audio_data)
        if thd_percent > 0:
            return 20 * np.log10(thd_percent / 100)
        else:
            return -60.0  # Very low distortion
    
    def _calculate_loudness(self, audio_data: np.ndarray) -> float:
        """Calculate loudness in LUFS (simplified)."""
        # Simplified loudness calculation (not full ITU-R BS.1770)
        # Apply K-weighting filter (simplified)
        
        # High-pass filter at 38 Hz
        sos_hp = scipy.signal.butter(2, 38, btype='high', fs=self.sample_rate, output='sos')
        filtered = scipy.signal.sosfilt(sos_hp, audio_data)
        
        # High-frequency shelving filter
        sos_shelf = scipy.signal.butter(2, 1681, btype='high', fs=self.sample_rate, output='sos')
        k_weighted = scipy.signal.sosfilt(sos_shelf, filtered)
        
        # Calculate mean square and convert to LUFS
        mean_square = np.mean(k_weighted ** 2)
        if mean_square > 0:
            lufs = -0.691 + 10 * np.log10(mean_square)
            return lufs
        else:
            return -70.0  # Very quiet
    
    def _calculate_speech_intelligibility(self, audio_data: np.ndarray) -> float:
        """Calculate speech intelligibility score (simplified)."""
        # Simplified speech intelligibility based on spectral characteristics
        fft_data = fft(audio_data)
        magnitude = np.abs(fft_data[:len(fft_data)//2])
        freqs = fftfreq(len(audio_data), 1/self.sample_rate)[:len(fft_data)//2]
        
        # Focus on speech frequency bands
        speech_bands = [
            (300, 500),    # Low speech
            (500, 1000),   # Mid speech
            (1000, 2000),  # High speech
            (2000, 4000)   # Consonant clarity
        ]
        
        band_energies = []
        for low_freq, high_freq in speech_bands:
            band_mask = (freqs >= low_freq) & (freqs <= high_freq)
            if np.any(band_mask):
                band_energy = np.sum(magnitude[band_mask] ** 2)
                band_energies.append(band_energy)
            else:
                band_energies.append(0)
        
        # Calculate intelligibility as weighted sum of band energies
        weights = [0.2, 0.3, 0.3, 0.2]  # Emphasize mid frequencies
        total_energy = sum(energy * weight for energy, weight in zip(band_energies, weights))
        
        # Normalize to 0-1 scale
        max_possible_energy = np.sum(magnitude ** 2)
        if max_possible_energy > 0:
            intelligibility = min(1.0, total_energy / (max_possible_energy * 0.5))
            return intelligibility
        else:
            return 0.0
    
    def _calculate_noise_reduction(self, reference: np.ndarray, processed: np.ndarray) -> float:
        """Calculate noise reduction achieved by processing."""
        # Estimate noise in both signals
        ref_noise = self._estimate_noise_level(reference)
        proc_noise = self._estimate_noise_level(processed)
        
        if ref_noise > 0 and proc_noise > 0:
            reduction_db = 20 * np.log10(ref_noise / proc_noise)
            return max(0, reduction_db)  # Only positive reductions
        else:
            return 0.0
    
    def _estimate_noise_level(self, audio_data: np.ndarray) -> float:
        """Estimate noise level in audio signal."""
        # Use spectral subtraction approach
        fft_data = fft(audio_data)
        magnitude = np.abs(fft_data[:len(fft_data)//2])
        
        # Estimate noise as minimum statistics
        noise_estimate = np.percentile(magnitude, 5)  # Bottom 5%
        return noise_estimate
    
    def _calculate_frequency_preservation(self, input_signal: np.ndarray, 
                                        output_signal: np.ndarray) -> float:
        """Calculate how well frequency content is preserved."""
        # Compare frequency spectra
        input_fft = np.abs(fft(input_signal)[:len(input_signal)//2])
        output_fft = np.abs(fft(output_signal)[:len(output_signal)//2])
        
        # Normalize spectra
        input_fft = input_fft / np.max(input_fft) if np.max(input_fft) > 0 else input_fft
        output_fft = output_fft / np.max(output_fft) if np.max(output_fft) > 0 else output_fft
        
        # Calculate correlation between spectra
        if len(input_fft) == len(output_fft):
            correlation = np.corrcoef(input_fft, output_fft)[0, 1]
            return max(0, correlation)  # Only positive correlations
        else:
            return 0.0
    
    def _calculate_average_metrics(self, metrics_list: List[QualityMetrics]) -> QualityMetrics:
        """Calculate average of quality metrics."""
        if not metrics_list:
            return QualityMetrics()
        
        avg_metrics = QualityMetrics()
        
        # Average all numeric fields
        for field_name in avg_metrics.__dataclass_fields__:
            values = [getattr(m, field_name) for m in metrics_list]
            setattr(avg_metrics, field_name, np.mean(values))
        
        return avg_metrics
    
    def _calculate_quality_consistency(self, metrics_list: List[QualityMetrics]) -> Dict[str, float]:
        """Calculate consistency (standard deviation) of quality metrics."""
        if len(metrics_list) < 2:
            return {}
        
        consistency = {}
        
        for field_name in metrics_list[0].__dataclass_fields__:
            values = [getattr(m, field_name) for m in metrics_list]
            consistency[f"{field_name}_std"] = np.std(values)
        
        return consistency
    
    def _calculate_overall_quality_score(self, metrics_list: List[QualityMetrics]) -> float:
        """Calculate overall quality score (0-100)."""
        if not metrics_list:
            return 0.0
        
        avg_metrics = self._calculate_average_metrics(metrics_list)
        
        # Weighted scoring of different quality aspects
        score_components = {
            'snr': min(100, max(0, (avg_metrics.snr_db + 10) * 2)),  # -10dB to 40dB -> 0-100
            'thd': max(0, 100 - avg_metrics.thd_percent * 10),  # Lower THD is better
            'dynamic_range': min(100, avg_metrics.dynamic_range_db * 2),  # 0-50dB -> 0-100
            'frequency_flatness': avg_metrics.frequency_response_flatness * 100,
            'speech_intelligibility': avg_metrics.speech_intelligibility_score * 100
        }
        
        # Weighted average
        weights = {
            'snr': 0.25,
            'thd': 0.15,
            'dynamic_range': 0.15,
            'frequency_flatness': 0.2,
            'speech_intelligibility': 0.25
        }
        
        overall_score = sum(score_components[key] * weights[key] for key in weights)
        return min(100, max(0, overall_score))
    
    def _aggregate_processing_impacts(self, impacts: List[Dict[str, float]]) -> Dict[str, float]:
        """Aggregate processing impact metrics."""
        if not impacts:
            return {}
        
        aggregated = {}
        
        # Calculate averages for all impact metrics
        for key in impacts[0].keys():
            values = [impact[key] for impact in impacts]
            aggregated[f"avg_{key}"] = np.mean(values)
            aggregated[f"std_{key}"] = np.std(values) if len(values) > 1 else 0.0
        
        return aggregated
    
    def _generate_reference_signals(self) -> Dict[str, np.ndarray]:
        """Generate reference signals for testing."""
        duration = 1.0  # 1 second
        samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, samples)
        
        references = {
            'sine_1khz': np.sin(2 * np.pi * 1000 * t),
            'white_noise': np.random.normal(0, 0.1, samples),
            'chirp': scipy.signal.chirp(t, 20, duration, 20000),
            'speech_like': self._generate_speech_like_signal(t)
        }
        
        return references
    
    def _generate_speech_like_signal(self, t: np.ndarray) -> np.ndarray:
        """Generate speech-like test signal."""
        # Combine multiple harmonics typical of speech
        fundamental = 150  # Hz
        signal = (
            0.5 * np.sin(2 * np.pi * fundamental * t) +
            0.3 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.2 * np.sin(2 * np.pi * fundamental * 3 * t) +
            0.1 * np.sin(2 * np.pi * fundamental * 4 * t)
        )
        
        # Apply speech-like envelope
        envelope = np.exp(-t * 0.5) * (1 + 0.5 * np.sin(2 * np.pi * 5 * t))
        
        return signal * envelope