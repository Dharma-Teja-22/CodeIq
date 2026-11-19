import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import yaml
except ImportError:
    yaml = None


class SkillMap:
    """
    Scans the skills directory (default: ~/.neo/skills) and extracts
    skill metadata (name, description, file path) from each SKILL.md.
    Provides structured summaries and system prompt integration similar to RepoMap.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        else:
            self.skills_dir = Path.home() / ".neo" / "skills"

    def scan_skills(self) -> List[Dict[str, str]]:
        """
        Dynamically scan skill folders under skills_dir and load
        skill name, description, and file path from each SKILL.md.

        Returns:
            List[Dict[str, str]]: Sorted list of dictionaries with 'name', 'description', and 'path'.
        """
        skills: List[Dict[str, str]] = []
        try:
            if not self.skills_dir.exists() or not self.skills_dir.is_dir():
                return skills
        except Exception:
            return skills

        try:
            items = sorted(self.skills_dir.iterdir(), key=lambda p: p.name.lower())
        except Exception:
            return skills

        # Sort folder names in sequence order
        for item in items:
            try:
                if item.is_dir():
                    skill_md = item / "SKILL.md"
                    # Case-insensitive check if SKILL.md exists
                    if not skill_md.exists():
                        matches = list(item.glob("[sS][kK][iI][lL][lL].[mM][dD]"))
                        if matches:
                            skill_md = matches[0]
                        else:
                            continue

                    info = self._parse_skill_md(skill_md, folder_name=item.name)
                    if info:
                        skills.append(info)
            except Exception:
                continue

        return skills

    def _parse_skill_md(self, skill_file: Path, folder_name: str) -> Optional[Dict[str, str]]:
        """
        Extracts skill name and description from the frontmatter
        or header of a SKILL.md file.
        """
        try:
            content = skill_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        name = folder_name
        description = ""

        # Check for frontmatter enclosed in ---
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if frontmatter_match:
            frontmatter_raw = frontmatter_match.group(1)
            parsed_dict = None
            if yaml is not None:
                try:
                    loaded = yaml.safe_load(frontmatter_raw)
                    if isinstance(loaded, dict):
                        parsed_dict = loaded
                except Exception:
                    pass

            if parsed_dict:
                if "name" in parsed_dict and parsed_dict["name"]:
                    name = str(parsed_dict["name"]).strip()
                if "description" in parsed_dict and parsed_dict["description"]:
                    description = str(parsed_dict["description"]).strip()
            else:
                # Robust regex-based extraction for name and description
                name_match = re.search(r"^name:\s*[\"']?(.*?)[\"']?\s*$", frontmatter_raw, re.MULTILINE)
                if name_match:
                    name = name_match.group(1).strip()
                
                # Multi-line or single-line description
                desc_match = re.search(
                    r"^description:\s*(?:\"([^\"]*)\"|'([^']*)'|(.*(?:\n\s+.*)*))",
                    frontmatter_raw,
                    re.MULTILINE,
                )
                if desc_match:
                    raw_desc = desc_match.group(1) or desc_match.group(2) or desc_match.group(3) or ""
                    # Clean up indented continuation lines
                    lines = [l.strip() for l in raw_desc.splitlines() if l.strip()]
                    description = " ".join(lines).strip().strip('"').strip("'")

        # If description is still empty, look for the first markdown paragraph
        if not description:
            body = content[frontmatter_match.end():] if frontmatter_match else content
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith("#")]
            if paragraphs:
                description = paragraphs[0].replace("\n", " ")

        return {
            "name": name,
            "description": description,
            "path": str(skill_file.resolve()),
        }

    def get_skills_prompt(self) -> str:
        """
        Format the loaded skills into a sequence order string suitable for inclusion in the system prompt.
        """
        skills = self.scan_skills()
        if not skills:
            return "No specialized skills currently available."

        lines = ["Available Skills:"]
        for idx, s in enumerate(skills, start=1):
            lines.append(f"{idx}. Skill Name: {s['name']}")
            lines.append(f"   Path: {s['path']}")
            lines.append(f"   Description: {s['description']}")

        return "\n".join(lines)


# Global helper functions for easy access
def get_available_skills(skills_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    return SkillMap(skills_dir=skills_dir).scan_skills()


def get_skills_prompt(skills_dir: Optional[Path] = None) -> str:
    return SkillMap(skills_dir=skills_dir).get_skills_prompt()
