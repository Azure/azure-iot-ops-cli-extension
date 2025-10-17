#!/usr/bin/env bash

# Script to find Kubernetes resources with specific keywords but WITHOUT their corresponding labels
# Compatible with bash 4+ and zsh

# Color codes
GREEN='\033[0;32m'      # Green for correct labels
RED='\033[0;31m'        # Red for missing labels
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

# Get all resource types in the cluster
RESOURCE_TYPES=(
    "pods"
    "services"
    "deployments"
    "replicasets"
    "statefulsets"
    "daemonsets"
    "configmaps"
    # "secrets"
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
# Handles special cases where alternative labels are acceptable
is_label_valid() {
    local name=$1
    local label_value=$2
    local expected_label=$3
    local name_lower=$(echo "${name}" | tr '[:upper:]' '[:lower:]')
    
    # Check if it matches the expected label
    if [[ "${label_value}" == "${expected_label}" ]]; then
        return 0
    fi
    
    # Special case 1: 'observability-cluster-metrics' resources can have 'microsoft-iotoperations-observability-cluster-metrics' label
    if echo "${name_lower}" | grep -q "observability-cluster-metrics"; then
        if [[ "${label_value}" == "microsoft-iotoperations-observability-cluster-metrics" ]]; then
            return 0
        fi
    fi
    
    # Special case 2: 'akri-adr' resources can still have 'microsoft-iotoperations-akri' label
    if echo "${name_lower}" | grep -q "akri-adr"; then
        if [[ "${label_value}" == "microsoft-iotoperations-akri" ]]; then
            return 0
        fi
    fi
    
    # Special case 3: 'opc-ua-broker' or 'opc-opcuabroker' resources can have 'microsoft-iotoperations-opcuabroker' label
    if echo "${name_lower}" | grep -qE "opc-ua-broker|opc-opcuabroker"; then
        if [[ "${label_value}" == "microsoft-iotoperations-opcuabroker" ]]; then
            return 0
        fi
    fi
    
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
        all_resources=$(kubectl get ${resource} --all-namespaces -o wide 2>/dev/null)
        
        if [[ $? -eq 0 ]] && [[ -n "${all_resources}" ]]; then
            # Check each line for matching keywords
            echo "${all_resources}" | tail -n +2 | while read -r line; do
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
                        labels=$(kubectl get ${resource} ${name} -o jsonpath='{.metadata.labels}' 2>/dev/null)
                    else
                        labels=$(kubectl get ${resource} ${name} -n ${namespace} -o jsonpath='{.metadata.labels}' 2>/dev/null)
                    fi
                    
                    # Check if it has the correct label
                    label_value=$(echo "${labels}" | jq -r '.["app.kubernetes.io/name"] // "no-label"' 2>/dev/null)
                    
                    if is_label_valid "${name}" "${label_value}" "${expected_label}"; then
                        echo -e "  ${GREEN}✓ ${BOLD}${resource}${RESET}${GREEN} ${namespace}/${name} has correct label ${BOLD}app.kubernetes.io/name=${label_value}${RESET}"
                    else
                        echo -e "  ${RED}✗ ${BOLD}${resource}${RESET}${RED} ${namespace}/${name} does NOT have label ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}${RED} (current: ${label_value})${RESET}"
                        UNLABELED_RESOURCES+=("${resource}\t${namespace}\t${name}\t${expected_label}\t${label_value}")
                    fi
                fi
            done
        fi
    done
    echo ""
    
    # Check CRDs
    echo "Checking Custom Resource Definitions..."
    all_crds=$(kubectl get crd 2>/dev/null)
    
    if [[ -n "${all_crds}" ]]; then
        echo "${all_crds}" | tail -n +2 | while read -r line; do
            # Extract CRD name
            crd_name=$(echo "${line}" | awk '{print $1}')
            
            # Skip if empty
            if [[ -z "${crd_name}" ]]; then
                continue
            fi
            
            # Check if name matches any keyword in the pattern
            if matches_keyword "${crd_name}" "${keywords_pattern}"; then
                # Get labels for this CRD
                labels=$(kubectl get crd ${crd_name} -o jsonpath='{.metadata.labels}' 2>/dev/null)
                label_value=$(echo "${labels}" | jq -r '.["app.kubernetes.io/name"] // "no-label"' 2>/dev/null)
                
                if is_label_valid "${crd_name}" "${label_value}" "${expected_label}"; then
                    echo -e "  ${GREEN}✓ ${BOLD}CRD${RESET}${GREEN} ${crd_name} has correct label ${BOLD}app.kubernetes.io/name=${label_value}${RESET}"
                else
                    echo -e "  ${RED}✗ ${BOLD}CRD${RESET}${RED} ${crd_name} does NOT have label ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}${RED} (current: ${label_value})${RESET}"
                    UNLABELED_RESOURCES+=("CustomResourceDefinition\tcluster-wide\t${crd_name}\t${expected_label}\t${label_value}")
                fi
            fi
        done
    fi
    echo ""
    
    # Check instances of all CRDs
    echo "Checking Custom Resource instances..."
    kubectl get crd -o name 2>/dev/null | while read crd; do
        crd_name=${crd#customresourcedefinition.apiextensions.k8s.io/}
        
        # Get all instances of this CRD
        all_instances=$(kubectl get ${crd_name} --all-namespaces 2>/dev/null)
        
        if [[ -n "${all_instances}" ]]; then
            echo "${all_instances}" | tail -n +2 | while read -r line; do
                # Extract namespace and name
                namespace=$(echo "${line}" | awk '{print $1}')
                name=$(echo "${line}" | awk '{print $2}')
                
                # Skip if empty
                if [[ -z "${namespace}" ]] || [[ -z "${name}" ]]; then
                    continue
                fi
                
                # Check if name matches any keyword in the pattern
                if matches_keyword "${name}" "${keywords_pattern}"; then
                    # Get labels for this instance
                    if [[ "${namespace}" == "" ]] || [[ "${namespace}" == "<none>" ]]; then
                        labels=$(kubectl get ${crd_name} ${name} -o jsonpath='{.metadata.labels}' 2>/dev/null)
                    else
                        labels=$(kubectl get ${crd_name} ${name} -n ${namespace} -o jsonpath='{.metadata.labels}' 2>/dev/null)
                    fi
                    
                    label_value=$(echo "${labels}" | jq -r '.["app.kubernetes.io/name"] // "no-label"' 2>/dev/null)
                    
                    if is_label_valid "${name}" "${label_value}" "${expected_label}"; then
                        echo -e "  ${GREEN}✓ ${BOLD}${crd_name}${RESET}${GREEN} ${namespace}/${name} has correct label ${BOLD}app.kubernetes.io/name=${label_value}${RESET}"
                    else
                        echo -e "  ${RED}✗ ${BOLD}${crd_name}${RESET}${RED} ${namespace}/${name} does NOT have label ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}${RED} (current: ${label_value})${RESET}"
                        UNLABELED_RESOURCES+=("${crd_name}\t${namespace}\t${name}\t${expected_label}\t${label_value}")
                    fi
                fi
            done
        fi
    done
    echo ""
    echo ""
done

# Display final results
echo ""
echo "=========================================="
echo "=== FINAL RESULTS ==="
echo "=========================================="
echo ""

if [[ ${#UNLABELED_RESOURCES[@]} -eq 0 ]]; then
    echo -e "${GREEN}✓ No unlabeled resources found! All resources have the proper labels.${RESET}"
else
    echo -e "${RED}Found ${BOLD}${#UNLABELED_RESOURCES[@]}${RESET}${RED} unlabeled resource(s):${RESET}"
    echo ""
    for resource in "${UNLABELED_RESOURCES[@]}"; do
        IFS=$'\t' read -r kind namespace name expected_label current_label <<< "${resource}"
        echo -e "  ${BOLD}${namespace}/${name}${RESET} (${kind}) - Expected: ${BOLD}app.kubernetes.io/name=${expected_label}${RESET}, Current: ${current_label}"
    done
    echo ""
fi

echo ""
echo "=== Done ==="
