import React from "react";
import type { LineChoice } from "ui";

/** Leave-outs are loud so a cook cannot miss them; picks carry their group so two "Medium" differ. */
export function KitchenChoices({ choices }: { choices?: LineChoice[] }) {
  if (!choices || choices.length === 0) return null;
  return (
    <ul className="mt-1.5 space-y-0.5 text-right text-sm">
      {choices.map((c) =>
        c.kind === "leave_out" ? (
          <li key={c.choice_id ?? c.label} className="font-black uppercase text-kds-warn">
            NO {c.label}
          </li>
        ) : (
          <li key={c.choice_id ?? c.label} className="text-cream">
            {c.kind === "pick" && c.group ? `${c.group}: ${c.label}` : c.label}
          </li>
        ),
      )}
    </ul>
  );
}
