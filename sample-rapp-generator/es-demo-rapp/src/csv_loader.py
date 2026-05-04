"""
CSV Data Loader for Energy Saving rApp
Loads historical CSV data with recent timestamps into InfluxDB
"""

import os
import csv
import logging
from datetime import datetime, timedelta
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)


def load_csv_data_recent(db_client, bucket, org, csv_file_path, 
                         measurement_name="branges-pm-data", 
                         cell_id_column="CELLULE", 
                         timestamp_column="MINIMALE(PSDATE)",
                         target_start_date=None):
    """
    Load CSV data with original timestamps or shifted to specific target dates.
    Preserves the original time granularity (15-minute intervals).
    
    Args:
        db_client: InfluxDB client instance
        bucket: InfluxDB bucket name
        org: InfluxDB organization name
        csv_file_path: Path to CSV file
        measurement_name: InfluxDB measurement name
        cell_id_column: Column containing cell ID
        timestamp_column: Column containing original timestamps
        target_start_date: Start date for shifted data in YYYY-MM-DD format. 
                          If None, use original CSV timestamps (default: None)
    
    Returns:
        bool: True if successful, False otherwise
    """
    
    if not os.path.exists(csv_file_path):
        logger.warning(f"CSV file not found: {csv_file_path} - skipping CSV load")
        return False
    
    if target_start_date:
        logger.info(f"📊 Loading CSV with shifted timestamps: {csv_file_path}")
        logger.info(f"Target start date: {target_start_date}")
    else:
        logger.info(f"📊 Loading CSV with ORIGINAL timestamps: {csv_file_path}")
    
    exclude_columns = {cell_id_column, timestamp_column, 'CODE_ELT_CELLULE'}
    
    # Parse target start date if provided
    target_start = None
    if target_start_date:
        try:
            target_start = datetime.strptime(target_start_date, '%Y-%m-%d')
        except:
            logger.error(f"Invalid target_start_date format: {target_start_date}. Use YYYY-MM-DD")
            return False
    
    # Find original time range (only needed if shifting timestamps)
    min_original = None
    max_original = None
    original_duration = None
    
    if target_start:
        original_timestamps = []
        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            for row in reader:
                timestamp_str = row.get(timestamp_column, '').strip()
                if timestamp_str:
                    try:
                        ts = datetime.strptime(timestamp_str, '%d/%m/%Y %H:%M:%S')
                        original_timestamps.append(ts)
                    except:
                        pass
        
        if not original_timestamps:
            logger.error("No valid timestamps found in CSV")
            return False
        
        min_original = min(original_timestamps)
        max_original = max(original_timestamps)
        original_duration = max_original - min_original
        
        logger.info(f"Original range: {min_original} to {max_original} ({original_duration})")
        
        # New time range: target_start_date + original_duration
        new_start = target_start
        new_end = new_start + original_duration
        
        logger.info(f"New range: {new_start} to {new_end}")
        logger.info(f"Duration: {original_duration} (preserving 15-minute granularity)")
    
    # Load and transform
    write_api = db_client.write_api(write_options=SYNCHRONOUS)
    records_written = 0
    points = []
    
    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        headers = reader.fieldnames
        
        for row in reader:
            try:
                timestamp_str = row.get(timestamp_column, '').strip()
                if not timestamp_str:
                    continue
                
                original_ts = datetime.strptime(timestamp_str, '%d/%m/%Y %H:%M:%S')
                
                # Use original timestamp or shifted timestamp
                if target_start:
                    # Calculate relative position and shift to new date
                    if original_duration.total_seconds() > 0:
                        relative_position = (original_ts - min_original).total_seconds() / original_duration.total_seconds()
                    else:
                        relative_position = 0.0
                    
                    # Map to new time range (preserves original time intervals)
                    new_timestamp = target_start + timedelta(seconds=relative_position * original_duration.total_seconds())
                else:
                    # Use original timestamp as-is
                    new_timestamp = original_ts
                
                point = influxdb_client.Point(measurement_name).time(new_timestamp)
                
                cell_id = row.get(cell_id_column, '').strip()
                if cell_id:
                    point = point.tag("CellID", cell_id)
                
                fields_added = 0
                for column_name in headers:
                    if column_name in exclude_columns:
                        continue
                    
                    value = row.get(column_name, '')
                    if value is None or (isinstance(value, str) and not value.strip()):
                        continue
                    
                    value = value.strip() if isinstance(value, str) else str(value)
                    
                    try:
                        value_clean = value.replace(',', '.')
                        numeric_value = float(value_clean)
                        point = point.field(column_name, numeric_value)
                        fields_added += 1
                    except ValueError:
                        point = point.field(column_name, value)
                        fields_added += 1
                
                if fields_added > 0:
                    points.append(point)
                    records_written += 1
                
                if len(points) >= 500:
                    write_api.write(bucket=bucket, org=org, record=points)
                    logger.info(f"Wrote batch: {len(points)} points (total: {records_written})")
                    points = []
            
            except Exception as e:
                continue
        
        if points:
            write_api.write(bucket=bucket, org=org, record=points)
            logger.info(f"Wrote final batch: {len(points)} points")
    
    write_api.close()
    
    if target_start:
        logger.info(f"Loaded {records_written} CSV points with SHIFTED timestamps!")
        logger.info(f"Data from {target_start.strftime('%Y-%m-%d %H:%M')} to {(target_start + original_duration).strftime('%Y-%m-%d %H:%M')}")
    else:
        logger.info(f"Loaded {records_written} CSV points with ORIGINAL timestamps!")
        logger.info(f"Data from original CSV dates (May 18-26, 2025)")
    
    return True
