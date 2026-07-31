@echo off
set TR_DEV_LICENSE=1
pip install -r requirements.txt
py -3.11 app.py
