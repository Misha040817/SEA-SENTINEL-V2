SEA SENTINEL V2 ONE-CLICK LAUNCHER (Windows PowerShell)

1. Extract all files into C:\Users\User\Sea-Sentinel-V2 (same folder as dashboard .py).
2. Run once in PowerShell (from the project folder):
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\SETUP_AIS_KEY.ps1
   Enter your NEW AISStream key at the hidden prompt.
3. Each time you want to start:
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\START_SEA_SENTINEL.ps1
4. To stop:
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\STOP_SEA_SENTINEL.ps1

If port 8574 is occupied, stop the old Streamlit process before starting.
If the receiver stops immediately, run it directly in PowerShell to see its error.
The key is encrypted with Windows DPAPI and is only decryptable by the same Windows user on the same computer.
Do not commit .aisstream_key.dpapi or .sea_sentinel_launcher_pids.json to GitHub.
This launcher has not been tested on your Windows PC.
