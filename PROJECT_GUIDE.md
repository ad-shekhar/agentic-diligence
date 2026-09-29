# AGENTIC DILIGENCE: THE COMPLETE MASTER GUIDE
## A Plain-English Explanation of What We Built, Why It Matters, and Our North Star

---

## Welcome! Read This First
If you are new to the company, new to software, or new to the world of Artificial Intelligence (AI), **welcome aboard!** 

This document was written specifically for you. You do not need a computer science degree or a background in venture capital to understand it. We avoid unnecessary jargon, and whenever a technical phrase is required, we explain it right away with real-world analogies.

By the end of this guide, you will thoroughly understand:
1. **The trillion-dollar problem** we solve.
2. **What an "AI Agent" actually is** (and how it differs from ChatGPT).
3. **The 10 core analytical engines** our platform uses to audit AI companies.
4. **How the system works under the hood** from telemetry to interactive dashboards.
5. **Our North Star**—where this product is heading over the next 12 to 24 months.

---

# SECTION 1: The Core Problem We Solve

### 1.1 The AI Gold Rush and the "Pitch Deck" Problem
Imagine you are an investor at a venture capital fund, or an executive at a large corporation looking to buy a promising startup. 

A startup founder walks into your boardroom with a glossy presentation (a "pitch deck"). They say:
> *"Our AI Customer Service Agent is **95% fully autonomous**! It resolves customer complaints for just **$0.001 per ticket**! We have built our own proprietary AI, and it never breaks!"*

If that statement is true, the startup is worth tens or hundreds of millions of dollars. They can replace huge call centers with pure software, generating 80%+ profit margins.

**Here is the catch:** Today, investors and buyers have **no reliable way to check if that claim is true or completely made up**.

### 1.2 The "Dirty Little Secrets" of AI Startups
When technical auditors look behind the curtain of modern AI companies, they frequently uncover what the industry calls **"The AI Façade"**:

1. **"Mechanical Turk" Autonomy (Secret Humans):** The company claims their system is 95% AI. In reality, whenever the AI gets confused (which is often), an alert is silently sent to low-cost human contractors in another timezone who take over the keyboard and answer the customer. The customer thinks it is AI; the investor thinks it is AI; but in truth, it is just an old-fashioned human services agency masquerading as a software company.
2. **The "Unit Economics" Mirage:** The founder claims each task costs a fraction of a penny ($0.001). But when the AI encounters an error, it gets stuck in retry loops, generating massive token bills. Plus, when you add the hidden hourly wages of the human helpers, each "cheap" AI task actually costs $2.00 or $5.00—meaning the startup **loses money on every customer they serve**.
3. **The "Thin Wrapper" Problem (No Real Moat):** The startup claims to have built revolutionary artificial intelligence. In reality, they just wrote a 20-line script that forwards prompts to OpenAI's ChatGPT. If OpenAI updates their API tomorrow, or if a high school student copies their prompt over a weekend, the startup's entire business vanishes overnight.
4. **Dangerous Security Permissions (The "Runaway Agent"):** The AI agent is given god-like access: full permission to run terminal commands, write to production databases, and charge credit cards, without any sandbox or safety guardrails. One malicious prompt from a hacker can wipe out the company's customer records.

### 1.3 The Solution: Agentic Diligence
**Agentic Diligence** is an automated, tamper-proof technical due diligence platform. 

Instead of trusting what founders put on pitch deck slides, our platform connects directly to the startup's live runtime data (called *telemetry*—the digital breadcrumbs left by every AI action). 

Our software deterministically inspects every single request, tracks every penny spent, measures every human intervention, maps every tool called, checks for single points of failure, tests the strength of their intellectual property, and produces a sealed, legally defensible audit package with a definitive **Investment Committee Recommendation**.

In short: **We are the forensic accountants and building inspectors for Artificial Intelligence.**

---

# SECTION 2: What is an "AI Agent"? (The Basics)

To understand our software, you only need to know three simple concepts:

### Concept A: Simple Chatbot vs. AI Agent
* **A Simple Chatbot (like basic ChatGPT):** You ask a question, it types an answer. It lives in a sandbox and cannot take actions in the physical or digital world.
* **An AI Agent:** An AI that has hands and feet. Given a goal (*"Refund this angry customer and update their billing address"*), the agent creates a multi-step plan. It calls the company CRM, looks up the order, communicates with a database, checks fraud rules, triggers a Stripe refund, and sends an email.

### Concept B: Traces and Spans (The Digital Breadcrumbs)
How do we inspect what an AI Agent did?
* **A Trace:** A complete story of one user request from start to finish. (For example: *"Customer #409 asked for an order cancellation"*).
* **A Span:** A single step within that story. A trace usually contains 5 to 20 spans:
  * *Span 1:* Orchestrator Agent plans the steps.
  * *Span 2:* Calls OpenAI GPT-4o to read the customer's sentiment.
  * *Span 3:* Calls a CRM tool to find order #9921.
  * *Span 4:* An error occurs! (CRM server timeout).
  * *Span 5:* A human operator steps in to manually finish the task.
  * *Span 6:* An automated grader checks if the answer was polite.

By collecting and analyzing these spans, our platform reconstructs 100% of the truth.

---

# SECTION 3: The 10 Core Engines We Have Built

Our platform is organized into 10 modular analytical engines. Each engine solves one specific due diligence question:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AGENTIC DILIGENCE PLATFORM                      │
├───────────────────────────────┬────────────────────────────────────────┤
│ 1. Pitch Claims vs Reality    │ 6. Cryptographic Digital Seal          │
│ 2. True Autonomy vs Human (HIR)│ 7. Tool Safety & Blast Radius          │
│ 3. Unit Economics & Trust Tax │ 8. Head-to-Head Target Comparison      │
│ 4. System Cascades & Overruns │ 9. Real Moat vs Commodity Wrapper      │
│ 5. AI Bill of Materials (AIBOM)│ 10. What-If Simulator & Deal Memo      │
└───────────────────────────────┴────────────────────────────────────────┘
```

---

### Engine 1: Pitch Deck Claim Verifier ("Did they tell the truth?")
* **The Goal:** Take the founder's exact words from their pitch deck or investor questionnaire, and mathematically test them against reality.
* **How It Works:** 
  1. We record the claim (e.g., *"95% Autonomous operations"*).
  2. We calculate the observed metric from real system data.
  3. We assign one of four verifiable verdicts:
     * **VERIFIED (Green):** True within acceptable statistical tolerance.
     * **PARTIALLY VERIFIED (Yellow):** Partially true, but with caveats.
     * **CONTRADICTED (Red):** The claim was false (e.g., claiming 95% autonomy when real data shows only 75%).
     * **INSUFFICIENT EVIDENCE (Gray):** Not enough data was provided to prove it.

---

### Engine 2: True Autonomy vs. Human Intervention Rate (HIR)
* **The Goal:** Figure out how much of the work is actually being done by software versus hidden human staff.
* **The Key Metric: Human Intervention Rate (HIR)**:
  $$\text{HIR} = \frac{\text{Number of Tasks Requiring Human Help}}{\text{Total Tasks Analyzed}} \times 100\%$$
* **How It Works:** We look for two things in the data:
  1. *Explicit Human Spans:* Where the system explicitly logged that an employee took over.
  2. *Heuristic Latency Gaps:* When a software task suddenly pauses for 8 minutes in the middle of a workflow before completing, that pause almost always represents a human reading a ticket and clicking a button.
* **Business Takeaway:** If a startup has an HIR of 25%, one out of every four customers requires an expensive human employee. That is not a 90% software business.

---

### Engine 3: True Unit Economics & The "Trust Tax"
* **The Goal:** Determine the exact computing cost to solve one customer task, and uncover hidden quality control expenses.
* **How It Works:**
  * We track the exact prompt tokens (words sent in) and completion tokens (words generated out) across every model call.
  * We multiply those tokens by our versioned enterprise pricing database (covering OpenAI, Anthropic, Google, and self-hosted hardware costs).
  * We calculate latency percentiles: **P50** (median speed), **P95** (the speed for slower cases), and **P99** (the worst-case lag).
* **The "Trust Tax" (Quality Control Overhead):**
  * When an AI produces an answer, smart companies run a second AI model to grade it and check for hallucinations.
  * That extra grading cost is the *Trust Tax*. If a company spends $0.004 on the initial answer and $0.001 on the grader, their Trust Tax is 25%. If a company has a 0% Trust Tax, it means **no automated quality control is happening at all**.

---

### Engine 4: System Cascades & Domino Effects
* **The Goal:** Measure what happens when a third-party tool or API temporarily fails. Does the agent handle it gracefully, or does it trigger an expensive downward spiral?
* **How It Works:**
  * We detect when an initial tool call fails (e.g., a CRM returns a 504 Timeout).
  * We track how many retry models were spawned and whether fallback tools were used.
  * We compute the **Average Cost Multiplier on Error** (typically 2.0x to 3.5x higher cost than a normal task) and added latency (+1,500ms or more).
* **Business Takeaway:** If a startup's external tools fail frequently, their AI computing bills can double or triple unexpectedly without any increase in customer volume.

---

### Engine 5: AI Bill of Materials (AIBOM) & Single Points of Failure
* **The Goal:** Just like a food label lists every ingredient in a cereal box, an AIBOM lists every single ingredient powering the AI product.
* **What is Inside the AIBOM:**
  1. **Models:** Every LLM used, their vendor, license, and hosting type.
  2. **Tools:** Every internal and external tool (CRM lookups, email dispatchers, database writers).
  3. **Databases:** Vector databases (Pinecone, Milvus), relational databases.
  4. **Single Point of Failure (SPOF) Analysis:** If the company sends 98% of its traffic to one provider (e.g., OpenAI) and has zero fallback code, that provider is a critical single point of failure. If that vendor has an outage, the startup is completely down.
* **Standards Compliance:** We generate this in both our native JSON format and the international **CycloneDX 1.6** cybersecurity standard.

---

### Engine 6: Tamper-Proof Cryptographic Digital Seal
* **The Goal:** Ensure that no one—not the startup, not the auditor, not a competitor—can alter the telemetry, change the numbers, or forge a passing grade.
* **How It Works (The Chain-of-Custody):**
  1. Every raw trace gets a unique SHA-256 cryptographic fingerprint (a 64-character hash that acts like a digital wax seal).
  2. The analytical metrics, the evidence records, the AIBOM, and the final PDF report are cryptographically linked together.
  3. A Master Manifest Seal is generated.
* **The Result:** Anyone can run a single command (`python cli.py verify-bundle --bundle package.zip`) to mathematically verify that every byte inside the diligence archive is authentic and untampered.

---

### Engine 7: Tool Safety & Blast Radius
* **The Goal:** Assess the physical and digital danger of what the AI is permitted to do.
* **Privilege Tiers:**
  * **CRITICAL RISK (Red):** Shell/terminal commands, Python code interpreters, root execution. If the AI gets tricked (via prompt injection), a hacker can run arbitrary code on the server.
  * **HIGH RISK (Orange):** Database write/delete operations (`UPDATE`, `DROP TABLE`). Risk of corrupting user data.
  * **MEDIUM RISK (Yellow):** External communications (Stripe charges, sending customer emails, public webhooks).
  * **LOW RISK (Green):** Read-only lookups (searching a knowledge base, viewing an order).
* **Unconstrained Traces:** We flag every trace where high-privilege tools were executed without a human checkpoint or sandbox barrier.

---

### Engine 8: Side-by-Side Target Comparison
* **The Goal:** Investors rarely look at one company in isolation. They want to compare **Target A vs. Target B** to decide where to invest.
* **How It Works:**
  * Our comparative engine runs two companies through identical analytical pipelines.
  * It generates a clear head-to-head matrix across 10 critical metrics.
  * It crowns explicit **Dimension Winners**:
    * *Autonomy Winner* (higher true AI rate).
    * *Unit Economics Winner* (lower cost per resolved task).
    * *Resilience Winner* (lower vendor dependency and fewer failure loops).
    * *Safety Winner* (fewer dangerous tool privileges and more verified claims).

---

### Engine 9: Real Moat vs. Copycat Risk ("Wrapper vs. Moat")
* **The Goal:** Answer the single most common question asked by venture capitalists: *"Is this company just a ChatGPT wrapper, or do they own a real technology moat?"*
* **The Composite Moat Score (0 to 100 points):**
  1. **Scaffolding Depth (25 pts):** Do they have complex multi-agent reasoning, deep state machines, and parent-child cognitive branching, or just a single prompt?
  2. **Model Sovereignty (25 pts):** Do they own their weights, fine-tune models, or run open-source models (like Llama-3) on their own servers? Or are they 100% reliant on commercial cloud APIs?
  3. **Custom Tool Connectors (25 pts):** Do they integrate deeply with proprietary enterprise systems (ERP, custom databases) that competitors cannot easily access?
  4. **Data Flywheel (25 pts):** Does the system record every human intervention and run automated grading to make itself smarter every day?
* **Cloning Barrier Output:** We estimate how many engineering months and how many dollars of capital a competitor would need to copy their product from scratch (e.g., *"1.5 months and $95k"* for a wrapper vs. *"18 months and $1.75M"* for a deep compound system).

---

### Engine 10: What-If Stress Simulator & Investment Committee Memo
* **The Goal:** Simulate the financial future of the company under stress, and give the investor an institutional deal memo with an actionable checklist.
* **The What-If Simulator:**
  * What if customer volume grows 10x?
  * What if OpenAI raises model prices by 25%?
  * What if we pay human reviewers $30/hour to fix the AI's mistakes?
  * *Result:* We calculate the **Fully-Loaded Gross Margin**. If the company sells a task for $0.05, but human review labor costs $0.30, their true margin is **-500%**. We highlight this immediately so buyers don't walk into a financial trap.
* **The Investment Committee (IC) Memo:**
  * **Diligence Risk Score (0–100):** A single composite risk gauge.
  * **Deal Verdict:** One of four clear recommendations:
    * `RECOMMENDED`
    * `CONDITIONAL_REMEDIATION_REQUIRED`
    * `HIGH_RISK_CAUTION`
    * `DO_NOT_PROCEED`
  * **Automated Flags:** Red Flags (dealbreakers), Yellow Flags (warnings), and Green Flags (strengths).
  * **100-Day Technical Remediation Playbook:** Concrete engineering milestones (P0 to P3) for fixing issues post-acquisition.

---

# SECTION 4: Architecture & How It All Fits Together

Here is how data moves through our platform:

1. **Ingestion Layer:**
   * Receives OpenTelemetry (OTEL) GenAI trace data from live agents or generated benchmark scenarios (Scenario A through J).
   * Parses spans, models, tokens, tools, latency, and human intervention flags.
2. **Analysis Layer (Deterministic Engines):**
   * Computes mathematical truth across Autonomy, Unit Economics, Failure Cascades, Tool Risk, AIBOM, Defensibility, and Operational Stress.
3. **Evidence Layer:**
   * Synthesizes formal `EvidenceRecord` nodes linking stated founder claims to observed facts, boundary formulas, and data limitations.
4. **Packaging Layer:**
   * Generates a tamper-proof `.zip` bundle containing the PDF report, CycloneDX AIBOM, Native AIBOM, Investment Committee Memo, JSON package, and SHA-256 checksums.
5. **Cockpit UI Layer:**
   * Serves an interactive executive dashboard with live scenario selectors, sensitivity sliders, and drill-down drawers.

---

# SECTION 5: How to Use the System (Step-by-Step)

### Option A: The Interactive Web Cockpit (Best for Visual Reviews)
1. Start the server:
   ```bash
   python cli.py serve --port 8000
   ```
2. Open your browser to `http://localhost:8000`.
3. In the top bar, pick any scenario (e.g., **Scenario A** for a standard benchmark, **Scenario C** for falsified claims, or **Scenario B** for verified high-quality AI).
4. Click **Run Benchmark**. Within 3 seconds, all 10 tabs populate with live charts, tables, and risk scores.
5. In **Tab 9 (What-If Simulator)**, move the sliders to see gross margins recalculate in real-time.
6. Click **Export Diligence Package** in the top right to download the official PDF report or cryptographic `.zip` bundle.

### Option B: The Command-Line Interface (Best for Automated Audits)
* **Generate a Full Diligence Package & PDF:**
  ```bash
  python cli.py generate-demo-report --scenario scenario_a
  ```
* **Verify Any Bundle's Cryptographic Seal:**
  ```bash
  python cli.py verify-bundle --bundle diligence_package_scenario_a.zip
  ```
* **Run a Moat Defensibility Audit:**
  ```bash
  python cli.py analyze-defensibility --scenario scenario_a
  ```
* **Run What-If Operational Stress Testing:**
  ```bash
  python cli.py stress-test --scenario scenario_a --volume-mult 5.0 --labor-rate 30.0
  ```
* **Generate an Executive Investment Committee Memo:**
  ```bash
  python cli.py diligence-memo --scenario scenario_a
  ```
* **Compare Two AI Companies Head-to-Head:**
  ```bash
  python cli.py compare-targets --target-a scenario_a --target-b scenario_c
  ```

---

# SECTION 6: The North Star (Where We Are Going)

We have built the industry's most thorough deterministic audit platform for AI agents. But our ultimate vision—our **North Star**—is much bigger:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE NORTH STAR ROADMAP                          │
├────────────────────────────────┬───────────────────────────────────────┤
│ PHASE 1 (COMPLETED):           │ Static Due Diligence Package Engine   │
│ PHASE 2 (NEXT 3-6 MONTHS):     │ Live VDR Connector & Real-Time Stream │
│ PHASE 3 (6-12 MONTHS):         │ Automated Red-Teaming & Jailbreaks    │
│ PHASE 4 (12-24 MONTHS):        │ Continuous Post-Close Monitoring      │
└────────────────────────────────┴───────────────────────────────────────┘
```

### 1. Direct Virtual Data Room (VDR) Ingestion
* Currently, users can upload trace JSON files or generate benchmark scenarios.
* **North Star:** Pre-built connectors to enterprise data rooms (Intralinks, Datasite) and cloud observability platforms (Datadog, LangSmith, Arize, OpenTelemetry collectors). An investor inputs an API key or data room link, and our system automatically pulls 90 days of telemetry and outputs the complete diligence report.

### 2. Automated Adversarial Red-Teaming (The "Crash Test")
* Beyond passive telemetry analysis, the system will actively send synthetic stress probes to the target company's agent in a staging environment.
* It will test for prompt injection, jailbreaking, privilege escalation, and data exfiltration, producing an automated "Crash Test Safety Rating" (like an automotive NCAP score for AI).

### 3. Continuous Post-Close AI Governance (The "Black Box" Recorder)
* Technical due diligence does not end when the acquisition closes. 
* **North Star:** The same Agentic Diligence engine is deployed into the portfolio company's production environment as a lightweight governance agent. If the acquired company's human intervention rate spikes from 10% to 35%, or if an unsandboxed bash command is called, the private equity firm or enterprise board receives an immediate automated alert.

### 4. Global AI Benchmarking Index
* As our platform audits hundreds of AI targets, we will build the world's largest anonymized database of empirical agent performance metrics (e.g., *"What is the median true autonomy rate for an AI legal assistant vs. an AI medical coder?"*). This allows investors to benchmark any new target against verified industry medians.

---

# SECTION 7: Newcomer's Jargon-Buster & Glossary

| Term / Acronym | What It Stands For | Plain-English Explanation |
| :--- | :--- | :--- |
| **HIR** | Human Intervention Rate | The percentage of customer tasks where a human employee had to step in and fix or finish what the AI was doing. Lower is better. |
| **HHI** | Herfindahl-Hirschman Index | A standard economic metric measuring vendor concentration. High HHI means the startup is 100% dependent on one provider (like OpenAI). |
| **AIBOM** | AI Bill of Materials | An ingredient list of every model, tool, database, and library used to create the AI application. |
| **SPOF** | Single Point of Failure | A single component that, if it goes down, breaks the entire customer workflow. |
| **Span** | OpenTelemetry Span | One single atomic step in an AI workflow (e.g., an LLM prompt call, a database search, or an email dispatch). |
| **Trace** | OpenTelemetry Trace | The full journey of one customer request, composed of multiple individual spans. |
| **P95 Latency** | 95th Percentile Speed | The response time that 95% of tasks finish under. It reveals how slow the system gets during peak or complex requests. |
| **Trust Tax** | Evaluation Overhead Rate | The extra computing cost spent on automated guardrails and judges to double-check that the AI didn't hallucinate. |
| **Prompt Injection** | Adversarial AI Attack | When a user inputs tricky instructions that force the AI to ignore its rules and perform unauthorized actions. |
| **Moat** | Defensibility Barrier | A unique technological or business advantage (like fine-tuned weights or deep data integrations) that prevents copycats. |
| **SHA-256** | Secure Hash Algorithm | A mathematical formula that turns any file into a unique 64-character code. If even one letter changes, the code breaks, proving tampering. |
| **VDR** | Virtual Data Room | A secure online repository where companies share confidential financial and technical documents during an acquisition or fundraising. |

---

### Summary in One Sentence
**Agentic Diligence is the truth engine for AI—we replace founder hype with verifiable mathematics so investors and enterprises can safely back, buy, and deploy autonomous systems.**
