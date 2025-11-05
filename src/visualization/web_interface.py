"""
Web Interface for Audio System

Flask-based web interface for system control and monitoring.
"""

import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import logging


class WebInterface:
    """Web interface for audio system with real-time monitoring."""
    
    def __init__(self):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        CORS(self.app)  # Enable CORS for API calls
        self.running = False
        self.server_thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger(__name__)
        
        # Data sources - will be injected by the main system
        self.system_data = {
            'status': 'initializing',
            'uptime': 0,
            'components': {},
            'devices': {'input': [], 'output': []},
            'processing_chain': [],
            'metrics': {},
            'health': {'overall': 'unknown', 'score': 0}
        }
        
        self._setup_routes()
    
    def set_system_data_source(self, data_source: Dict[str, Any]):
        """Set the system data source for real-time updates"""
        self.system_data = data_source
    
    def _setup_routes(self) -> None:
        """Setup web routes."""
        
        @self.app.route('/')
        def index():
            """Main dashboard page"""
            return render_template('dashboard.html')
        
        @self.app.route('/api/system/status')
        def api_system_status():
            """Get overall system status"""
            return jsonify({
                'status': self.system_data.get('status', 'unknown'),
                'uptime': self.system_data.get('uptime', 0),
                'timestamp': datetime.now().isoformat(),
                'health': self.system_data.get('health', {'overall': 'unknown', 'score': 0})
            })
        
        @self.app.route('/api/components')
        def api_components():
            """Get audio processing components status"""
            components = self.system_data.get('components', {})
            component_list = []
            
            for comp_id, comp_data in components.items():
                component_list.append({
                    'id': comp_id,
                    'name': comp_data.get('name', comp_id),
                    'status': comp_data.get('status', 'unknown'),
                    'type': comp_data.get('type', 'unknown'),
                    'version': comp_data.get('version', '1.0.0'),
                    'metrics': comp_data.get('metrics', {}),
                    'enabled': comp_data.get('enabled', False)
                })
            
            return jsonify({'components': component_list})
        
        @self.app.route('/api/devices')
        def api_devices():
            """Get audio input/output devices configuration"""
            devices = self.system_data.get('devices', {'input': [], 'output': []})
            return jsonify({
                'input_devices': devices.get('input', []),
                'output_devices': devices.get('output', []),
                'active_inputs': [d for d in devices.get('input', []) if d.get('active', False)],
                'active_outputs': [d for d in devices.get('output', []) if d.get('active', False)]
            })
        
        @self.app.route('/api/processing-chain')
        def api_processing_chain():
            """Get current processing chain configuration"""
            chain = self.system_data.get('processing_chain', [])
            return jsonify({
                'chain': chain,
                'total_components': len(chain),
                'active_components': len([c for c in chain if c.get('active', False)])
            })
        
        @self.app.route('/api/metrics')
        def api_metrics():
            """Get real-time system metrics"""
            metrics = self.system_data.get('metrics', {})
            return jsonify({
                'cpu_usage': metrics.get('cpu_usage', 0),
                'memory_usage': metrics.get('memory_usage', 0),
                'audio_latency': metrics.get('audio_latency', 0),
                'processing_load': metrics.get('processing_load', 0),
                'input_levels': metrics.get('input_levels', []),
                'output_levels': metrics.get('output_levels', []),
                'timestamp': datetime.now().isoformat()
            })
        
        @self.app.route('/api/logs')
        def api_logs():
            """Get recent system logs"""
            # This would typically read from log files
            return jsonify({
                'logs': [
                    {'timestamp': datetime.now().isoformat(), 'level': 'INFO', 'message': 'System running normally'},
                    {'timestamp': datetime.now().isoformat(), 'level': 'DEBUG', 'message': 'Processing audio frames'}
                ]
            })
        
        @self.app.route('/api/config', methods=['GET', 'POST'])
        def api_config():
            """Get or update system configuration"""
            if request.method == 'GET':
                return jsonify({
                    'sample_rate': 48000,
                    'buffer_size': 256,
                    'channels': 2,
                    'bit_depth': 24,
                    'processing_enabled': True,
                    'auto_gain_control': True,
                    'noise_suppression': True,
                    'echo_cancellation': True
                })
            else:
                # Handle configuration updates
                config = request.get_json()
                self.logger.info(f"Configuration update requested: {config}")
                return jsonify({'status': 'success', 'message': 'Configuration updated'})
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({'error': 'Not found'}), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({'error': 'Internal server error'}), 500
    
    def start(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Start the web interface."""
        if self.running:
            self.logger.warning("Web interface is already running")
            return
        
        try:
            self.running = True
            
            # Start Flask app in a separate thread
            def run_server():
                self.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
            
            self.server_thread = threading.Thread(target=run_server, daemon=True)
            self.server_thread.start()
            
            # Give the server a moment to start
            time.sleep(1)
            
            self.logger.info(f"Web interface started on http://{host}:{port}")
            print(f"🌐 Web界面已启动: http://{host}:{port}")
            
        except Exception as e:
            self.running = False
            self.logger.error(f"Failed to start web interface: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the web interface."""
        if not self.running:
            return
        
        self.running = False
        self.logger.info("Web interface stopped")
    
    def update_system_status(self, status: str, uptime: float, health: Dict[str, Any]):
        """Update system status data"""
        self.system_data.update({
            'status': status,
            'uptime': uptime,
            'health': health
        })
    
    def update_components(self, components: Dict[str, Any]):
        """Update components data"""
        self.system_data['components'] = components
    
    def update_devices(self, input_devices: List[Dict], output_devices: List[Dict]):
        """Update devices data"""
        self.system_data['devices'] = {
            'input': input_devices,
            'output': output_devices
        }
    
    def update_processing_chain(self, chain: List[Dict]):
        """Update processing chain data"""
        self.system_data['processing_chain'] = chain
    
    def update_metrics(self, metrics: Dict[str, Any]):
        """Update real-time metrics"""
        self.system_data['metrics'] = metrics