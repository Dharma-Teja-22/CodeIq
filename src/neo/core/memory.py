import os
import re
import math
import string
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Base directories
NEO_HOME = Path.home() / ".neo"
MEMORY_DIR = NEO_HOME / "memory"
PROJECTS_MEMORY_DIR = MEMORY_DIR / "projects"
CONCEPTS_DIR = MEMORY_DIR / "concepts"
DEBUG_HISTORY_FILE = MEMORY_DIR / "debug_history.md"
GLOBAL_MEMORY_FILE = MEMORY_DIR / "global_memory.md"

# Canonical 4-Section Schema headers for Tier 2
CANONICAL_SECTIONS = [
    "Tech Stack & Runtime",
    "Active Architecture & Key Modules",
    "Critical Constraints, Preferences",
    "Current/Ongoing Tasks",
]

# Common English stopwords for BM25 retrieval
STOPWORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s", "same", "she",
    "should", "so", "some", "such", "t", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself", "yourselves"
})


def ensure_memory_layout() -> None:
    """Ensure all expected storage directories exist on disk."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    (NEO_HOME / "sessions" / "archive").mkdir(parents=True, exist_ok=True)

    if not GLOBAL_MEMORY_FILE.exists():
        try:
            GLOBAL_MEMORY_FILE.touch()
        except Exception:
            pass

    if not DEBUG_HISTORY_FILE.exists():
        try:
            DEBUG_HISTORY_FILE.touch()
        except Exception:
            pass


def _atomic_write_text(file_path: Path, content: str) -> None:
    """Atomically write text content using a temporary file and os.replace."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = file_path.parent
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
        tf.write(content)
        temp_name = tf.name
    os.replace(temp_name, file_path)


# ==============================================================================
# Tier 3: Global User Memory & Preference Overwriting / Deduplication
# ==============================================================================

def load_global_memory() -> str:
    """Return raw content of global_memory.md."""
    ensure_memory_layout()
    if GLOBAL_MEMORY_FILE.exists():
        try:
            return GLOBAL_MEMORY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


def _extract_semantic_keywords(text: str) -> set:
    """Extract lowercased alphanumeric keywords excluding stopwords."""
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def save_to_memory(information: str, category: str = "preference") -> str:
    """
    Save user facts, instructions, or hard constraints to Tier 3 global memory.
    Implements intelligent deduplication and smart preference overwriting:
    e.g. Setting 'do not provide emojis' and later 'provide emojis' will supersede/overwrite
    the conflicting entry instead of duplicating.
    """
    ensure_memory_layout()
    clean_info = " ".join(information.strip().lstrip("-").strip().split())
    if not clean_info:
        return "Empty information provided."

    clean_category = category.strip().capitalize() or "Preference"

    existing_content = ""
    lines: List[str] = []
    if GLOBAL_MEMORY_FILE.exists():
        existing_content = GLOBAL_MEMORY_FILE.read_text(encoding="utf-8")
        lines = [line.strip() for line in existing_content.splitlines() if line.strip()]

    # Exact duplicate check (case-insensitive)
    normalized_clean = clean_info.lower()
    for line in lines:
        entry_text = line.lstrip("-").strip()
        if ":" in entry_text:
            _, _, entry_text = entry_text.partition(":")
            entry_text = entry_text.strip()
        if entry_text.lower() == normalized_clean:
            return f"Memory already contains this exact information under {clean_category}."

    # Conflict / Overwrite Detection:
    # If the new statement shares primary topic keywords (e.g. 'emoji', 'emojis')
    # with an existing preference in the same category or overall preferences,
    # supersede/overwrite that line.
    new_keywords = _extract_semantic_keywords(clean_info)
    overwritten = False
    new_lines: List[str] = []
    new_entry = f"-{clean_category}: {clean_info}"

    for line in lines:
        entry_text = line.lstrip("-").strip()
        cat = ""
        val = entry_text
        if ":" in entry_text:
            cat, _, val = entry_text.partition(":")
            cat = cat.strip()
            val = val.strip()

        line_keywords = _extract_semantic_keywords(val)
        # If substantial keyword overlap (>60% of significant content terms) or same topic entity
        common = new_keywords.intersection(line_keywords)
        is_same_topic = False
        if common and (len(common) >= max(1, min(len(new_keywords), len(line_keywords)) * 0.6)):
            is_same_topic = True

        if is_same_topic and (not cat or cat.lower() == clean_category.lower() or "preference" in cat.lower()):
            # Overwrite/update this preference
            new_lines.append(new_entry)
            overwritten = True
        else:
            new_lines.append(line)

    if not overwritten:
        new_lines.append(new_entry)

    updated_text = "\n".join(new_lines) + "\n"
    _atomic_write_text(GLOBAL_MEMORY_FILE, updated_text)

    if overwritten:
        return f"Updated and superseded existing preference in global memory with: '{clean_info}'."
    return f"Saved new {clean_category} to global memory: '{clean_info}'."


# ==============================================================================
# Tier 2: Project-Scoped Working Memory
# ==============================================================================

def get_project_memory_file(project_name: Optional[str] = None) -> Path:
    ensure_memory_layout()
    pname = project_name or Path.cwd().name
    return PROJECTS_MEMORY_DIR / f"{pname}.md"


def _normalize_section_title(section: str) -> str:
    """Fuzzy map input section names to canonical 4 headers."""
    s = section.lower().strip()
    if any(k in s for k in ("stack", "runtime", "tech", "dependencies", "python", "node")):
        return "Tech Stack & Runtime"
    if any(k in s for k in ("arch", "module", "router", "structure", "design")):
        return "Active Architecture & Key Modules"
    if any(k in s for k in ("constraint", "pref", "rule", "convention")):
        return "Critical Constraints, Preferences"
    if any(k in s for k in ("task", "todo", "ongoing", "current", "plan", "backlog")):
        return "Current/Ongoing Tasks"
    return section.strip()


def parse_project_memory(content: str) -> Dict[str, List[str]]:
    """Parse project markdown into canonical sections."""
    sections: Dict[str, List[str]] = {sec: [] for sec in CANONICAL_SECTIONS}
    current_sec: Optional[str] = None

    for line in content.splitlines():
        if line.startswith("## "):
            header = line[3:].strip()
            norm = _normalize_section_title(header)
            current_sec = norm
            if current_sec not in sections:
                sections[current_sec] = []
        elif current_sec is not None:
            if line.strip():
                sections[current_sec].append(line.strip())

    return sections


def load_project_memory(project_name: Optional[str] = None) -> str:
    """Load project memory markdown or return default canonical template if empty."""
    file_path = get_project_memory_file(project_name)
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""


def update_project_memory(section: str, content: str, mode: str = "replace", project_name: Optional[str] = None) -> str:
    """
    Atomically update a section in the active project's memory markdown file.
    Modes:
      - 'replace': Overwrites target section body (essential for Current/Ongoing Tasks).
      - 'append': Appends content lines without duplicating identical items.
    """
    file_path = get_project_memory_file(project_name)
    raw_content = ""
    if file_path.exists():
        try:
            raw_content = file_path.read_text(encoding="utf-8")
        except Exception:
            raw_content = ""

    parsed = parse_project_memory(raw_content)
    target_section = _normalize_section_title(section)

    new_items = [
        line.strip() if line.strip().startswith("-") else f"- {line.strip()}"
        for line in content.splitlines()
        if line.strip()
    ]

    if not new_items and content.strip():
        new_items = [f"- {content.strip()}"]

    if target_section not in parsed:
        parsed[target_section] = []

    if mode.lower() == "replace":
        parsed[target_section] = new_items
    else:  # append mode
        existing = parsed[target_section]
        existing_set = {x.lstrip("-").strip().lower() for x in existing}
        for item in new_items:
            if item.lstrip("-").strip().lower() not in existing_set:
                existing.append(item)

    # Reconstruct canonical markdown
    output_blocks = []
    # Emit canonical 4 sections first
    for sec in CANONICAL_SECTIONS:
        items = parsed.get(sec, [])
        output_blocks.append(f"## {sec}")
        if items:
            output_blocks.append("\n".join(items))
        else:
            output_blocks.append("- None specified")
        output_blocks.append("")

    # Any custom sections
    for sec, items in parsed.items():
        if sec not in CANONICAL_SECTIONS:
            output_blocks.append(f"## {sec}")
            output_blocks.append("\n".join(items) if items else "- None specified")
            output_blocks.append("")

    rendered = "\n".join(output_blocks).strip() + "\n"
    _atomic_write_text(file_path, rendered)
    return f"Successfully updated section '## {target_section}' in project memory ({mode} mode)."


# ==============================================================================
# Tier 4: Zero-Dependency Episodic BM25 Engine
# ==============================================================================

def log_successful_debug(error_description: str, solution: str) -> str:
    """Log verified debug solution to ~/.neo/memory/debug_history.md."""
    ensure_memory_layout()
    entry = (
        f"\n## Error: {error_description.strip()}\n"
        f"**Solution:**\n{solution.strip()}\n"
    )
    if DEBUG_HISTORY_FILE.exists():
        current = DEBUG_HISTORY_FILE.read_text(encoding="utf-8")
    else:
        current = ""
    _atomic_write_text(DEBUG_HISTORY_FILE, current + entry)
    return "Successfully logged debug solution to episodic history."


def save_concept(concept_name: str, explanation: str) -> str:
    """Save an architectural pattern or conceptual doc to ~/.neo/memory/concepts/{concept_name}.md."""
    ensure_memory_layout()
    safe_name = "".join(c for c in concept_name if c.isalnum() or c in ("-", "_")).strip()
    if not safe_name:
        safe_name = "concept"
    c_path = CONCEPTS_DIR / f"{safe_name}.md"
    body = f"# {concept_name}\n\n{explanation.strip()}\n"
    _atomic_write_text(c_path, body)
    return f"Saved concept '{concept_name}' to episodic concepts."


def _tokenize(text: str) -> List[str]:
    """Tokenize lowercase alphanumeric words filtering stopwords."""
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return [w for w in words if len(w) > 1 and w not in STOPWORDS]


class BM25Retriever:
    """
    Pure-Python Okapi BM25 Ranking Engine with exact substring boosting.
    Runs fully offline in < 2ms, zero dependencies.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def collect_chunks(self) -> List[Dict[str, str]]:
        """Collect chunk candidates from debug history, concepts, and workspace architecture."""
        ensure_memory_layout()
        chunks: List[Dict[str, str]] = []

        # 1. Debug History
        if DEBUG_HISTORY_FILE.exists():
            try:
                content = DEBUG_HISTORY_FILE.read_text(encoding="utf-8")
                blocks = content.split("## Error:")
                for block in blocks:
                    cleaned = block.strip()
                    if cleaned:
                        chunks.append({
                            "source": "debug_history.md",
                            "title": cleaned.split("\n", 1)[0].strip(),
                            "content": f"## Error: {cleaned}"
                        })
            except Exception:
                pass

        # 2. Concepts
        if CONCEPTS_DIR.exists():
            for c_file in CONCEPTS_DIR.glob("*.md"):
                try:
                    c_text = c_file.read_text(encoding="utf-8")
                    paras = c_text.split("\n\n")
                    for p in paras:
                        p_str = p.strip()
                        if len(p_str) > 20:
                            chunks.append({
                                "source": f"concepts/{c_file.name}",
                                "title": c_file.stem,
                                "content": p_str[:1200]
                            })
                except Exception:
                    pass

        # 3. Local architecture.md if present in current working dir
        arch_file = Path.cwd() / "architecture.md"
        if arch_file.exists():
            try:
                a_text = arch_file.read_text(encoding="utf-8")
                for p in a_text.split("\n\n"):
                    p_str = p.strip()
                    if len(p_str) > 20:
                        chunks.append({
                            "source": "architecture.md",
                            "title": "Architecture Map",
                            "content": p_str[:1200]
                        })
            except Exception:
                pass

        return chunks

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        chunks = self.collect_chunks()
        if not chunks or not query.strip():
            return []

        query_tokens = _tokenize(query)
        raw_query_lower = query.strip().lower()

        corpus_tokens = [_tokenize(c["content"] + " " + c["title"]) for c in chunks]
        N = len(corpus_tokens)
        doc_lens = [len(tokens) for tokens in corpus_tokens]
        avgdl = sum(doc_lens) / N if N > 0 else 1.0

        # Document frequencies for query tokens
        scores = [0.0] * N
        for t in set(query_tokens):
            # Calculate DF
            df = sum(1 for tokens in corpus_tokens if t in tokens)
            if df == 0:
                # Substring token fallback for tokens >= 4 chars
                if len(t) >= 4:
                    for i, tokens in enumerate(corpus_tokens):
                        if any(t in tok or tok in t for tok in tokens):
                            scores[i] += 0.4
                continue

            # Okapi BM25 IDF
            idf = math.log(1.0 + (N - df + 0.5) / (df + 0.5))
            for i, tokens in enumerate(corpus_tokens):
                tf = tokens.count(t)
                if tf > 0:
                    tf_score = (tf * (self.k1 + 1.0)) / (
                        tf + self.k1 * (1.0 - self.b + self.b * (doc_lens[i] / (avgdl or 1.0)))
                    )
                    scores[i] += idf * tf_score

        # Exact substring bonus (+3.0)
        for i, chunk in enumerate(chunks):
            chunk_text = (chunk["content"] + " " + chunk["title"] + " " + chunk["source"]).lower()
            if raw_query_lower in chunk_text:
                scores[i] += 3.0

        ranked = sorted(
            [{"score": scores[i], "chunk": chunks[i]} for i in range(N) if scores[i] > 0],
            key=lambda x: x["score"],
            reverse=True,
        )

        return [item["chunk"] for item in ranked[:top_k]]


def recall_memory(query: str) -> str:
    """
    Search past debugging sessions, saved concepts, and architectural docs
    using the pure-Python Okapi BM25 ranking engine.
    """
    retriever = BM25Retriever()
    results = retriever.search(query, top_k=3)
    if not results:
        return f"No relevant episodic memories found for query: '{query}'."

    output_lines = [f"Found {len(results)} relevant episodic memory items:"]
    for idx, r in enumerate(results, 1):
        output_lines.append(f"\n[{idx}] (Source: {r['source']})")
        output_lines.append(r["content"])

    return "\n".join(output_lines)

