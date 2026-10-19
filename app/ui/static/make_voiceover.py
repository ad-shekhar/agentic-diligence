import os
import win32com.client

voiceover_text = """
Welcome to the official demonstration of Agentic Diligence, the standardized technical due diligence platform built specifically for artificial intelligence agents and compound AI systems.

Today, enterprise acquirers and venture capital investors face a critical blind spot: the AI Façade. Founders routinely claim ninety-five percent autonomy, sub-penny unit economics, and proprietary defensible moats. But behind closed doors, many systems rely on secret human contractors in overseas call centers, catastrophic token retry cascades when external APIs fail, and dangerous unconstrained tool permissions with zero real defensibility.

Agentic Diligence solves this multi-billion dollar problem. Instead of relying on founder pitch decks, our platform connects directly to runtime OpenTelemetry logs, deterministically evaluating ten specialized analytical engines to deliver institutional-grade, mathematically verified audit packages.

Let us walk through the live executive cockpit.

At the top, our quick summary strip immediately reveals the company's real vital signs: True AI Automation, Measured Cost Per Task, Cost Spike on System Error, Quality Check Overhead, and Single Vendor Concentration.

In Tab One, the Pitch versus Reality Verifier mathematically cross-examines founder assertions against observed telemetry. While Acme AI claimed ninety-five percent autonomy, the live audit reveals only seventy-five point six percent autonomy, with a twenty-four point four percent Human Intervention Rate. The verdict: Contradicted, with immutable cryptographic evidence records.

In Tab Two, the AI Bill of Materials, or AIBOM, automatically itemizes every foundation model, external tool, and database powering the system, exported in both native JSON and CycloneDX one point six cybersecurity standards. Here, our Single Point of Failure engine flags an extreme ninety-eight percent dependence on a single model provider without automated fallback.

In Tab Three, Outages and Bottlenecks reveals what happens during real-world failures. When an upstream CRM or database times out, the agent spirals into unconstrained retry loops, driving a two point two times cost multiplier and severe latency degradation.

In Tab Six, Tool Safety and Permissions audits the agent's blast radius across low, medium, high, and critical privilege tiers. We flag unconstrained traces where arbitrary shell execution and database write operations occur without human-in-the-loop safeguards.

In Tab Seven, Head-to-Head Comparison allows investment committees to evaluate multiple acquisition targets side-by-side, crowning definitive winners across autonomy, economics, resilience, and safety.

In Tab Eight, Real Moat versus Copycat Risk evaluates true intellectual property defensibility. Our composite moat score calculates scaffolding depth, model sovereignty, proprietary connectors, and data flywheels, estimating the exact cloning barrier in engineering months and capital required for a competitor to replicate the system.

In Tab Nine, the What-If Financial Simulator provides interactive stress testing. As investors adjust volume, token price shocks, and human operator hourly wages, the platform dynamically recalculates fully loaded gross margins in real time, preventing buyers from acquiring unprofitable business models.

Finally, in Tab Ten, the platform synthesizes an institutional Investment Committee Deal Memo, delivering a clear acquisition verdict, prioritized red flags, and a concrete one-hundred-day technical remediation playbook, all sealed in a cryptographically verifiable tamper-proof audit package.

This is Agentic Diligence: transforming subjective AI promises into verifiable mathematical truth.
"""

artifact_dir = r"C:\Users\adity\.gemini\antigravity-ide\brain\b12b794c-36eb-4fcb-a0e9-c9499d9acc18"
out_wav = os.path.join(artifact_dir, "agentic_diligence_voiceover.wav")

speaker = win32com.client.Dispatch("SAPI.SpVoice")
# Set voice to Zira if available, or David
voices = speaker.GetVoices()
for i in range(voices.Count):
    desc = voices.Item(i).GetDescription()
    if "Zira" in desc:
        speaker.Voice = voices.Item(i)
        print("Selected voice:", desc)
        break

# Set audio output stream to WAV file
stream = win32com.client.Dispatch("SAPI.SpFileStream")
# 3 = SSFMCreateForWrite
stream.Open(out_wav, 3, False)
speaker.AudioOutputStream = stream
speaker.Rate = 0  # normal conversational pacing
speaker.Volume = 100
speaker.Speak(voiceover_text.strip())
stream.Close()

size_kb = round(os.path.getsize(out_wav) / 1024, 1)
print(f"Generated voiceover WAV successfully: {out_wav} ({size_kb} KB)")
