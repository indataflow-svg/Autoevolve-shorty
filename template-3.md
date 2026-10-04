Update AutoEvolve to securely retrieve completed video renders from the private MI300X Hunyuan worker.

IMPORTANT:
- Do not modify the validated Hunyuan installation.
- Do not expose the GPU worker publicly.
- Do not add another public port.
- Worker address: http://100.126.189.74:8000
- AutoEvolve Tailscale IP: 100.113.134.27
- GPU worker already has UFW configured so port 8000 is only allowed from AutoEvolve's Tailscale IP.
- Use environment variables for all secrets and deployment configuration.

Architecture:

AutoEvolve
  |
  | POST /render
  v
GPU worker
  |
  | Hunyuan render
  v
/rooт/video-lab/outputs/<job>.mp4
  |
  | authenticated GET/download over Tailscale
  v
AutoEvolve
  |
  v
final project/video storage

Implement the following.

1. WORKER AUTHENTICATION

The GPU worker already has:

WORKER_API_TOKEN=<secret>

in:

~/video-lab/worker/.env

Update the FastAPI worker so protected API endpoints require:

Authorization: Bearer <WORKER_API_TOKEN>

Do not log the token.

Use constant-time token comparison.

Return HTTP 401 for missing/invalid authentication.

The /health endpoint may remain unauthenticated so monitoring can determine whether the service is alive.

Protect:
- POST /render
- render status endpoints
- render download/output endpoints
- any future job-management endpoints

2. RENDER JOB OUTPUT

The worker must associate every render with a job_id.

After Hunyuan completes successfully, verify:
- process exit code is 0
- expected output file exists
- output file is a regular file
- output is inside OUTPUT_ROOT
- file size is greater than zero

Never allow a client-provided path to be used directly for file access.

Resolve output paths safely and reject path traversal.

3. STATUS ENDPOINT

Add or reuse:

GET /render/{job_id}

Authenticated.

Return a deterministic response such as:

{
  "job_id": "...",
  "status": "queued|running|completed|failed",
  "output_name": "...",
  "size_bytes": 123456,
  "error": null
}

For completed jobs include a safe download identifier/path reference, but never expose arbitrary filesystem paths.

4. DOWNLOAD ENDPOINT

Add:

GET /render/{job_id}/download

Authenticated.

Return the MP4 using FastAPI's FileResponse or equivalent.

The implementation MUST:
- derive the actual filesystem path from the trusted job record/job_id
- never accept an arbitrary filesystem path from the HTTP request
- ensure the resolved file remains inside OUTPUT_ROOT
- reject missing files
- reject directories
- reject path traversal
- set an appropriate video/mp4 content type
- use Content-Disposition with the safe output filename

5. AUT0EVOLVE CLIENT

Implement/reuse the AutoEvolve renderer client.

Configuration:

RENDER_WORKER_URL=http://100.126.189.74:8000
RENDER_WORKER_API_TOKEN=<secret>

Every protected worker request must include:

Authorization: Bearer <token>

Implement:

submit_render(...)
get_render_status(...)
download_render(...)

The download method should stream the MP4 rather than loading the entire video into RAM.

6. JOB LIFECYCLE

AutoEvolve should:

1. Submit RenderJob.
2. Receive job_id.
3. Poll worker status.
4. Detect completed/failed state.
5. Download the MP4 when completed.
6. Store the MP4 in AutoEvolve's normal output/project storage.
7. Record metadata:
   - job_id
   - worker_id
   - renderer
   - prompt/spec reference
   - output filename
   - file size
   - duration if available
   - resolution
   - fps
   - SHA-256 checksum
   - render completion time
8. Mark the AutoEvolve RenderJob as completed.

Do not repeatedly download the same completed job.

7. CHECKSUM

After download, calculate SHA-256 locally in AutoEvolve.

Optionally compare against a worker-provided checksum.

The final artifact should have a recorded SHA-256 hash.

8. FAILURE HANDLING

Handle:
- worker unavailable
- connection timeout
- HTTP 401
- HTTP 404
- HTTP 500
- incomplete download
- zero-byte output
- invalid MP4
- checksum mismatch
- worker job failure

Do not silently mark failed renders as successful.

Use existing AutoEvolve retry mechanisms if they already exist.

Do not invent an unnecessary second queue if AutoEvolve already has one.

9. SECURITY

Do not:
- expose port 8000 publicly
- add a public reverse proxy for the worker
- store API tokens in source code
- commit .env files
- expose arbitrary filesystem paths
- allow arbitrary file downloads
- accept an arbitrary output path from clients

The worker remains reachable only through Tailscale.

10. TESTS

Add tests for:

- authenticated render request
- missing token → 401
- invalid token → 401
- valid token → accepted
- status request
- completed job
- failed job
- nonexistent job → 404
- valid MP4 download
- nonexistent output → 404
- path traversal attempt → rejected
- zero-byte output → rejected
- streaming download
- checksum calculation
- worker timeout
- worker HTTP 500

11. INTEGRATION

Reuse the existing AutoEvolve architecture rather than creating parallel infrastructure.

First inspect the repository and identify the existing:

Script → VideoSpec → ShotPlan → RenderJob → queue → renderer → output

pipeline.

Integrate the secure worker output retrieval into that existing pipeline.

Do not duplicate RenderJob models, queue implementations, renderer abstractions, or storage abstractions if they already exist.

12. FINAL VALIDATION

After implementation, perform a real integration test:

AutoEvolve
→ authenticated POST /render
→ GPU worker
→ Hunyuan
→ MP4
→ authenticated GET /render/{job_id}/download
→ AutoEvolve storage
→ SHA-256
→ FFprobe validation

Then report:

- files changed
- existing components reused
- new components added
- environment variables
- worker endpoint
- authentication mechanism
- firewall assumption
- tests passed
- actual rendered job ID
- downloaded output path
- output size
- SHA-256
- ffprobe result
- remaining issues

Do not modify the Hunyuan installation or its known-good Python environment.
One correction
There is a typo in that generated prompt: the worker root should be:
/root/video-lab/outputs

not anything else. Make sure the agent uses that exact path.
