# Frontend Product Contract & UI Architecture

## Overview & Product Philosophy

The **VANI RAG** frontend is a high-performance, single-page application built on React 18, Vite, TypeScript, and Tailwind CSS. It is hosted at **`https://vani-rag.susdev.in`** with direct secure WebSocket/HTTPS connectivity to the **Azure Central India backend**.

The interface combines a visually rich 3D WebGL background wave simulation with an ultra-responsive, privacy-preserving **Chat Timeline** interface that caches all conversation state locally in the user's browser without database persistence.

---

## 🎨 Layout & Interaction Design

```
+---------------------------------------------------------------------------------------------------+
|                                 [ Voice Workspace | System Evidence ]                             |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ Sticky Top Header ]:  ✨ Active Conversation (N turns cached in browser)   [ New Conversation ]|
|                                                                                                   |
|                                                                     ┌───────────────────────────┐ |
|                                                                     │ 🗣️ USER QUESTION (Right)   │ |
|                                                                     │ "What is net gain and loss" │ |
|                                                                     │ 12:45:10 · [English] · 🎤 │ |
|                                                                     └───────────────────────────┘ |
|                                                                                                   |
| ┌─────────────────────────────────────────────────────────────┐                                   |
| │ 🟣 (Mini 3D Uiverse Orb) VANI RAG · Grounded Evidence       │                                   |
| │ ┌─────────────────────────────┐ ┌─────────────────────────┐ │                                   |
| │ │ 📄 Evidence Answer          │ │ 🧠 Groq Synthesis       │ │                                   |
| │ │ - Exact verbatim passage    │ │ - Structured claims     │ │                                   |
| │ │ - Up to 2 citations         │ │ - Up to 2 citations     │ │                                   |
| │ └─────────────────────────────┘ └─────────────────────────┘ │                                   |
| │ ┌─────────────────────────────────────────────────────────┐ │                                   |
| │ │ ⏱️ 8-Stage End-to-End Latency Breakdown Table (10.4ms)   │ │                                   |
| │ └─────────────────────────────────────────────────────────┘ │                                   |
| └─────────────────────────────────────────────────────────────┘                                   |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
|  [ Sticky Bottom Dock ]:  [Voice Mode]  [Questions Bank]  (🔴 Speak)  [Language: Auto/HI/EN]      |
|  [ Multilingual Quick Pills ]: [English Pill]  [हिंदी Pill]  [Hinglish Pill]                      |
+---------------------------------------------------------------------------------------------------+
```

---

## Key UI Components & Behavioral Specifications

### 1. In-Browser Cached Chat Timeline (`ChatTimeline.tsx`)
* **Dynamic Hero-to-Chat Transition**: Starts with a centered large pulsating Voice Orb. Upon submitting the first query, it seamlessly transitions into the continuous scrollable conversation stream.
* **Zero Database Retention**: All conversation turns (`ChatTurn[]`) are cached strictly in browser `sessionStorage` under `vani-rag.chat-session.v1`.
* **Sticky Header Row**: Pinned at `sticky top-16 z-30` with `backdrop-blur-2xl bg-[#070b14]/85`, housing the turn counter and **"New Conversation"** reset button.

### 2. User Question Bubbles (`ChatUserMessage.tsx`)
* **Right-Aligned**: Positioned on the right side of the screen (`justify-end`).
* Contains the user avatar, timestamp, language badge (`English`, `हिंदी`, `Hinglish`), source tag (`Voice` / `Text`), and transcript text.

### 3. System Response Stream (`ChatAssistantMessage.tsx`)
* **Left-Aligned**: Positioned on the left side of the screen (`justify-start`, `items-start`, `text-left`).
* **3D Animated Uiverse Mini-Orb**: Placed on the top-left above the response, featuring multi-color rotating inset shadows and live state indicators:
  * 🎙️ *"Listening to speech…"*
  * ⚙️ *"Searching verified index & synthesizing…"*
  * ✅ *"Grounded Multilingual Evidence"*
* **Dual-Column Output**:
  1. **Primary Extractive Evidence Card**: Verbatim passage text, exact character spans, parent doc IDs, and at most 2 citations.
  2. **Groq Grounded Synthesis Card**: Asynchronously resolved claims with verbatim quote attribution and at most 2 citations.
  3. **8-Stage Vertical Latency Breakdown Table**: Nanosecond-precision metrics from `01 Client Transport` to `08 Provenance & Grounding`.

### 4. Sticky Floating Action Dock (`VoicePillControls.tsx`)
* Pinned at the bottom of the viewport (`fixed bottom-4 left-0 right-0 z-40`).
* Houses the floating mic trigger, language hint selector (`Auto`, `Hindi`, `Hinglish`, `English`), Questions gallery modal trigger, and 3 canonical sample question pills.

### 5. Multilingual Verified Question Bank
* Provides 18 pre-validated prompts across English, Hindi, and Hinglish.
* Includes both clean search queries and natural conversational queries with mild background noise to test noise-robustness.

---

## Truthful Data Mapping

| UI Component | Data Source | Contract & Behavioral Rule |
| :--- | :--- | :--- |
| **System Readiness** | `GET /ready` | Displays exact component readiness checks. Never shows false green badges. |
| **Realtime Transcript**| `WS /v1/query/voice` (`stt_partial`) | Stable partial transcripts launch speculative search; final transcript authorises response. |
| **Grounded Citations** | `payload.citations` | Exact character span offsets into source passage with SHA-256 parent doc IDs. Max 2 citations. |
| **Groq Synthesis** | `POST /v1/query/synthesis` | Opaque short-lived token redeemed asynchronously. Post-primary only. Max 2 citations. |
| **Latency Table** | `payload.timings_ms` | 8-stage breakdown with exact microsecond duration per stage. |
| **Evidence Summary** | `GET /v1/evidence/summary` | Cryptographically hashed benchmark results and 13/13 guardrail evaluation report. |
