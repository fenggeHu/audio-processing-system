# Audio Recording and Playback System
"""
音频录制和回放系统

实现多通道音频录制、回放功能，支持WAV/FLAC格式输出，
提供录制控制界面和文件管理功能。
"""

import os
import wave
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from .interfaces import IAudioProcessor, IVisualizationProvider
from .models import AudioFrame, ProcessingMetrics, AudioDevice


class RecordingState(Enum):
    """录制状态枚举"""
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class AudioFormat(Enum):
    """音频格式枚举"""
    WAV = "wav"
    FLAC = "flac"
    MP3 = "mp3"


@dataclass
class RecordingConfig:
    """录制配置"""
    sample_rate: int = 48000
    channels: int = 2
    bit_depth: int = 24
    format: AudioFormat = AudioFormat.WAV
    buffer_size: int = 1024
    
    # 质量设置
    compression_level: int = 5  # FLAC压缩级别
    quality: str = "high"  # high, medium, low
    
    # 文件设置
    output_dir: str = "recordings"
    filename_template: str = "recording_{timestamp}"
    auto_split_duration: Optional[int] = None  # 自动分割时长(秒)
    max_file_size_mb: Optional[int] = None  # 最大文件大小


@dataclass
class RecordingSession:
    """录制会话信息"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: timedelta = field(default_factory=lambda: timedelta(0))
    
    # 文件信息
    file_path: str = ""
    file_size_bytes: int = 0
    
    # 音频信息
    sample_rate: int = 48000
    channels: int = 2
    bit_depth: int = 24
    format: AudioFormat = AudioFormat.WAV
    
    # 质量统计
    peak_level_db: float = -60.0
    rms_level_db: float = -60.0
    dynamic_range_db: float = 0.0
    snr_db: float = 0.0
    
    # 处理统计
    frames_recorded: int = 0
    frames_dropped: int = 0
    processing_errors: List[str] = field(default_factory=list)
    
    def update_duration(self):
        """更新录制时长"""
        if self.end_time:
            self.duration = self.end_time - self.start_time
        else:
            self.duration = datetime.now() - self.start_time


class AudioRecorder:
    """
    音频录制器类
    
    支持多通道音频录制和WAV/FLAC格式输出
    """
    
    def __init__(self, config: RecordingConfig = None):
        self.config = config or RecordingConfig()
        self.state = RecordingState.IDLE
        
        # 录制状态
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        
        # 当前会话
        self.current_session: Optional[RecordingSession] = None
        self.session_history: List[RecordingSession] = []
        
        # 音频缓冲区
        self._audio_buffer: List[np.ndarray] = []
        self._buffer_lock = threading.Lock()
        
        # 文件写入
        self._wave_file: Optional[wave.Wave_write] = None
        self._file_lock = threading.Lock()
        
        # 回调函数
        self._status_callbacks: List[Callable] = []
        self._data_callbacks: List[Callable] = []
        
        # 统计信息
        self._stats = {
            'total_sessions': 0,
            'total_duration': timedelta(0),
            'total_size_bytes': 0,
            'average_quality': 0.0
        }
        
        # 确保输出目录存在
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
    
    def start_recording(self, session_name: Optional[str] = None) -> bool:
        """
        开始录制
        
        Args:
            session_name: 会话名称，如果为None则自动生成
            
        Returns:
            bool: 是否成功开始录制
        """
        if self.state != RecordingState.IDLE:
            return False
        
        try:
            # 创建录制会话
            if session_name is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                session_name = self.config.filename_template.format(timestamp=timestamp)
            
            self.current_session = RecordingSession(
                session_id=session_name,
                start_time=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                bit_depth=self.config.bit_depth,
                format=self.config.format
            )
            
            # 创建输出文件
            file_path = Path(self.config.output_dir) / f"{session_name}.{self.config.format.value}"
            self.current_session.file_path = str(file_path)
            
            # 打开音频文件
            if not self._open_audio_file(file_path):
                return False
            
            # 重置事件
            self._stop_event.clear()
            self._pause_event.clear()
            
            # 启动录制线程
            self._recording_thread = threading.Thread(target=self._recording_loop)
            self._recording_thread.daemon = True
            self._recording_thread.start()
            
            self.state = RecordingState.RECORDING
            self._notify_status_change()
            
            return True
            
        except Exception as e:
            self.state = RecordingState.ERROR
            if self.current_session:
                self.current_session.processing_errors.append(str(e))
            return False
    
    def stop_recording(self) -> bool:
        """
        停止录制
        
        Returns:
            bool: 是否成功停止录制
        """
        if self.state not in [RecordingState.RECORDING, RecordingState.PAUSED]:
            return False
        
        try:
            self.state = RecordingState.STOPPING
            self._stop_event.set()
            
            # 等待录制线程结束
            if self._recording_thread and self._recording_thread.is_alive():
                self._recording_thread.join(timeout=5.0)
            
            # 关闭音频文件
            self._close_audio_file()
            
            # 完成会话
            if self.current_session:
                self.current_session.end_time = datetime.now()
                self.current_session.update_duration()
                
                # 获取文件大小
                if os.path.exists(self.current_session.file_path):
                    self.current_session.file_size_bytes = os.path.getsize(self.current_session.file_path)
                
                # 添加到历史记录
                self.session_history.append(self.current_session)
                self._update_stats()
            
            self.state = RecordingState.IDLE
            self._notify_status_change()
            
            return True
            
        except Exception as e:
            self.state = RecordingState.ERROR
            if self.current_session:
                self.current_session.processing_errors.append(str(e))
            return False
    
    def pause_recording(self) -> bool:
        """
        暂停录制
        
        Returns:
            bool: 是否成功暂停录制
        """
        if self.state != RecordingState.RECORDING:
            return False
        
        self._pause_event.set()
        self.state = RecordingState.PAUSED
        self._notify_status_change()
        return True
    
    def resume_recording(self) -> bool:
        """
        恢复录制
        
        Returns:
            bool: 是否成功恢复录制
        """
        if self.state != RecordingState.PAUSED:
            return False
        
        self._pause_event.clear()
        self.state = RecordingState.RECORDING
        self._notify_status_change()
        return True
    
    def add_audio_frame(self, frame: AudioFrame) -> bool:
        """
        添加音频帧到录制缓冲区
        
        Args:
            frame: 音频帧数据
            
        Returns:
            bool: 是否成功添加
        """
        if self.state != RecordingState.RECORDING:
            return False
        
        try:
            with self._buffer_lock:
                self._audio_buffer.append(frame.data)
                
                # 更新会话统计
                if self.current_session:
                    self.current_session.frames_recorded += 1
                    
                    # 更新音频质量指标
                    if frame.peak_level_db > self.current_session.peak_level_db:
                        self.current_session.peak_level_db = frame.peak_level_db
                    
                    # 计算RMS平均值
                    total_frames = self.current_session.frames_recorded
                    self.current_session.rms_level_db = (
                        (self.current_session.rms_level_db * (total_frames - 1) + frame.rms_level_db) / total_frames
                    )
            
            return True
            
        except Exception as e:
            if self.current_session:
                self.current_session.processing_errors.append(str(e))
                self.current_session.frames_dropped += 1
            return False
    
    def get_recording_status(self) -> Dict[str, Any]:
        """
        获取录制状态信息
        
        Returns:
            Dict: 录制状态信息
        """
        status = {
            'state': self.state.value,
            'current_session': None,
            'recording_time': '00:00:00',
            'file_size_mb': 0.0,
            'audio_quality': 'unknown'
        }
        
        if self.current_session:
            self.current_session.update_duration()
            
            status.update({
                'current_session': {
                    'session_id': self.current_session.session_id,
                    'start_time': self.current_session.start_time.isoformat(),
                    'duration': str(self.current_session.duration),
                    'file_path': self.current_session.file_path,
                    'sample_rate': self.current_session.sample_rate,
                    'channels': self.current_session.channels,
                    'bit_depth': self.current_session.bit_depth,
                    'format': self.current_session.format.value,
                    'frames_recorded': self.current_session.frames_recorded,
                    'frames_dropped': self.current_session.frames_dropped,
                    'peak_level_db': self.current_session.peak_level_db,
                    'rms_level_db': self.current_session.rms_level_db
                },
                'recording_time': str(self.current_session.duration).split('.')[0],
                'file_size_mb': self.current_session.file_size_bytes / (1024 * 1024),
                'audio_quality': self._assess_audio_quality()
            })
        
        return status
    
    def get_session_history(self) -> List[Dict[str, Any]]:
        """
        获取录制会话历史
        
        Returns:
            List[Dict]: 会话历史列表
        """
        history = []
        for session in self.session_history:
            history.append({
                'session_id': session.session_id,
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat() if session.end_time else None,
                'duration': str(session.duration),
                'file_path': session.file_path,
                'file_size_bytes': session.file_size_bytes,
                'sample_rate': session.sample_rate,
                'channels': session.channels,
                'bit_depth': session.bit_depth,
                'format': session.format.value,
                'frames_recorded': session.frames_recorded,
                'frames_dropped': session.frames_dropped,
                'peak_level_db': session.peak_level_db,
                'rms_level_db': session.rms_level_db,
                'processing_errors': session.processing_errors
            })
        return history
    
    def register_status_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """注册状态变化回调"""
        self._status_callbacks.append(callback)
    
    def register_data_callback(self, callback: Callable[[AudioFrame], None]):
        """注册数据回调"""
        self._data_callbacks.append(callback)
    
    def _recording_loop(self):
        """录制主循环"""
        while not self._stop_event.is_set():
            try:
                # 检查暂停状态
                if self._pause_event.is_set():
                    time.sleep(0.1)
                    continue
                
                # 处理音频缓冲区
                frames_to_write = []
                with self._buffer_lock:
                    if self._audio_buffer:
                        frames_to_write = self._audio_buffer.copy()
                        self._audio_buffer.clear()
                
                # 写入音频数据
                if frames_to_write:
                    self._write_audio_frames(frames_to_write)
                
                time.sleep(0.01)  # 10ms间隔
                
            except Exception as e:
                if self.current_session:
                    self.current_session.processing_errors.append(str(e))
                break
    
    def _open_audio_file(self, file_path: Path) -> bool:
        """打开音频文件进行写入"""
        try:
            with self._file_lock:
                if self.config.format == AudioFormat.WAV:
                    self._wave_file = wave.open(str(file_path), 'wb')
                    self._wave_file.setnchannels(self.config.channels)
                    self._wave_file.setsampwidth(self.config.bit_depth // 8)
                    self._wave_file.setframerate(self.config.sample_rate)
                    return True
                else:
                    # TODO: 实现FLAC支持
                    return False
        except Exception as e:
            if self.current_session:
                self.current_session.processing_errors.append(f"Failed to open file: {e}")
            return False
    
    def _close_audio_file(self):
        """关闭音频文件"""
        try:
            with self._file_lock:
                if self._wave_file:
                    self._wave_file.close()
                    self._wave_file = None
        except Exception as e:
            if self.current_session:
                self.current_session.processing_errors.append(f"Failed to close file: {e}")
    
    def _write_audio_frames(self, frames: List[np.ndarray]):
        """写入音频帧到文件"""
        try:
            with self._file_lock:
                if self._wave_file:
                    for frame in frames:
                        # 转换为字节数据
                        if self.config.bit_depth == 16:
                            audio_data = (frame * 32767).astype(np.int16)
                        elif self.config.bit_depth == 24:
                            audio_data = (frame * 8388607).astype(np.int32)
                        else:  # 32-bit
                            audio_data = (frame * 2147483647).astype(np.int32)
                        
                        self._wave_file.writeframes(audio_data.tobytes())
        except Exception as e:
            if self.current_session:
                self.current_session.processing_errors.append(f"Failed to write frames: {e}")
    
    def _assess_audio_quality(self) -> str:
        """评估音频质量"""
        if not self.current_session:
            return "unknown"
        
        # 基于峰值电平和RMS电平评估质量
        peak_db = self.current_session.peak_level_db
        rms_db = self.current_session.rms_level_db
        
        if peak_db > -6:
            return "poor"  # 可能削波
        elif peak_db > -12 and rms_db > -20:
            return "excellent"
        elif peak_db > -18 and rms_db > -30:
            return "good"
        elif peak_db > -30:
            return "fair"
        else:
            return "poor"  # 信号太弱
    
    def _notify_status_change(self):
        """通知状态变化"""
        status = self.get_recording_status()
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception:
                pass  # 忽略回调错误
    
    def _update_stats(self):
        """更新统计信息"""
        if not self.current_session:
            return
        
        self._stats['total_sessions'] += 1
        self._stats['total_duration'] += self.current_session.duration
        self._stats['total_size_bytes'] += self.current_session.file_size_bytes
        
        # 计算平均质量
        quality_scores = []
        for session in self.session_history:
            if session.rms_level_db > -60:  # 有效信号
                quality_scores.append(max(0, (session.rms_level_db + 60) / 60))
        
        if quality_scores:
            self._stats['average_quality'] = sum(quality_scores) / len(quality_scores)




class AudioPlayer:
    """
    音频播放器类
    
    支持录制文件的播放和处理效果验证
    """
    
    def __init__(self):
        self.state = RecordingState.IDLE
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        
        # 当前播放信息
        self.current_file: Optional[str] = None
        self.current_position: float = 0.0
        self.total_duration: float = 0.0
        
        # 音频数据
        self._audio_data: Optional[np.ndarray] = None
        self._sample_rate: int = 48000
        self._channels: int = 2
        
        # 回调函数
        self._position_callbacks: List[Callable] = []
        self._status_callbacks: List[Callable] = []
    
    def load_file(self, file_path: str) -> bool:
        """
        加载音频文件
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            bool: 是否成功加载
        """
        try:
            if not os.path.exists(file_path):
                return False
            
            # 读取WAV文件
            with wave.open(file_path, 'rb') as wav_file:
                self._sample_rate = wav_file.getframerate()
                self._channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                
                # 读取音频数据
                frames = wav_file.readframes(wav_file.getnframes())
                
                # 转换为numpy数组
                if sample_width == 2:  # 16-bit
                    self._audio_data = np.frombuffer(frames, dtype=np.int16)
                elif sample_width == 3:  # 24-bit
                    # 24-bit需要特殊处理
                    self._audio_data = np.frombuffer(frames, dtype=np.uint8)
                    self._audio_data = self._audio_data.reshape(-1, 3)
                    self._audio_data = np.pad(self._audio_data, ((0, 0), (0, 1)), mode='constant')
                    self._audio_data = self._audio_data.view(np.int32)[:, 0]
                else:  # 32-bit
                    self._audio_data = np.frombuffer(frames, dtype=np.int32)
                
                # 转换为浮点数
                if sample_width == 2:
                    self._audio_data = self._audio_data.astype(np.float32) / 32767.0
                elif sample_width == 3:
                    self._audio_data = self._audio_data.astype(np.float32) / 8388607.0
                else:
                    self._audio_data = self._audio_data.astype(np.float32) / 2147483647.0
                
                # 重塑为多通道格式
                if self._channels > 1:
                    self._audio_data = self._audio_data.reshape(-1, self._channels)
                
                self.current_file = file_path
                self.current_position = 0.0
                self.total_duration = len(self._audio_data) / self._sample_rate
                
                return True
                
        except Exception as e:
            print(f"Failed to load audio file: {e}")
            return False
    
    def play(self) -> bool:
        """
        开始播放
        
        Returns:
            bool: 是否成功开始播放
        """
        if self.state != RecordingState.IDLE or self._audio_data is None:
            return False
        
        try:
            self._stop_event.clear()
            self._pause_event.clear()
            
            self._playback_thread = threading.Thread(target=self._playback_loop)
            self._playback_thread.daemon = True
            self._playback_thread.start()
            
            self.state = RecordingState.RECORDING  # 复用状态枚举
            self._notify_status_change()
            
            return True
            
        except Exception as e:
            print(f"Failed to start playback: {e}")
            return False
    
    def stop(self) -> bool:
        """
        停止播放
        
        Returns:
            bool: 是否成功停止播放
        """
        if self.state not in [RecordingState.RECORDING, RecordingState.PAUSED]:
            return False
        
        try:
            self._stop_event.set()
            
            if self._playback_thread and self._playback_thread.is_alive():
                self._playback_thread.join(timeout=2.0)
            
            self.current_position = 0.0
            self.state = RecordingState.IDLE
            self._notify_status_change()
            
            return True
            
        except Exception as e:
            print(f"Failed to stop playback: {e}")
            return False
    
    def pause(self) -> bool:
        """
        暂停播放
        
        Returns:
            bool: 是否成功暂停播放
        """
        if self.state != RecordingState.RECORDING:
            return False
        
        self._pause_event.set()
        self.state = RecordingState.PAUSED
        self._notify_status_change()
        return True
    
    def resume(self) -> bool:
        """
        恢复播放
        
        Returns:
            bool: 是否成功恢复播放
        """
        if self.state != RecordingState.PAUSED:
            return False
        
        self._pause_event.clear()
        self.state = RecordingState.RECORDING
        self._notify_status_change()
        return True
    
    def seek(self, position: float) -> bool:
        """
        跳转到指定位置
        
        Args:
            position: 位置(秒)
            
        Returns:
            bool: 是否成功跳转
        """
        if self._audio_data is None:
            return False
        
        if 0 <= position <= self.total_duration:
            self.current_position = position
            return True
        
        return False
    
    def get_playback_status(self) -> Dict[str, Any]:
        """
        获取播放状态
        
        Returns:
            Dict: 播放状态信息
        """
        return {
            'state': self.state.value,
            'current_file': self.current_file,
            'current_position': self.current_position,
            'total_duration': self.total_duration,
            'progress_percent': (self.current_position / self.total_duration * 100) if self.total_duration > 0 else 0,
            'sample_rate': self._sample_rate,
            'channels': self._channels
        }
    
    def register_position_callback(self, callback: Callable[[float], None]):
        """注册位置更新回调"""
        self._position_callbacks.append(callback)
    
    def register_status_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """注册状态变化回调"""
        self._status_callbacks.append(callback)
    
    def _playback_loop(self):
        """播放主循环"""
        if self._audio_data is None:
            return
        
        frame_size = 1024  # 每次播放的帧数
        frame_duration = frame_size / self._sample_rate
        
        start_frame = int(self.current_position * self._sample_rate)
        
        while not self._stop_event.is_set():
            try:
                # 检查暂停状态
                if self._pause_event.is_set():
                    time.sleep(0.1)
                    continue
                
                # 计算当前帧位置
                current_frame = int(self.current_position * self._sample_rate)
                
                # 检查是否播放完毕
                if current_frame >= len(self._audio_data):
                    break
                
                # 获取音频帧
                end_frame = min(current_frame + frame_size, len(self._audio_data))
                audio_frame = self._audio_data[current_frame:end_frame]
                
                # 这里应该将音频数据发送到音频输出设备
                # 目前只是模拟播放时间
                time.sleep(frame_duration)
                
                # 更新播放位置
                self.current_position += frame_duration
                
                # 通知位置更新
                for callback in self._position_callbacks:
                    try:
                        callback(self.current_position)
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"Playback error: {e}")
                break
        
        # 播放结束
        self.state = RecordingState.IDLE
        self._notify_status_change()
    
    def _notify_status_change(self):
        """通知状态变化"""
        status = self.get_playback_status()
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception:
                pass




class RecordingControlInterface:
    """
    录制控制界面
    
    提供开始/停止/暂停录制的简单控制
    """
    
    def __init__(self, recorder: AudioRecorder, player: AudioPlayer):
        self.recorder = recorder
        self.player = player
        
        # 注册回调
        self.recorder.register_status_callback(self._on_recorder_status_change)
        self.player.register_status_callback(self._on_player_status_change)
        
        # 界面状态
        self.ui_callbacks: List[Callable] = []
    
    def start_recording(self, session_name: Optional[str] = None) -> Dict[str, Any]:
        """
        开始录制
        
        Args:
            session_name: 会话名称
            
        Returns:
            Dict: 操作结果
        """
        success = self.recorder.start_recording(session_name)
        return {
            'success': success,
            'message': 'Recording started' if success else 'Failed to start recording',
            'status': self.recorder.get_recording_status()
        }
    
    def stop_recording(self) -> Dict[str, Any]:
        """
        停止录制
        
        Returns:
            Dict: 操作结果
        """
        success = self.recorder.stop_recording()
        return {
            'success': success,
            'message': 'Recording stopped' if success else 'Failed to stop recording',
            'status': self.recorder.get_recording_status()
        }
    
    def pause_recording(self) -> Dict[str, Any]:
        """
        暂停录制
        
        Returns:
            Dict: 操作结果
        """
        success = self.recorder.pause_recording()
        return {
            'success': success,
            'message': 'Recording paused' if success else 'Failed to pause recording',
            'status': self.recorder.get_recording_status()
        }
    
    def resume_recording(self) -> Dict[str, Any]:
        """
        恢复录制
        
        Returns:
            Dict: 操作结果
        """
        success = self.recorder.resume_recording()
        return {
            'success': success,
            'message': 'Recording resumed' if success else 'Failed to resume recording',
            'status': self.recorder.get_recording_status()
        }
    
    def load_and_play_file(self, file_path: str) -> Dict[str, Any]:
        """
        加载并播放文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict: 操作结果
        """
        if self.player.load_file(file_path):
            success = self.player.play()
            return {
                'success': success,
                'message': 'Playback started' if success else 'Failed to start playback',
                'status': self.player.get_playback_status()
            }
        else:
            return {
                'success': False,
                'message': 'Failed to load audio file',
                'status': self.player.get_playback_status()
            }
    
    def stop_playback(self) -> Dict[str, Any]:
        """
        停止播放
        
        Returns:
            Dict: 操作结果
        """
        success = self.player.stop()
        return {
            'success': success,
            'message': 'Playback stopped' if success else 'Failed to stop playback',
            'status': self.player.get_playback_status()
        }
    
    def get_recording_status(self) -> Dict[str, Any]:
        """获取录制状态"""
        return self.recorder.get_recording_status()
    
    def get_playback_status(self) -> Dict[str, Any]:
        """获取播放状态"""
        return self.player.get_playback_status()
    
    def get_session_history(self) -> List[Dict[str, Any]]:
        """获取会话历史"""
        return self.recorder.get_session_history()
    
    def register_ui_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """注册UI更新回调"""
        self.ui_callbacks.append(callback)
    
    def _on_recorder_status_change(self, status: Dict[str, Any]):
        """录制状态变化回调"""
        for callback in self.ui_callbacks:
            try:
                callback('recorder', status)
            except Exception:
                pass
    
    def _on_player_status_change(self, status: Dict[str, Any]):
        """播放状态变化回调"""
        for callback in self.ui_callbacks:
            try:
                callback('player', status)
            except Exception:
                pass




class RecordingFileManager:
    """
    录制文件管理器
    
    支持文件命名、分类存储、快速检索
    """
    
    def __init__(self, base_dir: str = "recordings"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        self.categories = {
            'sessions': self.base_dir / 'sessions',
            'exports': self.base_dir / 'exports',
            'processed': self.base_dir / 'processed',
            'archive': self.base_dir / 'archive'
        }
        
        for category_dir in self.categories.values():
            category_dir.mkdir(parents=True, exist_ok=True)
    
    def list_recordings(self, category: str = 'sessions') -> List[Dict[str, Any]]:
        """
        列出录制文件
        
        Args:
            category: 文件分类
            
        Returns:
            List[Dict]: 文件信息列表
        """
        if category not in self.categories:
            return []
        
        category_dir = self.categories[category]
        recordings = []
        
        for file_path in category_dir.glob('*.wav'):
            try:
                stat = file_path.stat()
                
                # 获取音频文件信息
                with wave.open(str(file_path), 'rb') as wav_file:
                    sample_rate = wav_file.getframerate()
                    channels = wav_file.getnchannels()
                    frames = wav_file.getnframes()
                    duration = frames / sample_rate
                
                recordings.append({
                    'filename': file_path.name,
                    'path': str(file_path),
                    'size_bytes': stat.st_size,
                    'size_mb': stat.st_size / (1024 * 1024),
                    'created_time': datetime.fromtimestamp(stat.st_ctime),
                    'modified_time': datetime.fromtimestamp(stat.st_mtime),
                    'duration_seconds': duration,
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'category': category
                })
                
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                continue
        
        # 按修改时间排序
        recordings.sort(key=lambda x: x['modified_time'], reverse=True)
        return recordings
    
    def move_file(self, filename: str, from_category: str, to_category: str) -> bool:
        """
        移动文件到不同分类
        
        Args:
            filename: 文件名
            from_category: 源分类
            to_category: 目标分类
            
        Returns:
            bool: 是否成功移动
        """
        if from_category not in self.categories or to_category not in self.categories:
            return False
        
        source_path = self.categories[from_category] / filename
        target_path = self.categories[to_category] / filename
        
        try:
            if source_path.exists():
                source_path.rename(target_path)
                return True
        except Exception as e:
            print(f"Failed to move file: {e}")
        
        return False
    
    def delete_file(self, filename: str, category: str) -> bool:
        """
        删除文件
        
        Args:
            filename: 文件名
            category: 文件分类
            
        Returns:
            bool: 是否成功删除
        """
        if category not in self.categories:
            return False
        
        file_path = self.categories[category] / filename
        
        try:
            if file_path.exists():
                file_path.unlink()
                return True
        except Exception as e:
            print(f"Failed to delete file: {e}")
        
        return False
    
    def export_file(self, filename: str, source_category: str, export_path: str, 
                   format: AudioFormat = AudioFormat.WAV) -> bool:
        """
        导出文件
        
        Args:
            filename: 源文件名
            source_category: 源分类
            export_path: 导出路径
            format: 导出格式
            
        Returns:
            bool: 是否成功导出
        """
        if source_category not in self.categories:
            return False
        
        source_path = self.categories[source_category] / filename
        
        try:
            if source_path.exists():
                if format == AudioFormat.WAV:
                    # 直接复制WAV文件
                    import shutil
                    shutil.copy2(source_path, export_path)
                    return True
                else:
                    # TODO: 实现其他格式转换
                    return False
        except Exception as e:
            print(f"Failed to export file: {e}")
        
        return False
    
    def search_files(self, query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜索文件
        
        Args:
            query: 搜索关键词
            category: 搜索分类，None表示搜索所有分类
            
        Returns:
            List[Dict]: 匹配的文件列表
        """
        results = []
        
        categories_to_search = [category] if category else list(self.categories.keys())
        
        for cat in categories_to_search:
            if cat in self.categories:
                recordings = self.list_recordings(cat)
                for recording in recordings:
                    if query.lower() in recording['filename'].lower():
                        results.append(recording)
        
        return results
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            Dict: 存储统计
        """
        stats = {
            'total_files': 0,
            'total_size_bytes': 0,
            'total_size_mb': 0.0,
            'categories': {}
        }
        
        for category, category_dir in self.categories.items():
            category_stats = {
                'files': 0,
                'size_bytes': 0,
                'size_mb': 0.0
            }
            
            for file_path in category_dir.glob('*.wav'):
                try:
                    size = file_path.stat().st_size
                    category_stats['files'] += 1
                    category_stats['size_bytes'] += size
                except Exception:
                    continue
            
            category_stats['size_mb'] = category_stats['size_bytes'] / (1024 * 1024)
            stats['categories'][category] = category_stats
            
            stats['total_files'] += category_stats['files']
            stats['total_size_bytes'] += category_stats['size_bytes']
        
        stats['total_size_mb'] = stats['total_size_bytes'] / (1024 * 1024)
        return stats




class RecordingAnalyzer:
    """
    录制数据分析器
    
    生成录制会话的质量报告和统计信息
    """
    
    def __init__(self):
        pass
    
    def analyze_session(self, session: RecordingSession) -> Dict[str, Any]:
        """
        分析录制会话
        
        Args:
            session: 录制会话
            
        Returns:
            Dict: 分析报告
        """
        report = {
            'session_info': {
                'session_id': session.session_id,
                'duration': str(session.duration),
                'file_size_mb': session.file_size_bytes / (1024 * 1024),
                'format': session.format.value,
                'sample_rate': session.sample_rate,
                'channels': session.channels,
                'bit_depth': session.bit_depth
            },
            'quality_metrics': {
                'peak_level_db': session.peak_level_db,
                'rms_level_db': session.rms_level_db,
                'dynamic_range_db': session.dynamic_range_db,
                'snr_db': session.snr_db,
                'quality_assessment': self._assess_quality(session)
            },
            'performance_metrics': {
                'frames_recorded': session.frames_recorded,
                'frames_dropped': session.frames_dropped,
                'drop_rate_percent': (session.frames_dropped / max(session.frames_recorded, 1)) * 100,
                'processing_errors': len(session.processing_errors)
            },
            'recommendations': self._generate_recommendations(session)
        }
        
        return report
    
    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        分析音频文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict: 分析报告
        """
        try:
            # 读取音频文件
            with wave.open(file_path, 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                frames = wav_file.readframes(wav_file.getnframes())
                sample_width = wav_file.getsampwidth()
            
            # 转换为numpy数组
            if sample_width == 2:
                audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
            elif sample_width == 3:
                # 24-bit处理
                audio_bytes = np.frombuffer(frames, dtype=np.uint8)
                audio_data = audio_bytes.reshape(-1, 3)
                audio_data = np.pad(audio_data, ((0, 0), (0, 1)), mode='constant')
                audio_data = audio_data.view(np.int32)[:, 0].astype(np.float32) / 8388607.0
            else:
                audio_data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483647.0
            
            # 重塑为多通道
            if channels > 1:
                audio_data = audio_data.reshape(-1, channels)
            
            # 计算音频指标
            peak_level = np.max(np.abs(audio_data))
            rms_level = np.sqrt(np.mean(audio_data ** 2))
            
            peak_db = 20 * np.log10(peak_level) if peak_level > 0 else -60
            rms_db = 20 * np.log10(rms_level) if rms_level > 0 else -60
            
            # 计算动态范围
            dynamic_range = peak_db - rms_db
            
            # 估算信噪比
            snr = self._estimate_snr(audio_data)
            
            # 检测削波
            clipping_samples = np.sum(np.abs(audio_data) > 0.99)
            clipping_percent = (clipping_samples / len(audio_data.flatten())) * 100
            
            # 频谱分析
            spectrum_analysis = self._analyze_spectrum(audio_data, sample_rate)
            
            report = {
                'file_info': {
                    'path': file_path,
                    'size_bytes': os.path.getsize(file_path),
                    'duration_seconds': len(audio_data) / sample_rate,
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'bit_depth': sample_width * 8
                },
                'audio_metrics': {
                    'peak_level_db': float(peak_db),
                    'rms_level_db': float(rms_db),
                    'dynamic_range_db': float(dynamic_range),
                    'snr_db': float(snr),
                    'clipping_percent': float(clipping_percent)
                },
                'spectrum_analysis': spectrum_analysis,
                'quality_assessment': self._assess_file_quality(peak_db, rms_db, clipping_percent, snr)
            }
            
            return report
            
        except Exception as e:
            return {
                'error': f"Failed to analyze file: {e}",
                'file_info': {'path': file_path}
            }
    
    def compare_recordings(self, file1: str, file2: str) -> Dict[str, Any]:
        """
        比较两个录制文件
        
        Args:
            file1: 第一个文件路径
            file2: 第二个文件路径
            
        Returns:
            Dict: 比较报告
        """
        analysis1 = self.analyze_file(file1)
        analysis2 = self.analyze_file(file2)
        
        if 'error' in analysis1 or 'error' in analysis2:
            return {
                'error': 'Failed to analyze one or both files',
                'file1_analysis': analysis1,
                'file2_analysis': analysis2
            }
        
        # 计算差异
        metrics1 = analysis1['audio_metrics']
        metrics2 = analysis2['audio_metrics']
        
        differences = {}
        for key in metrics1:
            if key in metrics2:
                differences[key] = metrics2[key] - metrics1[key]
        
        return {
            'file1': analysis1,
            'file2': analysis2,
            'differences': differences,
            'summary': self._generate_comparison_summary(differences)
        }
    
    def _assess_quality(self, session: RecordingSession) -> str:
        """评估会话质量"""
        peak_db = session.peak_level_db
        rms_db = session.rms_level_db
        drop_rate = (session.frames_dropped / max(session.frames_recorded, 1)) * 100
        
        if drop_rate > 5:
            return "poor"
        elif peak_db > -6:
            return "poor"  # 可能削波
        elif peak_db > -12 and rms_db > -20:
            return "excellent"
        elif peak_db > -18 and rms_db > -30:
            return "good"
        elif peak_db > -30:
            return "fair"
        else:
            return "poor"
    
    def _assess_file_quality(self, peak_db: float, rms_db: float, 
                           clipping_percent: float, snr_db: float) -> str:
        """评估文件质量"""
        if clipping_percent > 1:
            return "poor"
        elif peak_db > -6:
            return "poor"
        elif snr_db > 40 and peak_db > -12 and rms_db > -20:
            return "excellent"
        elif snr_db > 30 and peak_db > -18 and rms_db > -30:
            return "good"
        elif snr_db > 20:
            return "fair"
        else:
            return "poor"
    
    def _estimate_snr(self, audio_data: np.ndarray) -> float:
        """估算信噪比"""
        # 简单的SNR估算：假设最安静的10%是噪声
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # 计算RMS值的滑动窗口
        window_size = 1024
        rms_values = []
        
        for i in range(0, len(audio_data) - window_size, window_size):
            window = audio_data[i:i + window_size]
            rms = np.sqrt(np.mean(window ** 2))
            rms_values.append(rms)
        
        if not rms_values:
            return 0.0
        
        rms_values = np.array(rms_values)
        
        # 噪声水平：最小的10%
        noise_level = np.percentile(rms_values, 10)
        
        # 信号水平：最大的10%的平均值
        signal_level = np.mean(np.percentile(rms_values, 90))
        
        if noise_level > 0:
            snr = 20 * np.log10(signal_level / noise_level)
            return max(0, min(60, snr))  # 限制在合理范围内
        
        return 0.0
    
    def _analyze_spectrum(self, audio_data: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        """频谱分析"""
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # FFT分析
        fft_size = min(2048, len(audio_data))
        fft_data = np.fft.fft(audio_data[:fft_size])
        freqs = np.fft.fftfreq(fft_size, 1/sample_rate)
        
        # 只取正频率部分
        positive_freqs = freqs[:fft_size//2]
        magnitude = np.abs(fft_data[:fft_size//2])
        
        # 转换为dB
        magnitude_db = 20 * np.log10(magnitude + 1e-10)
        
        # 找到主要频率成分
        peak_idx = np.argmax(magnitude_db)
        dominant_freq = positive_freqs[peak_idx]
        
        # 频带能量分析
        bands = {
            'sub_bass': (20, 60),
            'bass': (60, 250),
            'low_mid': (250, 500),
            'mid': (500, 2000),
            'high_mid': (2000, 4000),
            'presence': (4000, 6000),
            'brilliance': (6000, 20000)
        }
        
        band_energy = {}
        for band_name, (low_freq, high_freq) in bands.items():
            band_mask = (positive_freqs >= low_freq) & (positive_freqs <= high_freq)
            if np.any(band_mask):
                band_energy[band_name] = float(np.mean(magnitude_db[band_mask]))
            else:
                band_energy[band_name] = -60.0
        
        return {
            'dominant_frequency_hz': float(dominant_freq),
            'spectral_centroid_hz': float(np.sum(positive_freqs * magnitude) / np.sum(magnitude)),
            'band_energy_db': band_energy
        }
    
    def _generate_recommendations(self, session: RecordingSession) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if session.peak_level_db > -6:
            recommendations.append("降低输入增益以避免削波")
        
        if session.rms_level_db < -40:
            recommendations.append("增加输入增益以提高信号强度")
        
        drop_rate = (session.frames_dropped / max(session.frames_recorded, 1)) * 100
        if drop_rate > 1:
            recommendations.append("检查系统性能，减少帧丢失")
        
        if len(session.processing_errors) > 0:
            recommendations.append("检查处理链路配置，解决处理错误")
        
        if session.dynamic_range_db < 20:
            recommendations.append("考虑使用更高的位深度以增加动态范围")
        
        return recommendations
    
    def _generate_comparison_summary(self, differences: Dict[str, float]) -> str:
        """生成比较摘要"""
        summary_parts = []
        
        if 'peak_level_db' in differences:
            diff = differences['peak_level_db']
            if abs(diff) > 3:
                direction = "higher" if diff > 0 else "lower"
                summary_parts.append(f"Peak level is {abs(diff):.1f}dB {direction}")
        
        if 'rms_level_db' in differences:
            diff = differences['rms_level_db']
            if abs(diff) > 3:
                direction = "higher" if diff > 0 else "lower"
                summary_parts.append(f"RMS level is {abs(diff):.1f}dB {direction}")
        
        if 'snr_db' in differences:
            diff = differences['snr_db']
            if abs(diff) > 5:
                direction = "better" if diff > 0 else "worse"
                summary_parts.append(f"SNR is {abs(diff):.1f}dB {direction}")
        
        return "; ".join(summary_parts) if summary_parts else "Files are similar in quality"




class AudioRecordingSystem:
    """
    音频录制和回放系统主类
    
    集成录制器、播放器、文件管理器和分析器
    """
    
    def __init__(self, config: RecordingConfig = None):
        self.config = config or RecordingConfig()
        
        # 初始化组件
        self.recorder = AudioRecorder(self.config)
        self.player = AudioPlayer()
        self.file_manager = RecordingFileManager(self.config.output_dir)
        self.analyzer = RecordingAnalyzer()
        self.control_interface = RecordingControlInterface(self.recorder, self.player)
        
        # 系统状态
        self.is_initialized = False
        self.system_callbacks: List[Callable] = []
    
    def initialize(self) -> bool:
        """
        初始化系统
        
        Returns:
            bool: 是否成功初始化
        """
        try:
            # 确保目录存在
            Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
            
            # 注册系统级回调
            self.control_interface.register_ui_callback(self._on_system_event)
            
            self.is_initialized = True
            return True
            
        except Exception as e:
            print(f"Failed to initialize recording system: {e}")
            return False
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        
        Returns:
            Dict: 系统状态信息
        """
        return {
            'initialized': self.is_initialized,
            'recorder_status': self.recorder.get_recording_status(),
            'player_status': self.player.get_playback_status(),
            'storage_stats': self.file_manager.get_storage_stats(),
            'config': {
                'sample_rate': self.config.sample_rate,
                'channels': self.config.channels,
                'bit_depth': self.config.bit_depth,
                'format': self.config.format.value,
                'output_dir': self.config.output_dir
            }
        }
    
    def process_audio_frame(self, frame: AudioFrame) -> bool:
        """
        处理音频帧（用于实时录制）
        
        Args:
            frame: 音频帧
            
        Returns:
            bool: 是否成功处理
        """
        if not self.is_initialized:
            return False
        
        return self.recorder.add_audio_frame(frame)
    
    def export_processed_audio(self, session_id: str, processed_data: np.ndarray, 
                             suffix: str = "_processed") -> Optional[str]:
        """
        导出处理后的音频
        
        Args:
            session_id: 会话ID
            processed_data: 处理后的音频数据
            suffix: 文件名后缀
            
        Returns:
            Optional[str]: 导出文件路径，失败返回None
        """
        try:
            export_path = self.file_manager.categories['processed'] / f"{session_id}{suffix}.wav"
            
            # 写入WAV文件
            with wave.open(str(export_path), 'wb') as wav_file:
                wav_file.setnchannels(self.config.channels)
                wav_file.setsampwidth(self.config.bit_depth // 8)
                wav_file.setframerate(self.config.sample_rate)
                
                # 转换数据格式
                if self.config.bit_depth == 16:
                    audio_data = (processed_data * 32767).astype(np.int16)
                elif self.config.bit_depth == 24:
                    audio_data = (processed_data * 8388607).astype(np.int32)
                else:
                    audio_data = (processed_data * 2147483647).astype(np.int32)
                
                wav_file.writeframes(audio_data.tobytes())
            
            return str(export_path)
            
        except Exception as e:
            print(f"Failed to export processed audio: {e}")
            return None
    
    def generate_session_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        生成会话报告
        
        Args:
            session_id: 会话ID
            
        Returns:
            Optional[Dict]: 会话报告，失败返回None
        """
        # 查找会话
        for session in self.recorder.session_history:
            if session.session_id == session_id:
                return self.analyzer.analyze_session(session)
        
        return None
    
    def cleanup(self):
        """清理系统资源"""
        try:
            # 停止录制和播放
            self.recorder.stop_recording()
            self.player.stop()
            
            # 清理回调
            self.system_callbacks.clear()
            
            self.is_initialized = False
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def register_system_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """注册系统级回调"""
        self.system_callbacks.append(callback)
    
    def _on_system_event(self, event_type: str, data: Dict[str, Any]):
        """系统事件处理"""
        for callback in self.system_callbacks:
            try:
                callback(event_type, data)
            except Exception:
                pass


# 工厂函数
def create_recording_system(config: Optional[RecordingConfig] = None) -> AudioRecordingSystem:
    """
    创建音频录制系统实例
    
    Args:
        config: 录制配置
        
    Returns:
        AudioRecordingSystem: 录制系统实例
    """
    system = AudioRecordingSystem(config)
    if system.initialize():
        return system
    else:
        raise RuntimeError("Failed to initialize audio recording system")


# 示例使用
if __name__ == "__main__":
    # 创建录制配置
    config = RecordingConfig(
        sample_rate=48000,
        channels=2,
        bit_depth=24,
        format=AudioFormat.WAV,
        output_dir="test_recordings"
    )
    
    # 创建录制系统
    recording_system = create_recording_system(config)
    
    # 获取系统状态
    status = recording_system.get_system_status()
    print("System Status:", status)
    
    # 开始录制
    result = recording_system.control_interface.start_recording("test_session")
    print("Start Recording:", result)
    
    # 模拟录制一些数据
    import time
    for i in range(10):
        # 创建模拟音频帧
        audio_data = np.random.randn(1024, 2) * 0.1  # 模拟音频数据
        frame = AudioFrame(
            frame_id=i,
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            bit_depth=24,
            data=audio_data,
            frame_size=1024
        )
        recording_system.process_audio_frame(frame)
        time.sleep(0.1)
    
    # 停止录制
    result = recording_system.control_interface.stop_recording()
    print("Stop Recording:", result)
    
    # 获取录制历史
    history = recording_system.control_interface.get_session_history()
    print("Recording History:", history)
    
    # 清理系统
    recording_system.cleanup()

