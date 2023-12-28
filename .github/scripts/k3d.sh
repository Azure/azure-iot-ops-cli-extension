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
export K3D_FIX_MOUNTS=1
k3d cluster create -i ghcr.io/jlian/k3d-nfs:v1.25.3-k3s1 \
-p '1883:1883@loadbalancer' \
-p '8883:8883@loadbalancer' \
-p '6001:6001@loadbalancer' \
-p '4000:80@loadbalancer'
