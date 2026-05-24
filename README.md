# Helios — Aegis v1

**Aegis** is a Linux-resident AI symbiote. v1 is a minimal end-to-end loop: text in → NCP brain → Gemini renderer → text out, with SQLite episodic memory and a 6-scalar neuromodulator bus.

Runs as a systemd daemon on Helios1 (16 GB no-GPU GCP VM). Communicates over a unix socket. Connect with `aegis-cli`.

## Architecture

- **Nexus** — pub/sub message bus + clock + neuromodulator state
- **Hive** — sensory encoders (text via MiniLM in v1)
- **Brain** — ~200k-param Liquid Neural Network (CfC + AutoNCP)
- **Mnemosyne** — SQLite episode store + top-k cosine retrieval
- **Renderer** — Gemini API → template fallback chain

## Status

v1 live (2026-05-23). v1.1 polish in progress.

Full docs in the project's Notion workspace.

## Install (Helios1)
cd /opt/aegis

uv venv

uv pip install -e .

sudo cp systemd/aegis.service /etc/systemd/system/

sudo systemctl enable --now aegis

Then `aegis-cli` to talk to it.

## License

All rights reserved (for now).
