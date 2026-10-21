import React from "react";

export interface NavItem {
  href: string;
  label: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export interface AppShellProps {
  brand: React.ReactNode;
  groups: NavGroup[];
  currentPath: string;
  /** Link component, e.g. next/link. Defaults to a plain anchor. */
  linkAs?: React.ElementType;
  banner?: React.ReactNode;
  sidebarFooter?: React.ReactNode;
  children: React.ReactNode;
}

/** Owner layout: grouped sidebar from 768px, horizontally scrolling tab bar below. */
export function AppShell({
  brand,
  groups,
  currentPath,
  linkAs: Link = "a",
  banner,
  sidebarFooter,
  children,
}: AppShellProps) {
  const link = (item: NavItem, className: string) => {
    const current = item.href === currentPath;
    return (
      <Link
        key={item.href}
        href={item.href}
        aria-current={current ? "page" : undefined}
        className={`${className} ${current ? "bg-ink text-paper" : "text-ink hover:bg-paper"}`}
      >
        {item.label}
      </Link>
    );
  };

  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      {banner}
      <header className="flex items-center justify-between gap-3 border-b border-line bg-paper-2 px-4 py-3 md:hidden">
        {brand}
        {sidebarFooter}
      </header>
      <div className="flex flex-1">
        <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-paper-2 px-4 py-5 md:flex">
          {brand}
          <nav aria-label="Main" className="mt-4 flex-1 space-y-4">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
                  {group.label}
                </p>
                <div className="space-y-0.5">
                  {group.items.map((item) =>
                    link(item, "block rounded-lg px-2 py-2 text-sm font-medium"),
                  )}
                </div>
              </div>
            ))}
          </nav>
          {sidebarFooter}
        </aside>
        <main className="min-w-0 flex-1 px-4 pb-24 pt-6 sm:px-8 md:pb-8">{children}</main>
      </div>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 flex gap-1 overflow-x-auto border-t border-line bg-paper-2 px-2 py-2 md:hidden"
      >
        {groups.flatMap((group) => group.items).map((item) =>
          link(item, "whitespace-nowrap rounded-full px-3 py-2 text-xs font-semibold"),
        )}
      </nav>
    </div>
  );
}
