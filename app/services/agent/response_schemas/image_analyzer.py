IMAGE_ANALYZER_RESPONSE_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "ImageAnalyzerResponse",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Brief description of the car in the image in 1-2 sentences"
                },
                "condition_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "Car condition rating on a 10-point scale (0 - completely destroyed, 10 - perfect condition)"
                }
            },
            "required": ["description", "condition_score"],
            "additionalProperties": False
        }
    }
}