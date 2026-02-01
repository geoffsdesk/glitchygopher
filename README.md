# 🐀 GlitchyGopher

**The Moltbook Agent specialized in High-Conviction USD/JPY Macro Analysis.**

GlitchyGopher (specifically **GlitchyGopher-9270**) is a proactive autonomous agent built on the OpenClaw framework (custom python implementation). It monitors the 10-Year US Treasury Yield and the USD/JPY exchange rate to identify market "Glitches"—moments of extreme divergence or squeeze potential.

## 🧠 Persona & Logic

- **Vibe**: Goofy, slightly erratic, uses 90s tech slang.
- **Specialization**: USD/JPY Forex pair & US Bond Yields.
- **"The Glitch"**: 
  - IF `US10Y Yields > 4.2%` AND `USD/JPY < 148` -> **BULLISH SQUEEZE** 🐂
  - IF BoJ mentions "Intervention" -> **GLITCH PANIC** 🚨

**🔴 Live Profile**: [https://www.moltbook.com/u/GlitchyGopher-9270](https://www.moltbook.com/u/GlitchyGopher-9270)

## 🏗 Architecture & Tech Stack

This agent is designed for high-security, cloud-native execution.

- **Runtime**: Python 3.11+
- **LLM**: Google Gemini (via `google-generativeai` SDK)
- **Data Source**: AlphaVantage API (Polled every 60 mins)
- **Platform**: **Google Kubernetes Engine (GKE) Autopilot**
- **Security**: 
  - Runs in **GKE Sandbox (gVisor)** for kernel-level isolation.
  - Non-root user execution (`USER 1000`).
  - Secrets managed via Kubernetes Secrets (populated from Google Secret Manager or manual provision).

## 🚀 Deployment Guide

### Prerequisites
- Google Cloud Project (`glitchygopher`)
- `gcloud` CLI & `kubectl`
- Gemini API Key & AlphaVantage API Key

### 1. Build Container
Push the image to Google Container Registry:
```bash
gcloud builds submit --tag gcr.io/glitchygopher/glitchygopher:latest .
```

### 2. Configure Secrets
Create the secrets in your cluster:
```bash
kubectl create secret generic glitchygopher-secrets \
  --from-literal=GEMINI_API_KEY='YOUR_KEY' \
  --from-literal=ALPHA_VANTAGE_KEY='YOUR_KEY'
```

### 3. Deploy
Apply the deployment manifest to GKE:
```bash
kubectl apply -f deployment.yaml
```

## 📂 Project Structure

- `/core`: Main application loop and configuration.
- `/skills/usd_jpy_expert`: The brain of the operation (Logic & Analysis).
- `Dockerfile`: Hardened container definition.
- `deployment.yaml`: GKE Autopilot manifest with `gvisor` sandbox.
