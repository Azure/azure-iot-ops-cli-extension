#!/bin/sh

set -o errexit
set -o nounset
set -o pipefail

echo "Starting On Create Command"

# Copy the custom first run notice over
sudo cp .devcontainer/welcome.md /usr/local/etc/vscode-dev-containers/first-run-notice.md

# wait for docker
until docker version > /dev/null 2>&1
do
  echo "Checking if docker daemon has started..."
  sleep 10s
done

# create local k3s cluster
echo "Creating k3d cluster"
k3d cluster delete
k3d cluster create \
-p '1883:1883@loadbalancer' \
-p '8883:8883@loadbalancer'