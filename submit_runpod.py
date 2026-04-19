#!/usr/bin/env python3
"""Submit a test job to a RunPod serverless endpoint and poll for results."""
# python submit_runpod.py --input-file lora_input.json
# python submit_runpod.py --check <job-id>
# python submit_runpod.py --list-jobs

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import dotenv
dotenv.load_dotenv()

import requests

JOBS_FILE = Path(__file__).parent / ".runpod_jobs.json"

DEFAULT_INPUT = {
    "dataset_source": "gdrive://1i8rAZf2Uz89OvBMvaCEGUwbBVWlHLU10",
    "lora_name": "lora_name_here_to_test",
    "steps": 500,
    "resolution": [1024],
    "sample_prompts": [
        "person in a coffee shop",
        "portrait, studio lighting",
    ],
    "s3_prefix": "runpod/lora_training/test",
}


def submit_job(endpoint_id: str, api_key: str, job_input: dict) -> dict:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"input": job_input}

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def check_status(endpoint_id: str, api_key: str, job_id: str) -> dict:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_job(endpoint_id: str, api_key: str, job_id: str, interval: int = 15) -> dict:
    print(f"Polling job {job_id} every {interval}s ...")
    while True:
        result = check_status(endpoint_id, api_key, job_id)
        status = result.get("status")
        print(f"  [{time.strftime('%H:%M:%S')}] status={status}")

        if status in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"):
            return result

        time.sleep(interval)


def load_jobs() -> dict:
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text())
    return {}


def save_job(job_id: str, endpoint_id: str, label: str = "") -> None:
    jobs = load_jobs()
    jobs[job_id] = {
        "endpoint_id": endpoint_id,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
    }
    JOBS_FILE.write_text(json.dumps(jobs, indent=2))
    print(f"Job ID saved to {JOBS_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Submit a job to RunPod serverless endpoint")
    parser.add_argument("--endpoint-id", default=os.getenv("RUNPOD_ENDPOINT_ID"),
                        help="RunPod endpoint ID (or set RUNPOD_ENDPOINT_ID)")
    parser.add_argument("--api-key", default=os.getenv("RUNPOD_API_KEY"),
                        help="RunPod API key (or set RUNPOD_API_KEY)")
    parser.add_argument("--input-file", type=str, default=None,
                        help="Path to JSON file with job input (default: built-in test input)")
    parser.add_argument("--poll-interval", type=int, default=15,
                        help="Seconds between status checks (default: 15)")
    parser.add_argument("--no-poll", action="store_true",
                        help="Submit and save job ID, don't wait for completion")
    parser.add_argument("--check", metavar="JOB_ID", type=str, default=None,
                        help="Check status of a previously submitted job ID")
    parser.add_argument("--list-jobs", action="store_true",
                        help="List all saved job IDs and their saved metadata")
    parser.add_argument("--label", type=str, default="",
                        help="Optional label to attach to the saved job record")
    args = parser.parse_args()

    # --- list saved jobs ---
    if args.list_jobs:
        jobs = load_jobs()
        if not jobs:
            print("No saved jobs.")
            return
        print(f"{'JOB ID':<30}  {'SUBMITTED':<20}  {'ENDPOINT':<25}  LABEL")
        print("-" * 90)
        for jid, meta in jobs.items():
            print(f"{jid:<30}  {meta.get('submitted_at',''):<20}  {meta.get('endpoint_id',''):<25}  {meta.get('label','')}")
        return

    # --- check a saved (or explicit) job ---
    if args.check:
        job_id = args.check
        api_key = args.api_key
        if not api_key:
            sys.exit("Error: --api-key or RUNPOD_API_KEY is required")

        endpoint_id = args.endpoint_id
        if not endpoint_id:
            jobs = load_jobs()
            meta = jobs.get(job_id)
            if meta:
                endpoint_id = meta["endpoint_id"]
            else:
                sys.exit("Error: --endpoint-id is required (job not found in saved jobs)")

        result = check_status(endpoint_id, api_key, job_id)
        print(json.dumps(result, indent=2))
        return

    # --- submit a new job ---
    if not args.endpoint_id:
        sys.exit("Error: --endpoint-id or RUNPOD_ENDPOINT_ID is required")
    if not args.api_key:
        sys.exit("Error: --api-key or RUNPOD_API_KEY is required")

    if args.input_file:
        with open(args.input_file) as f:
            data = json.load(f)
        job_input = data.get("input", data)
    else:
        job_input = DEFAULT_INPUT

    print("Submitting job ...")
    print(json.dumps(job_input, indent=2))

    result = submit_job(args.endpoint_id, args.api_key, job_input)
    job_id = result["id"]
    print(f"Job submitted: {job_id}")
    save_job(job_id, args.endpoint_id, args.label)

    if args.no_poll:
        print(f"Run `python {os.path.basename(__file__)} --check {job_id}` to check status later.")
        return

    result = poll_job(args.endpoint_id, args.api_key, job_id, args.poll_interval)
    print("\n--- Result ---")
    print(json.dumps(result, indent=2))

    if result.get("status") != "COMPLETED":
        sys.exit(1)


if __name__ == "__main__":
    main()
