# wait for docker
until docker version > /dev/null 2>&1
do
  echo "Checking if docker daemon has started..."
  sleep 10s
done

# create local k3s cluster
echo "Creating k3d cluster"
k3d cluster create \
-p '1883:1883@loadbalancer' \
-p '8883:8883@loadbalancer' \
-p '6001:6001@loadbalancer' \
-p '4000:80@loadbalancer'

# write kubeconfig
k3d kubeconfig get k3s-default > ~/.kube/config

# install connectedk8s extension
az extension add -n connectedk8s -y

# local extension install
echo "Setting up CLI dev environment"
python -m venv env
source env/bin/activate

echo "Install AZDEV"
pip install azdev

echo "Install AZ CLI EDGE"
azdev setup -c EDGE

echo "Installing local dev extension"
pip install -U --target ~/.azure/cliextensions/azure-iot-ops .

# setup tox environment dependencies in parallel, but don't run tests
echo "Creating local tox environments"
python -m pip install tox
tox -np -e lint,python,coverage

echo "Install complete, please activate your environment with 'source env/bin/activate'"
echo "This should automatically occur the next time you connect to the codespace"

# Run the following to connect your cluster to ARC and install PAS
# RESOURCE_GROUP=[your_cluster_resource_group]
# az login [--use-device-code]
#
# If you've rebuilt this codespace, you'll also need to run the following command before running `az connectedk8s connect`:
# az connectedk8s delete -n $CODESPACE_NAME -g $RESOURCE_GROUP
#
# az connectedk8s connect -n $CODESPACE_NAME -g $RESOURCE_GROUP
# az connectedk8s enable-features -n $CODESPACE_NAME -g $RESOURCE_GROUP --features cluster-connect custom-locations
# az iot ops init --cluster $CODESPACE_NAME -g $RESOURCE_GROUP [--create-sync-rules]
