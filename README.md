# SOPSearch Vision

AI-powered field tool that analyzes photos of issues and generates
step-by-step repair checklists from your SOPs.

---

## Deploy to Render (free, public URL)

1. Create a free account at https://render.com
2. Click **New → Web Service**
3. Choose **Deploy from a Git repository**
   - Push these files to a GitHub repo first (see below)
   - Or use **Manual Deploy** and upload the files
4. Set the environment variable:
   - Key:   `ANTHROPIC_API_KEY`
   - Value: `sk-ant-...` (your key from console.anthropic.com)
5. Click **Deploy** — you'll get a URL like `https://sopsearch-vision.onrender.com`
6. Share that URL with anyone — works on any phone, anywhere

### Push to GitHub (required for Render)

In Terminal, from the folder containing these files:

```bash
git init
git add .
git commit -m "SOPSearch Vision"
git branch -M main
```

Then create a repo at github.com and follow their instructions to push.

---

## Run Locally

**Mac/Linux:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python3 server.py
```
Or just double-click START.sh — it will ask for your key.

**Windows:**
Double-click START.bat — it will ask for your key.

Then open: http://localhost:8765

**Share on local WiFi:**
Find your IP: `ipconfig getifaddr en0` (Mac) or `ipconfig` (Windows)
Send testers: `http://YOUR-IP:8765`

---

## Files

| File | Purpose |
|------|---------|
| `sopsearch-vision.html` | The app UI |
| `server.py` | Python web server + API proxy |
| `render.yaml` | Render deployment config |
| `requirements.txt` | Python dependencies (none) |
| `START.sh` | Mac/Linux launcher |
| `START.bat` | Windows launcher |
