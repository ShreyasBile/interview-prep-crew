# One-time setup for running the crew offline with Ollama.
# Pulls qwen3:4b-instruct (tool calling, no thinking step) and creates interview-prep-qwen3
# with an 8K context window.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
ollama pull qwen3:4b-instruct
ollama create interview-prep-qwen3 -f ollama/Modelfile
Write-Host "Done. Set MODEL=ollama/interview-prep-qwen3 in .env"
