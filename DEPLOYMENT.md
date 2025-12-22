# Deployment Guide: Google Cloud Run + Firestore

This assistant is designed to run serverlessly on Google Cloud Run, using Firestore for persistent storage.

## Prerequisites

1.  **Google Cloud Project**: Create one at [console.cloud.google.com](https://console.cloud.google.com).
2.  **Firestore**: Enable Firestore in **Native Mode**.
3.  **Gemini API Key**: Get one from AI Studio.
4.  **Google Cloud CLI**: Installed and authenticated (`gcloud auth login`).

## Local Development (with Firestore)

To run locally, you need to authenticate as your user so the app can access Firestore.

```bash
# 1. Login
gcloud auth application-default login

# 2. Set API Key
export GOOGLE_API_KEY="your_gemini_key"

# 3. Run Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## fast Deploy to Cloud Run

We can deploy the backend directly from source code.

```bash
# Deploy Backend
gcloud run deploy assistant-backend \
  --source ./backend \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="your_key_here"
```

Once deployed, copy the **Service URL** (e.g., `https://assistant-backend-xyz.a.run.app`).

## Frontend Deployment

## Frontend Deployment

Only the **Frontend** needs a special build step to embed the Backend URL.

### 1. Set your Backend URL
```bash
export BACKEND_URL="https://assistant-demo-1047514462039.us-west1.run.app"
```

### 2. Build the Image (using Cloud Build)
We use a `cloudbuild.yaml` because `gcloud builds submit` doesn't strictly support `--build-arg` on the command line.

```bash
gcloud builds submit ./frontend \
  --config ./frontend/cloudbuild.yaml \
  --substitutions=_BACKEND_URL=$BACKEND_URL
```

### 3. Deploy the Image
Now deploy the image we just built:

```bash
gcloud run deploy assistant-frontend \
  --image gcr.io/$(gcloud config get-value project)/assistant-frontend \
  --region us-west1 \
  --allow-unauthenticated
```

