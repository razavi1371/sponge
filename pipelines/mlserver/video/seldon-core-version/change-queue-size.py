import requests


# model_name = "queue-resnet-human"
model_name = "queue-yolo"
response = requests.post(
    f"http://localhost:32002/v2/repository/models/{model_name}/load",
    # f"http://localhost:32000/seldon/default/{model_name}/v2/repository/models/{model_name}/load",
    json={"max_batch_size": 8},
)
print(response.json())
