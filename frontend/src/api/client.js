const API_BASE = import.meta.env.VITE_API_BASE || "";

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

export const api = {
  importPgn(payload) {
    return fetch(`${API_BASE}/api/games/import/pgn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(parseResponse);
  },
  fetchArchives(username) {
    return fetch(`${API_BASE}/api/games/import/chesscom`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    }).then(parseResponse);
  },
  selectChessComGame(archive_url, game_index) {
    return fetch(`${API_BASE}/api/games/import/chesscom/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ archive_url, game_index }),
    }).then(parseResponse);
  },
  analyzeMove(payload) {
    return fetch(`${API_BASE}/api/analysis/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(parseResponse);
  },
  startFullAnalysis(payload) {
    return fetch(`${API_BASE}/api/analysis/full`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(parseResponse);
  },
  getFullStatus(jobId) {
    return fetch(`${API_BASE}/api/analysis/full/${jobId}`).then(parseResponse);
  },
  analyzeCoach(payload) {
    return fetch(`${API_BASE}/api/coach/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(parseResponse);
  },
};
