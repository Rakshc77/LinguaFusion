Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "W:\OfflineSpeechTranslator_dev_v1.0"
WshShell.Run """W:\OfflineSpeechTranslator_dev_v1.0\.venv\Scripts\pythonw.exe"" ""W:\OfflineSpeechTranslator_dev_v1.0\desktop\main.py""", 0, False
