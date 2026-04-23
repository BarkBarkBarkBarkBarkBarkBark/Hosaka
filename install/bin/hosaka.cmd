@echo off
rem Thin shim that forwards to the PowerShell launcher so `hosaka` works
rem identically from cmd.exe, PowerShell, and Windows Terminal.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0hosaka.ps1" %*
