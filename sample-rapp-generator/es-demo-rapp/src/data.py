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
import os
import time
import logging
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError
from requests.exceptions import RequestException, ConnectionError
import influxdb_client
from datetime import datetime, timedelta
import random
import json
from sme_client import SMEClient
from influxdb_client.client.write_api import SYNCHRONOUS
import pandas as pd

logger = logging.getLogger(__name__)

class DATABASE(object):

    def __init__(self, dbname='Timeseries', user='user', password='password', host="influxdb_ip", port='influxdb_port', path='', ssl=False):
        self.token = None
        self.org = None
        self.bucket = None
        self.data = None
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self.dbname = dbname
        self.client = None
        self.address = None
        self.influx_invoker_id = None
        self.influx_api_name = None
        self.influx_resource_name = None
        self.time_range = None
        self.measurements = None
        self.config()

        # Set pandas options to display all rows and columns
        pd.set_option('display.max_rows', None)  # Show all rows
        pd.set_option('display.max_columns', None)  # Show all columns
        pd.set_option('display.width', 1000)  # Adjust the width to avoid line breaks
        pd.set_option('display.colheader_justify', 'left')  # Align column headers to the left

    def get_url_from_sme(self):
        sme_client = SMEClient(
            invoker_id=self.influx_invoker_id,
            api_name=self.influx_api_name,
            resource_name=self.influx_resource_name
        )

        self.influx_url = sme_client.discover_service()

        logger.info("InfluxDB URL: {}".format(self.influx_url))

        if self.influx_url is not None:
            self.address = self.influx_url
            logger.debug(f"InfluxDB URL: {self.influx_url}")
            self.host = self.influx_url.split(":")[1].replace("//", "")
            logger.debug(f"InfluxDB Host: {self.host}")
            self.port = self.influx_url.split(":")[2].split("/")[0]
            logger.debug(f"InfluxDB Port: {self.port}")
            self.address = self.influx_url.rstrip('/')
            logger.debug(f"InfluxDB Address: {self.address}")
        else:
            logger.error("Failed to discover InfluxDB URL from SME.")

    # Connect with influxdb
    def connect(self):
        if self.client is not None:
            self.client.close()

        try:
            self.client = influxdb_client.InfluxDBClient(url=self.address, org=self.org, token=self.token)
            version = self.client.version()
            logger.info("Connected to Influx Database, InfluxDB version : {}".format(version))
            return True

        except (RequestException, InfluxDBClientError, InfluxDBServerError, ConnectionError):
            logger.error("Failed to establish a new connection with InflulxDB, Please check your url/hostname")
            time.sleep(120)

    # Query information
    def read_data_old(self, train=False, valid=False, limit=False):

        self.data = None
        query = 'from(bucket:"{}")'.format(self.bucket)
        query += '|> range(start: -10m) '
        query += ' |> filter(fn: (r) => r["_measurement"] == "o-ran-pm")'
        query += ' |> filter(fn: (r) => r["_field"] == "CellID" or r["_field"] == "DRB.UEThpUl" or r["_field"] == "RRU.PrbUsedUl" or r["_field"] == "PEE.AvgPower") '
        #query += ' |> filter(fn: (r) => r["_field"] == "CellID" or r["_field"] == "RRC.ConnMean" or r["_field"] == "DRB.UEThpUl" or r["_field"] == "RRU.PrbUsedUl" or r["_field"] == "PEE.AvgPower") '
        query += ' |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value") '
        result = self.query(query)
        self.data = result
        return result

    def read_data(self, train=False, valid=False, limit=False):
        self.data = None
        query = 'from(bucket:"{}")'.format(self.bucket)

        time_range = getattr(self, 'time_range', '-10m')
        query += f'|> range(start: {time_range}) '

        measurements = getattr(self, 'measurements', ['o-ran-pm'])
        if isinstance(measurements, str):
            measurements = [measurements]

        measurement_filters = [f'r["_measurement"] == "{m}"' for m in measurements]
        query += f' |> filter(fn: (r) => {" or ".join(measurement_filters)})'

        # Filter for both synthetic data fields AND CSV data fields
        query += ' |> filter(fn: (r) => r["_field"] == "CellID" or r["_field"] == "DRB.UEThpUl" or r["_field"] == "RRU.PrbUsedUl" or r["_field"] == "PEE.AvgPower" or r["_field"] == "PRB_DL" or r["_field"] == "USERTHROUGHPUTDL_MBPS" or r["_field"] == "ENDC_AVG_RRC_CONNECTED_USERS") '
        # Keep _measurement in the rowKey to preserve it
        query += ' |> pivot(rowKey: ["_time", "_measurement"], columnKey: ["_field"], valueColumn: "_value") '
       # logger.info(f"InfluxDB Query: {query}")
        result = self.query(query)
        #logger.debug(f"Data grouped by measurement:\n{result.groupby('_measurement').size()}")
        self.data = result
        return result

    # Query data
    def query(self, query):
        while True:
            try:
                query_api = self.client.query_api()
                result = query_api.query_data_frame(org=self.org, query=query)
                logger.debug(f'Cell data : {result}')
                return result
            except (RequestException, InfluxDBClientError, InfluxDBServerError, ConnectionError) as e:
                logger.error(f'Failed to query influxdb: {e}, retrying in 60 seconds...')
                time.sleep(60)

    def mapping(self, data):
        # Handle both BRANGES cell format and S-B-C format
        if data['CellID'].str.contains('BRANGES|[A-Z_]+', regex=True, na=False).any():
            # Custom mapping for cell names like BRANGES_T1
            logger.debug("Detected custom cell naming format (e.g., BRANGES_T1)")
            data['cellidnumber'] = pd.factorize(data['CellID'])[0] + 1
        else:
            # Original regex for S-B-C format (e.g., S2-B16-C1)
            logger.debug("Detected S-B-C cell naming format")
            data[['S', 'B', 'C']] = data['CellID'].str.extract(r'S(\d+)-[BN](\d+)-C(\d+)')
            data[['S', 'B', 'C']] = data[['S', 'B', 'C']].astype(int)
            data = data.sort_values(by=['B', 'S', 'C'])
            data['cellidnumber'] = data.groupby(['B', 'S', 'C']).ngroup().add(1)
            data = data.drop(['S', 'B', 'C'], axis=1)
        return data

    def generate_synthetic_data(self):
        data = []
        fields = ["CellID", "DRB.UEThpUl", "RRU.PrbUsedUl", "PEE.AvgPower", "GranularityPeriod", "RRC.ConnMean", "RRU.PrbTotDl", "DRB.UEThpDl"]
        measurements = ["o-ran-pm", "ManagedElement=o-du-pynts-1122,ManagedElement=o-du-pynts-1122,GNBDUFunction=1,NRCellDU=1", "ManagedElement=o-du-pynts-1123,ManagedElement=o-du-pynts-1123,GNBDUFunction=1,NRCellDU=1"]

        # Generate matching records (synchronized _time for each group of 4)
        for _ in range(50):  # 50 records, each with 4 rows sharing the same time
            common_time = datetime.now() - timedelta(minutes=random.randint(0, 60))
            iso_time = common_time.isoformat()
            measurement = random.choice(measurements)

            for field in fields:
                value = (
                    f"S{random.randint(1,9)}-B{random.randint(1,9)}-C{random.randint(1,9)}" if field == "CellID"
                    else (900 if field == "GranularityPeriod"
                    else str(round(random.uniform(1, 100), 5)))
                )
                record = {
                    "_time": iso_time,
                    "_measurement": measurement,
                    "_field": field,
                    "_value": value
                }
                data.append(record)

        # Log data to be written
        print(pd.DataFrame(data).to_string())

        self.write_synthetic_data_to_db(data)


    def write_synthetic_data_to_db(self, data):

        write_api = self.client.write_api(write_options=SYNCHRONOUS)
        for record in data:
            point = influxdb_client.Point(record["_measurement"]) \
                .field(record["_field"], record["_value"]) \
                .time(datetime.fromisoformat(record["_time"]))
            write_api.write(bucket=self.bucket, org=self.org, record=point)
        write_api.flush()
        write_api.close()
        logger.info("Synthetic data successfully written to InfluxDB.")

    def load_csv_to_influxdb(self, csv_file_path, measurement_name="o-ran-pm", cell_id_column="CELLULE", timestamp_column="MINIMALE(PSDATE)"):
        """
        Load data from CSV file and write to InfluxDB - GENERIC VERSION
        Automatically detects and uses all numeric columns as fields with their original names.
        
        Args:
            csv_file_path: Path to the CSV file
            measurement_name: Name of the measurement in InfluxDB
            cell_id_column: Column name to use as CellID tag (default: CELLULE)
            timestamp_column: Column name containing timestamps (default: MINIMALE(PSDATE))
        """
        import csv
        from datetime import datetime
        
        logger.info(f"Loading CSV data from: {csv_file_path}")
        logger.info(f"Cell ID column: {cell_id_column}, Timestamp column: {timestamp_column}")
        
        write_api = self.client.write_api(write_options=SYNCHRONOUS)
        records_written = 0
        points = []
        
        # Columns to exclude from fields (metadata columns)
        exclude_columns = {cell_id_column, timestamp_column, 'CODE_ELT_CELLULE'}
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile, delimiter=';')
                headers = reader.fieldnames
                
                # Auto-detect numeric columns
                logger.info(f"CSV columns found: {len(headers)}")
                logger.info(f"Columns: {headers}")
                
                for row in reader:
                    try:
                        # Parse timestamp from CSV
                        timestamp_str = row.get(timestamp_column, '').strip()
                        if timestamp_str:
                            # Parse DD/MM/YYYY HH:MM:SS format
                            timestamp = datetime.strptime(timestamp_str, '%d/%m/%Y %H:%M:%S')
                        else:
                            # Use current time if no timestamp
                            timestamp = datetime.now()
                        
                        # Create a single point for this row
                        point = influxdb_client.Point(measurement_name).time(timestamp)
                        
                        # Add CellID as a tag
                        cell_id = row.get(cell_id_column, '').strip()
                        if cell_id:
                            point = point.tag("CellID", cell_id)
                        
                        # Add all other columns as fields (auto-detect numeric vs string)
                        fields_added = 0
                        for column_name in headers:
                            if column_name in exclude_columns:
                                continue
                            
                            value = row.get(column_name, '')
                            if value is None or (isinstance(value, str) and not value.strip()):
                                continue
                            
                            value = value.strip() if isinstance(value, str) else str(value)
                            
                            try:
                                # Try to parse as numeric (handle French decimal format)
                                value_clean = value.replace(',', '.')
                                numeric_value = float(value_clean)
                                point = point.field(column_name, numeric_value)
                                fields_added += 1
                            except ValueError:
                                # If not numeric, store as string
                                point = point.field(column_name, value)
                                fields_added += 1
                                fields_added += 1
                        
                        # Only add point if it has at least one field
                        if fields_added > 0:
                            points.append(point)
                            records_written += 1
                        
                        # Write in batches of 500
                        if len(points) >= 500:
                            write_api.write(bucket=self.bucket, org=self.org, record=points)
                            logger.info(f"Wrote batch of {len(points)} points (total: {records_written})...")
                            points = []
                    
                    except Exception as e:
                        logger.warning(f"Error processing row: {e}")
                        continue
                
                # Write remaining points
                if points:
                    write_api.write(bucket=self.bucket, org=self.org, record=points)
                    logger.info(f"Wrote final batch of {len(points)} points...")
            
            write_api.close()
            logger.info(f"Successfully loaded {records_written} data points from CSV to InfluxDB")
            logger.info(f"Measurement: {measurement_name}, Bucket: {self.bucket}")
            
        except FileNotFoundError:
            logger.error(f"CSV file not found: {csv_file_path}")
        except Exception as e:
            logger.error(f"Error loading CSV to InfluxDB: {e}", exc_info=True)
            
        except FileNotFoundError:
            logger.error(f"CSV file not found: {csv_file_path}")
        except Exception as e:
            logger.error(f"Error loading CSV to InfluxDB: {e}")

    def config(self):

        with open('config.json', 'r') as f:
            config = json.load(f)

        # Load the SME configuration from the JSON file
        sme_config = config.get("SME", {})
        self.influx_invoker_id = sme_config.get("influxdb_invoker_id")
        self.influx_api_name = sme_config.get("influxdb_api_name")
        self.influx_resource_name = sme_config.get("influxdb_resource_name")

        # Initialize the InfluxDB client
        influx_config = config.get("DB", {})

        if os.getenv('INFLUX_TOKEN'):
            self.token = os.getenv('INFLUX_TOKEN')
        else:
            logger.info("INFLUX_TOKEN environment variable is not set.")
            self.token = influx_config.get("token")

        self.org = influx_config.get("org")
        self.bucket = influx_config.get("bucket")
        self.address = influx_config.get("address")
        self.host = influx_config.get("host")
        self.port = influx_config.get("port")
        self.ssl = influx_config.get("ssl")
        self.dbname = influx_config.get("database")
        self.user = influx_config.get("user")
        self.password = influx_config.get("password")
        # Override time_range to query May 2025 CSV data
        self.time_range = "2025-05-01T00:00:00Z"
        # Override measurements to only query CSV data
        self.measurements = ["branges-pm-data"]
