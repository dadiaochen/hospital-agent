type PageHeaderProps = {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
};

export function PageHeader({
  eyebrow,
  title,
  description,
  children,
}: PageHeaderProps) {
  return (
    <header className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#0f766e]">
            {eyebrow}
          </p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-[#173c38] sm:text-3xl">
            {title}
          </h2>
          <p className="mt-3 text-sm leading-6 text-[#64748b]">{description}</p>
        </div>
        {children ? <div>{children}</div> : null}
      </div>
    </header>
  );
}
