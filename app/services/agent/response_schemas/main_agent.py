MAIN_AGENT_JSON_SCHEMA = {
            "format": {
                "type": "json_schema",
                "name": "AgentResult",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "numbers": {"type": "array", "items": {"type": "number"}},
                        "is_error": {"type": "boolean"},
                        "error_detail": {"type": ["string", "null"]}
                    },
                    "required": ["numbers", "is_error", "error_detail"]
            }
    }
}