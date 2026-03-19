#!/usr/bin/env bash
set -o pipefail

# Script to find Kubernetes resources with specific keywords but WITHOUT their corresponding labels
# Compatible with bash 4+ and zsh

command -v jq >/dev/null 2>&1 || { echo "jq is required but not installed."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required but not installed."; exit 1; }

# Color codes
GREEN='\033[0;32m'      # Green for correct labels
RED='\033[0;31m'        # Red for missing labels (CLI gaps)
BOLD='\033[1m'          # Bold for titles
RESET='\033[0m'         # Reset colors

echo -e "${BOLD}=== Finding resources with keywords but WITHOUT correct labels ===${RESET}"
echo ""

# Define keyword to label mappings
# Format: "keyword1|keyword2|keyword3:expected-label-value"
declare -A KEYWORD_LABEL_MAP=(
    ["mq|broker"]="microsoft-iotoperations-mqttbroker"
    ["opcua|opc"]="microsoft-iotoperations-opcuabroker"
    ["akri"]="microsoft-iotoperations-akri"
    ["dataflow"]="microsoft-iotoperations-dataflows"
    ["schema-registry|schema_registry|adr"]="microsoft-iotoperations-schemas"
    ["meso|observability"]="microsoft-iotoperations-observability"
)

# All valid AIO app.kubernetes.io/name label values — derived from KEYWORD_LABEL_MAP
# plus the base label, so this stays in sync automatically.
VALID_AIO_LABELS=("microsoft-iotoperations")
for _label in "${KEYWORD_LABEL_MAP[@]}"; do
    VALID_AIO_LABELS+=("${_label}")
done
# Sub-component label variant not in KEYWORD_LABEL_MAP
VALID_AIO_LABELS+=("microsoft-iotoperations-observability-cluster-metrics")
unset _label

# Resources that are intentionally unlabeled or already captured via alternative means
# (e.g. cert-manager module, no diagnostic value). Format: "namespace/name".
# These are known gaps that do NOT need a CLI fix.
KNOWN_UNLABELED_EXCLUSIONS=(
    # Captured by cert-manager module; adding the common label is a service team task
    "azure-iot-operations/azure-iot-operations-observability-trust-bundle"
    # Bare serviceaccount with no diagnostic content
    "azure-iot-operations/mqtt-client"
)

# Get all resource types in the cluster
RESOURCE_TYPES=(
    "pods"
    "services"
    "deployments"
    "replicasets"
    "statefulsets"
    "daemonsets"
    "configmaps"
    "serviceaccounts"
    "persistentvolumeclaims"
    "jobs"
    "cronjobs"
    "ingresses"
    "networkpolicies"
    "validatingwebhookconfigurations"
    "mutatingwebhookconfigurations"
)

UNLABELED_RESOURCES=()

# Function to check if a name matches any keyword pattern
matches_keyword() {
    local name=$1
    local keywords=$2
    local name_lower=$(echo "${name}" | tr '[:upper:]' '[:lower:]')
    
    # Split keywords by | (compatible with both bash and zsh)
    IFS='|' read -ra keyword_array <<< "${keywords}"
    for keyword in "${keyword_array[@]}"; do
        if echo "${name_lower}" | grep -q "${keyword}"; then
            return 0
        fi
    done
    return 1
}

# Function to check if a label is valid for a resource
is_label_valid() {
    local label_value=$1
    local expected_label=$2

    # Check if it matches the expected label
    if [[ "${label_value}" == "${expected_label}" ]]; then
        return 0
    fi

    # If the resource already has any valid AIO label (just a different one), it is
    # owned by another AIO service — not a labeling gap, just a name collision.
    for valid_label in "${VALID_AIO_LABELS[@]}"; do
        if [[ "${label_value}" == "${valid_label}" ]]; then
            return 0
        fi
    done

    return 1
}

# Function to check if a namespace/name pair is in the known exclusions list
is_excluded() {
    local namespace=$1
    local name=$2
    local key="${namespace}/${name}"
    for exclusion in "${KNOWN_UNLABELED_EXCLUSIONS[@]}"; do
        if [[ "${exclusion}" == "${key}" ]]; then
            return 0
        fi
    done
    return 1
}

# Check each keyword-label pair
# Compatible iteration over associative array keys (works in both bash and zsh)
for keywords_pattern in "${!KEYWORD_LABEL_MAP[@]}"; do
    expected_label="${KEYWORD_LABEL_MAP[$keywords_pattern]}"
    
    echo "========================================"
    echo -e "Checking resources with keywords: ${BOLD}${keywords_pattern}${RESET}"
    echo -e "Expected label: ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}"
    echo "========================================"
    echo ""
    
    for resource in "${RESOURCE_TYPES[@]}"; do
        echo "Checking ${resource}..."
        
        # Get all resources
        all_resources=$(kubectl get ${resource} --all-namespaces -o wide 2>/dev/null || true)

        if [[ -n "${all_resources}" ]]; then
            # Check each line for matching keywords
            while IFS= read -r line; do
                # Extract namespace and name from the line
                namespace=$(echo "${line}" | awk '{print $1}')
                name=$(echo "${line}" | awk '{print $2}')
                
                # Skip if empty
                if [[ -z "${namespace}" ]] || [[ -z "${name}" ]]; then
                    continue
                fi
                
                # Check if name matches any keyword in the pattern
                if matches_keyword "${name}" "${keywords_pattern}"; then
                    # Get labels for this specific resource
                    if [[ "${namespace}" == "" ]] || [[ "${namespace}" == "<none>" ]]; then
                        labels=$(kubectl get ${resource} ${name} -o jsonpath='{.metadata.labels}' 2>/dev/null || true)
                    else
                        labels=$(kubectl get ${resource} ${name} -n ${namespace} -o jsonpath='{.metadata.labels}' 2>/dev/null || true)
                    fi
                    
                    # Check if it has the correct label
                    label_value=$(echo "${labels}" | jq -r '.["app.kubernetes.io/name"] // "no-label"' 2>/dev/null)
                    
                    if is_label_valid "${label_value}" "${expected_label}"; then
                        echo -e "  ${GREEN}✓ ${BOLD}${resource}${RESET}${GREEN} ${namespace}/${name} has correct label ${BOLD}app.kubernetes.io/name=${label_value}${RESET}"
                    elif is_excluded "${namespace}" "${name}"; then
                        echo -e "  ${GREEN}~ ${BOLD}${resource}${RESET}${GREEN} ${namespace}/${name} is a known exclusion (no label needed by CLI)${RESET}"
                    else
                        echo -e "  ${RED}✗ ${BOLD}${resource}${RESET}${RED} ${namespace}/${name} does NOT have label ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}${RED} (current: ${label_value})${RESET}"
                        UNLABELED_RESOURCES+=("${resource}|${namespace}|${name}|${expected_label}|${label_value}")
                    fi
                fi
            done < <(echo "${all_resources}" | tail -n +2)
        fi
    done
    echo ""
done

# Display final results
echo ""
echo "=========================================="
echo "=== FINAL RESULTS: CLI GAPS ==="
echo "=== (resources missing from support bundle) ==="
echo "=========================================="
echo ""

if [[ ${#UNLABELED_RESOURCES[@]} -eq 0 ]]; then
    echo -e "${GREEN}✓ No CLI gaps found! All runtime resources are captured by the support bundle.${RESET}"
else
    echo -e "${RED}Found ${BOLD}${#UNLABELED_RESOURCES[@]}${RESET}${RED} resource(s) missing from support bundle:${RESET}"
    echo ""
    for resource in "${UNLABELED_RESOURCES[@]}"; do
        IFS='|' read -r kind namespace name expected_label current_label <<< "${resource}"
        echo -e "  ${BOLD}${namespace}/${name}${RESET} (${kind}) - Expected: ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}, Current: ${current_label}"
    done
    echo ""
fi

echo ""
echo "=== Done ==="
