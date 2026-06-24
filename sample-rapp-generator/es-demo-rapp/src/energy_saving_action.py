"""
Energy Saving Action Handler
Handles ML predictions and sends NETCONF XML messages to turn off cells when needed.
"""

import logging
import random
import requests
from typing import Optional
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)


class NETCONFCLIENT:
    """Handles NETCONF XML generation and communication."""

    def __init__(self, gnodeb_id: str = "2623693"):
        """
        Initialize NETCONF client.
        Configuration is read from config.json (O1 section).
        Any value can be overridden by the corresponding environment variable.
        """
        # Load O1 config from config.json as base; env vars override
        _cfg_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(_cfg_path, 'r') as _f:
                _o1 = json.load(_f).get('O1', {})
        except Exception:
            _o1 = {}

        self.host     = os.environ.get('O1_SERVER_HOST') or _o1.get('host')
        _port_raw     = os.environ.get('O1_SERVER_PORT') or _o1.get('port')
        self.gnodeb_id = gnodeb_id

        missing = [k for k, v in [('host', self.host), ('port', _port_raw)] if not v]
        if missing:
            logger.warning(
                f"O1 server config missing field(s): {missing}. "
                f"Set them via env vars (O1_SERVER_HOST, O1_SERVER_PORT) or in the .env file. "
                f"NETCONF actions will be skipped until config is provided."
            )
            self._configured = False
            self.port = None
        else:
            self.port = int(_port_raw)
            self._configured = True
            logger.info(f"NETCONF client configured: {self.host}:{self.port}")

    def convert_to_xml(self, index: int) -> str:
        """
        Create XML config to turn OFF a cell (energy saving mode).
        
        Args:
            index: Cell ID (e.g., 16 for BRANGES_T1)
            
        Returns:
            XML string for NETCONF edit-config
        """
        # RPC wrapper matching O1 server expected format
        rpc = ET.Element("rpc", xmlns="urn:ietf:params:xml:ns:netconf:base:1.0")
        rpc.set("message-id", "1")
        
        edit_config = ET.SubElement(rpc, "edit-config")
        target = ET.SubElement(edit_config, "target")
        ET.SubElement(target, "running")
        
        config = ET.SubElement(edit_config, "config")
        managed_element = ET.SubElement(config, "ManagedElement", xmlns="urn:3gpp:sa5:_3gpp-common-managed-element")
        id_element = ET.SubElement(managed_element, "id")
        id_element.text = self.gnodeb_id
        gnb_ucp_function = ET.SubElement(managed_element, "GNBCUCPFunction", xmlns="urn:3gpp:sa5:_3gpp-nr-nrm-gnbcucpfunction")
        id_element = ET.SubElement(gnb_ucp_function, "id")
        id_element.text = "1"
        nr_cell_cu = ET.SubElement(gnb_ucp_function, "NRCellCU", xmlns="urn:3gpp:sa5:_3gpp-nr-nrm-nrcellcu")
        id_element = ET.SubElement(nr_cell_cu, "id")
        id_element.text = str(index)
        ces_management_function = ET.SubElement(nr_cell_cu, "CESManagementFunction", xmlns="urn:3gpp:sa5:_3gpp-nr-nrm-cesmanagementfunction")
        id_element = ET.SubElement(ces_management_function, "id")
        id_element.text = str(index)  # Using same ID as cell
        attributes = ET.SubElement(ces_management_function, "attributes")
        energy_saving_control = ET.SubElement(attributes, "energySavingControl")
        energy_saving_control.text = "toBeEnergySaving"
        energy_saving_state = ET.SubElement(attributes, "energySavingState")
        energy_saving_state.text = "isNotEnergySaving"
        return ET.tostring(rpc, encoding="unicode")

    def convert_to_xml_1(self, index: int) -> str:
        """
        Create XML config to turn ON a cell (exit energy saving mode).
        
        Args:
            index: Cell ID (e.g., 16 for BRANGES_T1)
            
        Returns:
            XML string for NETCONF edit-config
        """
        # RPC wrapper matching O1 server expected format
        rpc = ET.Element("rpc", xmlns="urn:ietf:params:xml:ns:netconf:base:1.0")
        rpc.set("message-id", "1")
        
        edit_config = ET.SubElement(rpc, "edit-config")
        target = ET.SubElement(edit_config, "target")
        ET.SubElement(target, "running")
        
        config = ET.SubElement(edit_config, "config")
        managed_element = ET.SubElement(config, "ManagedElement", xmlns="urn:3gpp:sa5:_3gpp-common-managed-element")
        id_element = ET.SubElement(managed_element, "id")
        id_element.text = self.gnodeb_id
        gnb_ucp_function = ET.SubElement(managed_element, "GNBCUCPFunction", xmlns="urn:3gpp:sa5:_3gpp-nr-nrm-gnbcucpfunction")
        id_element = ET.SubElement(gnb_ucp_function, "id")
        id_element.text = "1"
        nr_cell_cu = ET.SubElement(gnb_ucp_function, "NRCellCU", xmlns="urn:3gpp:sa5:_3gpp-nr-nrm-nrcellcu")
        id_element = ET.SubElement(nr_cell_cu, "id")
        id_element.text = str(index)
        ces_management_function = ET.SubElement(nr_cell_cu, "CESManagementFunction", xmlns="urn:3gpp:sa5:_3gpp-nr-nrm-cesmanagementfunction")
        id_element = ET.SubElement(ces_management_function, "id")
        id_element.text = str(index)  # Using same ID as cell
        attributes = ET.SubElement(ces_management_function, "attributes")
        energy_saving_control = ET.SubElement(attributes, "energySavingControl")
        energy_saving_control.text = "toBeNotEnergySaving"
        energy_saving_state = ET.SubElement(attributes, "energySavingState")
        energy_saving_state.text = "isNotEnergySaving"
        return ET.tostring(rpc, encoding="unicode")

    def perform_action(self, index: int) -> Optional[str]:
        """
        Perform NETCONF edit-config to turn OFF a cell.
        """
        if not self._configured:
            logger.warning(f"O1 server not configured — skipping turn-OFF for cell {index}")
            return None
        xml_data = self.convert_to_xml(index)
        try:
            # Send HTTP POST directly to O1 server (which expects XML-RPC style)
            url = f"http://{self.host}:{self.port}/"
            headers = {"Content-Type": "text/xml"}
            response = requests.post(url, data=xml_data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Successfully turned OFF cell {index}")
                logger.debug(f"O1 Server Response:\n{response.text}")
                return response.text
            else:
                logger.error(f"O1 server returned status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to turn OFF cell {index}: {str(e)}")
            return None

    def perform_action_on(self, index: int) -> Optional[str]:
        """
        Perform NETCONF edit-config to turn ON a cell.
        """
        if not self._configured:
            logger.warning(f"O1 server not configured — skipping turn-ON for cell {index}")
            return None
        xml_data = self.convert_to_xml_1(index)
        try:
            # Send HTTP POST directly to O1 server (which expects XML-RPC style)
            url = f"http://{self.host}:{self.port}/"
            headers = {"Content-Type": "text/xml"}
            response = requests.post(url, data=xml_data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Successfully turned ON cell {index}")
                logger.debug(f"O1 Server Response:\n{response.text}")
                return response.text
            else:
                logger.error(f"O1 server returned status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to turn ON cell {index}: {str(e)}")
            return None


class EnergySavingAction:
    """Handles energy saving actions based on static predictions."""
    
    def __init__(self, ncmp_client, start_date=None):
        """
        Initialize the Energy Saving Action handler.

        Args:
            ncmp_client: NCMP client instance (for compatibility)
        """
        self.ncmp_client = ncmp_client
        self.turn_off_threshold = 0.1  # Turn OFF if prediction <= 0.1
        self.turn_on_threshold = 0.14  # Turn ON if prediction >= 0.14
        
        # Load predictions from file (generated by entrypoint.sh)
        self.static_predictions = self._load_predictions()
        
        # Tracking state
        self.current_hour = 0  # Current hour index (0-47 for 2 days)
        self.cell_state = 1  # Cell state flag: 1=ON, 0=OFF (starts as ON)
        self.actions_taken = 0  # Counter for total actions taken
        
        # Start date for predictions (derived from InfluxDB by caller when available)
        self.start_date = start_date or datetime.now().replace(minute=0, second=0, microsecond=0)
        
        # Initialize NETCONF client — reads host/port/user/password from config.json
        self.netconf = NETCONFCLIENT()
        logger.info(f"NETCONF client initialized: {self.netconf.host}:{self.netconf.port}")
        logger.info(f"Static prediction vector loaded: {len(self.static_predictions)} values")

    
    
    def _load_predictions(self) -> list:
        """
        Load prediction vector from JSON file generated by entrypoint.sh.
        Falls back to random values if file not found.
        
        Returns:
            List of prediction values (N values for n days at 15-min intervals)
        """
        predictions_file = "/app/data/predictions_vector.json"
        
        # Try to load from file first
        if os.path.exists(predictions_file):
            try:
                with open(predictions_file, 'r') as f:
                    # Save directly to self.predictions
                    self.predictions = json.load(f)
                logger.info(f"Loaded {len(self.predictions)} predictions from {predictions_file}")
                return self.predictions
            except Exception as e:
                logger.warning(f"Failed to load predictions from file: {str(e)}")
                logger.warning(f"Falling back to random predictions")
        else:
            logger.warning(f"Predictions file not found: {predictions_file}")
            logger.warning(f"Falling back to random predictions")
        
        # Fallback path: Initialize and fill self.predictions
        self.predictions = []
        for _ in range(192):  
            val = round(random.uniform(0.01, 0.20), 6)
            self.predictions.append(val)

        # Return self.predictions instead of the local variable
        return self.predictions
    

    def total_hours(self) -> int:
        """Return the number of hourly periods available in the prediction vector."""
        # This will now work perfectly every time!
        return len(self.predictions) // 4
    
    def initialize_o1_server(self, topo_file: str = "Topo_Example.xml"):
        """
        Send init-config to O1 server to configure the topology file.
        
        Args:
            topo_file: Name of the topology XML file (default: Topo_Example.xml)
        """
        if not self.netconf._configured:
            logger.info("O1 server not configured — skipping initialization. "
                        "Set O1 server details in values.yaml (o1Server section) or via "
                        "O1_SERVER_HOST / O1_SERVER_PORT / O1_SERVER_USER / O1_SERVER_PASS env vars.")
            return False

        init_config_xml = f"""<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="0">
    <init-config>
        <config>
            <file>{topo_file}</file>
        </config>
    </init-config>
</rpc>"""
        
        try:
            url = f"http://{self.netconf.host}:{self.netconf.port}/"
            headers = {"Content-Type": "text/xml"}
            response = requests.post(url, data=init_config_xml, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"O1 server initialized with topology file: {topo_file}")
                logger.debug(f"O1 Server init-config response:\n{response.text}")
                return True
            else:
                logger.warning(f" O1 server init-config returned status {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Failed to initialize O1 server: {str(e)}")
            logger.warning(f"Make sure O1 server is running on {self.netconf.host}:{self.netconf.port}")
            return False
    
    def make_hourly_decision(self, cell_id: int = 1, cell_name: str = "BRANGES_T1") -> bool:
        """
        Make hourly decision based on max of 4 predictions (15-min intervals).
        
        Args:
            cell_id: Cell ID (1 for BRANGES_T1)
            cell_name: Cell name
            
        Returns:
            True if action was taken, False otherwise
        """

        total_hours = self.total_hours()
        # Check if we've run out of predictions
        if self.current_hour >= total_hours:
            end_date = self.start_date + timedelta(hours=total_hours)
            # Print summary at the end
            logger.info("\n" + "="*70)
            logger.info(f" {total_hours}-HOUR SUMMARY")
            logger.info(f"   Period: {self.start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")
            logger.info(f"   Total actions taken: {self.actions_taken}")
            logger.info(f"   Final cell state: {'ON' if self.cell_state == 1 else 'OFF'}")
            logger.info("="*70 + "\n")
            return False
        
        # Get the 4 predictions for this hour (indices: hour*4 to hour*4+3)
        start_idx = self.current_hour * 4
        end_idx = min(start_idx + 4, len(self.static_predictions))
        
        if start_idx >= len(self.static_predictions):
            logger.warning(f" Prediction index out of range: {start_idx}")
            return False
        
        hour_predictions = self.static_predictions[start_idx:end_idx]
        max_prediction = max(hour_predictions)
        
        # Calculate current timestamp
        current_timestamp = self.start_date + timedelta(hours=self.current_hour)
        timestamp_str = current_timestamp.strftime('%Y-%m-%d %H:%M')
        
        # Decision logic
        action_taken = False
        
        if max_prediction <= self.turn_off_threshold:
            if self.cell_state == 1:  # Cell is currently ON - TAKE ACTION
                time_str = current_timestamp.strftime('%I:%M %p on %Y-%m-%d')  # e.g., "01:00 PM on 2025-05-18"
                logger.warning(f"🔴 [{timestamp_str}] Turning OFF {cell_name} at {time_str} (max prediction: {max_prediction:.6f})")
                
                response = self.netconf.perform_action(cell_id)
                if response:
                    self.cell_state = 0  # Update flag to OFF
                    self.actions_taken += 1
                    action_taken = True
                else:
                    logger.error(f" Failed to turn OFF {cell_name} at {time_str}")
            # Skip logging if cell is already OFF
                
        elif max_prediction >= self.turn_on_threshold:
            if self.cell_state == 0:  # Cell is currently OFF - TAKE ACTION
                time_str = current_timestamp.strftime('%I:%M %p on %Y-%m-%d')  # e.g., "03:00 AM on 2025-05-18"
                logger.info(f"🟢 [{timestamp_str}] Turning ON {cell_name} at {time_str} (max prediction: {max_prediction:.6f})")
                
                response = self.netconf.perform_action_on(cell_id)
                if response:
                    self.cell_state = 1  # Update flag to ON
                    self.actions_taken += 1
                    action_taken = True
                else:
                    logger.error(f" Failed to turn ON {cell_name} at {time_str}")
            # Skip logging if cell is already ON
        # Skip logging for neutral zone - reduces noise
        
        # Move to next hour
        self.current_hour += 1
        
        return action_taken
    


