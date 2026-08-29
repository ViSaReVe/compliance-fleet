import "./Legend.css";

const ITEMS = [
  { swatch: "legend-swatch--pulse", label: "Pulsing node", detail: "that agent is actively working" },
  { swatch: "legend-swatch--sweep", label: "Moving dot", detail: "control handed to another agent" },
  { swatch: "legend-swatch--blip", label: "Red flash", detail: "Model Armor or Agent Gateway blocked something" },
];

export default function Legend() {
  return (
    <div className="legend">
      {ITEMS.map((item) => (
        <div className="legend-item" key={item.label}>
          <span className={`legend-swatch ${item.swatch}`} />
          <span className="legend-text">
            <strong>{item.label}</strong> — {item.detail}
          </span>
        </div>
      ))}
    </div>
  );
}
