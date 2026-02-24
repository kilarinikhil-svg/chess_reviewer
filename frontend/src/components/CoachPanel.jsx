import { useState } from "react";

export default function CoachPanel({ onAnalyze, loading, report }) {
  const [pgn, setPgn] = useState("");
  const [username, setUsername] = useState("");

  async function submit(event) {
    event.preventDefault();
    await onAnalyze({ pgn, username: username || null });
  }

  return (
    <section className="panel coach-panel">
      <h2>Coach</h2>
      <p>Paste multiple games and get recurring mistakes, trends, and a 7-day action plan.</p>
      <form onSubmit={submit}>
        <label htmlFor="coach-username">Player username (optional)</label>
        <input
          id="coach-username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="nikhil_kilari"
        />
        <label htmlFor="coach-pgn">Multi-game PGN</label>
        <textarea
          id="coach-pgn"
          rows={14}
          value={pgn}
          onChange={(event) => setPgn(event.target.value)}
          placeholder="Paste one or many PGN games here"
        />
        <button type="submit" disabled={loading || !pgn.trim()}>
          Analyze Trends
        </button>
      </form>

      {report && (
        <div className="coach-results">
          <h3>Top recurring mistakes</h3>
          {report.top_mistakes.length === 0 ? (
            <p>No repeated patterns detected from current data.</p>
          ) : (
            report.top_mistakes.map((mistake) => (
              <article key={mistake.key} className="coach-card">
                <strong>{mistake.label}</strong>
                <p>
                  {mistake.count} occurrences · {mistake.description}
                </p>
                <ul>
                  {mistake.examples.map((example) => (
                    <li key={example}>{example}</li>
                  ))}
                </ul>
              </article>
            ))
          )}

          <h3>Phase breakdown</h3>
          <p>
            Opening: {report.phase_breakdown.opening} · Middlegame: {report.phase_breakdown.middlegame} · Endgame: {report.phase_breakdown.endgame}
          </p>

          <h3>White vs Black split</h3>
          <div className="coach-split-grid">
            {Object.entries(report.color_stats).map(([color, stats]) => (
              <div key={color} className="coach-card">
                <strong>{color}</strong>
                <p>
                  Games: {stats.games} | W: {stats.wins} L: {stats.losses} D: {stats.draws}
                </p>
              </div>
            ))}
          </div>

          <h3>Action plan (next 7 days)</h3>
          {report.action_plan.map((item) => (
            <article key={item.focus} className="coach-card">
              <strong>{item.focus}</strong>
              <ul>
                {item.drills.map((drill) => (
                  <li key={drill}>{drill}</li>
                ))}
              </ul>
            </article>
          ))}

          <h3>Next-game focus checklist</h3>
          <ul>
            {report.next_game_focus.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
