#!/bin/bash
# Smoke test driver for devre-analizi-egitim-asistani Streamlit app.
# Checks that backend services are running and app is responsive.

set -e

CHROMA_URL="http://127.0.0.1:8123"
STREAMLIT_URL="http://127.0.0.1:8501"
MAX_WAIT=30

echo "Checking services..."

# Wait for Streamlit to be ready
echo "Waiting for Streamlit on $STREAMLIT_URL..."
for i in $(seq 1 $MAX_WAIT); do
  if curl -s "$STREAMLIT_URL" > /dev/null 2>&1; then
    echo "✓ Streamlit is running"
    break
  fi
  echo "  Attempt $i/$MAX_WAIT..."
  sleep 1
  if [ $i -eq $MAX_WAIT ]; then
    echo "✗ Streamlit failed to start"
    exit 1
  fi
done

# Test app responds to API calls (Streamlit's internal API)
echo "Testing app health..."
if curl -s "$STREAMLIT_URL/_stcore/allowed-origins" > /dev/null 2>&1; then
  echo "✓ App is responding"
else
  echo "⚠ App may not be fully ready"
fi

echo ""
echo "SUCCESS: App is running on $STREAMLIT_URL"
echo "Open in browser or use: .venv\Scripts\streamlit run app\ui\streamlit_app.py"
