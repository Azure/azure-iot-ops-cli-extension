#!/bin/bash
: '
This script is used to create and/or connect to a github codespace running a kubernetes cluster

Requirements:
 - github CLI - `gh` (logged in with codespace permissions)
 - grep
 - sed

Usage:
    codespace_connect.sh -c codepsace_name
    codespace_connect.sh -r azure/azure-iot-operations-cli-extension [-b dev]

If you provide a codespace name, the script will attempt to start and use that codespace
If you provide a repo and an optional branch (dev is default), it will create a codespace first.

Once that initial step is complete, the script will:
 - Copy ~/.kube/config from the codespace to your local ~/.kube/config
 - Replace the local 0.0.0.0 IP address in your kubeconfig with local 127.0.0.1
 - Parse the service port from the kubeconfig
 - Forward your codespaces port to your local machine port

This script will pause / stall while the port is forwarded, so please run in a separate process.
'

#  Parse options - R repo B branch C codespace
while getopts ":r:b:c:" opt; do
  case $opt in
    r) REPO="$OPTARG"
    ;;
    b) BRANCH="$OPTARG"
    ;;
    c) CODESPACE_NAME="$OPTARG"
    ;;
    \?) echo "Invalid option -$OPTARG" >&2
    exit 1
    ;;
  esac
done

# Use 'dev' if no branch provided
BRANCH="${BRANCH:-dev}"

# Kubeconfig paths
LOCAL_KUBECONF=~/.kube/config
# needs to be quoted or it will be replaced with local equivalent of '~'
REMOTE_KUBECONF="~/.kube/config"

# If no codespace name was provided
if [ -z $CODESPACE_NAME ]; then
    # without a repo or a branch we cannot create a codespace
    if [ -z $REPO ] || [ -z $BRANCH ]; then
        echo "Must either provide '-r org/repo [-b branch]' to create a codespace or '-c codespace' to connect to an existing codespace" 
        exit 1
    else
        # Create codespace
        echo "Creating codespace on $REPO using branch $BRANCH"
        CODESPACE_NAME=$(gh codespace create -R $REPO -b $BRANCH -m "standardLinux32gb")
        echo "Created codespace $CODESPACE_NAME"
    fi
else
    echo "Using existing codespace $CODESPACE_NAME"
fi

# Copy kubeconfig from codespace
TRIES=0
MAX_TRIES=5
SLEEP=15s
echo "Copying $REMOTE_KUBECONF from codespace $CODESPACE_NAME to local $LOCAL_KUBECONF"
until gh codespace cp -e "remote:$REMOTE_KUBECONF" -e $LOCAL_KUBECONF -c $CODESPACE_NAME || (( TRIES++ >= MAX_TRIES ))
do
    echo "Attempt $TRIES: Failed to copy kubeconfig, retrying in 15 seconds"
    sleep $SLEEP
done

# Update local IP
echo "Updating localhost endpoint in local config $LOCAL_KUBECONF"
sed -i -e "s/0.0.0.0/127.0.0.1/g" "$LOCAL_KUBECONF"

# Parse port
echo "Determining port from local $LOCAL_KUBECONF"
PORT=$(grep -Ei 'server:' $LOCAL_KUBECONF | grep -oEi '[0-9]+$')

# Forward port
echo "forwarding codespace $CODESPACE_NAME port $PORT to local port $PORT"
gh codespace ports forward $PORT:$PORT -c $CODESPACE_NAME
