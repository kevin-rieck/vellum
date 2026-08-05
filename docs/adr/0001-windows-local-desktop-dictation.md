# Windows-first local desktop dictation

Vellum v1 is a Windows user-level tray application because its first user and target workstation are Windows. It requires an NVIDIA CUDA-capable GPU and performs capture, VAD, transcription, vocabulary hinting, and insertion locally; audio and transcripts are never sent to a remote service, and the local GPU provides practical low-latency transcription. A model may be explicitly downloaded during setup, but runtime dictation remains offline.
