#!/bin/bash
sudo dos2unix main.py
pip install -r requirements.txt --upgrade
export GPT_ENGINE=text-davinci-003
python3 main.py
