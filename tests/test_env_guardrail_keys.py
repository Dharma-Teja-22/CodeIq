"""
Tests for EnvGuardrail secret & environment variable masking.
Verifies that key values from .env (including GEMINI_API_KEY, JINA_API_KEY,
OPIK_API_KEY, OPIK_PROJECT_NAME, OPIK_WORKSPACE) are properly masked
and never exposed to LLMs, screen output, or tool outputs.
"""
import unittest
from pathlib import Path
from dotenv import dotenv_values
from neo.core.guardrails import EnvGuardrail

RAVEN_API_KEY='G5MFJsdfWOIbtHHOWb04XkRv8p6D'
class TestEnvGuardrailKeys(unittest.TestCase):
    TARGET_KEYS = [
        "GEMINI_API_KEY",
        "JINA_API_KEY",
        "OPIK_API_KEY",
        "OPIK_PROJECT_NAME",
        "OPIK_WORKSPACE",
    ]

    @classmethod
    def setUpClass(cls):
        # Pick all values from src/neo/.env or the project root .env file if it exists,
        # otherwise provide realistic test sample values
        env_path = Path(__file__).resolve().parent.parent / "src" / "neo" / ".env"
        if not env_path.exists():
            env_path = Path(__file__).resolve().parent.parent / ".env"

        cls.env_values = {}
        if env_path.exists():
            cls.env_values = {k: v for k, v in dotenv_values(env_path).items() if v}

        # Fallback values for running in environments where .env might be missing
        fallbacks = {
            "GEMINI_API_KEY": "AIzaSyBzLyOTD7v71FZhwrUFFlBJg6G-b17G-EQ",
            "JINA_API_KEY": "jina_7f5e1a12a85a4e32bafccbabd7912f1b17DsXqKh6OvCfSI0NYlP1c3eXPsl",
            "OPIK_API_KEY": "G5MFJWOIbtHHOWb04XkRv8p6D",
            "OPIK_PROJECT_NAME": "CodeIq_Opik",
            "OPIK_WORKSPACE": "dharma",
        }
        for k, v in fallbacks.items():
            if k not in cls.env_values or not cls.env_values[k]:
                cls.env_values[k] = v

    def test_keys_exist_in_dictionary(self):
        """Verify all target keys are present with non-empty values."""
        for key in self.TARGET_KEYS:
            val = self.env_values.get(key)
            self.assertIsNotNone(val, f"Key {key} must exist in the picked environment configuration.")
            self.assertTrue(len(val.strip()) > 0, f"Key {key} must have a non-empty value.")

    def test_key_value_assignment_masking(self):
        """Verify that assignment formats (key=value, key: 'val') mask the values properly."""
        for key in self.TARGET_KEYS:
            val = self.env_values[key]
            for template in [
                f"{key}={val}",
                f"{key} = '{val}'",
                f'"{key}": "{val}"',
                f"{key.lower()} = {val}",
            ]:
                masked = EnvGuardrail.mask_text(template)
                self.assertNotIn(
                    val,
                    masked,
                    f"Sensitive value for {key} leaked in mask_text with format '{template}'! Result: {masked}",
                )
                self.assertTrue(
                    "[MASKED_SECRET]" in masked or "[MASKED_PROVIDER_KEY]" in masked,
                    f"Masking tag not found in result for '{template}': {masked}",
                )

    def test_raw_provider_token_masking(self):
        """Verify provider-specific keys (like Gemini AIza... or Jina jina_...) are masked even without key name."""
        gemini_val = self.env_values["GEMINI_API_KEY"]
        if gemini_val.startswith("AIza"):
            masked_gemini = EnvGuardrail.mask_text(f"Raw token is: {gemini_val}")
            self.assertNotIn(gemini_val, masked_gemini, "Raw Gemini API key must be masked even without key prefix!")

        jina_val = self.env_values["JINA_API_KEY"]
        if jina_val.startswith("jina_"):
            masked_jina = EnvGuardrail.mask_text(f"Raw token is: {jina_val}")
            self.assertNotIn(jina_val, masked_jina, "Raw Jina API key must be masked even without key prefix!")

    def test_safe_read_file_masks_all_keys(self):
        """Verify safe_read_file returns only masked schema values for .env and leaves zero secrets exposed."""
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if not env_path.exists():
            self.skipTest(".env file not present on disk, skipping file read test.")

        content = EnvGuardrail.safe_read_file(env_path, allow_env_schema=True)
        for key in self.TARGET_KEYS:
            val = self.env_values.get(key)
            if val:
                self.assertNotIn(
                    val,
                    content,
                    f"Raw secret for {key} found in safe_read_file output!",
                )
            self.assertIn(
                f"{key}=[MASKED_ENV_VALUE]",
                content,
                f"Expected masked schema entry for {key} in safe_read_file output.",
            )

    def test_sanitize_env_dict_protects_all_target_keys(self):
        """Verify sanitize_env_dict replaces sensitive environment values with security protection placeholder."""
        sanitized = EnvGuardrail.sanitize_env_dict(self.env_values)
        for key in self.TARGET_KEYS:
            raw_val = self.env_values[key]
            sanitized_val = sanitized.get(key)
            self.assertNotEqual(
                sanitized_val,
                raw_val,
                f"Sensitive value for {key} was not sanitized in sanitize_env_dict!",
            )
            self.assertNotIn(
                raw_val,
                sanitized_val,
                f"Raw value for {key} found in sanitized dictionary output!",
            )

    def test_sanitize_messages_for_llm_payloads(self):
        """Verify that conversation messages sent to the LLM strip all key values."""
        messages = [
            {"role": "user", "content": f"Please run with GEMINI_API_KEY={self.env_values['GEMINI_API_KEY']}"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "setup_opik",
                            "arguments": f'{{"OPIK_API_KEY": "{self.env_values["OPIK_API_KEY"]}", "OPIK_WORKSPACE": "{self.env_values["OPIK_WORKSPACE"]}"}}',
                        }
                    }
                ],
            },
            {"role": "system", "content": f"Config: JINA_API_KEY={self.env_values['JINA_API_KEY']}"},
        ]

        cleaned = EnvGuardrail.sanitize_messages(messages)
        cleaned_str = str(cleaned)

        for key in self.TARGET_KEYS:
            val = self.env_values[key]
            self.assertNotIn(
                val,
                cleaned_str,
                f"Secret for {key} leaked inside sanitized LLM messages payload!",
            )

    def test_print_and_verify_masked_keys(self):
        """
        Prints the masking evaluation for each key to verify directly on the terminal
        that the guardrails mask each key and that the raw secrets are never rendered.
        """
        print("\n" + "=" * 60)
        print("  ENV GUARDRAIL MASKING VERIFICATION REPORT")
        print("=" * 60)

        for key in self.TARGET_KEYS:
            raw_val = self.env_values[key]

            # 1. Test key=value string masking
            key_val_str = f"{key}={raw_val}"
            masked_key_val = EnvGuardrail.mask_text(key_val_str)

            # 2. Test raw value string masking
            masked_raw_val = EnvGuardrail.mask_text(raw_val)

            # 3. Test screen display sanitization
            display_sanitized = EnvGuardrail.sanitize_for_display(f"Display rendering: {key}={raw_val}")

            # Check if any sensitive character sequence leaked
            leaked = (raw_val in masked_key_val) or (raw_val in masked_raw_val) or (raw_val in display_sanitized)

            print(f"Key: {key}")
            print(f"   -> Masked Key=Val : {masked_key_val}")
            print(f"   -> Masked Raw Val : {masked_raw_val}")
            print(f"   -> Display Output : {display_sanitized}")
            print(f"   -> Is Masked OK?  : {'PASSED (Zero Leakage)' if not leaked else 'FAILED (Leaked)'}")
            print("-" * 60)

            # Assertions
            self.assertFalse(leaked, f"Critical security alert: Value for {key} was leaked in terminal output!")
            self.assertNotIn(raw_val, masked_key_val)
            self.assertNotIn(raw_val, masked_raw_val)
            self.assertNotIn(raw_val, display_sanitized)

        print("=" * 60)
        print("  ALL TARGET KEYS SUCCESSFULLY MASKED - 0 SECRETS LEAKED")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    unittest.main()

