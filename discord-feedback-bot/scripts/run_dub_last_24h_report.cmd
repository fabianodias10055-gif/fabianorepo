@echo off
cd /d "%~dp0.."
py scripts\dub_daily_report.py --window last-24h
