"""
Energy Saving Action Handler
Handles ML predictions and sends NETCONF XML messages to turn off cells when needed.
"""

import logging
import requests
from typing import Optional
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)


class NETCONFCLIENT:
    """Handles NETCONF XML generation and communication."""
    
    def __init__(self, host: str = "172.19.1.86", port: int = 8831, 
                 username: str = "admin", password: str = "netconf", 
                 gnodeb_id: str = "2623693"):
        """
        Initialize NETCONF client.
        
        Args:
            host: NETCONF server host (default: 172.19.1.86 - Kubernetes node IP)
            port: NETCONF server port (default: 8831 for O1 server)
            username: NETCONF username
            password: NETCONF password
            gnodeb_id: gNodeB ID for the managed element
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.gnodeb_id = gnodeb_id
        logger.info(f"NETCONF client configured: {host}:{port}")

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
        
        Args:
            index: Cell ID (e.g., 1, 2, or 3)
            
        Returns:
            NETCONF response XML or None on failure
        """
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
        
        Args:
            index: Cell ID (e.g., 1, 2, or 3)
            
        Returns:
            NETCONF response XML or None on failure
        """
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
    
    def __init__(self, ncmp_client, netconf_host: str = "172.19.1.86", 
                 netconf_port: int = 8831, netconf_user: str = "admin", 
                 netconf_pass: str = "netconf"):
        """
        Initialize the Energy Saving Action handler.
        
        Args:
            ncmp_client: NCMP client instance (for compatibility)
            netconf_host: NETCONF server host (default: 172.19.1.86 - node IP)
            netconf_port: NETCONF server port (default: 8831 for O1 server)
            netconf_user: NETCONF username
            netconf_pass: NETCONF password
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
        
        # Start date for predictions (2025-05-18 00:00:00)
        self.start_date = datetime(2025, 5, 18, 0, 0, 0)
        
        # Initialize NETCONF client
        self.netconf = NETCONFCLIENT(
            host=netconf_host,
            port=netconf_port,
            username=netconf_user,
            password=netconf_pass
        )
        logger.info(f"NETCONF client initialized: {netconf_host}:{netconf_port}")
        logger.info(f"Static prediction vector loaded: {len(self.static_predictions)} values")
    
    def _load_predictions(self) -> list:
        """
        Load prediction vector from JSON file generated by entrypoint.sh.
        Falls back to hardcoded values if file not found.
        
        Returns:
            List of prediction values (192 values for 2 days at 15-min intervals)
        """
        predictions_file = "/app/data/predictions_vector.json"
        
        # Try to load from file first
        if os.path.exists(predictions_file):
            try:
                with open(predictions_file, 'r') as f:
                    predictions = json.load(f)
                logger.info(f"Loaded {len(predictions)} predictions from {predictions_file}")
                return predictions
            except Exception as e:
                logger.warning(f"Failed to load predictions from file: {str(e)}")
                logger.warning(f"Falling back to hardcoded predictions")
        else:
            logger.warning(f"Predictions file not found: {predictions_file}")
            logger.warning(f"Falling back to hardcoded predictions")
        
        # Fallback to hardcoded predictions (original static values)
        return [
            0.074074, 0.092593, 0.055556, 0.055556, 0.037037, 0.037037, 0.037037, 0.037037,
            0.018519, 0.018519, 0.018519, 0.037037, 0.055556, 0.055556, 0.074074, 0.092593,
            0.11111, 0.12963, 0.12963, 0.166667, 0.166667, 0.166667, 0.166667, 0.166667,
            0.166667, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148,
            0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148,
            0.148148, 0.148148, 0.148148, 0.12963, 0.12963, 0.12963, 0.12963, 0.12963,
            0.12963, 0.12963, 0.12963, 0.11111, 0.11111, 0.11111, 0.11111, 0.11111,
            0.11111, 0.092593, 0.092593, 0.074074, 0.074074, 0.074074, 0.074074, 0.055556,
            0.055556, 0.055556, 0.037037, 0.037037, 0.037037, 0.037037, 0.018519, 0.018519,
            0.018519, 0.018519, 0.018519, 0.037037, 0.037037, 0.037037, 0.037037, 0.055556,
            0.055556, 0.055556, 0.055556, 0.074074, 0.074074, 0.074074, 0.092593, 0.092593,
            0.092593, 0.092593, 0.11111, 0.11111, 0.11111, 0.11111, 0.11111, 0.11111,
            0.074074, 0.092593, 0.055556, 0.055556, 0.037037, 0.037037, 0.037037, 0.037037,
            0.018519, 0.018519, 0.018519, 0.037037, 0.055556, 0.055556, 0.074074, 0.092593,
            0.11111, 0.12963, 0.12963, 0.166667, 0.166667, 0.166667, 0.166667, 0.166667,
            0.166667, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148,
            0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148, 0.148148,
            0.148148, 0.148148, 0.148148, 0.12963, 0.12963, 0.12963, 0.12963, 0.12963,
            0.12963, 0.12963, 0.12963, 0.11111, 0.11111, 0.11111, 0.11111, 0.11111,
            0.11111, 0.092593, 0.092593, 0.074074, 0.074074, 0.074074, 0.074074, 0.055556,
            0.055556, 0.055556, 0.037037, 0.037037, 0.037037, 0.037037, 0.018519, 0.018519,
            0.018519, 0.018519, 0.018519, 0.037037, 0.037037, 0.037037, 0.037037, 0.055556,
            0.055556, 0.055556, 0.055556, 0.074074, 0.074074, 0.074074, 0.092593, 0.092593,
            0.092593, 0.092593, 0.11111, 0.11111, 0.11111, 0.11111, 0.11111, 0.11111
        ]
    
    def initialize_o1_server(self, topo_file: str = "Topo_Example.xml"):
        """
        Send init-config to O1 server to configure the topology file.
        
        Args:
            topo_file: Name of the topology XML file (default: Topo_Example.xml)
        """
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
        # Check if we've run out of predictions
        if self.current_hour >= 48:  # 48 hours total (2 days)
            end_date = self.start_date + timedelta(hours=48)
            # Print summary at the end
            logger.info("\n" + "="*70)
            logger.info(" 48-HOUR SUMMARY")
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
    
    # OLD METHOD - Kept for reference but not used with static predictions
    # This method was used for real-time ML predictions
    def process_prediction(self, cell_name: str, cell_id: int, prediction_value: float) -> bool:
        """
        Process ML prediction and take action if needed.
        
        Args:
            cell_name: Name of the cell (e.g., "BRANGES_T1")
            cell_id: The cell ID (1, 2, or 3)
            prediction_value: The prediction value from ML model
            
        Returns:
            True if action was taken, False otherwise
        """
        logger.info(f" Processing prediction for {cell_name} (ID: {cell_id}): {prediction_value:.6f}")
        
        # Check if prediction suggests turning off the cell
        if prediction_value < self.prediction_threshold:
            logger.warning(f" Prediction {prediction_value:.6f} < threshold {self.prediction_threshold}")
            logger.warning(f"🔴 Cell {cell_name} should be turned OFF for energy saving!")
            
            # Get XML and log it
            xml_config = self.netconf.convert_to_xml(cell_id)
            logger.info(f" NETCONF XML config to turn OFF cell {cell_id}:")
            logger.info(f"\n{xml_config}")
            
            # Send NETCONF command to turn OFF the cell
            response = self.netconf.perform_action(cell_id)
            
            if response:
                logger.info(f" Successfully sent energy saving OFF command for {cell_name}")
                return True
            else:
                logger.error(f" Failed to send energy saving OFF command for {cell_name}")
                return False
        else:
            logger.info(f" Cell {cell_name} is operating normally (prediction: {prediction_value:.6f})")
            logger.info(f"🟢 Cell {cell_name} should remain ON or be turned ON")
            
            # Get XML and log it
            xml_config = self.netconf.convert_to_xml_1(cell_id)
            logger.info(f"NETCONF XML config to turn ON cell {cell_id}:")
            logger.info(f"\n{xml_config}")
            
            # Send NETCONF command to turn ON the cell
            response = self.netconf.perform_action_on(cell_id)
            
            if response:
                logger.info(f" Successfully sent energy saving ON command for {cell_name}")
                return True
            else:
                logger.error(f" Failed to send energy saving ON command for {cell_name}")
                return False

