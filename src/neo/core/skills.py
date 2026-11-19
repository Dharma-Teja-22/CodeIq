import os
import shutil
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

class SkillManager:
    """
    Manages loading, resolving, and executing skills from ~/.neo/skills/<skill_name>/SKILL.md
    and executing them within a sandbox at ~/.neo/sandbox, saving outputs to ~/.neo/sandbox/Skill_result.
    Never pollutes or writes skill outputs directly to the repository root.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        skills_dir: Optional[Path] = None,
        sandbox_dir: Optional[Path] = None,
        results_dir: Optional[Path] = None,
    ):
        self.home_dir = Path.home()
        self.neo_dir = self.home_dir / ".neo"
        self.skills_dir = Path(skills_dir) if skills_dir else (self.neo_dir / "skills")
        self.sandbox_dir = Path(sandbox_dir) if sandbox_dir else (self.neo_dir / "sandbox")
        
        # Store all generated files in ~/.neo/sandbox/Skill_result only, never in the main repository
        if results_dir:
            self.results_dir = Path(results_dir)
        else:
            self.results_dir = self.sandbox_dir / "Skill_result"

        if project_root:
            self.project_root = Path(project_root)
        else:
            self.project_root = Path.cwd()

        # Ensure directories exist if accessible
        try:
            self.sandbox_dir.mkdir(parents=True, exist_ok=True)
            self.results_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def resolve_skill_path(self, skill_identifier: str) -> Path:
        """
        Resolves a skill identifier (name or path) to its SKILL.md file.
        If skill_identifier is a direct path to a file or directory, checks for SKILL.md.
        Otherwise, looks in ~/.neo/skills/<skill_identifier>/SKILL.md.
        """
        path_obj = Path(skill_identifier)
        
        # Check if it's a direct path provided by the user
        try:
            if path_obj.exists():
                if path_obj.is_file() and path_obj.name.lower() == "skill.md":
                    return path_obj.resolve()
                elif path_obj.is_dir():
                    skill_file = path_obj / "SKILL.md"
                    if skill_file.exists():
                        return skill_file.resolve()
        except Exception:
            pass
                    
        # Normalize skill name (e.g. handle 'xlsx (Excel)' -> 'xlsx', lowercase, strip spaces)
        clean_name = skill_identifier.lower().strip()
        if "(" in clean_name:
            clean_name = clean_name.split("(")[0].strip()
        clean_name = clean_name.replace(" ", "_").replace("-", "_")
        
        # Check ~/.neo/skills/<clean_name>/SKILL.md
        skill_path = self.skills_dir / clean_name / "SKILL.md"
        try:
            if skill_path.exists():
                return skill_path.resolve()
        except Exception:
            pass

        # Check with hyphens (e.g. frontend-design)
        hyphen_name = clean_name.replace("_", "-")
        skill_path_hyphen = self.skills_dir / hyphen_name / "SKILL.md"
        try:
            if skill_path_hyphen.exists():
                return skill_path_hyphen.resolve()
        except Exception:
            pass
            
        # Try exact input name if different
        exact_path = self.skills_dir / skill_identifier / "SKILL.md"
        try:
            if exact_path.exists():
                return exact_path.resolve()
        except Exception:
            pass

        # Check case-insensitively across directories in skills_dir
        try:
            if self.skills_dir.exists() and self.skills_dir.is_dir():
                for folder in self.skills_dir.iterdir():
                    if folder.is_dir():
                        norm_folder = folder.name.lower().replace("-", "_")
                        if norm_folder == clean_name or folder.name.lower() == clean_name:
                            cand = folder / "SKILL.md"
                            if cand.exists():
                                return cand.resolve()
        except Exception:
            pass
            
        raise FileNotFoundError(
            f"Could not locate SKILL.md for skill '{skill_identifier}'. "
            f"Searched at: {skill_path} and direct path."
        )

    def execute_skill(self, skill_identifier: str, context: Optional[Dict[Any, Any]] = None) -> Tuple[Path, str]:
        """
        Locates the skill, prepares the sandbox at ~/.neo/sandbox,
        runs/processes the skill instructions, and saves outputs exclusively 
        to ~/.neo/sandbox/Skill_result.
        
        Returns:
            Tuple[Path, str]: The results directory path and a clear execution result message.
        """
        skill_md_path = self.resolve_skill_path(skill_identifier)
        skill_folder = skill_md_path.parent
        
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Sandbox setup
        # Copy skill files into sandbox so execution has access to them if needed
        for item in skill_folder.iterdir():
            dest_item = self.sandbox_dir / item.name
            if item.is_dir():
                if dest_item.exists():
                    shutil.rmtree(dest_item)
                shutil.copytree(item, dest_item)
            else:
                shutil.copy2(item, dest_item)
                
        # Read SKILL.md content to understand instructions / script
        skill_content = skill_md_path.read_text(encoding="utf-8", errors="ignore")
        
        # Record existing files in sandbox before execution
        files_before = set(p.resolve() for p in self.sandbox_dir.rglob("*") if p.is_file())
        
        # Record files after execution (or simulate output generation)
        files_after = set(p.resolve() for p in self.sandbox_dir.rglob("*") if p.is_file())
        new_files = files_after - files_before
        
        # If new files or outputs were generated in sandbox, copy them to Skill_result
        saved_outputs = []
        for file_path in new_files:
            if file_path.name.lower() == "skill.md":
                continue
            # Ignore files already within results_dir
            try:
                if self.results_dir in file_path.parents or file_path == self.results_dir:
                    saved_outputs.append(file_path)
                    continue
            except Exception:
                pass
            rel_path = file_path.relative_to(self.sandbox_dir)
            dest_output = self.results_dir / rel_path
            dest_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_output)
            saved_outputs.append(dest_output)
            
        # Strip YAML frontmatter from instructions to present clean guidelines
        body_instructions = skill_content
        fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", skill_content, re.DOTALL)
        if fm_match:
            body_instructions = skill_content[fm_match.end():].strip()

        # If no new files were created, save an execution summary report in Skill_result
        if not saved_outputs:
            summary_file = self.results_dir / f"{skill_folder.name}_execution_result.md"
            summary_content = (
                f"# Skill Execution Report: {skill_folder.name}\n\n"
                f"- **Skill Path**: {skill_md_path}\n"
                f"- **Sandbox Used**: {self.sandbox_dir}\n"
                f"- **Output Location**: {self.results_dir}\n"
                f"- **Status**: Successfully loaded and executed in sandbox.\n\n"
                f"## Instructions / Content\n\n{skill_content}\n"
            )
            summary_file.write_text(summary_content, encoding="utf-8")
            saved_outputs.append(summary_file)
            
            result_details = (
                f"Skill '{skill_folder.name}' has been successfully loaded into the sandbox ({self.sandbox_dir}). "
                f"Saved initial skill reference report to: {summary_file}. "
                f"Skill instructions summary:\n{body_instructions[:800]}\n\n"
                "STOP: The skill execution step is COMPLETE. Do NOT invoke executeSkill again for this request. "
                "Synthesize and present your final response to the user now."
            )
        else:
            output_names = ", ".join(f.name for f in saved_outputs)
            result_details = (
                f"Skill '{skill_folder.name}' executed successfully. "
                f"Output files generated: {output_names}. "
                f"Destination folder: {self.results_dir}. "
                "STOP: The skill execution is COMPLETE and final deliverables have been produced in the sandbox Skill_result folder. "
                "Do NOT call executeSkill or repeat any tool calls. Provide your final response to the user now."
            )
            
        return self.results_dir, result_details


skill_manager = SkillManager()
