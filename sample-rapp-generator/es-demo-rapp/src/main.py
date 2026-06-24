#  ============LICENSE_START===============================================
#  Copyright (C) 2025 OpenInfra Foundation Europe. All rights reserved.
#  ========================================================================
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#  ============LICENSE_END=================================================
#

import argparse
import time
import pandas as pd
import schedule
from threading import Lock
import logging
from dotenv import load_dotenv
import requests

# Load .env file before reading any os.environ values (optional override)
load_dotenv()

from data import DATABASE
from assist import ASSIST
from ncmp_client import NCMP_CLIENT
from teiv_client import TEIV_CLIENT
from energy_saving_action import EnergySavingAction
import json
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Version tracking for deployment verification
RAPP_VERSION = "v1.0.33-o1-server-fix"
BUILD_INFO = "O1 server connection fixed: localhost:8831 with environment variable support (hostNetwork enabled)"

# CSV data configuration
CSV_FILE_PATH = os.environ.get('CSV_FILE_PATH', '')
CSV_LOAD_ON_STARTUP = os.environ.get('CSV_LOAD_ON_STARTUP', 'false').lower() == 'true'

# Resolve absolute path if provided
if CSV_FILE_PATH:
    CSV_FILE_PATH = os.path.abspath(CSV_FILE_PATH)

# O1 NETCONF server configuration is read directly from config.json by NETCONFCLIENT


class ESrapp():
    def __init__(self, generate_db_data=True, use_sme_db=False, random_predictions=False, load_csv_data=True):

        logger.info("="*70)
        logger.info(" ENERGY SAVING rAPP INITIALIZING ")
        logger.info(f"Version: {RAPP_VERSION}")
        logger.info(f"Build Info: {BUILD_INFO}")
        logger.info(f"Configuration: generate_db_data={generate_db_data}, use_sme_db={use_sme_db}, random_predictions={random_predictions}, load_csv_data={load_csv_data}")
        logger.info(f"CSV Configuration: path={CSV_FILE_PATH}, exists={os.path.exists(CSV_FILE_PATH)}, load_on_startup={CSV_LOAD_ON_STARTUP}")
        logger.info("="*70)

        # Initialize the local storage of cell status
        self.cell_power_status = {}
        self.teiv_cells = {}

        # Initialize the database and prediction client
        self.db = DATABASE()
        self.assist=ASSIST()

        self.random_predictions = random_predictions

        if use_sme_db:
            # Get the InfluxDB URL from SME
            self.db.get_url_from_sme()

        self.db.connect()

        if load_csv_data:
            # Load CSV data into InfluxDB using the local DATABASE helper
            if os.path.exists(CSV_FILE_PATH):
                logger.info(f"✓ Loading CSV data from: {CSV_FILE_PATH}")
                self.db.load_csv_to_influxdb(CSV_FILE_PATH)
                first_csv_time = self.db.get_first_measurement_time(measurement_name="o-ran-pm")
                if first_csv_time is not None:
                    logger.info(
                        f"First detected _time in InfluxDB for measurement 'o-ran-pm': "
                        f"{first_csv_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                else:
                    logger.warning("No _time found in InfluxDB for measurement 'o-ran-pm' after CSV load.")
            else:
                logger.warning(f"✗ CSV file not found at {CSV_FILE_PATH} — skipping CSV load")
                if generate_db_data:
                    logger.info("Generating synthetic data instead...")
                    self.db.generate_synthetic_data()
        elif generate_db_data:
            # Use local InfluxDB and generate synthetic data - only for local testing
            logger.info("Generating synthetic data...")
            self.db.generate_synthetic_data()


        self.threshold = 50
        # Initialize the NCMP client - allows us to query the cells from the RAN and power them on/off
        self.ncmp_client = NCMP_CLIENT()
        self.index = 1

        start_date = self.db.get_first_measurement_time(measurement_name="o-ran-pm")
        if start_date is not None:
            logger.info(f"Using first InfluxDB timestamp as start date: {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            logger.warning("Could not find first _time for measurement 'o-ran-pm'. Falling back to current hour.")

        # Initialize the Energy Saving Action handler
        self.energy_action = EnergySavingAction(self.ncmp_client, start_date=start_date)
        logger.info(f" Energy Saving Action handler initialized (O1 Server: {self.energy_action.netconf.host}:{self.energy_action.netconf.port})")
        
        # Initialize O1 server with topology configuration
        self.energy_action.initialize_o1_server()

        # Get the ODU function ID from the database
        self.teiv_client = TEIV_CLIENT()
        #self.get_teiv_cells()
        # Create Policy Manager instance
        #self.policy_manager = PolicyManager(base_url="http://192.168.8.111:32080/a1mediator/A1-P/v2", policy_type_id=20008)

        # Create policy type and policy instance
        #self.policy_manager.create_policy_type()
        self.inference_lock = Lock()
        self._running = False


    def entry(self):
        if self._running:
            logger.warning("ES rApp is already running")
            return

        total_hours = self.energy_action.total_hours()
        logger.info(" TRACE: Starting main entry loop - STATIC PREDICTION MODE!")
        logger.info(f" TRACE: Running version {RAPP_VERSION}")
        logger.info(f" Processing all {total_hours} hours with hourly decisions (running every 10 seconds for testing)")
        
        self._running = True
        # Run every 10 seconds to process each hour (for testing/demo purposes)
        # In production, you might want 3600 seconds (1 hour) per iteration
        self.job = schedule.every(10).seconds.do(self.safe_inference)
        last_run = 0

        try:
            while self._running:
                # Check if we've processed all predictions
                if self.energy_action.current_hour >= self.energy_action.total_hours():
                    logger.info(" All predictions have been processed. Stopping application.")
                    self._running = False
                    break
                
                now = time.time()
                if now - last_run >= 10:  # 10 second interval to process each hour
                    self.safe_inference()
                    last_run = now
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("ES rApp shutting down gracefully")
        except Exception as e:
            logger.error(f"Error in entry loop: {str(e)}", exc_info=True)
        finally:
            try:
                schedule.cancel_job(self.job)
            except:
                pass
            self._running = False
            try:
                if self.inference_lock.locked():
                    self.inference_lock.release()
            except:
                pass

    def safe_inference(self):
        if not self.inference_lock.acquire(blocking=False):
            logger.warning("Previous inference still running, skipping this iteration")
            return

        try:
            self.inference()
        finally:
            self.inference_lock.release()
    # Send data to ML rApp
    def inference(self):
        """
        Processes one hour at a time from the prediction vector.
        
        Each call processes the next hour (4 predictions at 15-min intervals).
        Will process all available prediction hours and then stop.
        """
        # Check if we've processed all hours
        if self.energy_action.current_hour >= self.energy_action.total_hours():
            return
        
        # Process the next hour's predictions for BRANGES_T1 sector using cell ID 16
        
        action_taken = self.energy_action.make_hourly_decision(cell_id=16, cell_name="BRANGES_T1")
        
        # OLD CODE BELOW - Using real-time data from InfluxDB and ML predictions
        # This is commented out as we now use static predictions
        """
        #logger.info(f" TRACE: Running inference cycle (version: {RAPP_VERSION})")
        
        data = self.db.read_data()

        if data.empty:
            logger.info("No data to process... skipping this iteration of inference.")
            return

       # logger.info(f" TRACE: Processing {len(data)} data points")
        
        data_mapping = self.mapping(data)
        # Group the data by CellID and _measurement. This means that even if cell ids are the same, but the measurement is different, they will be processed separately.
        groups = data_mapping.groupby(["CellID", "_measurement"])
        
        # Define the order of cells to process
        cell_order = ['BRANGES_T1', 'BRANGES_T2', 'BRANGES_T3']
        
        # Process cells in order
        for cell_name in cell_order:
            # Find the group for this cell
            group_found = False
            for group_name, group_data in groups:
                cell_id_name = group_data['CellID'].iloc[0]
                
                if cell_id_name != cell_name:
                    continue
                    
                group_found = True
                logger.info(f" Processing cell: {cell_id_name}")
                
                # Get the cell ID number (1 for T1, 2 for T2, 3 for T3)
                cell_mapping = {'BRANGES_T1': 1, 'BRANGES_T2': 2, 'BRANGES_T3': 3}
                cell_id_number = cell_mapping.get(cell_id_name, 0)
                
                # Take only first 1 data point for this cell (ONE value)
                limited_data = group_data.head(1)
                
                json_data = self.generate_json_data(limited_data)
                logger.info(f" Send 1 value to ML rApp for {group_name}: {json_data}")
                status_code, response_text = self.assist.send_request_to_server(json_data, randomize=self.random_predictions)
                logger.info(f" Received prediction for {cell_name}: {response_text}")
                
                # Parse the prediction value
                try:
                    import json as json_lib
                    prediction_dict = json_lib.loads(response_text)
                    prediction_value = prediction_dict['predictions'][0][0]
                    
                    # Use the energy_action handler to process the prediction
                    self.energy_action.process_prediction(cell_id_name, cell_id_number, prediction_value)
                    
                except Exception as e:
                    logger.error(f" Error parsing prediction: {e}")
                
                break  # Move to next cell in order
            
            if not group_found:
                logger.warning(f"  No data found for cell {cell_name}")
                continue
            
            # Continue with action logic for the current cell
            group_data = limited_data
            if not self.check_and_perform_action(response_text):
                cell_id_name = group_data['CellID'].iloc[0]
                # Check if the cell is in TEIV
                self.check_cell_in_teiv(cell_id_name)
                du_name = self.extract_managed_element(group_data['_measurement'].iloc[0])
                cell_with_node = cell_id_name + "_" + du_name
                logger.info(f"Turn on the cell {group_name}")
                # Wait for 3 seconds before performing the action
                time.sleep(3)

                if cell_with_node not in self.cell_power_status:
                    logger.debug(f"Cell {cell_with_node} not in local cache. Adding it...")
                    self.cell_power_status[cell_with_node] = "off"
                # Check if the cell is already powered on
                if self.cell_power_status[cell_with_node] == "on":
                    logger.debug(f"Cell {cell_with_node} is already powered on.")
                    # continue
                else:
                    self.ncmp_client.power_on_cell(cell_with_node)
                    self.cell_power_status[cell_with_node] = "on"
            else:
                du_name = self.extract_managed_element(group_data['_measurement'].iloc[0])
                cell_id_name = group_data['CellID'].iloc[0]
                # Check if the cell is in TEIV
                self.check_cell_in_teiv(cell_id_name)
                cell_with_node = cell_id_name + "_" + du_name
                logger.info(f"Turn off the cell {group_name}")
                # Wait for 3 seconds before performing the action
                time.sleep(3)

                if cell_with_node not in self.cell_power_status:
                    logger.debug(f"Cell {cell_with_node} not in local cache. Adding it...")
                    self.cell_power_status[cell_with_node] = "on"

                if self.cell_power_status[cell_with_node] == "off":
                    logger.debug(f"Cell {cell_with_node} is already powered off.")
                    # continue
                else:
                    if self.ncmp_client.power_off_cell(cell_with_node):
                        self.cell_power_status[cell_with_node] = "off"
        """

    def extract_managed_element(self, measurement):
        if '=' not in measurement or ',' not in measurement:
            return measurement

        parts = measurement.split(',')
        for part in parts:
            if part.startswith('ManagedElement='):
                return part.split('=')[1]

        return measurement
    
    # Generate the input data for MLOps cycle
    def generate_json_data(self, data):
        import numpy as np
        
        # Check if this is CSV data (BRANGES format) or synthetic data
        if "PRB_DL" in data.columns and "USERTHROUGHPUTDL_MBPS" in data.columns and "ENDC_AVG_RRC_CONNECTED_USERS" in data.columns:
            # CSV data format - use PRB_DL, USERTHROUGHPUTDL_MBPS, ENDC_AVG_RRC_CONNECTED_USERS
            logger.debug("Detected CSV data format - using PRB_DL, USERTHROUGHPUTDL_MBPS, ENDC_AVG_RRC_CONNECTED_USERS")
            
            # Replace NaN values with 0.0 before converting to list
            data_clean = data[["PRB_DL", "USERTHROUGHPUTDL_MBPS", "ENDC_AVG_RRC_CONNECTED_USERS"]].fillna(0.0)
            
            prb_dl_values = data_clean["PRB_DL"].tolist()
            throughput_dl_values = data_clean["USERTHROUGHPUTDL_MBPS"].tolist()
            rrc_connected_values = data_clean["ENDC_AVG_RRC_CONNECTED_USERS"].tolist()

            instances = [
                [
                    [prb, throughput, rrc]
                    for prb, throughput, rrc in zip(
                        prb_dl_values,
                        throughput_dl_values,
                        rrc_connected_values
                    )
                ]
            ]
        else:
            # Synthetic data format - use original measurements
            logger.debug("Detected synthetic data format - using DRB.UEThpUl, RRU.PrbUsedUl, PEE.AvgPower")
            
            # Replace NaN values with 0.0 before converting to list
            data_clean = data[["DRB.UEThpUl", "RRU.PrbUsedUl", "PEE.AvgPower"]].fillna(0.0)
            
            drb_ue_thp_ul_values = data_clean["DRB.UEThpUl"].tolist()
            rru_prb_used_ul_values = data_clean["RRU.PrbUsedUl"].tolist()
            pee_avg_power_values = data_clean["PEE.AvgPower"].tolist()

            instances = [
                [
                    [drb, rru, pee]
                    for drb, rru, pee in zip(
                        drb_ue_thp_ul_values,
                        rru_prb_used_ul_values,
                        pee_avg_power_values
                    )
                ]
            ]

        json_data = {"signature_name": "serving_default", "instances": instances}
        logger.debug(f'Generated JSON data: {json_data}')
        return json_data
    # Mapping CellID and Cell name
    def mapping(self, data):
        data = pd.DataFrame(data)
        # TODO: This regex is not likely to match all cell IDs. Will need to be improved.
        data[['S', 'B', 'C']] = data['CellID'].str.extract(r'S(\d+)-[BN](\d+)-C(\d+)')
        data[['S', 'B', 'C']] = data[['S', 'B', 'C']].astype(int)
        data = data.sort_values(by=['B', 'S', 'C'])
        data['cellidnumber'] = data.groupby(['B', 'S', 'C']).ngroup().add(1)
        data = data.drop(['S', 'B', 'C'], axis=1)
        return data

    def export_influx_to_nginx(self, nginx_url=None, output_file=None):
        """
        Export InfluxDB data to JSON and POST to nginx.
        Reads URL from NGINX_EXPORT_URL environment variable if not provided.
        """
        # Priority: function arg > env variable > default
        nginx_url = nginx_url or os.environ.get('NGINX_EXPORT_URL', '')
        output_file = output_file or os.environ.get('EXPORT_JSON_FILE', '')

        logger.info(f"Exporting InfluxDB data to {nginx_url}")
        
        # Read data from InfluxDB
        data = self.db.read_data()
        
        if data is None or data.empty:
            logger.warning("No InfluxDB data to export")
            return False

        # Detect field format and build instances
        csv_fields = ["PRB_DL", "USERTHROUGHPUTDL_MBPS", "ENDC_AVG_RRC_CONNECTED_USERS"]
        synthetic_fields = ["DRB.UEThpUl", "RRU.PrbUsedUl", "PEE.AvgPower"]

        if all(field in data.columns for field in csv_fields):
            fields = csv_fields
            logger.debug("Using CSV field format")
        elif all(field in data.columns for field in synthetic_fields):
            fields = synthetic_fields
            logger.debug("Using synthetic field format")
        else:
            fields = [col for col in data.columns if col not in ['_time', '_measurement', 'CellID']]
            logger.warning(f"Using available fields: {fields}")

        data_clean = data[fields].fillna(0.0)
        instances = [row.tolist() for _, row in data_clean.iterrows()]

        # Build JSON payload
        payload = {
            "signature_name": "serving_default",
            "fields": fields,
            "instances": [instances]
        }

        # Add measurement metadata if available
        if '_measurement' in data.columns:
            measurements = data['_measurement'].dropna().unique().tolist()
            if len(measurements) == 1:
                payload['measurement'] = measurements[0]
            else:
                payload['measurements'] = measurements

        # Save to file
        with open(output_file, 'w') as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Saved JSON payload to {output_file}")

        # POST to nginx
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(nginx_url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            logger.info(f"Successfully POSTed to {nginx_url} - Status: {response.status_code}")
            logger.debug(f"Response: {response.text}")
            return True
        except Exception as e:
            logger.error(f"Failed to POST to {nginx_url}: {e}")
            return False


if __name__ == "__main__":

    logger.info("="*70)
    logger.info(" ENERGY SAVING rAPP STARTING")
    logger.info(f" Version: {RAPP_VERSION}")
    logger.info(f"  {BUILD_INFO}")
    logger.info(f" CSV File: {CSV_FILE_PATH}")
    logger.info("="*70)

    def str2bool(v):
        if isinstance(v, bool):
            return v
        if v.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif v.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    parser = argparse.ArgumentParser(description="Run ESrapp with optional localdb data generation.")
    parser.add_argument("--generate_db_data", type=str2bool, default=True, help="Set to True to generate data in db.")
    parser.add_argument("--use_sme_db", type=str2bool, default=False, help="Set to True use SME url for DB.")
    parser.add_argument("--random_predictions", type=str2bool, default=False, help="Set to True to generate random predictions.")
    parser.add_argument("--load_csv_data", type=str2bool, default=CSV_LOAD_ON_STARTUP, help="Set to True to load CSV data on startup.")
    parser.add_argument("--export", type=str2bool, default=False, help="Set to True to export InfluxDB data to nginx URL and exit.")
    parser.add_argument("--export-url", type=str, default=None, help="Custom nginx URL for export (overrides config.json).")
    parser.add_argument("--export-file", type=str, default=None, help="Output JSON file path (overrides config.json).")
    args = parser.parse_args()

    rapp = ESrapp(
        generate_db_data=args.generate_db_data, 
        use_sme_db=args.use_sme_db, 
        random_predictions=args.random_predictions,
        load_csv_data=args.load_csv_data
    )
    logger.info("TRACE: ESrapp instance created successfully")
    logger.debug("ES rApp starting")

    if args.export:
        rapp.export_influx_to_nginx(nginx_url=args.export_url, output_file=args.export_file)
    else:
        rapp.entry()
