Analyze the following move entries and return JSON matching the required schema.

Payload:
{payload_json}

Output formatting requirements (mandatory):
- Return exactly one fenced JSON block that validates against this schema:
  ```json
  {{
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": false,
    "required": ["moves"],
    "properties": {{
      "moves": {{
        "type": "array",
        "minItems": 1,
        "items": {{
          "type": "object",
          "additionalProperties": false,
          "required": [
            "ply",
            "classification",
            "best_uci",
            "pv",
            "suggestion",
            "explanation",
            "confidence",
            "themes"
          ],
          "properties": {{
            "ply": {{
              "type": "integer",
              "minimum": 1
            }},
            "classification": {{
              "type": "string",
              "enum": ["best", "good", "inaccuracy", "mistake", "blunder"]
            }},
            "best_uci": {{
              "type": "string",
              "pattern": "^[a-h][1-8][a-h][1-8][qrbn]?$"
            }},
            "pv": {{
              "type": "array",
              "maxItems": 8,
              "items": {{
                "type": "string",
                "pattern": "^[a-h][1-8][a-h][1-8][qrbn]?$"
              }}
            }},
            "suggestion": {{
              "type": "string",
              "minLength": 1,
              "maxLength": 280
            }},
            "explanation": {{
              "type": "string",
              "minLength": 1,
              "maxLength": 320
            }},
            "confidence": {{
              "type": "number",
              "minimum": 0,
              "maximum": 1
            }},
            "themes": {{
              "type": "array",
              "maxItems": 4,
              "items": {{
                "type": "string",
                "minLength": 1,
                "maxLength": 48
              }}
            }}
          }}
        }}
      }}
    }}
  }}
  ```
- Do not output any text before or after the fenced JSON block.
- Required top-level key: `moves`.
- `moves` must be an array of objects keyed by `ply`.
