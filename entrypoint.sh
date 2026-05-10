#!/bin/bash
if [ "$SERVICE" = "ui" ]; then
    exec chainlit run app/ui.py --host 0.0.0.0 --port 8001
elif [ "$SERVICE" = "ingestor" ]; then
    exec python ingest_pipeline.py
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi