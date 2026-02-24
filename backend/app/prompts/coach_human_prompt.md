Player summary:
{payload_json}

Use the provided aggregate evidence only. Keep advice concrete and training-oriented.

Output formatting requirements (mandatory):
- Return exactly one fenced JSON block using this format:
  ```json
  {{ ... }}
  ```
- Do not output any text before or after the fenced JSON block.
- Required top-level keys: `top_mistakes`, `action_plan`, `next_game_focus`.
- `top_mistakes`: array (1-3) of objects with keys `label`, `count`, `description`, `fix`, `evidence`.
- `count` must be an integer >= 0.
- `evidence` must be an array of short strings.
- `action_plan`: array (1-3) of objects with keys `focus`, `drills` (`drills` must be an array of short strings).
- `next_game_focus`: array of exactly 3 short checklist strings.
