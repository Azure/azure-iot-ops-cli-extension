# CLUSTER NAME
echo 'export CLUSTER_NAME=${CODESPACE_NAME}' >> ~/.bashrc
echo 'export KUBECONFIG=~/.kube/config' >> ~/.bashrc
source ~/.bashrc

# write kubeconfig
k3d kubeconfig get k3s-default > ~/.kube/config

echo "Setting up CLI dev environment"

# Install virtualenv
python -m venv env
source env/bin/activate

# Install azdev
echo "Install AZDEV"
pip install azdev

# Install CLI core (EDGE) and configure extension repo
echo "azdev setup"
azdev setup -c EDGE -r ./

# install dev requirements (overrides setuptools)
echo "Installing extension and dev requirements..."
pip install -r dev_requirements.txt

# setup tox environment dependencies in parallel, but don't run tests
echo "Creating local tox environments..."
python -m pip install tox
tox -np -e lint,python,coverage

# Run the following to connect your cluster to ARC
# RESOURCE_GROUP=[your_cluster_resource_group]
# az login [--use-device-code]
#
# If you've rebuilt this codespace, you'll also need to run the following command before running `az connectedk8s connect`:
# az connectedk8s delete -n $CODESPACE_NAME -g $RESOURCE_GROUP
#
# az connectedk8s connect -n $CODESPACE_NAME -g $RESOURCE_GROUP
# az connectedk8s enable-features -n $CODESPACE_NAME -g $RESOURCE_GROUP --features cluster-connect custom-locations