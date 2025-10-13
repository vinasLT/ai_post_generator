MAIN_AGENT_JSON_SCHEMA = {
            "format": {
                "type": "json_schema",
                "name": "AgentResult",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "lot_ids": {"type": "array", "items": {"type": "number"}, "minItems": 25},
                        "is_error": {"type": "boolean"},
                        "error_detail": {"type": ["string", "null"]}
                    },
                    "required": ["lot_ids", "is_error", "error_detail"]
            }
    }
}