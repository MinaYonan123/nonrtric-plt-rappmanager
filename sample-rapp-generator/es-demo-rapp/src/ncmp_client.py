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

import json
import logging
import requests
from sme_client import SMEClient

logger = logging.getLogger(__name__)

class NCMP_CLIENT(object):
    def __init__(self):
        with open('config.json', 'r') as f:
            config = json.load(f)

        sme_config = config.get("SME", {})
        self.host = sme_config.get("host")
        self.port = sme_config.get("port")
        self.ncmp_invoker_id = sme_config.get("ncmp_invoker_id")
        self.ncmp_api_name = sme_config.get("ncmp_api_name")
        self.ncmp_resource_name = sme_config.get("ncmp_resource_name")
        self.ncmp_me = sme_config.get("ncmp_managed_element_id", "ManagedElement-002")
        self.ncmp_gnb = sme_config.get("ncmp_gnbdufunction_id", "GNBDUFunction-001")
        self.resourse_identifier = sme_config.get("resource_id")
        
        # NCMP authentication credentials (optional, for direct SDNC access)
        self.ncmp_username = sme_config.get("ncmp_username", "admin")
        self.ncmp_password = sme_config.get("ncmp_password", "Kp8bJ4SXszM0WXlhak3eHlcse2gAw84vaoGGmJvUy2U")
        
        self.ncmp_uri = None

        sme_client = SMEClient(
            invoker_id=self.ncmp_invoker_id,
            api_name=self.ncmp_api_name,
            resource_name=self.ncmp_resource_name
        )

        self.ncmp_uri = sme_client.discover_service()

        # NCMP is not used in static prediction mode - suppress error logs
        if self.ncmp_uri:
            logger.debug(f"Discovered NCMP URI: {self.ncmp_uri}")
        else:
            logger.debug("NCMP service discovery skipped (using O1 NETCONF server instead)")

    def power_off_cell(self, cell_with_node):

        passthrough_request = self.make_passthrough_request(cell_with_node)
        
        if not passthrough_request:
            logger.error(f"Cannot power off cell {cell_with_node}: NCMP URL construction failed")
            return False
            
        # This log is all it does in testing
        logger.info("Powering-off cell " + str(cell_with_node) + " in progress...")

        # It expects the SME ncmp endpoint to call power off
        # endpoint_with_query = f"{endpoint}?resourceIdentifier={self.resourse_identifier}"
        #
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Add Basic Auth for SDNC/NCMP (default credentials)
        # If authentication is handled by Kong/SME, these may not be needed
        # Common SDNC credentials: admin/Kp8bJ4SXszM0WXlhak3eHlcse2gAw84vaoGGmJvUy2U
        auth = None
        if hasattr(self, 'ncmp_username') and hasattr(self, 'ncmp_password'):
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(self.ncmp_username, self.ncmp_password)
            logger.debug("Using Basic Auth for NCMP request")

        body = {
            "attributes": {
                "administrativeState": "LOCKED"
            }
        }

        response = requests.patch(passthrough_request, json=body, headers=headers, auth=auth)
        
        logger.info(f"NCMP power-off request URL: {passthrough_request}")
        logger.info(f"NCMP power-off response status: {response.status_code}")

        if response.status_code == 200:
            logger.info("Power-off successful. " + response.text)
            return True
        else:
            logger.error(f"Error in connection to NCMP for power off: {response.status_code}")
            logger.error(f"Response body: {response.text}")
            logger.error(f"Request URL was: {passthrough_request}")
            return False

    def power_on_cell(self, cell_with_node):

        # This log is all it does in testing
        passthrough_request = self.make_passthrough_request(cell_with_node)
        
        if not passthrough_request:
            logger.error(f"Cannot power on cell {cell_with_node}: NCMP URL construction failed")
            return False
            
        logger.info("Powering-on cell " + str(cell_with_node) + " in progress...")

        # It expects the SME ncmp endpoint to call power on
        # endpoint_with_query = f"{endpoint}?resourceIdentifier={self.resourse_identifier}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Add Basic Auth for SDNC/NCMP (default credentials)
        auth = None
        if hasattr(self, 'ncmp_username') and hasattr(self, 'ncmp_password'):
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(self.ncmp_username, self.ncmp_password)
            logger.debug("Using Basic Auth for NCMP request")

        body = {
            "attributes": {
                "administrativeState": "UNLOCKED"
            }
        }

        response = requests.patch(passthrough_request, json=body, headers=headers, auth=auth)
        
        logger.info(f"NCMP power-on request URL: {passthrough_request}")
        logger.info(f"NCMP power-on response status: {response.status_code}")

        if response.status_code == 200:
            logger.info("Power-on successful. " + response.text)
            return True
        else:
            logger.error(f"Error in connection to NCMP for power on: {response.status_code}")
            logger.error(f"Response body: {response.text}")
            logger.error(f"Request URL was: {passthrough_request}")
            return False

    def make_passthrough_request(self, cell_with_node):
        if not self.ncmp_uri:
            logger.error("Cannot construct NCMP request: NCMP URI is None (service discovery failed)")
            return None
            
        node_id = cell_with_node.split('_')[1]
        cell_id = cell_with_node.split('_')[0]

        # The NCMP URI from SME already has the base path, just append the NCMP-specific path
        # Format: {base}/ncmp/v1/ch/{cmHandleId}/data/ds/{datastoreName}?resourceIdentifier={resource}
        endpoint = f"ncmp/v1/ch/{node_id}/data/ds/ncmp-datastore:passthrough-running"
        query_param = (f"?resourceIdentifier=/_3gpp-common-managed-element:ManagedElement={self.ncmp_me}"
                       f"/_3gpp-nr-nrm-gnbdufunction:GNBDUFunction={self.ncmp_gnb}"
                       f"/_3gpp-nr-nrm-nrcelldu:NRCellDU={cell_id}/attributes")

        # Ensure proper URL construction - remove trailing slash from base URI if present
        base_uri = self.ncmp_uri.rstrip('/')
        full_url = f"{base_uri}/{endpoint}{query_param}"
        logger.info(f"NCMP passthrough URL: {full_url}")
        return full_url

# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)  # Set up logging for better visibility
#
#     # Instantiate the NcmpClient
#     ncmp_client = NCMP_CLIENT()

# Test the discover_ncmp_via_sme method
# Discover service

# Test the power_off_cell method
#if discovery_result:
#    power_off_result = ncmp_client.power_off_cell(discovery_result)
#    print(f"Power Off Result: {power_off_result}")

# Test the power_on_cell method
#if discovery_result:
#    power_on_result = ncmp_client.power_on_cell(discovery_result)
#    print(f"Power On Result: {power_on_result}")

