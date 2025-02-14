#!/bin/bash

install_kubectl() {
    echo "Install kubectl"
    curl -LO https://dl.k8s.io/release/v$K8SVERSION.2/bin/linux/amd64/kubectl
    sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
    sudo microk8s config > $HOME/.kube/config
    sudo ufw allow 16443
    echo "y" | sudo ufw enable
    echo "End Install kubectl"
    rm kubectl
}

install_network_tools() {
    sudo apt install iproute2 iperf
    sudo ufw allow 5001/udp
    sudo ufw allow 5001/tcp
    echo "End Install Network tools"
    echo
}


function install_istio() {
    echo "Install Istio"

    if [ "$VPABRANCH" = "Yes" ]; then
        minikube addons enable istio-provisioner
        minikube addons enable istio
    else
        sudo microk8s enable community
        sudo microk8s enable istio
    fi
    # kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.13/samples/addons/prometheus.yaml
    # kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.13/samples/addons/kiali.yaml
    # script_dir=$(dirname "$0")
    # cd "$script_dir"
    # kubectl apply -f istio-monitoring.yaml
    echo "End Install Istio"
    echo
}

function install_seldon_core() {
    echo "Install Seldon Core"
    kubectl create namespace seldon-system
    helm install seldon-core seldon-core-operator \
        --repo https://storage.googleapis.com/seldon-charts \
        --set usageMetrics.enabled=true \
        --set istio.enabled=true \
        --namespace seldon-system

    cat <<EOF | kubectl apply -f -
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: seldon-gateway
  namespace: istio-system
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 80
      name: http
      protocol: HTTP
    hosts:
    - "*"
EOF

    kubectl patch svc istio-ingressgateway -n istio-system --patch '{"spec": {"ports": [{"name": "http2", "nodePort": 32000, "port": 80, "protocol": "TCP", "targetPort": 8080}]}}'
    echo "End Install Seldon Core"
    echo
}

function configure_monitoring() {
    echo "Configure monitoring"

    if [ "$VPABRANCH" = "Yes" ]; then
        helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
        helm install prometheus prometheus-community/prometheus
        helm install prometheus prometheus-community/prometheus
    else
        sudo microk8s enable prometheus
    fi

    cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: seldon-podmonitor
  namespace: observability
spec:
  selector:
    matchLabels:
      app.kubernetes.io/managed-by: seldon-core
  podMetricsEndpoints:
    - port: metrics
      interval: 1s
      path: /prometheus
  namespaceSelector:
    any: true
EOF

    kubectl apply -f ~/infrastructure/istio-monitoring.yaml
    kubectl patch svc prometheus-k8s -n monitoring --type='json' -p '[{"op":"replace","path":"/spec/type","value":"NodePort"}]'
    kubectl patch svc grafana -n monitoring --type='json' -p '[{"op":"replace","path":"/spec/type","value":"NodePort"}]'
    kubectl patch svc prometheus-k8s -n monitoring --patch '{"spec": {"type": "NodePort", "ports": [{"port": 9090, "nodePort": 30090}]}}'
    kubectl patch svc grafana -n monitoring --patch '{"spec": {"type": "NodePort", "ports": [{"port": 3000, "nodePort": 30300}]}}'
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.13/samples/addons/kiali.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.13/samples/addons/jaeger.yaml
    echo "End Configure monitoring"
    echo
}

function install_docker() {
    echo "Install Docker"
    sudo apt-get remove -y docker docker-engine docker.io containerd runc
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo groupadd docker
    sudo usermod -aG docker $USER
    sudo systemctl enable docker.service
    sudo systemctl enable containerd.service
    rm get-docker.sh
    echo "End Install Docker"
    echo
}

install_kubectl
install_istio
if [ "$VPABRANCH" = "No" ]; then
    install_seldon_core
fi
configure_monitoring
install_docker
install_network_tools
