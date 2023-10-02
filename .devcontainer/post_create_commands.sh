# create local k3s cluster
k3d cluster create -i ghcr.io/jlian/k3d-nfs:v1.25.3-k3s1

# write kubeconfig
k3d kubeconfig get k3s-default > ~/.kube/config

# install connectedk8s extension
az extension add -n connectedk8s -y

# local extension install
pip install -U --target ~/.azure/cliextensions/azure-edge .

# Run the following to connect your cluster to ARC and install PAS
# RESOURCE_GROUP=[your_cluster_resource_group]
# az login [--use-device-code]
# az connectedk8s connect -n $CODESPACE_NAME -g $RESOURCE_GROUP
# az connectedk8s enable-features -n $CODESPACE_NAME -g $RESOURCE_GROUP --features cluster-connect custom-locations
# az edge init --cluster $CODESPACE_NAME -g $RESOURCE_GROUP [--create-sync-rules]