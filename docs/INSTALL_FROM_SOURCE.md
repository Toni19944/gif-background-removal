# Install from source (Windows)

This guide runs the app from source using Python.

## Requirements

- Windows 10/11
- Python 3.13 recommended
- Git (optional)

## 1) Get the code

### Option A: Clone with Git

```bash
git clone https://github.com/toni19944/gif-background-removal.git
cd gif-background-removal
```
### Option B: Download ZIP

Download the repo ZIP from GitHub, extract it, and open a terminal in the extracted folder.

## 2) Create and activate a virtual environment (PowerShell)

Open PowerShell in the project folder and run:
```
py -3.13 -m venv .venv  
.\.venv\Scripts\activate  
python -m pip install -U pip setuptools wheel  
```
## 3) Install dependencies

CPU-only (recommended)  
```
pip install -r requirements-cpu.txt
```  
GPU (NVIDIA) from source  
```
pip install -r requirements-gpu.txt
```
GPU notes:

You still need a compatible NVIDIA driver installed.

CUDA Toolkit is usually not required if you use requirements-gpu.txt (it installs NVIDIA runtime wheels), but drivers are required.

## 4) Run the app
```
python app.py
```
## 5) Updating later  
```
git pull  
pip install -r requirements-cpu.txt --upgrade
```

(Use requirements-gpu.txt instead if you installed GPU dependencies.)

## Logs and outputs

- The app writes a log next to your output file, e.g. output.gif.log  
- It also creates a work folder next to your output file, e.g. output.gif.work\ 
  - frames, transparent frames, masks, previews, and manifest.json

## Troubleshooting  
## “py” not found  

Install Python 3.13 and ensure the Windows Python launcher is installed. Then retry the commands.  

## App starts but GPU falls back to CPU  

Check the .log file created next to your output GIF. It will show available providers and which provider the app used.
