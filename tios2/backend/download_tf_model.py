import urllib.request
import tarfile
import os

MODEL_NAME = 'ssd_mobilenet_v2_coco_2018_03_29'
MODEL_URL = f'http://download.tensorflow.org/models/object_detection/{MODEL_NAME}.tar.gz'

print(f"Downloading {MODEL_URL}...")
urllib.request.urlretrieve(MODEL_URL, 'model.tar.gz')

print("Extracting model...")
with tarfile.open('model.tar.gz', 'r:gz') as tar:
    tar.extractall()

print("Model downloaded and extracted.")
os.remove('model.tar.gz')
