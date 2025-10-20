MAIN_AGENT_JSON_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "AgentResult",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "lot_ids": {
                    "type": "array",
                    "description": "Lot IDs of vehicles that you choose (ONLY UNIQUE VALUES)",
                    "minItems": 25,
                    "maxItems": 30,
                    "items": {"type": "integer"}
                },
                "is_error": {"type": "boolean"},
                "error_detail": {"type": ["string", "null"]}
            },
            "required": ["lot_ids", "is_error", "error_detail"]
        }
    }
}