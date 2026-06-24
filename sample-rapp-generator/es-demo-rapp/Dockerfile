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

FROM python:3.10.17-alpine3.21

WORKDIR /app

# Install curl and jq for fetching predictions
RUN apk add --no-cache curl jq grep

# Copy all source files to /app
COPY src/ /app/

# Copy any CSV files from root to /app
COPY *.csv /app/

# Ensure predictions are baked into the image so the entrypoint can find them
RUN mkdir -p /app/data

# Install Python dependencies
RUN pip install -r requirements.txt

# Try to fetch fresh predictions during build (non-fatal fallback to baked-in files)
COPY fetch_predictions.sh /fetch_predictions.sh
RUN chmod +x /fetch_predictions.sh && /fetch_predictions.sh || echo "Using fallback predictions during build"

# Copy entrypoint script (simple startup, no fetching)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["python", "main.py", "--generate_db_data=True", "--use_sme_db=True", "--random_predictions=False"]

ENTRYPOINT ["/entrypoint.sh"]
