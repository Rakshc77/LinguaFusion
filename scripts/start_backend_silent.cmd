@echo off
cd /d "W:\OfflineSpeechTranslator_dev_v1.0"
set PATH=W:\OfflineSpeechTranslator_dev_v1.0\.venv\Lib\site-packages\nvidia\cublas\bin;W:\OfflineSpeechTranslator_dev_v1.0\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;W:\OfflineSpeechTranslator_dev_v1.0\.venv\Lib\site-packages\torch\lib;%PATH%
set PYTHONPATH=W:\OfflineSpeechTranslator_dev_v1.0
set LF_WHISPER_MODEL=medium
set LF_WHISPER_DEVICE=cuda
set NLLB_DEVICE=cuda
set NLLB_COMPUTE_TYPE=int8
"W:\OfflineSpeechTranslator_dev_v1.0\.venv\Scripts\python.exe" -m uvicorn backend.server:app --host 0.0.0.0 --port 8000
