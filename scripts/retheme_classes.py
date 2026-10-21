"""One-off: replace hard-coded colour classes with design-system tokens. Deleted after use."""

import re
import sys
from pathlib import Path

NN = r"(?:/\d+)?"  # optional opacity suffix

# Light theme (guest app, owner dashboard, login, landing). Order matters: specific first.
LIGHT = [
    (r"glass-panel", "mise-card"),
    (r"gradient-text", "text-terracotta"),
    (rf"text-\[#8FA3B3\]{NN}", "text-ink-muted"),
    (rf"text-\[#F3F8FC\]{NN}", "text-ink"),
    (rf"bg-\[#070B10\]{NN}", "bg-paper"),
    (r"via-\[#070B10\]", "via-paper"),
    (rf"bg-\[#0D141B\]{NN}", "bg-card"),
    (r"from-\[#0D141B\]", "from-card"),
    (r"to-\[#0D141B\]", "to-card"),
    (rf"bg-\[#38BDF8\]{NN}", "bg-paper-2"),
    (rf"(border|divide)-\[#38BDF8\]{NN}", r"\1-line"),
    (rf"text-\[#(?:22D3EE|2F7BFF)\]", "text-terracotta"),
    (rf"bg-\[#(?:22D3EE|2F7BFF)\]{NN}", "bg-terracotta/10"),
    (rf"(border|ring)-\[#(?:22D3EE|2F7BFF)\]{NN}", r"\1-terracotta"),
    (r"from-\[#2F7BFF\]", "from-terracotta"),
    (r"to-\[#22D3EE\]", "to-terracotta"),
    (r"text-\[#FF9F2E\]", "text-warn-fg"),
    (rf"bg-\[#FF9F2E\]{NN}", "bg-warn-bg"),
    (rf"border-\[#FF9F2E\]{NN}", "border-warn-fg/30"),
    (r"text-\[#EF4444\]", "text-danger-fg"),
    (r"bg-\[#EF4444\]/\d+", "bg-danger-bg"),
    (r"bg-\[#EF4444\]", "bg-danger-fg"),
    (rf"(border|ring)-\[#EF4444\]{NN}", r"\1-danger-fg"),
    (r"text-\[#34D399\]", "text-olive"),
    (r"bg-\[#34D399\]/\d+", "bg-safe-bg"),
    (r"bg-\[#34D399\]", "bg-olive"),
    (rf"border-\[#34D399\]{NN}", "border-olive"),
    (r"bg-\[#F59E0B\]", "bg-warn-fg"),
    (r"text-\[#070B10\]", "text-cream"),
    (r"bg-\[#F3F8FC\]", "bg-ink"),
    (r"text-zinc-(?:50|100|200)", "text-ink"),
    (r"text-zinc-(?:300|400|500|600|700)", "text-ink-muted"),
    (r"text-zinc-950", "text-cream"),
    (rf"bg-zinc-950{NN}", "bg-paper"),
    (rf"bg-zinc-900{NN}", "bg-card"),
    (rf"bg-zinc-(?:600|700|800){NN}", "bg-paper-2"),
    (rf"(border|divide)-zinc-\d+{NN}", r"\1-line"),
    (rf"bg-emerald-950{NN}", "bg-safe-bg"),
    (r"bg-emerald-400", "bg-olive"),
    (rf"bg-emerald-\d+{NN}", "bg-terracotta"),
    (r"text-emerald-\d+", "text-terracotta"),
    (rf"(border|ring)-emerald-\d+{NN}", r"\1-terracotta"),
    (rf"bg-(?:rose|red)-(?:900|950){NN}", "bg-danger-bg"),
    (rf"bg-(?:rose|red)-\d+{NN}", "bg-danger-fg"),
    (r"text-(?:rose|red)-\d+", "text-danger-fg"),
    (rf"border-(?:rose|red)-\d+{NN}", "border-danger-fg/40"),
    (rf"bg-amber-950{NN}", "bg-warn-bg"),
    (rf"bg-amber-\d+{NN}", "bg-warn-fg"),
    (r"text-amber-\d+", "text-warn-fg"),
    (rf"border-amber-\d+{NN}", "border-warn-fg/30"),
    (r"text-blue-\d+", "text-terracotta"),
    (rf"bg-blue-\d+{NN}", "bg-paper-2"),
    (r"border-blue-\d+", "border-terracotta"),
    (rf"shadow-(?:cyan|emerald|blue|sky)-\d+{NN}", "shadow-ink/10"),
    (rf"bg-black{NN}", "bg-ink/40"),
    (r"text-white", "text-cream"),
]

# Kitchen display (dark). Text on kds accents is espresso; fixed by hand in a later task.
KDS = [
    (rf"bg-\[#070B10\]{NN}", "bg-espresso"),
    (rf"bg-\[#0D141B\]{NN}", "bg-kds-card"),
    (r"text-\[#F3F8FC\]", "text-cream"),
    (rf"text-\[#8FA3B3\]{NN}", "text-kds-muted"),
    (rf"(border|divide)-\[#38BDF8\]{NN}", r"\1-cream/10"),
    (r"text-\[#22D3EE\]", "text-kds-accent"),
    (r"text-\[#34D399\]", "text-kds-fresh"),
    (r"bg-\[#34D399\]/\d+", "bg-kds-fresh/20"),
    (rf"border(-l)?-\[#34D399\]{NN}", r"border\1-kds-fresh"),
    (r"text-\[#FF9F2E\]", "text-kds-warn"),
    (rf"bg-\[#FF9F2E\]{NN}", "bg-kds-warn/15"),
    (rf"border-\[#FF9F2E\]{NN}", "border-kds-warn"),
    (r"bg-\[#EF4444\]/\d+", "bg-kds-late/20"),
    (r"bg-\[#EF4444\]", "bg-kds-late"),
    (rf"(border(?:-l)?|ring)-\[#EF4444\]{NN}", r"\1-kds-late"),
    (r"bg-\[#F59E0B\]", "bg-kds-warn"),
    (r"border-l-\[#F59E0B\]", "border-l-kds-warn"),
    (r"text-\[#070B10\]", "text-espresso"),
    (rf"bg-black{NN}", "bg-espresso"),
    (r"text-white", "text-cream"),
    (r"text-black", "text-espresso"),
    (r"bg-white", "bg-cream"),
    (r"text-zinc-(?:100|200)", "text-cream"),
    (r"text-zinc-\d+", "text-kds-muted"),
    (rf"bg-zinc-\d+{NN}", "bg-kds-card"),
    (rf"border-zinc-\d+{NN}", "border-cream/10"),
    (rf"bg-emerald-950{NN}", "bg-kds-fresh/20"),
    (rf"bg-emerald-\d+{NN}", "bg-kds-fresh"),
    (r"text-emerald-\d+", "text-kds-fresh"),
    (rf"(border|ring)-emerald-\d+{NN}", r"\1-kds-fresh"),
    (rf"bg-(?:rose|red)-(?:900|950){NN}", "bg-kds-late/20"),
    (rf"bg-(?:rose|red)-\d+{NN}", "bg-kds-late"),
    (r"text-(?:rose|red)-\d+", "text-kds-late"),
    (rf"border-(?:rose|red)-\d+{NN}", "border-kds-late"),
    (rf"bg-amber-\d+{NN}", "bg-kds-warn"),
    (r"text-amber-\d+", "text-kds-warn"),
]

KITCHEN = {"apps/owner-web/src/app/(kitchen)/kitchen/page.tsx", "apps/owner-web/src/app/(kitchen)/layout.tsx"}
LEFTOVER = re.compile(
    r"\[#[0-9A-Fa-f]{6}\]|(?:zinc|emerald|rose|red|amber|blue|cyan|sky)-\d{2,3}"
    r"|glass-panel|gradient-text"
)


def apply(text: str, rules: list[tuple[str, str]]) -> str:
    for pattern, repl in rules:
        text = re.sub(rf"(?<![\w\[#-]){pattern}(?![\w\]-])", repl, text)
    return text


def main() -> int:
    leftovers = 0
    for path in sorted(Path("apps").glob("*/src/**/*.tsx")):
        rel = path.as_posix()
        old = path.read_text(encoding="utf-8")
        new = apply(old, KDS if rel in KITCHEN else LIGHT)
        if new != old:
            path.write_text(new, encoding="utf-8", newline="\n")
            print(f"updated {rel}")
        for n, line in enumerate(new.splitlines(), 1):
            for m in LEFTOVER.finditer(line):
                leftovers += 1
                print(f"LEFTOVER {rel}:{n}: {m.group(0)}")
    print(f"leftovers: {leftovers}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
