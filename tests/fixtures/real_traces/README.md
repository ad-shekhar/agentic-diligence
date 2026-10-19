# Real-Agent OpenTelemetry Trace Fixtures

This directory contains real, reproducible, and sanitized OpenTelemetry trace fixtures exported from production AI agent frameworks to validate the `agd` ingestion and normalization pipeline.

## Fixture Inventory & Provenance

### 1. `langchain_openai_real.json`
- **Source Framework:** LangChain / LangGraph (Python SDK `opentelemetry-sdk` v1.24.0)
- **Agent Architecture:** Multi-step customer support ticket resolution orchestrator.
- **Workflow Topology:**
  1. `LangGraph_SupportOrchestrator` (Root span, `kind: INTERNAL`)
  2. `ChatOpenAI.generate` (Child span calling OpenAI `gpt-4o`, 540 prompt tokens, 135 completion tokens)
  3. `Tool:postgres_order_lookup` (Child tool call executing database lookup)
  4. `ChatOpenAI.synthesize_response` (Child span calling OpenAI `gpt-4o-mini`, 720 prompt tokens, 180 completion tokens)
- **Sanitization Details:** Customer PII (customer email, phone number, order ID), proprietary database credentials, and secret OpenAI API keys have been scrubbed. Attribute keys, span timing hierarchies, and token usages are preserved verbatim.
- **Epistemic Trust Level:** `T1` (In-process SDK).

---

### 2. `claude_mcp_real.json`
- **Source Framework:** Claude Desktop with Model Context Protocol (MCP protocol version `2024-11-05`)
- **Agent Architecture:** Stdio/SSE tool-calling agent executing filesystem operations.
- **Workflow Topology:**
  1. `mcp.tool_call.read_file` (Captured via observe-only MCP proxy, `tools/call`, status `success`)
  2. `anthropic.messages.create` (Calling Anthropic `claude-3-5-sonnet-20241022`, 1,420 input tokens, 380 output tokens)
- **Sanitization Details:** File system absolute paths and private file buffer contents have been redacted. Tool metadata (`gen_ai.tool.name`, `call_id`), latency measurements, and provider attributes are preserved verbatim.
- **Epistemic Trust Level:** `T2` (Independent Proxy for tool calls).
