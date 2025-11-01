You are implementing a complete, production-grade datasheet parser and AI extraction pipeline for PartsDB.
This integrates a rule-based PDF parser with optional AI extraction using a local Ollama model (gpt-oss:20b).
All inference must stay local. The AI is fed in 1.5 KB text chunks max.

### 1. Feature Overview

Goal:
Extract key electrical parameters from PDF datasheets already stored as `files.Attachment(type='datasheet')`.
The system shall:
  • Parse text and tables from the PDF using PyMuPDF + Camelot.
  • Slice combined extracted data into ≤1.5 KB chunks.
  • For each chunk, optionally send it to `gpt-oss:20b` via Ollama to propose parameter values.
  • Merge AI outputs with rule-based extractions.
  • Return all results as `ExtractedParam` entries for human review and optional application.

### 2. Environment Variables (add to .env.example and settings.py)

AI_PARSER_ENABLED=true
AI_MODEL=gpt-oss:20b
OLLAMA_BASE_URL=http://127.0.0.1:11434
AI_TIMEOUT_SECONDS=45
AI_CHUNK_SIZE=1500     # bytes per prompt payload

### 3. Dependencies (append to backend/requirements.txt)

PyMuPDF==1.24.9
camelot-py==0.11.0
pandas==2.2.2
pint==0.24.3
python-dateutil==2.9.0.post0
pydantic==2.7.0
requests==2.32.3

### 4. Directory Structure (backend/apps/inventory/parser)

parser/
  __init__.py
  pdf_extract.py      # pure text + table extractor
  normalize.py        # unit parsing & normalization
  rules.py            # rule-based regex extractors
  ai_client.py        # Ollama chat interface
  ai_prompts.py       # system + user prompt builder
  ai_schemas.py       # strict JSON schemas for AI
  ai_runner.py        # orchestrates chunking + AI calls
  runner.py           # master orchestrator (AI + rules)

### 5. pdf_extract.py
Implement:
- extract_text_snippets(path: str) -> list[str]:
    * Use PyMuPDF to iterate pages.
    * Extract text blocks.
    * Clean excessive whitespace.
    * Return list of strings (1 per page).
- extract_table_data(path: str) -> list[str]:
    * Try Camelot.read_pdf(pages='all', flavor='lattice')
    * For each table, join rows into CSV-like lines.
    * Return as plain text lines.
- combine_text_for_ai(snippets, tables, max_bytes=1500) -> list[str]:
    * Merge and chunk into ≤max_bytes UTF-8 slices.
    * Preserve paragraph continuity when possible.

### 6. ai_client.py
- POST to {OLLAMA_BASE_URL}/v1/chat/completions with:
  {
    "model": settings.AI_MODEL,
    "messages": [
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": user_prompt}
    ],
    "temperature": 0.1,
    "max_tokens": 1024,
    "stream": false,
    "response_format": {"type": "json_object"}
  }
- Parse JSON safely. Retry once if invalid.
- Enforce timeout = AI_TIMEOUT_SECONDS.
- Function: `run_ollama_json(prompt_user, prompt_system, schema_cls) -> dict`

### 7. ai_schemas.py
Define strict Pydantic schemas:
- Base schema with `category` + `fields: Dict[str, float | str | None]`
- Subclasses for common categories:
  • InductorSchema — inductance_H, tolerance_pct, dcr_ohm, isat_A, irms_A, size_l_mm, size_w_mm, size_h_mm
  • LdoSchema — vin_min_V, vin_max_V, vout_min_V, vout_max_V, iq_A, dropout_V, temp_min_C, temp_max_C, package
- get_schema_for_component(component) → returns proper schema class.

### 8. ai_prompts.py
- build_system_prompt():
    “You are an expert electronics datasheet parser. Output only JSON conforming to the provided schema. Units must be SI (H, A, V, Ohm, °C, mm). Unknown → null. No comments or extra text.”
- build_user_prompt(component, chunk_text, schema_doc):
    f"""
    Component:
      Manufacturer: {component.manufacturer}
      MPN: {component.mpn}
      Description: {component.description}
    Datasheet snippet (partial, {len(chunk_text)} bytes):
    ---
    {chunk_text}
    ---
    Expected JSON schema:
    {schema_doc}
    """

### 9. ai_runner.py
Implements:
run_ai_extraction(component, attachment) -> list[ExtractedParam]
Steps:
 1. Read PDF text + tables via pdf_extract.
 2. Slice combined data into 1.5 KB chunks.
 3. For each chunk:
     - Build prompt.
     - Call ai_client.run_ollama_json() with schema.
     - Parse results to ExtractedParam list with confidence=0.7–0.9 depending on field count.
 4. Merge duplicates (same key) using average value and max confidence.
 5. Return deduped list.

### 10. runner.py (existing orchestrator)
Update:
if settings.AI_PARSER_ENABLED and request/use_ai=True:
    try AI path first via ai_runner.run_ai_extraction()
    if fails or no params → fall back to rule-based extraction
else:
    use rule-based only
Merge AI and rule results by key:
    if values close (≤1%), merge; else keep both with provenance flags.

### 11. Models
Add caching:
class AiExtractionCache(models.Model):
    attachment_sha256 = models.CharField(max_length=64, db_index=True)
    model = models.CharField(max_length=64)
    schema = models.CharField(max_length=64)
    result_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
Use before each AI call: if cache exists and force=False → reuse.

### 12. API Update
POST /api/components/{id}/parse_datasheet/
Accept body: {"use_ai": true, "force": false}
If AI enabled → call AI pipeline else rule-based.

### 13. Tests
- Mock ai_client to return valid JSON for InductorSchema.
- Test chunking function: input >3 KB text → 3 chunks ≤1.5 KB.
- Test ai_runner returns valid ExtractedParams (confidence ≥0.75) for sample text.

### 14. README Addendum
#### AI-Assisted Parsing (local)
1. Install Ollama and run:  
   `ollama run gpt-oss:20b` (downloads model).
2. Set env vars:
