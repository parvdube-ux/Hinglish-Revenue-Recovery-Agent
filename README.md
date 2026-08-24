# Razorpay AI Buildathon — Track 3 (AI Revenue Recovery)
## Hinglish Checkout Recovery Agent

Built by Parv Dube for the Razorpay AI Buildathon 2026 — Track 3.

This repository contains the codebase for the **Hinglish Checkout Recovery Agent**, built explicitly for Track 3 (AI Revenue Recovery) of the Razorpay AI Buildathon.

The agent automates the detection, diagnosis, and recovery of failed/abandoned payments for online merchants, using natural Hinglish SMS/WhatsApp nudges, bounded negotiation (discounts), and real Razorpay payment integration, while adhering to strict, un-bypassable anti-spam compliance rules.

---

## 🎯 Project Alignment with Track 3 Guidelines

Here is how the project addresses each core evaluation criterion from the buildathon brief:

| Buildathon Brief Requirement | Project Implementation & Proof |
| :--- | :--- |
| **"Every money action explainable, bounded and gated"** | All nudges, dynamic link generations, and discounts are logged in the `AuditLogEntry` with clear `observation → diagnosis → decision → reasoning → action_taken → outcome` columns. No discounts can exceed `config.MAX_DYNAMIC_DISCOUNT_PERCENT` (10%). |
| **"Show measured money recovered across a batch"** | The simulator runs 55 synthetic journeys and outputs a dashboard detailing exactly: **₹ Amount at Risk**, **₹ Amount Recovered**, **₹ Amount Unrecovered**, and **Recovery Rate (%)**. |
| **"Compliant escalation and stopping rules"** | Hard stopping rules are hardcoded in `agent.py` and *proven by unit tests*: hard-stop at max 3 messages, instant stop on payment success (no double-recovery nudge), opt-out keyword detection (e.g. "stop", "nahi chahiye"), and link expiry. |
| **"Show one failure handled gracefully"** | When the Razorpay API connection times out or fails (simulated in `test_recovery_agent.py` and the CLI), the agent catches the error, transitions to using a local fallback checkout link, and alerts support rather than crashing. |
| **"Hinglish recovery"** | Copywriter generates natural Hinglish templates (or dynamic Gemini text) tailored to the exact failure category (`insufficient_funds`, `bank_technical_error`, `card_declined`, etc.) to build customer trust. |

---

## 📁 Repository Structure

* **`config.py`** — Environment variables, API credential loaders, and configurable anti-spam thresholds.
* **`razorpay_client.py`** — Wrapper for `razorpay` python SDK with simulated mode fallback and connection error generation.
* **`database.py`** — Pydantic schemas and thread-safe in-memory store for orders, campaigns, messages, and audit trails.
* **`agent.py`** — The core brain. Contains the classification diagnosis (keyword/Gemini), copy generator, and stopping rule state machine.
* **`simulator.py`** — Batch runner driving 55 customer journeys with diverse personas (Cooperative, Delayed, Hostile, Unresponsive, Paid Elsewhere, System Failure).
* **`main.py`** — Interactive CLI offering Batch Simulation reports, Campaign Audit Trail inspector, and Interactive Chat mode.
* **`test_recovery_agent.py`** — Unit tests verifying the stopping rules and agent fallbacks.

---

## 🚀 How to Run the Project

### Prerequisites
* **Python version:** Python 3.10+ is required.
* **Virtual Environment:** We highly recommend creating and activating a virtual environment (e.g., `python -m venv venv` and activating it) before installing dependencies.

### 1. Installation
Clone the repository and install the dependencies:
```bash
pip install -r requirements.txt
```

### 2. Configuration (Optional)
Create a `.env` file in the project directory to test live Razorpay credentials or dynamic Gemini reasoning:
```ini
# For live Test/Live Mode Payment Link generation
RAZORPAY_KEY_ID=your_key_id
RAZORPAY_KEY_SECRET=your_key_secret

# For LLM-based error classification and Hinglish generation
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.6-flash

# Configurable Thresholds (defaults)
MAX_OUTBOUND_MESSAGES=3
MAX_RETRIES=3
RECOVERY_TIMEOUT_HOURS=24
```
*Note: If no `.env` file is present, the codebase automatically runs in **Mock mode** (safe, sandbox fallback with zero setups required).*

### 3. Run the CLI
Start the main application console:
```bash
python main.py
```
You can choose from three options:
1. **Run Batch Simulation (55 Journeys):** Simulates 55 users over a 24-hour timeline and displays the Rupee-based recovery dashboard. It also writes the full log to `recovery_audit_log.csv`.
2. **Inspect Campaign Audit Trail:** Choose any campaign to see the exact reasoning trail behind every nudge.
3. **Run Interactive Demo Mode:** Play the customer! Attempt a failed purchase, receive a Hinglish nudge, choose to reply with opt-outs, ignore it, or complete payment.

### 4. Run the Unit Tests
Execute the test suite to verify that the stopping rules and API timeout fallbacks are functioning securely:
```bash
python -m unittest test_recovery_agent.py
```

---

## ⚠️ Limitations & Next Steps

* **Synthetic Personas:** The timeline simulator relies on predefined customer personas and reply patterns rather than live customer behavior data. In production, response likelihood will vary dynamically.
* **A/B Testing:** Timing intervals (4h/8h/12h nudges) and discount thresholds (5% dynamic discount) are currently hardcoded configurations rather than A/B tested optimizations.
* **Language Scope:** Currently optimized for Hinglish-only messaging. Next steps include expanding support to regional Indian languages (Tamil, Telugu, Marathi, etc.) based on customer location data.
* **LLM Fallback Handlers:** The agent relies on Gemini API for diagnosis. During test suite executions, rate-limits or deprecations (e.g. stale model configuration) are automatically caught, and the agent successfully and gracefully falls back to rule-based keyword templates to avoid silent failure.

---

## 📈 Simulated Persona Performance Summary
During the batch simulation, the agent processes these distinct customer profiles:
* **Cooperative Payer (15):** Completes payment immediately after Nudge #1. (100% agent-attributed recovery)
* **Delayed Payer (12):** Pays after receiving Nudge #2 (with a 5% discount) or Nudge #3. (100% agent-attributed recovery)
* **Hostile / Opts-Out (10):** Replies with opt-out keywords. The agent halts immediately under compliance rules. (0% recovered, 0% spam)
* **Unresponsive (12):** Never replies. Agent halts strictly after Nudge #3. (0% recovered, 0% spam)
* **Paid Elsewhere (4):** Customer finishes transaction on website directly *before* the recovery agent triggers (outbound_count == 0). Halted under double-recovery prevention. (0% agent-attributed recovery, 100% organic checkout)
* **System Failure (2):** Razorpay API times out. Agent falls back to using the merchant's checkout link; customer still completes payment. (100% agent-attributed recovery via fallback)
