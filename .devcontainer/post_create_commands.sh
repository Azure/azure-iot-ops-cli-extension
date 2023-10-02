# create local k3s cluster
k3d cluster create -i ghcr.io/jlian/k3d-nfs:v1.25.3-k3s1

# install connectedk8s extension
az extension add -n connectedk8s -y