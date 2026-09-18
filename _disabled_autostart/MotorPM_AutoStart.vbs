' MotorPM - Silent auto-start (no window, no tray icon)
' Runs at Windows startup. Watchdog keeps server alive 24/7.

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "D:\AI\motor-pm"

shell.Run "C:\Users\qianjia\AppData\Local\Programs\Python\Python312\python.exe server_watchdog.py", 0, False
