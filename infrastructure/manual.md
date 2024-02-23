# Infrastructure Setup Manual (mandatory steps are X)

X: necessary steps
* **Physical Resources** [chameleon cloud](https://www.chameleoncloud.org/) and [cloudlab](https://www.cloudlab.us/)
   1. Steps to leasing a server from Chameleon cloud [chameleon-lease](manual-installation/chameleon-lease.md)
   2. Uncommon stes of leasing a server from Cloudlab [cloudlab-lease](manual-installation/cloudlab-lease.md) from chameleon

Do the steps in the following orders to setup the environment:

* **Server Utility Tools** [zsh](https://www.zsh.org/) and [ohmyzsh](https://ohmyz.sh/)
   1. Installation of [zsh](https://github.com/ohmyzsh/ohmyzsh/wiki/Installing-ZSH)
   2. Installation of [ohmyzsh](https://github.com/ohmyzsh/ohmyzsh)
   3. Installation of [zsh autosuggestion](https://github.com/zsh-users/zsh-autosuggestions/blob/master/INSTALL.md)

* **Python Environment** X
  1. Download and install [miniconda](https://docs.conda.io/en/latest/miniconda.html)
  2. Create [conda](https://docs.conda.io/en/latest/miniconda.html) virtual-environment
     ```
      conda create --name central python=3.9.15
     ```
  3. Activate conda environment
     ```
      conda activate central
     ```
  4. if you want to use GPUs make sure that you have the correct version of CUDA and cuDNN installed from [here](https://docs.nvidia.com/deeplearning/cudnn/install-guide/index.html)

  5. Install the followings
     ```
      sudo apt install cmake libz-dev
     ```
  6. For Open-CV to work install:
    ```
      sudo apt-get update
      sudo apt-get install ffmpeg libsm6 libxext6  -y
    ```

* **Repos** X
Clone the repos in the following order

   1. [**MLServer Custom Fork**](https://github.com/saeid93/MLServer) and [Complete Manual](manual-installation/custom-mlserver.md) 
   2. **IPA** [ipa-private](https://github.com/reconfigurable-ml-pipeline/ipa-private) and install requirements
     ```
      pip install -r requirements.txt
     ```
   3. **inference_x** [inference_x](https://github.com/reconfigurable-ml-pipeline/inference_x) and install requirements
     ```
      pip install -r requirements.txt
     ```
   4. **Barazmoon saeed branch** [Barzamoon](https://github.com/reconfigurable-ml-pipeline/load_tester)

**Note** MLServer installation will install torch and tensorflow. However, if you have skipped MLServer installation use [PyTorch](https://pytorch.org/) or [Tensorflow](https://www.tensorflow.org/install/pip#virtual-environment-install) isntallation manual to installation of them based-on your preference

* **Project Data** X
Project data are stored in the google bucket [`ipa-results`](https://console.cloud.google.com/storage/browser?authuser=7&hl=en&project=kubernetes-consolidation)
1. Install [Gcloud CLI](https://cloud.google.com/sdk/docs/install) for downloading data.

* **Infrastracture** [Kubernetes](https://kubernetes.io/) X
   1. Install [Helm](https://helm.sh/docs/intro/install/)
   3. Setup a K8S cluster [k8s-setup](manual-installation/setup-chameleon-k8s.md)
   3. To setup with in-place vpa feature use [in-place installation manual](installation/in-place-installation.md)
   4. Set up multi node cluster [Multi-node cluster](https://microk8s.io/docs/clustering)

* **Network Service Mesh Tool** [Istio](https://istio.io/) X
   1. Setup Istio on Chameleon [istio-setup](manual-installation/setup-istio.md)

* **ML Inference DAG Technology** [Seldon Core](https://docs.seldon.io/projects/seldon-core/en/latest/) X
   1. Setup the Seldon core operator on your cluster [seldon-core-installation](manual-installation/setup-seldon-core-installation.md)
   2. See [Overview of Component](https://docs.seldon.io/projects/seldon-core/en/latest/workflow/overview.html#metrics-with-prometheus) for an overview of the Seldon core framework
   3. Also see the link to the [shortlisted](manual-installation/guide-seldon.md) parts of the documentation

* **Testing Installation**
   1. Up to this point you should have a complete working installation
   2. To test the installation use [test-installation](manual-installation/test_installation.md)

* **Resources Observibility Tool** [Prometheus](https://prometheus.io/) and [Grafana](https://grafana.com/) X
   1. Setup the observibitliy tools for services resource usage monitoring [setup-observibility](manual-installation/setup-prometeus-monitoring.md)
   2. check out the [guide-obervibility](manual-installation/guide-prometheus.md) for usefule information about using the observability tools

* **Docker** X
   1. For compiling model images of the pipeline you'll need [Dcoker](https://www.docker.com/)
   2. Install them using the offical documentation for [docker-doc](https://docs.docker.com/engine/install/ubuntu/). Also do the [post-installation-steps](https://docs.docker.com/engine/install/linux-postinstall/)

* **Chameleon Object Storage**
   1. we keep the datasets and models in the Chameleon object storage to moount it on a directory use the guide on [chameleon website](https://chameleoncloud.readthedocs.io/en/latest/technical/swift.html#:~:text=Chameleon%20provides%20an%20object%20store,results%20produced%20by%20your%20experiments.)

* **Minio and nfs** X
   1. [Minio](https://min.io/) and [nfs](https://en.wikipedia.org/wiki/Network_File_System) are needed for the storage
   2. Setup them using [setup-storage](manual-installation/setup-storage.md)

* **Guide to Deploy a Model and Pipeline**
   1. [Guide-model-deployment](manual-installation/guide-model-deployment.md)

* **Debug Mode**
    1. Debug mode with saving pods logs [debug-mode](manual-installation/debug-mode.md)

* **Multi Node server**
    1. How to set multiNode cluster [MultiNode](manual-installation/multi-node.md)

* **GPU server**
    1. How to set GPU cluster [GPU](manual-installation/gpu.md)

* **GPU Sharing**
    1. How to set GPU sharing [GPU](manual-installation/gpu-sharing.md)

* **GPU metrics**
   1. How to use GPU [metrics](manual-installation/gpu-metrics.md)

* **ML Inference Server**
   1. [Triton Server](https://developer.nvidia.com/nvidia-triton-inference-server)

* **Load Tester**
   1. For load testing we use the [BarAzmoon library saeed branch](https://github.com/reconfigurable-ml-pipeline/load_tester). Installed as instructed in the reop.

* **Installing Gurobi Sovler** X
   1. [Gurobi Solver Installation](manual-installation/gurobi-installation.md)

* **Installing Image registry**
   1. Images can be added to the local registry using the following approach in [microk8s containerd runtime](https://microk8s.io/docs/registry-images). However, it is easier to just load pipeline once before experiment to make sure they are cached.

* **Kubernetes Development Tools**
   1. For implementing K8S operator and hacking Seldon core we will need the installation of a set Gloang related tools, find the full manual on [Kubernetes Development Tools](manual-installation/k8s-development-tools.md)

* **Setup Remote Load Tester**
   1. To place the load tester on a remote machine follow [these steps](manual-installation/setup-remote-load-tester.md)

