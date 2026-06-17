type PagePanelProps = {
  title: string;
  description: string;
  items?: string[];
};

export function PagePanel({ title, description, items = [] }: PagePanelProps) {
  return (
    <section className="rounded-md border border-[#d9e5e1] bg-white p-6">
      <div className="max-w-3xl">
        <p className="text-sm font-medium text-clinic">Phase 1</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-normal">{title}</h2>
        <p className="mt-3 text-sm leading-6 text-[#475569]">{description}</p>
      </div>
      {items.length > 0 ? (
        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {items.map((item) => (
            <div className="rounded-md border border-[#e2e8f0] bg-[#fbfdfc] p-4 text-sm text-[#334155]" key={item}>
              {item}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

