#!/bin/bash

app="k3d"
release_url="https://github.com/k3d-io/k3d/releases/download"
k3d_version="v5.5.1"
k3d_binary="k3d-linux-amd64"
k3d_url="$release_url/$k3d_version/$k3d_binary"
k3d_install_dir="/usr/local/bin"

# install k3d
curl -sL $k3d_url -o "$k3d_binary"
sudo chmod +x "$k3d_binary"
sudo cp "$k3d_binary" "$k3d_install_dir/$app"

# create cluster
k3d cluster create

# downgrade helm to temporarily fix issue with helm
curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash -s -- --version v3.12.3

# install e4k, e4i, opcua
helm install e4k oci://e4kpreview.azurecr.io/helm/az-e4k --version 0.6.0 --set global.quickstart=true
helm upgrade -i e4i oci://e4ipreview.azurecr.io/helm/az-e4i --version 0.5.1 --namespace e4i-runtime --create-namespace --set mqttBroker.authenticationMethod="serviceAccountToken" --set mqttBroker.name="azedge-dmqtt-frontend" --set mqttBroker.namespace="default" --set opcPlcSimulation.deploy=true --wait
helm upgrade -i opcua oci://e4ipreview.azurecr.io/helm/az-e4i-opcua-connector --version 0.5.1 --namespace opcua --create-namespace --set payloadCompression="none" --set opcUaConnector.settings.discoveryUrl="opc.tcp://opcplc.e4i-runtime:50000" --set opcUaConnector.settings.autoAcceptUntrustedCertificates=true --set mqttBroker.name="azedge-dmqtt-frontend" --set mqttBroker.namespace="default" --set mqttBroker.authenticationMethod="serviceAccountToken" --wait
