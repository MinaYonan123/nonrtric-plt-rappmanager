# Energy Saving rApp Demo

The code, helm chart and rApp specification contained in this directory implement an Energy Saving rApp for the O-RAN SMO platform. The rApp monitors RAN cell load using PM data from InfluxDB, runs ML-based predictions via KServe, and applies energy saving control actions over the O1 interface (NETCONF) to power cells on or off based on predicted traffic load.

The instructions below describe how to:

- Deploy the demo in a Kubernetes cluster.
- Create and deploy the Energy Saving rApp using the rApp Manager REST API (curl commands) and postman.
- Confirm that the Energy Saving rApp is running and managing energy consumption in the network.
- Undeploy the Energy Saving rApp.
- Troubleshoot any issues that may arise during the deployment or undeployment process.

## Prerequisites
- A Kubernetes cluster, various versions and sims supported - see [here](https://gerrit.o-ran-sc.org/r/gitweb?p=it/dep.git;a=blob_plain;f=smo-install/README.md;hb=HEAD).
- See prerequisites [here](https://gerrit.o-ran-sc.org/r/gitweb?p=it/dep.git;a=blob_plain;f=smo-install/README.md;hb=HEAD)
- A clone of this repository.
- Postman.

## Deployment Steps

### SMO Installation
For a complete guide on the installation of the SMO rApp platform,
please follow the instructions [here](https://gerrit.o-ran-sc.org/r/gitweb?p=it/dep.git;a=blob_plain;f=smo-install/README.md;hb=HEAD).

As an additional note, a special flavour of the SMO installation is available for the Energy Saving rApp demo.
This flavour is located in the `smo-install/helm-override/ranpm-pynts-es-rapp` directory. 
There is some detail on flavours [here](https://github.com/o-ran-sc/it-dep/blob/master/smo-install/README.md).
This flavour is designed to install the SMO components required for the Energy Saving rapp demo.
After all the other steps in the SMO installation guide are completed, you can run the following command to 
install the Energy Saving rApp flavour:

```bash
./dep/smo-install/scripts/layer-2/2-install-oran.sh ranpm-pynts-es-rapp dev
```

Once all the components are installed and ready, you can proceed with the install of the DU simulators.
These will start a flow of sample data through the system, which will be used by the Energy Saving rApp demo.
wait around 10 minutes after all the components are installed before proceeding with the next simulator install.

```bash
./dep/smo-install/scripts/layer-2/2-install-simulators.sh ranpm-pynts-es-rapp
```

```text
NOTE: The installation is just pointed at with the above commands. For the full installation and details of flavours, go to the smo installation docs.
```
[SMO Install Guide](https://github.com/o-ran-sc/it-dep/blob/master/smo-install/README.md)

### Energy Saving rApp Deployment Preparation
1. The rApp needs to know the address and port of your chart repository. If you need to run a local chart repository, you can refer to the instructions [here](https://github.com/o-ran-sc/it-dep/blob/master/smo-install/helm-override/rappmanager/README.md#helm-repository-configuration)
    Replace `IP_ADD` and `PORT` in the command below with the address and port of your chart repository.
   ```bash
   cd scripts/install
   ./patch-sample-rapps.sh -i IP_ADD -p PORT -r "es-demo-rapp/rapp-energy-saving"
   ```
2. Navigate to the `es-demo-rapp` directory.
3. To generate the rApp csar and helm chart, run the following command:
   ```bash
   ./generate.sh rapp-energy-saving
   ```
4. Make sure to expose the rappmanager service in the `nonrtric` namespace. This is done by running the following command:
   ```bash
   kubectl expose service rappmanager --type=NodePort --name=rappmanager-exposed -n nonrtric
   ```
5. Find the ClusterIP of the exposed service:
   ```bash
   kubectl get svc -A | grep rappmanager
   ```
   Example output:
   ```
   nonrtric   rappmanager            ClusterIP   10.98.19.4    <none>   8080/TCP           3h25m
   nonrtric   rappmanager-exposed    NodePort    10.106.58.138 <none>   8080:32692/TCP     3h25m
   ```
   Use the ClusterIP of `rappmanager-exposed` (e.g. `10.106.58.138`) and port `8080` in all API calls below.
   Replace `<RAPPMANAGER_IP>` with this IP throughout the curl commands.
6. You will be using the postman collection provided in the main directory of this repository to create the rApp.
7. Open Postman and import the `rapp-energy-saving.postman_collection.json` file.
8. It is important to note the collection-level variables in the postman collection.
    1. REMOTE-IP: This is the location the rappmanager service is deployed/exposed to.
    2. PORT: This should be the port where the rappmanager is exposed.
    3. rappId: This is the ID of the rApp you will be creating. It should be unique and can be any alphanumeric string.
    4. rappInstanceId: It will be automatically populated when you create the rApp instance.
    5. PREIDCT_PORT: This is the port where the prediction service is running. It should be set to `40077` by default.

---

### rApp Deployment via Postman
1. In Postman, select the `Onboard ES rApp` request from the collection. Send this request.
2. Then run the `Get Rapps` request to confirm that the rApp has been onboarded successfully.
3. Run the `Prime rApp` request to prime the rApp.
4. Run `Get All Rapp Instances` to confirm that no rApp instance have been created.
5. Run the `Create Rapp Instance ES` request to create an instance of the rApp.
6. Run the `Get Rapp Instance` request to confirm that the rApp instance has been created successfully.
7. Run the `Deploy Rapp Instance` to trigger installation of the rApp instance.
8. The above deployment can take time, so you can run the `Get Rapp Instance` request to check the status of the rApp instance.
9. You can also monitor the kubernetes pods in the `nonrtric` namespace to see if the rApp instance helm charts are being deployed.

---

### rApp Deployment via curl

> The rApp name `energy-saving-1` is chosen to describe what is being deployed. It must be consistent across all commands for a given lifecycle.
>
> The `.csar` path below must match the location of the file generated in step 3.

#### 1. Onboard the rApp package

```bash
curl -X POST http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1 \
  -F "file=@/home/oie/nonrtric-plt-rappmanager/sample-rapp-generator/rapp-energy-saving.csar"
```

#### 2. Prime the rApp

```bash
curl -X PUT http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1 \
  -H "Content-Type: application/json" \
  -d '{"primeOrder": "PRIME"}'
```

#### 3. Check the rApp status

```bash
curl -X GET http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1
```

Wait until the status shows `PRIMED` before proceeding.

#### 4. Create an rApp instance

```bash
curl -X POST http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1/instance \
  -H "Content-Type: application/json" \
  -d '{
    "acm": {
      "instance": "es-instance"
    },
    "sme": {
      "providerFunction": "es-model-provider-function",
      "serviceApis": "api-set-kserve-predictor",
      "invokers": "invoker-app1"
    }
  }'
```

Note the `rappInstanceId` returned in the response (e.g. `6cf1718e-2b7d-42b9-b606-80854adc9e25`). Use it in the commands below as `<INSTANCE_ID>`.

#### 5. Deploy the rApp instance

```bash
curl -X PUT http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1/instance/<INSTANCE_ID> \
  -H "Content-Type: application/json" \
  -d '{"deployOrder": "DEPLOY"}'
```

#### 6. Check the rApp instance status

```bash
curl -X GET http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1/instance/<INSTANCE_ID>
```

You can also monitor Kubernetes pods in the `nonrtric` namespace:
```bash
kubectl get pods -n nonrtric | grep energy-saving
```

### Confirmation
1. To confirm successful running of the demo energy saving rApp, we can look at the kubernetes logs of the pod.
   ```bash
   kubectl logs -f -l app.kubernetes.io/name=energy-saving-rapp -n nonrtric
   ```
2. You should see logs indicating that the rApp is running and managing energy consumption in the network.
3. For example, you should see:
    1. Logs of cells being turned off and on based on the energy consumption in the network.
    2. Predictions of energy consumption based on the current network load being returned to make power management decisions.
    3. NETCONF responses from the O1 server confirming cell state changes.

## Undeployment

Undeployment is done in reverse order: undeploy the instance, delete the instance, deprime the rApp, then delete the rApp package.

### Undeploy via Postman
1. Run the `Undeploy Rapp Instance` request to undeploy the rApp instance. This takes some time.
2. Run the `Get Rapp Instance` request to confirm that the rApp instance has been undeployed successfully.
3. Run the `Delete Rapp Instance` request to delete the rApp instance.
4. Run the `Get All Rapp Instances` request to confirm that no rApp instances are present.
5. Run the `Deprime rApp` request to deprime the rApp.
6. Run the `Delete ES Rapp` request to delete the rApp.
7. This should conclude the undeployment of the Energy Saving rApp.

### Undeploy via curl

#### 1. Undeploy the rApp instance

```bash
curl -X PUT http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1/instance/<INSTANCE_ID> \
  -H "Content-Type: application/json" \
  -d '{"deployOrder": "UNDEPLOY"}'
```

#### 2. Delete the rApp instance

```bash
curl -X DELETE http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1/instance/<INSTANCE_ID>
```

#### 3. Deprime the rApp

```bash
curl -X PUT http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1 \
  -H "Content-Type: application/json" \
  -d '{"primeOrder": "DEPRIME"}'
```

#### 4. Delete the rApp package

```bash
curl -X DELETE http://<RAPPMANAGER_IP>:8080/rapps/energy-saving-1
```

---

## What is Implemented

### Overview

The rApp is a Python application that runs inside the Kubernetes cluster as a Helm-deployed workload. It operates on a loop and, for each iteration (every 10 seconds in demo mode), decides whether a RAN cell should be powered on or off based on predicted traffic load.

```
InfluxDB (PM data) ──► EnergySavingAction (decision logic)
KServe (ML model)  ──►        │
                               ▼
                     NETCONF / O1 Server (cell on/off)
```

### Source Files (`src/`)

| File | Description |
|---|---|
| `main.py` | Entry point. Initialises all components, loads CSV data into InfluxDB, and starts the inference scheduling loop. |
| `energy_saving_action.py` | Core decision logic. Reads a 192-value prediction vector (48 hours × 4 quarters), applies a threshold with hysteresis, then sends NETCONF XML to turn a cell on or off. Also contains the `NETCONFCLIENT` class. |
| `data.py` | `DATABASE` class — connects to InfluxDB, queries PM data, and can generate synthetic data for local testing. Discovers the InfluxDB URL via SME. |
| `assist.py` | `ASSIST` class — discovers the KServe predictor URL via SME and sends inference requests to the ML model (`es-aiml-model`). |
| `ncmp_client.py` | `NCMP_CLIENT` class — discovers the NCMP (CPS/SDNC) service via SME and sends `PATCH` requests to lock (power off) a cell via the O1/NCMP interface. |
| `sme_client.py` | `SMEClient` helper — queries the CAPIF/SME service discovery endpoint to resolve service URLs at runtime. |
| `teiv_client.py` | `TEIV_CLIENT` class — queries the Topology Exposure and Inventory (TEIV) service for cell topology information. |
| `csv_loader.py` | Loads historical PM CSV data into InfluxDB, with optional timestamp shifting to make the data appear recent. |
| `config.json` | Static configuration: SME host/port, SME invoker IDs, InfluxDB connection details, NCMP resource identifiers. |

### Decision Flow

1. **Startup** — `main.py` connects to InfluxDB, loads the CSV PM data (with timestamp shifting if configured), and initialises the NETCONF, NCMP, KServe, and TEIV clients.
2. **Inference loop** — every 10 seconds (demo cadence), `safe_inference()` is called. It delegates to `EnergySavingAction.make_hourly_decision()`.
3. **Energy decision** — for each hour (out of 48), the prediction vector is read. If predicted load for cell `BRANGES_T1` (cell ID 16) is below a threshold (50), the cell is put into energy saving mode (`toBeEnergySaving`). If load is at or above the threshold, the cell is restored (`toBeNotEnergySaving`). A hysteresis margin prevents oscillation.
4. **NETCONF action** — `NETCONFCLIENT.perform_action()` or `perform_action_on()` sends a 3GPP-compliant NETCONF `edit-config` XML message over HTTP to the O1 server (default `172.19.1.86:8831`). The message targets the `CESManagementFunction` attribute of the relevant `NRCellCU`.
5. **Termination** — after all 48 hours are processed, the loop exits gracefully.

### Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `O1_SERVER_HOST` | `172.19.1.86` | IP of the O1/NETCONF server (Kubernetes node IP) |
| `O1_SERVER_PORT` | `8831` | Port of the O1 server |
| `O1_SERVER_USER` | `admin` | NETCONF username |
| `O1_SERVER_PASS` | `netconf` | NETCONF password |
| `CSV_FILE_PATH` | `SU_MIMO_15m 1.csv` | Path to the PM CSV file to load |
| `CSV_LOAD_ON_STARTUP` | `false` | Whether to load CSV data on startup |
| `CSV_TARGET_START_DATE` | _(empty)_ | Shift CSV timestamps to this date (`YYYY-MM-DD`) |

### rApp Package Structure (`rapp-energy-saving/`)

| Path | Description |
|---|---|
| `Artifacts/Deployment/HELM/energy-saving-chart/` | Helm chart that deploys the rApp container |
| `Definitions/asd.yaml` | ASD (Application Service Descriptor) referencing the Helm chart |
| `Files/Acm/definition/compositions.json` | ACM composition definition (automation policy types) |
| `Files/Acm/instances/es-instance.json` | ACM instance configuration used when creating the rApp instance |
| `Files/Sme/providers/` | SME provider function registrations (KServe predictor, InfluxDB) |
| `Files/Sme/invokers/` | SME invoker registrations (NCMP, InfluxDB, KServe, TEIV) |
| `Files/Sme/serviceapis/` | SME service API definitions |

---

## Troubleshooting
If you encounter any issues during the deployment or undeployment of the rApp, please check the following:
1. Is deployment of the pods stuck in ACM?
    - Check the logs of the ACM pod and the kubernetes participant in the `onap` namespace.
    - Is there any indication that install of the pods failed?
    - Check the deployment status of the pods
2. Is there an issue with the SME part of the installation?
    - Check the logs of the servicemanager pod in the `nonrtric` namespace.
    - Is there any indication that the SME is not able to communicate with the rApp Manager?

### Clean Up
If there is a case of a failed deployment that cannot be cleaned up via the API, we can use the following steps.
When cleaning up, it is best to carry out both ACM Cleanup and SME Cleanup - detailed below.

#### ACM Cleanup
Consult the postman collection under the "Cleanup" directory for the ACM cleanup steps.
1. Run `Get All Templates ACM-Direct`
2. Run `Get Template ACM-Direct`
3. Run `Get All Instances ACM-Direct`
4. Run `Get Instance ACM-Direct`
5. The above will populate the postman collection variables with the template and instance IDs.
6. Run `Undeploy Instance ACM-Direct` to undeploy the instance.
   Wait for the pods to undeploy (if they are stuck or leftover).
7. Run `Delete Instance ACM-Direct` to delete the instance.
8. Run `Delete Template ACM-Direct` to delete the template.
9. That should conclude the ACM cleanup.

#### SME Cleanup
SME cleanup requires some manual steps.
1. Delete all the kong services and routes. Put this in some "script.sh" file and run it. The place where you run it
   should have access to the cluster.
   ```bash
      SERVICEMANAGER_POD=$(kubectl get pods -o custom-columns=NAME:.metadata.name -l app.kubernetes.io/name=servicemanager --no-headers -n nonrtric)
      if [[ -n $SERVICEMANAGER_POD ]]; then
      kubectl exec $SERVICEMANAGER_POD -n nonrtric -- ./kongclearup
      else
      echo "Error - Servicemanager pod not found, didn't delete Kong routes and services for ServiceManager."
      fi

   ```
2. Once the above has been run, we must restart some pods.
   ```bash
   kubectl delete pod -l app.kubernetes.io/name=servicemanager -n nonrtric
   kubectl delete pod -l app.kubernetes.io/name=rappmanager -n nonrtric
   kubectl delete pod -l app.kubernetes.io/name=capifcore -n nonrtric
   ```
3. Wait for these pods to come up again to a `Running` state.
4. Now we need to add some preloaded SME configurations.
    1. In the `it/dep` repository, navigate to the `nonrtric/servicemanager-preload` directory.
    2. Preload some of the nonrtric services by running the following command:
       ```bash
       ./servicemanager-preload.sh config-nonrtric.yaml
       ```
    3. Preload the SMO services by running the following command:
       ```bash
       ./servicemanager-preload.sh config-smo.yaml
       ```
5. This should conclude the SME cleanup. Then we can attempt to redeploy the rApp again with whatever
   changes we made to fix the issues.

## Acknowledgements
This project was based on the [OSC Non-RT RIC Energy Saving rAPP](https://github.com/bmw-ece-ntust/nonrtric-rapp-energysaving). Many thanks to the original authors for their work.

### Citation
```text
Lan, Y., Zhang, H., & Bimo, F. A. (2025). nonrtric-rapp-energysaving (Version 1.0.0) [Computer software]. https://github.com/bmw-ece-ntust/nonrtric-rapp-energysaving
```
