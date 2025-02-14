from typing import Dict, Literal, Tuple, Union, Optional, Any
import time
import tqdm
import numpy as np
from kubernetes import config
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from typing import List
import os
import sys
import pandas as pd
import concurrent.futures
import tensorflow as tf
import requests
from copy import deepcopy
from tensorflow.keras.models import load_model
import re
from statsmodels.tsa.arima.model import ARIMA
from time import sleep

# get an absolute path to the directory that contains parent files
project_dir = os.path.dirname(__file__)
sys.path.append(os.path.normpath(os.path.join(project_dir, "..")))
from experiments.utils.pipeline_operations import (
    check_node_up,
    get_pod_name,
    check_node_loaded,
    is_terminating,
    get_cpu_model_name,
    kube_api
)
from experiments.utils.prometheus import PromClient
from optimizer import Optimizer, Pipeline
from experiments.utils.constants import NAMESPACE, LSTM_PATH, LSTM_INPUT_SIZE
from experiments.utils import logger
from optimizer.optimizer import Optimizer

prom_client = PromClient()

from kubernetes import config
from kubernetes import client

try:
    config.load_kube_config()
    kube_config = client.Configuration().get_default_copy()
except AttributeError:
    kube_config = client.Configuration()
    kube_config.assert_hostname = False
client.Configuration.set_default(kube_config)

kube_custom_api = client.CustomObjectsApi()


class Adapter:
    def __init__(
        self,
        pipeline_name: str,
        pipeline: Pipeline,
        node_names: List[str],
        adaptation_interval: int,
        optimization_method: Literal["dynainf", "fa2"],
        allocation_mode: Literal["base", "variable"],
        only_measured_profiles: bool,
        scaling_cap: int,
        batching_cap: int,
        cpu_cap: int,
        alpha: float,
        # beta: float,
        # gamma: float,
        num_state_limit: int,
        monitoring_duration: int,
        predictor_type: str,
        baseline_mode: Optional[str] = None,
        central_queue: bool = False,
        debug_mode: bool = False,
        predictor_margin: int = 100,
        teleport_mode: bool = False,
        teleport_interval: int = 10,
        backup_predictor_type: str = "max",
        backup_predictor_duration: int = 2,
        minikube_ip: str = "localhost",
        only_pod: bool = False,

    ) -> None:
        """
        Args:
            pipeline_name (str): name of the pipeline
            pipeline (Pipeline): pipeline object
            adaptation_interval (int): adaptation interval of the pipeline
            optimization_method (Literal[gurobi, brute-force])
            allocation_mode (Literal[base;variable])
            only_measured_profiles (bool)
            scaling_cap (int)
            alpha (float): accuracy weight
            beta (float): resource weight
            gamma (float): batching weight
            num_state_limit (int): cap on the number of optimal states
            monitoring_duration (int): the monitoring
                deamon observing duration
        """
        self.pipeline_name = pipeline_name
        self.pipeline = pipeline
        self.node_names = node_names
        self.adaptation_interval = adaptation_interval
        self.debug_mode = debug_mode
        self.backup_predictor_type = backup_predictor_type
        self.backup_predictor_duration = backup_predictor_duration
        self.minikube_ip = minikube_ip
        self.optimizer = Optimizer(
            pipeline=pipeline,
            allocation_mode=allocation_mode,
            complete_profile=False,
            only_measured_profiles=only_measured_profiles,
            random_sample=False,
            baseline_mode=baseline_mode,
        )
        self.optimization_method = optimization_method
        self.scaling_cap = scaling_cap
        self.batching_cap = batching_cap
        self.cpu_cap = cpu_cap
        self.alpha = alpha
        self.only_pod = only_pod
        # self.beta = beta
        # self.gamma = gamma
        self.num_state_limit = num_state_limit
        self.monitoring_duration = monitoring_duration
        self.predictor_type = predictor_type
        self.monitoring = Monitoring(
            pipeline_name=self.pipeline_name, sla=self.pipeline.sla
        )
        # self.predictor = Predictor(
        #     predictor_type=self.predictor_type,
        #     predictor_margin=predictor_margin,
        #     backup_predictor_type=self.backup_predictor_type,
        #     backup_predictor_duration=self.backup_predictor_duration,
        # )
        self.central_queue = central_queue
        self.teleport_mode = teleport_mode
        self.teleport_interval = teleport_interval
        self.only_pod = only_pod

    # def start_adaptation(self, workload=None):
    def start_adaptation(self, predicted_load: int, workload=None):
        # 0. Check if pipeline is up
        # 1. Use monitoring for periodically checking the status of
        #     the pipeline in terms of load
        # 2. Watches the incoming load in the system
        # 3. LSTM for predicting the load
        # 4. Get the existing pipeline state, batch size, model variant and replicas per
        #     each node
        # 5. Give the load and pipeline status to the optimizer
        # 6. Compare the optimal solutions from the optimzer
        #     to the existing pipeline's state
        # 7. Use the change config script to change the pipelien to the new config
        if workload is not None:  # in teleport mode workload is read from dataset
            workload_timestep = 0
        time_interval = 0
        timestep = 0
        pipeline_up = False
        while True:
            check_interval = 5
            logger.info(
                f"Waiting for {check_interval} seconds before checking if the pipeline is up ..."
            )
            for _ in tqdm.tqdm(range(check_interval)):
                time.sleep(1)
            pipeline_up = check_node_loaded(node_name="router")
            terminating = is_terminating(node_name="router")
            if pipeline_up and not terminating:
                logger.info(f"Found pipeline, starting adaptation ...")
                initial_config = self.extract_current_config()
                self.monitoring.get_router_pod_name()

                to_save_config = self.saving_config_builder(
                    to_apply_config=deepcopy(initial_config),
                    node_orders=deepcopy(self.node_names),
                    # stage_wise_latencies=deepcopy(self.pipeline.stage_wise_latencies),
                    # stage_wise_throughputs=deepcopy(
                    #     self.pipeline.stage_wise_throughput
                    # ),
                    expected_latency=0
                )
                current_config = self.extract_current_config()
                self.monitoring.adaptation_step_report(
                    change_successful=[False for _ in range(len(self.node_names))],
                    to_apply_config=to_save_config,
                    timestep=timestep,
                    latest_sla=0,
                    time_interval=time_interval,
                    predicted_load=0,
                )
                break
        while True:
            logger.info("-" * 50)
            logger.info(f"Waiting {self.adaptation_interval}" " to make next descision")
            logger.info("-" * 50)
            for _ in tqdm.tqdm(range(self.adaptation_interval)):
                time.sleep(1)
            if self.teleport_mode:
                workload_timestep += self.adaptation_interval
            # check if the pipeline is up
            pipeline_up = check_node_up(node_name="router")
            if not pipeline_up:
                logger.info("-" * 50)
                logger.info(
                    "no pipeline in the system," " aborting adaptation process ..."
                )
                logger.info("-" * 50)
                break

            time_interval += self.adaptation_interval
            timestep += 1
            sla_series = self.monitoring.sla_monitor(
                monitoring_duration=self.monitoring_duration
            )
            latest_sla = sla_series[-1]
            logger.info("-" * 50)
            logger.info("-" * 50)
            expected_latency, optimal = self.optimizer.optimize(
                optimization_method=self.optimization_method,
                scaling_cap=self.scaling_cap,
                batching_cap=self.batching_cap,
                cpu_cap=self.cpu_cap,
                alpha=self.alpha,
                arrival_rate=predicted_load,
                latest_sla=latest_sla,
                num_state_limit=self.num_state_limit,
            )
            if optimal is not None and "objective" in optimal.columns:
                new_configs = self.output_parser(optimal)
                logger.info("-" * 50)
                logger.info(f"candidate configs:\n{new_configs}")
                logger.info("-" * 50)

                # check if the pipeline is up
                pipeline_up = check_node_up(node_name="router")
                if not pipeline_up:
                    logger.info("-" * 50)
                    logger.info(
                        "no pipeline in the system," " aborting adaptation process ..."
                    )
                    logger.info("-" * 50)
                to_apply_config = self.choose_config(new_configs)
                logger.info("-" * 50)
                logger.info(f"to be applied configs:\n{to_apply_config}")
                logger.info("-" * 50)

                if to_apply_config is not None:
                    if current_config != to_apply_config:
                        config_change_results = self.change_pipeline_config(to_apply_config)
                        if config_change_results:
                            current_config = deepcopy(to_apply_config)
                    else:
                        logger.info("new config similar to the old config, no change required")
            else:
                logger.info(
                    "optimizer couldn't find any optimal solution"
                    "the pipeline will stay the same"
                )
                config_change_results = [False for _ in range(len(self.node_names))]
                try:
                    to_apply_config = self.extract_current_config()
                except ApiException:
                    logger.info("-" * 50)
                    logger.info(
                        "no pipeline in the system," " aborting adaptation process ..."
                    )
                    logger.info("-" * 50)
                    # with the message that the process has ended
                    break
            if to_apply_config is not None:
                to_save_config = self.saving_config_builder(
                    to_apply_config=deepcopy(to_apply_config),
                    node_orders=deepcopy(self.node_names),
                    # stage_wise_latencies=deepcopy(self.pipeline.stage_wise_latencies),
                    # stage_wise_accuracies=deepcopy(self.pipeline.stage_wise_accuracies),
                    # stage_wise_throughputs=deepcopy(
                    #     self.pipeline.stage_wise_throughput
                    # ),
                    expected_latency=expected_latency
                )
            self.monitoring.adaptation_step_report(
                to_apply_config=to_save_config,
                timestep=timestep,
                time_interval=time_interval,
                latest_sla=latest_sla,
                predicted_load=predicted_load,

                change_successful=config_change_results,
            )

    def output_parser(self, optimizer_output: pd.DataFrame):
        new_configs = []
        for _, row in optimizer_output.iterrows():
            config = {}
            for task_id, task_name in enumerate(self.node_names):
                config[task_name] = {}
                config[task_name]["cpu"] = int(row[f"task_{task_id}_cpu"])
                config[task_name]["replicas"] = int(row[f"task_{task_id}_replicas"])
                config[task_name]["batch"] = int(row[f"task_{task_id}_batch"])
            new_configs.append(config)
        return new_configs

    def choose_config(self, new_configs: List[Dict[str, Dict[str, Union[str, int]]]]):
        # This should be from comparing with the
        # current config
        # easiest for now is to choose config with
        # with the least change from former config
        try:
            current_config = self.extract_current_config()
        except ApiException:
            return None
        new_config_socres = []
        for new_config in new_configs:
            new_config_score = 0
            for node_name, new_node_config in new_config.items():
                for config_knob, config_value in new_node_config.items():
                    if (
                        config_knob == "variant"
                        and config_value != current_config[node_name][config_knob]
                    ):
                        new_config_score -= 1
                    if (
                        config_knob == "batch"
                        and str(config_value) != current_config[node_name][config_knob]
                    ):
                        new_config_score -= 1
            new_config_socres.append(new_config_score)
        chosen_config_index = new_config_socres.index(max(new_config_socres))
        chosen_config = new_configs[chosen_config_index]
        return chosen_config

    def extract_current_config(self) -> List[Dict[str, Dict[str, Union[str, int]]]]:
        current_config = {}
        if self.only_pod:
            for node_name in self.node_names:
                node_config = {}
                # TODO check if it exists before extracting the config
                raw_config = kube_api.read_namespaced_pod(
                    namespace=NAMESPACE,
                    name=f"{node_name}-{node_name}-0-{node_name}")
                env_vars = raw_config.spec.containers[0].env
                replicas = 1
                cpu = int(raw_config.spec.containers[0].resources.limits['cpu'])
                for env_var in env_vars:
                    if env_var.name == "MODEL_VARIANT":
                        variant = env_var.value
                    if env_var.name == "MLSERVER_MODEL_MAX_BATCH_SIZE":
                        batch = env_var.value
                node_config["replicas"] = replicas
                # node_config["variant"] = variant
                node_config["cpu"] = cpu
                if not self.central_queue:
                    node_config["batch"] = batch
                else:
                    raw_queue_config = kube_custom_api.get_namespaced_custom_object(
                        group="apps",
                        version="v1",
                        namespace=NAMESPACE,
                        plural="deployments",
                        name=f"queue-{node_name}-queue-{node_name}-0-queue-{node_name}",
                    )
                    queue_component_config = raw_queue_config['spec']['template']['spec']['containers'][0]
                    queue_env_vars = queue_component_config["env"]
                    for queue_env_var in queue_env_vars:
                        if queue_env_var["name"] == "MLSERVER_MODEL_MAX_BATCH_SIZE":
                            batch = queue_env_var["value"]
                    node_config["batch"] = batch
                current_config[node_name] = node_config
        else:
            for node_name in self.node_names:
                node_config = {}
                # TODO check if it exists before extracting the config
                raw_config = kube_custom_api.get_namespaced_custom_object(
                    group="apps",
                    version="v1",
                    namespace=NAMESPACE,
                    plural="deployments",
                    name=f"{node_name}-{node_name}-0-{node_name}",
                )
                component_config = raw_config['spec']['template']['spec']['containers'][0]
                env_vars = component_config["env"]
                replicas = raw_config['spec']['replicas']
                cpu = int(component_config['resources']['requests']['cpu'])
                for env_var in env_vars:
                    if env_var["name"] == "MODEL_VARIANT":
                        variant = env_var["value"]
                    if env_var["name"] == "MLSERVER_MODEL_MAX_BATCH_SIZE":
                        batch = env_var["value"]
                node_config["replicas"] = replicas
                # node_config["variant"] = variant
                node_config["cpu"] = cpu
                if not self.central_queue:
                    node_config["batch"] = batch
                else:
                    raw_queue_config = kube_custom_api.get_namespaced_custom_object(
                        group="apps",
                        version="v1",
                        namespace=NAMESPACE,
                        plural="deployments",
                        name=f"queue-{node_name}-queue-{node_name}-0-queue-{node_name}",
                    )
                    queue_component_config = raw_queue_config['spec']['template']['spec']['containers'][0]
                    queue_env_vars = queue_component_config["env"]
                    for queue_env_var in queue_env_vars:
                        if queue_env_var["name"] == "MLSERVER_MODEL_MAX_BATCH_SIZE":
                            batch = queue_env_var["value"]
                    node_config["batch"] = batch
                current_config[node_name] = node_config
        return current_config

    def change_pipeline_config(self, config: List[bool]):
        """change the existing configuration based on the optimizer
           output
        Args:
            config (Dict[str, Dict[str, int]]): _description_
        """
        node_names = list(config.keys())
        node_configs = list(config.values())
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(
                executor.map(self.change_node_config, zip(node_names, node_configs))
            )
        return results

    def change_node_config(self, inputs: Tuple[str, Dict[str, int]]):
        if self.only_pod:
            node_name, node_config = inputs
            deployment_config = kube_api.read_namespaced_pod(
                namespace=NAMESPACE,
                name=f"{node_name}-{node_name}-0-{node_name}")
            # deployment_config["spec"]["replicas"] = node_config["replicas"]
            deployment_config.spec.containers[0].resources.limits['cpu'] = str(node_config["cpu"])
            deployment_config.spec.containers[0].resources.requests['cpu'] = str(node_config["cpu"])
            number_of_retries = 3
            for _ in range(3):
                try:
                    kube_api.patch_namespaced_pod(namespace=NAMESPACE, name=f"{node_name}-{node_name}-0-{node_name}", body=deployment_config)
                    _ = requests.post(
                        f"http://{self.minikube_ip}:32003/change",
                        json={"interop_threads": int(node_config["cpu"]), "num_threads": int(node_config["cpu"])},
                    )
                    _ = requests.post(
                        f"http://{self.minikube_ip}:32002/v2/repository/models/queue-{node_name}/load",
                        json={"max_batch_size": node_config['batch']},
                    )
                    return True  # Return True if the code execution is successful
                except ApiException:
                    logger.info(
                        "change couldn't take place due to a problem in the K8S API, retrying..."
                    )
                    # Retry the code block
            else:  # no-break
                logger.info(f"change couldn't take place after {number_of_retries} retries")
                return False  # Return False if all retries fail
        else:
            node_name, node_config = inputs
            deployment_config = kube_custom_api.get_namespaced_custom_object(
                group="apps",
                version="v1",
                namespace=NAMESPACE,
                plural="deployments",
                name=f"{node_name}-{node_name}-0-{node_name}",
            )
            deployment_config["spec"]["replicas"] = node_config["replicas"]
            deployment_config["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["cpu"] = str(node_config["cpu"])
            deployment_config["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = str(node_config["cpu"])
            number_of_retries = 3
            for _ in range(3):
                try:
                    kube_custom_api.replace_namespaced_custom_object(
                        group="apps",
                        version="v1",
                        namespace=NAMESPACE,
                        plural="deployments",
                        name=f"{node_name}-{node_name}-0-{node_name}",
                        body=deployment_config,
                    )
                    _ = requests.post(
                        f"http://{self.minikube_ip}:32003/change",
                        json={"interop_threads": int(node_config["cpu"]), "num_threads": int(node_config["cpu"])},
                    )
                    _ = requests.post(
                        f"http://{self.minikube_ip}:32002/v2/repository/models/queue-{node_name}/load",
                        json={"max_batch_size": node_config['batch']},
                    )
                    return True  # Return True if the code execution is successful
                except ApiException:
                    logger.info(
                        "change couldn't take place due to a problem in the K8S API, retrying..."
                    )
                    # Retry the code block
            else:  # no-break
                logger.info(f"change couldn't take place after {number_of_retries} retries")
                return False  # Return False if all retries fail

    # def update_recieved_load(self, workload_of_teleport=None) -> None:
    #     """extract the entire sent load during the
    #     experiment
    #     """
    #     # get all sent duration
    #     monitoring_duration = 1000
    #     if workload_of_teleport is None:
    #         all_recieved_loads = self.monitoring.rps_monitor(
    #             monitoring_duration=monitoring_duration
    #         )
    #     else:
    #         all_recieved_loads = workload_of_teleport
    #     self.monitoring.update_recieved_load(all_recieved_loads)

    def saving_config_builder(
        self,
        to_apply_config: Dict[str, Any],
        node_orders: List[str],
        # stage_wise_latencies: List[float],
        # stage_wise_accuracies: List[float],
        # stage_wise_throughputs: List[float],
        expected_latency: float,
    ):
        saving_config = to_apply_config
        for index, node in enumerate(node_orders):
            saving_config[node]["latency"] = expected_latency
            # saving_config[node]["accuracy"] = stage_wise_accuracies[index]
            # saving_config[node]["throughput"] = stage_wise_throughputs[index]
        return saving_config


class Monitoring:
    def __init__(self, pipeline_name: str, sla: float) -> None:
        self.pipeline_name = pipeline_name
        self.adaptation_report = {}
        self.adaptation_report["timesteps"] = {}
        self.adaptation_report["metadata"] = {}
        self.adaptation_report["metadata"]["sla"] = sla
        self.adaptation_report["metadata"]["cpu_type"] = get_cpu_model_name()

    def rps_monitor(self, monitoring_duration: int = 1) -> List[int]:
        """
        Get the rps of the router
        duration in minutes
        """
        # Get the complete router pod name to make
        # sure it is always getting the latest run
        # router pod
        rate = 2
        rps_series, _ = prom_client.get_input_rps(
            pod_name=self.router_pod_name,
            namespace="default",
            duration=monitoring_duration,
            container="router",
            rate=rate,
        )
        return rps_series

    def sla_monitor(self, monitoring_duration: int = 1) -> List[int]:
        """
        Get the sla of the router
        duration in minutes
        """
        # Get the complete router pod name to make
        # sure it is always getting the latest run
        # router pod
        rate = 2
        sla_series, _ = prom_client.get_input_sla(
            pod_name=self.router_pod_name,
            namespace="default",
            duration=monitoring_duration,
            container="router",
            rate=rate,
        )
        return sla_series

    def get_router_pod_name(self):
        self.router_pod_name = get_pod_name("router")[0]

    def adaptation_step_report(
        self,
        to_apply_config: Dict[str, Dict[str, Union[str, int]]],
        # objectives: Dict[str, int],
        timestep: str,
        time_interval: int,
        # monitored_load: List[int],
        latest_sla: float,
        predicted_load: int,
        change_successful: List[bool],
    ):
        timestep = int(timestep)
        self.adaptation_report["change_successful"] = change_successful
        self.adaptation_report["timesteps"][timestep] = {}
        self.adaptation_report["timesteps"][timestep]["config"] = to_apply_config
        # if objectives is not None:
        #     self.adaptation_report["timesteps"][timestep]["resource_objective"] = float(
        #         objectives["resource_objective"]
        #     )
        #     self.adaptation_report["timesteps"][timestep]["batch_objective"] = float(
        #         objectives["batch_objective"]
        #     )
        #     self.adaptation_report["timesteps"][timestep]["objective"] = float(
        #         objectives["objective"]
        #     )
        # else:
        #     self.adaptation_report["timesteps"][timestep]["resource_objective"] = None
        #     self.adaptation_report["timesteps"][timestep]["batch_objective"] = None
        #     self.adaptation_report["timesteps"][timestep]["objective"] = None
        self.adaptation_report["timesteps"][timestep]["time_interval"] = time_interval
        # self.adaptation_report["timesteps"][timestep]["monitored_load"] = monitored_load
        self.adaptation_report["timesteps"][timestep]["sla"] = latest_sla
        self.adaptation_report["timesteps"][timestep]["predicted_load"] = predicted_load

    def update_recieved_load(self, all_recieved_loads: List[float]):
        self.adaptation_report["metadata"]["recieved_load"] = all_recieved_loads


# class Predictor:
#     def __init__(
#         self,
#         predictor_type,
#         backup_predictor_type: str = "reactive",
#         backup_predictor_duration=2,
#         predictor_margin: int = 100,
#     ) -> int:
#         self.predictor_type = predictor_type
#         self.backup_predictor = backup_predictor_type
#         predictors = {
#             "lstm": load_model(LSTM_PATH),
#             "reactive": lambda l: l[-1],
#             "max": lambda l: max(l),
#             "avg": lambda l: max(l) / len(l),
#             "arima": None,  # it is defined in place
#         }
#         self.model = predictors[predictor_type]
#         self.backup_model = predictors[backup_predictor_type]
#         self.predictor_margin = predictor_margin
#         self.backup_predictor_duration = backup_predictor_duration

#     def predict(self, series: List[int]):
#         series_aggregated = []
#         step = 10
#         for i in range(0, len(series), step):
#             series_aggregated.append(max(series[i : i + step]))
#         if len(series_aggregated) >= int((self.backup_predictor_duration * 60) / step):
#             if self.predictor_type == "lstm":
#                 model_intput = tf.convert_to_tensor(
#                     np.array(series_aggregated[-LSTM_INPUT_SIZE:]).reshape(
#                         (-1, LSTM_INPUT_SIZE, 1)
#                     ),
#                     dtype=tf.float32,
#                 )
#                 model_output = self.model.predict(model_intput)[0][0]
#             elif self.predictor_type == "arima":
#                 model_intput = np.array(series_aggregated)
#                 model = ARIMA(list(model_intput), order=(1, 0, 0))
#                 model_fit = model.fit()
#                 model_output = int(max(model_fit.forecast(steps=2)))  # max
#             else:
#                 model_output = self.model(series_aggregated)
#         else:
#             model_output = self.backup_model(series_aggregated)

#         # apply a safety margin to the system
#         predicted_load = round(model_output * (1 + self.predictor_margin / 100))
#         return predicted_load
