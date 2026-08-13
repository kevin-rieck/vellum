# Vellum

Vellum is a private desktop dictation product that turns a user's spoken input into text for the currently focused application.

## Language

**Vellum**:
The Windows-first local desktop dictation product described by this context.
_Avoid_: Voice agent, local dictation app


**Dictation session**:
A user-initiated period of spoken input that produces one piece of text for insertion into the focused application. V1 permits only one active session, has no manual cancellation while it is transcribing, and captures at most 60 seconds of audio.
_Avoid_: Recording, transcription

**Push-to-talk**:
An activation mode in which holding the configured hotkey defines the duration of a Dictation session; releasing it ends the session.
_Avoid_: Toggle, hands-free dictation

**Text insertion**:
The automatic placement of a completed Dictation session's text into the currently focused application by copying it to the system clipboard and sending Ctrl+V. Its text remains in the system clipboard after insertion. If the target is elevated and cannot accept the paste, insertion fails with a notification while the text remains available in the clipboard.
_Avoid_: Typing, output

**Local-only processing**:
The privacy boundary under which Dictation session audio, transcripts, and derived text never leave the user's device; the product makes no telemetry or cloud-inference requests.
_Avoid_: Private mode, offline-capable

**Transcription engine**:
A replaceable local component that converts Dictation session audio into a transcript. V1 uses faster-whisper with the `large-v3-turbo` model, warms asynchronously at Tray application startup, and remains resident while it runs.
_Avoid_: Whisper, model

**Transcript**:
The English text produced directly by the Transcription engine for a Dictation session. V1 inserts it without LLM-based meaning, grammar, punctuation cleanup, or interpretation of spoken commands.
_Avoid_: Cleaned text, prompt output

**Silence trimming**:
The removal of leading and trailing non-speech audio from a completed Dictation session. It never ends a Push-to-talk session before its hotkey is released.
_Avoid_: Automatic stop, hands-free endpointing

**Activation hotkey**:
The configurable system-wide key combination held for Push-to-talk. Its v1 default is Ctrl+Alt+Space.
_Avoid_: Shortcut, trigger key

**Insertion target**:
The foreground application associated with a Dictation session when microphone capture ends, either at Push-to-talk hotkey release or at the 60-second duration limit. Text insertion is cancelled if that application no longer has focus when the Transcript is ready.
_Avoid_: Current focus, destination

**Session feedback**:
The user-visible state of a Dictation session. V1 indicates idle, recording, and transcribing through the system-tray icon, makes brief sounds at capture start and end, and uses Windows notifications only for errors or cancelled Text insertion.
_Avoid_: Progress UI, status display

**No-speech result**:
A completed Dictation session with no usable detected speech or no usable Transcript. It produces no Text insertion, preserves the existing clipboard, and notifies the user.
_Avoid_: Empty transcript, successful blank output

**Tray application**:
The user-level background application that owns the Activation hotkey and Dictation session lifecycle. It may start automatically at Windows sign-in and can be quit from its system-tray menu.
_Avoid_: Service, daemon

**Settings**:
The native configuration window for microphone selection, Activation hotkey, start-at-sign-in, sounds, and Transcription engine model selection. Its choices persist in a user-owned configuration file.
_Avoid_: Config-only setup, preferences file

**Input device**:
The microphone selected in Settings for Dictation sessions. V1 uses the Windows default input initially, but does not silently switch away from a user-selected device if it becomes unavailable.
_Avoid_: Audio source, default mic

**Ephemeral processing**:
The retention policy under which Dictation session audio exists only in memory until transcription completes and the application stores no Transcript history. The system clipboard is the sole intentional short-term retention channel.
_Avoid_: Recording history, transcript archive

**Vocabulary hints**:
A Settings-managed list of technical terms supplied to the Transcription engine to improve recognition. V1 seeds the list with common engineering terminology and does not apply post-transcription replacement rules.
_Avoid_: Autocorrect, replacement dictionary
